"""Native Qt checks for keyboard use, layout and diagnostics/retry."""
from __future__ import annotations

import os
from pathlib import Path
import time


def check_ui() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAccessible
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from ocryon.core.document import DocumentPage
    from ocryon.core.qualification import sample_image
    from ocryon.ui.diagnostics import DiagnosticsDialog, diagnostic_report
    from ocryon.ui.main_window import MainWindow
    from ocryon.ui.theme import APP_STYLESHEET

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    window.resize(940, 480)
    window.show()
    app.processEvents()
    controls = [window.open_button, window.recognize_button, window.recognize_all_button,
                window.cancel_ocr_button, *window._export_buttons, window.diagnostics_button,
                window.language, window.preprocess_profile, window.page_list, window.result]
    for control in controls:
        interface = QAccessible.queryAccessibleInterface(control)
        if interface is None or not interface.text(QAccessible.Name):
            raise AssertionError("Control has no accessible name")
        if not control.isVisible() or control.width() <= 0 or control.height() <= 0:
            raise AssertionError("Control is not visible")
        top_left = control.mapTo(window, control.rect().topLeft())
        bottom_right = control.mapTo(window, control.rect().bottomRight())
        if not window.rect().contains(top_left) or not window.rect().contains(bottom_right):
            raise AssertionError(f"Control is clipped: {control.accessibleName()}")
    window.language.setFocus()
    QTest.keyClick(window.language, Qt.Key_Tab)
    # Inspect this window's focus chain even if Windows keeps another app in
    # the foreground. Qualification must not depend on stealing user focus.
    if window.focusWidget() is not window.preprocess_profile:
        raise AssertionError("Keyboard tab order is broken")
    if len({action.shortcut().toString() for action in window._menu_actions}) != 8:
        raise AssertionError("Keyboard shortcuts missing or ambiguous")

    image = sample_image()
    window.pages = [DocumentPage(Path("synthetic-sample.png"), 1, image)]
    window.page_list.addItem(window.pages[0].label)
    window.page_list.setCurrentRow(0)
    window._last_ocr_indexes = (0,)
    dialog = DiagnosticsDialog(window)
    if not all(f"Language {code}: OK" in dialog.report.toPlainText() for code in ("eng", "pol", "nor")):
        raise AssertionError("Diagnostics does not detect bundled languages")
    if "synthetic-sample" in dialog.report.toPlainText():
        raise AssertionError("Diagnostics exposes document data")
    dialog.retry_ocr()
    if window.preprocess_profile.isEnabled() or not window.result.isReadOnly():
        raise AssertionError("OCR controls are not protected during retry")
    deadline = time.monotonic() + 30
    while window._ocr_thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    if window._ocr_thread is not None or not window.pages[0].has_ocr:
        raise AssertionError("Recovery retry did not finish real OCR")
    if not window.preprocess_profile.isEnabled() or window.result.isReadOnly():
        raise AssertionError("OCR controls did not unlock")
    previous = window.engine.executable
    try:
        window.engine.executable = None
        if "Recovery:" not in diagnostic_report(window.engine):
            raise AssertionError("Missing runtime has no recovery guidance")
    finally:
        window.engine.executable = previous
    check_document_workflow(window, app)
    screenshot = os.environ.get("OCRYON_UI_SCREENSHOT")
    if screenshot and not window.grab().save(screenshot):
        raise AssertionError("Screenshot could not be saved")
    window.close()
    app.processEvents()


