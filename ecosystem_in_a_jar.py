#!/usr/bin/env python3
"""
🫙 ECOSYSTEM IN A JAR  — PyQt6 edition
Living simulation · evolving creatures · disasters · AI lore

Requirements:
    pip install PyQt6 requests mlx-lm

The local AI narrator runs in-process via mlx-lm; the model downloads
automatically on first run.

Edit settings.json to change colours, fonts, model, and timing.
State is saved to ./jar_data/ automatically.
"""

import sys

from PyQt6.QtWidgets import QApplication, QToolTip

from ui_utils import mkfont
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Ecosystem in a Jar")
    QToolTip.setFont(mkfont("ui"))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())