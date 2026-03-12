"""Right-pane async thumbnail grid (QListView + IconMode).

Thumbnails are generated in background threads (BaseWorker) using PIL/PyMuPDF.
QImage is emitted from the worker; converted to QPixmap on the main thread.
Includes an OCR/classification status badge overlay.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QSize,
    Qt,
    QThreadPool,
)
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QListView, QMenu, QWidget

from core.config import Config
from core.signals import AppSignals
from core.threadpool import BaseWorker
from ui.drag_drop import DragDropHandler

log = logging.getLogger(__name__)

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".pdf"}


# ── Thumbnail renderer (runs in thread pool) ────────────────────────────────

def _render_thumbnail(path: str, size: int) -> QImage:
    """Build a QImage thumbnail from an image or PDF file."""
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            with fitz.open(path) as doc:
                if doc.page_count == 0:
                    raise ValueError("Empty PDF")
                page = doc[0]
                mat = fitz.Matrix(size / max(page.rect.width, 1),
                                  size / max(page.rect.height, 1))
                pix = page.get_pixmap(matrix=mat, alpha=False)
            img = QImage(pix.samples, pix.width, pix.height,
                         pix.stride, QImage.Format.Format_RGB888)
        else:
            with Image.open(path) as pil:
                pil = pil.convert("RGBA")
                pil.thumbnail((size, size), Image.LANCZOS)
                data = pil.tobytes("raw", "RGBA")
                img = QImage(data, pil.width, pil.height,
                             QImage.Format.Format_RGBA8888)
        return img.copy()
    except Exception as exc:
        log.debug("Thumbnail render failed for %s: %s", path, exc)
        # Return a grey placeholder
        img = QImage(size, size, QImage.Format.Format_RGB888)
        img.fill(QColor("#3A3A3A"))
        return img


# ── List Model ───────────────────────────────────────────────────────────────

class ThumbnailModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths: list[str] = []
        self._pixmaps: dict[str, QPixmap] = {}
        self._badges: dict[str, str] = {}  # path → badge text
        self._thumb_size: int = 120

    def set_thumb_size(self, size: int) -> None:
        self._thumb_size = size

    def set_folder(self, folder: str) -> None:
        self.beginResetModel()
        folder_path = Path(folder)
        if folder_path.exists():
            self._paths = [
                str(folder_path / f)
                for f in sorted(os.listdir(folder_path))
                if Path(f).suffix.lower() in SUPPORTED_EXTS
            ]
        else:
            self._paths = []
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._paths)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._paths):
            return None
        path = self._paths[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return Path(path).name
        if role == Qt.ItemDataRole.DecorationRole:
            return self._pixmaps.get(path, self._placeholder())
        if role == Qt.ItemDataRole.SizeHintRole:
            s = self._thumb_size + 32
            return QSize(s, s)
        if role == Qt.ItemDataRole.UserRole:
            return path
        if role == Qt.ItemDataRole.ToolTipRole:
            return path
        return None

    def receive_thumbnail(self, path: str, img: QImage) -> None:
        """Called from main thread when a worker finishes."""
        pm = QPixmap.fromImage(img)
        # Draw badge if present
        badge = self._badges.get(path)
        if badge:
            pm = self._draw_badge(pm, badge)
        self._pixmaps[path] = pm
        if path in self._paths:
            row = self._paths.index(path)
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def set_badge(self, path: str, badge: str) -> None:
        self._badges[path] = badge
        if path in self._pixmaps:
            # Trigger redraw with badge
            self._pixmaps.pop(path, None)

    def _placeholder(self) -> QPixmap:
        pm = QPixmap(self._thumb_size, self._thumb_size)
        pm.fill(QColor("#3A3A3A"))
        return pm

    @staticmethod
    def _draw_badge(pm: QPixmap, text: str) -> QPixmap:
        result = pm.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Badge background
        painter.setBrush(QColor("#0078D4"))
        painter.setPen(Qt.PenStyle.NoPen)
        rect_h = 18
        painter.drawRoundedRect(2, result.height() - rect_h - 2,
                                result.width() - 4, rect_h, 4, 4)
        # Badge text
        font = QFont("Segoe UI Variable", 7)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(2, result.height() - rect_h - 2,
                         result.width() - 4, rect_h,
                         Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return result


# ── View ─────────────────────────────────────────────────────────────────────

class ThumbnailPanel(DragDropHandler, QListView):
    """Right-pane thumbnail grid with async rendering and drag/drop support."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        QListView.__init__(self, parent)
        self._model = ThumbnailModel(self)
        self._signals = AppSignals.instance()
        self._pool = QThreadPool.globalInstance()

        cfg = Config.instance()
        self._thumb_size: int = int(cfg.get("ui.thumbnail_size", 120))
        self._model.set_thumb_size(self._thumb_size)

        self.setModel(self._model)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSpacing(8)
        self.setIconSize(QSize(self._thumb_size, self._thumb_size))
        self.setUniformItemSizes(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.doubleClicked.connect(self._on_double_clicked)

        self._init_drag_drop()

        # Listen for new OCR-completed files to badge them
        self._signals.ocr_complete.connect(self._on_ocr_complete)
        self._signals.classification_done.connect(self._on_classified)

    # ── Public API ─────────────────────────────────────────────────────────
    def load_folder(self, folder: str) -> None:
        self._model.set_folder(folder)
        # Kick off async thumbnail rendering for each file
        for i in range(self._model.rowCount()):
            idx = self._model.index(i)
            path = self._model.data(idx, Qt.ItemDataRole.UserRole)
            self._request_thumbnail(path)

    def refresh(self) -> None:
        """Reload current folder (e.g. after merge/split)."""
        # Re-trigger folder load by re-setting same paths
        if self._current_folder:
            self.load_folder(self._current_folder)

    # ── Async thumbnails ────────────────────────────────────────────────────
    def _request_thumbnail(self, path: str) -> None:
        size = self._thumb_size
        worker = BaseWorker(_render_thumbnail, path, size)
        worker.signals.result.connect(
            lambda img, p=path: self._model.receive_thumbnail(p, img)
        )
        self._pool.start(worker)

    # ── Signals ─────────────────────────────────────────────────────────────
    def _on_ocr_complete(self, path: str, result) -> None:
        self._model.set_badge(path, "OCR ✓")
        self._request_thumbnail(path)

    def _on_classified(self, src: str, dst: str, rule_id: str) -> None:
        self._model.set_badge(src, f"→{rule_id}")

    # ── Context menu ─────────────────────────────────────────────────────────
    def _context_menu(self, pos) -> None:
        index = self.indexAt(pos)
        path: str | None = (
            self._model.data(index, Qt.ItemDataRole.UserRole)
            if index.isValid() else None
        )
        menu = QMenu(self)

        if path:
            from pathlib import Path as _P
            if _P(path).suffix.lower() == ".pdf":
                act_split = menu.addAction("✂  Split PDF Pages…")
                act_split.triggered.connect(
                    lambda: self._show_split_menu(pos, path)
                )
            act_ocr = menu.addAction("🔍  Run OCR")
            act_ocr.triggered.connect(lambda: self._run_ocr(path))
            menu.addSeparator()

        act_refresh = menu.addAction("🔄  Refresh")
        act_refresh.triggered.connect(self.refresh)
        menu.exec(self.viewport().mapToGlobal(pos))

    def _run_ocr(self, path: str) -> None:
        self._signals.file_ready.emit(path)

    def _on_double_clicked(self, index: QModelIndex) -> None:
        """Open file with default application when double-clicked."""
        path: str | None = self._model.data(index, Qt.ItemDataRole.UserRole)
        if path:
            file_path = Path(path)
            if sys.platform == "win32":
                os.startfile(str(file_path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(file_path)])
            else:
                subprocess.Popen(["xdg-open", str(file_path)])
            self._signals.status_message.emit(f"Opened: {file_path.name}")

    # ── Folder tracking ────────────────────────────────────────────────────
    _current_folder: str = ""

    def load_folder(self, folder: str) -> None:  # type: ignore[override]
        self._current_folder = folder
        self._model.set_folder(folder)
        for i in range(self._model.rowCount()):
            idx = self._model.index(i)
            path = self._model.data(idx, Qt.ItemDataRole.UserRole)
            self._request_thumbnail(path)
