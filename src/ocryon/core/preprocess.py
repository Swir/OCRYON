from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


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
) -> Image.Image:
    """Return an OCR-friendly copy without mutating the source image."""

    options = options or PreprocessOptions()
    prepared = ImageOps.exif_transpose(image).copy()

    if options.grayscale:
        prepared = prepared.convert("L")
    elif prepared.mode not in {"RGB", "RGBA"}:
        prepared = prepared.convert("RGB")

    if options.denoise:
        prepared = prepared.filter(ImageFilter.MedianFilter(size=3))

    if options.autocontrast:
        prepared = ImageOps.autocontrast(prepared)

    if options.binarize_threshold is not None:
        if prepared.mode != "L":
            prepared = prepared.convert("L")
        threshold = options.binarize_threshold
        prepared = prepared.point(lambda value: 255 if value >= threshold else 0)

    if options.invert:
        if prepared.mode == "RGBA":
            rgb = ImageOps.invert(prepared.convert("RGB"))
            rgb.putalpha(prepared.getchannel("A"))
            prepared = rgb.convert("RGBA")
        else:
            prepared = ImageOps.invert(prepared)

    width, height = prepared.size
    short_edge = min(width, height)
    if (
        options.target_short_edge > 0
        and short_edge > 0
        and short_edge < options.target_short_edge
    ):
        scale = min(options.max_upscale, options.target_short_edge / short_edge)
        if scale > 1.0:
            new_size = (
                max(1, round(width * scale)),
                max(1, round(height * scale)),
            )
            prepared = prepared.resize(new_size, Image.Resampling.LANCZOS)

    if options.sharpen:
        prepared = ImageEnhance.Sharpness(prepared).enhance(1.35)
        prepared = prepared.filter(ImageFilter.SHARPEN)

    return prepared
