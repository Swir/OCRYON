from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys

from PIL import Image
import pytesseract

from ocryon.core.preprocess import PreprocessOptions, prepare_for_ocr


@dataclass(slots=True)
class OCRResult:
    text: str
    language: str


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

    def _resolve_executable(self) -> Path | None:
        configured = os.getenv("OCRYON_TESSERACT")

        app_root = Path(getattr(sys, "_MEIPASS", Path.cwd()))
        module_root = Path(__file__).resolve().parents[3]

        candidates = [
            Path(configured) if configured else None,
            app_root / "vendor" / "tesseract" / "tesseract.exe",
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

    def recognize(self, image: Image.Image, language: str = "eng") -> OCRResult:
        if not self.available():
            raise RuntimeError(
                "Offline OCR engine not found. Development builds can set "
                "OCRYON_TESSERACT to tesseract.exe."
            )

        prepared = prepare_for_ocr(image, self.preprocess_options)
        tessdata = self.executable.parent / "tessdata"
        config = "--oem 1"
        if tessdata.is_dir():
            config += f' --tessdata-dir "{tessdata}"'
        text = pytesseract.image_to_string(prepared, lang=language, config=config)
        return OCRResult(text=text, language=language)
