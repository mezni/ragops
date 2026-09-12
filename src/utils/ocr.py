from pathlib import Path

from core.config import get_settings


def ocr_text(file_path: Path, page_number: int) -> str:
    """OCR fallback for scanned pages (no embedded text layer).

    Requires pdf2image + pytesseract + the tesseract binary. Degrades
    to "" (empty) when the toolchain is unavailable.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        return ""

    try:
        images = convert_from_path(
            str(file_path),
            first_page=page_number,
            last_page=page_number,
            dpi=get_settings().ocr.dpi,
        )
        if not images:
            return ""
        return (pytesseract.image_to_string(images[0]) or "").strip()
    except Exception:
        # Covers missing tesseract binary and any render/OCR failure.
        return ""