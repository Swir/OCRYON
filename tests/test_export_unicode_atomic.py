"""Real PyMuPDF / DOCX / TXT release-blocker regressions (Linux, not Windows)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from docx import Document as WordDocument
from PIL import Image

from ocryon.core.document import DocumentPage
from ocryon.core import exporters


POLISH = "Zażółć gęślą jaźń"
NORWEGIAN = "Rød blåbær og øya i Ålesund"


def _page(text: str, number: int = 1, words: tuple = ()) -> DocumentPage:
    return DocumentPage(
        source_path=Path("dokument_żółw_Ålesund.pdf"), page_number=number,
        image=Image.new("RGB", (1200, 350), "white"),
        ocr_text=text, ocr_language="pol+nor", ocr_words=words,
    )


def test_unicode_pdf_without_word_boxes_is_extractable_and_searchable(tmp_path):
    path = tmp_path / "Zażółć Ålesund — wyniki.pdf"
    assert exporters.export_searchable_pdf([_page(f"{POLISH}\n{NORWEGIAN}")], path) == 1
    with fitz.open(path) as pdf:
        assert len(pdf) == 1
        text = pdf[0].get_text()
        for expected in (POLISH, NORWEGIAN):
            assert expected in text
        assert pdf[0].search_for("Zażółć")
        assert pdf[0].search_for("Ålesund")
        assert pdf[0].get_images()
    # Font subset is materially smaller than an unsubsettled 3.5 MB font.
    assert path.stat().st_size < 250_000


def test_unicode_word_level_search_preserves_coordinates(tmp_path):
    words = (
        SimpleNamespace(text="Zażółć", left=70, top=90, width=150, height=30),
        SimpleNamespace(text="Ålesund", left=340, top=90, width=180, height=30),
    )
    path = tmp_path / "OCR_po_pozycjach.pdf"
    exporters.export_searchable_pdf([_page("Zażółć Ålesund", words=words)], path)
    with fitz.open(path) as pdf:
        text = pdf[0].get_text()
        assert "Zażółć" in text and "Ålesund" in text
        bounds = {word[4]: word for word in pdf[0].get_text("words")}
        assert abs(bounds["Zażółć"][0] - 70) < 3
        assert abs(bounds["Ålesund"][0] - 340) < 3
        assert pdf[0].search_for("Ålesund")


def test_atomic_text_export_preserves_existing_on_midwrite_failure(tmp_path, monkeypatch):
    path = tmp_path / "old.txt"
    path.write_bytes(b"KEEP ORIGINAL")
    original = Path.write_text

    def fail_after_write(self, text, *args, **kwargs):
        if self.name.startswith(".old.txt.ocryon-"):
            original(self, "BROKEN PARTIAL", *args, **kwargs)
            raise OSError("simulated disk failure")
        return original(self, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_after_write)
    with pytest.raises(OSError, match="simulated"):
        exporters.export_txt([_page(POLISH)], path)
    assert path.read_bytes() == b"KEEP ORIGINAL"
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_docx_export_preserves_existing_on_serializer_failure(tmp_path, monkeypatch):
    path = tmp_path / "old.docx"
    path.write_bytes(b"KEEP ORIGINAL")

    class BrokenDocument:
        def add_heading(self, *args, **kwargs): pass
        def add_paragraph(self, *args, **kwargs): pass
        def add_page_break(self): pass
        def save(self, path):
            Path(path).write_bytes(b"INCOMPLETE ZIP")
            raise OSError("simulated DOCX failure")

    monkeypatch.setattr(exporters, "WordDocument", BrokenDocument)
    with pytest.raises(OSError, match="simulated"):
        exporters.export_docx([_page(NORWEGIAN)], path)
    assert path.read_bytes() == b"KEEP ORIGINAL"
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_pdf_export_preserves_existing_on_serializer_failure(tmp_path, monkeypatch):
    path = tmp_path / "old.pdf"
    path.write_bytes(b"KEEP ORIGINAL")
    original_save = fitz.Document.save

    def fail_after_write(self, filename, *args, **kwargs):
        Path(filename).write_bytes(b"INCOMPLETE PDF")
        raise OSError("simulated PDF failure")

    monkeypatch.setattr(fitz.Document, "save", fail_after_write)
    with pytest.raises(OSError, match="simulated"):
        exporters.export_searchable_pdf([_page(POLISH)], path)
    assert path.read_bytes() == b"KEEP ORIGINAL"
    assert list(tmp_path.iterdir()) == [path]
    monkeypatch.setattr(fitz.Document, "save", original_save)


def test_txt_and_docx_round_trip_unicode(tmp_path):
    pages = [_page(POLISH), _page(NORWEGIAN, 2)]
    txt_path = tmp_path / "zażółć.txt"
    docx_path = tmp_path / "Ålesund.docx"
    assert exporters.export_txt(pages, txt_path) == 2
    assert exporters.export_docx(pages, docx_path) == 2
    for phrase in (POLISH, NORWEGIAN):
        assert phrase in txt_path.read_text(encoding="utf-8")
        assert phrase in "\n".join(p.text for p in WordDocument(docx_path).paragraphs)


def test_font_unsupported_character_fails_closed_preserves_pdf(tmp_path):
    path = tmp_path / "already.pdf"
    path.write_bytes(b"KEEP ORIGINAL")
    # Most built-in Unicode fallback fonts do not have musical symbols.
    rare = "\U0001fa9c"
    if exporters._unicode_font().has_glyph(ord(rare)):
        pytest.skip("bundled font unexpectedly supports chosen rare glyph")
    with pytest.raises(ValueError, match="font cannot represent"):
        exporters.export_searchable_pdf([_page(rare)], path)
    assert path.read_bytes() == b"KEEP ORIGINAL"


def test_ocr_searchable_pdf_two_pages_preserves_unicode_and_image(tmp_path):
    path = tmp_path / "two_pages.pdf"
    pages = [_page(POLISH), _page(NORWEGIAN,2)]
    assert exporters.export_searchable_pdf(pages, path)==2
    with fitz.open(path) as pdf:
        assert len(pdf)==2
        assert POLISH in pdf[0].get_text()
        assert NORWEGIAN in pdf[1].get_text()
        assert all(p.get_images() for p in pdf)


def test_tiny_scan_preserves_every_word_across_invisible_layers(tmp_path):
    # Previously every OCR PDF export from this legitimate thumbnail failed,
    # even though its complete Unicode text can be indexed in stacked layers.
    path = tmp_path / 'tiny-scan.pdf'
    text = 'Zażółć gęślą jaźń Søndag blåbær ' * 40
    image = Image.new('RGB', (40, 40), 'white')
    page = DocumentPage(Path('small.png'), 1, image, ocr_text=text)
    assert exporters.export_searchable_pdf([page], path) == 1
    with fitz.open(path) as pdf:
        assert ' '.join(pdf[0].get_text().split()) == ' '.join(text.split())
        assert pdf[0].search_for('blåbær')


def test_existing_pdf_survives_unreasonably_large_text(tmp_path):
    path = tmp_path / 'keep.pdf'
    path.write_bytes(b'KEEP ORIGINAL')
    image = Image.new('RGB', (40, 40), 'white')
    page = DocumentPage(Path('scan.png'), 1, image, ocr_text='Zażółć ' * 30_000)
    with pytest.raises(ValueError, match='safe searchable PDF layer limit'):
        exporters.export_searchable_pdf([page], path)
    assert path.read_bytes() == b'KEEP ORIGINAL'


def test_partial_or_invalid_ocr_word_boxes_preserve_complete_unicode_pdf(tmp_path):
    """Searchable PDF must never silently lose words present in OCR text.

    A prior positive *partial* count of coordinates suppressed fallback text,
    yielding a valid-looking PDF missing "Świr" from text search. Invalid
    geometry must also select the full page fallback before drawing anything.
    """
    cases = (
        (SimpleNamespace(text="Witaj", left=40, top=40, width=120, height=25),),
        (
            SimpleNamespace(text="Witaj", left=40, top=40, width=120, height=25),
            SimpleNamespace(text="Świr", left=1190, top=40, width=90, height=25),
        ),
    )
    for index, words in enumerate(cases):
        destination = tmp_path / f"partial-word-layer-{index}.pdf"
        exporters.export_searchable_pdf([_page("Witaj Świr", words=words)], destination)
        with fitz.open(destination) as pdf:
            extracted = " ".join(pdf[0].get_text().split())
            assert extracted == "Witaj Świr"
            assert pdf[0].search_for("Świr")


def test_long_unbroken_token_is_not_silently_broken_in_pdf(tmp_path):
    path = tmp_path / 'preserve.pdf'
    path.write_bytes(b'KEEP ORIGINAL')
    token = 'ąćęłńóśźż' * 100
    image = Image.new('RGB', (300, 400), 'white')
    page = DocumentPage(Path('scan.png'), 1, image, ocr_text=token)
    with pytest.raises(ValueError, match='did not preserve complete OCR text'):
        exporters.export_searchable_pdf([page], path)
    assert path.read_bytes() == b'KEEP ORIGINAL'
