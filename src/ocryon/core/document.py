from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


@dataclass(slots=True)
class DocumentPage:
    source_path: Path
    page_number: int
    image: Image.Image
    ocr_text: str = ""
    ocr_language: str | None = None

    @property
    def label(self) -> str:
        return f"{self.source_path.name} — page {self.page_number}"

    @property
    def has_ocr(self) -> bool:
        return bool(self.ocr_text.strip())


@dataclass(slots=True)
class LoadedDocument:
    source_path: Path
    pages: list[DocumentPage] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.pages)

    @property
    def recognized_pages(self) -> int:
        return sum(page.has_ocr for page in self.pages)
