from pathlib import Path

from PIL import Image

from ocryon.core.document import DocumentPage, LoadedDocument


def test_page_label_contains_filename_and_page_number() -> None:
    page = DocumentPage(Path("scan.png"), 3, Image.new("RGB", (4, 4)))
    assert page.label == "scan.png — page 3"


def test_page_tracks_ocr_result() -> None:
    page = DocumentPage(Path("scan.png"), 1, Image.new("RGB", (4, 4)))
    assert page.has_ocr is False
    assert page.ocr_language is None

    page.ocr_text = "Recognized text"
    page.ocr_language = "eng"

    assert page.has_ocr is True
    assert page.ocr_language == "eng"


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


def test_loaded_document_counts_recognized_pages() -> None:
    path = Path("scan.png")
    doc = LoadedDocument(
        path,
        [
            DocumentPage(path, 1, Image.new("RGB", (4, 4)), ocr_text="one"),
            DocumentPage(path, 2, Image.new("RGB", (4, 4))),
            DocumentPage(path, 3, Image.new("RGB", (4, 4)), ocr_text="three"),
        ],
    )

    assert doc.recognized_pages == 2
