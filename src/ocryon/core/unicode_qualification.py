"""Actual frozen OCR and Unicode export acceptance, isolated from Qt.

Only used by ``OCRYON.exe --self-test-unicode`` in the RC pipeline.  Test
images contain synthetic words and stay in a temporary Unicode directory.
The gate fails closed; a partial or substituted PDF text layer is not PASS.
"""
from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
from threading import Event


def _font():
    from PIL import ImageFont

    fonts = (
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for filename in fonts:
        if filename.is_file():
            return ImageFont.truetype(str(filename), 64)
    raise RuntimeError("Native Unicode test font unavailable")


def _verify_unicode_round_trip() -> None:
    from PIL import Image, ImageDraw
    from docx import Document
    import fitz

    from ocryon.core.cancellable_tesseract import recognize_cancellable
    from ocryon.core.document import DocumentPage
    from ocryon.core.exporters import export_docx, export_searchable_pdf, export_txt
    from ocryon.core.ocr import TesseractEngine

    engine = TesseractEngine()
    if not engine.available() or (
        getattr(sys, "frozen", False) and not engine.uses_bundled_engine()
    ):
        raise RuntimeError("Bundled Tesseract engine unavailable")

    font = _font()
    cases = (
        ("pol", "Zażółć gęślą jaźń Łódź", ("Zażółć", "Łódź")),
        ("nor", "Ålesund Ørsta blåbær æøå", ("Ålesund", "Ørsta", "æøå")),
    )
    with tempfile.TemporaryDirectory(prefix="OCRYON-unicode-rc-") as temporary:
        root = Path(temporary) / "Zażółć_Ålesund_Ørsta"
        root.mkdir()
        pages = []
        for number, (language, expected, words) in enumerate(cases, 1):
            image = Image.new("RGB", (2200, 360), "white")
            ImageDraw.Draw(image).text((60, 45), expected, font=font, fill="black")
            result = recognize_cancellable(
                engine, image, language, Event(), timeout_seconds=75
            )
            if " ".join(result.text.split()) != expected or not result.words:
                raise AssertionError("OCR lost real Unicode text")
            if any(word not in result.text.split() for word in words):
                raise AssertionError("OCR lost mandatory Unicode word")
            pages.append(DocumentPage(
                source_path=root / f"Źródło_{number}_Å.png",
                page_number=number,
                image=image,
                ocr_text=result.text,
                ocr_language=language,
                ocr_words=result.words,
            ))

        pdf_path = root / "Wynik_Żółw_Å.pdf"
        txt_path = root / "Wynik_Żółw_Å.txt"
        docx_path = root / "Wynik_Żółw_Å.docx"
        count = len(cases)
        if (export_searchable_pdf(pages, pdf_path) != count or
                export_txt(pages, txt_path) != count or
                export_docx(pages, docx_path) != count):
            raise AssertionError("Unicode export page count changed")

        with fitz.open(pdf_path) as document:
            if len(document) != count:
                raise AssertionError("Unicode PDF page count changed")
            for index, (_, expected, words) in enumerate(cases):
                page = document[index]
                if " ".join(page.get_text("text").split()) != expected:
                    raise AssertionError("Unicode PDF text is incomplete")
                if any(not page.search_for(word) for word in words):
                    raise AssertionError("Unicode PDF search is incomplete")

        txt = " ".join(txt_path.read_text(encoding="utf-8").split())
        docx = " ".join(" ".join(
            paragraph.text for paragraph in Document(docx_path).paragraphs
        ).split())
        if any(expected not in txt or expected not in docx
               for _, expected, _ in cases):
            raise AssertionError("Unicode TXT/DOCX round trip is incomplete")


def run_unicode_selftest() -> int:
    """0=real OCR+all exports PASS; 25=missing evidence (no private trace)."""
    try:
        _verify_unicode_round_trip()
    except Exception:
        from ocryon.core.qualification import _report_selftest_status
        _report_selftest_status("OCRYON UNICODE SELFTEST FAIL")
        return 25
    from ocryon.core.qualification import _report_selftest_status
    _report_selftest_status("OCRYON UNICODE SELFTEST PASS: pol/nor OCR and PDF/TXT/DOCX")
    return 0
