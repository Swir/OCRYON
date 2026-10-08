"""Actual headless OCR smoke, safe to call before importing Qt.

This is a qualification gate, not a UI or production OCR fallback.
"""
from __future__ import annotations

import os
import sys
from PIL import Image, ImageDraw, ImageFont

from ocryon.core.ocr import TesseractEngine
from ocryon.resources import asset_path

UI_LANGUAGES = ('eng', 'pol', 'nor', 'eng+pol', 'eng+nor')


def _report_selftest_status(message: str) -> None:
    """Keep the self-test usable from PyInstaller's Windows --windowed EXE.

    The windowed bootloader sets sys.stdout/stderr to None.  The exit status
    is the qualification contract; readable output is optional if a console
    exists, not a reason to fail an otherwise healthy frozen OCR engine.
    """
    stream = getattr(sys, 'stdout', None)
    if stream is None:
        return
    try:
        stream.write(message + '\n')
    except (OSError, ValueError, AttributeError):
        # Output can be missing/closed even when a stream-like object exists.
        pass


def sample_image() -> Image.Image:
    image = Image.new('RGB', (1300, 320), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=92)
        draw.text((50, 60), 'OCRYON 123 TEST', font=font, fill='black')
    except (TypeError, OSError):
        # Pillow minimal font on some frozen systems has no scale parameter.
        raw = Image.new('L', (210, 38), 255)
        ImageDraw.Draw(raw).text((10, 8), 'TEST 123', fill=0, font=ImageFont.load_default())
        # Pixel-exact magnification keeps thin bitmap-font digits unambiguous;
        # LANCZOS smoothing caused OCR to misread 123 as 128 in ENG mode.
        image = raw.resize((1260, 228), Image.Resampling.NEAREST).convert('RGB')
    return image


def run_selftest() -> int:
    """Exit code: 0=ok, 21=bundle engine missing, 22=assets, 23=OCR output, 24=runtime failure."""
    try:
        frozen = bool(getattr(sys, 'frozen', False))
        if frozen and not all(asset_path(name).is_file() for name in ('ocryon.svg', 'ocryon.png')):
            _report_selftest_status('OCRYON SELFTEST FAIL: packaged artwork missing')
            return 22
        engine = TesseractEngine()
        if not engine.available() or (frozen and not engine.uses_bundled_engine()):
            _report_selftest_status('OCRYON SELFTEST FAIL: bundled OCR engine unavailable')
            return 21
        image = sample_image()
        for language in UI_LANGUAGES:
            result = engine.recognize(image, language)
            words = result.text.upper().split()
            if not ('TEST' in words and '123' in words):
                _report_selftest_status(f'OCRYON SELFTEST FAIL: OCR mismatch [{language}]')
                return 23
        _report_selftest_status('OCRYON SELFTEST PASS: all five OCR languages')
        return 0
    except Exception:
        # Never dump the exception/traceback; paths and extracted document text
        # must not leak from a public smoke log.
        _report_selftest_status('OCRYON SELFTEST FAIL: runtime error')
        return 24
