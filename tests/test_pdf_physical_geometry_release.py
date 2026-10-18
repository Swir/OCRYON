"""Native PyMuPDF round-trips: raster OCR words are pixels, PDFs are points."""
from pathlib import Path
import fitz
from PIL import Image
import pytest

from ocryon.core.document import DocumentPage
from ocryon.core.loaders import load_document
from ocryon.core.exporters import export_searchable_pdf
from ocryon.core.ocr import OCRWord


@pytest.mark.parametrize('zoom', [1.8, 1.37])
def test_pdf_export_keeps_source_physical_media_and_scales_ocr_boxes(tmp_path, zoom):
    original = tmp_path / 'private-original.pdf'
    with fitz.open() as doc:
        p = doc.new_page(width=240, height=360)
        p.insert_text((70, 100), 'VECTOR ORIGINAL')
        doc.save(original)
    original_bytes = original.read_bytes()
    image_page = load_document(original, pdf_scale=zoom).pages[0]
    assert image_page.image.width > 300
    # OCR's source pixel coordinates must map into physical PDF points.
    word = OCRWord('RECOVERED', 60, 80, 135, 25, 93.0)
    image_page.ocr_text = 'RECOVERED'
    image_page.ocr_words = (word,)
    exported = tmp_path / f'output-{zoom}.pdf'
    assert export_searchable_pdf([image_page], exported) == 1
    assert original.read_bytes() == original_bytes
    with fitz.open(exported) as pdf:
        page = pdf[0]
        assert page.rect.width == pytest.approx(240, abs=0.01)
        assert page.rect.height == pytest.approx(360, abs=0.01)
        assert page.search_for('RECOVERED')
        ocr_word = next(w for w in page.get_text('words') if w[4] == 'RECOVERED')
        assert ocr_word[0] == pytest.approx(60 * 240 / image_page.image.width, abs=3.0)
        assert ocr_word[1] == pytest.approx(80 * 360 / image_page.image.height, abs=8.0)
        assert page.get_images()


def test_raster_only_export_retains_existing_one_pixel_one_point_mapping(tmp_path):
    original = tmp_path / 'scan.png'
    image = Image.new('RGB', (500, 250), 'white')
    image.save(original)
    page = DocumentPage(
        original, 1, image, ocr_text='NORMAL',
        ocr_words=(OCRWord('NORMAL', 60, 80, 120, 25, 93.0),)
    )
    target = tmp_path / 'normal.pdf'
    export_searchable_pdf([page], target)
    with fitz.open(target) as pdf:
        assert (pdf[0].rect.width, pdf[0].rect.height) == (500.0, 250.0)
        words = pdf[0].get_text('words')
        assert any(w[4] == 'NORMAL' and abs(w[0] - 60) < 3 for w in words)


def test_bad_physical_geometry_fails_closed_before_overwriting_existing(tmp_path):
    page = DocumentPage(Path('external-input.pdf'), 1,
                        Image.new('RGB', (350, 400), 'white'), ocr_text='LABEL',
                        page_size_pt=(float('nan'), 250.0))
    path = tmp_path / 'qualified.pdf'
    path.write_bytes(b'KEEP-VALID-PREVIOUS-OUTPUT')
    with pytest.raises(ValueError, match='physical PDF page'):
        export_searchable_pdf([page], path)
    assert path.read_bytes() == b'KEEP-VALID-PREVIOUS-OUTPUT'
