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
