"""
Unit tests for the ecosystem simulation.

simulation.py has no Qt or network dependencies, so most tests need
no mocking at all.  The image_gen tests still mock Qt/requests because
image_gen.py imports QThread at module level.

Run with:  python -m pytest test_simulation.py
"""

import sys
import types
import random
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# ── Minimal Qt stubs (only needed to import image_gen) ───────────────────────

def _make_qt_stubs():
    class _Base:
        def __init__(self, *a, **kw): pass

    class _QThread(_Base):
        done = failed = None
        def start(self): pass
        def isRunning(self): return False

    def _pyqtSignal(*a): return MagicMock()

    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_core.Qt         = MagicMock()
    qt_core.QTimer     = MagicMock()
    qt_core.QThread    = _QThread
    qt_core.pyqtSignal = _pyqtSignal
    qt_core.QPointF    = MagicMock()
    qt_core.QRectF     = MagicMock()

    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    for name in [
        "QApplication", "QMainWindow", "QWidget", "QVBoxLayout", "QHBoxLayout",
        "QGridLayout", "QLabel", "QPushButton", "QSlider", "QTextEdit",
        "QScrollArea", "QTreeWidget", "QTreeWidgetItem", "QProgressBar",
        "QFrame", "QSplitter", "QDialog", "QDialogButtonBox", "QLineEdit",
        "QRadioButton", "QButtonGroup", "QDoubleSpinBox", "QGroupBox",
        "QSizePolicy", "QMessageBox", "QToolTip",
    ]:
        setattr(qt_widgets, name, _Base)

    qt_gui = types.ModuleType("PyQt6.QtGui")
    for name in [
        "QFont", "QPainter", "QColor", "QBrush", "QPen",
        "QTextCursor", "QPalette", "QPixmap", "QRadialGradient",
    ]:
        setattr(qt_gui, name, MagicMock())

    pyqt6 = types.ModuleType("PyQt6")
    return pyqt6, qt_core, qt_widgets, qt_gui


_pyqt6, _qt_core, _qt_widgets, _qt_gui = _make_qt_stubs()
sys.modules.setdefault("PyQt6",           _pyqt6)
sys.modules.setdefault("PyQt6.QtCore",    _qt_core)
sys.modules.setdefault("PyQt6.QtWidgets", _qt_widgets)
sys.modules.setdefault("PyQt6.QtGui",     _qt_gui)
sys.modules.setdefault("requests",        MagicMock())

# ── Imports ───────────────────────────────────────────────────────────────────

import simulation as sim          # no Qt needed — pure Python
import settings   as _settings    # no Qt needed
import image_gen  as _image_gen   # needs Qt stub (QThread base class)

# Redirect save/load to a temp directory so tests never touch real data
_tmp = tempfile.TemporaryDirectory()
sim.DATA_DIR = Path(_tmp.name)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_creature(**kwargs) -> sim.Creature:
    defaults = dict(
        id=1, species="Grazzle", emoji="🐇", diet="herbivore",
        traits=sim.Traits(size=3.0, speed=7.0, resilience=5.0,
                          camouflage=7.0, aggression=2.0),
        age=10, hunger=20.0, health=100.0, generation=1,
        x=100.0, y=100.0, dx=1.0, dy=0.0,
    )
    defaults.update(kwargs)
    return sim.Creature(**defaults)


def _world_with(*creatures) -> sim.World:
    w = sim.World(); w.creatures = list(creatures); return w


# ═════════════════════════════════════════════════════════════════════════════
# Traits
# ═════════════════════════════════════════════════════════════════════════════

