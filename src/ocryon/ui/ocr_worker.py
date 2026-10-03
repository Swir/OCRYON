from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QObject, Signal, Slot

from ocryon.core.document import DocumentPage
from ocryon.core.ocr import OCREngine, TesseractEngine
from ocryon.core.preprocess import preprocess_options_for_preset


class OCRWorker(QObject):
    """Run OCR outside the GUI thread.

    The worker is deliberately UI-agnostic: it receives document pages and
    emits page indexes plus recognized text and optional structured layout.
    """

    page_recognized = Signal(int, str, str)
    layout_recognized = Signal(int, object)
    progress = Signal(int, int)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        engine: OCREngine,
        pages: Sequence[DocumentPage],
        page_indexes: Sequence[int],
        language: str,
        preprocess_preset: str | None = None,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._pages = pages
        self._page_indexes = list(page_indexes)
        self._language = language
        if preprocess_preset is not None:
            if not isinstance(engine, TesseractEngine):
                raise TypeError("preprocess_preset requires TesseractEngine")
            engine.preprocess_options = preprocess_options_for_preset(preprocess_preset)
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    @Slot()
    def run(self) -> None:
        total = len(self._page_indexes)
        try:
            for position, page_index in enumerate(self._page_indexes, start=1):
                if self._cancel_requested:
                    break

                page = self._pages[page_index]
                result = self._engine.recognize(page.image, self._language)
                self.page_recognized.emit(page_index, result.text, result.language)
                self.layout_recognized.emit(page_index, result.words)
                self.progress.emit(position, total)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
