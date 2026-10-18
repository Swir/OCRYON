"""Cancellable, private Tesseract runner for the interactive Qt OCR worker.

No OCR text, source path, or Tesseract stderr is included in public errors.
The CLI headless qualification continues to use the normal TesseractEngine.
"""
from __future__ import annotations

import csv
from collections.abc import Callable
from io import StringIO
import math
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
import time

from PIL import Image

from ocryon.core.ocr import OCRResult, TesseractEngine, _result_from_tesseract_data
from ocryon.core.preprocess import prepare_for_ocr


class OCRCancelled(Exception):
    """Expected operator cancellation; must not produce a GUI failure popup."""


class OCRDeadlineExceeded(Exception):
    """OCR process did not exit within the bounded end-to-end time budget."""


_MAX_OCR_OUTPUT_BYTES = 32 * 1024 * 1024  # One page; do not buffer unbounded TSV in RAM.
_MAX_OCR_WORDS = 50_000  # OCR word objects/CSV rows are expensive even under a byte cap.
_MAX_OCR_CHARACTERS = 200_000  # Searchable PDF per-page hard limit.


class OCRLayoutIncomplete(Exception):
    """The TSV had text that could not be positioned reliably."""


def _run_tesseract(
    executable: Path,
    source: Path,
    language: str,
    output_mode: str,
    cancellation: Event,
    deadline: float,
) -> str:
    if cancellation.is_set():
        raise OCRCancelled()
    if time.monotonic() >= deadline:
        raise OCRDeadlineExceeded("Offline OCR exceeded its time budget")
    executable = executable.resolve()
    # The upstream Windows CLI uses narrow filesystem arguments. Pass the
    # image via an inherited file handle and resolve models from a Unicode-
    # aware Windows working directory, keeping every path argument ASCII.
    argv = [str(executable), "stdin", "stdout", "-l", language, "--oem", "1"]
    tessdata = executable.parent / "tessdata"
    if tessdata.is_dir():
        argv.extend(["--tessdata-dir", "tessdata"])
    if output_mode == "tsv":
        argv.append("tsv")
    elif output_mode != "txt":
        raise ValueError("Unsupported internal OCR mode")

    # In frozen mode only the frozen image's own tessdata is allowed; a host
    # TESSDATA_PREFIX cannot silently substitute languages in release QA.
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        env.pop("TESSDATA_PREFIX", None)
    flags = 0
    if os.name == "nt":
        flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    # Never PIPE a potentially huge TSV into subprocess.communicate(): Python
    # buffers it without a size limit, which can exhaust memory in frozen Qt
    # releases. A per-page disk-backed temporary file keeps memory bounded and
    # lets wait() poll cancellation without risking a descendant-held pipe.
    with source.open("rb") as input_file, tempfile.TemporaryFile(mode="w+b", prefix="ocryon-tsv-") as output_file:
        try:
            process = subprocess.Popen(
                argv, stdout=output_file, stderr=subprocess.DEVNULL,
                stdin=input_file, cwd=executable.parent, env=env, creationflags=flags,
                start_new_session=(os.name != "nt"),
            )
        except OSError:
            raise RuntimeError("Offline OCR process could not be started") from None

        completed = False
        try:
            while True:
                if cancellation.is_set():
                    raise OCRCancelled()
                # A disk-backed stdout avoids Python RAM spikes but does not
                # itself limit disk consumption. Check the LIVE file size while
                # Tesseract runs; otherwise a noisy/malicious page can fill
                # the user's drive for the entire 120-second OCR deadline.
                # fstat never moves the child/parent shared file offset.
                if os.fstat(output_file.fileno()).st_size > _MAX_OCR_OUTPUT_BYTES:
                    raise RuntimeError("Offline OCR output exceeds safe size limit")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OCRDeadlineExceeded("Offline OCR exceeded its time budget")
                try:
                    process.wait(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if cancellation.is_set():
                raise OCRCancelled()
            if process.returncode != 0:
                raise RuntimeError("Offline OCR process failed")

            output_file.seek(0, os.SEEK_END)
            if output_file.tell() > _MAX_OCR_OUTPUT_BYTES:
                raise RuntimeError("Offline OCR output exceeds safe size limit")
            output_file.seek(0)
            output = output_file.read(_MAX_OCR_OUTPUT_BYTES + 1)
            if len(output) > _MAX_OCR_OUTPUT_BYTES:
                raise RuntimeError("Offline OCR output exceeds safe size limit")
            # Tesseract's stdout is UTF-8. Replacement characters corrupt
            # Polish/Norwegian Unicode and make searchable PDFs unfaithful.
            try:
                result = output.decode("utf-8-sig", errors="strict")
            except UnicodeDecodeError:
                raise RuntimeError("Offline OCR returned invalid UTF-8") from None
            if output_mode == "txt" and len(result) > _MAX_OCR_CHARACTERS:
                raise RuntimeError("Offline OCR text exceeds safe size limit")
            completed = True
            return result
        finally:
            if not completed:
                # Cancellation and timeout must reap the child. Windows also
                # needs to terminate its tree; no pipe-draining is necessary.
                if process.poll() is None:
                    if os.name == "nt":
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=2.0,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                check=False,
                            )
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                    else:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    if process.poll() is None:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                try:
                    process.wait(timeout=0.8)
                except subprocess.TimeoutExpired:
                    # Do not hang the Qt worker during application close.
                    pass


