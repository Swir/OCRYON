from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


@dataclass(frozen=True, slots=True)
class PreprocessOptions:
    grayscale: bool = True
    autocontrast: bool = True
    sharpen: bool = True
    max_upscale: float = 2.0
    target_short_edge: int = 1200


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

    if options.autocontrast:
        prepared = ImageOps.autocontrast(prepared)

    width, height = prepared.size
    short_edge = min(width, height)
    if short_edge > 0 and short_edge < options.target_short_edge:
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
