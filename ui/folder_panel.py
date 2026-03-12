"""Left-pane folder browser bound to QFileSystemModel."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileSystemModel,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core.signals import AppSignals


class FolderPanel(QWidget):
    """Left-pane QTreeView that exposes the OS file system tree.

    Emits ``folder_selected(path)`` when the user clicks a directory.
    """

    folder_selected = Signal(str)  # local re-emission for convenience

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._signals = AppSignals.instance()

        # ── Model ──────────────────────────────────────────────────────────
        self._model = QFileSystemModel(self)
        self._model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self._model.setRootPath("")  # Show all drives / mount points

        # ── View ───────────────────────────────────────────────────────────
        self._tree = QTreeView(self)
        self._tree.setModel(self._model)
        self._tree.setRootIndex(self._model.index(""))
        self._tree.setHeaderHidden(True)
        # Hide size/type/modified columns
        for col in (1, 2, 3):
            self._tree.setColumnHidden(col, True)
        self._tree.setAnimated(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        self._tree.clicked.connect(self._on_clicked)
        self._tree.expanded.connect(self._on_expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)

    # ── Slots ──────────────────────────────────────────────────────────────────
    def _on_clicked(self, index: QModelIndex) -> None:
        path = self._model.filePath(index)
        if path:
            self.folder_selected.emit(path)
            self._signals.status_message.emit(path)

    def _on_expanded(self, index: QModelIndex) -> None:
        self._tree.resizeColumnToContents(0)

    def _context_menu(self, pos) -> None:  # type: ignore[override]
        index = self._tree.indexAt(pos)
        path = self._model.filePath(index) if index.isValid() else ""
        menu = QMenu(self)

        act_watch = QAction("📁  Add as Watch Folder", self)
        act_watch.triggered.connect(lambda: self._add_watch(path))
        menu.addAction(act_watch)

        if path:
            act_reveal = QAction("🔎  Reveal in Explorer", self)
            act_reveal.triggered.connect(lambda: self._reveal(path))
            menu.addAction(act_reveal)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ── Actions ────────────────────────────────────────────────────────────────
    def _add_watch(self, path: str) -> None:
        if not path:
            return
        from watcher.watch_manager import WatchManager
        # Access the globally shared WatchManager instance
        # (injected from MainWindow after construction)
        if hasattr(self, "_watch_manager") and self._watch_manager:
            self._watch_manager.add_folder(path)
            self._signals.status_message.emit(f"Watching: {path}")

    @staticmethod
    def _reveal(path: str) -> None:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(Path(path))])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def set_watch_manager(self, wm) -> None:  # type: ignore[type-arg]
        self._watch_manager = wm
