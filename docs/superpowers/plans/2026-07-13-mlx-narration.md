# mlx-lm Narration Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Ollama HTTP narration backend with in-process generation via mlx-lm using `mlx-community/gemma-4-26B-A4B-it-qat-mxfp8`.

**Architecture:** All MLX work (model load + generate) is confined to one module-level `ThreadPoolExecutor(max_workers=1)` in `narration.py`, because MLX binds its GPU stream to the loading thread (`docs/mlx-lm-handover.md` §2.1). `NarrationWorker(QThread)` keeps its existing interface toward `main_window.py` — it builds the prompt, blocks on a future, and emits `done`. The model preloads in the background at app start.

**Tech Stack:** Python 3, PyQt6, mlx-lm (with mlx-vlm fallback for the gemma-4 "unified" architecture), pytest.

**Spec:** `docs/superpowers/specs/2026-07-13-mlx-narration-design.md`

## Global Constraints

- Model repo id: `mlx-community/gemma-4-26B-A4B-it-qat-mxfp8` (an `-it` QAT/mxfp8 conversion — never a base or naive-4-bit model).
- Dependencies: `mlx-lm>=0.31`, `mlx-vlm>=0.6.1`. Keep `requests` (used by `image_gen.py`).
- Every narration failure is emitted through the `done` signal as a short parenthesized string (e.g. `"(model load failed: …)"`); the simulation never blocks or crashes on narrator failure.
- Tests must run without mlx installed and without downloading any model — mock the runtime.
- Tests must not require real PyQt6 — stub it in `sys.modules` before importing `narration`, following the pattern in `test_simulation.py`.
- No Ollama code remains at the end (clean replacement, no backend flag).
- Run tests with `python -m pytest test_narration.py -v` (project convention: flat test files in the repo root).

---

### Task 1: Output cleaning and guards in `narration.py`

Pure text functions, added alongside the existing Ollama code without breaking it.

**Files:**
- Modify: `narration.py` (add `NarratorError`, `check_output`; keep everything else untouched)
- Create: `test_narration.py`

**Interfaces:**
- Produces: `NarratorError(Exception)` — message is shown verbatim in the UI, always wrapped in parentheses.
- Produces: `check_output(text: str) -> str` — cleans raw model output (reasoning-channel markers, code fences) and raises `NarratorError` on empty or repetition-looped output.

- [ ] **Step 1: Write the failing tests**

Create `test_narration.py`:

```python
"""
Unit tests for the mlx-lm narration backend.

narration.py imports PyQt6.QtCore at module level, so we stub Qt in
sys.modules first (same approach as test_simulation.py).  The mlx
runtime itself is always mocked — no model download, mlx not required.

Run with:  python -m pytest test_narration.py
"""

import sys
import types
import threading
from unittest.mock import MagicMock

import pytest

# ── Minimal Qt stubs (narration.py only needs QThread + pyqtSignal) ──────────

def _stub_qt():
    class _QThread:
        def __init__(self, *a, **kw): pass
        def start(self): pass

    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_core.QThread    = _QThread
    qt_core.pyqtSignal = lambda *a: MagicMock()

    pkg = types.ModuleType("PyQt6")
    pkg.QtCore = qt_core
    sys.modules["PyQt6"] = pkg
    sys.modules["PyQt6.QtCore"] = qt_core

_stub_qt()
import narration


# ── check_output: cleaning ────────────────────────────────────────────────────

def test_clean_text_passes_through():
    assert narration.check_output("The moss endures.  ") == "The moss endures."

def test_channel_marker_keeps_text_after_last_marker():
    raw = "<channel|>first thought<channel|>The jar breathes."
    assert narration.check_output(raw) == "The jar breathes."

def test_piped_channel_marker_variant():
    raw = "<|channel|>thought…<|channel|>Silence settles over the glass."
    assert narration.check_output(raw) == "Silence settles over the glass."

def test_code_fences_stripped():
    raw = "```\nA quiet year passes.\n```"
    assert narration.check_output(raw) == "A quiet year passes."


# ── check_output: guards ──────────────────────────────────────────────────────

def test_empty_output_raises():
    with pytest.raises(narration.NarratorError):
        narration.check_output("   ")

def test_channel_only_output_raises():
    with pytest.raises(narration.NarratorError):
        narration.check_output("<channel|>only thoughts, no answer<channel|>")

def test_repetition_loop_raises():
    with pytest.raises(narration.NarratorError):
        narration.check_output("the jar grows own " + "own " * 12)

def test_benign_repetition_passes():
    assert narration.check_output("It rains and rains and rains.") \
        == "It rains and rains and rains."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_narration.py -v`
