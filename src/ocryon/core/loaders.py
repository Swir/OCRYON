from __future__ import annotations

from pathlib import Path
import math

import fitz
from PIL import Image

from ocryon.core.document import DocumentPage, LoadedDocument


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# Decoding a single malicious oversized PDF page/image in the UI process can
# allocate multiple copies of its pixels and terminate OCRYON without a saved
# export. Preflight *all* pages before rasterizing any of them. These are pixel
# limits, not file-byte limits: a tiny vector PDF can render to gigabytes.
MAX_PAGE_PIXELS = 24_000_000
MAX_DOCUMENT_PIXELS = 180_000_000
MAX_DOCUMENT_PAGES = 200


class UnsupportedDocumentError(ValueError):
    pass


class DocumentTooLargeError(ValueError):
    """Untrusted document exceeds the bounded local rasterization budget."""


def load_document(
    path: str | Path,
    pdf_scale: float = 1.8,
    *,
    available_pixels: int | None = None,
) -> LoadedDocument:
    """Bound new document decoding by the caller's remaining image budget.

    The GUI retains images from earlier loads. A per-file cap alone permits
    unlimited RAM growth after opening many individually valid documents.
    Perform preflight before decoding the next one instead.
    """
    budget = MAX_DOCUMENT_PIXELS if available_pixels is None else min(
        MAX_DOCUMENT_PIXELS, available_pixels
    )
    if not isinstance(budget, int) or budget <= 0:
        raise DocumentTooLargeError("OCRYON's document-memory budget is exhausted")
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(source, pdf_scale, budget)
    if suffix in IMAGE_EXTENSIONS:
        return _load_image(source, budget)

    raise UnsupportedDocumentError(f"Unsupported file type: {suffix or '<none>'}")


def _load_image(source: Path, budget: int) -> LoadedDocument:
    with Image.open(source) as opened:
        width, height = opened.size
        if width <= 0 or height <= 0 or width * height > MAX_PAGE_PIXELS:
            raise DocumentTooLargeError("Image exceeds OCRYON's safe page-size limit")
        if width * height > budget:
            raise DocumentTooLargeError("Image exceeds OCRYON's remaining document-memory budget")
        image = opened.convert("RGB").copy()

    return LoadedDocument(
        source_path=source,
        pages=[DocumentPage(source_path=source, page_number=1, image=image)],
    )


def _load_pdf(source: Path, scale: float, budget: int) -> LoadedDocument:
    if not math.isfinite(scale) or not 0 < scale <= 4.0:
        raise ValueError("PDF raster scale must be between 0 and 4")
    pages: list[DocumentPage] = []
    matrix = fitz.Matrix(scale, scale)

    with fitz.open(source) as pdf:
        if pdf.page_count > MAX_DOCUMENT_PAGES:
            raise DocumentTooLargeError("PDF exceeds OCRYON's safe page-count limit")

        # Page.rect applies page rotation; round UP and leave a small margin
        # for renderer pixel rounding. Importantly, this executes before the
        # first get_pixmap(), so a later page cannot crash the UI midway.
        total_pixels = 0
        for page in pdf:
            rect = page.rect
            width = math.ceil(float(rect.width) * scale) + 2
            height = math.ceil(float(rect.height) * scale) + 2
            pixels = width * height
            if width <= 0 or height <= 0 or pixels > MAX_PAGE_PIXELS:
                raise DocumentTooLargeError("PDF exceeds OCRYON's safe page-size limit")
            total_pixels += pixels
            if total_pixels > budget:
                raise DocumentTooLargeError("PDF exceeds OCRYON's safe document-memory limit")

        for index, page in enumerate(pdf):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            if pix.width * pix.height > MAX_PAGE_PIXELS:
                raise DocumentTooLargeError("Rendered PDF exceeds the safe page-size limit")
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(
                DocumentPage(
                    source_path=source,
                    page_number=index + 1,
                    image=image,
                )
            )

    return LoadedDocument(source_path=source, pages=pages)