class TestTraits:

    def test_mutate_stays_in_range(self):
        random.seed(0)
        t = sim.Traits(5.0, 5.0, 5.0, 5.0, 5.0)
        for _ in range(200):
            m = t.mutate()
            for field in ("size", "speed", "resilience", "camouflage", "aggression"):
                v = getattr(m, field)
                assert 1.0 <= v <= 10.0, f"{field}={v} out of [1, 10]"

    def test_mutate_returns_new_instance(self):
        t = sim.Traits(5.0, 5.0, 5.0, 5.0, 5.0)
        assert t.mutate() is not t

    def test_to_dict_roundtrip(self):
        t = sim.Traits(2.5, 8.1, 4.0, 6.3, 9.9)
        assert sim.Traits.from_dict(t.to_dict()) == t

    def test_to_dict_keys(self):
        d = sim.Traits(1.0, 2.0, 3.0, 4.0, 5.0).to_dict()
        assert set(d) == {"size", "speed", "resilience", "camouflage", "aggression"}

    def test_crossover_in_range(self):
        random.seed(7)
        a = sim.Traits(2.0, 8.0, 3.0, 9.0, 1.0)
        b = sim.Traits(8.0, 2.0, 9.0, 1.0, 9.0)
        for _ in range(100):
            child = a.crossover(b)
            for field in ("size", "speed", "resilience", "camouflage", "aggression"):
                assert 1.0 <= getattr(child, field) <= 10.0

    def test_crossover_produces_variation(self):
        random.seed(0)
        a = sim.Traits(1.0, 1.0, 1.0, 1.0, 1.0)
        b = sim.Traits(10.0, 10.0, 10.0, 10.0, 10.0)
        children = [a.crossover(b) for _ in range(30)]
        assert len({c.size for c in children}) > 1

    def test_crossover_returns_new_instance(self):
        a = sim.Traits(5.0, 5.0, 5.0, 5.0, 5.0)
        b = sim.Traits(5.0, 5.0, 5.0, 5.0, 5.0)
        child = a.crossover(b)
        assert child is not a and child is not b


# ═════════════════════════════════════════════════════════════════════════════
# Creature
# ═════════════════════════════════════════════════════════════════════════════

class TestCreature:

    def test_max_age_formula(self):
        c = _make_creature(traits=sim.Traits(3, 7, 6.0, 7, 2))
        assert c.max_age() == int(30 + 6.0 * 5)

    def test_max_age_varies_with_resilience(self):
        low  = _make_creature(traits=sim.Traits(3, 7, 1.0, 7, 2))
        high = _make_creature(traits=sim.Traits(3, 7, 10.0, 7, 2))
        assert low.max_age() < high.max_age()

    def test_to_dict_roundtrip(self):
        c  = _make_creature()
        c2 = sim.Creature.from_dict(c.to_dict())
        assert c2.id == c.id and c2.species == c.species
        assert c2.traits == c.traits and c2.age == c.age

    def test_to_dict_contains_traits(self):
        assert isinstance(_make_creature().to_dict()["traits"], dict)


# ═════════════════════════════════════════════════════════════════════════════
# World — properties and housekeeping
# ═════════════════════════════════════════════════════════════════════════════

class TestWorldProperties:

    def test_season_idx_cycles(self):
        w = sim.World()
        for tick, expected in [(0, 0), (29, 0), (30, 1), (60, 2), (90, 3), (120, 0)]:
            w.tick = tick
            assert w.season_idx == expected, f"tick={tick}"

    def test_season_label(self):
        w = sim.World(); w.tick = 0
        assert w.season == sim.SEASONS[0]

    def test_year_starts_at_1(self):
        assert sim.World().year == 1

    def test_year_advances(self):
        w = sim.World(); w.tick = sim.SEASON_LENGTH * 4
        assert w.year == 2

    def test_new_id_increments(self):
        w = sim.World()
        assert [w.new_id() for _ in range(5)] == list(range(1, 6))

    def test_population_by_species_empty(self):
        assert sim.World().population_by_species() == {}

    def test_population_by_species_counts(self):
        w = _world_with(
            _make_creature(id=1, species="Alpha"),
            _make_creature(id=2, species="Alpha"),
            _make_creature(id=3, species="Beta"),
        )
        assert w.population_by_species() == {"Alpha": 2, "Beta": 1}