Expected: all tests FAIL/ERROR with `AttributeError: module 'narration' has no attribute 'check_output'` (or `NarratorError`).

- [ ] **Step 3: Implement `NarratorError` and `check_output`**

In `narration.py`, add below the imports (do not touch `NarrationWorker` or `append_lore` yet):

```python
class NarratorError(Exception):
    """Any narration failure. Message is shown verbatim in the UI."""


# Reasoning-channel close markers seen from gemma-4 family templates
# (docs/mlx-lm-handover.md §2.3) — keep only text after the LAST one.
_CHANNEL_MARKERS = ("<|channel|>", "<channel|>")
_MAX_WORD_RUN = 10   # "own own own …" repetition-loop guard (§3)


def check_output(text: str) -> str:
    """Clean raw model output; raise NarratorError if nothing usable remains."""
    for marker in _CHANNEL_MARKERS:
        if marker in text:
            text = text.rsplit(marker, 1)[-1]
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text:
        raise NarratorError("(narrator produced no usable text)")
    words, run = text.split(), 1
    for prev, cur in zip(words, words[1:]):
        run = run + 1 if cur == prev else 1
        if run >= _MAX_WORD_RUN:
            raise NarratorError("(narrator produced no usable text)")
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_narration.py -v`
Expected: 8 passed. Also run `python -m pytest test_simulation.py -q` — still passing (nothing existing changed).

- [ ] **Step 5: Commit**

```bash
git add narration.py test_narration.py
git commit -m "feat: add narration output cleaning and guards"
```

---

### Task 2: MLX runtime — single-thread executor, loader, generate, preload

Adds the in-process runtime next to the (still live) Ollama worker. The app keeps working via Ollama after this task; nothing calls the new code yet.

**Files:**
- Modify: `settings.py` (add `"narrator"` defaults + `NARR` alias; keep `"ollama"`/`OL` for now)
- Modify: `narration.py` (add executor, `_apply_template`, `_load_runtime`, `generate_narration`, `preload`)
- Modify: `requirements.txt`
- Test: `test_narration.py`

**Interfaces:**
- Consumes: `NarratorError`, `check_output(text) -> str` from Task 1.
- Produces: `generate_narration(prompt: str) -> str` — blocking, callable from any thread, raises `NarratorError` on any failure.
- Produces: `preload() -> None` — fire-and-forget model warm-up on the MLX thread.
- Produces: `NARR` dict in `settings.py` with keys `model`, `max_tokens`, `temperature`, `auto_advance_sec`.
- Internal: `_load_runtime()` returns `gen(prompt: str, max_tokens: int) -> str`; module global `_gen_fn` memoizes it. Tests monkeypatch `narration._load_runtime` and reset `narration._gen_fn`.

- [ ] **Step 1: Write the failing tests**

Append to `test_narration.py`:

```python
# ── generate_narration: thread confinement (handover doc §2.1) ────────────────

@pytest.fixture
def fresh_runtime(monkeypatch):
    """Reset the memoized runtime between tests."""
    monkeypatch.setattr(narration, "_gen_fn", None)
    return monkeypatch


def test_mlx_work_confined_to_one_worker_thread(fresh_runtime):
    threads = []

    def fake_load_runtime():
        threads.append(threading.current_thread())
        def gen(prompt, max_tokens):
            threads.append(threading.current_thread())
            return "The jar breathes."
        return gen

    fresh_runtime.setattr(narration, "_load_runtime", fake_load_runtime)
    assert narration.generate_narration("a prompt") == "The jar breathes."
    assert len(set(threads)) == 1                      # load + generate: same thread
    assert threads[0] is not threading.current_thread()  # …and not the caller's
    assert threads[0].name.startswith("mlx")


def test_concurrent_requests_are_serialized(fresh_runtime):
    import time
    from concurrent.futures import ThreadPoolExecutor
    active, peaks = [], []

    def fake_load_runtime():
        def gen(prompt, max_tokens):
            active.append(1); peaks.append(len(active))
            time.sleep(0.05)
            active.pop()
            return "ok"
        return gen

    fresh_runtime.setattr(narration, "_load_runtime", fake_load_runtime)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(narration.generate_narration, "p") for _ in range(2)]
        assert [f.result() for f in futures] == ["ok", "ok"]
    assert max(peaks) == 1


def test_generate_failure_wrapped_as_narrator_error(fresh_runtime):
    def fake_load_runtime():
        raise RuntimeError("metal exploded")
    fresh_runtime.setattr(narration, "_load_runtime", fake_load_runtime)
    with pytest.raises(narration.NarratorError):
        narration.generate_narration("p")


def test_generate_output_is_cleaned(fresh_runtime):
    def fake_load_runtime():
        return lambda prompt, max_tokens: "<channel|>hmm<channel|>Dust settles."
    fresh_runtime.setattr(narration, "_load_runtime", fake_load_runtime)
    assert narration.generate_narration("p") == "Dust settles."


# ── _apply_template: enable_thinking fallback (§2.3) ─────────────────────────

def test_template_passes_enable_thinking_false():
    calls = {}
    class Tok:
        def apply_chat_template(self, msgs, add_generation_prompt, tokenize,
                                enable_thinking):
            calls.update(msgs=msgs, enable_thinking=enable_thinking)
            return "TEMPLATED"
    assert narration._apply_template(Tok(), "hello jar") == "TEMPLATED"
    assert calls["enable_thinking"] is False
    assert calls["msgs"] == [{"role": "user", "content": "hello jar"}]


def test_template_retries_without_enable_thinking():
    class Tok:
        def apply_chat_template(self, msgs, add_generation_prompt, tokenize):
            return "TEMPLATED-NO-KWARG"
    assert narration._apply_template(Tok(), "hello") == "TEMPLATED-NO-KWARG"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_narration.py -v`
