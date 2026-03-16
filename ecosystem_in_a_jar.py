#!/usr/bin/env python3
"""
🫙 ECOSYSTEM IN A JAR  — PyQt6 edition
Living simulation · evolving creatures · disasters · AI lore

Requirements:
    pip install PyQt6 requests

Ollama (local AI narrator):
    ollama pull gemma3:27b
    ollama serve

Edit settings.json to change colours, fonts, model, and timing.
State is saved to ./jar_data/ automatically.
"""

import json, math, random, datetime, sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSlider, QTextEdit, QScrollArea,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QFrame, QSplitter,
    QDialog, QDialogButtonBox, QLineEdit, QRadioButton, QButtonGroup,
    QDoubleSpinBox, QGroupBox, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (
    QFont, QPainter, QColor, QBrush, QPen, QTextCursor, QPalette,
)
import requests

# ─────────────────────── SETTINGS ────────────────────────────

SETTINGS_PATH = Path("./settings.json")
DATA_DIR      = Path("./jar_data")
CANVAS_W, CANVAS_H = 520, 400
HUNT_RADIUS   = 80.0
SEASON_LENGTH = 30
SEASONS       = ["🌱 Spring", "☀️ Summer", "🍂 Autumn", "❄️ Winter"]
SEASON_PLANT  = [80, 95, 50, 18]


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
        "ollama": {
            "model": "gemma3:27b",
            "url": "http://localhost:11434/api/generate",
            "max_tokens": 180, "temperature": 0.88, "auto_advance_sec": 4,
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


CFG = load_settings()
C   = CFG["colors"]
F   = CFG["font"]
OL  = CFG["ollama"]


def mkfont(key: str = "ui", bold: bool = False, italic: bool = False) -> QFont:
    f = QFont(F.get(f"family_{key}", F["family_ui"]),
              F.get(f"size_{key}", F["size_ui"]))
    f.setBold(bold); f.setItalic(italic)
    return f


def btn_css(bg: str, fg_key: str = "text_button") -> str:
    bg_c = QColor(bg)
    hov  = bg_c.lighter(120).name()
    prs  = bg_c.lighter(90).name()
    return f"""
        QPushButton {{
            background: {bg}; color: {C[fg_key]};
            border: 1px solid {C['border']}; border-radius: 5px;
            padding: 5px 9px;
        }}
        QPushButton:hover   {{ background: {hov}; }}
        QPushButton:pressed {{ background: {prs}; }}
        QPushButton:disabled {{
            color: {C['text_screen_dim']}; background: {C['panel_bg_alt']};
        }}
    """


# ═══════════════════════ SIMULATION ═══════════════════════════

@dataclass
class Traits:
    size: float; speed: float; resilience: float
    camouflage: float; aggression: float

    def mutate(self) -> "Traits":
        def m(v):
            if random.random() < 0.30: v += random.gauss(0, 0.35)
            return round(max(1.0, min(10.0, v)), 2)
        return Traits(m(self.size), m(self.speed), m(self.resilience),
                      m(self.camouflage), m(self.aggression))

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
        for c in self.creatures: out[c.species] = out.get(c.species,0) + 1
        return out

    def spawn_starters(self):
        for name,emoji,diet,sz,sp,rs,cm,ag,count in STARTER_SPECIES:
            self.all_known_species.add(name)
            base = Traits(sz,sp,rs,cm,ag)
            for _ in range(count):
                c = Creature(id=self.new_id(),species=name,emoji=emoji,diet=diet,
                             traits=base.mutate(),generation=1,
                             x=random.uniform(20,CANVAS_W-20),
                             y=random.uniform(20,CANVAS_H-20))
                angle=random.uniform(0,2*math.pi); spd=random.uniform(1.5,3.0)
                c.dx,c.dy=math.cos(angle)*spd,math.sin(angle)*spd
                self.creatures.append(c)

    def _move(self):
        for c in self.creatures:
            if random.random()<0.12:
                angle=random.uniform(0,2*math.pi)
                spd=(c.traits.speed/5.0)*random.uniform(1.5,3.0)
                c.dx,c.dy=math.cos(angle)*spd,math.sin(angle)*spd
            c.x=(c.x+c.dx)%CANVAS_W; c.y=(c.y+c.dy)%CANVAS_H

    def tick_world(self) -> list:
        self.tick+=1; events=[]; self._move()
        target=SEASON_PLANT[self.season_idx]
        self.plant_abundance+=(target-self.plant_abundance)*0.10
        self.plant_abundance=max(2.0,min(100.0,self.plant_abundance+random.gauss(0,1.8)))
        herbivores=[c for c in self.creatures if c.diet in ("herbivore","omnivore")]
        carnivores=[c for c in self.creatures if c.diet in ("carnivore","omnivore")]
        share=self.plant_abundance/max(len(herbivores),1)
        for c in herbivores:
            c.hunger=max(0.0,c.hunger-min(share*(c.traits.speed/5.0)*2.0,55.0))
        for pred in carnivores:
            if pred.hunger<30: continue
            nearby=[p for p in herbivores if math.hypot(p.x-pred.x,p.y-pred.y)<=HUNT_RADIUS]
            if not nearby: pred.hunger=min(100.0,pred.hunger+2); continue
            prey=random.choice(nearby)
            hunt=pred.traits.aggression+pred.traits.speed
            evade=prey.traits.camouflage*1.6+prey.traits.speed
            if random.random()<hunt/(hunt+evade):
                pred.hunger=max(0.0,pred.hunger-65); prey.health-=random.uniform(30,75)
                if prey.health<=0:
                    events.append(f"{pred.emoji} {pred.species} kills a {prey.emoji} {prey.species}")
        survivors=[]
        for c in self.creatures:
            c.age+=1; c.hunger=min(100.0,c.hunger+random.uniform(3.5,7.5))
            if c.hunger>70: c.health-=(c.hunger-70)/max(c.traits.resilience*1.5,1)
            elif c.hunger<30: c.health=min(100.0,c.health+1.2)
            if c.hunger>=100 or c.health<=0 or c.age>=c.max_age():
                if c.age>=c.max_age(): events.append(f"🕯️ A {c.emoji} {c.species} dies at age {c.age}")
                elif c.hunger>=100: events.append(f"💧 A {c.emoji} {c.species} starves")
                continue
            repro={"herbivore":0.055,"carnivore":0.018,"omnivore":0.038}
            minage={"herbivore":6,"carnivore":14,"omnivore":10}
            dens=max(0.0,(len(herbivores)-22)*0.003) if c.diet=="herbivore" else 0.0
            rate=max(0.003,repro.get(c.diet,0.04)*(c.traits.resilience/5.0)-dens)
            if c.hunger<35 and c.health>60 and c.age>minage.get(c.diet,8) and random.random()<rate:
                child=Creature(id=self.new_id(),species=c.species,emoji=c.emoji,
                               diet=c.diet,traits=c.traits.mutate(),generation=c.generation+1,
                               x=c.x+random.uniform(-10,10),y=c.y+random.uniform(-10,10))
                angle=random.uniform(0,2*math.pi); spd=(child.traits.speed/5.0)*random.uniform(1.5,3.0)
                child.dx,child.dy=math.cos(angle)*spd,math.sin(angle)*spd
                survivors.append(child)
            survivors.append(c)
        self.creatures=survivors
        alive={c.species for c in self.creatures}
        for sp in list(self.all_known_species):
            if sp not in alive and sp not in self.extinct_species:
                self.extinct_species.add(sp); events.append(f"💀 {sp} has gone EXTINCT")
        self.event_log=(events+self.event_log)[:80]; return events

    def apply_disaster(self,kind:str)->str:
        k=kind.lower()
        if k=="meteor":
            n=sum(1 for c in self.creatures if random.random()<0.60)
            self.creatures=[c for c in self.creatures if random.random()>=0.60]
            self.plant_abundance*=0.10; return f"☄️ Meteor! {n} killed. Plants scorched."
        elif k=="drought":
            self.plant_abundance=3.0
            for c in self.creatures:
                if c.diet!="carnivore": c.hunger=min(100,c.hunger+45)
            return "🏜️ Drought — vegetation collapses."
        elif k=="plague":
            sp_list=list({c.species for c in self.creatures})
            if not sp_list: return "🦠 Nothing to infect."
            target=random.choice(sp_list)
            before=sum(1 for c in self.creatures if c.species==target)
            self.creatures=[c for c in self.creatures if c.species!=target or random.random()>=0.75]
            after=sum(1 for c in self.creatures if c.species==target)
            return f"🦠 Plague hits {target} — {before-after} dead."
        elif k=="bloom":
            self.plant_abundance=100.0
            for c in self.creatures: c.hunger=max(0,c.hunger-55)
            return "🌸 Miraculous bloom — every creature feasts."
        elif k=="cold":
            n=sum(1 for c in self.creatures if c.traits.resilience<5 and random.random()<0.45)
            self.creatures=[c for c in self.creatures if c.traits.resilience>=5 or random.random()>=0.45]
            return f"🧊 Cold snap — {n} fragile creatures perish."
        elif k=="flood":
            self.plant_abundance=min(100,self.plant_abundance+35)
            n=sum(1 for c in self.creatures if c.traits.size<4 and random.random()<0.50)
            self.creatures=[c for c in self.creatures if c.traits.size>=4 or random.random()>=0.50]
            return f"🌊 Flood! {n} small creatures drown."
        return f"Unknown: {kind}"

    def add_species(self,name,emoji,diet,traits=None)->str:
        if traits is None: traits=Traits(*[random.uniform(3,7) for _ in range(5)])
        self.all_known_species.add(name)
        for _ in range(6):
            c=Creature(id=self.new_id(),species=name,emoji=emoji,diet=diet,
                       traits=traits.mutate(),generation=1,
                       x=random.uniform(20,CANVAS_W-20),y=random.uniform(20,CANVAS_H-20))
            angle=random.uniform(0,2*math.pi); spd=(c.traits.speed/5.0)*2.0
            c.dx,c.dy=math.cos(angle)*spd,math.sin(angle)*spd; self.creatures.append(c)
        return f"✨ {name} {emoji} ({diet}) introduced — 6 individuals."

    def to_dict(self):
        return {"tick":self.tick,"_next_id":self._next_id,
                "plant_abundance":self.plant_abundance,
                "creatures":[c.to_dict() for c in self.creatures],
                "event_log":self.event_log,
                "extinct_species":list(self.extinct_species),
                "all_known_species":list(self.all_known_species)}

    @classmethod
    def from_dict(cls,d):
        w=cls(); w.tick=d["tick"]; w._next_id=d["_next_id"]
        w.plant_abundance=d["plant_abundance"]
        w.creatures=[Creature.from_dict(c) for c in d["creatures"]]
        w.event_log=d.get("event_log",[]); w.extinct_species=set(d.get("extinct_species",[]))
        w.all_known_species=set(d.get("all_known_species",[])); return w

    def save(self):
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        (DATA_DIR/"world.json").write_text(json.dumps(self.to_dict(),indent=2))

    @classmethod
    def load(cls):
        fp=DATA_DIR/"world.json"
        if not fp.exists(): return None
        return cls.from_dict(json.loads(fp.read_text()))


# ════════════════════ OLLAMA WORKER ═══════════════════════════

class NarrationWorker(QThread):
    done = pyqtSignal(str)

    def __init__(self, world: World, events: list):
        super().__init__(); self.world=world; self.events=events

    def run(self):
        pop=self.world.population_by_species()
        pop_str=", ".join(f"{k}: {v}" for k,v in pop.items()) or "nothing survives"
        evt_str="\n".join(f"- {e}" for e in self.events[:6]) or "- Quiet."
        ext_str=", ".join(self.world.extinct_species) or "none yet"
        prompt=(
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
            r=requests.post(OL["url"],json={
                "model":OL["model"],"prompt":prompt,"stream":False,
                "options":{"num_predict":OL["max_tokens"],"temperature":OL["temperature"]}
            },timeout=45)
            if r.status_code==200: self.done.emit(r.json().get("response","").strip()); return
            self.done.emit(f"(Ollama returned {r.status_code})")
        except requests.exceptions.ConnectionError:
            self.done.emit("(Ollama not reachable — run: ollama serve)")
        except Exception as e:
            self.done.emit(f"(Narrator error: {e})")


def append_lore(world: World, narration: str, events: list):
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    entry={"tick":world.tick,"year":world.year,"season":world.season,
           "narration":narration,"events":events,
           "populations":world.population_by_species(),
           "plants":round(world.plant_abundance,1),
           "timestamp":datetime.datetime.now().isoformat()}
    with open(DATA_DIR/"lore.jsonl","a") as f: f.write(json.dumps(entry)+"\n")


# ═══════════════════════ CANVAS ════════════════════════════════

class JarCanvas(QWidget):
    def __init__(self, world: World, parent=None):
        super().__init__(parent); self.world=world
        self.setFixedSize(CANVAS_W, CANVAS_H)
        random.seed(42)
        self._plant_pos=[(random.randint(0,CANVAS_W),random.randint(0,CANVAS_H)) for _ in range(90)]
        random.seed()

    def paintEvent(self, _):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0,0,CANVAS_W,CANVAS_H,QColor(C["canvas_bg"]))
        density=self.world.plant_abundance/100.0
        p.setBrush(QBrush(QColor(C["plant_dot"]))); p.setPen(Qt.PenStyle.NoPen)
        for px,py in self._plant_pos[:int(density*90)]:
            p.drawEllipse(QPointF(px,py),2.5,2.5)
        for c in self.world.creatures:
            col=QColor(C["creature_unhealthy"] if c.health<50
                       else C.get(f"creature_{c.diet}","#ffffff"))
            r=4+c.traits.size*0.65
            p.setBrush(QBrush(col)); p.setPen(QPen(QColor("#000000"),0.5))
            p.drawEllipse(QPointF(c.x,c.y),r,r)
        p.end()


# ═══════════════════════ SPECIES TREE ══════════════════════════

class SpeciesTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        headers=["Species","Pop","Diet","Size","Speed","Resil","Camo","Aggr","Gen"]
        self.setHeaderLabels(headers); self.setColumnCount(len(headers))
        for i,w in enumerate([110,40,100,58,58,58,58,58,52]): self.setColumnWidth(i,w)
        self.setFont(mkfont("ui")); self.setAlternatingRowColors(False)
        self.setStyleSheet(f"""
            QTreeWidget {{background:{C['panel_bg']};color:{C['text_screen']};
                          border:none;outline:none;}}
            QTreeWidget::item {{padding:2px;border-bottom:1px solid {C['border']};}}
            QTreeWidget::item:selected {{background:{C['panel_bg_alt']};}}
            QHeaderView::section {{background:{C['panel_bg_alt']};color:{C['text_screen_dim']};
                                   border:none;border-bottom:1px solid {C['border']};padding:4px;}}
        """)

    def populate(self,world:World):
        self.clear()
        sp={}
        for c in world.creatures:
            if c.species not in sp:
                sp[c.species]={"emoji":c.emoji,"diet":c.diet,"count":0,"traits":[],"gens":[]}
            sp[c.species]["count"]+=1; sp[c.species]["traits"].append(c.traits)
            sp[c.species]["gens"].append(c.generation)
        def tbar(v): return "█"*int((v/10)*6)+"░"*(6-int((v/10)*6))
        dsym={"herbivore":"🌿","carnivore":"🔴","omnivore":"🟡"}
        dcol={"herbivore":C["creature_herbivore"],"carnivore":C["creature_carnivore"],
              "omnivore":C["creature_omnivore"]}
        for name,d in sorted(sp.items(),key=lambda x:-x[1]["count"]):
            trs=d["traits"]; avg=lambda a: sum(getattr(t,a) for t in trs)/len(trs)
            g=sum(d["gens"])/len(d["gens"])
            it=QTreeWidgetItem([f"{d['emoji']} {name}",str(d["count"]),
                f"{dsym.get(d['diet'],'?')} {d['diet']}",
                tbar(avg("size")),tbar(avg("speed")),tbar(avg("resilience")),
                tbar(avg("camouflage")),tbar(avg("aggression")),f"G{g:.1f}"])
            it.setForeground(0,QColor(C["text_screen"]))
            it.setForeground(1,QColor(dcol.get(d["diet"],C["text_screen"])))
            for col in range(2,9): it.setForeground(col,QColor(C["text_screen_dim"]))
            self.addTopLevelItem(it)
        for name in sorted(world.extinct_species):
            it=QTreeWidgetItem([f"💀 {name}","0","extinct","—","—","—","—","—","—"])
            for col in range(9): it.setForeground(col,QColor(C["text_screen_dim"]))
            self.addTopLevelItem(it)


# ═════════════════════ MAIN WINDOW ════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🫙 Ecosystem in a Jar"); self.setMinimumSize(1100,720)
        world=World.load(); is_new=(world is None)
        if is_new: world=World(); world.spawn_starters(); world.save()
        self.world=world
        self._narration="Press ▶ Advance to begin."
        self._narrator=None; self._narrator_busy=False
        self._auto_timer=QTimer(); self._auto_timer.timeout.connect(self._advance)
        self._anim_timer=QTimer(); self._anim_timer.timeout.connect(lambda: self.canvas.update())
        self._anim_timer.start(80)
        self._build_ui(); self._apply_style(); self._refresh_all()
        self._log("🫙 New jar." if is_new else f"🫙 Resumed — Year {world.year}, {world.season}, Tick {world.tick}")

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow,QWidget{{background:{C['window_bg']};color:{C['text_screen']};}}
            QScrollBar:vertical{{background:{C['panel_bg_alt']};width:8px;border-radius:4px;}}
            QScrollBar::handle:vertical{{background:{C['border']};border-radius:4px;}}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
            QScrollBar:horizontal{{background:{C['panel_bg_alt']};height:8px;border-radius:4px;}}
            QScrollBar::handle:horizontal{{background:{C['border']};border-radius:4px;}}
            QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0;}}
            QToolTip{{background:{C['panel_bg_alt']};color:{C['text_screen']};
                      border:1px solid {C['border']};padding:5px 9px;border-radius:4px;}}
        """)

    def _panel(self)->QFrame:
        f=QFrame(); f.setFrameShape(QFrame.Shape.StyledPanel)
        f.setStyleSheet(f"QFrame{{background:{C['panel_bg']};border:1px solid {C['border']};border-radius:6px;}}")
        return f

    def _btn(self,text:str,cb,bg_key:str,tip:str="",fg_key:str="text_button")->QPushButton:
        b=QPushButton(text); b.setFont(mkfont("ui"))
        b.setStyleSheet(btn_css(C[bg_key],fg_key))
        b.setCursor(Qt.CursorShape.PointingHandCursor); b.clicked.connect(cb)
        if tip: b.setToolTip(tip)
        return b

    def _lbl(self,text:str,col_key:str="text_screen",bold:bool=False)->QLabel:
        l=QLabel(text); l.setFont(mkfont("ui",bold=bold))
        l.setStyleSheet(f"color:{C[col_key]};background:transparent;"); return l

    def _build_ui(self):
        root_w=QWidget(); self.setCentralWidget(root_w)
        root=QVBoxLayout(root_w); root.setSpacing(6); root.setContentsMargins(8,8,8,8)

        # Top bar
        top=QHBoxLayout()
        t=QLabel("🫙  ECOSYSTEM IN A JAR"); t.setFont(mkfont("title",bold=True))
        t.setStyleSheet(f"color:{C['accent_green']};background:transparent;"); top.addWidget(t)
        self._lbl_info=self._lbl("",col_key="text_screen_dim"); top.addWidget(self._lbl_info)
        top.addStretch(); root.addLayout(top)

        # Splitter
        spl=QSplitter(Qt.Orientation.Horizontal)
        spl.setChildrenCollapsible(False)
        spl.setStyleSheet("QSplitter::handle{background:transparent;width:6px;}")
        root.addWidget(spl,stretch=1)

        # ── Left: canvas ──────────────────────────────────
        lp=self._panel(); lv=QVBoxLayout(lp); lv.setSpacing(4); lv.setContentsMargins(8,8,8,8)
        jar_lbl=self._lbl("The Jar",col_key="text_screen_dim")
        jar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); lv.addWidget(jar_lbl)
        self.canvas=JarCanvas(self.world); lv.addWidget(self.canvas)
        pr=QHBoxLayout()
        pr.addWidget(self._lbl("🌿 Plants",col_key="text_screen_dim"))
        self._plant_bar=QProgressBar(); self._plant_bar.setRange(0,100)
        self._plant_bar.setTextVisible(False); self._plant_bar.setFixedHeight(10)
        self._plant_bar.setStyleSheet(
            f"QProgressBar{{background:{C['progressbar_bg']};border-radius:5px;border:none;}}"
            f"QProgressBar::chunk{{background:{C['progressbar_fill']};border-radius:5px;}}")
        pr.addWidget(self._plant_bar,stretch=1)
        self._plant_lbl=self._lbl("75","accent_green"); self._plant_lbl.setFixedWidth(30)
        pr.addWidget(self._plant_lbl); lv.addLayout(pr); spl.addWidget(lp)

        # ── Middle: species + log ─────────────────────────
        mw=QWidget(); mw.setStyleSheet("background:transparent;")
        mv=QVBoxLayout(mw); mv.setSpacing(6); mv.setContentsMargins(0,0,0,0)
        sp=self._panel(); spv=QVBoxLayout(sp); spv.setSpacing(4); spv.setContentsMargins(6,6,6,6)
        st=self._lbl("Species",bold=True); st.setAlignment(Qt.AlignmentFlag.AlignCenter); spv.addWidget(st)
        self.tree=SpeciesTree(); spv.addWidget(self.tree,stretch=1)
        mv.addWidget(sp,stretch=1)
        lgp=self._panel(); lgp.setFixedHeight(165)
        lgv=QVBoxLayout(lgp); lgv.setSpacing(3); lgv.setContentsMargins(6,6,6,6)
        lgv.addWidget(self._lbl("Event log",col_key="text_screen_dim"))
        self._log_text=QTextEdit(); self._log_text.setReadOnly(True)
        self._log_text.setFont(mkfont("mono"))
        self._log_text.setStyleSheet(
            f"QTextEdit{{background:{C['panel_bg']};color:{C['text_screen_dim']};border:none;padding:2px;}}")
        lgv.addWidget(self._log_text); mv.addWidget(lgp); spl.addWidget(mw)

        # ── Right: narration + controls ───────────────────
        rw=QWidget(); rw.setStyleSheet("background:transparent;"); rw.setFixedWidth(280)
        rv=QVBoxLayout(rw); rv.setSpacing(6); rv.setContentsMargins(0,0,0,0)
        np=self._panel(); nv=QVBoxLayout(np); nv.setSpacing(4); nv.setContentsMargins(8,8,8,8)
        nt=QLabel("📽️  Nature Doc"); nt.setFont(mkfont("ui",bold=True))
        nt.setStyleSheet(f"color:{C['accent_yellow']};background:transparent;")
        nt.setAlignment(Qt.AlignmentFlag.AlignCenter); nv.addWidget(nt)
        self._nar_text=QTextEdit(); self._nar_text.setReadOnly(True)
        self._nar_text.setFont(mkfont("lore",italic=True))
        self._nar_text.setStyleSheet(
            f"QTextEdit{{background:{C['panel_bg']};color:{C['text_lore']};border:none;padding:4px;}}")
        nv.addWidget(self._nar_text,stretch=1)
        self._nar_spin=QLabel(""); self._nar_spin.setFont(mkfont("ui"))
        self._nar_spin.setStyleSheet(f"color:{C['accent_yellow']};background:transparent;")
        self._nar_spin.setAlignment(Qt.AlignmentFlag.AlignCenter); nv.addWidget(self._nar_spin)
        rv.addWidget(np,stretch=1)

        # Controls panel
        cp=self._panel(); cv=QVBoxLayout(cp); cv.setSpacing(5); cv.setContentsMargins(8,8,8,8)

        # Advance + auto
        ar=QHBoxLayout(); ar.setSpacing(4)
        self._btn_adv=self._btn("▶  Advance  (+10)",self._advance,"btn_advance",
            tip="Run 10 simulation ticks and request narration from Ollama.")
        ar.addWidget(self._btn_adv,stretch=1)
        self._btn_auto=self._btn("⏸",self._toggle_auto,"btn_auto",fg_key="text_button",
            tip=f"Toggle auto-advance (runs every {OL['auto_advance_sec']}s automatically).")
        self._btn_auto.setFixedWidth(38); ar.addWidget(self._btn_auto); cv.addLayout(ar)

        # Fast-forward
        ff=QHBoxLayout(); ff.setSpacing(6)
        fl=self._lbl("⏭ Skip:","text_screen_dim"); ff.addWidget(fl)
        self._fast_sl=QSlider(Qt.Orientation.Horizontal)
        self._fast_sl.setRange(10,500); self._fast_sl.setValue(50)
        self._fast_sl.setToolTip("Number of ticks to skip (no narration).")
        self._fast_sl.setStyleSheet(f"""
            QSlider::groove:horizontal{{background:{C['panel_bg_alt']};height:6px;border-radius:3px;}}
            QSlider::handle:horizontal{{background:{C['accent_blue']};width:14px;height:14px;
                border-radius:7px;margin:-4px 0;}}
            QSlider::sub-page:horizontal{{background:{C['accent_blue']};border-radius:3px;}}
        """)
        self._fast_val=self._lbl("50t","text_screen_dim"); self._fast_val.setFixedWidth(34)
        self._fast_sl.valueChanged.connect(lambda v: self._fast_val.setText(f"{v}t"))
        ff.addWidget(self._fast_sl,stretch=1); ff.addWidget(self._fast_val)
        ff.addWidget(self._btn("⏭",self._fast_forward,"btn_default",
            tip="Jump forward the selected number of ticks instantly."))
        cv.addLayout(ff)

        # Disasters
        cv.addWidget(self._lbl("DISASTERS","text_screen_dim"))
        DISASTERS=[
            ("☄️  Meteor","meteor","btn_meteor","60% of all creatures die instantly. Plants scorched to 10%.","text_button_danger"),
            ("🏜️  Drought","drought","btn_drought","Vegetation crashes to 3. Herbivores begin starving immediately.","text_button_danger"),
            ("🦠 Plague","plague","btn_plague","75% of one randomly chosen species is wiped out.","text_button_danger"),
            ("🌸 Bloom","bloom","btn_bloom","Plants max to 100. All creatures are immediately fed.","text_button"),
            ("🧊 Cold","cold","btn_cold","Creatures with resilience < 5 face a 45% chance of death.","text_button_danger"),
            ("🌊 Flood","flood","btn_flood","Small creatures (size < 4) have a 50% death chance. Plants gain +35.","text_button_danger"),
        ]
        dg=QGridLayout(); dg.setSpacing(4)
        for i,(label,kind,bg,tip,fg_k) in enumerate(DISASTERS):
            dg.addWidget(self._btn(label,lambda k=kind:self._disaster(k),bg,tip=tip,fg_key=fg_k),i//2,i%2)
        cv.addLayout(dg)

        # Add / Lore
        br=QHBoxLayout(); br.setSpacing(4)
        br.addWidget(self._btn("✨ Add Species",self._add_species_dialog,"btn_add",
            tip="Open a dialog to introduce a fully custom species with hand-crafted traits."))
        br.addWidget(self._btn("📖 Lore",self._open_lore,"btn_lore",
            tip="Browse the complete AI-narrated history of everything that has happened in the jar."))
        cv.addLayout(br); rv.addWidget(cp); spl.addWidget(rw)
        spl.setSizes([CANVAS_W+30, 570, 290])

    # ─────────────────── REFRESH ──────────────────────────────

    def _refresh_all(self):
        w=self.world; total=sum(w.population_by_species().values())
        self._lbl_info.setText(
            f"Year {w.year}  ·  {w.season}  ·  Tick {w.tick}"
            f"  ·  {total} creatures  ·  {len(w.extinct_species)} extinct")
        self._plant_bar.setValue(int(w.plant_abundance))
        self._plant_lbl.setText(f"{w.plant_abundance:.0f}")
        self.tree.populate(w); self._set_narration(self._narration)

    def _set_narration(self,text:str):
        self._nar_text.setPlainText(text); self._narration=text

    def _log(self,msg:str):
        ts=datetime.datetime.now().strftime("%H:%M:%S")
        self._log_text.append(f"[{ts}] {msg}")
        self._log_text.moveCursor(QTextCursor.MoveOperation.End)

    # ─────────────────── ACTIONS ──────────────────────────────

    def _run_ticks(self,n:int)->list:
        all_e=[]
        for _ in range(n):
            all_e.extend(self.world.tick_world())
            if not self.world.creatures: break
        return all_e

    def _advance(self):
        if self._narrator_busy: return
        events=self._run_ticks(10); self.world.save()
        self._refresh_all()
        for e in events[:5]: self._log(e)
        self._start_narration(events)

    def _start_narration(self,events:list):
        self._narrator_busy=True; self._nar_spin.setText("✦ narrating…")
        self._narrator=NarrationWorker(self.world,events)
        self._narrator.done.connect(self._on_narration_done)
        self._narrator.start()

    def _on_narration_done(self,text:str):
        self._narrator_busy=False; self._nar_spin.setText("")
        append_lore(self.world,text,[]); self._set_narration(text)

    def _toggle_auto(self):
        if self._auto_timer.isActive():
            self._auto_timer.stop(); self._btn_auto.setText("⏸")
            self._btn_auto.setStyleSheet(btn_css(C["btn_auto"])); self._log("Auto paused.")
        else:
            self._auto_timer.start(OL["auto_advance_sec"]*1000)
            self._btn_auto.setText("⏹")
            self._btn_auto.setStyleSheet(btn_css(C["accent_red"])); self._log("Auto started.")

    def _fast_forward(self):
        n=self._fast_sl.value(); self._log(f"⏭ Fast-forwarding {n} ticks…")
        events=self._run_ticks(n); self.world.save(); self._refresh_all()
        for e in events[-4:]: self._log(e)
        self._log(f"Done. Tick {self.world.tick}")
        self._set_narration(f"({n} ticks pass in the blink of an eye.)")

    def _disaster(self,kind:str):
        msg=self.world.apply_disaster(kind); self._log(msg)
        events=self._run_ticks(10); self.world.save(); self._refresh_all()
        self._start_narration([msg]+events)

    # ─────────────────── ADD SPECIES ──────────────────────────

    def _add_species_dialog(self):
        dlg=QDialog(self); dlg.setWindowTitle("Add Species"); dlg.setMinimumWidth(340)
        dlg.setStyleSheet(f"""
            QDialog{{background:{C['window_bg']};}}
            QLabel{{color:{C['text_screen']};background:transparent;}}
            QLineEdit,QDoubleSpinBox{{background:{C['panel_bg_alt']};color:{C['text_screen']};
                border:1px solid {C['border']};border-radius:4px;padding:4px;}}
            QRadioButton{{color:{C['text_screen']};background:transparent;}}
            QGroupBox{{color:{C['text_screen_dim']};border:1px solid {C['border']};
                border-radius:4px;margin-top:8px;padding-top:12px;}}
            QGroupBox::title{{subcontrol-origin:margin;left:8px;}}
        """)
        lay=QVBoxLayout(dlg); lay.setSpacing(10)

        def row(lbl,w):
            h=QHBoxLayout(); l=QLabel(lbl); l.setFont(mkfont("ui")); l.setFixedWidth(80)
            h.addWidget(l); h.addWidget(w); return h

        name_e=QLineEdit("Kreel"); name_e.setFont(mkfont("ui"))
        emoji_e=QLineEdit("🦎");  emoji_e.setFont(mkfont("ui"))
        lay.addLayout(row("Name:",name_e)); lay.addLayout(row("Emoji:",emoji_e))

        diet_gb=QGroupBox("Diet"); dgl=QHBoxLayout(diet_gb); diet_bg=QButtonGroup()
        for d in ("herbivore","carnivore","omnivore"):
            rb=QRadioButton(d); rb.setFont(mkfont("ui"))
            if d=="herbivore": rb.setChecked(True)
            diet_bg.addButton(rb); dgl.addWidget(rb)
        lay.addWidget(diet_gb)

        trait_gb=QGroupBox("Traits  (1 = min · 10 = max)")
        tgl=QGridLayout(trait_gb); tgl.setSpacing(6); trait_spins={}
        for i,t in enumerate(["size","speed","resilience","camouflage","aggression"]):
            l=QLabel(t.capitalize()); l.setFont(mkfont("ui"))
            sp=QDoubleSpinBox(); sp.setRange(1,10); sp.setValue(5.0)
            sp.setSingleStep(0.5); sp.setFont(mkfont("ui")); trait_spins[t]=sp
            tgl.addWidget(l,i,0); tgl.addWidget(sp,i,1)
        lay.addWidget(trait_gb)

        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.setFont(mkfont("ui")); bb.setStyleSheet(btn_css(C["btn_advance"]))
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)

        if dlg.exec()==QDialog.DialogCode.Accepted:
            name=name_e.text().strip().capitalize() or "Unknown"
            emoji=emoji_e.text().strip() or "❓"
            diet=next((b.text() for b in diet_bg.buttons() if b.isChecked()),"herbivore")
            tr=Traits(**{k:v.value() for k,v in trait_spins.items()})
            msg=self.world.add_species(name,emoji,diet,tr)
            self.world.save(); self._log(msg); self._refresh_all()

    # ─────────────────── LORE ─────────────────────────────────

    def _open_lore(self):
        lp=DATA_DIR/"lore.jsonl"
        if not lp.exists():
            QMessageBox.information(self,"Lore","No lore yet — press Advance to start."); return
        dlg=QDialog(self); dlg.setWindowTitle("📖 The Lore of the Jar"); dlg.resize(640,640)
        dlg.setStyleSheet(f"QDialog{{background:{C['window_bg']};}}")
        lv=QVBoxLayout(dlg)
        txt=QTextEdit(); txt.setReadOnly(True); txt.setFont(mkfont("lore",italic=True))
        txt.setStyleSheet(
            f"QTextEdit{{background:{C['panel_bg']};color:{C['text_lore']};border:none;padding:8px;}}")
        lv.addWidget(txt)
        with open(lp) as f:
            for line in f:
                e=json.loads(line)
                txt.append(f"\n{'─'*52}"); txt.append(f"Year {e['year']} · {e['season']} · Tick {e['tick']}\n")
                txt.append(e["narration"])
                for ev in (e.get("events") or [])[:4]: txt.append(f"  • {ev}")
        txt.moveCursor(QTextCursor.MoveOperation.End); dlg.exec()

    def closeEvent(self,event):
        self._auto_timer.stop(); self._anim_timer.stop(); self.world.save(); event.accept()


# ════════════════════ ENTRY POINT ═════════════════════════════

if __name__=="__main__":
    app=QApplication(sys.argv); app.setApplicationName("Ecosystem in a Jar")
    from PyQt6.QtWidgets import QToolTip
    QToolTip.setFont(mkfont("ui"))
    win=MainWindow(); win.show(); sys.exit(app.exec())
