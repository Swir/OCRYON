"""Release-critical: Qt cancel/deadline also cover Pillow preprocessing.

The worker's process polling is not enough when a large image is still being
converted, denoised, or resized before the subprocess can start.
"""
from __future__ import annotations

from pathlib import Path
import sys
from threading import Event
import time

import pytest
from PIL import Image

from ocryon.core import cancellable_tesseract, preprocess
from ocryon.core.ocr import TesseractEngine


def _engine_without_external_dependency() -> TesseractEngine:
    engine = TesseractEngine()
    engine.executable = Path(sys.executable)  # Never launched by these tests.
    return engine


def _no_child(*args: object, **kwargs: object) -> None:
    pytest.fail("Cancelled/timed-out preprocessing must not spawn Tesseract")


def test_cancel_mid_preprocess_returns_without_launching_tesseract(monkeypatch):
    cancel = Event()
    image = Image.new("RGB", (200, 120), "white")

    original = preprocess.ImageOps.autocontrast
    reached = []

    def trigger_cancel(prepared):
        reached.append(True)
        processed = original(prepared)
        cancel.set()  # This happens mid-pipeline, not before first checkpoint.
        return processed

    monkeypatch.setattr(preprocess.ImageOps, "autocontrast", trigger_cancel)
    monkeypatch.setattr(cancellable_tesseract, "_run_tesseract", _no_child)
    with pytest.raises(cancellable_tesseract.OCRCancelled):
        cancellable_tesseract.recognize_cancellable(
            _engine_without_external_dependency(), image, "pol", cancel
        )
    assert reached == [True]


def test_deadline_mid_preprocess_returns_without_launching_tesseract(monkeypatch):
    image = Image.new("RGB", (200, 120), "white")
    original = preprocess.ImageOps.autocontrast
    reached = []

    def exceed_budget(prepared):
        reached.append(True)
        time.sleep(0.3)
        return original(prepared)

    monkeypatch.setattr(preprocess.ImageOps, "autocontrast", exceed_budget)
    monkeypatch.setattr(cancellable_tesseract, "_run_tesseract", _no_child)
    with pytest.raises(cancellable_tesseract.OCRDeadlineExceeded):
        cancellable_tesseract.recognize_cancellable(
            _engine_without_external_dependency(), image, "nor", Event(),
            timeout_seconds=0.15,
        )
    assert reached == [True]
