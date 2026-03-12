"""QMainWindow — application shell with Fluent Design dual-pane layout."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from core.config import Config
from core.signals import AppSignals
from ui.folder_panel import FolderPanel
from ui.thumbnail_panel import ThumbnailPanel
from watcher.processing_queue import ProcessingQueue
from watcher.watch_manager import WatchManager

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Application main window — dual-pane splitter layout."""

    def __init__(self) -> None:
        super().__init__()
        self._cfg = Config.instance()
        self._signals = AppSignals.instance()

        # ── Window geometry ────────────────────────────────────────────────
        self.setWindowTitle(self._cfg.get("ui.window_title", "DMS"))
        w = int(self._cfg.get("ui.window_width", 1280))
        h = int(self._cfg.get("ui.window_height", 800))
        self.resize(w, h)

        # ── Central widget: splitter ───────────────────────────────────────
        self._folder_panel = FolderPanel(self)
        self._thumb_panel = ThumbnailPanel(self)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.addWidget(self._folder_panel)
        self._splitter.addWidget(self._thumb_panel)
        self._splitter.setSizes([280, 900])
        self._splitter.setChildrenCollapsible(False)
        self.setCentralWidget(self._splitter)

        # ── Toolbar ────────────────────────────────────────────────────────
        self._build_toolbar()

        # ── Status bar ─────────────────────────────────────────────────────
        self._build_status_bar()

        # ── Watch-folder pipeline ──────────────────────────────────────────
        self._watch_manager = WatchManager()
        self._proc_queue = ProcessingQueue()
        self._folder_panel.set_watch_manager(self._watch_manager)
        self._start_watchers()

        # ── Signal connections ─────────────────────────────────────────────
        self._folder_panel.folder_selected.connect(self._thumb_panel.load_folder)
        self._signals.status_message.connect(self._status_label.setText)
        self._signals.ocr_started.connect(
            lambda p: self._status_label.setText(f"OCR running: {Path(p).name}")
        )
        self._signals.ocr_complete.connect(
            lambda p, _: self._status_label.setText(f"OCR done: {Path(p).name}")
        )
        self._signals.ocr_failed.connect(
            lambda p, err: self._status_label.setText(f"OCR error: {Path(p).name} — {err}")
        )
        self._signals.classification_done.connect(
            lambda src, dst, rule: self._status_label.setText(
                f"Classified by {rule}: {Path(src).name} → {Path(dst).name}"
            )
        )
        self._signals.file_ready.connect(
            lambda p: self._progress.setVisible(True)
        )
        self._signals.ocr_complete.connect(
            lambda *_: self._progress.setVisible(False)
        )

    # ── Toolbar ────────────────────────────────────────────────────────────────
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar", self)
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)
        self.addToolBar(tb)

        act_add_watch = QAction("📁 Add Watch Folder", self)
        act_add_watch.setToolTip("Add a folder to the watch pipeline")
        act_add_watch.triggered.connect(self._add_watch_folder_dialog)
        tb.addAction(act_add_watch)

        act_show_watched = QAction("📋 Show Watched Folders", self)
        act_show_watched.setToolTip("Show currently watched folders")
        act_show_watched.triggered.connect(self._show_watched_folders)
        tb.addAction(act_show_watched)

        tb.addSeparator()

        act_ocr_all = QAction("🔍 OCR All", self)
        act_ocr_all.setToolTip("Run OCR on all files in the current folder")
        act_ocr_all.triggered.connect(self._ocr_current_folder)
        tb.addAction(act_ocr_all)

        tb.addSeparator()

        act_ocr_output = QAction("📂 OCR Output Folder", self)
        act_ocr_output.setToolTip("Select folder for OCR text output")
        act_ocr_output.triggered.connect(self._select_ocr_output_folder)
        tb.addAction(act_ocr_output)

        act_settings = QAction("⚙ Settings", self)
        act_settings.setToolTip("Open settings")
        act_settings.triggered.connect(self._open_settings)
        tb.addAction(act_settings)

        tb.addSeparator()
        
        # Engine selector
        self._engine_combo = QComboBox(self)
        self._engine_combo.setToolTip("Select OCR Engine Strategy")
        self._engine_combo.addItems(["🪄 Auto (Prefer Local)", "☁️ Cloud (Zhipu API)", "🖥️ Local (Hugging Face)"])
        
        # Set current mapped value
        current_mode = self._cfg.get("ocr.mode", "auto").lower()
        mode_idx = {"auto": 0, "cloud": 1, "local": 2}.get(current_mode, 0)
        self._engine_combo.setCurrentIndex(mode_idx)
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        
        tb.addWidget(QLabel(" Engine: ", self))
        tb.addWidget(self._engine_combo)

        # Theme toggle
        tb.addSeparator()
        act_theme = QAction("◑ Theme", self)
        act_theme.setToolTip("Toggle dark/light theme")
        act_theme.triggered.connect(self._toggle_theme)
        tb.addAction(act_theme)

    # ── Status bar ─────────────────────────────────────────────────────────────
    def _build_status_bar(self) -> None:
        sb = QStatusBar(self)
        self.setStatusBar(sb)

        self._status_label = QLabel("Ready")
        self._status_label.setProperty("secondary", "true")
        sb.addWidget(self._status_label, 1)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFixedWidth(140)
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)
        sb.addPermanentWidget(self._progress)

    # ── Watchers ───────────────────────────────────────────────────────────────
    def _start_watchers(self) -> None:
        watch_list = self._cfg.get("watch_folders", []) or []
        for entry in watch_list:
            path = entry.get("path", "") if isinstance(entry, dict) else str(entry)
            recursive = entry.get("recursive", False) if isinstance(entry, dict) else False
            auto_create = entry.get("auto_create", True) if isinstance(entry, dict) else True
            if auto_create:
                Path(path).mkdir(parents=True, exist_ok=True)
            self._watch_manager.add_folder(path, recursive=recursive)
        self._watch_manager.start()

    # ── Actions ────────────────────────────────────────────────────────────────
    def _add_watch_folder_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Watch Folder")
        if folder:
            self._watch_manager.add_folder(folder)
            self._signals.status_message.emit(f"Now watching: {folder}")

    def _ocr_current_folder(self) -> None:
        model = self._thumb_panel._model  # type: ignore[attr-defined]
        for i in range(model.rowCount()):
            idx = model.index(i)
            path = model.data(idx, Qt.ItemDataRole.UserRole)
            if path:
                self._signals.file_ready.emit(path)

    def _select_ocr_output_folder(self) -> None:
        """Prompt user to select OCR output folder."""
        from PySide6.QtWidgets import QFileDialog
        
        current_dir = self._cfg.get("output.ocr_output_dir", "./processed")
        folder = QFileDialog.getExistingDirectory(
            self, "Select OCR Output Folder", current_dir
        )
        if folder:
            self._cfg.set("output.ocr_output_dir", folder)
            self._signals.status_message.emit(f"OCR output folder set to: {folder}")
            log.info("OCR output folder updated to: %s", folder)

    def _open_settings(self) -> None:
        cfg_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        import subprocess, sys
        if sys.platform == "win32":
            os.startfile(str(cfg_path))
        else:
            subprocess.Popen(["xdg-open", str(cfg_path)])

    def _on_engine_changed(self, idx: int) -> None:
        """Update the configuration dynamically from the UI combo box."""
        mode_map = {0: "auto", 1: "cloud", 2: "local"}
        new_mode = mode_map.get(idx, "auto")
        
        # If switching to cloud mode, prompt for API key if not set
        if new_mode == "cloud":
            current_key = self._cfg.get("ocr.api_key", "")
            if not current_key or current_key == "${ZHIPU_API_KEY}":
                api_key = self._prompt_api_key()
                if api_key:
                    self._cfg.set("ocr.api_key", api_key)
                    log.info("API key saved to configuration")
                else:
                    # User cancelled, revert to auto mode
                    self._engine_combo.blockSignals(True)
                    self._engine_combo.setCurrentIndex(0)
                    self._engine_combo.blockSignals(False)
                    self._signals.status_message.emit("Cloud OCR cancelled - API key required")
                    return
        
        self._cfg.set("ocr.mode", new_mode)
        log.info(f"UI changed OCR engine mode to: {new_mode}")
        self._signals.status_message.emit(f"OCR Mode set to: {new_mode.upper()}")

    def _prompt_api_key(self) -> str | None:
        """Prompt user for Zhipu API key using a dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Cloud OCR - API Key Required")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        label = QLabel("Enter your Zhipu API Key for Cloud OCR:")
        label.setWordWrap(True)
        layout.addWidget(label)
        
        input_field = QLineEdit()
        input_field.setEchoMode(QLineEdit.EchoMode.Password)
        input_field.setPlaceholderText("Enter API key...")
        layout.addWidget(input_field)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return input_field.text().strip()
        return None

    def _show_watched_folders(self) -> None:
        """Display a dialog showing all currently watched folders."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Watched Folders")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        
        folders = self._watch_manager.watched_folders
        if folders:
            label = QLabel("Currently watched folders:")
            layout.addWidget(label)
            
            folder_list = QLabel("\n".join(f"• {f}" for f in folders))
            folder_list.setStyleSheet("font-family: monospace; padding: 10px;")
            layout.addWidget(folder_list)
        else:
            label = QLabel("No folders are currently being watched.")
            layout.addWidget(label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        
        dialog.exec()

    def _toggle_theme(self) -> None:
        from ui.styles import DARK_THEME, LIGHT_THEME
        current = QApplication.instance().styleSheet()
        new_sheet = LIGHT_THEME if DARK_THEME in current else DARK_THEME
        QApplication.instance().setStyleSheet(new_sheet)

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._watch_manager.stop()
        super().closeEvent(event)