# ═════════════════════════════════════════════════════════════════════════════
# World — spawn_starters
# ═════════════════════════════════════════════════════════════════════════════

class TestSpawnStarters:

    def test_spawns_all_three_species(self):
        w = sim.World(); w.spawn_starters()
        assert {c.species for c in w.creatures} == {"Grazzle", "Thornback", "Vorren"}

    def test_creature_count(self):
        w = sim.World(); w.spawn_starters()
        assert len(w.creatures) == 29  # 16 + 10 + 3

    def test_all_known_species_populated(self):
        w = sim.World(); w.spawn_starters()
        assert {"Grazzle", "Thornback", "Vorren"} <= w.all_known_species

    def test_creature_positions_within_canvas(self):
        w = sim.World(); w.spawn_starters()
        for c in w.creatures:
            assert 0 <= c.x <= sim.CANVAS_W
            assert 0 <= c.y <= sim.CANVAS_H


# ═════════════════════════════════════════════════════════════════════════════
# World — tick_world
# ═════════════════════════════════════════════════════════════════════════════

class TestTickWorld:

    def test_tick_increments(self):
        w = sim.World(); w.spawn_starters(); w.tick_world()
        assert w.tick == 1

    def test_returns_list(self):
        w = sim.World(); w.spawn_starters()
        assert isinstance(w.tick_world(), list)

    def test_creatures_age(self):
        w = sim.World(); c = _make_creature(age=5)
        w.creatures = [c]; w.all_known_species.add("Grazzle")
        w.tick_world()
        if w.creatures: assert w.creatures[0].age == 6

    def test_very_old_creature_dies(self):
        t = sim.Traits(3.0, 7.0, 5.0, 7.0, 2.0)
        c = _make_creature(age=int(30 + 5.0 * 5), traits=t, hunger=10.0, health=100.0)
        w = sim.World(); w.creatures = [c]; w.all_known_species.add("Grazzle")
        w.tick_world()
        assert c not in w.creatures

    def test_starving_carnivore_dies(self):
        """Lone carnivore with hunger=99 hits 100 after one tick."""
        c = _make_creature(hunger=99.0, diet="carnivore")
        w = sim.World(); w.creatures = [c]; w.all_known_species.add("Grazzle")
        w.tick_world()
        assert c not in w.creatures

    def test_plant_abundance_bounded(self):
        w = sim.World(); w.spawn_starters()
        for _ in range(50): w.tick_world()
        assert 2.0 <= w.plant_abundance <= 100.0

    def test_event_log_trimmed_to_80(self):
        w = sim.World(); w.spawn_starters()
        for _ in range(30): w.tick_world()
        assert len(w.event_log) <= 80

    def test_extinction_recorded(self):
        c = _make_creature(id=1, species="Loner", age=999, hunger=99.0, health=1.0)
        w = sim.World(); w.creatures = [c]; w.all_known_species.add("Loner")
        for _ in range(5): w.tick_world()
        assert "Loner" in w.extinct_species


# ═════════════════════════════════════════════════════════════════════════════
# World — apply_disaster
# ═════════════════════════════════════════════════════════════════════════════

