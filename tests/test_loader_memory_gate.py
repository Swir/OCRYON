"""Real PyMuPDF/Pillow limits for untrusted user-supplied documents."""
from pathlib import Path

import fitz
import pytest
from PIL import Image

from ocryon.core import loaders


def _pdf(path: Path, sizes: list[tuple[int, int]]) -> Path:
    with fitz.open() as pdf:
        for w, h in sizes:
            pdf.new_page(width=w, height=h)
        pdf.save(path)
    return path


def test_untrusted_vector_page_rejected_before_rasterization(tmp_path):
    # This one-page PDF is tiny on disk but would need >1 GB decoded.
    source = _pdf(tmp_path / "HugeVector.pdf", [(19000, 19000)])
    with pytest.raises(loaders.DocumentTooLargeError, match="page-size"):
        loaders.load_document(source)


def test_total_pdf_budget_preflight_rejects_before_first_render(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "multi.pdf", [(120, 110)] * 3)
    monkeypatch.setattr(loaders, "MAX_DOCUMENT_PIXELS", 110_000)
    with pytest.raises(loaders.DocumentTooLargeError, match="document-memory"):
        loaders.load_document(source)


def test_pdf_page_count_rejected_before_render(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "many.pdf", [(100, 100)] * 3)
    monkeypatch.setattr(loaders, "MAX_DOCUMENT_PAGES", 2)
    with pytest.raises(loaders.DocumentTooLargeError, match="page-count"):
        loaders.load_document(source)


def test_image_metadata_limit_checked_before_decoding(tmp_path, monkeypatch):
    source = tmp_path / "huge.png"
    Image.new("RGB", (120, 100), "white").save(source)
    monkeypatch.setattr(loaders, "MAX_PAGE_PIXELS", 1000)
    with pytest.raises(loaders.DocumentTooLargeError, match="page-size"):
        loaders.load_document(source)


def test_two_page_pdf_still_loads_and_preserves_numbering(tmp_path):
    source = _pdf(tmp_path / "Zażółć_Ålesund.pdf", [(120, 100), (130, 110)])
    document = loaders.load_document(source)
    assert len(document.pages) == 2
    assert [page.page_number for page in document.pages] == [1, 2]
    assert all(page.image.width > 0 for page in document.pages)


def test_invalid_scale_rejected_before_pixmap(tmp_path):
    source = _pdf(tmp_path / "scale.pdf", [(120, 100)])
    with pytest.raises(ValueError, match="scale"):
        loaders.load_document(source, pdf_scale=float("inf"))


def test_second_image_blocked_by_remaining_window_budget(tmp_path):
    source = tmp_path / "Łódź_Ørsta.png"
    Image.new("RGB", (100, 100), "white").save(source)
    assert len(loaders.load_document(source, available_pixels=10_000).pages) == 1
    with pytest.raises(loaders.DocumentTooLargeError, match="remaining document-memory"):
        loaders.load_document(source, available_pixels=9_999)


def test_second_pdf_preflight_uses_remaining_budget_before_render(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "second.pdf", [(100, 100)])
    def no_rasterize(*args, **kwargs):
        pytest.fail("PDF renderer ran before rejecting the aggregate pixel budget")
    monkeypatch.setattr(fitz.Page, "get_pixmap", no_rasterize)
    with pytest.raises(loaders.DocumentTooLargeError, match="document-memory"):
        loaders.load_document(source, pdf_scale=2, available_pixels=20_000)


def test_budget_argument_cannot_override_global_safety_limit(tmp_path, monkeypatch):
    source = tmp_path / "x.png"
    Image.new("RGB", (100, 100), "white").save(source)
    monkeypatch.setattr(loaders, "MAX_DOCUMENT_PIXELS", 9_000)
    with pytest.raises(loaders.DocumentTooLargeError, match="remaining document-memory"):
        loaders.load_document(source, available_pixels=1_000_000)


def test_exhausted_window_budget_fails_before_loading(tmp_path):
    source = tmp_path / "x.png"
    Image.new("RGB", (100, 100), "white").save(source)
    with pytest.raises(loaders.DocumentTooLargeError, match="budget is exhausted"):
        loaders.load_document(source, available_pixels=0)