Expected: Task 1 tests still pass; the new ones ERROR with `AttributeError` (`_gen_fn`, `_load_runtime`, `generate_narration`, `_apply_template` missing).

- [ ] **Step 3: Implement the runtime**

In `settings.py`, add to `defaults` (above the `"ollama"` entry, which stays until Task 3):

```python
        "narrator": {
            "model": "mlx-community/gemma-4-26B-A4B-it-qat-mxfp8",
            "max_tokens": 180, "temperature": 0.88, "auto_advance_sec": 4,
        },
```

and at the bottom, next to the other aliases:

```python
NARR  = CFG["narrator"]
```

In `narration.py`, replace the import block at the top with:

```python
import json, datetime, sys

from concurrent.futures import ThreadPoolExecutor

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from settings import OL, NARR
from simulation import World, DATA_DIR
```

and add below `check_output`:

```python
# All MLX work (load AND generate) must run on this one thread — MLX binds
# its GPU stream to the loading thread (docs/mlx-lm-handover.md §2.1).
# max_workers=1 also serializes concurrent requests.
_MLX_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")
_gen_fn = None   # memoized by _load_runtime, on the MLX thread only


def _apply_template(tok, prompt: str) -> str:
    msgs = [{"role": "user", "content": prompt}]
    try:
        return tok.apply_chat_template(
            msgs, add_generation_prompt=True, tokenize=False,
            enable_thinking=False)
    except TypeError:
        print("[narration] chat template rejects enable_thinking — "
              "output may include a reasoning channel", file=sys.stderr)
        return tok.apply_chat_template(
            msgs, add_generation_prompt=True, tokenize=False)


def _load_runtime():
    """Load the model; return gen(prompt, max_tokens) -> raw text.

    Runs on the MLX thread only.
    """
    global _gen_fn
    if _gen_fn is not None:
        return _gen_fn
    repo = NARR["model"]
    try:
        try:
            from mlx_lm import load, generate
            from mlx_lm.sample_utils import make_sampler
            model, tok = load(repo)
            sampler = make_sampler(temp=NARR["temperature"])

            def gen(prompt, max_tokens):
                return generate(model, tok, prompt=_apply_template(tok, prompt),
                                max_tokens=max_tokens, sampler=sampler,
                                verbose=False)
        except (ValueError, ModuleNotFoundError) as e:
            # gemma-4 "unified" architectures live in mlx-vlm (§2.4)
            if "not supported" not in str(e) and "No module named" not in str(e):
                raise
            from mlx_vlm import load as vlm_load, generate as vlm_generate
            model, processor = vlm_load(repo)
            tok = getattr(processor, "tokenizer", processor)

            def gen(prompt, max_tokens):
                out = vlm_generate(model, processor,
                                   prompt=_apply_template(tok, prompt),
                                   max_tokens=max_tokens,
                                   temperature=NARR["temperature"],
                                   verbose=False)
                return getattr(out, "text", out)
    except ImportError:
        raise NarratorError("(mlx-lm not available — pip install mlx-lm mlx-vlm)")
    except NarratorError:
        raise
    except Exception as e:
        raise NarratorError(f"(model load failed: {e})")
    _gen_fn = gen
    return gen


def preload():
    """Warm the model on the MLX thread. Errors also surface on first use."""
    def body():
        try:
            _load_runtime()
        except Exception as e:
            print(f"[narration] preload failed: {e}", file=sys.stderr)
    _MLX_THREAD.submit(body)


def generate_narration(prompt: str) -> str:
    """Blocking; safe to call from any thread. Raises NarratorError on failure."""
    def body():
        return _load_runtime()(prompt, NARR["max_tokens"])
    try:
        # generous cap: covers a first-run model download (~13 GB)
        raw = _MLX_THREAD.submit(body).result(timeout=600)
    except NarratorError:
        raise
    except Exception as e:
        raise NarratorError(f"(narrator error: {e})")
    return check_output(raw)
```

