"""Render the repository's original OCRYON artwork for the Windows RC."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


SOURCE = Path("src/ocryon/assets/ocryon.svg")
DESTINATION = Path("build/ocryon.png")


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise RuntimeError("OCRYON SVG icon is invalid")
    image = QImage(512, 512, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 512, 512))
    painter.end()
    DESTINATION.parent.mkdir(exist_ok=True)
    if image.isNull() or not image.save(str(DESTINATION)):
        raise RuntimeError("OCRYON release icon rendering failed")
    print("PASS: bundled OCRYON application icon")


if __name__ == "__main__":
    main()
