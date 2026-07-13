# 🫙 Ecosystem in a Jar

A living simulation with a full dark-themed GUI. Creatures evolve, eat, hunt, and die.
You intervene with disasters. A local AI narrates. The lore accumulates forever.

---

## Setup

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

---

## Run

```bash
python ecosystem_in_a_jar.py
```

State saves to `./jar_data/` after every action. Run again to resume.

---

## The Interface

```
┌────────────────────┬─────────────────────┬─────────────────────┐
│  The Jar (canvas)  │  Species Table      │  📽️ Nature Doc     │
│  creatures as dots │  traits + gen bar   │  (AI narration)     │
│  🟢 herbivore      │  Event Log          │  Disaster buttons   │
│  🔴 carnivore      │  (scrollable)       │  Add Species        │
└────────────────────┴─────────────────────┴─────────────────────┘
```

---

## Starter Species

| Species     | Diet      | Notes                                       |
|-------------|-----------|---------------------------------------------|
| Grazzle 🐇  | Herbivore | Fast + camouflaged; classic prey species    |
| Thornback 🐢| Herbivore | Incredibly resilient but slow               |
| Vorren 🦊   | Carnivore | Aggressive hunter — tends to boom and crash |

Traits mutate with every birth. Over generations species drift, shaped by your disasters.

**Vorren ecology**: they typically hunt Thornbacks to extinction, then starve —
classic predator collapse. This is intentional. Reintroduce carnivores to experiment.

---

## Controls

| Control | Effect |
|---|---|
| ▶ Advance (+10) | Run 10 ticks + AI narration |
| ⏸ / ⏹ | Toggle auto-advance every 4s |
| Fast-forward slider + ⏭ | Skip N ticks silently |
| ☄️ Meteor | 60% die; plants → 10% |
| 🏜️ Drought | Plants → 3; herbivores weaken |
| 🦠 Plague | 75% of one random species dies |
| 🌸 Bloom | Plants → 100; all creatures fed |
| 🧊 Cold | Low-resilience creatures die (45%) |
| 🌊 Flood | Small creatures drown; plants +35 |
| ✨ Add Species | Custom species dialog with trait sliders |
| 📖 Lore | Full narrated history window |

---

## The Lore Archive

Every advance appends a narration entry to `jar_data/lore.jsonl`.
Over months of play it becomes a strange, personal natural history.
Click **📖 Lore** to scroll through everything that has ever happened.