Replace `requirements.txt` content with:

```
PyQt6>=6.4
requests>=2.28
mlx-lm>=0.31
mlx-vlm>=0.6.1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_narration.py test_simulation.py -v`
Expected: all pass (mlx is never imported — `_load_runtime` is mocked everywhere).

- [ ] **Step 5: Commit**

```bash
git add narration.py settings.py requirements.txt test_narration.py
git commit -m "feat: add in-process mlx-lm narration runtime"
```

---

### Task 3: The switch — rewire worker, remove Ollama everywhere

**Files:**
- Modify: `narration.py` (rewrite `NarrationWorker.run()`, drop `requests` + `OL`)
- Modify: `settings.py` (delete `"ollama"` defaults and `OL` alias)
- Modify: `settings.json` (replace `"ollama"` section with `"narrator"`)
- Modify: `main_window.py:14` (imports), `:17` (imports), `__init__` (preload), `:159` (tooltip), `:162` and `:258` (`OL` → `NARR`)
- Test: `test_narration.py`

**Interfaces:**
- Consumes: `generate_narration`, `preload`, `NarratorError` from Task 2; `NARR` from `settings.py`.
- Produces: `NarrationWorker(world, events)` with `done = pyqtSignal(str)` — unchanged signature, now backed by mlx-lm. `main_window.py` calls `preload()` once at startup.

- [ ] **Step 1: Write the failing tests**

Append to `test_narration.py`:

```python
# ── NarrationWorker: same contract as the old Ollama worker ──────────────────

def _make_world():
    from simulation import World
    return World()


def test_worker_emits_narration_text(fresh_runtime):
    fresh_runtime.setattr(narration, "generate_narration",
                          lambda prompt: "A hush falls over the jar.")
    worker = narration.NarrationWorker(_make_world(), ["something happened"])
    worker.done.emit.reset_mock()
    worker.run()
    worker.done.emit.assert_called_once_with("A hush falls over the jar.")


def test_worker_emits_error_message_instead_of_raising(fresh_runtime):
    def boom(prompt):
        raise narration.NarratorError("(model load failed: no metal)")
    fresh_runtime.setattr(narration, "generate_narration", boom)
    worker = narration.NarrationWorker(_make_world(), [])
    worker.done.emit.reset_mock()
    worker.run()
    worker.done.emit.assert_called_once_with("(model load failed: no metal)")


def test_worker_wraps_unexpected_exceptions(fresh_runtime):
    def boom(prompt):
        raise ValueError("surprise")
    fresh_runtime.setattr(narration, "generate_narration", boom)
    worker = narration.NarrationWorker(_make_world(), [])
    worker.done.emit.reset_mock()
    worker.run()
    (msg,), _ = worker.done.emit.call_args
    assert msg.startswith("(narrator error:") and "surprise" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_narration.py -v`
Expected: the three new tests FAIL — the current `run()` still calls `requests.post` (emits an Ollama error string, not the mocked narration).

- [ ] **Step 3: Rewire and remove Ollama**

In `narration.py`:
- Module docstring → `"""mlx-lm narration worker and lore file persistence."""`
- Delete `import requests` and change the settings import to `from settings import NARR`.
- Replace `NarrationWorker.run()`'s `try/except` block (everything after `prompt = (…)`) with:

```python
        try:
            self.done.emit(generate_narration(prompt))
        except NarratorError as e:
            print(f"[narration] {e}", file=sys.stderr)
            self.done.emit(str(e))
        except Exception as e:
            print(f"[narration] unexpected: {e}", file=sys.stderr)
            self.done.emit(f"(narrator error: {e})")
```

