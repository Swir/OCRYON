from pathlib import Path

from PIL import Image

from ocryon.core.document import DocumentPage, LoadedDocument


def test_page_label_contains_filename_and_page_number() -> None:
    page = DocumentPage(Path("scan.png"), 3, Image.new("RGB", (4, 4)))
    assert page.label == "scan.png — page 3"


def test_loaded_document_len_tracks_pages() -> None:
    path = Path("scan.png")
    doc = LoadedDocument(
        path,
        [
            DocumentPage(path, 1, Image.new("RGB", (4, 4))),
            DocumentPage(path, 2, Image.new("RGB", (4, 4))),
        ],
    )
    assert len(doc) == 2
