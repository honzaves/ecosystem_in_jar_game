"""Ollama narration worker and lore file persistence."""

import json, datetime

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from settings import OL
from simulation import World, DATA_DIR


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