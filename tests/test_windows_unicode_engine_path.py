"""Real Windows Tesseract in a non-ASCII directory, with non-ASCII scratch."""
import os
import shutil
import tempfile

import pytest

from ocryon.core.ocr import TesseractEngine
from ocryon.core.qualification import sample_image


@pytest.mark.skipif(os.name != "nt", reason="Windows native path regression")
def test_real_engine_and_scratch_in_unicode_paths(tmp_path, monkeypatch):
    engine = TesseractEngine()
    if not engine.available() or not (engine.executable.parent / "tessdata" / "eng.traineddata").is_file():
        pytest.skip("Native source test needs a real Tesseract runtime")
    runtime = tmp_path / "Silnik_Zażółć_Ålesund"
    shutil.copytree(engine.executable.parent, runtime)
    scratch = tmp_path / "Tymczasowe_żółw_æøå"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    engine.executable = runtime / engine.executable.name
    result = engine.recognize(sample_image(), "eng")
    assert "123" in result.text.split()
    assert result.words
