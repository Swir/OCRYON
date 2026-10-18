"""Non-native Qt contract check: exercise exact production main-window methods.

AST method extraction avoids claiming real PySide6 or QThread acceptance. Only
uses production function bodies, not a rewritten test double implementation.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'src/ocryon/ui/main_window.py'


def _window_methods():
    module = ast.parse(SOURCE.read_text(encoding='utf-8'))
    cls = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
    target_names = {'_store_ocr_page', '_update_ocr_progress', '_ocr_failed', '_ocr_finished'}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in target_names]
    assert {node.name for node in methods} == target_names
    output = ast.Module(body=[ast.ClassDef(
        name='ExtractedMainWindow', bases=[], keywords=[], body=methods, decorator_list=[]
    )], type_ignores=[])
    ast.fix_missing_locations(output)
    seen_popups = []
    qtimer_calls = []
    namespace = {
        'QMessageBox': SimpleNamespace(critical=lambda *args: seen_popups.append(args)),
        'QTimer': SimpleNamespace(singleShot=lambda *args: qtimer_calls.append(args)),
    }
    exec(compile(output, str(SOURCE), 'exec'), namespace)
    return namespace['ExtractedMainWindow'], seen_popups, qtimer_calls


class FakeProgress:
    def __init__(self):
        self.state = [0, 1]

    def setRange(self, low, high):
        self.state[1] = high

    def setValue(self, value):
        self.state[0] = value

    def value(self):
        return self.state[0]

    def maximum(self):
        return self.state[1]


@pytest.fixture
def ui():
    cls, popups, timer_calls = _window_methods()
    instance = cls()
    class FakeQThread:
        def __init__(self):
            self.running_cleanup = False
            self.wait_calls = []
            self.deleted = False

        def wait(self, timeout):
            self.wait_calls.append(timeout)
            return not self.running_cleanup

        def deleteLater(self):
            assert not self.running_cleanup, "QThread deleted before native teardown"
            self.deleted = True

    active = FakeQThread()
    old = FakeQThread()
    instance._ocr_run_id = 9
    instance._ocr_thread = active
    instance._ocr_worker = object()
    instance._ocr_cancelling = False
    instance._ocr_failed_run = False
    instance._ocr_batch_state = None
    instance._ocr_original_pages = {}
    instance._ocr_target_indexes = set()
    instance._ocr_received_indexes = set()
    instance._close_after_ocr = False
    instance._updating_result = False
    instance.pages = [SimpleNamespace(label='P1', ocr_text='LATEST', ocr_language='eng', ocr_words=())]
    labels = []
    texts = []
    statuses = []
    instance.page_list = SimpleNamespace(
        item=lambda index: SimpleNamespace(setText=labels.append),
        currentRow=lambda: 0,
    )
    instance.result = SimpleNamespace(setPlainText=texts.append)
    instance.ocr_progress = FakeProgress()
    instance.statusBar = lambda: SimpleNamespace(showMessage=statuses.append)
    instance.sender = lambda: active
    instance._set_ocr_controls_enabled = lambda enabled: None
    instance.close = lambda: None
    return instance, active, old, labels, texts, statuses, popups, timer_calls


def test_late_old_run_cannot_replace_new_ocr_text_coordinates_or_progress(ui):
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    instance._store_ocr_page(8, 0, 'STALE PRIVATE OCR', 'pol', ((1, 2, 3),))
    instance._update_ocr_progress(8, 1, 1)
    instance._ocr_failed(8, 'OLD FAILED')
    assert instance.pages[0].ocr_text == 'LATEST'
    assert not texts and not labels and not popups and not statuses
    assert instance.ocr_progress.state == [0, 1]


def test_current_run_writes_text_and_pdf_coordinates_atomically(ui):
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    words = ((17, 20, 42, 10),)
    instance._store_ocr_page(9, 0, 'Zażółć Ålesund', 'pol', words)
    assert instance.pages[0].ocr_text == 'Zażółć Ålesund'
    assert instance.pages[0].ocr_words == words
    assert instance.pages[0].ocr_language == 'pol'
    assert texts == ['Zażółć Ålesund']
    assert labels and '✓' in labels[0]
    instance._update_ocr_progress(9, 1, 1)
    assert instance.ocr_progress.state == [1, 1]


def test_cancelled_run_discards_even_current_queued_ocr(ui):
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    instance._ocr_cancelling = True
    instance._store_ocr_page(9, 0, 'LATE', 'eng', ((3, 4),))
    assert instance.pages[0].ocr_text == 'LATEST'
    assert not texts and not labels


def test_stale_qthread_completion_cannot_clear_new_active_thread(ui):
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    instance.sender = lambda: old
    instance._ocr_finished()
    assert instance._ocr_thread is active
    assert instance._ocr_worker is not None
    assert not statuses
    instance.sender = lambda: active
    instance._ocr_finished()
    assert instance._ocr_thread is None
    assert instance._ocr_worker is None
    assert statuses


def test_qobject_deletion_occurs_after_thread_has_finished():
    """Keep Qt's supported worker/QThread cleanup order (static, not native)."""
    parsed = ast.parse(SOURCE.read_text(encoding='utf-8'))
    cls = next(node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
    start = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_start_ocr')
    connections = [ast.unparse(call.value) for call in ast.walk(start)
                   if isinstance(call, ast.Expr) and isinstance(call.value, ast.Call)]
    assert 'thread.finished.connect(worker.deleteLater)' in connections
    assert 'thread.finished.connect(thread.deleteLater)' not in connections
    assert 'worker.finished.connect(worker.deleteLater)' not in connections
    assert 'worker.finished.connect(thread.quit)' in connections



def test_preprocessing_preset_is_locked_across_full_background_ocr_lifecycle():
    """Source-backed fake: no preset changes while shared engine runs OCR."""
    src = SOURCE.read_text(encoding='utf-8')
    tree = ast.parse(src)
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'MainWindow')
    setter = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == '_set_ocr_controls_enabled')
    generated = ast.Module(body=[ast.ClassDef(
        name='WindowControls', bases=[], keywords=[], body=[setter], decorator_list=[]
    )], type_ignores=[])
    ast.fix_missing_locations(generated)
    scope = {}
    exec(compile(generated, str(SOURCE), 'exec'), scope)
    locked = []
    class FakeButton:
        def setEnabled(self, enabled):
            locked.append(enabled)
    win = scope['WindowControls']()
    win.recognize_button = FakeButton()
    win.recognize_all_button = FakeButton()
    win.language = FakeButton()
    win.cancel_ocr_button = FakeButton()
    win.open_button = FakeButton()
    win._export_buttons = (FakeButton(), FakeButton(), FakeButton())
    win.result = SimpleNamespace(setReadOnly=lambda read_only: locked.append(('readonly', read_only)))
    win.preprocess_profile = FakeButton()
    win._ocr_cancelling = False

    win._set_ocr_controls_enabled(False)
    assert len(locked) == 10
    assert locked == [False, False, False, False, True, False, False, False, False, ('readonly', True)]
    # The application must register the *same* control it connects to the
    # shared TesseractEngine's preprocessing options.
    assert 'self.preprocess_profile.currentIndexChanged.connect(self._change_preprocessing)' in src
    locked.clear()
    win._set_ocr_controls_enabled(True)
    assert locked[3] is True
    assert locked[-1] == ('readonly', False)


