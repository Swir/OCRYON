from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from PIL import Image
import pytesseract


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
    builds will bundle the engine, so end users will not need a separate setup.
    """

    def __init__(self) -> None:
        self.executable = self._resolve_executable()
        if self.executable:
            pytesseract.pytesseract.tesseract_cmd = str(self.executable)

    def _resolve_executable(self) -> Path | None:
        configured = os.getenv("OCRYON_TESSERACT")
        candidates = [
            Path(configured) if configured else None,
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

        text = pytesseract.image_to_string(image, lang=language)
        return OCRResult(text=text, language=language)
