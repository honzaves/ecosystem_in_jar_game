"""Core ecosystem simulation — no Qt or network dependencies."""

import json, math, random
from pathlib import Path
from dataclasses import dataclass

DATA_DIR = Path("./jar_data")

CANVAS_W, CANVAS_H = 520, 400
HUNT_RADIUS   = 80.0
MATE_RADIUS   = 70.0
SEASON_LENGTH = 30
SEASONS       = ["🌱 Spring", "☀️ Summer", "🍂 Autumn", "❄️ Winter"]
SEASON_PLANT  = [80, 95, 50, 18]


@dataclass
class Traits:
    size: float; speed: float; resilience: float
    camouflage: float; aggression: float

    def mutate(self) -> "Traits":
        def m(v):
            if random.random() < 0.35: v += random.gauss(0, 0.50)
            return round(max(1.0, min(10.0, v)), 2)
        return Traits(m(self.size), m(self.speed), m(self.resilience),
                      m(self.camouflage), m(self.aggression))

    def crossover(self, other: "Traits") -> "Traits":
        """Offspring traits: each field randomly inherited from one parent, then mutated."""
        def pick(a: float, b: float) -> float:
            r = random.random()
            if   r < 0.45: return a
            elif r < 0.90: return b
            else:          return round((a + b) / 2, 2)
        return Traits(
            pick(self.size,       other.size),
            pick(self.speed,      other.speed),
            pick(self.resilience, other.resilience),
            pick(self.camouflage, other.camouflage),
            pick(self.aggression, other.aggression),
        ).mutate()

    def to_dict(self): return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d): return cls(**d)


@dataclass
class Creature:
    id: int; species: str; emoji: str; diet: str; traits: Traits
    age: int = 0; hunger: float = 25.0; health: float = 100.0
    generation: int = 1; x: float = 0.0; y: float = 0.0
    dx: float = 0.0; dy: float = 0.0

    def max_age(self): return int(30 + self.traits.resilience * 5)

    def to_dict(self):
        d = {k: v for k, v in self.__dict__.items()}
        d["traits"] = self.traits.to_dict(); return d

    @classmethod
    def from_dict(cls, d):
        d = d.copy(); d["traits"] = Traits.from_dict(d["traits"]); return cls(**d)


STARTER_SPECIES = [
    ("Grazzle",   "🐇", "herbivore",  3, 7, 5, 7, 2, 16),
    ("Thornback", "🐢", "herbivore",  7, 2, 9, 3, 2, 10),
    ("Vorren",    "🦊", "carnivore",  5, 6, 5, 2, 7,  3),
]


