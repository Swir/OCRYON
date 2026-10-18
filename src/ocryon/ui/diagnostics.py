"""Local diagnostics with no document text or source paths in the report."""
from __future__ import annotations

import platform
import subprocess
import sys

from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from ocryon import __version__
from ocryon.core.ocr import TesseractEngine


def diagnostic_report(engine: TesseractEngine) -> str:
    lines = [f"OCRYON {__version__}", f"Qt {qVersion()}",
             f"System: {platform.system()} {platform.version()}",
             f"Application: {'portable / installed' if getattr(sys, 'frozen', False) else 'source'}",
             "License: GNU AGPL v3 — distributed without warranty",
             "Full source: https://github.com/Swir/OCRYON/tree/v0.2.0"]
    executable = engine.executable
    if executable is None or not executable.is_file():
        return "\n".join(lines + ["OCR engine: MISSING", "Recovery: extract the complete portable ZIP or reinstall OCRYON."])
    try:
        version = subprocess.run([str(executable), "--version"], capture_output=True,
                                 text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = executable.parent / "tessdata"
        if version.returncode:
            raise RuntimeError("Engine check failed")
        lines.append("OCR engine: " + version.stdout.splitlines()[0])
        # Upstream --list-langs fails when the Windows current directory has
        # non-ASCII characters, even though actual stdin OCR works correctly.
        # Describe this check precisely: bundled files, not OCR accuracy.
        for language in ("eng", "pol", "nor"):
            model = data / f"{language}.traineddata"
            present = model.is_file() and model.stat().st_size > 0
            lines.append(f"Language {language}: {'OK (file present)' if present else 'MISSING'}")
        lines.append("Recovery: use Retry last OCR after checking language and preprocessing settings.")
    except (OSError, RuntimeError, IndexError, subprocess.TimeoutExpired):
        lines += ["OCR engine: could not be started", "Recovery: extract the complete ZIP or reinstall OCRYON."]
    lines.append("This report contains no document text or document paths.")
    return "\n".join(lines)


class DiagnosticsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle("OCRYON — Diagnostics and recovery")
        self.resize(620, 430)
        layout = QVBoxLayout(self)
        heading = QLabel("Check the offline engine and recover from an interrupted OCR run.")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setAccessibleName("Diagnostics report")
        layout.addWidget(self.report)
        refresh = QPushButton("&Refresh engine checks")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        self.retry = QPushButton("&Retry last OCR")
        self.retry.setEnabled(bool(window._last_ocr_indexes) and window._ocr_thread is None)
        self.retry.clicked.connect(self.retry_ocr)
        layout.addWidget(self.retry)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.refresh()

    def refresh(self):
        window = self.parent()
        # Never replace the engine while a worker is reading it.
        engine = TesseractEngine(window.engine.preprocess_options)
        if window._ocr_thread is None:
            window.engine = engine
        self.report.setPlainText(diagnostic_report(engine))

    def retry_ocr(self):
        window = self.parent()
        self.accept()
        window._start_ocr(list(window._last_ocr_indexes))
