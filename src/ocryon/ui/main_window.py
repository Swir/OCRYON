from __future__ import annotations

from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ocryon.core.document import LoadedDocument
from ocryon.core.exporters import (
    export_docx,
    export_searchable_pdf,
    export_txt,
    recognized_pages,
)
from ocryon.core.loaders import MAX_DOCUMENT_PIXELS, load_document
from ocryon.core.ocr import TesseractEngine
from ocryon.core.preprocess import PREPROCESS_PRESET_NAMES, preprocess_options_for_preset
from ocryon.ui.ocr_worker import OCRBatchState, OCRWorker
from ocryon.ui.preview import DocumentPreview


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCRYON — Intelligent Document Recognition")
        self.resize(1380, 820)
        self.setMinimumSize(760, 440)

        self.documents: list[LoadedDocument] = []
        self.pages = []
        self.engine = TesseractEngine()

        self._ocr_run_id = 0
        self._last_ocr_indexes: tuple[int, ...] = ()
        self._ocr_thread: QThread | None = None
        self._ocr_worker: OCRWorker | None = None
        self._ocr_batch_state: OCRBatchState | None = None
        self._ocr_cancelling = False
        self._ocr_failed_run = False
        # A multi-page OCR run is a single document transaction. Cancel or
        # failure must not leave half a document newly recognized and quietly
        # eligible for PDF/DOCX/TXT export after the thread has stopped.
        self._ocr_original_pages: dict[int, tuple[str, str, object, str | None]] = {}
        self._ocr_target_indexes: set[int] = set()
        self._ocr_received_indexes: set[int] = set()
        self._close_after_ocr = False
        # Created together with the other controls in _build_ui.
        self.preprocess_profile: QComboBox | None = None
        self._updating_result = False

        self._build_ui()
        self._build_accessible_actions()
        self.statusBar().showMessage("Ready — documents stay on this computer")

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 10)
        root_layout.setSpacing(12)

        top = QFrame(objectName="topBar")
        top_layout = QVBoxLayout(top)
        header = QHBoxLayout()
        top_layout.addLayout(header)
        actions = QGridLayout()
        top_layout.addLayout(actions)

        brand_box = QVBoxLayout()
        brand = QLabel("OCRYON", objectName="brand")
        tagline = QLabel("Local-first intelligent document recognition", objectName="tagline")
        brand_box.addWidget(brand)
        brand_box.addWidget(tagline)
        header.addLayout(brand_box)
        header.addStretch(1)

        self.language = QComboBox()
        self.language.addItems(["eng", "pol", "nor", "eng+pol", "eng+nor"])
        self.language.setToolTip("OCR language")
        self.language.setAccessibleName("OCR language")
        header.addWidget(self.language)
        self.preprocess_profile = QComboBox()
        for preset in PREPROCESS_PRESET_NAMES:
            self.preprocess_profile.addItem(preset.replace("_", " ").title(), preset)
        self.preprocess_profile.setAccessibleName("Preprocessing profile")
        self.preprocess_profile.setToolTip("Choose how to prepare the scan before OCR")
        self.preprocess_profile.currentIndexChanged.connect(self._change_preprocessing)
        header.addWidget(self.preprocess_profile)

        self.open_button = QPushButton("Open document")
        self.open_button.clicked.connect(self.open_document)
        actions.addWidget(self.open_button, 0, 0)

        self.recognize_button = QPushButton("Recognize page", objectName="primary")
        self.recognize_button.clicked.connect(self.recognize_current_page)
        actions.addWidget(self.recognize_button, 0, 1)

        self.recognize_all_button = QPushButton("Recognize all")
        self.recognize_all_button.clicked.connect(self.recognize_all_pages)
        actions.addWidget(self.recognize_all_button, 0, 2)

        self.cancel_ocr_button = QPushButton("Cancel OCR")
        self.cancel_ocr_button.setToolTip("Stop the running OCR process safely")
        self.cancel_ocr_button.setEnabled(False)
        self.cancel_ocr_button.clicked.connect(self.cancel_ocr)
        actions.addWidget(self.cancel_ocr_button, 0, 3)

        export_txt_button = QPushButton("TXT")
        export_txt_button.setToolTip("Export all recognized pages as text")
        export_txt_button.clicked.connect(self.export_all_txt)
        actions.addWidget(export_txt_button, 1, 0)

        export_docx_button = QPushButton("DOCX")
        export_docx_button.setToolTip("Export all recognized pages as a Word document")
        export_docx_button.clicked.connect(self.export_all_docx)
        actions.addWidget(export_docx_button, 1, 1)

        export_pdf_button = QPushButton("Searchable PDF")
        export_pdf_button.setToolTip("Keep page images and add a searchable OCR text layer")
        export_pdf_button.clicked.connect(self.export_all_pdf)
        actions.addWidget(export_pdf_button, 1, 2)
        self.diagnostics_button = QPushButton("Diagnostics / recovery")
        self.diagnostics_button.clicked.connect(self.show_diagnostics)
        actions.addWidget(self.diagnostics_button, 1, 3)

        self._export_buttons = (export_txt_button, export_docx_button, export_pdf_button)
        root_layout.addWidget(top)

        self.ocr_progress = QProgressBar()
        self.ocr_progress.setAccessibleName("OCR progress")
        self.ocr_progress.setRange(0, 1)
        self.ocr_progress.setValue(0)
        self.ocr_progress.setTextVisible(True)
        self.ocr_progress.hide()
        root_layout.addWidget(self.ocr_progress)

        splitter = QSplitter(Qt.Horizontal)

        left = QFrame(objectName="panel")
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Pages"))
        self.page_list = QListWidget()
        self.page_list.setAccessibleName("Document pages")
        self.page_list.setMinimumWidth(120)
        self.page_list.currentRowChanged.connect(self.show_page)
        left_layout.addWidget(self.page_list)
        splitter.addWidget(left)

        preview_panel = QFrame(objectName="panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(QLabel("Document preview"))
        self.preview = DocumentPreview("Open an image or PDF to begin")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(160, 80)
        self.preview.setAccessibleName("Document preview")
        self.preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.preview)
        preview_layout.addWidget(scroll)
        splitter.addWidget(preview_panel)

        result_panel = QFrame(objectName="panel")
        result_layout = QVBoxLayout(result_panel)
        result_layout.addWidget(QLabel("Recognized text"))
        self.result = QPlainTextEdit()
        self.result.setAccessibleName("Recognized text editor")
        self.result.setTabChangesFocus(True)
        self.result.setMinimumWidth(180)
        self.result.setPlaceholderText("OCR result will appear here and remain editable.")
        self.result.textChanged.connect(self._sync_current_text)
        result_layout.addWidget(self.result)
        splitter.addWidget(result_panel)

        splitter.setSizes([260, 650, 470])
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

    def _change_preprocessing(self, _index: int) -> None:
        if self._ocr_thread is None:
            self.engine.preprocess_options = preprocess_options_for_preset(
                str(self.preprocess_profile.currentData())
            )

    def _build_accessible_actions(self) -> None:
        menu = self.menuBar().addMenu("&Document")
        self._menu_actions = []
        controls = [self.open_button, self.recognize_button, self.recognize_all_button,
                    self.cancel_ocr_button, *self._export_buttons, self.diagnostics_button]
        shortcuts = ["Ctrl+O", "F5", "Ctrl+F5", "Escape", "Ctrl+Shift+T",
                     "Ctrl+Shift+D", "Ctrl+Shift+P", "F1"]
        for button, shortcut in zip(controls, shortcuts):
            button.setAccessibleName(button.text())
            action = QAction(button.text(), self)
            action.setShortcut(QKeySequence(shortcut))
            # QPushButton.click respects disabled controls during OCR.
            action.triggered.connect(lambda _checked=False, target=button: target.click())
            menu.addAction(action)
            self._menu_actions.append(action)
            button.setToolTip(f"{button.toolTip() or button.text()} ({shortcut})")
        focus_order = [self.open_button, self.language, self.preprocess_profile,
                       *controls[1:], self.page_list, self.result]
        for first, second in zip(focus_order, focus_order[1:]):
            QWidget.setTabOrder(first, second)

    def show_diagnostics(self) -> None:
        from ocryon.ui.diagnostics import DiagnosticsDialog
        DiagnosticsDialog(self).exec()

    def open_document(self) -> None:
        if self._ocr_thread is not None:
            self.statusBar().showMessage("Wait for OCR before opening another document")
            return
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open document",
            str(Path.home()),
            "Documents and images (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)",
        )
        if not file_name:
            return

        # Cap the TOTAL decoded images retained by this window, not merely
        # each individual file. New files are rejected at metadata preflight
        # before rasterization can exhaust memory across repeated imports.
        remaining_pixels = MAX_DOCUMENT_PIXELS - sum(
            page.image.width * page.image.height for page in self.pages
        )
        try:
            document = load_document(file_name, available_pixels=remaining_pixels)
        except Exception as exc:
            QMessageBox.critical(self, "OCRYON", f"Could not open document:\n{exc}")
            return

        self.documents.append(document)
        for page in document.pages:
            self.pages.append(page)
            self.page_list.addItem(page.label)

        if self.page_list.currentRow() < 0 and self.pages:
            self.page_list.setCurrentRow(0)

        if self.pages:
            self.page_list.setFocus(Qt.OtherFocusReason)

        self.statusBar().showMessage(
            f"Loaded {document.source_path.name} — {len(document)} page(s)"
        )

    def show_page(self, row: int) -> None:
        if row < 0 or row >= len(self.pages):
            return

        page = self.pages[row]
        # Resize in Pillow BEFORE constructing ImageQt/QPixmap. A valid 24 MP
        # input otherwise creates another full-resolution RGBA Qt allocation
        # (often >100 MiB) just to immediately shrink the preview. Very tall
        # scans also need a height bound, not only a 900 px width bound.
        preview_image = page.image
        width, height = preview_image.size
        scale = min(1.0, 900 / width, 1400 / height)
        if scale < 1.0:
            preview_image = preview_image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.BILINEAR,
                reducing_gap=2.0,
            )
        qimage = ImageQt(preview_image)
        pixmap = QPixmap.fromImage(qimage)

        self.preview.setPixmap(pixmap)

        self._updating_result = True
        self.result.setPlainText(page.ocr_text)
        self._updating_result = False

    def _sync_current_text(self) -> None:
        if self._updating_result:
            return

        row = self.page_list.currentRow()
        if 0 <= row < len(self.pages):
            page = self.pages[row]
            edited_text = self.result.toPlainText()
            if edited_text != page.ocr_text:
                page.ocr_text = edited_text
                # Manual edits no longer match the original word coordinates.
                # Falling back to page-level PDF text keeps exports truthful.
                page.ocr_words = ()

    def recognize_current_page(self) -> None:
        row = self.page_list.currentRow()
        if row < 0 or row >= len(self.pages):
            QMessageBox.information(self, "OCRYON", "Open a document first.")
            return

        self._start_ocr([row])

    def recognize_all_pages(self) -> None:
        if not self.pages:
            QMessageBox.information(self, "OCRYON", "Open a document first.")
            return

        self._start_ocr(list(range(len(self.pages))))

    def _start_ocr(self, page_indexes: list[int]) -> None:
        if self._ocr_thread is not None:
            self.statusBar().showMessage("OCR is already running")
            return

        if not self.engine.available():
            QMessageBox.warning(
                self,
                "Offline OCR engine",
                "The OCR engine is not bundled in this development build yet. "
                "For development, set OCRYON_TESSERACT to tesseract.exe.",
            )
            return

        # Capture existing OCR text, language, PDF word coordinates and page
        # labels before starting. Only the selected pages are touched, and
        # immutable strings/word tuples are referenced rather than copied.
        self._ocr_target_indexes = set(page_indexes)
        self._last_ocr_indexes = tuple(page_indexes)
        self._ocr_received_indexes = set()
        self._ocr_original_pages = {}
        for index in self._ocr_target_indexes:
            page = self.pages[index]
            item = self.page_list.item(index)
            self._ocr_original_pages[index] = (
                page.ocr_text, page.ocr_language, page.ocr_words,
                item.text() if item is not None else None,
            )

        self._ocr_run_id = (self._ocr_run_id % 2_000_000_000) + 1
        self._ocr_cancelling = False
        self._ocr_failed_run = False
        self._set_ocr_controls_enabled(False)
        self.ocr_progress.setRange(0, len(page_indexes))
        self.ocr_progress.setValue(0)
        self.ocr_progress.show()
        self.statusBar().showMessage(
            f"Recognizing {len(page_indexes)} page(s) in background…"
        )

        thread = QThread(self)
        batch_state = OCRBatchState()
        worker = OCRWorker(
            self.engine,
            self.pages,
            page_indexes,
            self.language.currentText(),
            run_id=self._ocr_run_id,
            batch_state=batch_state,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.page_ready.connect(self._store_ocr_page)
        worker.progress.connect(self._update_ocr_progress)
        worker.failed.connect(self._ocr_failed)
        worker.finished.connect(thread.quit)
        # Ensure QObject is deleted only once its background thread has exited.
        # Deleting on OCRWorker.finished races with queued page-ready delivery.
        thread.finished.connect(worker.deleteLater)
        # Finalize only after QThread.wait(0) proves all thread-local cleanup
        # has completed. QThread.finished can precede that cleanup on Windows.
        # Never queue QObject deletion ahead of the final lifecycle barrier.
        thread.finished.connect(self._ocr_finished)

        self._ocr_thread = thread
        self._ocr_worker = worker
        self._ocr_batch_state = batch_state
        thread.start()

    def cancel_ocr(self) -> None:
        """Set the worker's thread-safe cancellation Event synchronously.

        Do not invoke this method by a queued signal: the worker is busy
        running OCR and may not process its Qt event loop until too late.
        """
        if self._ocr_thread is None or self._ocr_cancelling:
            return

        self._ocr_cancelling = True
        self.cancel_ocr_button.setEnabled(False)
        worker = self._ocr_worker
        if worker is not None:
            # The worker patch replaces _cancel_requested with threading.Event.
            # cancel() only sets that Event and never accesses Qt GUI objects.
            try:
                worker.cancel()
            except RuntimeError:
                # The worker QObject may already have been deleteLater()'d.
                pass
        self.statusBar().showMessage("Cancelling OCR — finishing worker cleanup…")

    def closeEvent(self, event: object) -> None:
        if self._ocr_thread is not None:
            # Never destroy a QThread while it is still active. The worker's
            # finished/quit path will cause _ocr_finished to close us later.
            event.ignore()
            self._close_after_ocr = True
            self.cancel_ocr()
            return
        super().closeEvent(event)

    def _store_ocr_page(self, run_id: int, page_index: int, text: str, language: str, words: object) -> None:
        """Commit OCR text and PDF coordinates together from one queued Qt signal."""
        if (
            self._ocr_thread is None or run_id != self._ocr_run_id
            or self._ocr_cancelling or not 0 <= page_index < len(self.pages)
        ):
            return
        try:
            coordinates = tuple(words)
        except TypeError:
            coordinates = ()

        page = self.pages[page_index]
        page.ocr_text = text
        page.ocr_language = language
        page.ocr_words = coordinates
        self._ocr_received_indexes.add(page_index)

        item = self.page_list.item(page_index)
        if item is not None:
            item.setText(f"{page.label}  ✓")

        if self.page_list.currentRow() == page_index:
            self._updating_result = True
            try:
                self.result.setPlainText(text)
            finally:
                self._updating_result = False

    def _update_ocr_progress(self, run_id: int, completed: int, total: int) -> None:
        if self._ocr_thread is None or run_id != self._ocr_run_id or self._ocr_cancelling:
            return
        self.ocr_progress.setRange(0, total)
        self.ocr_progress.setValue(completed)
        self.statusBar().showMessage(f"OCR progress — {completed}/{total} page(s)")

    def _ocr_failed(self, run_id: int, message: str) -> None:
        if self._ocr_thread is None or run_id != self._ocr_run_id or self._ocr_cancelling:
            return
        self._ocr_failed_run = True
        QMessageBox.critical(self, "OCRYON", f"OCR failed:\n{message}")
        self.statusBar().showMessage("OCR failed")

    def _ocr_finished(self, finished_thread: QThread | None = None) -> None:
        # QThread.finished is emitted BEFORE thread-local destructors finish.
        # Closing the last window or deleting its child QThread at that point
        # can trigger `QThread: Destroyed while thread is still running`.
        # wait(0) is nonblocking: postpone finalization until the REAL native
        # thread has exited, with no GUI freeze and no premature QObject delete.
        thread = finished_thread if finished_thread is not None else self.sender()
        if thread is not self._ocr_thread:
            return
        if not thread.wait(0):
            QTimer.singleShot(40, lambda t=thread: self._ocr_finished(t))
            return
        total = self.ocr_progress.maximum()
        cancelled = self._ocr_cancelling
        batch = self._ocr_batch_state
        # This independent journal is complete when QThread.finished fires.
        # Qt queued page_ready/failed callbacks are NOT guaranteed to have
        # reached the GUI before QThread.finished; they may be delivered late.
        failed = self._ocr_failed_run or (batch.failed if batch is not None else False)
        if not cancelled and not failed and batch is not None:
            for page_index, text, language, words in batch.completed:
                if page_index not in self._ocr_received_indexes:
                    self._store_ocr_page(self._ocr_run_id, page_index, text, language, words)
            self.ocr_progress.setValue(len(self._ocr_received_indexes))
        completed = self.ocr_progress.value()
        # QThread.finished is the final lifecycle barrier: roll back only now,
        # after the producer can no longer send any OCR page. A queued old
        # page_ready cannot mutate results once _ocr_thread becomes None.
        expected = self._ocr_target_indexes
        received = self._ocr_received_indexes
        incomplete = received != expected
        if cancelled or failed or incomplete:
            for index, (text, language, words, label) in self._ocr_original_pages.items():
                page = self.pages[index]
                page.ocr_text = text
                page.ocr_language = language
                page.ocr_words = words
                item = self.page_list.item(index)
                if item is not None and label is not None:
                    item.setText(label)
            row = self.page_list.currentRow()
            if row in self._ocr_original_pages:
                self._updating_result = True
                try:
                    self.result.setPlainText(self.pages[row].ocr_text)
                finally:
                    self._updating_result = False
        self._ocr_original_pages = {}
        self._ocr_target_indexes = set()
        self._ocr_received_indexes = set()
        self._ocr_thread = None
        self._ocr_worker = None
        self._ocr_batch_state = None
        # `thread.finished -> thread.deleteLater` is deliberately absent:
        # delete QThread only after wait(0) confirmed native thread teardown.
        thread.deleteLater()
        self._set_ocr_controls_enabled(True)

        if self._close_after_ocr:
            self._close_after_ocr = False
            QTimer.singleShot(0, self.close)
            return

        if cancelled:
            self.statusBar().showMessage(
                f"Recognition cancelled — {completed}/{total} processed; previous OCR restored"
            )
        elif failed:
            self.statusBar().showMessage("OCR failed — previous OCR restored")
        elif not incomplete and total:
            self.statusBar().showMessage(f"Recognition complete — {completed} page(s)")
        else:
            self.statusBar().showMessage(
                f"Recognition incomplete — {completed}/{total}; previous OCR restored"
            )

    def _set_ocr_controls_enabled(self, enabled: bool) -> None:
        self.recognize_button.setEnabled(enabled)
        self.recognize_all_button.setEnabled(enabled)
        self.language.setEnabled(enabled)
        # Do not mutate shared TesseractEngine.preprocess_options while OCRWorker
        # reads it on a background thread, including between document pages.
        if self.preprocess_profile is not None:
            self.preprocess_profile.setEnabled(enabled)
        self.cancel_ocr_button.setEnabled(not enabled and not self._ocr_cancelling)
        self.open_button.setEnabled(enabled)
        # An export while recognition is still running can silently save a
        # partially recognized document. Keep all exports and OCR edits locked
        # until worker and its QThread have actually finished.
        for button in self._export_buttons:
            button.setEnabled(enabled)
        self.result.setReadOnly(not enabled)

    def export_all_txt(self) -> None:
        # Prevent queued exports from saving incomplete recognition data.
        if self._ocr_thread is not None:
            self.statusBar().showMessage("Wait for OCR before exporting")
            return
        source_pages = tuple(self.pages)
        pages = recognized_pages(source_pages)
        if not pages:
            QMessageBox.information(self, "OCRYON", "Recognize at least one page first.")
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Export recognized document",
            str(Path.home() / "OCRYON-export.txt"),
            "Text files (*.txt)",
        )
        if not file_name:
            return
        if self._ocr_thread is not None:
            self.statusBar().showMessage("OCR started — export cancelled")
            return

        try:
            count = export_txt(source_pages, file_name)
        except Exception as exc:
            QMessageBox.critical(self, "OCRYON", f"TXT export failed:\n{exc}")
            return

        self.statusBar().showMessage(
            f"Exported {count} recognized page(s) to {Path(file_name).name}"
        )

    def export_all_docx(self) -> None:
        # Prevent queued exports from saving incomplete recognition data.
        if self._ocr_thread is not None:
            self.statusBar().showMessage("Wait for OCR before exporting")
            return
        source_pages = tuple(self.pages)
        pages = recognized_pages(source_pages)
        if not pages:
            QMessageBox.information(self, "OCRYON", "Recognize at least one page first.")
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Export recognized document",
            str(Path.home() / "OCRYON-export.docx"),
            "Word documents (*.docx)",
        )
        if not file_name:
            return
        if self._ocr_thread is not None:
            self.statusBar().showMessage("OCR started — export cancelled")
            return

        try:
            count = export_docx(source_pages, file_name)
        except Exception as exc:
            QMessageBox.critical(self, "OCRYON", f"DOCX export failed:\n{exc}")
            return

        self.statusBar().showMessage(
            f"Exported {count} recognized page(s) to {Path(file_name).name}"
        )

    def export_all_pdf(self) -> None:
        # Prevent queued exports from saving incomplete recognition data.
        if self._ocr_thread is not None:
            self.statusBar().showMessage("Wait for OCR before exporting")
            return
        source_pages = tuple(self.pages)
        pages = recognized_pages(source_pages)
        if not pages:
            QMessageBox.information(self, "OCRYON", "Recognize at least one page first.")
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Export searchable PDF",
            str(Path.home() / "OCRYON-searchable.pdf"),
            "PDF documents (*.pdf)",
        )
        if not file_name:
            return
        if self._ocr_thread is not None:
            self.statusBar().showMessage("OCR started — export cancelled")
            return

        try:
            count = export_searchable_pdf(source_pages, file_name)
        except Exception as exc:
            QMessageBox.critical(self, "OCRYON", f"PDF export failed:\n{exc}")
            return

        self.statusBar().showMessage(
            f"Exported {count} searchable page(s) to {Path(file_name).name}"
        )
