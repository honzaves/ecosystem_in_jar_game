"""Qt font and button-stylesheet helpers that depend on loaded settings."""

from PyQt6.QtGui import QFont, QColor

from settings import C, F


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