class TestDisasters:

    def _world(self, n=20):
        w = sim.World(); w.plant_abundance = 80.0
        for i in range(n):
            w.creatures.append(_make_creature(id=i+1, traits=sim.Traits(6, 6, 6, 6, 6)))
        return w

    def test_meteor_reduces_population(self):
        random.seed(1); w = self._world(40); before = len(w.creatures)
        w.apply_disaster("meteor")
        assert len(w.creatures) < before

    def test_meteor_scorches_plants(self):
        w = self._world(); w.plant_abundance = 80.0
        w.apply_disaster("meteor")
        assert w.plant_abundance < 20.0

    def test_drought_collapses_plants(self):
        w = self._world(); w.apply_disaster("drought")
        assert w.plant_abundance == 3.0

    def test_drought_raises_herbivore_hunger(self):
        w = self._world()
        before = [c.hunger for c in w.creatures]
        w.apply_disaster("drought")
        assert all(a >= b for a, b in zip([c.hunger for c in w.creatures], before))

    def test_bloom_maxes_plants(self):
        w = self._world(); w.plant_abundance = 10.0
        w.apply_disaster("bloom")
        assert w.plant_abundance == 100.0

    def test_bloom_reduces_hunger(self):
        w = self._world()
        for c in w.creatures: c.hunger = 80.0
        w.apply_disaster("bloom")
        for c in w.creatures: assert c.hunger <= 80.0

    def test_plague_kills_one_species(self):
        w = self._world(20)
        for i in range(5):
            w.creatures.append(_make_creature(id=100+i, species="OtherSpecies"))
        random.seed(42); w.apply_disaster("plague")
        assert len(w.creatures) < 25

    def test_plague_empty_world(self):
        assert "Nothing" in sim.World().apply_disaster("plague")

    def test_cold_kills_low_resilience(self):
        random.seed(0); w = sim.World()
        for i in range(20):
            w.creatures.append(_make_creature(id=i, traits=sim.Traits(3, 3, 2.0, 3, 3)))
        before = len(w.creatures); w.apply_disaster("cold")
        assert len(w.creatures) < before

    def test_cold_spares_resilient(self):
        w = sim.World()
        for i in range(10):
            w.creatures.append(_make_creature(id=i, traits=sim.Traits(5, 5, 8.0, 5, 5)))
        w.apply_disaster("cold")
        assert len(w.creatures) == 10

    def test_flood_kills_small(self):
        random.seed(0); w = sim.World()
        for i in range(20):
            w.creatures.append(_make_creature(id=i, traits=sim.Traits(2.0, 5, 5, 5, 5)))
        before = len(w.creatures); w.apply_disaster("flood")
        assert len(w.creatures) < before

    def test_flood_boosts_plants(self):
        w = self._world(); w.plant_abundance = 40.0
        w.apply_disaster("flood")
        assert w.plant_abundance > 40.0

    def test_unknown_disaster(self):
        assert "Unknown" in sim.World().apply_disaster("unicorn")


# ═════════════════════════════════════════════════════════════════════════════
# World — add_species
# ═════════════════════════════════════════════════════════════════════════════

class TestAddSpecies:

    def test_adds_six_creatures(self):
        w = sim.World(); w.add_species("Florp", "🦋", "herbivore")
        assert sum(1 for c in w.creatures if c.species == "Florp") == 6

    def test_species_recorded_as_known(self):
        w = sim.World(); w.add_species("Zorp", "🐍", "carnivore")
        assert "Zorp" in w.all_known_species

    def test_custom_traits_in_range(self):
        w = sim.World(); w.add_species("BigBoi", "🐘", "omnivore",
                                       traits=sim.Traits(9, 9, 9, 9, 9))
        for c in w.creatures:
            for field in ("size", "speed", "resilience", "camouflage", "aggression"):
                assert 1.0 <= getattr(c.traits, field) <= 10.0

    def test_return_message_contains_name(self):
        w = sim.World()
        assert "Glorp" in w.add_species("Glorp", "🐡", "herbivore")


# ═════════════════════════════════════════════════════════════════════════════
# World — serialisation
# ═════════════════════════════════════════════════════════════════════════════

