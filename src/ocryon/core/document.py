from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


@dataclass(slots=True)
class DocumentPage:
    source_path: Path
    page_number: int
    image: Image.Image

    @property
    def label(self) -> str:
        return f"{self.source_path.name} — page {self.page_number}"


@dataclass(slots=True)
class LoadedDocument:
    source_path: Path
    pages: list[DocumentPage] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.pages)
