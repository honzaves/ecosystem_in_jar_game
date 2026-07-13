"""SpeciesTree widget — tabular view of living and extinct species."""

from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from settings import C
from simulation import World
from ui_utils import mkfont


class SpeciesTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        headers = ["Species", "Pop", "Diet", "Size", "Speed", "Resil", "Camo", "Aggr", "Gen"]
        self.setHeaderLabels(headers); self.setColumnCount(len(headers))
        for i, w in enumerate([110, 40, 100, 58, 58, 58, 58, 58, 52]):
            self.setColumnWidth(i, w)
        self.setFont(mkfont("ui")); self.setAlternatingRowColors(False)
        self.setStyleSheet(f"""
            QTreeWidget {{background:{C['panel_bg']};color:{C['text_screen']};
                          border:none;outline:none;}}
            QTreeWidget::item {{padding:2px;border-bottom:1px solid {C['border']};}}
            QTreeWidget::item:selected {{background:{C['panel_bg_alt']};}}
            QHeaderView::section {{background:{C['panel_bg_alt']};color:{C['text_screen_dim']};
                                   border:none;border-bottom:1px solid {C['border']};padding:4px;}}
        """)

    def populate(self, world: World):
        self.clear()
        sp = {}
        for c in world.creatures:
            if c.species not in sp:
                sp[c.species] = {"emoji": c.emoji, "diet": c.diet,
                                 "count": 0, "traits": [], "gens": []}
            sp[c.species]["count"] += 1
            sp[c.species]["traits"].append(c.traits)
            sp[c.species]["gens"].append(c.generation)

        def tbar(v): return "█"*int((v/10)*6) + "░"*(6-int((v/10)*6))
        dsym = {"herbivore": "🌿", "carnivore": "🔴", "omnivore": "🟡"}
        dcol = {"herbivore": C["creature_herbivore"], "carnivore": C["creature_carnivore"],
                "omnivore":  C["creature_omnivore"]}

        for name, d in sorted(sp.items(), key=lambda x: -x[1]["count"]):
            trs = d["traits"]
            avg = lambda a: sum(getattr(t, a) for t in trs) / len(trs)
            g   = sum(d["gens"]) / len(d["gens"])
            it  = QTreeWidgetItem([f"{d['emoji']} {name}", str(d["count"]),
                                   f"{dsym.get(d['diet'], '?')} {d['diet']}",
                                   tbar(avg("size")), tbar(avg("speed")),
                                   tbar(avg("resilience")), tbar(avg("camouflage")),
                                   tbar(avg("aggression")), f"G{g:.1f}"])
            it.setForeground(0, QColor(C["text_screen"]))
            it.setForeground(1, QColor(dcol.get(d["diet"], C["text_screen"])))
            for col in range(2, 9): it.setForeground(col, QColor(C["text_screen_dim"]))
            self.addTopLevelItem(it)

        for name in sorted(world.recently_extinct):
            it = QTreeWidgetItem([f"💀 {name}", "0", "extinct",
                                  "—", "—", "—", "—", "—", "—"])
            for col in range(9): it.setForeground(col, QColor(C["text_screen_dim"]))
            self.addTopLevelItem(it)