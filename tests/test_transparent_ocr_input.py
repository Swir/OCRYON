from pathlib import Path

from PIL import Image, ImageDraw

from ocryon.core.loaders import load_document


def test_rgba_png_transparent_black_pixels_are_composited_to_white(tmp_path: Path):
    image = Image.new("RGBA", (96, 48), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((10, 12, 70, 27), fill=(0, 0, 0, 255))
    source = tmp_path / "transparent-ocr.png"
    image.save(source)

    result = load_document(source).pages[0].image
    assert result.mode == "RGB"
    assert result.getpixel((0, 0)) == (255, 255, 255)  # visible white scan background
    assert result.getpixel((20, 20)) == (0, 0, 0)  # opaque black OCR foreground


def test_paletted_png_transparent_background_is_composited_to_white(tmp_path: Path):
    image = Image.new("P", (24, 24), 0)
    image.putpalette([0, 0, 0, 0, 0, 0] + [0, 0, 0] * 254)
    image.info["transparency"] = 0
    ImageDraw.Draw(image).rectangle((4, 4, 15, 15), fill=1)
    source = tmp_path / "palette-transparent.png"
    image.save(source)
    result = load_document(source).pages[0].image
    assert result.getpixel((0, 0)) == (255, 255, 255)
    assert result.getpixel((5, 5)) == (0, 0, 0)
