"""Export must preserve *every* imported source, including failed/blank OCR pages."""
from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest
from docx import Document as WordDocument
from PIL import Image

from ocryon.core.document import DocumentPage
from ocryon.core.exporters import export_docx, export_searchable_pdf, export_txt


def _make_original(path: Path) -> None:
    if path.suffix == ".pdf":
        with fitz.open() as document:
            page = document.new_page(width=200, height=280)
            page.insert_text((25, 80), "PRIVATE ORIGINAL")
            document.set_metadata({"title": "Important source"})
            document.save(path)
    elif path.suffix == ".docx":
        document = WordDocument()
        document.add_paragraph("PRIVATE ORIGINAL")
        document.save(path)
    else:
        path.write_text("PRIVATE ORIGINAL\n", encoding="utf-8")


def _page(source: Path, text: str) -> DocumentPage:
    return DocumentPage(
        source_path=source, page_number=1,
        image=Image.new("RGB", (240, 360), "white"),
        ocr_text=text,
    )


@pytest.mark.parametrize(
    "suffix,exporter", [
        (".pdf", export_searchable_pdf),
        (".txt", export_txt),
        (".docx", export_docx),
    ],
)
def test_unrecognized_source_is_never_overwritten(
    tmp_path: Path, suffix: str, exporter
) -> None:
    source = tmp_path / f"private{suffix}"
    _make_original(source)
    before = source.read_bytes()
    another = tmp_path / "other.png"
    another.write_bytes(b"unchanged")

    # One page failed OCR; a different page succeeded. The export must not
    # treat the failed page's imported source as disposable.
    pages = [_page(source, ""), _page(another, "OCRYON TEST")]
    with pytest.raises(ValueError, match="original source document"):
        exporter(pages, source)
    assert source.read_bytes() == before
    assert another.read_bytes() == b"unchanged"


def test_unrecognized_source_hardlink_alias_is_never_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "private.pdf"
    _make_original(source)
    alias = tmp_path / "alias.pdf"
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("Filesystem does not support hardlinks")
    before = source.read_bytes()
    pages = [_page(source, ""), _page(tmp_path / "other.png", "OCRYON TEST")]
    with pytest.raises(ValueError, match="original source document"):
        export_searchable_pdf(pages, alias)
    assert source.read_bytes() == before
    assert alias.read_bytes() == before
    assert source.samefile(alias)


def test_other_destination_still_exports_only_recognized_pages(tmp_path: Path) -> None:
    source = tmp_path / "private.pdf"
    _make_original(source)
    before = source.read_bytes()
    output = tmp_path / "output.pdf"
    pages = [_page(source, ""), _page(tmp_path / "other.png", "OCRYON TEST")]
    assert export_searchable_pdf(pages, output) == 1
    assert source.read_bytes() == before
    with fitz.open(output) as doc:
        assert len(doc) == 1
        assert "OCRYON TEST" in doc[0].get_text()
