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


# ── NarrationWorker: same contract as the old HTTP-based worker ──────────────

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
