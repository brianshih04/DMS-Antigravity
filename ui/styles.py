"""Windows 11 Fluent Design QSS stylesheets for PySide6.

Reads the current Windows system theme preference (dark/light) via the
registry when ``theme="auto"`` is configured.  Falls back to dark theme
on non-Windows platforms.

Skill reference: .agent/skills/ui_fluent_design.json
"""
from __future__ import annotations

import platform
import sys

DARK_THEME = """
/* ── Global ───────────────────────────────────────────────────────────────── */
QMainWindow, QWidget {
    background-color: #202020;
    color: #FFFFFF;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 14px;
}

/* ── Menu Bar ─────────────────────────────────────────────────────────────── */
QMenuBar {
    background-color: #202020;
    color: #FFFFFF;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    padding: 2px 4px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
QMenuBar::item:selected { background-color: rgba(255,255,255,0.09); }

/* ── Menus ────────────────────────────────────────────────────────────────── */
QMenu {
    background-color: #2C2C2C;
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 4px;
}
QMenu::item { padding: 6px 16px; border-radius: 4px; }
QMenu::item:selected { background-color: rgba(255,255,255,0.09); }
QMenu::separator { height: 1px; background: rgba(255,255,255,0.1); margin: 4px 8px; }

/* ── Toolbar ──────────────────────────────────────────────────────────────── */
QToolBar {
    background-color: #2C2C2C;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    padding: 4px 8px;
    spacing: 4px;
}
QToolButton {
    background-color: transparent;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
}
QToolButton:hover { background-color: rgba(255,255,255,0.09); }
QToolButton:pressed { background-color: rgba(255,255,255,0.05); }
QToolButton:checked { background-color: rgba(0,120,212,0.25); }

/* ── Splitter ─────────────────────────────────────────────────────────────── */
QSplitter::handle { background-color: rgba(255,255,255,0.07); }
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical { height: 2px; }
QSplitter::handle:hover { background-color: #0078D4; }

/* ── Tree View (Folder Panel) ─────────────────────────────────────────────── */
QTreeView {
    background-color: #1A1A1A;
    border: none;
    outline: none;
    show-decoration-selected: 1;
    alternate-background-color: #222222;
}
QTreeView::item { padding: 4px 8px; border-radius: 4px; min-height: 22px; }
QTreeView::item:hover { background-color: rgba(255,255,255,0.05); }
QTreeView::item:selected { background-color: rgba(0,120,212,0.25); color: #FFFFFF; }
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {
    image: url(:/icons/chevron-right.svg);
}
QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {
    image: url(:/icons/chevron-down.svg);
}

/* ── List View (Thumbnail Panel) ──────────────────────────────────────────── */
QListView {
    background-color: #202020;
    border: none;
    outline: none;
}
QListView::item {
    border-radius: 8px;
    margin: 4px;
    padding: 4px;
}
QListView::item:hover { background-color: rgba(255,255,255,0.06); }
QListView::item:selected { background-color: rgba(0,120,212,0.30); }

/* ── Scrollbars ───────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: rgba(255,255,255,0.30);
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background-color: rgba(255,255,255,0.55); }
QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
QScrollBar:horizontal {
    background-color: transparent;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background-color: rgba(255,255,255,0.30);
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background-color: rgba(255,255,255,0.55); }

/* ── Push Buttons ─────────────────────────────────────────────────────────── */
QPushButton {
    background-color: #0078D4;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 14px;
    min-width: 80px;
}
QPushButton:hover { background-color: #1A90E8; }
QPushButton:pressed { background-color: #005FA3; }
QPushButton:disabled { background-color: rgba(255,255,255,0.08); color: rgba(255,255,255,0.33); }
QPushButton[secondary="true"] { background-color: rgba(255,255,255,0.09); color: #FFFFFF; }
QPushButton[secondary="true"]:hover { background-color: rgba(255,255,255,0.14); }

/* ── Status Bar ───────────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #1A1A1A;
    color: rgba(255,255,255,0.67);
    border-top: 1px solid rgba(255,255,255,0.07);
    font-size: 12px;
}

/* ── Progress Bar ─────────────────────────────────────────────────────────── */
QProgressBar {
    background-color: rgba(255,255,255,0.09);
    border-radius: 2px;
    height: 4px;
    text-align: center;
    border: none;
}
QProgressBar::chunk { background-color: #0078D4; border-radius: 2px; }

/* ── Labels ───────────────────────────────────────────────────────────────── */
QLabel { color: #FFFFFF; background-color: transparent; }
QLabel[secondary="true"] { color: rgba(255,255,255,0.67); font-size: 12px; }

/* ── Line Edit ────────────────────────────────────────────────────────────── */
QLineEdit {
    background-color: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    border-bottom-color: rgba(255,255,255,0.50);
    border-radius: 4px;
    color: #FFFFFF;
    padding: 4px 8px;
}
QLineEdit:focus { border-bottom-color: #0078D4; }

/* ── Group Box ────────────────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    color: rgba(255,255,255,0.67);
    font-size: 12px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; }
"""

LIGHT_THEME = """
QMainWindow, QWidget {
    background-color: #F3F3F3;
    color: #000000;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 14px;
}
QToolBar { background-color: #FFFFFF; border-bottom: 1px solid rgba(0,0,0,0.07); padding: 4px 8px; }
QTreeView { background-color: #FAFAFA; border: none; }
QTreeView::item:hover { background-color: rgba(0,0,0,0.05); }
QTreeView::item:selected { background-color: rgba(0,120,212,0.15); }
QListView { background-color: #F3F3F3; border: none; }
QListView::item:hover { background-color: rgba(0,0,0,0.05); }
QListView::item:selected { background-color: rgba(0,120,212,0.15); }
QStatusBar { background-color: #EFEFEF; color: rgba(0,0,0,0.67); border-top: 1px solid rgba(0,0,0,0.07); }
QPushButton { background-color: #0078D4; color: white; border: none; border-radius: 6px; padding: 6px 16px; }
QPushButton:hover { background-color: #1A90E8; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: rgba(0,0,0,0.25); border-radius: 4px; min-height: 24px; }
QMenu { background-color: #FFFFFF; border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; padding: 4px; }
QMenu::item:selected { background-color: rgba(0,0,0,0.06); }
"""


def _windows_using_dark_mode() -> bool:
    """Read Windows registry to detect dark/light app theme preference."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0  # 0 = dark, 1 = light
    except Exception:
        return True  # default to dark


def get_stylesheet(theme: str = "auto") -> str:
    """Return the appropriate QSS string for the given theme setting."""
    if theme == "dark":
        return DARK_THEME
    if theme == "light":
        return LIGHT_THEME
    # "auto"
    if platform.system() == "Windows":
        return DARK_THEME if _windows_using_dark_mode() else LIGHT_THEME
    return DARK_THEME
