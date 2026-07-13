"""Ollama narration worker and lore file persistence."""

import json, datetime

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from settings import OL
from simulation import World, DATA_DIR


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


class NarrationWorker(QThread):
    done = pyqtSignal(str)

    def __init__(self, world: World, events: list):
        super().__init__(); self.world = world; self.events = events

    def run(self):
        pop     = self.world.population_by_species()
        pop_str = ", ".join(f"{k}: {v}" for k, v in pop.items()) or "nothing survives"
        evt_str = "\n".join(f"- {e}" for e in self.events[:6]) or "- Quiet."
        ext_str = ", ".join(self.world.extinct_species) or "none yet"
        prompt  = (
            "You are the narrator of a nature documentary about a sealed glass jar "
            "containing a miniature alien ecosystem called The Jar. Tone: poetic, "
            "slightly melancholy, precise — David Attenborough on a strange planet.\n\n"
            f"State: Year {self.world.year}, {self.world.season}, Tick {self.world.tick}\n"
            f"Plants: {self.world.plant_abundance:.0f}/100\nPopulations: {pop_str}\n"
            f"Recent events:\n{evt_str}\nExtinct: {ext_str}\n\n"
            "Write exactly 2–3 sentences. Don't recite numbers — paint the picture. "
            "End on tension or wonder."
        )
        try:
            r = requests.post(OL["url"], json={
                "model": OL["model"], "prompt": prompt, "stream": False,
                "options": {"num_predict": OL["max_tokens"], "temperature": OL["temperature"]},
            }, timeout=45)
            if r.status_code == 200: self.done.emit(r.json().get("response", "").strip()); return
            self.done.emit(f"(Ollama returned {r.status_code})")
        except requests.exceptions.ConnectionError:
            self.done.emit("(Ollama not reachable — run: ollama serve)")
        except Exception as e:
            self.done.emit(f"(Narrator error: {e})")


def append_lore(world: World, narration: str, events: list):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"tick": world.tick, "year": world.year, "season": world.season,
             "narration": narration, "events": events,
             "populations": world.population_by_species(),
             "plants": round(world.plant_abundance, 1),
             "timestamp": datetime.datetime.now().isoformat()}
    with open(DATA_DIR / "lore.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")