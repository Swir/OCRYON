"""Multipage TIFF must never silently discard recognized source pages."""
from pathlib import Path

import pytest
from PIL import Image

from ocryon.core import loaders


def _multipage_tiff(path: Path) -> Path:
    first = Image.new("RGB", (80, 90), "red")
    second = Image.new("RGB", (60, 70), "green")
    first.save(path, save_all=True, append_images=[second], compression="tiff_deflate")
    return path


def test_multipage_tiff_preserves_all_frames_and_labels(tmp_path):
    path = _multipage_tiff(tmp_path / "Zażółć_Ålesund.tiff")
    result = loaders.load_document(path)
    assert len(result.pages) == 2
    assert [page.page_number for page in result.pages] == [1, 2]
    assert [page.image.size for page in result.pages] == [(80, 90), (60, 70)]
    assert result.pages[0].image.getpixel((0, 0)) != result.pages[1].image.getpixel((0, 0))
    assert all(page.source_path == path for page in result.pages)


def test_multiframe_budget_checks_all_frames_before_decoding(tmp_path, monkeypatch):
    path = _multipage_tiff(tmp_path / "large.tif")
    def forbidden_convert(*args, **kwargs):
        pytest.fail("image decoded before aggregate multipage budget preflight")
    monkeypatch.setattr(Image.Image, "convert", forbidden_convert)
    with pytest.raises(loaders.DocumentTooLargeError, match="remaining document-memory"):
        loaders.load_document(path, available_pixels=10_000)


def test_multiframe_page_count_limit_is_fail_closed(tmp_path, monkeypatch):
    path = _multipage_tiff(tmp_path / "many.tiff")
    monkeypatch.setattr(loaders, "MAX_DOCUMENT_PAGES", 1)
    with pytest.raises(loaders.DocumentTooLargeError, match="page-count"):
        loaders.load_document(path)