def test_main_window_open_document_passes_remaining_aggregate_pixel_budget():
    """Production method's bound must reach the real loader, not just tests."""
    parsed = ast.parse(SOURCE.read_text(encoding='utf-8'))
    cls = next(x for x in parsed.body if isinstance(x, ast.ClassDef) and x.name == 'MainWindow')
    load = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == 'open_document')
    calls = [node for node in ast.walk(load)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == 'load_document']
    assert len(calls) == 1
    assert any(keyword.arg == 'available_pixels' and isinstance(keyword.value, ast.Name)
               and keyword.value.id == 'remaining_pixels'
               for keyword in calls[0].keywords)
    assert 'MAX_DOCUMENT_PIXELS' in ast.unparse(load)


def test_cancel_after_one_completed_page_restores_prior_text_pdf_boxes_and_ui(ui):
    """A partially updated batch must never become exportable on cancel."""
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    prior_words = (("PRIOR", 7, 10),)
    instance.pages[0].ocr_text = 'Original Ålesund'
    instance.pages[0].ocr_language = 'nor'
    instance.pages[0].ocr_words = prior_words
    instance._ocr_target_indexes = {0, 1}
    instance._ocr_original_pages = {
        0: ('Original Ålesund', 'nor', prior_words, 'P1  ✓'),
        1: ('', '', (), 'P2'),
    }
    instance.pages.append(SimpleNamespace(label='P2', ocr_text='', ocr_language='', ocr_words=()))
    instance._store_ocr_page(9, 0, 'NEW INCOMPLETE', 'pol', ((1, 2),))
    assert instance.pages[0].ocr_text == 'NEW INCOMPLETE'
    assert instance._ocr_received_indexes == {0}
    instance._update_ocr_progress(9, 1, 2)
    instance._ocr_cancelling = True
    instance._ocr_finished()
    assert instance.pages[0].ocr_text == 'Original Ålesund'
    assert instance.pages[0].ocr_language == 'nor'
    assert instance.pages[0].ocr_words is prior_words
    assert instance.pages[1].ocr_text == ''
    assert texts[-1] == 'Original Ålesund'
    assert labels[-2:] == ['P1  ✓', 'P2']
    assert not instance._ocr_original_pages
    assert not instance._ocr_received_indexes
    assert 'previous OCR restored' in statuses[-1]