class TestWorldSerialisation:

    def test_to_dict_from_dict_roundtrip(self):
        w = sim.World(); w.spawn_starters()
        w.tick = 42; w.plant_abundance = 55.5; w.extinct_species = {"OldOne"}
        w2 = sim.World.from_dict(w.to_dict())
        assert w2.tick == 42 and w2.plant_abundance == 55.5
        assert w2.extinct_species == {"OldOne"}
        assert len(w2.creatures) == len(w.creatures)

    def test_creatures_survive_roundtrip(self):
        w = sim.World(); w.spawn_starters()
        before = sorted(c.species for c in w.creatures)
        assert before == sorted(c.species for c in sim.World.from_dict(w.to_dict()).creatures)

    def test_save_and_load(self):
        w = sim.World(); w.spawn_starters(); w.tick = 7; w.save()
        w2 = sim.World.load()
        assert w2 is not None and w2.tick == 7
        assert len(w2.creatures) == len(w.creatures)


# ═════════════════════════════════════════════════════════════════════════════
# Settings helpers
# ═════════════════════════════════════════════════════════════════════════════

class TestDeepUpdate:

    def test_shallow_override(self):
        b = _settings._deep_update({"a": 1, "b": 2}, {"b": 99})
        assert b["b"] == 99 and b["a"] == 1

    def test_nested_merge(self):
        b = _settings._deep_update({"x": {"a": 1, "b": 2}}, {"x": {"b": 99}})
        assert b["x"]["a"] == 1 and b["x"]["b"] == 99

    def test_private_keys_ignored(self):
        b = _settings._deep_update({"a": 1}, {"_comment": "ignored"})
        assert "_comment" not in b

    def test_adds_new_key(self):
        b = _settings._deep_update({"a": 1}, {"z": 42})
        assert b["z"] == 42


# ═════════════════════════════════════════════════════════════════════════════
# image_gen helpers
# ═════════════════════════════════════════════════════════════════════════════

class TestPick:

    def test_finds_keyword(self):
        assert _image_gen._pick(["flux1-schnell.safetensors", "sdxl.safetensors"], "schnell") \
               == "flux1-schnell.safetensors"

    def test_case_insensitive(self):
        assert _image_gen._pick(["Flux1-Schnell.safetensors"], "schnell") \
               == "Flux1-Schnell.safetensors"

    def test_first_keyword_wins(self):
        assert _image_gen._pick(["clip_l.safetensors", "t5xxl.safetensors"], "t5", "clip") \
               == "t5xxl.safetensors"

    def test_returns_none_when_no_match(self):
        assert _image_gen._pick(["abc.safetensors"], "xyz") is None

    def test_empty_choices(self):
        assert _image_gen._pick([], "flux") is None


class TestBuildWorkflowMerged:

    def test_required_nodes_present(self):
        wf = _image_gen._build_workflow_merged("test prompt", seed=42, ckpt="flux.safetensors")
        class_types = {v["class_type"] for v in wf.values()}
        assert {"CheckpointLoaderSimple", "KSampler", "SaveImage"} <= class_types

    def test_prompt_in_clip_node(self):
        wf = _image_gen._build_workflow_merged("my unique prompt", seed=1, ckpt="c.safetensors")
        clip_texts = [v["inputs"]["text"] for v in wf.values() if v["class_type"] == "CLIPTextEncode"]
        assert "my unique prompt" in clip_texts

    def test_seed_in_ksampler(self):
        wf = _image_gen._build_workflow_merged("p", seed=12345, ckpt="c.safetensors")
        sampler = next(v for v in wf.values() if v["class_type"] == "KSampler")
        assert sampler["inputs"]["seed"] == 12345


# ═════════════════════════════════════════════════════════════════════════════
# Movement
# ═════════════════════════════════════════════════════════════════════════════

class TestMovement:

    def test_wraps_horizontally(self):
        w = sim.World()
        c = _make_creature(x=sim.CANVAS_W - 1, y=100.0, dx=5.0, dy=0.0)
        w.creatures = [c]; w._move()
        assert 0 <= c.x < sim.CANVAS_W

    def test_wraps_vertically(self):
        w = sim.World()
        c = _make_creature(x=100.0, y=sim.CANVAS_H - 1, dx=0.0, dy=5.0)
        w.creatures = [c]; w._move()
        assert 0 <= c.y < sim.CANVAS_H


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])