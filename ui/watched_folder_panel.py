"""Left-pane panel for managing and viewing watched folders."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.signals import AppSignals


class WatchedFolderPanel(QWidget):
    """Left-pane panel showing watched folders and their contents.

    Provides:
    - A dropdown to select from watched folders and OCR output folder
    - A file list view showing contents of the selected folder
    - Ability to add/remove watched folders

    Emits ``folder_selected(path)`` when a folder is selected.
    """

    folder_selected = Signal(str)  # local re-emission for convenience

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = Config.instance()
        self._signals = AppSignals.instance()
        self._watch_manager = None  # Set by MainWindow
        self._ocr_output_folder = self._cfg.get("output.ocr_output_dir", "./processed")

        # ── UI Components ────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header with folder selector
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 8, 8, 4)

        self._folder_combo = QComboBox(self)
        self._folder_combo.setMinimumWidth(200)
        self._folder_combo.currentIndexChanged.connect(self._on_folder_changed)
        header_layout.addWidget(QLabel("📁", self))
        header_layout.addWidget(self._folder_combo)

        # Add/Remove folder buttons
        self._btn_add = QToolButton(self)
        self._btn_add.setText("+")
        self._btn_add.setToolTip("Add watched folder")
        self._btn_add.clicked.connect(self._add_watch_folder_dialog)
        header_layout.addWidget(self._btn_add)

        self._btn_remove = QToolButton(self)
        self._btn_remove.setText("−")
        self._btn_remove.setToolTip("Remove selected watched folder")
        self._btn_remove.clicked.connect(self._remove_watch_folder)
        header_layout.addWidget(self._btn_remove)

        layout.addLayout(header_layout)

        # File list view
        self._file_list = QListWidget(self)
        self._file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_list.customContextMenuRequested.connect(self._context_menu)
        self._file_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._file_list)

        # Status label
        self._status_label = QLabel("Ready", self)
        self._status_label.setProperty("secondary", "true")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        layout.addWidget(self._status_label)

    # ── Public Methods ───────────────────────────────────────────────────────────
    def set_watch_manager(self, wm) -> None:  # type: ignore[type-arg]
        """Set the WatchManager instance."""
        self._watch_manager = wm

    def refresh_folder_list(self) -> None:
        """Refresh the dropdown list of folders."""
        self._folder_combo.blockSignals(True)
        self._folder_combo.clear()

        # Add OCR output folder first
        ocr_output = self._cfg.get("output.ocr_output_dir", "./processed")
        self._folder_combo.addItem("📄 OCR Output", ocr_output)

        # Add watched folders
        if self._watch_manager:
            for folder in self._watch_manager.watched_folders:
                self._folder_combo.addItem(f"📂 {Path(folder).name}", folder)

        # Add separator for adding new folders
        self._folder_combo.insertSeparator(self._folder_combo.count())
        self._folder_combo.addItem("+ Add New Folder...", "__add_new__")

        self._folder_combo.blockSignals(False)

        # Refresh current folder contents
        self._on_folder_changed()

    def refresh_file_list(self) -> None:
        """Refresh the file list for the currently selected folder."""
        current_data = self._folder_combo.currentData()
        if current_data and current_data != "__add_new__":
            self._load_folder_contents(current_data)

    # ── Slots ───────────────────────────────────────────────────────────────────
    def _on_folder_changed(self) -> None:
        """Handle folder selection change."""
        current_data = self._folder_combo.currentData()

        if current_data == "__add_new__":
            self._add_watch_folder_dialog()
            # Reset to previous selection
            self._folder_combo.setCurrentIndex(0)
            return

        if current_data:
            self._load_folder_contents(current_data)
            self.folder_selected.emit(current_data)
            self._signals.status_message.emit(current_data)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on a file item."""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if file_path:
            self._reveal(file_path)

    def _load_folder_contents(self, folder_path: str) -> None:
        """Load and display files in the specified folder."""
        self._file_list.clear()
        folder = Path(folder_path)

        if not folder.exists():
            # Create folder if it's the OCR output folder
            ocr_output = self._cfg.get("output.ocr_output_dir", "./processed")
            if str(folder.resolve()) == str(Path(ocr_output).resolve()):
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self._status_label.setText(f"Error creating folder: {e}")
                    return
            else:
                self._status_label.setText(f"Folder not found: {folder_path}")
                return

        try:
            files = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            file_count = 0
            dir_count = 0

            for path in files:
                if path.is_dir():
                    item = QListWidgetItem(f"📁 {path.name}")
                    item.setForeground(Qt.GlobalColor.gray)
                    self._file_list.addItem(item)
                    dir_count += 1
                else:
                    ext = path.suffix.lower()
                    icon = "📄"
                    if ext in {".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".png"}:
                        icon = "🖼️"
                    elif ext == ".pdf":
                        icon = "📕"
                    elif ext in {".txt", ".md"}:
                        icon = "📝"

                    item = QListWidgetItem(f"{icon} {path.name}")
                    item.setData(Qt.ItemDataRole.UserRole, str(path))
                    self._file_list.addItem(item)
                    file_count += 1

            self._status_label.setText(f"{file_count} files, {dir_count} folders")

        except Exception as e:
            self._status_label.setText(f"Error loading folder: {e}")

    def _context_menu(self, pos) -> None:  # type: ignore[override]
        """Show context menu for file list items."""
        item = self._file_list.itemAt(pos)
        if not item:
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            return

        menu = QMenu(self)

        act_reveal = QAction("🔎 Reveal in Explorer", self)
        act_reveal.triggered.connect(lambda: self._reveal(file_path))
        menu.addAction(act_reveal)

        act_ocr = QAction("🔍 Run OCR", self)
        act_ocr.triggered.connect(lambda: self._run_ocr(file_path))
        menu.addAction(act_ocr)

        menu.exec(self._file_list.viewport().mapToGlobal(pos))

    # ── Actions ────────────────────────────────────────────────────────────────
    def _add_watch_folder_dialog(self) -> None:
        """Show dialog to add a new watch folder."""
        current_dir = self._cfg.get("output.default_output_dir", ".")
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder to Watch", current_dir
        )
        if folder:
            if self._watch_manager:
                self._watch_manager.add_folder(folder)
                self._save_watch_folders_to_config()
                self.refresh_folder_list()
                self._signals.status_message.emit(f"Now watching: {folder}")

    def _remove_watch_folder(self) -> None:
        """Remove the currently selected watch folder."""
        current_data = self._folder_combo.currentData()
        if current_data and current_data != "__add_new__":
            # Don't allow removing OCR output folder
            ocr_output = self._cfg.get("output.ocr_output_dir", "./processed")
            if Path(current_data).resolve() == Path(ocr_output).resolve():
                self._signals.status_message.emit("Cannot remove OCR output folder")
                return

            if self._watch_manager:
                self._watch_manager.remove_folder(current_data)
                self._save_watch_folders_to_config()
                self.refresh_folder_list()
                self._signals.status_message.emit(f"Stopped watching: {current_data}")

    def _save_watch_folders_to_config(self) -> None:
        """Save current watched folders to config and persist to disk."""
        if not self._watch_manager:
            return

        watched = self._watch_manager.watched_folders
        watch_list = []

        for folder in watched:
            # Preserve existing config entries if they exist
            existing_entry = None
            current_watch_list = self._cfg.get("watch_folders", [])
            for entry in current_watch_list:
                if isinstance(entry, dict) and entry.get("path") == folder:
                    existing_entry = entry
                    break

            if existing_entry:
                watch_list.append(existing_entry)
            else:
                watch_list.append({
                    "path": folder,
                    "recursive": False,
                    "auto_create": True
                })

        self._cfg.set("watch_folders", watch_list)
        self._cfg.save()

    @staticmethod
    def _reveal(path: str) -> None:
        """Reveal the file/folder in the system file explorer."""
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(Path(path))], shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", str(Path(path).parent)])

    def _run_ocr(self, path: str) -> None:
        """Trigger OCR on the selected file."""
        self._signals.file_ready.emit(path)
        self._signals.status_message.emit(f"Queued for OCR: {Path(path).name}")
