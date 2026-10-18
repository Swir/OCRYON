"""Release-critical OCR output limits: source-backed code, no Qt simulation."""
from pathlib import Path
from threading import Event
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from ocryon.core import cancellable_tesseract as engine


_TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def _tsv_words(words):
    return _TSV_HEADER + "".join(
        f"5\t1\t1\t1\t1\t{i+1}\t0\t0\t10\t10\t98\t{word}\n"
        for i, word in enumerate(words)
    )


def test_tsv_words_bounded_before_python_word_allocation(monkeypatch):
    monkeypatch.setattr(engine, "_MAX_OCR_WORDS", 3)
    source = _tsv_words(["a", "b", "c", "PRIVATE"])
    with pytest.raises(RuntimeError, match="safe size limit") as err:
        engine._parse_tsv(source, prepared_size=(50, 50), strict=True)
    assert "PRIVATE" not in str(err.value)


def test_tsv_unicode_character_cap_fails_closed_without_leaking(monkeypatch):
    monkeypatch.setattr(engine, "_MAX_OCR_CHARACTERS", 5)
    source = _tsv_words(["Żółw", "Ålesund"])
    with pytest.raises(RuntimeError, match="safe size limit") as err:
        engine._parse_tsv(source, prepared_size=(50, 50), strict=True)
    assert "Ålesund" not in str(err.value)


def test_tsv_unicode_words_below_cap_preserve_text(monkeypatch):
    monkeypatch.setattr(engine, "_MAX_OCR_CHARACTERS", 30)
    rows = engine._parse_tsv(
        _tsv_words(["Zażółć", "Ålesund"]), prepared_size=(50, 50), strict=True
    )
    assert rows["text"] == ["Zażółć", "Ålesund"]


def test_real_plain_text_tesseract_output_has_same_character_limit(monkeypatch, tmp_path):
    (tmp_path / "fake.png").write_bytes(b"synthetic")
    monkeypatch.setattr(engine, "_MAX_OCR_CHARACTERS", 10)
    original = subprocess.Popen
    def real_child(*_args, **_kwargs):
        return original([sys.executable, "-X", "utf8", "-c", "print('Zażółć' * 10)"],
                        stdout=_kwargs["stdout"], stderr=_kwargs["stderr"],
                        stdin=_kwargs["stdin"], env=_kwargs["env"],
                        start_new_session=_kwargs["start_new_session"])
    monkeypatch.setattr(engine.subprocess, "Popen", real_child)
    with pytest.raises(RuntimeError, match="safe size limit"):
        engine._run_tesseract(Path(sys.executable), tmp_path / "fake.png",
                              "pol", "txt", Event(), time.monotonic() + 5)


def test_tsv_open_quote_must_not_swallow_next_word_and_pdf_layer():
    # Tesseract emits quotes as plain text. Default csv.DictReader quoting
    # erroneously merged the second complete TSV row into the first text.
    rows = engine._parse_tsv(
        _tsv_words(['"Zażółć', 'Ålesund']),
        prepared_size=(50, 50), strict=True,
    )
    assert rows["text"] == ['"Zażółć', 'Ålesund']
    assert len(rows["left"]) == 2


def test_tsv_extra_tab_never_silently_truncates_a_recognized_word():
    # A malformed row with another tab in the OCR text must abandon all
    # spatial boxes, so the caller can obtain complete plain-text OCR.
    bad = _tsv_words(["good", "PRIVATE\tMISSING"])
    with pytest.raises(engine.OCRLayoutIncomplete) as error:
        engine._parse_tsv(bad, prepared_size=(50, 50), strict=True)
    assert "PRIVATE" not in str(error.value)
    assert "MISSING" not in str(error.value)


def test_quoted_tsv_word_survives_actual_pdf_export(tmp_path, monkeypatch):
    """OCR stdout -> production parser -> searchable PDF, no swallowed row."""
    from threading import Event
    from PIL import Image
    import fitz
    from ocryon.core.document import DocumentPage
    from ocryon.core.exporters import export_searchable_pdf
    from ocryon.core.ocr import TesseractEngine
    from ocryon.core.preprocess import PreprocessOptions

    fake = tmp_path / "quoted-tesseract"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "print('level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext')\n"
        "print('5\\t1\\t1\\t1\\t1\\t1\\t20\\t40\\t170\\t30\\t98\\t\\\"Zażółć')\n"
        "print('5\\t1\\t1\\t1\\t1\\t2\\t220\\t40\\t175\\t30\\t98\\tÅlesund')\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    original_popen = subprocess.Popen
    proxy = SimpleNamespace(**vars(subprocess))
    proxy.Popen = lambda _argv, **kwargs: original_popen(
        [sys.executable, "-X", "utf8", str(fake)], **kwargs
    )
    monkeypatch.setattr(engine, "subprocess", proxy)
    image = Image.new("RGB", (800, 200), "white")
    engine_instance = TesseractEngine(
        PreprocessOptions(grayscale=False, autocontrast=False, sharpen=False,
                          target_short_edge=0, max_upscale=1.0)
    )
    engine_instance.executable = fake
    result = engine.recognize_cancellable(engine_instance, image, "eng", Event())
    assert result.text == '"Zażółć Ålesund'
    assert [word.text for word in result.words] == ['"Zażółć', 'Ålesund']
    destination = tmp_path / "quote-Żółw-Ålesund.pdf"
    page = DocumentPage(
        source_path=tmp_path / "quoted-image.png", page_number=1,
        image=image, ocr_text=result.text, ocr_language=result.language,
        ocr_words=result.words,
    )
    assert export_searchable_pdf([page], destination) == 1
    with fitz.open(destination) as pdf:
        assert " ".join(pdf[0].get_text().split()) == result.text
        assert pdf[0].search_for("Ålesund")


def test_tsv_streaming_parser_honors_cancellation_during_large_layout():
    # The child already exited successfully, but tens of thousands of TSV
    # rows may still keep Python busy while the user closes the GUI.
    rows = _tsv_words(["Żółw"] * 2000)
    event = Event()
    calls = 0

    def check_interrupt():
        nonlocal calls
        calls += 1
        if calls == 3:
            event.set()
        if event.is_set():
            raise engine.OCRCancelled()

    with pytest.raises(engine.OCRCancelled):
        engine._parse_tsv(rows, prepared_size=(50, 50), strict=True,
                          check_interrupt=check_interrupt)
    assert calls == 3


def test_tsv_parser_enforces_deadline_even_on_single_last_row():
    # The final check closes the gap between two 256-row poll boundaries.
    calls = 0

    def check_interrupt():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise engine.OCRDeadlineExceeded()

    with pytest.raises(engine.OCRDeadlineExceeded):
        engine._parse_tsv(_tsv_words(["Ålesund"]), prepared_size=(50, 50),
                          strict=True, check_interrupt=check_interrupt)
    assert calls == 3