class World:
    def __init__(self):
        self.tick = 0; self._next_id = 1
        self.creatures: list = []; self.plant_abundance: float = 75.0
        self.event_log: list = []
        self.extinct_species: set = set()
        self.recently_extinct: set = set()
        self.all_known_species: set = set()

    @property
    def season_idx(self): return (self.tick // SEASON_LENGTH) % 4
    @property
    def season(self): return SEASONS[self.season_idx]
    @property
    def year(self): return self.tick // (SEASON_LENGTH * 4) + 1

    def new_id(self):
        i = self._next_id; self._next_id += 1; return i

    def population_by_species(self) -> dict:
        out = {}
        for c in self.creatures: out[c.species] = out.get(c.species, 0) + 1
        return out

    def spawn_starters(self):
        for name, emoji, diet, sz, sp, rs, cm, ag, count in STARTER_SPECIES:
            self.all_known_species.add(name)
            base = Traits(sz, sp, rs, cm, ag)
            for _ in range(count):
                c = Creature(id=self.new_id(), species=name, emoji=emoji, diet=diet,
                             traits=base.mutate(), generation=1,
                             x=random.uniform(20, CANVAS_W-20),
                             y=random.uniform(20, CANVAS_H-20))
                angle = random.uniform(0, 2*math.pi); spd = random.uniform(1.5, 3.0)
                c.dx, c.dy = math.cos(angle)*spd, math.sin(angle)*spd
                self.creatures.append(c)

    def _move(self):
        DETECT_R = 150.0
        FLEE_R   = 120.0
        STEER    = 0.22

        herbivores = [c for c in self.creatures if c.diet in ("herbivore", "omnivore")]
        carnivores = [c for c in self.creatures if c.diet in ("carnivore", "omnivore")]

        for c in self.creatures:
            if random.random() < 0.06:
                angle = random.uniform(0, 2*math.pi)
                spd   = (c.traits.speed / 5.0) * random.uniform(1.5, 3.0)
                c.dx, c.dy = math.cos(angle)*spd, math.sin(angle)*spd

            spd_now = math.hypot(c.dx, c.dy) or 1.0

            if c.diet == "carnivore":
                nearest, nearest_d = None, DETECT_R
                for prey in herbivores:
                    d = math.hypot(prey.x - c.x, prey.y - c.y)
                    if d < nearest_d:
                        nearest_d = d; nearest = prey
                if nearest:
                    dx = nearest.x - c.x; dy = nearest.y - c.y
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        tx = (dx / dist) * spd_now; ty = (dy / dist) * spd_now
                        s = min(STEER * (c.traits.aggression / 5.0), 0.45)
                        c.dx = c.dx*(1-s) + tx*s; c.dy = c.dy*(1-s) + ty*s

            elif c.diet == "herbivore":
                nearest, nearest_d = None, FLEE_R
                for pred in carnivores:
                    d = math.hypot(pred.x - c.x, pred.y - c.y)
                    if d < nearest_d:
                        nearest_d = d; nearest = pred
                if nearest:
                    dx = c.x - nearest.x; dy = c.y - nearest.y
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        tx = (dx / dist) * spd_now; ty = (dy / dist) * spd_now
                        s = min(STEER * (c.traits.speed / 5.0), 0.45)
                        c.dx = c.dx*(1-s) + tx*s; c.dy = c.dy*(1-s) + ty*s

            c.x = (c.x + c.dx) % CANVAS_W
            c.y = (c.y + c.dy) % CANVAS_H

    def tick_world(self) -> list:
        self.tick += 1; events = []; self._move()
        target = SEASON_PLANT[self.season_idx]
        self.plant_abundance += (target - self.plant_abundance) * 0.10
        self.plant_abundance = max(2.0, min(100.0, self.plant_abundance + random.gauss(0, 1.8)))
        herbivores = [c for c in self.creatures if c.diet in ("herbivore", "omnivore")]
        carnivores = [c for c in self.creatures if c.diet in ("carnivore", "omnivore")]
        share = self.plant_abundance / max(len(herbivores), 1)
        for c in herbivores:
            c.hunger = max(0.0, c.hunger - min(share*(c.traits.speed/5.0)*2.0, 55.0))
        for pred in carnivores:
            if pred.hunger < 30: continue
            nearby = [p for p in herbivores if math.hypot(p.x-pred.x, p.y-pred.y) <= HUNT_RADIUS]
            if not nearby: pred.hunger = min(100.0, pred.hunger+2); continue
            prey = random.choice(nearby)
            hunt  = pred.traits.aggression + pred.traits.speed
            evade = prey.traits.camouflage*1.6 + prey.traits.speed
            if random.random() < hunt/(hunt+evade):
                pred.hunger = max(0.0, pred.hunger-65); prey.health -= random.uniform(30, 75)
                if prey.health <= 0:
                    events.append(f"{pred.emoji} {pred.species} kills a {prey.emoji} {prey.species}")

        by_species: dict = {}
        for cr in self.creatures:
            by_species.setdefault(cr.species, []).append(cr)

        survivors = []
        repro  = {"herbivore": 0.055, "carnivore": 0.018, "omnivore": 0.038}
        minage = {"herbivore": 6,     "carnivore": 14,    "omnivore": 10}
        for c in self.creatures:
            c.age += 1; c.hunger = min(100.0, c.hunger + random.uniform(3.5, 7.5))
            if c.hunger > 70: c.health -= (c.hunger-70) / max(c.traits.resilience*1.5, 1)
            elif c.hunger < 30: c.health = min(100.0, c.health + 1.2)
            if c.hunger >= 100 or c.health <= 0 or c.age >= c.max_age():
                if c.age >= c.max_age(): events.append(f"🕯️ A {c.emoji} {c.species} dies at age {c.age}")
                elif c.hunger >= 100:    events.append(f"💧 A {c.emoji} {c.species} starves")
                continue
            dens = max(0.0, (len(herbivores)-22)*0.003) if c.diet == "herbivore" else 0.0
            rate = max(0.003, repro.get(c.diet, 0.04)*(c.traits.resilience/5.0) - dens)
            if c.hunger < 35 and c.health > 60 and c.age > minage.get(c.diet, 8) and random.random() < rate:
                mates = [m for m in by_species.get(c.species, [])
                         if m is not c and m.health > 60 and m.hunger < 50
                         and math.hypot(m.x-c.x, m.y-c.y) <= MATE_RADIUS]
                if mates:
                    mate = random.choice(mates)
                    child_traits = c.traits.crossover(mate.traits)
                    child_gen    = max(c.generation, mate.generation) + 1
                else:
                    child_traits = c.traits.mutate()
                    child_gen    = c.generation + 1
                child = Creature(id=self.new_id(), species=c.species, emoji=c.emoji,
                                 diet=c.diet, traits=child_traits, generation=child_gen,
                                 x=c.x+random.uniform(-10, 10), y=c.y+random.uniform(-10, 10))
                angle = random.uniform(0, 2*math.pi); spd = (child.traits.speed/5.0)*random.uniform(1.5, 3.0)
                child.dx, child.dy = math.cos(angle)*spd, math.sin(angle)*spd
                survivors.append(child)
            survivors.append(c)
        self.creatures = survivors
        alive = {c.species for c in self.creatures}
        for sp in list(self.all_known_species):
            if sp not in alive and sp not in self.extinct_species:
                self.extinct_species.add(sp); self.recently_extinct.add(sp)
                events.append(f"💀 {sp} has gone EXTINCT")
        self.event_log = (events + self.event_log)[:80]; return events

    def apply_disaster(self, kind: str) -> str:
        k = kind.lower()
        if k == "meteor":
            n = sum(1 for c in self.creatures if random.random() < 0.60)
            self.creatures = [c for c in self.creatures if random.random() >= 0.60]
            self.plant_abundance *= 0.10; return f"☄️ Meteor! {n} killed. Plants scorched."
        elif k == "drought":
            self.plant_abundance = 3.0
            for c in self.creatures:
                if c.diet != "carnivore": c.hunger = min(100, c.hunger+45)
            return "🏜️ Drought — vegetation collapses."
        elif k == "plague":
            sp_list = list({c.species for c in self.creatures})
            if not sp_list: return "🦠 Nothing to infect."
            target = random.choice(sp_list)
            before = sum(1 for c in self.creatures if c.species == target)
            self.creatures = [c for c in self.creatures if c.species != target or random.random() >= 0.75]
            after = sum(1 for c in self.creatures if c.species == target)
            return f"🦠 Plague hits {target} — {before-after} dead."
        elif k == "bloom":
            self.plant_abundance = 100.0
            for c in self.creatures: c.hunger = max(0, c.hunger-55)
            return "🌸 Miraculous bloom — every creature feasts."
        elif k == "cold":
            n = sum(1 for c in self.creatures if c.traits.resilience < 5 and random.random() < 0.45)
            self.creatures = [c for c in self.creatures if c.traits.resilience >= 5 or random.random() >= 0.45]
            return f"🧊 Cold snap — {n} fragile creatures perish."
        elif k == "flood":
            self.plant_abundance = min(100, self.plant_abundance+35)
            n = sum(1 for c in self.creatures if c.traits.size < 4 and random.random() < 0.50)
            self.creatures = [c for c in self.creatures if c.traits.size >= 4 or random.random() >= 0.50]
            return f"🌊 Flood! {n} small creatures drown."
        return f"Unknown: {kind}"

    def add_species(self, name, emoji, diet, traits=None) -> str:
        if traits is None: traits = Traits(*[random.uniform(3, 7) for _ in range(5)])
        self.all_known_species.add(name)
        for _ in range(6):
            c = Creature(id=self.new_id(), species=name, emoji=emoji, diet=diet,
                         traits=traits.mutate(), generation=1,
                         x=random.uniform(20, CANVAS_W-20), y=random.uniform(20, CANVAS_H-20))
            angle = random.uniform(0, 2*math.pi); spd = (c.traits.speed/5.0)*2.0
            c.dx, c.dy = math.cos(angle)*spd, math.sin(angle)*spd; self.creatures.append(c)
        return f"✨ {name} {emoji} ({diet}) introduced — 6 individuals."

    def to_dict(self):
        return {"tick": self.tick, "_next_id": self._next_id,
                "plant_abundance": self.plant_abundance,
                "creatures": [c.to_dict() for c in self.creatures],
                "event_log": self.event_log,
                "extinct_species": list(self.extinct_species),
                "all_known_species": list(self.all_known_species)}

    @classmethod
    def from_dict(cls, d):
        w = cls(); w.tick = d["tick"]; w._next_id = d["_next_id"]
        w.plant_abundance = d["plant_abundance"]
        w.creatures = [Creature.from_dict(c) for c in d["creatures"]]
        w.event_log = d.get("event_log", []); w.extinct_species = set(d.get("extinct_species", []))
        w.all_known_species = set(d.get("all_known_species", [])); return w

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "world.json").write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls):
        fp = DATA_DIR / "world.json"
        if not fp.exists(): return None
        return cls.from_dict(json.loads(fp.read_text()))