from __future__ import annotations

import re

import pymupdf


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be read or contains no usable text."""


def extract_text_from_pdf(data: bytes) -> str:
    """Extract plain text from a PDF byte payload."""
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — surface as domain error
        raise PDFExtractionError("Не удалось открыть PDF. Убедитесь, что файл не повреждён.") from exc

    if document.page_count == 0:
        document.close()
        raise PDFExtractionError("PDF не содержит страниц.")

    parts: list[str] = []
    try:
        for page in document:
            text = page.get_text("text")
            if text and text.strip():
                parts.append(text.strip())
    finally:
        document.close()

    raw = "\n\n".join(parts).strip()
    if not raw:
        raise PDFExtractionError(
            "В PDF не найден извлекаемый текст. Возможно, это скан без OCR."
        )

    # Normalize excessive whitespace while keeping paragraph breaks.
    cleaned = re.sub(r"[ \t]+\n", "\n", raw)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def is_pdf_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    return content_type.lower().split(";")[0].strip() in {
        "application/pdf",
        "application/x-pdf",
    }


def looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"
