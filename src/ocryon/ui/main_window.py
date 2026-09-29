from __future__ import annotations

from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt
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
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ocryon.core.document import LoadedDocument
from ocryon.core.loaders import load_document
from ocryon.core.ocr import TesseractEngine


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCRYON — Intelligent Document Recognition")
        self.resize(1380, 820)
        self.setMinimumSize(1040, 680)

        self.documents: list[LoadedDocument] = []
        self.pages = []
        self.engine = TesseractEngine()

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

        recognize_button = QPushButton("Recognize", objectName="primary")
        recognize_button.clicked.connect(self.recognize_current_page)
        top_layout.addWidget(recognize_button)

        save_button = QPushButton("Save TXT")
        save_button.clicked.connect(self.save_text)
        top_layout.addWidget(save_button)

        root_layout.addWidget(top)

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

        image = self.pages[row].image
        qimage = ImageQt(image)
        pixmap = QPixmap.fromImage(qimage)

        max_width = 900
        if pixmap.width() > max_width:
            pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)

        self.preview.setPixmap(pixmap)
        self.preview.resize(pixmap.size())

    def recognize_current_page(self) -> None:
        row = self.page_list.currentRow()
        if row < 0 or row >= len(self.pages):
            QMessageBox.information(self, "OCRYON", "Open a document first.")
            return

        if not self.engine.available():
            QMessageBox.warning(
                self,
                "Offline OCR engine",
                "The OCR engine is not bundled in this development build yet. "
                "For development, set OCRYON_TESSERACT to tesseract.exe.",
            )
            return

        self.statusBar().showMessage("Recognizing current page…")
        try:
            result = self.engine.recognize(
                self.pages[row].image,
                self.language.currentText(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "OCRYON", f"OCR failed:\n{exc}")
            self.statusBar().showMessage("OCR failed")
            return

        self.result.setPlainText(result.text)
        self.statusBar().showMessage(
            f"Recognition complete — language: {result.language}"
        )

    def save_text(self) -> None:
        text = self.result.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "OCRYON", "There is no recognized text to save.")
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save recognized text",
            str(Path.home() / "OCRYON.txt"),
            "Text files (*.txt)",
        )
        if not file_name:
            return

        Path(file_name).write_text(text, encoding="utf-8")
        self.statusBar().showMessage(f"Saved {Path(file_name).name}")
