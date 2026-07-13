"""Configuration loading — no Qt dependency."""

import json
from pathlib import Path

SETTINGS_PATH = Path("./settings.json")


def _deep_update(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if k.startswith("_"): continue
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_settings() -> dict:
    defaults = {
        "narrator": {
            "model": "mlx-community/gemma-4-26B-A4B-it-qat-mxfp8",
            "max_tokens": 180, "temperature": 0.88, "auto_advance_sec": 4,
        },
        "ollama": {
            "model": "gemma3:27b",
            "url": "http://localhost:11434/api/generate",
            "max_tokens": 180, "temperature": 0.88, "auto_advance_sec": 4,
        },
        "comfyui": {
            "url": "http://localhost:8188",
            "checkpoint": "flux1-schnell.safetensors",
            "width": 512, "height": 384,
            "steps": 4, "cfg": 1.0, "enabled": True,
        },
        "font": {
            "size_ui": 11, "size_mono": 10, "size_title": 15, "size_lore": 12,
            "family_ui": "Helvetica", "family_mono": "Courier New",
            "family_lore": "Georgia",
        },
        "colors": {
            "window_bg": "#0d1117", "panel_bg": "#161b22",
            "panel_bg_alt": "#21262d", "border": "#30363d",
            "text_screen": "#e6edf3", "text_screen_dim": "#8b949e",
            "text_lore": "#d1c284",
            "text_button": "#ffffff", "text_button_danger": "#ffcccc",
            "accent_green": "#3fb950", "accent_yellow": "#d29922",
            "accent_red": "#da3633", "accent_blue": "#58a6ff",
            "btn_default": "#21262d", "btn_advance": "#1f6831",
            "btn_auto": "#21262d", "btn_add": "#2d2a1a", "btn_lore": "#1a1a3d",
            "btn_meteor": "#3d1a1a", "btn_drought": "#3d2a1a",
            "btn_plague": "#1a3d1a", "btn_bloom": "#1a3d3d",
            "btn_cold": "#1a1a3d", "btn_flood": "#1a2d5c",
            "creature_herbivore": "#4ade80", "creature_carnivore": "#f87171",
            "creature_omnivore": "#facc15", "creature_unhealthy": "#8b949e",
            "plant_dot": "#1a3a1a", "canvas_bg": "#0a1628",
            "progressbar_bg": "#21262d", "progressbar_fill": "#3fb950",
        },
    }
    if SETTINGS_PATH.exists():
        try:
            user = json.loads(SETTINGS_PATH.read_text())
            _deep_update(defaults, user)
        except Exception as e:
            print(f"[settings] Warning: {e}")
    return defaults


CFG   = load_settings()
C     = CFG["colors"]
F     = CFG["font"]
OL    = CFG["ollama"]
NARR  = CFG["narrator"]
COMFY = CFG["comfyui"]