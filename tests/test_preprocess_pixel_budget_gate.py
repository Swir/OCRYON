"""Prevent excessive memory allocation before and during OCR preprocessing."""
from __future__ import annotations

from PIL import Image
import pytest

from ocryon.core import preprocess


def test_preflight_rejects_oversized_image_before_decoding(monkeypatch):
    monkeypatch.setattr(preprocess, "MAX_PREPARED_PIXELS", 250_000)

    class UntrustedImage:
        size = (1000, 251)

    # Not a Pillow image: reaching ImageOps before preflight would fail.
    with pytest.raises(ValueError, match="pixel budget"):
        preprocess.prepare_for_ocr(UntrustedImage())


def test_long_narrow_scan_upscaling_stays_within_pixel_budget(monkeypatch):
    monkeypatch.setattr(preprocess, "MAX_PREPARED_PIXELS", 250_000)
    image = Image.new("RGB", (1000, 200), "white")
    opts = preprocess.PreprocessOptions(
        grayscale=False, autocontrast=False, sharpen=False,
        max_upscale=2.0, target_short_edge=1200,
    )
    result = preprocess.prepare_for_ocr(image, opts)
    assert result.width >= image.width
    assert result.height >= image.height
    assert result.width * result.height <= 250_000
    assert result.width * result.height > image.width * image.height


def test_small_scan_retains_expected_upscale(monkeypatch):
    monkeypatch.setattr(preprocess, "MAX_PREPARED_PIXELS", 250_000)
    image = Image.new("RGB", (100, 100), "white")
    opts = preprocess.PreprocessOptions(
        grayscale=False, autocontrast=False, sharpen=False,
        max_upscale=2.0, target_short_edge=1200,
    )
    assert preprocess.prepare_for_ocr(image, opts).size == (200, 200)
