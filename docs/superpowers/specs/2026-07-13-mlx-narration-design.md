# Design: Switch narration from Ollama to in-process mlx-lm

**Date:** 2026-07-13
**Status:** Approved approach A (single-thread executor), pending spec review
**Reference:** `docs/mlx-lm-handover.md` (all section numbers below refer to it)

## Goal

Replace the Ollama HTTP narration backend with in-process generation via
mlx-lm, using `mlx-community/gemma-4-26B-A4B-it-qat-mxfp8`. Clean
replacement — the Ollama path is deleted, no backend flag. Target machine:
Apple silicon, 96 GB unified memory.

## Decisions made

- **No Ollama fallback.** The HTTP path and its settings are removed.
- **Preload at app start.** The model load is submitted to the MLX thread
  when the main window starts, in the background. First narration waits on
  the load only if it hasn't finished yet.
- **Architecture: Approach A.** A module-level
  `ThreadPoolExecutor(max_workers=1)` in `narration.py` owns *all* MLX work
  (load + generate) to satisfy MLX thread affinity (§2.1).
  `NarrationWorker(QThread)` keeps its exact current interface — it builds
  the prompt, submits to the executor, blocks on `Future.result()`, and
  emits `done`. It never touches MLX objects itself.

## Component changes

### `narration.py` (the bulk of the diff)

- `_MLX_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")`,
  module level. Also serializes concurrent generation requests (§3).
- `_load_runtime()` — runs on the MLX thread, memoized in a module global:
  - Try `mlx_lm.load(repo_id)`; on unsupported-architecture /
    missing-module errors fall through to `mlx_vlm.load(repo_id)` (§2.4 —
    gemma-4 unified arch may not be in mlx-lm).
  - Build sampler via `make_sampler(temp=…)` from settings (§3 sampling
    parity; `num_predict` → `max_tokens`).
- `preload()` — public; submits `_load_runtime` to the executor and returns
  immediately (fire-and-forget future; errors surface on first generate).
- Prompt path (§2.3, §2.5):
  - `apply_chat_template([{"role": "user", "content": prompt}],
    add_generation_prompt=True, tokenize=False, enable_thinking=False)`.
  - `TypeError` on `enable_thinking` → retry without it and log a warning.
  - Template exception on message structure → fold-in fallback (single user
    message is already the primary path; no system role is used today).
- Output cleaning + guards, applied in order (§2.3, §3):
  1. If a channel-close marker is present, keep only text after the *last*
     one (`rsplit`).
  2. Strip whitespace/code fences.
  3. Empty output → error message.
  4. Repetition guard: the same word appearing ≥10 times consecutively →
     error message (§3, the `"own own own …"` failure mode).
- `NarrationWorker.run()` — same signature and `done` signal as today:
  builds the same documentary prompt, submits generation, waits with a
  timeout (generation is ~5 s for 180 tokens on this MoE model; keep a
  generous cap, e.g. 120 s to cover a first-run load/download), emits the
  cleaned text or a parenthesized error message.
- **Error contract unchanged:** every failure (import, download, load,
  generate, guard trip) is emitted through `done` as a short
  `"(…)"`-style message, mirroring today's `"(Ollama not reachable…)"`.
  The simulation never blocks or crashes on narration failure.
- `append_lore()` unchanged.

### `settings.py` / `settings.json`

- `"ollama"` section renamed to `"narrator"`:
  - `model: "mlx-community/gemma-4-26B-A4B-it-qat-mxfp8"`
  - `max_tokens: 180`
  - `temperature: 0.88`
  - `auto_advance_sec: 4` (stays here; read by the auto-advance timer)
  - `url` removed.
- `OL` alias in `settings.py` renamed accordingly (e.g. `NARR`); update the
  two consumers (`narration.py`, `main_window.py`).

### `main_window.py` (minimal)

- Call `narration.preload()` during startup.
- Update the Advance tooltip text ("…request narration from Ollama").
- `auto_advance_sec` read from the renamed settings section.

### `ecosystem_in_a_jar.py`, `README.md`

- Replace Ollama setup instructions (`ollama pull` / `ollama serve` /
  stale `llama3.2` references) with: Apple-silicon requirement, pip
  install, note that the first run downloads ~13 GB from Hugging Face into
  `~/.cache/huggingface/hub`, and ~16 GB resident memory while running.

### `requirements.txt`

- Add `mlx-lm>=0.31` and `mlx-vlm>=0.6.1`.
- Keep `requests` (still used by `image_gen.py` for ComfyUI).

## Error handling summary

| Failure | Surfaced as |
|---|---|
| mlx not importable / not Apple silicon | `done("(mlx-lm not available — pip install mlx-lm mlx-vlm)")` |
| Download/load failure | `done("(model load failed: …)")` |
| Generation exception | `done("(narrator error: …)")` |
| Empty / repetition-loop output | `done("(narrator produced no usable text)")` |

All errors are also printed to stderr for diagnosis. Today
`_on_narration_done` appends whatever text arrives to lore, including error
strings; keep that behavior (error strings in lore are visible and
harmless, and changing it is out of scope).

## Testing

New `test_narration.py` next to `test_simulation.py`, using a mocked
runtime (no model download, no mlx import required to run tests):

1. **Thread-confinement regression test** (§2.1 checklist item): with the
   loader and generator mocked, assert both execute on the same thread and
   that it is not the caller's thread.
2. Cleaner tests: channel-marker splitting (last marker wins), fence
   stripping, passthrough of clean text.
3. Guard tests: empty output and repetition loop map to error messages.
4. Serialization: two concurrent submissions execute sequentially.

Manual verification (per project /verify norms): launch the app, press
Advance, confirm narration appears and `jar_data/lore.jsonl` grows.

## Out of scope

- ComfyUI image generation path (unchanged; it shares the GPU but with
  96 GB unified memory concurrent Flux + 26B-A4B is acceptable).
- Model unloading / idle eviction.
- Streaming narration into the UI.
