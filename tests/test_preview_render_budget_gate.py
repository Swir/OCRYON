"""Release-critical preview memory gate without claiming native PySide6 proof."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

SOURCE = Path(__file__).resolve().parents[1] / "src/ocryon/ui/main_window.py"


def _show_page():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    window = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                  and node.name == "MainWindow")
    method = next(node for node in window.body if isinstance(node, ast.FunctionDef)
                  and node.name == "show_page")
    namespace = {}
    observed = []

    class FakePixmap:
        def __init__(self, image):
            self.image = image

        def size(self):
            return self.image.size

        @staticmethod
        def fromImage(image):
            return FakePixmap(image)

    namespace.update(Image=Image, ImageQt=lambda img: observed.append(img.size) or img,
                     QPixmap=FakePixmap)
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace["show_page"], observed


def test_24mp_scan_is_shrunk_before_qt_allocation():
    show, observed = _show_page()
    # A 24 MP image is within the loader budget, but its full QPixmap would
    # consume 96 MiB+ before the old width-only resize was applied.
    source = Image.new("RGB", (6000, 4000), "white")
    preview = SimpleNamespace(setPixmap=lambda pix: None, resize=lambda size: None)
    editor = SimpleNamespace(setPlainText=lambda text: None)
    fake = SimpleNamespace(pages=[SimpleNamespace(image=source, ocr_text="OCR")],
                           preview=preview, result=editor, _updating_result=False)
    show(fake, 0)
    assert observed and observed[0][0] <= 900 and observed[0][1] <= 1400
    assert observed[0][0] * observed[0][1] < 1_300_000
    assert source.size == (6000, 4000), "GUI thumbnail must not mutate OCR source"
    assert not fake._updating_result


def test_extremely_tall_scan_has_bounded_qt_height():
    show, observed = _show_page()
    source = Image.new("RGB", (500, 48000), "white")
    preview = SimpleNamespace(setPixmap=lambda pix: None, resize=lambda size: None)
    editor = SimpleNamespace(setPlainText=lambda text: None)
    fake = SimpleNamespace(pages=[SimpleNamespace(image=source, ocr_text="")],
                           preview=preview, result=editor, _updating_result=False)
    show(fake, 0)
    assert observed[0][0] <= 900 and observed[0][1] <= 1400
    assert source.size == (500, 48000)