def check_document_workflow(window, app) -> None:
    """Real import -> batch worker -> edit -> three GUI exports.

    Only the file chooser answers and message-box presentation are supplied
    by the harness. Loaders, widgets, OCR processes and exporters are real.
    """
    import hashlib
    import io
    import tempfile
    import pymupdf
    from docx import Document
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from ocryon.core.qualification import sample_image

    original_open = QFileDialog.getOpenFileName
    original_save = QFileDialog.getSaveFileName
    original_critical = QMessageBox.critical
    errors = []
    with tempfile.TemporaryDirectory(prefix="OCRYON_workflow_") as temporary:
        root = Path(temporary) / "Zażółć_Ålesund"
        root.mkdir()
        png = root / "scan.png"
        source_pdf = root / "two-pages.pdf"
        sample = sample_image()
        sample.save(png)
        data = io.BytesIO()
        sample.save(data, format="PNG")
        with pymupdf.open() as document:
            for _ in range(2):
                page = document.new_page(width=650, height=160)
                page.insert_image(page.rect, stream=data.getvalue())
            document.save(source_pdf)
        originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (png, source_pdf)}
        window.pages.clear()
        window.documents.clear()
        window.page_list.clear()
        try:
            QMessageBox.critical = lambda *args: errors.append(str(args[-1]))
            for source in (png, source_pdf):
                QFileDialog.getOpenFileName = lambda *args, path=source: (str(path), "")
                QTest.mouseClick(window.open_button, Qt.LeftButton)
                app.processEvents()
            if errors or len(window.pages) != 3 or window.preview.pixmap().isNull():
                raise AssertionError("Native GUI image/PDF import failed")
            QTest.mouseClick(window.recognize_all_button, Qt.LeftButton)
            deadline = time.monotonic() + 60
            while window._ocr_thread is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            if window._ocr_thread is not None or errors or any("123" not in p.ocr_text for p in window.pages):
                raise AssertionError("Native GUI batch OCR failed")
            window.page_list.setCurrentRow(0)
            window.result.selectAll()
            QTest.keyClicks(window.result, "Edited OCRYON 123")
            app.processEvents()
            if window.pages[0].ocr_text != "Edited OCRYON 123" or window.pages[0].ocr_words:
                raise AssertionError("Native editor did not invalidate stale coordinates")
            for button, suffix in zip(window._export_buttons, ("txt", "docx", "pdf")):
                destination = root / ("result." + suffix)
                QFileDialog.getSaveFileName = lambda *args, path=destination: (str(path), "")
                QTest.mouseClick(button, Qt.LeftButton)
                app.processEvents()
                if errors or not destination.is_file():
                    raise AssertionError("Native GUI export failed")
            if "Edited OCRYON 123" not in (root / "result.txt").read_text(encoding="utf-8"):
                raise AssertionError("GUI TXT lost manual edits")
            if "Edited OCRYON 123" not in " ".join(p.text for p in Document(root / "result.docx").paragraphs):
                raise AssertionError("GUI DOCX lost manual edits")
            with pymupdf.open(root / "result.pdf") as result:
                if len(result) != 3 or not result[0].search_for("Edited OCRYON 123"):
                    raise AssertionError("GUI PDF lost searchable edited text")
                if abs(result[1].rect.width - 650) > 0.1 or abs(result[1].rect.height - 160) > 0.1:
                    raise AssertionError("GUI PDF lost original physical dimensions")
            QFileDialog.getSaveFileName = lambda *args: (str(source_pdf), "")
            QTest.mouseClick(window._export_buttons[2], Qt.LeftButton)
            app.processEvents()
            if not errors or any(hashlib.sha256(p.read_bytes()).hexdigest() != digest for p, digest in originals.items()):
                raise AssertionError("GUI export did not protect original files")
            window.statusBar().showMessage("Verified: image/PDF import, batch OCR, editing and TXT/DOCX/PDF export")
        finally:
            QFileDialog.getOpenFileName = original_open
            QFileDialog.getSaveFileName = original_save
            QMessageBox.critical = original_critical


def run_ui_selftest() -> int:
    from ocryon.core.qualification import _report_selftest_status, _report_selftest_failure
    try:
        check_ui()
    except Exception:
        _report_selftest_failure()
        _report_selftest_status("OCRYON UI SELFTEST FAIL")
        return 27
    _report_selftest_status("OCRYON UI SELFTEST PASS: accessibility, diagnostics, import, batch OCR, editing and exports")
    return 0