(`sys` is already imported by Task 2's import block.)

The prompt construction (`pop`, `pop_str`, `evt_str`, `ext_str`, `prompt`) stays byte-for-byte identical.

In `settings.py`: delete the `"ollama"` block from `defaults` and the `OL = CFG["ollama"]` line.

In `settings.json`: replace the `"ollama"` object with:

```json
  "narrator": {
    "model":            "mlx-community/gemma-4-26B-A4B-it-qat-mxfp8",
    "max_tokens":       180,
    "temperature":      0.88,
    "auto_advance_sec": 4
  },
```

In `main_window.py`:
- Line 14: `from settings import C, F, NARR, COMFY`
- Line 17: `from narration import NarrationWorker, append_lore, preload`
- In `__init__`, after `self._anim_timer.start(80)`, add:

```python
        preload()   # warm the narrator model in the background (~7s, 13 GB download on first run)
```

- Line 159 tooltip: `tip="Run 10 simulation ticks and request narration from the local model."`
- Lines 162 and 258: replace `OL["auto_advance_sec"]` with `NARR["auto_advance_sec"]`.

- [ ] **Step 4: Run tests and verify the app imports**

Run: `python -m pytest test_narration.py test_simulation.py -v`
Expected: all pass.
Run: `grep -ri ollama *.py settings.json`
Expected: no matches.
Run: `python -c "import main_window"` (requires PyQt6)
Expected: no ImportError.

- [ ] **Step 5: Commit**

```bash
git add narration.py settings.py settings.json main_window.py test_narration.py
git commit -m "feat: switch narration from Ollama to in-process mlx-lm"
```

---

### Task 4: Documentation and manual verification

**Files:**
- Modify: `README.md` (Setup section, interface diagram, controls table, intro line)
- Modify: `ecosystem_in_a_jar.py:1-15` (module docstring)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `ecosystem_in_a_jar.py` docstring**

Replace lines 6–11 of the docstring with:

```
Requirements (Apple silicon only — MLX is Metal-based):
    pip install PyQt6 requests mlx-lm mlx-vlm

The narrator model (mlx-community/gemma-4-26B-A4B-it-qat-mxfp8, ~13 GB)
downloads from Hugging Face on first run and uses ~16 GB of memory while
the app is open.
```

- [ ] **Step 2: Update `README.md`**

- Line 4: `You intervene with disasters. A local AI narrates. The lore accumulates forever.`
- Replace the Setup section's dependency + Ollama parts (lines 10–30) with:

````markdown
```bash
pip install PyQt6 requests mlx-lm mlx-vlm
```

Narration runs **in-process on Apple silicon** via
[mlx-lm](https://github.com/ml-explore/mlx-lm) — no server needed. The model
(`mlx-community/gemma-4-26B-A4B-it-qat-mxfp8`, ~13 GB) downloads from Hugging
Face on the first run and stays cached in `~/.cache/huggingface/hub`. While
the app is open it keeps ~16 GB of unified memory resident.

Change the model in `settings.json`:
```json
"narrator": { "model": "mlx-community/gemma-4-26B-A4B-it-qat-mxfp8" }
```

Narration shows an error message if the model can't load — but the sim runs
fine without it.
````

- Interface diagram line 50: `(AI narration)` instead of `(Ollama narration)`.
- Controls table line 76: `| ▶ Advance (+10) | Run 10 ticks + AI narration |`
- Delete the stale tkinter note (lines 14–16) — the app is PyQt6.

- [ ] **Step 3: Full test suite + Ollama sweep**

Run: `python -m pytest -q`
Expected: all pass.
Run: `grep -ri ollama README.md *.py settings.json`
Expected: no matches (`docs/mlx-lm-handover.md` and the spec still mention Ollama — that's fine, they document the migration).

- [ ] **Step 4: Manual verification (real model — needs the ~13 GB download)**

Run: `python ecosystem_in_a_jar.py`
- App opens immediately; model loads/downloads in the background (watch stderr).
- Press **▶ Advance**: spinner shows `✦ narrating…`, then a 2–3 sentence documentary narration appears (~5 s once the model is warm).
- Confirm `jar_data/lore.jsonl` gained an entry.
- Trigger a disaster button; confirm narration again.

- [ ] **Step 5: Commit**

```bash
git add README.md ecosystem_in_a_jar.py
git commit -m "docs: replace Ollama setup with mlx-lm instructions"
```
