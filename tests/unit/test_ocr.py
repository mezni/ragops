from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from utils.ocr import ocr_text


def _make_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, "Rendered text with no text layer")
    c.save()


def test_ocr_returns_empty_when_toolchain_unavailable(tmp_path):
    pdf = tmp_path / "scanned.pdf"
    _make_pdf(pdf)
    # tesseract binary is absent in CI/dev: OCR must degrade to "".
    assert ocr_text(pdf, 1) == ""


def test_ocr_returns_empty_for_missing_file(tmp_path):
    assert ocr_text(tmp_path / "does-not-exist.pdf", 1) == ""


def test_ocr_returns_empty_for_invalid_page_number(tmp_path):
    pdf = tmp_path / "scanned.pdf"
    _make_pdf(pdf)
    assert ocr_text(pdf, 999) == ""