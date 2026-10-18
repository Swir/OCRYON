"""Linux subprocess regression and fake-Qt worker tests; NOT native GUI QA."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import threading
import time
import types
from dataclasses import dataclass

import pytest
from PIL import Image, ImageDraw, ImageFont

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

# Keep these fake dependencies in this test module only. Pytest collects every
# file in one interpreter: leaving a stub in sys.modules made real exporter
# tests import a fake DocumentPage and invalidated the CI qualification suite.
_SCOPED_MODULE_NAMES = (
    "ocryon.core.ocr", "ocryon.core.preprocess", "ocryon.core.document",
    "ocryon.core.cancellable_tesseract", "ocryon.ui.ocr_worker",
    "PySide6", "PySide6.QtCore",
)
_ORIGINAL_MODULES = {name: sys.modules.get(name) for name in _SCOPED_MODULE_NAMES}

# The original OCRYON production modules are present remotely, but are not
# available in this recovered scratch checkpoint; use interface shims ONLY
# to test the new Popen implementation, never to claim full app acceptance.
@dataclass
class OCRResult:
    text: str
    language: str
    words: tuple = ()

class OCREngine:
    pass

class TesseractEngine(OCREngine):
    def __init__(self, executable=None):
        self.executable = Path(executable or "/usr/bin/tesseract")
        self.preprocess_options = None


def _result_from_tesseract_data(data, *, language, source_size, prepared_size):
    texts = []
    coords = []
    for pos, text in enumerate(data["text"]):
        if str(text).strip():
            texts.append(str(text))
            coords.append((data["left"][pos], data["top"][pos]))
    return OCRResult(" ".join(texts), language, tuple(coords))

core_ocr = types.ModuleType("ocryon.core.ocr")
core_ocr.OCRResult = OCRResult
core_ocr.OCREngine = OCREngine
core_ocr.TesseractEngine = TesseractEngine
core_ocr._result_from_tesseract_data = _result_from_tesseract_data
sys.modules["ocryon.core.ocr"] = core_ocr

preprocess = types.ModuleType("ocryon.core.preprocess")
def _shim_prepare_for_ocr(image, options, *, check_interrupt=None):
    # The production cancellable runner passes a cancellation checkpoint to
    # preprocessing. Keep the isolated fake-Qt smoke harness in sync so it
    # exercises the actual Tesseract runner rather than failing at the stub.
    if check_interrupt is not None:
        check_interrupt()
    return image

preprocess.prepare_for_ocr = _shim_prepare_for_ocr
preprocess.preprocess_options_for_preset = lambda name: name
sys.modules["ocryon.core.preprocess"] = preprocess

class SignalInstance:
    def __init__(self): self.listeners = []; self.messages = []
    def connect(self, fn): self.listeners.append(fn)
    def emit(self, *args):
        self.messages.append(args)
        for fn in self.listeners: fn(*args)

class SignalDescriptor:
    def __init__(self, *args): pass
    def __set_name__(self, owner, name): self.name = name
    def __get__(self, instance, owner):
        if instance is None: return self
        return instance.__dict__.setdefault(self.name, SignalInstance())

qtcore = types.ModuleType("PySide6.QtCore")
qtcore.QObject = type("QObject", (), {"__init__": lambda self: None})
qtcore.Signal = SignalDescriptor
qtcore.Slot = lambda *a, **k: (lambda fn: fn)
qt = types.ModuleType("PySide6")
qt.QtCore = qtcore
sys.modules["PySide6"] = qt
sys.modules["PySide6.QtCore"] = qtcore

document = types.ModuleType("ocryon.core.document")
@dataclass
class DocumentPage:
    image: object
document.DocumentPage = DocumentPage
sys.modules["ocryon.core.document"] = document

cancellable = importlib.import_module("ocryon.core.cancellable_tesseract")
worker_mod = importlib.import_module("ocryon.ui.ocr_worker")

# Both imported objects keep the dependencies they were loaded with; restore
# the interpreter registry before pytest discovers other production tests.
for _name, _previous in _ORIGINAL_MODULES.items():
    if _previous is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _previous


def sample():
    img = Image.new("RGB", (1250, 290), "white")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 92)
    ImageDraw.Draw(img).text((35, 55), "OCRYON TEST 123", font=font, fill="black")
    return img


def test_real_tesseract_five_modes():
    if not Path("/usr/bin/tesseract").is_file():
        pytest.skip("Linux Tesseract missing")
    image = sample()
    for lang in ("eng", "pol", "nor", "eng+pol", "eng+nor"):
        result = cancellable.recognize_cancellable(TesseractEngine(), image, lang, threading.Event())
        assert "TEST" in result.text.upper().split(), (lang, result.text)
        assert "123" in result.text.split(), (lang, result.text)
        assert result.words, lang


def slow_executable(tmp_path):
    exe = tmp_path / "fake-tesseract"
    exe.write_text("#!/usr/bin/env python3\nimport os,time\nopen(os.environ['OCRYON_TEST_PID'],'w').write(str(os.getpid()))\ntime.sleep(30)\n", encoding="utf-8")
    exe.chmod(0o755)
    return exe


def wait_for_marker(marker, timeout=4):
    start = time.monotonic()
    while not marker.exists():
        if time.monotonic() - start > timeout: raise AssertionError("subprocess did not start")
        time.sleep(0.015)


def test_cancel_kills_active_subprocess_and_reaps(tmp_path, monkeypatch):
    marker = tmp_path / "pid"
    monkeypatch.setenv("OCRYON_TEST_PID", str(marker))
    exe = slow_executable(tmp_path)
    evt = threading.Event()
    outcome = []
    def job():
        try: cancellable.recognize_cancellable(TesseractEngine(exe), sample(), "eng", evt)
        except BaseException as exc: outcome.append(exc)
    thr = threading.Thread(target=job, daemon=True)
    thr.start()
    wait_for_marker(marker)
    start = time.monotonic()
    evt.set()
    thr.join(3)
    assert not thr.is_alive(), "cancel did not stop real active OCR process"
    assert time.monotonic() - start < 3
    assert len(outcome) == 1 and isinstance(outcome[0], cancellable.OCRCancelled)
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)



def test_cancel_kills_child_inheriting_stdout_pipe(tmp_path, monkeypatch):
    """Regression: killing only the parent left communicate() hung for 30s."""
    marker = tmp_path / "spawned"
    monkeypatch.setenv("OCRYON_TEST_MARKER", str(marker))
    exe = tmp_path / "forking-tesseract"
    exe.write_text(
        '#!/bin/sh\nsleep 30 &\nchild=$!\nprintf "%s" "$child" > "$OCRYON_TEST_MARKER"\nwait "$child"\n',
        encoding="utf-8",
    )
    exe.chmod(0o755)
    image = tmp_path / "sample.png"
    sample().save(image)
    cancel = threading.Event()
    received = []

    def run():
        try:
            cancellable._run_tesseract(
                exe, image, "eng", "tsv", cancel, time.monotonic() + 20
            )
        except BaseException as error:
            received.append(error)

    job = threading.Thread(target=run, daemon=True)
    job.start()
    wait_for_marker(marker)
    began = time.monotonic()
    cancel.set()
    job.join(timeout=3)
    assert not job.is_alive(), "OCR cancellation hung on a descendant's stdout"
    assert time.monotonic() - began < 3
    assert len(received) == 1 and isinstance(received[0], cancellable.OCRCancelled)

def test_deadline_kills_active_subprocess(tmp_path, monkeypatch):
    marker = tmp_path / "pid"
    monkeypatch.setenv("OCRYON_TEST_PID", str(marker))
    exe = slow_executable(tmp_path)
    source = tmp_path / "test.png"
    sample().save(source)
    start = time.monotonic()
    with pytest.raises(cancellable.OCRDeadlineExceeded):
        cancellable._run_tesseract(
            exe, source, "eng", "tsv", threading.Event(), start + 2.0
        )
    assert 1.7 <= time.monotonic() - start < 3.5
    assert marker.is_file(), "cannot claim subprocess reap if it never started"
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)



def test_partial_tsv_layout_falls_back_to_complete_plain_text(tmp_path):
    """A bad single word box must not silently erase OCR words in a PDF."""
    source = tmp_path / "page.png"
    sample().save(source)
    fake = tmp_path / "fake_tesseract"
    fake.write_text(
        '#!/usr/bin/env python3\n'
        'import sys\n'
        'if sys.argv[-1] == "tsv":\n'
        ' print("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext")\n'
        ' print("5\t1\t1\t1\t1\t1\t10\t20\t50\t30\t99\tGOOD")\n'
        ' print("5\t1\t1\t1\t1\t2\t99999\t20\t50\t30\t99\tMISSING")\n'
        'else: print("GOOD MISSING")\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    result = cancellable.recognize_cancellable(
        TesseractEngine(fake), sample(), "eng", threading.Event()
    )
    assert result.text.strip() == "GOOD MISSING"
    assert not result.words, "Partial TSV boxes could produce a misleading PDF"


def test_worker_discards_late_page_after_direct_cancel():
    class SlowCustomEngine(OCREngine):
        def __init__(self): self.started = threading.Event(); self.resume = threading.Event()
        def recognize(self, image, lang):
            self.started.set()
            self.resume.wait(2)
            return OCRResult("private data", lang, ((1, 2),))
    engine = SlowCustomEngine()
    worker = worker_mod.OCRWorker(engine, [DocumentPage(sample())], [0], "eng")
    th = threading.Thread(target=worker.run)
    th.start()
    assert engine.started.wait(1)
    worker.cancel()  # Called from a different thread, without a Qt queued slot.
    engine.resume.set()
    th.join(2)
    assert not th.is_alive()
    assert worker.page_ready.messages == []
    assert worker.progress.messages == []
    assert worker.failed.messages == []
    assert worker.finished.messages == [()]


def test_worker_catches_cancel_without_failure_signal(monkeypatch):
    def cancel_immediately(engine, image, language, cancellation):
        cancellation.set()
        raise cancellable.OCRCancelled()
    monkeypatch.setattr(worker_mod, "recognize_cancellable", cancel_immediately)
    worker = worker_mod.OCRWorker(TesseractEngine(), [DocumentPage(sample())], [0], "eng")
    worker.run()
    assert worker.finished.messages == [()]
    assert not worker.failed.messages


def test_real_polish_and_norwegian_unicode():
    if not Path("/usr/bin/tesseract").is_file():
        pytest.skip("Linux Tesseract missing")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 85)
    for text, language, expected in (
        ("Zażółć gęślą jaźń", "pol", ("Zażółć", "gęślą", "jaźń")),
        ("Rød blåbær og øya i Ålesund", "nor", ("Rød", "blåbær", "Ålesund")),
    ):
        image = Image.new("RGB", (1700, 250), "white")
        ImageDraw.Draw(image).text((35, 50), text, font=font, fill="black")
        result = cancellable.recognize_cancellable(
            TesseractEngine(), image, language, threading.Event()
        )
        assert all(word in result.text for word in expected), (language, result.text)


def test_worker_timeout_message_is_redacted(monkeypatch):
    def timeout(engine, image, lang, cancellation):
        raise cancellable.OCRDeadlineExceeded("secret user document path")
    monkeypatch.setattr(worker_mod, "recognize_cancellable", timeout)
    worker = worker_mod.OCRWorker(TesseractEngine(), [DocumentPage(sample())], [0], "eng")
    worker.run()
    assert worker.failed.messages == [(0, "Offline OCR timed out",)]
    assert worker.finished.messages == [()]
    assert not worker.page_ready.messages


def test_malformed_tsv_boxes_are_not_mapped_to_pdf_coordinates():
    """A broken TSV row must be dropped, not clamped to a bogus PDF box."""
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    def row(word, x, y, w, h, conf="95"):
        return f"5\t1\t1\t1\t1\t1\t{x}\t{y}\t{w}\t{h}\t{conf}\t{word}"
    rows = [header, row("VALID", 10, 20, 80, 25),
            row("OUT_OF_BOUNDS", 1190, 20, 40, 25),
            row("INVALID", "not-a-number", 20, 80, 25),
            row("ZERO", 10, 20, 0, 25), row("NEGATIVE", -2, 20, 80, 25),
            row("NAN", 10, 20, 80, 25, "nan")]
    boxes = cancellable._parse_tsv("\n".join(rows), prepared_size=(1200, 220))
    assert boxes["text"] == ["VALID"]
    assert boxes["left"] == ["10"]
    assert all(len(value) == 1 for value in boxes.values())


def test_worker_emits_atomic_ocr_text_words_and_language():
    class SinglePageEngine(OCREngine):
        def recognize(self, image, language):
            return OCRResult("żółw Ålesund", language, ((17, 20, 50, 12),))
    worker = worker_mod.OCRWorker(
        SinglePageEngine(), [DocumentPage(sample())], [0], "pol"
    )
    worker.run()
    assert worker.page_ready.messages == [
        (0, 0, "żółw Ålesund", "pol", ((17, 20, 50, 12),))
    ]
    assert worker.progress.messages == [(0, 1, 1)]
    assert worker.finished.messages == [()]
    assert worker.failed.messages == []


def test_worker_includes_run_token_to_reject_stale_queued_signals():
    class SinglePageEngine(OCREngine):
        def recognize(self, image, language):
            return OCRResult("recognized", language, ())
    worker = worker_mod.OCRWorker(
        SinglePageEngine(), [DocumentPage(sample())], [0], "eng", run_id=29
    )
    worker.run()
    assert worker.page_ready.messages == [(29, 0, "recognized", "eng", ())]
    assert worker.progress.messages == [(29, 1, 1)]
    assert worker.finished.messages == [()]