def _parse_tsv(
    tsv: str, *, prepared_size: tuple[int, int], strict: bool = False,
    check_interrupt: Callable[[], None] | None = None,
) -> dict[str, list[object]]:
    keys = (
        "text", "conf", "left", "top", "width", "height", "page_num",
        "block_num", "par_num", "line_num", "word_num",
    )
    output: dict[str, list[object]] = {key: [] for key in keys}
    page_width, page_height = prepared_size
    recognized_words = 0
    recognized_characters = 0
    # Tesseract TSV is tab-delimited *raw output*, not RFC4180 CSV: OCR
    # words may begin with a literal quote. csv's default QUOTE_MINIMAL
    # would join that row with subsequent lines and silently make their OCR
    # text part of one word (and of the searchable PDF). Disable quoting.
    # The end-to-end OCR deadline/cancel signal must remain effective while
    # parsing a valid but huge TSV. Without checkpoints, a cancelled Qt close
    # or timed-out page remains busy in Python long after Tesseract exits.
    if check_interrupt is not None:
        check_interrupt()
    for row_number, row in enumerate(
        csv.DictReader(StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    ):
        if check_interrupt is not None and row_number % 256 == 0:
            check_interrupt()
        # An embedded TAB introduces surplus fields. Never silently drop
        # these: strict mode must use the full plain-text fallback instead of
        # producing incomplete or misleading PDF word coordinates.
        if row.get(None) is not None:
            if strict:
                raise OCRLayoutIncomplete()
            continue
        # Never map corrupt, negative, zero-size, or out-of-page TSV boxes to
        # plausible source coordinates: a searchable PDF must not silently
        # place a word at the wrong location.
        # Tesseract writes empty layout rows for blocks/paragraphs. Only a
        # nonblank recognized word creates a text-loss risk.
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        # TSV's disk byte bound does not cap Python allocation: each parsed
        # CSV row builds a dict, and each accepted OCR word becomes a PDF
        # positioning object. Bound BOTH counts before constructing them.
        recognized_words += 1
        recognized_characters += len(text)
        if (recognized_words > _MAX_OCR_WORDS
                or recognized_characters > _MAX_OCR_CHARACTERS):
            raise RuntimeError("Offline OCR text exceeds safe size limit")
        if not all(row.get(k) is not None for k in keys):
            if strict:
                raise OCRLayoutIncomplete()  # No private OCR text in errors.
            continue
        try:
            x, y = int(row["left"]), int(row["top"])
            w, h = int(row["width"]), int(row["height"])
            confidence = float(row["conf"])
        except (ValueError, TypeError, OverflowError):
            if strict:
                raise OCRLayoutIncomplete() from None
            continue
        if (
            not math.isfinite(confidence)
            or x < 0 or y < 0 or w <= 0 or h <= 0
            or x + w > page_width or y + h > page_height
        ):
            if strict:
                raise OCRLayoutIncomplete()
            continue
        for key in keys:
            output[key].append(row[key])
    if check_interrupt is not None:
        check_interrupt()
    return output


def recognize_cancellable(
    engine: TesseractEngine,
    image: Image.Image,
    language: str,
    cancellation: Event,
    *,
    timeout_seconds: float = 120.0,
) -> OCRResult:
    """Recognize image with responsive cancellation of an active subprocess."""
    if cancellation.is_set():
        raise OCRCancelled()
    if engine.executable is None:
        raise RuntimeError("Offline OCR engine unavailable")
    deadline = time.monotonic() + timeout_seconds

    def check_interrupt() -> None:
        if cancellation.is_set():
            raise OCRCancelled()
        if time.monotonic() >= deadline:
            raise OCRDeadlineExceeded("Offline OCR exceeded its time budget")

    # Cancellation/deadline must cover Pillow preprocessing as well as the
    # Tesseract child. Without checkpoints, closing the Qt window during a
    # large denoise/resize leaves QThread stuck before Popen even begins.
    prepared = prepare_for_ocr(
        image, engine.preprocess_options, check_interrupt=check_interrupt
    )
    check_interrupt()
    with tempfile.TemporaryDirectory(prefix="ocryon-ocr-") as scratch:
        source = Path(scratch) / "page.png"
        prepared.save(source, format="PNG")
        check_interrupt()
        tsv = _run_tesseract(
            engine.executable, source, language, "tsv", cancellation, deadline
        )
        check_interrupt()
        try:
            parsed = _parse_tsv(
                tsv, prepared_size=prepared.size, strict=True,
                check_interrupt=check_interrupt,
            )
        except OCRLayoutIncomplete:
            # A valid TSV word does not prove full coverage when another word
            # had corrupt geometry. Abandon ALL boxes and retry plain text;
            # otherwise the OCR page and searchable PDF lose words silently.
            parsed = None
        check_interrupt()
        result = (
            _result_from_tesseract_data(
                parsed, language=language,
                source_size=image.size, prepared_size=prepared.size,
            ) if parsed is not None else OCRResult(text="", language=language)
        )
        check_interrupt()
        # Reconstructing paragraphs adds newlines/spaces beyond TSV word
        # lengths. Enforce the exact PDF limit before leaving this worker.
        if len(result.text) > _MAX_OCR_CHARACTERS:
            raise RuntimeError("Offline OCR text exceeds safe size limit")
        if parsed is None or not result.words:
            result = OCRResult(
                text=_run_tesseract(
                    engine.executable, source, language, "txt", cancellation, deadline
                ),
                language=language,
            )
    check_interrupt()
    return result
