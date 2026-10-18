"""Real OCRWorker production-method execution without pretending PySide6 is installed."""
from __future__ import annotations

import ast
from pathlib import Path
from threading import Event
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / 'src/ocryon/ui/ocr_worker.py'


def _worker_methods():
    source_tree = ast.parse(SOURCE.read_text('utf-8'))
    production = next(n for n in source_tree.body if isinstance(n, ast.ClassDef) and n.name == 'OCRWorker')
    names = {'__init__', 'cancel', 'run'}
    selected = [n for n in production.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for method in selected:
        # @Slot() is Qt metadata. Exercise the same method body without Qt.
        method.decorator_list = []
    class_node = ast.ClassDef(name='FakeQtWorker', bases=[], keywords=[], body=selected, decorator_list=[])
    tree = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(tree)
    class TesseractEngine:
        pass
    class OCRCancelled(Exception):
        pass
    class OCRDeadlineExceeded(Exception):
        pass
    namespace = {
        'Event': Event,
        'TesseractEngine': TesseractEngine,
        'OCRCancelled': OCRCancelled,
        'OCRDeadlineExceeded': OCRDeadlineExceeded,
        'preprocess_options_for_preset': lambda _x: None,
        'recognize_cancellable': lambda *_: None,
    }
    exec(compile(tree, str(SOURCE), 'exec'), namespace)
    return namespace['FakeQtWorker']


class Emissions:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


def _worker(engine):
    cls = _worker_methods()
    state = SimpleNamespace(completed=[], failed=False)
    pages = [SimpleNamespace(image='image')]
    worker = cls(engine, pages, [0], 'nor', run_id=27, batch_state=state)
    worker.page_ready = Emissions()
    worker.progress = Emissions()
    worker.failed = Emissions()
    worker.finished = Emissions()
    return worker, state


def test_worker_journals_success_before_any_qt_signal_delivery():
    class Engine:
        def recognize(self, *_):
            return SimpleNamespace(text='Zażółć Ålesund', language='nor', words=(('Å', 1),))
    worker, state = _worker(Engine())
    worker.run()
    assert state.completed == [(0, 'Zażółć Ålesund', 'nor', (('Å', 1),))]
    assert state.failed is False
    assert worker.page_ready.calls and worker.finished.calls == [()]


def test_worker_records_failure_without_exposing_private_path_in_signal():
    class Engine:
        def recognize(self, *_):
            raise ValueError('/private/document/sekret.pdf')
    worker, state = _worker(Engine())
    worker.run()
    assert state.failed is True
    assert state.completed == []
    assert worker.failed.calls == [(27, 'Offline OCR failed')]
    assert worker.finished.calls == [()]


def test_worker_cancelled_result_never_enters_commit_journal():
    class Engine:
        def recognize(self, *_):
            worker.cancel()
            return SimpleNamespace(text='PRIVATE', language='nor', words=())
    worker, state = _worker(Engine())
    worker.run()
    assert state.completed == []
    assert state.failed is False
    assert worker.page_ready.calls == []
    assert worker.finished.calls == [()]
