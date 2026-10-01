from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import fitz
from docx import Document as WordDocument

from ocryon.core.document import DocumentPage

if TYPE_CHECKING:
    from ocryon.core.ocr import OCRWord


def recognized_pages(pages: Sequence[DocumentPage]) -> list[DocumentPage]:
    return [page for page in pages if page.has_ocr]


def export_txt(pages: Sequence[DocumentPage], destination: str | Path) -> int:
    selected = recognized_pages(pages)
    if not selected:
        raise ValueError("There are no recognized pages to export.")

    blocks = []
    for page in selected:
        blocks.append(f"=== {page.label} ===\n{page.ocr_text.rstrip()}")

    path = Path(destination)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return len(selected)


def export_docx(pages: Sequence[DocumentPage], destination: str | Path) -> int:
    selected = recognized_pages(pages)
    if not selected:
        raise ValueError("There are no recognized pages to export.")

    document = WordDocument()
    document.add_heading("OCRYON OCR Export", level=0)

    for index, page in enumerate(selected):
        if index:
            document.add_page_break()
        document.add_heading(page.label, level=1)
        document.add_paragraph(page.ocr_text)

    document.save(str(destination))
    return len(selected)


def export_searchable_pdf(
    pages: Sequence[DocumentPage],
    destination: str | Path,
) -> int:
    """Export page images with an invisible searchable OCR text layer."""

    selected = recognized_pages(pages)
    if not selected:
        raise ValueError("There are no recognized pages to export.")

    document = fitz.open()
    try:
        for source_page in selected:
            image = source_page.image
            width, height = image.size
            pdf_page = document.new_page(width=width, height=height)

            image_buffer = BytesIO()
            image.save(image_buffer, format="PNG")
            pdf_page.insert_image(pdf_page.rect, stream=image_buffer.getvalue())

            inserted_words = _insert_invisible_words(pdf_page, source_page.ocr_words)
            if inserted_words == 0:
                text_rect = fitz.Rect(
                    12,
                    12,
                    max(13, width - 12),
                    max(13, height - 12),
                )
                _insert_invisible_text(pdf_page, text_rect, source_page.ocr_text)

        document.save(str(destination), garbage=4, deflate=True)
    finally:
        document.close()

    return len(selected)


def _insert_invisible_words(
    page: fitz.Page,
    words: Sequence["OCRWord"],
) -> int:
    """Place OCR words near their original positions in the PDF text layer."""

    inserted = 0
    page_width = float(page.rect.width)
    page_height = float(page.rect.height)

    for word in words:
        text = word.text.strip()
        if not text:
            continue

        x = max(0.5, min(float(word.left), max(0.5, page_width - 0.5)))
        top = max(0.0, min(float(word.top), max(0.0, page_height - 1.0)))
        width = max(1.0, min(float(word.width), max(1.0, page_width - x)))
        height = max(1.0, min(float(word.height), max(1.0, page_height - top)))

        max_font_size = max(1.0, min(72.0, height * 0.85))
        unit_width = fitz.get_text_length(text, fontname="helv", fontsize=1.0)
        if unit_width > 0:
            font_size = max(1.0, min(max_font_size, (width / unit_width) * 0.95))
        else:
            font_size = max_font_size

        baseline = min(page_height - 0.5, top + max(1.0, height * 0.82))
        page.insert_text(
            fitz.Point(x, baseline),
            text,
            fontsize=font_size,
            fontname="helv",
            render_mode=3,
            overlay=True,
        )
        inserted += 1

    return inserted


def _insert_invisible_text(page: fitz.Page, rect: fitz.Rect, text: str) -> None:
    cleaned = text.strip()
    if not cleaned:
        return

    for font_size in (11, 9, 7, 5, 3):
        remaining = page.insert_textbox(
            rect,
            cleaned,
            fontsize=font_size,
            fontname="helv",
            render_mode=3,
            overlay=True,
        )
        if remaining >= 0:
            return

    compact = " ".join(cleaned.split())
    page.insert_text(
        fitz.Point(12, 18),
        compact,
        fontsize=2,
        fontname="helv",
        render_mode=3,
        overlay=True,
    )
