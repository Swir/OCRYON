from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys

from PIL import Image
import pytesseract

from ocryon.core.preprocess import PreprocessOptions, prepare_for_ocr


@dataclass(frozen=True, slots=True)
class OCRWord:
    """One recognized word positioned in source-image pixel coordinates."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    page: int = 1
    block: int = 0
    paragraph: int = 0
    line: int = 0
    word: int = 0

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


@dataclass(slots=True)
class OCRResult:
    text: str
    language: str
    words: tuple[OCRWord, ...] = ()


class OCREngine(ABC):
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def recognize(self, image: Image.Image, language: str) -> OCRResult:
        raise NotImplementedError


class TesseractEngine(OCREngine):
    """Offline OCR backend.

    Development builds can use an installed Tesseract binary. Packaged OCRYON
    builds can bundle the engine under vendor/tesseract.
    """

    def __init__(self, preprocess_options: PreprocessOptions | None = None) -> None:
        self.preprocess_options = preprocess_options or PreprocessOptions()
        self.executable = self._resolve_executable()
        if self.executable:
            pytesseract.pytesseract.tesseract_cmd = str(self.executable)

    @staticmethod
    def _bundled_executable() -> Path:
        # PyInstaller 6 onedir uses sys._MEIPASS for the _internal data root.
        # Never infer a bundled binary from the current working directory.
        root = Path(
            getattr(sys, "_MEIPASS", Path(sys.executable).parent)
        )
        return root / "vendor" / "tesseract" / "tesseract.exe"

    def _resolve_executable(self) -> Path | None:
        bundled = self._bundled_executable()
        if getattr(sys, "frozen", False):
            # Qualification must not be fooled by host OCRYON_TESSERACT,
            # PATH, or a vendor folder under an attacker-chosen cwd.
            return bundled if bundled.is_file() else None

        configured = os.getenv("OCRYON_TESSERACT")
        module_root = Path(__file__).resolve().parents[3]
        candidates = [
            Path(configured) if configured else None,
            bundled,
            module_root / "vendor" / "tesseract" / "tesseract.exe",
            Path.cwd() / "vendor" / "tesseract" / "tesseract.exe",
        ]
        on_path = shutil.which("tesseract")
        if on_path:
            candidates.append(Path(on_path))

        for candidate in candidates:
            if candidate and candidate.is_file():
                return candidate
        return None

    def available(self) -> bool:
        return self.executable is not None

    def uses_bundled_engine(self) -> bool:
        # A frozen image must provide the executable AND all three bundled
        # language models used by the five selectable OCR modes. Otherwise a
        # developer machine's TESSDATA_PREFIX can mask a broken public ZIP.
        if self.executable is None:
            return False
        if self.executable.resolve() != self._bundled_executable().resolve():
            return False
        tessdata = self.executable.parent / "tessdata"
        return all(
            (tessdata / f"{code}.traineddata").is_file()
            for code in ("eng", "pol", "nor")
        )

    def recognize(self, image: Image.Image, language: str = "eng") -> OCRResult:
        if not self.available():
            raise RuntimeError(
                "Offline OCR engine not found. Development builds can set "
                "OCRYON_TESSERACT to tesseract.exe."
            )

        # Use the same bounded runner as the Qt worker. It passes the data
        # directory as one argv item, including spaces and Unicode on Windows.
        # pytesseract's Windows config splitting retains literal quotes here.
        from threading import Event
        from ocryon.core.cancellable_tesseract import recognize_cancellable

        return recognize_cancellable(self, image, language, Event())


def _result_from_tesseract_data(
    data: Mapping[str, Sequence[object]],
    *,
    language: str,
    source_size: tuple[int, int],
    prepared_size: tuple[int, int],
) -> OCRResult:
    source_width, source_height = source_size
    prepared_width, prepared_height = prepared_size
    scale_x = source_width / prepared_width if prepared_width else 1.0
    scale_y = source_height / prepared_height if prepared_height else 1.0

    words: list[OCRWord] = []
    for index, raw_text in enumerate(data.get("text", ())):
        text = str(raw_text or "").strip()
        if not text:
            continue

        left = _scaled_coordinate(_data_int(data, "left", index), scale_x, source_width)
        top = _scaled_coordinate(_data_int(data, "top", index), scale_y, source_height)
        width = _scaled_extent(
            _data_int(data, "width", index),
            scale_x,
            source_width - left,
        )
        height = _scaled_extent(
            _data_int(data, "height", index),
            scale_y,
            source_height - top,
        )

        words.append(
            OCRWord(
                text=text,
                left=left,
                top=top,
                width=width,
                height=height,
                confidence=_data_float(data, "conf", index, -1.0),
                page=_data_int(data, "page_num", index, 1),
                block=_data_int(data, "block_num", index),
                paragraph=_data_int(data, "par_num", index),
                line=_data_int(data, "line_num", index),
                word=_data_int(data, "word_num", index),
            )
        )

    frozen_words = tuple(words)
    return OCRResult(
        text=_reconstruct_text(frozen_words),
        language=language,
        words=frozen_words,
    )


def _reconstruct_text(words: Sequence[OCRWord]) -> str:
    if not words:
        return ""

    output: list[str] = []
    current_words: list[str] = []
    previous_line: tuple[int, int, int, int] | None = None
    previous_paragraph: tuple[int, int, int] | None = None

    for word in words:
        line_key = (word.page, word.block, word.paragraph, word.line)
        paragraph_key = line_key[:3]

        if previous_line is not None and line_key != previous_line:
            output.append(" ".join(current_words))
            current_words = []
            if paragraph_key != previous_paragraph:
                output.append("")

        current_words.append(word.text)
        previous_line = line_key
        previous_paragraph = paragraph_key

    if current_words:
        output.append(" ".join(current_words))

    return "\n".join(output).strip()


def _data_value(
    data: Mapping[str, Sequence[object]],
    key: str,
    index: int,
    default: object,
) -> object:
    values = data.get(key, ())
    if index >= len(values):
        return default
    return values[index]


def _data_int(
    data: Mapping[str, Sequence[object]],
    key: str,
    index: int,
    default: int = 0,
) -> int:
    try:
        return int(float(_data_value(data, key, index, default)))
    except (TypeError, ValueError):
        return default


def _data_float(
    data: Mapping[str, Sequence[object]],
    key: str,
    index: int,
    default: float = 0.0,
) -> float:
    try:
        return float(_data_value(data, key, index, default))
    except (TypeError, ValueError):
        return default


def _scaled_coordinate(value: int, scale: float, limit: int) -> int:
    if limit <= 0:
        return 0
    return max(0, min(limit - 1, round(value * scale)))


def _scaled_extent(value: int, scale: float, available: int) -> int:
    if available <= 0:
        return 1
    return max(1, min(available, round(value * scale)))
