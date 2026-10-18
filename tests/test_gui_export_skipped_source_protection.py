"""Exercise real GUI export method bodies against real exporters without PySide6.

This is source-method integration, NOT native Qt/Windows acceptance.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from docx import Document as WordDocument
from PIL import Image

from ocryon.core.document import DocumentPage
from ocryon.core.exporters import export_txt, export_docx, export_searchable_pdf, recognized_pages

SOURCE = Path(__file__).resolve().parents[1] / "src/ocryon/ui/main_window.py"


def _window_export(method_name: str, destination: Path):
    """Compile production method (not a replicated algorithm) with dialog fakes."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    node = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "MainWindow")
    method = next(x for x in node.body if isinstance(x, ast.FunctionDef) and x.name == method_name)
    module = ast.Module(body=[ast.ClassDef(name="ExactGuiExport", bases=[], keywords=[], body=[method], decorator_list=[])], type_ignores=[])
    ast.fix_missing_locations(module)
    prompts = []
    ns = {
        "Path": Path,
        "recognized_pages": recognized_pages,
        "export_txt": export_txt,
        "export_docx": export_docx,
        "export_searchable_pdf": export_searchable_pdf,
        "QFileDialog": SimpleNamespace(getSaveFileName=lambda *args: (str(destination), "")),
        "QMessageBox": SimpleNamespace(
            information=lambda *args: prompts.append(("info", args)),
            critical=lambda *args: prompts.append(("critical", args)),
        ),
    }
    exec(compile(module, str(SOURCE), "exec"), ns)
    window = ns["ExactGuiExport"]()
    window._ocr_thread = None
    window.statusBar = lambda: SimpleNamespace(showMessage=lambda *_: None)
    return window, prompts


def _original(path: Path):
    if path.suffix == ".pdf":
        with fitz.open() as doc:
            page = doc.new_page(width=220, height=320)
            page.insert_text((40, 60), "PRIVATE ORIGINAL")
            doc.set_metadata({"title": "Unrecognized private document"})
            doc.save(path)
    elif path.suffix == ".docx":
        doc = WordDocument()
        doc.add_paragraph("PRIVATE ORIGINAL")
        doc.save(path)
    else:
        path.write_text("PRIVATE ORIGINAL\n", encoding="utf-8")


def _pages(original: Path):
    b = original.parent / "other.png"
    b.write_bytes(b"unchanged")
    return [
        DocumentPage(source_path=original, page_number=1, image=Image.new("RGB", (240, 360), "white"), ocr_text=""),
        DocumentPage(source_path=b, page_number=1, image=Image.new("RGB", (240, 360), "white"), ocr_text="OCRYON TEST"),
    ]


@pytest.mark.parametrize("method,suffix", [
    ("export_all_pdf", ".pdf"),
    ("export_all_txt", ".txt"),
    ("export_all_docx", ".docx"),
])
def test_gui_export_cannot_overwrite_unrecognized_original(tmp_path, method, suffix):
    original = tmp_path / ("private" + suffix)
    _original(original)
    before = original.read_bytes()
    window, prompts = _window_export(method, original)
    window.pages = _pages(original)
    getattr(window, method)()
    assert original.read_bytes() == before, "GUI passed filtered pages and destroyed an original OCR source"
    assert prompts and prompts[-1][0] == "critical", "Save to a loaded original must be rejected"


def test_gui_export_cannot_overwrite_unrecognized_source_hardlink(tmp_path):
    original = tmp_path / "private.pdf"
    _original(original)
    alias = tmp_path / "alias.pdf"
    try:
        os.link(original, alias)
    except OSError:
        pytest.skip("Hardlinks unsupported")
    before = original.read_bytes()
    window, prompts = _window_export("export_all_pdf", alias)
    window.pages = _pages(original)
    window.export_all_pdf()
    assert original.read_bytes() == before
    assert alias.read_bytes() == before
    assert original.samefile(alias)
    assert prompts and prompts[-1][0] == "critical"


def test_gui_export_to_separate_destination_still_works(tmp_path):
    original = tmp_path / "private.pdf"
    _original(original)
    before = original.read_bytes()
    output = tmp_path / "ocr.pdf"
    window, prompts = _window_export("export_all_pdf", output)
    window.pages = _pages(original)
    window.export_all_pdf()
    assert not prompts
    assert original.read_bytes() == before
    with fitz.open(output) as result:
        assert len(result) == 1
        assert "OCRYON TEST" in result[0].get_text()
