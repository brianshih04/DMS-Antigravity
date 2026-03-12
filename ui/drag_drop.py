"""Drag-and-drop handler for document merge and split operations.

Installed on ThumbnailPanel as a mixin.  Supports:
  - Drop files onto a thumbnail → PDF merge
  - Right-click → Split PDF by page
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtWidgets import QListView, QMenu

from ocr.pdf_builder import PdfBuilder

log = logging.getLogger(__name__)


class DragDropHandler:
    """Mixin methods to be used by ThumbnailPanel (which is a QListView)."""

    # NOTE: `self` is assumed to be a QListView instance.

    def _init_drag_drop(self) -> None:
        """Call from __init__ of the host widget."""
        self: QListView  # type: ignore[annotation-unchecked]
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QListView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        md: QMimeData = event.mimeData()
        if not md.hasUrls():
            event.ignore()
            return

        dropped_paths = [
            url.toLocalFile() for url in md.urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".pdf"
        ]
        if not dropped_paths:
            event.ignore()
            return

        # Get target PDF from the item under drop position
        index = self.indexAt(event.position().toPoint())  # type: ignore[attr-defined]
        target_path: str | None = None
        if index.isValid():
            target_path = self.model().data(index, Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]

        if target_path and Path(target_path).suffix.lower() == ".pdf":
            self._merge_pdfs(target_path, dropped_paths)
        else:
            log.debug("Drop target is not a PDF; ignoring merge.")

        event.acceptProposedAction()

    def _merge_pdfs(self, base_path: str, additional: list[str]) -> None:
        all_paths = [base_path] + additional
        out_path = str(Path(base_path).parent / (Path(base_path).stem + "_merged.pdf"))
        try:
            PdfBuilder.merge_pdfs(all_paths, out_path)
            log.info("Merged %d PDFs → %s", len(all_paths), out_path)
            # Refresh the panel to show the new file
            if hasattr(self, "refresh"):
                self.refresh()  # type: ignore[attr-defined]
        except Exception as exc:
            log.error("PDF merge failed: %s", exc)

    def _show_split_menu(self, pos, pdf_path: str) -> None:
        """Right-click context menu: split PDF pages."""
        import fitz
        try:
            doc = fitz.open(pdf_path)
            page_count = doc.page_count
            doc.close()
        except Exception:
            return

        menu = QMenu(self)  # type: ignore[call-arg]
        for i in range(page_count):
            act = menu.addAction(f"Extract page {i + 1}")
            act.triggered.connect(lambda checked, idx=i: self._split_page(pdf_path, idx))
        menu.addSeparator()
        act_all = menu.addAction("Split all pages")
        act_all.triggered.connect(lambda: self._split_all(pdf_path, page_count))
        menu.exec(self.mapToGlobal(pos))  # type: ignore[attr-defined]

    def _split_page(self, pdf_path: str, page_idx: int) -> None:
        out_dir = str(Path(pdf_path).parent)
        PdfBuilder.split_pdf(pdf_path, [page_idx], out_dir)
        if hasattr(self, "refresh"):
            self.refresh()  # type: ignore[attr-defined]

    def _split_all(self, pdf_path: str, page_count: int) -> None:
        out_dir = str(Path(pdf_path).parent)
        PdfBuilder.split_pdf(pdf_path, list(range(page_count)), out_dir)
        if hasattr(self, "refresh"):
            self.refresh()  # type: ignore[attr-defined]
