"""Release gate: page image, OCR coordinates and PDF orientation must agree."""
from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageOps

from ocryon.core.document import DocumentPage
from ocryon.core.exporters import export_searchable_pdf
from ocryon.core.loaders import load_document
from ocryon.core.preprocess import PreprocessOptions, prepare_for_ocr


@pytest.mark.parametrize("orientation, upright_size", [(3, (96, 54)), (6, (54, 96)), (8, (54, 96))])
def test_exif_jpeg_orientation_is_normalized_before_preview_ocr_and_pdf(
    tmp_path: Path, orientation: int, upright_size: tuple[int, int]
) -> None:
    source = tmp_path / f"Źródło_Å_EXIF_{orientation}.jpg"
    raw = Image.new("RGB", (96, 54), "white")
    for x in range(5, 24):
        for y in range(5, 21):
            raw.putpixel((x, y), (0, 0, 0))
    exif = raw.getexif()
    exif[274] = orientation
    raw.save(source, exif=exif, quality=95)

    with Image.open(source) as opened:
        expected_upright = ImageOps.exif_transpose(opened).convert("RGB")
    document = load_document(source)
    page = document.pages[0]
    assert page.image.size == upright_size
    assert page.image.getexif().get(274) is None
    assert page.image.tobytes() == expected_upright.tobytes()

    # The OCR path must not rotate the same image a second time, and exported
    # page pixels must match the user's actual upright preview orientation.
    prepared = prepare_for_ocr(page.image, PreprocessOptions(
        grayscale=False, autocontrast=False, sharpen=False,
        target_short_edge=0, max_upscale=1.0,
    ))
    assert prepared.size == upright_size
    page.ocr_text = "EXIF"
    page.ocr_language = "eng"
    path = tmp_path / f"Szukalny_Å_{orientation}.pdf"
    assert export_searchable_pdf([page], path) == 1
    with fitz.open(path) as result:
        assert len(result) == 1
        assert tuple(int(v) for v in result[0].rect[2:]) == upright_size
        assert result[0].search_for("EXIF")
