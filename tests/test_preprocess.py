from PIL import Image

from ocryon.core.preprocess import PreprocessOptions, prepare_for_ocr


def test_preprocess_does_not_mutate_source() -> None:
    source = Image.new("RGB", (200, 100), "white")

    prepared = prepare_for_ocr(source)

    assert source.mode == "RGB"
    assert source.size == (200, 100)
    assert prepared is not source
    assert prepared.mode == "L"


def test_preprocess_upscales_small_images_with_cap() -> None:
    source = Image.new("RGB", (400, 200), "white")

    prepared = prepare_for_ocr(
        source,
        PreprocessOptions(target_short_edge=1200, max_upscale=2.0),
    )

    assert prepared.size == (800, 400)


def test_preprocess_keeps_large_image_size() -> None:
    source = Image.new("RGB", (1800, 1400), "white")

    prepared = prepare_for_ocr(source)

    assert prepared.size == source.size


def test_preprocess_can_keep_color() -> None:
    source = Image.new("RGB", (1600, 1200), "white")

    prepared = prepare_for_ocr(
        source,
        PreprocessOptions(
            grayscale=False,
            autocontrast=False,
            sharpen=False,
        ),
    )

    assert prepared.mode == "RGB"
