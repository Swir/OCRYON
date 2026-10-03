from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ocryon.resources import asset_path
from ocryon.ui.main_window import MainWindow
from ocryon.ui.theme import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OCRYON")
    app.setApplicationDisplayName("OCRYON")
    app.setOrganizationName("Swir")
    app.setWindowIcon(QIcon(str(asset_path("ocryon.svg"))))
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()
