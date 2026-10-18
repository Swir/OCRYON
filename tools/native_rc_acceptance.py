"""Release-critical Windows acceptance gates, run against real source/frozen app.

This module deliberately does not claim that Windows acceptance passed until it
has been executed on Windows with the same runtime and archives to be shipped.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from zipfile import ZipFile


def _check_frozen(executable: Path, *, cwd: Path | None = None) -> None:
    """All five engine modes must work without the build machine's OCR tools."""
    if not executable.is_file():
        raise AssertionError("Frozen OCRYON.exe is missing")
    env = os.environ.copy()
    env["OCRYON_TESSERACT"] = str(executable.parent / "missing-host-tesseract.exe")
    env["TESSDATA_PREFIX"] = str(executable.parent / "missing-host-tessdata")
    env.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
    for mode in ("--self-test", "--self-test-unicode", "--self-test-qt", "--self-test-ui"):
        result = subprocess.run(
            [str(executable), mode], cwd=cwd or executable.parent,
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=180, check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"Frozen OCR/Unicode qualification {mode} failed "
                f"(exit={result.returncode})"
            )


def _check_portable_zip(path: Path) -> None:
    if not path.is_file():
        raise AssertionError("Portable ZIP is missing")
    with tempfile.TemporaryDirectory(prefix="OCRYON_") as tmp:
        root = Path(tmp) / "Zażółć_Ålesund_Ørsta"
        root.mkdir()
        with ZipFile(path) as bundle:
            bad = bundle.testzip()
            if bad is not None:
                raise AssertionError("Portable ZIP failed CRC")
            for entry in bundle.infolist():
                destination = (root / entry.filename).resolve()
                if not destination.is_relative_to(root.resolve()):
                    raise AssertionError("Unsafe portable ZIP entry")
            bundle.extractall(root)
        exe = root / "OCRYON.exe"
        if not exe.is_file():
            raise AssertionError("Portable ZIP has no top-level OCRYON.exe")
        _check_frozen(exe, cwd=root)
    print("PASS: portable Unicode ZIP, CRC and isolated frozen OCR modes")


def _find_unicode_font():
    """Use an actual installed TrueType font with Polish/Norwegian glyphs.

    This gate must fail closed if a native runner lacks such a font; replacing
    it with Pillow's built-in raster font would not test Unicode OCR.
    """
    from PIL import ImageFont

    paths = (
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for font_path in paths:
        if font_path.is_file():
            return ImageFont.truetype(str(font_path), 64)
    raise AssertionError("No installed TrueType font for native Unicode OCR evidence")


def _check_native_pdf() -> None:
    from PIL import Image, ImageDraw
    import fitz
    from ocryon.core.document import DocumentPage
    from ocryon.core.exporters import export_docx, export_searchable_pdf, export_txt
    from ocryon.core.ocr import TesseractEngine
    from ocryon.core.qualification import run_selftest

    if run_selftest() != 0:
        raise AssertionError("Source Tesseract five-mode qualification failed")

    # Use real Tesseract recognition to generate the page text and word boxes.
    # Merely setting DocumentPage.ocr_text to a known Unicode string could
    # falsely pass even when Windows OCR drops every Polish/Norwegian accent.
    cases = (
        ("pol", "Zażółć gęślą jaźń Łódź", ("Zażółć", "Łódź")),
        ("nor", "Ålesund Ørsta blåbær æøå", ("Ålesund", "Ørsta", "æøå")),
    )
    font = _find_unicode_font()
    engine = TesseractEngine()
    if not engine.available():
        raise AssertionError("Native Tesseract engine unavailable")

    with tempfile.TemporaryDirectory(prefix="OCRYON_") as tmp:
        root = Path(tmp) / "Zażółć_Ålesund_Ørsta"
        root.mkdir()
        pages = []
        for page_number, (language, expected, required_words) in enumerate(cases, start=1):
            image = Image.new("RGB", (2200, 360), "white")
            ImageDraw.Draw(image).text((60, 45), expected, fill="black", font=font)
            result = engine.recognize(image, language)
            normalized = " ".join(result.text.split())
            if normalized != expected or not result.words:
                raise AssertionError(f"Native {language} OCR did not preserve Unicode words")
            if any(word not in normalized.split() for word in required_words):
                raise AssertionError(f"Native {language} OCR lost a mandatory Unicode word")
            pages.append(
                DocumentPage(
                    source_path=root / f"Źródło_{page_number}_Å.png",
                    page_number=page_number,
                    image=image,
                    ocr_text=result.text,
                    ocr_language=language,
                    ocr_words=result.words,
                )
            )

        pdf_path = root / "Wynik_Żółw_Å.pdf"
        txt_path = root / "Wynik_Żółw_Å.txt"
        docx_path = root / "Wynik_Żółw_Å.docx"
        if export_searchable_pdf(pages, pdf_path) != len(cases):
            raise AssertionError("Searchable PDF page count changed")
        if export_txt(pages, txt_path) != len(cases):
            raise AssertionError("TXT page count changed")
        if export_docx(pages, docx_path) != len(cases):
            raise AssertionError("DOCX page count changed")

        with fitz.open(pdf_path) as pdf:
            if len(pdf) != len(cases):
                raise AssertionError("Searchable PDF page count changed")
            for index, (_, expected, required_words) in enumerate(cases):
                actual = " ".join(pdf[index].get_text("text").split())
                if actual != expected:
                    raise AssertionError("Searchable PDF lost real Polish/Norwegian OCR text")
                for word in required_words:
                    if not pdf[index].search_for(word):
                        raise AssertionError("Searchable PDF cannot find real Unicode OCR word")

        txt = txt_path.read_text(encoding="utf-8")
        from docx import Document
        docx_text = " ".join(p.text for p in Document(docx_path).paragraphs)
        for _, expected, _ in cases:
            if expected not in " ".join(txt.split()):
                raise AssertionError("TXT export lost real Unicode OCR text")
            if expected not in docx_text:
                raise AssertionError("DOCX export lost real Unicode OCR text")
    print("PASS: real pol/nor Tesseract OCR -> Unicode searchable PDF/TXT/DOCX")


def _check_native_qt_lifecycle() -> None:
    # Production code inside the frozen application runs this exact same
    # acceptance, preventing source-only Qt PASS from masking broken EXE Qt.
    from ocryon.ui.qt_qualification import check_qt_lifecycle

    check_qt_lifecycle()


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--source-native", action="store_true")
    modes.add_argument("--portable-zip", type=Path)
    modes.add_argument("--installed-exe", type=Path)
    parser.add_argument("--skip-qt", action="store_true", help="Non-native exploratory source check only")
    args = parser.parse_args()
    if args.source_native:
        _check_native_pdf()
        if not args.skip_qt:
            if os.name != "nt":
                raise AssertionError("Native Qt release gate requires Windows")
            _check_native_qt_lifecycle()
    elif args.portable_zip:
        _check_portable_zip(args.portable_zip.resolve())
    else:
        _check_frozen(args.installed_exe.resolve())
        print("PASS: installed isolated frozen OCR modes")


if __name__ == "__main__":
    main()
