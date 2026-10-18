from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from ocryon.core.cancellable_tesseract import (
    OCRCancelled, OCRDeadlineExceeded, recognize_cancellable,
)
from ocryon.core.document import DocumentPage
from ocryon.core.ocr import OCREngine, TesseractEngine
from ocryon.core.preprocess import preprocess_options_for_preset


@dataclass
class OCRBatchState:
    """Pure-Python commit journal, finalized before QThread.finished.

    Queued Qt page_ready/failed callbacks may arrive AFTER QThread.finished.
    This journal is owned by the window, independent of worker QObject
    deleteLater; the GUI reads it only when the QThread has terminated.
    """

    completed: list[tuple[int, str, str, tuple]] = field(default_factory=list)
    failed: bool = False


class OCRWorker(QObject):
    """Background OCR; cancellation is synchronous and thread-safe.

    Signals are emitted from the worker thread and delivered to the GUI by Qt.
    A cancelled run never delivers a late page or a failure dialog.
    """

    page_ready = Signal(int, int, str, str, object)
    progress = Signal(int, int, int)
    failed = Signal(int, str)
    finished = Signal()

    def __init__(
        self,
        engine: OCREngine,
        pages: Sequence[DocumentPage],
        page_indexes: Sequence[int],
        language: str,
        preprocess_preset: str | None = None,
        run_id: int = 0,
        batch_state: OCRBatchState | None = None,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._pages = pages
        self._page_indexes = list(page_indexes)
        self._language = language
        self._run_id = run_id
        self._batch_state = batch_state
        if preprocess_preset is not None:
            if not isinstance(engine, TesseractEngine):
                raise TypeError("preprocess_preset requires TesseractEngine")
            engine.preprocess_options = preprocess_options_for_preset(preprocess_preset)
        self._cancel_requested = Event()

    def cancel(self) -> None:
        """May be called directly from GUI thread while worker.run() is busy."""
        self._cancel_requested.set()

    @Slot()
    def run(self) -> None:
        total = len(self._page_indexes)
        try:
            for position, page_index in enumerate(self._page_indexes, start=1):
                if self._cancel_requested.is_set():
                    break
                page = self._pages[page_index]
                if isinstance(self._engine, TesseractEngine):
                    result = recognize_cancellable(
                        self._engine, page.image, self._language,
                        self._cancel_requested,
                    )
                else:
                    result = self._engine.recognize(page.image, self._language)
                if self._cancel_requested.is_set():
                    break
                if self._batch_state is not None:
                    self._batch_state.completed.append(
                        (page_index, result.text, result.language, tuple(result.words))
                    )
                self.page_ready.emit(self._run_id, page_index, result.text, result.language, result.words)
                self.progress.emit(self._run_id, position, total)
        except OCRCancelled:
            pass
        except OCRDeadlineExceeded:
            if not self._cancel_requested.is_set():
                if self._batch_state is not None:
                    self._batch_state.failed = True
                self.failed.emit(self._run_id, "Offline OCR timed out")
        except Exception:
            # Do not leak extracted private document text/paths from exceptions.
            if not self._cancel_requested.is_set():
                if self._batch_state is not None:
                    self._batch_state.failed = True
                self.failed.emit(self._run_id, "Offline OCR failed")
        finally:
            self.finished.emit()
