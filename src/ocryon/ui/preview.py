from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel


class DocumentPreview(QLabel):
    """Fit the bounded preview to the pane while preserving aspect ratio."""
    _original: QPixmap | None = None

    def setPixmap(self, pixmap: QPixmap) -> None:
        self._original = pixmap
        self._fit()

    def _fit(self) -> None:
        if self._original is not None and not self._original.isNull():
            super().setPixmap(self._original.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()
