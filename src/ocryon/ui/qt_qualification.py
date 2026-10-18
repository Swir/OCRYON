"""Actual native PySide6/QThread/cancel/deferred-close release gate.

The SAME implementation is invoked from installed/frozen OCRYON.exe and from
source-level acceptance on Windows. No mocks; a real Tesseract child is spawned
and observed before cancellation. The CLI reports only pass/fail, not paths.
"""
from __future__ import annotations

import os
import sys
import time

def check_qt_lifecycle() -> None:
    """Run actual Qt/QThread worker lifecycle, not AST mocks."""
    if os.name != "nt":
        raise AssertionError("Native Qt acceptance requires Windows")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from pathlib import Path
    from PIL import Image
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    from ocryon.core.document import DocumentPage
    from ocryon.core.qualification import sample_image
    from ocryon.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()  # Even offscreen, closeEvent must operate on a visible widget.
    app.processEvents()
    if not window.engine.available() or (
        getattr(sys, "frozen", False) and not window.engine.uses_bundled_engine()
    ):
        raise AssertionError("Windows Qt acceptance missing native Tesseract engine")
    sample = sample_image()
    window.pages = [DocumentPage(Path("OCRYON_sample.png"), 1, sample)]
    window.page_list.addItem(window.pages[0].label)
    window.page_list.setCurrentRow(0)
    window._start_ocr([0])
    if window._ocr_thread is None:
        raise AssertionError("QThread was never created")
    deadline = time.monotonic() + 80
    while window._ocr_thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    if window._ocr_thread is not None or not window.pages[0].has_ocr:
        raise AssertionError("Native Qt/QThread OCR failed to finish and return text")
    app.processEvents()

    # This must prove cancellation of an *already spawned* real Tesseract
    # subprocess. Cancelling before QThread starts can appear to pass while
    # never exercising Windows process cleanup, and must not qualify an RC.
    from threading import Event
    from ocryon.core import cancellable_tesseract

    original_subprocess = cancellable_tesseract.subprocess
    child_spawned = Event()
    release_spawn = Event()
    spawned_children = []

    class ObservedSubprocess:
        """Intercept only this OCR module, not global subprocess.Popen.

        Pause the worker immediately after the real Windows child starts so
        the GUI can request cancellation while that process is still alive.
        The worker then uses the unmodified production kill-and-reap logic.
        """

        def __getattr__(self, name):
            return getattr(original_subprocess, name)

        def Popen(self, *args, **kwargs):
            child = original_subprocess.Popen(*args, **kwargs)
            spawned_children.append(child)
            child_spawned.set()
            if not release_spawn.wait(10):
                child.kill()
                child.wait(timeout=3)
                raise AssertionError("Native OCR spawn barrier timed out")
            return child

    # A larger image keeps Tesseract alive long enough to prove that the
    # observed process is still running, rather than race a tiny OCR sample.
    window.pages[0].image = sample.resize(
        (sample.width * 5, sample.height * 5), Image.Resampling.NEAREST
    )
    cancellable_tesseract.subprocess = ObservedSubprocess()
    try:
        window._start_ocr([0])
        if window._ocr_thread is None:
            raise AssertionError("Second native Qt OCR did not start")
        active_worker = window._ocr_worker
        deadline = time.monotonic() + 40
        while not child_spawned.is_set() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        if not child_spawned.is_set():
            raise AssertionError("Native Qt OCR never launched real Tesseract")
        child = spawned_children[0]
        if child.poll() is not None:
            raise AssertionError("Tesseract finished before in-flight cancel proof")
        window.cancel_ocr()
        if (not window._ocr_cancelling or active_worker is None
                or not active_worker._cancel_requested.is_set()):
            raise AssertionError("Native Qt did not set worker cancellation Event")
        window.close()  # must defer destruction while QThread is active
        release_spawn.set()
        deadline = time.monotonic() + 20
        while window._ocr_thread is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        for _ in range(10):
            app.processEvents()
            time.sleep(0.01)
        if window._ocr_thread is not None or window.isVisible():
            raise AssertionError("Native Qt cancellation/deferred close failed")
        if child.poll() is None:
            raise AssertionError("Native Windows cancellation left Tesseract running")
    finally:
        release_spawn.set()
        cancellable_tesseract.subprocess = original_subprocess
        if window._ocr_thread is not None:
            window.cancel_ocr()
            deadline = time.monotonic() + 5
            while window._ocr_thread is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
        for child in spawned_children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)

    QCoreApplication.sendPostedEvents()
    app.processEvents()
    print("PASS: native PySide6 OCR QThread, cancellation and deferred close")


def run_qt_selftest() -> int:
    """Frozen GUI gate: 0=real native Qt/worker PASS, 26=missing evidence."""
    from ocryon.core.qualification import _report_selftest_status, _report_selftest_failure

    try:
        check_qt_lifecycle()
    except Exception:
        _report_selftest_failure()
        # A Windows --windowed EXE may have no stdout/stderr. Never leak
        # private OCR text, source paths, or system environment via a traceback.
        _report_selftest_status("OCRYON QT SELFTEST FAIL")
        return 26
    _report_selftest_status("OCRYON QT SELFTEST PASS")
    return 0
