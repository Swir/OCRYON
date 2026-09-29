from pathlib import Path

from PIL import Image
import pytest

from ocryon.core.loaders import UnsupportedDocumentError, load_document


def test_load_image_creates_single_page(tmp_path: Path) -> None:
    source = tmp_path / "sample.png"
    Image.new("RGB", (16, 12), "white").save(source)

    document = load_document(source)

    assert len(document) == 1
    assert document.pages[0].image.size == (16, 12)
    assert document.pages[0].source_path == source.resolve()


def test_unsupported_file_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "sample.xyz"
    source.write_text("not a document", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentError):
        load_document(source)
