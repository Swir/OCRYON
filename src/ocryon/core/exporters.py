from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document as WordDocument

from ocryon.core.document import DocumentPage


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
    """Export page images with an invisible searchable OCR text layer.

    The first alpha keeps a page-level text layer rather than word bounding
    boxes. The visual page stays identical to the loaded scan while PDF search
    and text extraction become available.
    """

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

            text_rect = fitz.Rect(12, 12, max(13, width - 12), max(13, height - 12))
            _insert_invisible_text(pdf_page, text_rect, source_page.ocr_text)

        document.save(str(destination), garbage=4, deflate=True)
    finally:
        document.close()

    return len(selected)


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

    # Very dense OCR output can still exceed the page-sized text box. Keep a
    # searchable fallback instead of silently producing an image-only page.
    compact = " ".join(cleaned.split())
    page.insert_text(
        fitz.Point(12, 18),
        compact,
        fontsize=2,
        fontname="helv",
        render_mode=3,
        overlay=True,
    )
