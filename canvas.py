"""JarCanvas — the animated simulation viewport."""

import math, random, time

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QRadialGradient

from settings import C
from simulation import World, CANVAS_W, CANVAS_H


class JarCanvas(QWidget):
    def __init__(self, world: World, parent=None):
        super().__init__(parent); self.world = world
        self.setFixedSize(CANVAS_W, CANVAS_H)
        random.seed(42)
        self._plant_pos   = [(random.randint(5, CANVAS_W-5),
                              random.randint(5, CANVAS_H-5)) for _ in range(130)]
        self._plant_size  = [random.uniform(1.8, 4.8) for _ in range(130)]
        self._plant_phase = [random.uniform(0, 2*math.pi) for _ in range(130)]
        random.seed()
        self._t0         = time.time()
        self._emoji_font = QFont("Apple Color Emoji", 11)

    def paintEvent(self, _):
        t  = time.time() - self._t0
        pa = QPainter(self)
        pa.setRenderHint(QPainter.RenderHint.Antialiasing)
        pa.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Background: radial glow
        grad = QRadialGradient(QPointF(CANVAS_W * 0.5, CANVAS_H * 0.45),
                               max(CANVAS_W, CANVAS_H) * 0.70)
        grad.setColorAt(0.0, QColor("#0d2040"))
        grad.setColorAt(1.0, QColor(C["canvas_bg"]))
        pa.fillRect(0, 0, CANVAS_W, CANVAS_H, QBrush(grad))

        # Plants: breathing animation
        density  = self.world.plant_abundance / 100.0
        n_plants = int(density * 130)
        pa.setPen(Qt.PenStyle.NoPen)
        for i in range(n_plants):
            px, py = self._plant_pos[i]
            pulse  = 1.0 + 0.18 * math.sin(t * 1.3 + self._plant_phase[i])
            r      = self._plant_size[i] * pulse
            shade  = 45 + (i % 11) * 6
            pa.setBrush(QBrush(QColor(0, shade + 50, 12, 190)))
            pa.drawEllipse(QPointF(px, py), r, r)

        # Creatures
        for c in self.world.creatures:
            is_healthy = c.health >= 50
            diet_col   = QColor(C.get(f"creature_{c.diet}", "#ffffff")
                                if is_healthy else C["creature_unhealthy"])
            r          = 4.0 + c.traits.size * 0.65

            if is_healthy:
                halo = QColor(diet_col); halo.setAlpha(30)
                pa.setBrush(QBrush(halo)); pa.setPen(Qt.PenStyle.NoPen)
                pa.drawEllipse(QPointF(c.x, c.y), r * 2.6, r * 2.6)

            spd = math.hypot(c.dx, c.dy)
            if spd > 0.3:
                tail_col = QColor(diet_col); tail_col.setAlpha(70)
                pen = QPen(tail_col, 1.8)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pa.setPen(pen)
                tail = 3.5 + spd * 2.8
                pa.drawLine(QPointF(c.x - c.dx/spd*tail, c.y - c.dy/spd*tail),
                             QPointF(c.x, c.y))

            pa.setBrush(QBrush(diet_col))
            pa.setPen(QPen(QColor(0, 0, 0, 90), 0.8))
            pa.drawEllipse(QPointF(c.x, c.y), r, r)

            pa.setFont(self._emoji_font)
            pa.setPen(QPen(QColor(255, 255, 255, 230)))
            fm = pa.fontMetrics()
            ew = fm.horizontalAdvance(c.emoji)
            pa.drawText(QPointF(c.x - ew*0.5, c.y + fm.ascent()*0.38), c.emoji)

        # Jar border: glass ring
        pa.setPen(QPen(QColor(180, 215, 255, 50), 2.5))
        pa.setBrush(Qt.BrushStyle.NoBrush)
        pa.drawRoundedRect(2, 2, CANVAS_W-4, CANVAS_H-4, 10, 10)
        pa.setPen(QPen(QColor(220, 240, 255, 20), 1.0))
        pa.drawRoundedRect(5, 5, CANVAS_W-10, CANVAS_H-10, 8, 8)

        pa.end()