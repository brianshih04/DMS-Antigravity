"""Searchable PDF builder using PyMuPDF (fitz).

Overlays an invisible text layer aligned to OCR bounding boxes on top of
the original image, producing a text-searchable PDF while preserving the
original visual appearance.
"""
from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

from core.config import Config
from ocr.base_engine import BoundingBox, OcrResult

log = logging.getLogger(__name__)

_INVISIBLE_RENDER_MODE = 3   # fitz text render mode: invisible


class PdfBuilder:
    """Converts an image + OcrResult into a searchable PDF file."""

    def __init__(self) -> None:
        cfg = Config.instance()
        self._suffix: str = cfg.get("output.searchable_pdf_suffix", "_searchable")
        self._out_dir: str = cfg.get("output.default_output_dir", "./processed")

    def build(self, image_path: str, result: OcrResult) -> str:
        """Create a searchable PDF next to *image_path* and return its path.

        The PDF is placed in ``output.default_output_dir`` (created if needed).
        """
        src = Path(image_path)
        out_dir = Path(self._out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        stem = src.stem + self._suffix
        out_path = out_dir / (stem + ".pdf")

        doc = fitz.open()
        try:
            # Insert the source image as a full-page PDF page
            with fitz.open(str(src)) as img_doc:
                # fitz can open JPEG/PNG/BMP/TIFF directly
                pdfbytes = img_doc.convert_to_pdf()

            img_pdf = fitz.open("pdf", pdfbytes)
            doc.insert_pdf(img_pdf)
            page: fitz.Page = doc[0]

            page_rect = page.rect          # points
            img_w = result.image_width or page_rect.width
            img_h = result.image_height or page_rect.height

            # Overlay invisible text for each bounding box
            for bb in result.bounding_boxes:
                self._insert_text(page, bb, img_w, img_h, page_rect)

            doc.save(str(out_path), garbage=4, deflate=True)
            log.info("Searchable PDF saved: %s", out_path)
        finally:
            doc.close()

        return str(out_path)

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _insert_text(
        page: "fitz.Page",
        bb: BoundingBox,
        img_w: float,
        img_h: float,
        page_rect: "fitz.Rect",
    ) -> None:
        """Map normalized bounding box to page coordinates and insert text."""
        pw = page_rect.width
        ph = page_rect.height

        # Convert normalized (0-1) coords to page points
        x0 = bb.x * pw
        y0 = bb.y * ph
        x1 = (bb.x + bb.w) * pw
        y1 = (bb.y + bb.h) * ph
        rect = fitz.Rect(x0, y0, x1, y1)

        if not bb.text.strip():
            return

        # Font size proportional to bounding-box height
        font_size = max(4, (y1 - y0) * 0.9)

        try:
            # insert_text places text at bottom-left of bbox (x0, y1)
            page.insert_text(
                fitz.Point(x0, y1 - 1),
                bb.text,
                fontname="helv",
                fontsize=font_size,
                render_mode=_INVISIBLE_RENDER_MODE,
                color=(0, 0, 0),
            )
        except Exception as exc:
            log.debug("insert_text failed for %r: %s", bb.text[:20], exc)

    # ── Merge / Split helpers (used by UI drag-drop) ──────────────────────────
    @staticmethod
    def merge_pdfs(pdf_paths: list[str], output_path: str) -> str:
        """Concatenate multiple PDFs into one. Returns *output_path*."""
        merged = fitz.open()
        try:
            for p in pdf_paths:
                with fitz.open(p) as doc:
                    merged.insert_pdf(doc)
            merged.save(output_path, garbage=4, deflate=True)
        finally:
            merged.close()
        return output_path

    @staticmethod
    def split_pdf(pdf_path: str, page_indices: list[int], output_dir: str) -> list[str]:
        """Extract *page_indices* from *pdf_path* into separate single-page PDFs."""
        out_paths: list[str] = []
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = Path(pdf_path).stem

        with fitz.open(pdf_path) as src_doc:
            for idx in page_indices:
                part = fitz.open()
                part.insert_pdf(src_doc, from_page=idx, to_page=idx)
                dest = str(out / f"{stem}_page{idx + 1}.pdf")
                part.save(dest)
                part.close()
                out_paths.append(dest)

        return out_paths
