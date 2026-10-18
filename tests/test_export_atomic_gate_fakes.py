"""Linux source-backed fake-Qt export guards; not a native Windows GUI test."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'src/ocryon/ui/main_window.py'
EXPORT_NAMES = ('export_all_txt', 'export_all_docx', 'export_all_pdf')


def extract_export_methods():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    cls = next(c for c in tree.body if isinstance(c, ast.ClassDef) and c.name == 'MainWindow')
    methods = [f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name in EXPORT_NAMES]
    assert len(methods) == len(EXPORT_NAMES)
    output = ast.Module(body=[ast.ClassDef(name='Window', bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[])
    ast.fix_missing_locations(output)
    return compile(output, str(SOURCE), 'exec')


@pytest.mark.parametrize('method', EXPORT_NAMES)
def test_queued_export_during_ocr_never_opens_dialog_or_saves(method):
    calls = []
    class Stub:
        _ocr_thread = object()
        pages = [object()]
        def statusBar(self):
            return SimpleNamespace(showMessage=lambda message: calls.append(('status', message)))
    def no_access(*args, **kwargs):
        raise AssertionError('Exported partial OCR data while worker running')
    ns = dict(
        Path=Path, recognized_pages=no_access,
        QFileDialog=SimpleNamespace(getSaveFileName=no_access),
        QMessageBox=SimpleNamespace(information=no_access,critical=no_access),
        export_txt=no_access,export_docx=no_access,export_searchable_pdf=no_access,
    )
    exec(extract_export_methods(), ns)
    subject=ns['Window']()
    subject._ocr_thread=object()
    subject.pages=[object()]
    subject.statusBar=Stub().statusBar
    getattr(subject,method)()
    assert len(calls)==1 and 'OCR' in calls[0][1]


@pytest.mark.parametrize('method', EXPORT_NAMES)
def test_ocr_started_during_save_dialog_cancels_export(method):
    calls=[]
    class Stub:
        _ocr_thread=None
        pages=[object()]
        def statusBar(self):
            return SimpleNamespace(showMessage=lambda message: calls.append(('status',message)))
    subject=Stub()
    def file_dialog(*args):
        subject._ocr_thread=object()
        calls.append(('dialog','opened'))
        return '/tmp/should-not-exist', None
    def forbidden_export(*args):
        raise AssertionError('Partial OCR data written after modal dialog')
    ns=dict(Path=Path,recognized_pages=lambda pages:pages,
            QFileDialog=SimpleNamespace(getSaveFileName=file_dialog),
            QMessageBox=SimpleNamespace(information=forbidden_export,critical=forbidden_export),
            export_txt=forbidden_export,export_docx=forbidden_export,
            export_searchable_pdf=forbidden_export)
    exec(extract_export_methods(),ns)
    for key in ('export_all_txt','export_all_docx','export_all_pdf'):
        setattr(subject,key,getattr(ns['Window'],key).__get__(subject,Stub))
    getattr(subject,method)()
    assert calls[0]==('dialog','opened')
    assert calls[-1][0]=='status' and 'cancelled' in calls[-1][1]
