from ocryon.core.ocr import _result_from_tesseract_data


def test_tesseract_data_builds_word_coordinates_and_layout_text() -> None:
    data = {
        "text": ["", "Hello", "world", "Next"],
        "conf": ["-1", "96.5", "88", "91"],
        "left": [0, 100, 300, 120],
        "top": [0, 80, 80, 220],
        "width": [0, 160, 180, 140],
        "height": [0, 60, 60, 60],
        "page_num": [1, 1, 1, 1],
        "block_num": [0, 1, 1, 1],
        "par_num": [0, 1, 1, 2],
        "line_num": [0, 1, 1, 1],
        "word_num": [0, 1, 2, 1],
    }

    result = _result_from_tesseract_data(
        data,
        language="eng",
        source_size=(1000, 500),
        prepared_size=(2000, 1000),
    )

    assert result.language == "eng"
    assert result.text == "Hello world\n\nNext"
    assert [word.text for word in result.words] == ["Hello", "world", "Next"]

    hello = result.words[0]
    assert hello.bbox == (50, 40, 130, 70)
    assert hello.confidence == 96.5
    assert hello.block == 1
    assert hello.paragraph == 1
    assert hello.line == 1
    assert hello.word == 1


def test_tesseract_data_tolerates_missing_or_invalid_numeric_fields() -> None:
    result = _result_from_tesseract_data(
        {
            "text": ["Alpha"],
            "conf": ["not-a-number"],
            "left": ["bad"],
        },
        language="pol",
        source_size=(200, 100),
        prepared_size=(200, 100),
    )

    assert result.text == "Alpha"
    assert len(result.words) == 1
    assert result.words[0].left == 0
    assert result.words[0].top == 0
    assert result.words[0].width == 1
    assert result.words[0].height == 1
    assert result.words[0].confidence == -1.0
