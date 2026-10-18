"""Subprocess UTF-8 integrity gate for private OCR output.

A corrupted byte stream must not become U+FFFD in a searchable PDF.
This exercises the production subprocess path with a real child process.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from threading import Event
import time
from types import SimpleNamespace

import pytest

from ocryon.core import cancellable_tesseract


def _redirect_ocr_child(monkeypatch, factory):
    # Keep taskkill/subprocess.run real; replacing the global Popen also
    # redirected Windows cleanup into a second sleeping test child.
    proxy = SimpleNamespace(**vars(subprocess))
    proxy.Popen = factory
    monkeypatch.setattr(cancellable_tesseract, "subprocess", proxy)


def test_malformed_tesseract_utf8_rejected_without_leaking_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    original_popen = subprocess.Popen
    payload = "import sys; sys.stdout.buffer.write(bytes([0xff, 0xfe, 0x50]))"

    def run_real_child(*_argv: object, **kwargs: object) -> subprocess.Popen:
        return original_popen([sys.executable, "-c", payload], **kwargs)

    _redirect_ocr_child(monkeypatch, run_real_child)
    png = tmp_path / "page.png"
    png.write_bytes(b"synthetic")
    with pytest.raises(RuntimeError, match=r"^Offline OCR returned invalid UTF-8$") as exc:
        cancellable_tesseract._run_tesseract(
            Path(sys.executable), png, "pol", "tsv", Event(),
            time.monotonic() + 10,
        )
    message = str(exc.value)
    assert "\ufffd" not in message
    assert "page.png" not in message
    assert "0xff" not in message
    assert exc.value.__cause__ is None


def test_large_tesseract_stdout_is_bounded_and_redacted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Prove the real child cannot force unbounded Python stdout buffering."""
    original_popen = subprocess.Popen
    payload = "import sys; sys.stdout.buffer.write(b'X' * 16384)"
    def run_real_child(*_argv: object, **kwargs: object) -> subprocess.Popen:
        return original_popen([sys.executable, "-c", payload], **kwargs)
    _redirect_ocr_child(monkeypatch, run_real_child)
    monkeypatch.setattr(cancellable_tesseract, "_MAX_OCR_OUTPUT_BYTES", 4096)
    page = tmp_path / "private.png"
    page.write_bytes(b"private")
    with pytest.raises(RuntimeError, match="^Offline OCR output exceeds safe size limit$") as exc:
        cancellable_tesseract._run_tesseract(
            Path(sys.executable), page, "pol", "tsv", Event(), time.monotonic() + 10
        )
    assert "private" not in str(exc.value)
    assert "XXXXX" not in str(exc.value)


def test_streaming_oversized_stdout_stops_child_before_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Disk quota must abort a still-running child, not just its final output."""
    original_popen = subprocess.Popen
    children = []
    # Write 128 KiB, flush, THEN sleep. The previous implementation only
    # measured output after wait() and left the child sleeping until timeout.
    payload = (
        "import sys,time; "
        "sys.stdout.buffer.write(b'P' * 131072); "
        "sys.stdout.buffer.flush(); time.sleep(20)"
    )

    def run_real_child(*_argv: object, **kwargs: object) -> subprocess.Popen:
        child = original_popen([sys.executable, "-c", payload], **kwargs)
        children.append(child)
        return child

    _redirect_ocr_child(monkeypatch, run_real_child)
    monkeypatch.setattr(cancellable_tesseract, "_MAX_OCR_OUTPUT_BYTES", 32768)
    page = tmp_path / "private.png"
    page.write_bytes(b"private")
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match=r"^Offline OCR output exceeds safe size limit$"):
            cancellable_tesseract._run_tesseract(
                Path(sys.executable), page, "pol", "tsv", Event(),
                time.monotonic() + 10,
            )
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
    assert len(children) == 1
    assert children[0].poll() is not None, "Overflow left Tesseract running"
    assert time.monotonic() - started < 3, "Overflow was not stopped in-flight"


def test_real_sleeping_child_cancellation_stops_and_reaps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A running child must exit after a direct Event, not when a pipe drains."""
    from threading import Timer
    original_popen = subprocess.Popen
    children = []
    def run_real_child(*_argv: object, **kwargs: object) -> subprocess.Popen:
        child = original_popen([sys.executable, "-c", "import time; time.sleep(20)"], **kwargs)
        children.append(child)
        return child
    _redirect_ocr_child(monkeypatch, run_real_child)
    page = tmp_path / "private.png"
    page.write_bytes(b"private")
    event = Event()
    timer = Timer(0.25, event.set)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(cancellable_tesseract.OCRCancelled):
            cancellable_tesseract._run_tesseract(
                Path(sys.executable), page, "nor", "tsv", event,
                time.monotonic() + 10,
            )
    finally:
        timer.join(timeout=2)
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
    assert len(children) == 1
    assert children[0].poll() is not None
    assert time.monotonic() - started < 4


def test_real_sleeping_child_deadline_stops_and_reaps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    original_popen = subprocess.Popen
    children = []
    def run_real_child(*_argv: object, **kwargs: object) -> subprocess.Popen:
        child = original_popen([sys.executable, "-c", "import time; time.sleep(20)"], **kwargs)
        children.append(child)
        return child
    _redirect_ocr_child(monkeypatch, run_real_child)
    page = tmp_path / "private.png"
    page.write_bytes(b"private")
    started = time.monotonic()
    try:
        with pytest.raises(cancellable_tesseract.OCRDeadlineExceeded):
            cancellable_tesseract._run_tesseract(
                Path(sys.executable), page, "eng", "tsv", Event(),
                time.monotonic() + 0.25,
            )
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
    assert len(children) == 1
    assert children[0].poll() is not None
    assert time.monotonic() - started < 4
