"""Tests for PdfBuilder — searchable text overlay verification."""
from __future__ import annotations

import pytest
from pathlib import Path


def test_pdf_builder_creates_searchable_pdf(tmp_path, sample_image_path, mock_ocr_result):
    """PdfBuilder should produce a PDF with text spans covering OCR bboxes."""
    from ocr.pdf_builder import PdfBuilder
    import fitz

    builder = PdfBuilder()
    builder._out_dir = str(tmp_path)
    builder._suffix = "_searchable"

    out_pdf = builder.build(sample_image_path, mock_ocr_result)
    assert Path(out_pdf).exists(), "Output PDF was not created"
    assert out_pdf.endswith(".pdf")

    with fitz.open(out_pdf) as doc:
        assert doc.page_count == 1
        page = doc[0]
        # get_text("dict") captures all spans including render_mode=3 (invisible)
        page_dict = page.get_text("dict")

    all_span_text = " ".join(
        span["text"]
        for block in page_dict.get("blocks", [])
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    )

    for bb in mock_ocr_result.bounding_boxes:
        assert bb.text in all_span_text, (
            f"Expected {bb.text!r} in PDF text spans.\nGot: {all_span_text!r}"
        )


def test_pdf_merge(tmp_path, sample_image_path, mock_ocr_result):
    """Merged PDF should contain pages from both source PDFs."""
    from ocr.pdf_builder import PdfBuilder
    import fitz

    builder = PdfBuilder()
    builder._out_dir = str(tmp_path)
    builder._suffix = "_s"

    pdf1 = builder.build(sample_image_path, mock_ocr_result)
    pdf2 = builder.build(sample_image_path, mock_ocr_result)

    merged = str(tmp_path / "merged.pdf")
    PdfBuilder.merge_pdfs([pdf1, pdf2], merged)

    with fitz.open(merged) as doc:
        assert doc.page_count == 2


def test_pdf_split(tmp_path, sample_image_path, mock_ocr_result):
    """Splitting a 2-page PDF should produce 2 single-page PDFs."""
    from ocr.pdf_builder import PdfBuilder
    import fitz

    builder = PdfBuilder()
    builder._out_dir = str(tmp_path)
    builder._suffix = "_s"

    pdf1 = builder.build(sample_image_path, mock_ocr_result)
    pdf2 = builder.build(sample_image_path, mock_ocr_result)
    merged = str(tmp_path / "two_page.pdf")
    PdfBuilder.merge_pdfs([pdf1, pdf2], merged)

    out_pages = PdfBuilder.split_pdf(merged, [0, 1], str(tmp_path / "split"))
    assert len(out_pages) == 2
    for p in out_pages:
        with fitz.open(p) as doc:
            assert doc.page_count == 1
