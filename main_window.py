"""MainWindow — ties together all UI panels and drives the simulation loop."""

import json, datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSlider, QTextEdit, QProgressBar, QFrame,
    QSplitter, QDialog, QDialogButtonBox, QLineEdit, QRadioButton,
    QButtonGroup, QDoubleSpinBox, QGroupBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QFont, QColor, QPixmap, QTextCursor

from settings import C, F, OL, COMFY
from ui_utils import mkfont, btn_css
from simulation import World, Traits, DATA_DIR, CANVAS_W
from narration import NarrationWorker, append_lore
from image_gen import ImageGenWorker
from canvas import JarCanvas
from species_tree import SpeciesTree

SPECIES_EMOJIS = [
    "🐇","🐢","🦊","🦎","🐍","🦋","🐝","🐛","🦗","🐞","🐜","🦂",
    "🦀","🦞","🦐","🦑","🐙","🦈","🐬","🐟","🐠","🐡","🦭","🦦",
    "🐦","🦅","🦆","🦉","🦇","🐿","🦔","🦡","🦥","🦨","🦘","🐘",
    "🦏","🦛","🐆","🐅","🐻","🐼","🐨","🦁","🐯","🐺","🐸","🐊",
    "🦕","🦖","🐉","🐲","👾","👽","🤖","🧬","🦠","🌟","💀","⚡",
    "🔥","❄️","🌊","🌪","🍄","🌵","🌿","🌸","🦋","🪲","🪳","🪸",
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🫙 Ecosystem in a Jar"); self.setMinimumSize(1100, 720)
        world  = World.load(); is_new = (world is None)
        if is_new: world = World(); world.spawn_starters(); world.save()
        self.world = world
        self._narration     = "Press ▶ Advance to begin."
        self._narrator      = None; self._narrator_busy = False
        self._img_worker    = None
        self._auto_timer    = QTimer(); self._auto_timer.timeout.connect(self._advance)
        self._anim_timer    = QTimer(); self._anim_timer.timeout.connect(lambda: self.canvas.update())
        self._anim_timer.start(80)
        self._build_ui(); self._apply_style(); self._refresh_all()
        self._log("🫙 New jar." if is_new
                  else f"🫙 Resumed — Year {world.year}, {world.season}, Tick {world.tick}")

    # ── Styling ───────────────────────────────────────────────

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

    def _panel(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.Shape.StyledPanel)
        f.setStyleSheet(f"QFrame{{background:{C['panel_bg']};border:1px solid {C['border']};border-radius:6px;}}")
        return f

    def _btn(self, text: str, cb, bg_key: str, tip: str = "", fg_key: str = "text_button") -> QPushButton:
        b = QPushButton(text); b.setFont(mkfont("ui"))
        b.setStyleSheet(btn_css(C[bg_key], fg_key))
        b.setCursor(Qt.CursorShape.PointingHandCursor); b.clicked.connect(cb)
        if tip: b.setToolTip(tip)
        return b

    def _lbl(self, text: str, col_key: str = "text_screen", bold: bool = False) -> QLabel:
        l = QLabel(text); l.setFont(mkfont("ui", bold=bold))
        l.setStyleSheet(f"color:{C[col_key]};background:transparent;"); return l

    # ── UI construction ───────────────────────────────────────

    def _build_ui(self):
        root_w = QWidget(); self.setCentralWidget(root_w)
        root   = QVBoxLayout(root_w); root.setSpacing(6); root.setContentsMargins(8, 8, 8, 8)

        top = QHBoxLayout()
        t   = QLabel("🫙  ECOSYSTEM IN A JAR"); t.setFont(mkfont("title", bold=True))
        t.setStyleSheet(f"color:{C['accent_green']};background:transparent;"); top.addWidget(t)
        self._lbl_info = self._lbl("", col_key="text_screen_dim"); top.addWidget(self._lbl_info)
        top.addStretch(); root.addLayout(top)

        spl = QSplitter(Qt.Orientation.Horizontal)
        spl.setChildrenCollapsible(False)
        spl.setStyleSheet("QSplitter::handle{background:transparent;width:6px;}")
        root.addWidget(spl, stretch=1)

        # Left: species tree + canvas + plant bar
        lp = self._panel(); lv = QVBoxLayout(lp); lv.setSpacing(4); lv.setContentsMargins(8, 8, 8, 8)
        self.tree = SpeciesTree()
        self.tree.setFixedHeight(145)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lv.addWidget(self.tree)
        self.canvas = JarCanvas(self.world); lv.addWidget(self.canvas)
        pr = QHBoxLayout()
        pr.addWidget(self._lbl("🌿 Plants", col_key="text_screen_dim"))
        self._plant_bar = QProgressBar(); self._plant_bar.setRange(0, 100)
        self._plant_bar.setTextVisible(False); self._plant_bar.setFixedHeight(10)
        self._plant_bar.setStyleSheet(
            f"QProgressBar{{background:{C['progressbar_bg']};border-radius:5px;border:none;}}"
            f"QProgressBar::chunk{{background:{C['progressbar_fill']};border-radius:5px;}}")
        pr.addWidget(self._plant_bar, stretch=1)
        self._plant_lbl = self._lbl("75", "accent_green"); self._plant_lbl.setFixedWidth(30)
        pr.addWidget(self._plant_lbl); lv.addLayout(pr); spl.addWidget(lp)

        # Middle: generated image + event log
        mw = QWidget(); mw.setStyleSheet("background:transparent;")
        mv = QVBoxLayout(mw); mv.setSpacing(6); mv.setContentsMargins(0, 0, 0, 0)
        ip = self._panel(); iv = QVBoxLayout(ip); iv.setSpacing(3); iv.setContentsMargins(6, 6, 6, 6)
        self._img_lbl = QLabel(); self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet(
            f"background:{C['canvas_bg']};border-radius:4px;color:{C['text_screen_dim']};")
        self._img_lbl.setText("🖼️  Waiting for first image…")
        self._img_lbl.setFont(mkfont("ui")); self._img_lbl.setWordWrap(True)
        self._img_status = self._lbl("", "text_screen_dim")
        self._img_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        iv.addWidget(self._img_lbl, stretch=1); iv.addWidget(self._img_status)
        mv.addWidget(ip, stretch=1)
        lgp = self._panel(); lgp.setFixedHeight(165)
        lgv = QVBoxLayout(lgp); lgv.setSpacing(3); lgv.setContentsMargins(6, 6, 6, 6)
        lgv.addWidget(self._lbl("Event log", col_key="text_screen_dim"))
        self._log_text = QTextEdit(); self._log_text.setReadOnly(True)
        self._log_text.setFont(mkfont("mono"))
        self._log_text.setStyleSheet(
            f"QTextEdit{{background:{C['panel_bg']};color:{C['text_screen_dim']};border:none;padding:2px;}}")
        lgv.addWidget(self._log_text); mv.addWidget(lgp); spl.addWidget(mw)

        # Right: narration + controls
        rw = QWidget(); rw.setStyleSheet("background:transparent;")
        rv = QVBoxLayout(rw); rv.setSpacing(6); rv.setContentsMargins(0, 0, 0, 0)
        np = self._panel(); nv = QVBoxLayout(np); nv.setSpacing(4); nv.setContentsMargins(10, 10, 10, 10)
        nt = QLabel("📽️  Nature Doc"); nt.setFont(mkfont("title", bold=True))
        nt.setStyleSheet(f"color:{C['accent_yellow']};background:transparent;")
        nt.setAlignment(Qt.AlignmentFlag.AlignCenter); nv.addWidget(nt)
        self._nar_text = QTextEdit(); self._nar_text.setReadOnly(True)
        nar_font = QFont(F["family_lore"], F["size_lore"]+4); nar_font.setItalic(True)
        self._nar_text.setFont(nar_font)
        self._nar_text.setStyleSheet(
            f"QTextEdit{{background:{C['panel_bg']};color:{C['text_lore']};border:none;padding:6px;}}")
        nv.addWidget(self._nar_text, stretch=1)
        self._nar_spin = QLabel(""); self._nar_spin.setFont(mkfont("ui"))
        self._nar_spin.setStyleSheet(f"color:{C['accent_yellow']};background:transparent;")
        self._nar_spin.setAlignment(Qt.AlignmentFlag.AlignCenter); nv.addWidget(self._nar_spin)
        rv.addWidget(np, stretch=1)

        cp = self._panel(); cv = QVBoxLayout(cp); cv.setSpacing(5); cv.setContentsMargins(8, 8, 8, 8)

        ar = QHBoxLayout(); ar.setSpacing(4)
        self._btn_adv = self._btn("▶  Advance  (+10)", self._advance, "btn_advance",
                                  tip="Run 10 simulation ticks and request narration from Ollama.")
        ar.addWidget(self._btn_adv, stretch=1)
        self._btn_auto = self._btn("⏸", self._toggle_auto, "btn_auto", fg_key="text_button",
                                   tip=f"Toggle auto-advance (runs every {OL['auto_advance_sec']}s).")
        self._btn_auto.setFixedWidth(38); ar.addWidget(self._btn_auto); cv.addLayout(ar)

        ff = QHBoxLayout(); ff.setSpacing(6)
        ff.addWidget(self._lbl("⏭ Skip:", "text_screen_dim"))
        self._fast_sl = QSlider(Qt.Orientation.Horizontal)
        self._fast_sl.setRange(10, 500); self._fast_sl.setValue(50)
        self._fast_sl.setToolTip("Number of ticks to skip (no narration).")
        self._fast_sl.setStyleSheet(f"""
            QSlider::groove:horizontal{{background:{C['panel_bg_alt']};height:6px;border-radius:3px;}}
            QSlider::handle:horizontal{{background:{C['accent_blue']};width:14px;height:14px;
                border-radius:7px;margin:-4px 0;}}
            QSlider::sub-page:horizontal{{background:{C['accent_blue']};border-radius:3px;}}
        """)
        self._fast_val = self._lbl("50t", "text_screen_dim"); self._fast_val.setFixedWidth(34)
        self._fast_sl.valueChanged.connect(lambda v: self._fast_val.setText(f"{v}t"))
        ff.addWidget(self._fast_sl, stretch=1); ff.addWidget(self._fast_val)
        ff.addWidget(self._btn("⏭", self._fast_forward, "btn_default",
                               tip="Jump forward the selected number of ticks instantly."))
        cv.addLayout(ff)

        cv.addWidget(self._lbl("DISASTERS", "text_screen_dim"))
        DISASTERS = [
            ("☄️  Meteor",  "meteor",  "btn_meteor",  "60% of all creatures die instantly. Plants scorched to 10%.", "text_button_danger"),
            ("🏜️  Drought", "drought", "btn_drought", "Vegetation crashes to 3. Herbivores begin starving immediately.", "text_button_danger"),
            ("🦠 Plague",   "plague",  "btn_plague",  "75% of one randomly chosen species is wiped out.", "text_button_danger"),
            ("🌸 Bloom",    "bloom",   "btn_bloom",   "Plants max to 100. All creatures are immediately fed.", "text_button"),
            ("🧊 Cold",     "cold",    "btn_cold",    "Creatures with resilience < 5 face a 45% chance of death.", "text_button_danger"),
            ("🌊 Flood",    "flood",   "btn_flood",   "Small creatures (size < 4) have a 50% death chance. Plants gain +35.", "text_button_danger"),
        ]
        dg = QGridLayout(); dg.setSpacing(4)
        for i, (label, kind, bg, tip, fg_k) in enumerate(DISASTERS):
            dg.addWidget(self._btn(label, lambda checked=False, k=kind: self._disaster(k),
                                   bg, tip=tip, fg_key=fg_k), i//2, i%2)
        cv.addLayout(dg)

        br = QHBoxLayout(); br.setSpacing(4)
        br.addWidget(self._btn("✨ Add Species", self._add_species_dialog, "btn_add",
                               tip="Open a dialog to introduce a fully custom species."))
        br.addWidget(self._btn("📖 Lore", self._open_lore, "btn_lore",
                               tip="Browse the complete AI-narrated history of the jar."))
        cv.addLayout(br); rv.addWidget(cp); spl.addWidget(rw)
        spl.setSizes([CANVAS_W+30, 420, 360])

    # ── Refresh ───────────────────────────────────────────────

    def _refresh_all(self):
        w = self.world; total = sum(w.population_by_species().values())
        self._lbl_info.setText(
            f"Year {w.year}  ·  {w.season}  ·  Tick {w.tick}"
            f"  ·  {total} creatures  ·  {len(w.extinct_species)} extinct")
        self._plant_bar.setValue(int(w.plant_abundance))
        self._plant_lbl.setText(f"{w.plant_abundance:.0f}")
        self.tree.populate(w); self._set_narration(self._narration)

    def _set_narration(self, text: str):
        self._nar_text.setPlainText(text); self._narration = text

    def _log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log_text.append(f"[{ts}] {msg}")
        self._log_text.moveCursor(QTextCursor.MoveOperation.End)

    # ── Actions ───────────────────────────────────────────────

    def _run_ticks(self, n: int) -> list:
        all_e = []
        for _ in range(n):
            all_e.extend(self.world.tick_world())
            if not self.world.creatures: break
        return all_e

    def _advance(self):
        if self._narrator_busy: return
        self.world.recently_extinct.clear()
        events = self._run_ticks(10); self.world.save()
        self._refresh_all()
        for e in events[:5]: self._log(e)
        self._start_narration(events)
        self._start_image_gen("advance")

    def _start_narration(self, events: list):
        self._narrator_busy = True; self._nar_spin.setText("✦ narrating…")
        self._narrator = NarrationWorker(self.world, events)
        self._narrator.done.connect(self._on_narration_done)
        self._narrator.start()

    def _on_narration_done(self, text: str):
        self._narrator_busy = False; self._nar_spin.setText("")
        append_lore(self.world, text, []); self._set_narration(text)

    def _toggle_auto(self):
        if self._auto_timer.isActive():
            self._auto_timer.stop(); self._btn_auto.setText("⏸")
            self._btn_auto.setStyleSheet(btn_css(C["btn_auto"])); self._log("Auto paused.")
        else:
            self._auto_timer.start(OL["auto_advance_sec"] * 1000)
            self._btn_auto.setText("⏹")
            self._btn_auto.setStyleSheet(btn_css(C["accent_red"])); self._log("Auto started.")

    def _fast_forward(self):
        n = self._fast_sl.value(); self._log(f"⏭ Fast-forwarding {n} ticks…")
        events = self._run_ticks(n); self.world.save(); self._refresh_all()
        for e in events[-4:]: self._log(e)
        self._log(f"Done. Tick {self.world.tick}")
        self._set_narration(f"({n} ticks pass in the blink of an eye.)")

    def _disaster(self, kind: str):
        msg = self.world.apply_disaster(kind); self._log(msg)
        events = self._run_ticks(10); self.world.save(); self._refresh_all()
        self._start_narration([msg] + events)
        self._start_image_gen(f"disaster: {kind}")

    # ── Image generation ──────────────────────────────────────

    def _start_image_gen(self, trigger: str):
        if not COMFY.get("enabled", True): return
        if self._img_worker and self._img_worker.isRunning(): return
        self._img_status.setText("🎨 generating…")
        self._img_worker = ImageGenWorker(self.world, trigger)
        self._img_worker.done.connect(self._on_image_done)
        self._img_worker.failed.connect(self._on_image_failed)
        self._img_worker.start()

    def _on_image_done(self, data: bytes):
        px = QPixmap(); px.loadFromData(data)
        if not px.isNull():
            w = max(self._img_lbl.width()  - 4, 1)
            h = max(self._img_lbl.height() - 4, 1)
            scaled = px.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._img_lbl.setPixmap(scaled)
        self._img_status.setText("")

    def _on_image_failed(self, msg: str):
        self._img_status.setText(f"⚠ {msg[:50]}")
        self._log(f"[ComfyUI] {msg}")

    # ── Add species dialog ────────────────────────────────────

    def _add_species_dialog(self):
        dlg = QDialog(self); dlg.setWindowTitle("Add Species"); dlg.setMinimumWidth(340)
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
        lay = QVBoxLayout(dlg); lay.setSpacing(10)

        def row(lbl, w):
            h = QHBoxLayout(); l = QLabel(lbl); l.setFont(mkfont("ui")); l.setFixedWidth(80)
            h.addWidget(l); h.addWidget(w); return h

        name_e = QLineEdit("Kreel"); name_e.setFont(mkfont("ui"))
        lay.addLayout(row("Name:", name_e))

        selected_emoji = ["🦎"]
        emoji_btn = QPushButton(selected_emoji[0])
        emoji_btn.setFont(QFont(F["family_ui"], 20))
        emoji_btn.setFixedSize(52, 52)
        emoji_btn.setStyleSheet(f"""
            QPushButton {{background:{C['panel_bg_alt']};border:1px solid {C['border']};border-radius:6px;}}
            QPushButton:hover {{background:{C['border']};}}
        """)
        emoji_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def open_picker():
            picker = QDialog(dlg); picker.setWindowTitle("Choose Icon")
            picker.setStyleSheet(f"QDialog{{background:{C['window_bg']};}}")
            grid = QGridLayout(picker); grid.setSpacing(4); grid.setContentsMargins(8, 8, 8, 8)
            cols = 12
            for idx, em in enumerate(SPECIES_EMOJIS):
                btn = QPushButton(em); btn.setFont(QFont(F["family_ui"], 18))
                btn.setFixedSize(42, 42)
                btn.setStyleSheet(f"""
                    QPushButton {{background:{C['panel_bg_alt']};border:1px solid {C['border']};border-radius:5px;}}
                    QPushButton:hover {{background:{C['accent_blue']};}}
                """)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                def pick(checked=False, e=em):
                    selected_emoji[0] = e; emoji_btn.setText(e); picker.accept()
                btn.clicked.connect(pick)
                grid.addWidget(btn, idx // cols, idx % cols)
            picker.exec()

        emoji_btn.clicked.connect(open_picker)
        emoji_row = QHBoxLayout()
        emoji_lbl = QLabel("Icon:"); emoji_lbl.setFont(mkfont("ui")); emoji_lbl.setFixedWidth(80)
        emoji_row.addWidget(emoji_lbl); emoji_row.addWidget(emoji_btn); emoji_row.addStretch()
        lay.addLayout(emoji_row)

        diet_gb = QGroupBox("Diet"); dgl = QHBoxLayout(diet_gb); diet_bg = QButtonGroup()
        for d in ("herbivore", "carnivore", "omnivore"):
            rb = QRadioButton(d); rb.setFont(mkfont("ui"))
            if d == "herbivore": rb.setChecked(True)
            diet_bg.addButton(rb); dgl.addWidget(rb)
        lay.addWidget(diet_gb)

        trait_gb = QGroupBox("Traits  (1 = min · 10 = max)")
        tgl = QGridLayout(trait_gb); tgl.setSpacing(6); trait_spins = {}
        for i, t in enumerate(["size", "speed", "resilience", "camouflage", "aggression"]):
            l = QLabel(t.capitalize()); l.setFont(mkfont("ui"))
            sp = QDoubleSpinBox(); sp.setRange(1, 10); sp.setValue(5.0)
            sp.setSingleStep(0.5); sp.setFont(mkfont("ui")); trait_spins[t] = sp
            tgl.addWidget(l, i, 0); tgl.addWidget(sp, i, 1)
        lay.addWidget(trait_gb)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.setFont(mkfont("ui")); bb.setStyleSheet(btn_css(C["btn_advance"]))
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            name  = name_e.text().strip().capitalize() or "Unknown"
            emoji = selected_emoji[0]
            diet  = next((b.text() for b in diet_bg.buttons() if b.isChecked()), "herbivore")
            tr    = Traits(**{k: v.value() for k, v in trait_spins.items()})
            msg   = self.world.add_species(name, emoji, diet, tr)
            self.world.save(); self._log(msg); self._refresh_all()

    # ── Lore viewer ───────────────────────────────────────────

    def _open_lore(self):
        lp = DATA_DIR / "lore.jsonl"
        if not lp.exists():
            QMessageBox.information(self, "Lore", "No lore yet — press Advance to start."); return
        dlg = QDialog(self); dlg.setWindowTitle("📖 The Lore of the Jar"); dlg.resize(640, 640)
        dlg.setStyleSheet(f"QDialog{{background:{C['window_bg']};}}")
        lv  = QVBoxLayout(dlg)
        txt = QTextEdit(); txt.setReadOnly(True); txt.setFont(mkfont("lore", italic=True))
        txt.setStyleSheet(
            f"QTextEdit{{background:{C['panel_bg']};color:{C['text_lore']};border:none;padding:8px;}}")
        lv.addWidget(txt)
        with open(lp) as f:
            for line in f:
                e = json.loads(line)
                txt.append(f"\n{'─'*52}")
                txt.append(f"Year {e['year']} · {e['season']} · Tick {e['tick']}\n")
                txt.append(e["narration"])
                for ev in (e.get("events") or [])[:4]: txt.append(f"  • {ev}")
        txt.moveCursor(QTextCursor.MoveOperation.End); dlg.exec()

    def closeEvent(self, event):
        self._auto_timer.stop(); self._anim_timer.stop(); self.world.save(); event.accept()