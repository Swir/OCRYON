from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from ocryon.core.document import DocumentPage, LoadedDocument


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class UnsupportedDocumentError(ValueError):
    pass


def load_document(path: str | Path, pdf_scale: float = 1.8) -> LoadedDocument:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(source, pdf_scale)
    if suffix in IMAGE_EXTENSIONS:
        return _load_image(source)

    raise UnsupportedDocumentError(f"Unsupported file type: {suffix or '<none>'}")


def _load_image(source: Path) -> LoadedDocument:
    with Image.open(source) as opened:
        image = opened.convert("RGB").copy()

    return LoadedDocument(
        source_path=source,
        pages=[DocumentPage(source_path=source, page_number=1, image=image)],
    )


def _load_pdf(source: Path, scale: float) -> LoadedDocument:
    pages: list[DocumentPage] = []
    matrix = fitz.Matrix(scale, scale)

    with fitz.open(source) as pdf:
        for index, page in enumerate(pdf):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(
                DocumentPage(
                    source_path=source,
                    page_number=index + 1,
                    image=image,
                )
            )

    return LoadedDocument(source_path=source, pages=pages)
