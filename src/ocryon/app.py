from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ocryon.ui.main_window import MainWindow
from ocryon.ui.theme import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OCRYON")
    app.setOrganizationName("Swir")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()
