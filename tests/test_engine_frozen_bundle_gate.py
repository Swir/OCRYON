"""Release-critical frozen OCR-engine discovery regression tests.

These tests simulate PyInstaller path semantics on Linux. They are NOT native
Windows/PySide6 validation and must not be counted as such.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
import pytesseract


HERE = Path(__file__).resolve().parents[1]
SOURCE = HERE / "src" / "ocryon" / "core" / "ocr.py"
QUALIFICATION = HERE / "src" / "ocryon" / "core" / "qualification.py"


@pytest.fixture
def project(monkeypatch, tmp_path):
    # Stub only preprocessing; exercise production TesseractEngine unchanged.
    pkg = types.ModuleType("ocryon")
    pkg.__path__ = []
    core_pkg = types.ModuleType("ocryon.core")
    core_pkg.__path__ = []
    preprocess = types.ModuleType("ocryon.core.preprocess")
    preprocess.PreprocessOptions = type("PreprocessOptions", (), {})
    preprocess.prepare_for_ocr = lambda image, options: image
    resources = types.ModuleType("ocryon.resources")
    resources.asset_path = lambda name: tmp_path / "assets" / name
    for name, module in (
        ("ocryon", pkg),
        ("ocryon.core", core_pkg),
        ("ocryon.core.preprocess", preprocess),
        ("ocryon.resources", resources),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    previous_cmd = pytesseract.pytesseract.tesseract_cmd
    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", previous_cmd)
    spec = importlib.util.spec_from_file_location("ocryon.core.ocr", SOURCE)
    ocr = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ocryon.core.ocr", ocr)
    spec.loader.exec_module(ocr)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    return ocr, resources


def _create_executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake exe for resolver tests only")
    return path


def test_frozen_bundle_wins_over_host_override_and_path(project, monkeypatch, tmp_path):
    ocr, _ = project
    bundled = _create_executable(tmp_path / "_internal/vendor/tesseract/tesseract.exe")
    for code in ("eng", "pol", "nor"):
        _create_executable(bundled.parent / "tessdata" / f"{code}.traineddata")
    host = _create_executable(tmp_path / "external/tesseract.exe")
    monkeypatch.setenv("OCRYON_TESSERACT", str(host))
    monkeypatch.setattr(ocr.shutil, "which", lambda name: str(host))
    engine = ocr.TesseractEngine()
    assert engine.executable == bundled
    assert engine.available()
    assert engine.uses_bundled_engine()


def test_frozen_refuses_host_engine_when_bundle_missing(project, monkeypatch, tmp_path):
    ocr, _ = project
    host = _create_executable(tmp_path / "external/tesseract.exe")
    monkeypatch.setenv("OCRYON_TESSERACT", str(host))
    monkeypatch.setattr(ocr.shutil, "which", lambda name: str(host))
    engine = ocr.TesseractEngine()
    assert engine.executable is None
    assert not engine.available()
    assert not engine.uses_bundled_engine()


def test_nonfrozen_maintains_external_override(project, monkeypatch, tmp_path):
    ocr, _ = project
    monkeypatch.setattr(sys, "frozen", False)
    external = _create_executable(tmp_path / "external/tesseract.exe")
    monkeypatch.setenv("OCRYON_TESSERACT", str(external))
    assert ocr.TesseractEngine().executable == external
    assert not ocr.TesseractEngine().uses_bundled_engine()


def test_unicode_meipass_and_relative_cwd_not_trusted(project, monkeypatch, tmp_path):
    ocr, _ = project
    fake_cwd = tmp_path / "host"
    _create_executable(fake_cwd / "vendor/tesseract/tesseract.exe")
    real_bundle = _create_executable(tmp_path / "Żółw Šíř _internal/vendor/tesseract/tesseract.exe")
    monkeypatch.chdir(fake_cwd)
    monkeypatch.setattr(sys, "_MEIPASS", str(real_bundle.parents[2]))
    assert ocr.TesseractEngine().executable == real_bundle
    real_bundle.unlink()
    assert ocr.TesseractEngine().executable is None


def test_frozen_qualification_fails_with_21_when_only_host_present(project, monkeypatch, tmp_path):
    ocr, resources = project
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "ocryon.svg").touch()
    (assets / "ocryon.png").touch()
    host = _create_executable(tmp_path / "external/tesseract.exe")
    monkeypatch.setenv("OCRYON_TESSERACT", str(host))
    spec = importlib.util.spec_from_file_location("ocryon.core.qualification", QUALIFICATION)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ocryon.core.qualification", module)
    spec.loader.exec_module(module)
    assert module.run_selftest() == 21


def test_frozen_qualification_five_modes_run_with_true_bundle(project, monkeypatch, tmp_path):
    ocr, resources = project
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "ocryon.svg").touch()
    (assets / "ocryon.png").touch()
    bundled = _create_executable(tmp_path / "_internal/vendor/tesseract/tesseract.exe")
    for code in ("eng", "pol", "nor"):
        _create_executable(bundled.parent / "tessdata" / f"{code}.traineddata")
    called = []

    def recognize(self, image, language):
        called.append(language)
        return ocr.OCRResult(text="TEST 123", language=language)

    monkeypatch.setattr(ocr.TesseractEngine, "recognize", recognize)
    spec = importlib.util.spec_from_file_location("ocryon.core.qualification", QUALIFICATION)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ocryon.core.qualification", module)
    spec.loader.exec_module(module)
    assert module.run_selftest() == 0
    assert called == ["eng", "pol", "nor", "eng+pol", "eng+nor"]


def test_frozen_cannot_pass_with_host_traineddata_when_norwegian_missing(
    project, monkeypatch, tmp_path
):
    ocr, resources = project
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "ocryon.svg").touch()
    (assets / "ocryon.png").touch()
    bundled = _create_executable(tmp_path / "_internal/vendor/tesseract/tesseract.exe")
    for code in ("eng", "pol"):
        _create_executable(bundled.parent / "tessdata" / f"{code}.traineddata")
    external = tmp_path / "host_tessdata"
    _create_executable(external / "nor.traineddata")
    monkeypatch.setenv("TESSDATA_PREFIX", str(external))
    assert ocr.TesseractEngine().available()
    assert not ocr.TesseractEngine().uses_bundled_engine()
    spec = importlib.util.spec_from_file_location("ocryon.core.qualification", QUALIFICATION)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ocryon.core.qualification", module)
    spec.loader.exec_module(module)
    assert module.run_selftest() == 21
    _create_executable(bundled.parent / "tessdata" / "nor.traineddata")
    assert ocr.TesseractEngine().uses_bundled_engine()
