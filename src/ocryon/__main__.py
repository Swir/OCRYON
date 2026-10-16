"""Keep the frozen qualification path independent of Qt initialization."""
from __future__ import annotations

import sys


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        # A windowed PyInstaller process may lack stdout. Importing app here
        # would load Qt before we could inspect the bundled OCR engine.
        from ocryon.core.qualification import run_selftest

        return run_selftest()

    if sys.argv[1:] == ["--self-test-unicode"]:
        # Execute the full real bundled-OCR -> PDF/TXT/DOCX round trip inside
        # the actual frozen executable, not only in Python source tests.
        from ocryon.core.unicode_qualification import run_unicode_selftest

        return run_unicode_selftest()

    if sys.argv[1:] == ["--self-test-qt"]:
        # Execute actual frozen PySide6/QThread cancellation, not a GUI
        # startup-only smoke or a source-only Qt test.
        from ocryon.ui.qt_qualification import run_qt_selftest

        return run_qt_selftest()

    from ocryon.app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
