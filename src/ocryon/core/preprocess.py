from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Callable

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


PREPROCESS_PRESET_NAMES = ("automatic", "clean_scan", "photo", "high_contrast", "original")

# A legal 24MP source page must never be upscaled into a 96MP temporary.
# This ceiling applies before copying pixels and after any enlargement.
MAX_PREPARED_PIXELS = 24_000_000


@dataclass(frozen=True, slots=True)
class PreprocessOptions:
    grayscale: bool = True
    autocontrast: bool = True
    denoise: bool = False
    sharpen: bool = True
    binarize_threshold: int | None = None
    invert: bool = False
    max_upscale: float = 2.0
    target_short_edge: int = 1200

    def __post_init__(self) -> None:
        if self.binarize_threshold is not None and not 0 <= self.binarize_threshold <= 255:
            raise ValueError("binarize_threshold must be between 0 and 255")
        if self.max_upscale < 1.0:
            raise ValueError("max_upscale must be at least 1.0")
        if self.target_short_edge < 0:
            raise ValueError("target_short_edge cannot be negative")


def preprocess_options_for_preset(name: str) -> PreprocessOptions:
    """Return a stable preprocessing profile for the desktop controls."""

    key = name.strip().lower()
    presets = {
        "automatic": PreprocessOptions(),
        "clean_scan": PreprocessOptions(
            denoise=True,
            target_short_edge=1400,
        ),
        "photo": PreprocessOptions(
            denoise=True,
            sharpen=False,
            target_short_edge=1600,
        ),
        "high_contrast": PreprocessOptions(
            denoise=True,
            binarize_threshold=170,
            target_short_edge=1400,
        ),
        "original": PreprocessOptions(
            grayscale=False,
            autocontrast=False,
            sharpen=False,
            max_upscale=1.0,
            target_short_edge=0,
        ),
    }
    try:
        return presets[key]
    except KeyError as exc:
        raise ValueError(f"Unknown preprocessing preset: {name}") from exc


def prepare_for_ocr(
    image: Image.Image,
    options: PreprocessOptions | None = None,
    *,
    check_interrupt: Callable[[], None] | None = None,
) -> Image.Image:
    """Prepare an independent image, honoring cancellation between expensive steps.

    The optional callback may raise the caller's cancellation/deadline
    exception. This avoids importing the OCR worker (and circular imports)
    into generic preprocessing. Each Pillow operation still runs atomically.
    """

    options = options or PreprocessOptions()
    check = check_interrupt or (lambda: None)
    check()
    # Inspect dimensions before ImageOps.exif_transpose(), which decodes and
    # copies the input. An oversized direct/API image could otherwise consume
    # large amounts of RAM before a release-safety check becomes possible.
    source_width, source_height = image.size
    if (source_width <= 0 or source_height <= 0
            or source_width * source_height > MAX_PREPARED_PIXELS):
        raise ValueError("OCR preprocessing exceeds safe pixel budget")
    prepared = ImageOps.exif_transpose(image).copy()
    check()

    if options.grayscale:
        prepared = prepared.convert("L")
    elif prepared.mode not in {"RGB", "RGBA"}:
        prepared = prepared.convert("RGB")

    check()
    if options.denoise:
        prepared = prepared.filter(ImageFilter.MedianFilter(size=3))

    check()
    if options.autocontrast:
        prepared = ImageOps.autocontrast(prepared)

    check()
    if options.binarize_threshold is not None:
        if prepared.mode != "L":
            prepared = prepared.convert("L")
        threshold = options.binarize_threshold
        prepared = prepared.point(lambda value: 255 if value >= threshold else 0)

    check()
    if options.invert:
        if prepared.mode == "RGBA":
            rgb = ImageOps.invert(prepared.convert("RGB"))
            rgb.putalpha(prepared.getchannel("A"))
            prepared = rgb.convert("RGBA")
        else:
            prepared = ImageOps.invert(prepared)

    check()
    width, height = prepared.size
    short_edge = min(width, height)
    if (
        options.target_short_edge > 0
        and short_edge > 0
        and short_edge < options.target_short_edge
    ):
        scale = min(options.max_upscale, options.target_short_edge / short_edge)
        # Prevent a long, narrow 24MP page from temporarily becoming 96MP.
        # Round DOWN after bounding area; Pillow must never allocate beyond
        # the pixel budget, even if rounding would tip it over the limit.
        scale = min(scale, math.sqrt(MAX_PREPARED_PIXELS / (width * height)))
        if scale > 1.0:
            new_size = (max(width, int(width * scale)),
                        max(height, int(height * scale)))
            if new_size[0] * new_size[1] > MAX_PREPARED_PIXELS:
                raise ValueError("OCR preprocessing exceeds safe pixel budget")
            if new_size != prepared.size:
                prepared = prepared.resize(new_size, Image.Resampling.LANCZOS)

    check()
    if options.sharpen:
        prepared = ImageEnhance.Sharpness(prepared).enhance(1.35)
        prepared = prepared.filter(ImageFilter.SHARPEN)

    check()
    return prepared
