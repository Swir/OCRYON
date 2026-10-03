from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QFrame

from ocryon.core.preprocess import PREPROCESS_PRESET_NAMES, preprocess_options_for_preset
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

    preprocess_profile = QComboBox(window)
    for preset in PREPROCESS_PRESET_NAMES:
        preprocess_profile.addItem(preset.replace("_", " ").title(), preset)
    preprocess_profile.setToolTip("Preprocessing profile")
    preprocess_profile.currentIndexChanged.connect(
        lambda _index: setattr(
            window.engine,
            "preprocess_options",
            preprocess_options_for_preset(str(preprocess_profile.currentData())),
        )
    )
    top_bar = window.findChild(QFrame, "topBar")
    if top_bar is not None and top_bar.layout() is not None:
        top_bar.layout().addWidget(preprocess_profile)

    window.show()
    return app.exec()