def test_failed_ocr_restores_all_partial_pages_before_enabling_export(ui):
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    instance._ocr_target_indexes = {0}
    instance._ocr_original_pages = {0: ('LATEST', 'eng', (), 'P1')}
    instance._store_ocr_page(9, 0, 'BAD PARTIAL', 'pol', ((1,),))
    instance._ocr_failed_run = True
    # Assert rollback happens before the UI export control is enabled.
    def on_controls_enabled(enabled):
        if enabled:
            assert instance.pages[0].ocr_text == 'LATEST'
            assert instance.pages[0].ocr_words == ()
    instance._set_ocr_controls_enabled = on_controls_enabled
    instance._ocr_finished()
    assert instance.pages[0].ocr_text == 'LATEST'
    assert statuses[-1] == 'OCR failed — previous OCR restored'


def test_successful_complete_batch_keeps_unicode_words_and_exportable_text(ui):
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    instance._ocr_target_indexes = {0}
    instance._ocr_original_pages = {0: ('LATEST', 'eng', (), 'P1')}
    expected_words = (('Zażółć', 1, 2, 3),)
    instance._store_ocr_page(9, 0, 'Zażółć', 'pol', expected_words)
    instance.ocr_progress.setValue(1)
    instance._ocr_finished()
    assert instance.pages[0].ocr_text == 'Zażółć'
    assert instance.pages[0].ocr_words == expected_words
    assert 'Recognition complete' in statuses[-1]


def test_qthread_finished_reconciles_dropped_queued_pages_before_export_enabled(ui):
    """Qt finished can overtake queued page_ready; journal is authoritative."""
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    from types import SimpleNamespace
    words = (('Ålesund', 4, 6, 20),)
    instance._ocr_target_indexes = {0}
    instance._ocr_original_pages = {0: ('LATEST', 'eng', (), 'P1')}
    instance._ocr_batch_state = SimpleNamespace(completed=[(0, 'Ålesund', 'nor', words)], failed=False)
    seen_enabled = []
    def enable(enabled):
        if enabled:
            assert instance.pages[0].ocr_text == 'Ålesund'
            assert instance.pages[0].ocr_words == words
        seen_enabled.append(enabled)
    instance._set_ocr_controls_enabled = enable
    # No page_ready or progress Qt slot has run yet.
    instance._ocr_finished()
    assert instance.pages[0].ocr_text == 'Ålesund'
    assert instance.pages[0].ocr_language == 'nor'
    assert instance.ocr_progress.state == [1, 1]
    assert seen_enabled == [True]
    assert 'Recognition complete' in statuses[-1]
    assert instance._ocr_batch_state is None
    # A delayed Qt event from the terminated thread must not overwrite it.
    instance._store_ocr_page(9, 0, 'STALE', 'pol', ())
    assert instance.pages[0].ocr_text == 'Ålesund'


def test_qthread_finished_detects_worker_failure_before_queued_failed_signal(ui):
    """Failed result journal rolls back even when Qt failed() is delayed."""
    instance, active, old, labels, texts, statuses, popups, timer_calls = ui
    instance._ocr_target_indexes = {0}
    instance._ocr_original_pages = {0: ('LATEST', 'eng', (), 'P1')}
    instance._ocr_batch_state = SimpleNamespace(completed=[(0, 'PARTIAL', 'pol', ())], failed=True)
    instance._ocr_finished()
    assert instance.pages[0].ocr_text == 'LATEST'
    assert statuses[-1] == 'OCR failed — previous OCR restored'
    assert not popups  # Failure emitted on worker, but GUI callback not yet delivered.


def test_native_qthread_teardown_barrier_defers_commit_and_deletion(ui):
    """Production Qt slot: finished() is not evidence that native thread exited.

    A thread-local destructor can still be active after QThread.finished.
    This fake exercises actual production slot code, NOT native Qt acceptance.
    """
    instance, active, old, labels, texts, statuses, popups, timers = ui
    active.running_cleanup = True
    instance._ocr_target_indexes = {0}
    instance._ocr_original_pages = {0: ('LATEST', 'eng', (), 'P1')}
    instance._ocr_batch_state = SimpleNamespace(
        completed=[(0, 'Ålesund', 'nor', (('Ålesund', 1),))], failed=False
    )
    instance._close_after_ocr = True
    instance._ocr_finished()
    assert active.wait_calls == [0]
    assert instance._ocr_thread is active
    assert instance.pages[0].ocr_text == 'LATEST'
    assert not active.deleted and not statuses
    assert len(timers) == 1 and timers[0][0] == 40

    # Delayed Qt timer checks the SAME thread after its native teardown.
    active.running_cleanup = False
    timers.pop()[1]()
    assert active.wait_calls == [0, 0]
    assert active.deleted and instance._ocr_thread is None
    assert instance.pages[0].ocr_text == 'Ålesund'
    assert len(timers) == 1 and timers[0][0] == 0  # deferred close
    assert instance._close_after_ocr is False


def test_old_thread_timer_cannot_finalize_new_active_qthread(ui):
    instance, active, old, labels, texts, statuses, popups, timers = ui
    active.running_cleanup = True
    instance._ocr_finished()
    assert timers and not active.deleted
    # New run has started before a stale timer could fire. It must not clear it.
    replacement = type(active)()
    instance._ocr_thread = replacement
    timers.pop()[1]()
    assert instance._ocr_thread is replacement
    assert not replacement.deleted
