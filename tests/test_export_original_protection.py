"""Actual PDF export must never silently destroy imported source documents."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import fitz
import pytest
from PIL import Image

from ocryon.core.document import DocumentPage
from ocryon.core.exporters import export_searchable_pdf


def source_page(path: Path) -> DocumentPage:
    return DocumentPage(
        source_path=path,
        page_number=1,
        image=Image.new("RGB", (240, 360), "white"),
        ocr_text="OCRYON TEST",
    )


def original_pdf(path: Path) -> bytes:
    with fitz.open() as doc:
        page = doc.new_page(width=240, height=360)
        page.insert_text((25, 70), "PRIVATE ORIGINAL", fontsize=13)
        doc.set_metadata({"title": "Unmodified original source"})
        doc.save(path)
    return path.read_bytes()


def test_export_cannot_replace_imported_original_pdf(tmp_path: Path) -> None:
    original = tmp_path / "source.pdf"
    original_bytes = original_pdf(original)

    with pytest.raises(ValueError, match="original source document"):
        export_searchable_pdf([source_page(original)], original)

    assert original.read_bytes() == original_bytes
    with fitz.open(original) as doc:
        assert doc.metadata["title"] == "Unmodified original source"
        assert "PRIVATE ORIGINAL" in doc[0].get_text()


def test_export_cannot_replace_existing_hardlink_alias(tmp_path: Path) -> None:
    original = tmp_path / "original.pdf"
    original_bytes = original_pdf(original)
    alias = tmp_path / "alias.pdf"
    try:
        os.link(original, alias)
    except OSError:
        pytest.skip("Filesystem has no hardlink support")

    with pytest.raises(ValueError, match="original source document"):
        export_searchable_pdf([source_page(original)], alias)

    assert original.read_bytes() == original_bytes
    assert alias.read_bytes() == original_bytes
    assert original.samefile(alias)


def test_separate_destination_still_exports_without_mutating_original(tmp_path: Path) -> None:
    original = tmp_path / "source.pdf"
    original_hash = hashlib.sha256(original_pdf(original)).digest()
    output = tmp_path / "recognized.pdf"

    assert export_searchable_pdf([source_page(original)], output) == 1
    assert hashlib.sha256(original.read_bytes()).digest() == original_hash
    with fitz.open(output) as doc:
        assert "OCRYON TEST" in doc[0].get_text()
    with fitz.open(original) as doc:
        assert "PRIVATE ORIGINAL" in doc[0].get_text()
