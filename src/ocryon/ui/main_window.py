from __future__ import annotations

from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ocryon.core.document import LoadedDocument
from ocryon.core.exporters import export_docx, export_txt, recognized_pages
from ocryon.core.loaders import load_document
from ocryon.core.ocr import TesseractEngine
from ocryon.ui.ocr_worker import OCRWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCRYON — Intelligent Document Recognition")
        self.resize(1380, 820)
        self.setMinimumSize(1040, 680)

        self.documents: list[LoadedDocument] = []
        self.pages = []
        self.engine = TesseractEngine()

        self._ocr_thread: QThread | None = None
        self._ocr_worker: OCRWorker | None = None
        self._updating_result = False

        self._build_ui()
        self.statusBar().showMessage("Ready — documents stay on this computer")

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 10)
        root_layout.setSpacing(12)

        top = QFrame(objectName="topBar")
        top_layout = QHBoxLayout(top)

        brand_box = QVBoxLayout()
        brand = QLabel("OCRYON", objectName="brand")
        tagline = QLabel("Local-first intelligent document recognition", objectName="tagline")
        brand_box.addWidget(brand)
        brand_box.addWidget(tagline)
        top_layout.addLayout(brand_box)
        top_layout.addStretch(1)

        self.language = QComboBox()
        self.language.addItems(["eng", "pol", "nor", "eng+pol", "eng+nor"])
        self.language.setToolTip("OCR language")
        top_layout.addWidget(self.language)

        open_button = QPushButton("Open document")
        open_button.clicked.connect(self.open_document)
        top_layout.addWidget(open_button)

        self.recognize_button = QPushButton("Recognize page", objectName="primary")
        self.recognize_button.clicked.connect(self.recognize_current_page)
        top_layout.addWidget(self.recognize_button)

        self.recognize_all_button = QPushButton("Recognize all")
        self.recognize_all_button.clicked.connect(self.recognize_all_pages)
        top_layout.addWidget(self.recognize_all_button)

        export_txt_button = QPushButton("Export TXT")
        export_txt_button.clicked.connect(self.export_all_txt)
        top_layout.addWidget(export_txt_button)

        export_docx_button = QPushButton("Export DOCX")
        export_docx_button.clicked.connect(self.export_all_docx)
        top_layout.addWidget(export_docx_button)

        root_layout.addWidget(top)

        self.ocr_progress = QProgressBar()
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
        self.page_list.currentRowChanged.connect(self.show_page)
        left_layout.addWidget(self.page_list)
        splitter.addWidget(left)

        preview_panel = QFrame(objectName="panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(QLabel("Document preview"))
        self.preview = QLabel("Open an image or PDF to begin")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(420, 520)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.preview)
        preview_layout.addWidget(scroll)
        splitter.addWidget(preview_panel)

        result_panel = QFrame(objectName="panel")
        result_layout = QVBoxLayout(result_panel)
        result_layout.addWidget(QLabel("Recognized text"))
        self.result = QPlainTextEdit()
        self.result.setPlaceholderText("OCR result will appear here and remain editable.")
        self.result.textChanged.connect(self._sync_current_text)
        result_layout.addWidget(self.result)
        splitter.addWidget(result_panel)

        splitter.setSizes([260, 650, 470])
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

    def open_document(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open document",
            str(Path.home()),
            "Documents and images (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)",
        )
        if not file_name:
            return

        try:
            document = load_document(file_name)
        except Exception as exc:
            QMessageBox.critical(self, "OCRYON", f"Could not open document:\n{exc}")
            return

        self.documents.append(document)
        for page in document.pages:
            self.pages.append(page)
            self.page_list.addItem(page.label)

        if self.page_list.currentRow() < 0 and self.pages:
            self.page_list.setCurrentRow(0)

        self.statusBar().showMessage(
            f"Loaded {document.source_path.name} — {len(document)} page(s)"
        )

    def show_page(self, row: int) -> None:
        if row < 0 or row >= len(self.pages):
            return

        page = self.pages[row]
        qimage = ImageQt(page.image)
        pixmap = QPixmap.fromImage(qimage)

        max_width = 900
        if pixmap.width() > max_width:
            pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)

        self.preview.setPixmap(pixmap)
        self.preview.resize(pixmap.size())

        self._updating_result = True
        self.result.setPlainText(page.ocr_text)
        self._updating_result = False

    def _sync_current_text(self) -> None:
        if self._updating_result:
            return

        row = self.page_list.currentRow()
        if 0 <= row < len(self.pages):
            self.pages[row].ocr_text = self.result.toPlainText()

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

        self._set_ocr_controls_enabled(False)
        self.ocr_progress.setRange(0, len(page_indexes))
        self.ocr_progress.setValue(0)
        self.ocr_progress.show()
        self.statusBar().showMessage(
            f"Recognizing {len(page_indexes)} page(s) in background…"
        )

        thread = QThread(self)
        worker = OCRWorker(
            self.engine,
            self.pages,
            page_indexes,
            self.language.currentText(),
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.page_recognized.connect(self._store_ocr_result)
        worker.progress.connect(self._update_ocr_progress)
        worker.failed.connect(self._ocr_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._ocr_finished)

        self._ocr_thread = thread
        self._ocr_worker = worker
        thread.start()

    def _store_ocr_result(self, page_index: int, text: str, language: str) -> None:
        if not 0 <= page_index < len(self.pages):
            return

        page = self.pages[page_index]
        page.ocr_text = text
        page.ocr_language = language

        item = self.page_list.item(page_index)
        if item is not None:
            item.setText(f"{page.label}  ✓")

        if self.page_list.currentRow() == page_index:
            self._updating_result = True
            self.result.setPlainText(text)
            self._updating_result = False

    def _update_ocr_progress(self, completed: int, total: int) -> None:
        self.ocr_progress.setRange(0, total)
        self.ocr_progress.setValue(completed)
        self.statusBar().showMessage(f"OCR progress — {completed}/{total} page(s)")

    def _ocr_failed(self, message: str) -> None:
        QMessageBox.critical(self, "OCRYON", f"OCR failed:\n{message}")
        self.statusBar().showMessage("OCR failed")

    def _ocr_finished(self) -> None:
        completed = self.ocr_progress.value()
        total = self.ocr_progress.maximum()
        self._ocr_thread = None
        self._ocr_worker = None
        self._set_ocr_controls_enabled(True)

        if completed == total and total:
            self.statusBar().showMessage(f"Recognition complete — {completed} page(s)")
        elif self.statusBar().currentMessage() != "OCR failed":
            self.statusBar().showMessage(
                f"Recognition stopped — {completed}/{total} page(s) completed"
            )

    def _set_ocr_controls_enabled(self, enabled: bool) -> None:
        self.recognize_button.setEnabled(enabled)
        self.recognize_all_button.setEnabled(enabled)
        self.language.setEnabled(enabled)

    def export_all_txt(self) -> None:
        pages = recognized_pages(self.pages)
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

        try:
            count = export_txt(pages, file_name)
        except Exception as exc:
            QMessageBox.critical(self, "OCRYON", f"TXT export failed:\n{exc}")
            return

        self.statusBar().showMessage(
            f"Exported {count} recognized page(s) to {Path(file_name).name}"
        )

    def export_all_docx(self) -> None:
        pages = recognized_pages(self.pages)
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

        try:
            count = export_docx(pages, file_name)
        except Exception as exc:
            QMessageBox.critical(self, "OCRYON", f"DOCX export failed:\n{exc}")
            return

        self.statusBar().showMessage(
            f"Exported {count} recognized page(s) to {Path(file_name).name}"
        )
