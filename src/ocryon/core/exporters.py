from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

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
