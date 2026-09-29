from pathlib import Path

from docx import Document as WordDocument
from PIL import Image
import pytest

from ocryon.core.document import DocumentPage
from ocryon.core.exporters import export_docx, export_txt


def page(number: int, text: str) -> DocumentPage:
    return DocumentPage(
        Path("scan.pdf"),
        number,
        Image.new("RGB", (4, 4)),
        ocr_text=text,
        ocr_language="eng" if text else None,
    )


def test_export_txt_writes_only_recognized_pages(tmp_path: Path) -> None:
    destination = tmp_path / "export.txt"

    count = export_txt([page(1, "Alpha"), page(2, ""), page(3, "Gamma")], destination)

    assert count == 2
    content = destination.read_text(encoding="utf-8")
    assert "scan.pdf — page 1" in content
    assert "Alpha" in content
    assert "page 2" not in content
    assert "scan.pdf — page 3" in content
    assert "Gamma" in content


def test_export_docx_writes_recognized_pages(tmp_path: Path) -> None:
    destination = tmp_path / "export.docx"

    count = export_docx([page(1, "Alpha"), page(2, "Beta")], destination)

    assert count == 2
    document = WordDocument(destination)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "OCRYON OCR Export" in text
    assert "scan.pdf — page 1" in text
    assert "Alpha" in text
    assert "scan.pdf — page 2" in text
    assert "Beta" in text


@pytest.mark.parametrize("exporter", [export_txt, export_docx])
def test_export_rejects_empty_recognition(tmp_path: Path, exporter) -> None:
    destination = tmp_path / "empty.out"

    with pytest.raises(ValueError):
        exporter([page(1, "")], destination)
