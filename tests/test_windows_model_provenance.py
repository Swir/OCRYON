"""Release-critical: --list-langs is not proof that a model is usable/untampered."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest


def _builder():
    script = Path(__file__).resolve().parents[1] / "tools" / "build_on_windows_preview.py"
    spec = importlib.util.spec_from_file_location("ocryon_model_provenance", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejects_bad_cached_models_even_when_real_tesseract_lists_all_languages(tmp_path, monkeypatch):
    engine = shutil.which("tesseract")
    if not engine:
        pytest.skip("Requires real Tesseract to demonstrate --list-langs false positive")
    builder = _builder()
    vendor = tmp_path / "vendor" / "tesseract"
    models = vendor / "tessdata"
    models.mkdir(parents=True)
    binary = vendor / "tesseract.exe"
    shutil.copy2(engine, binary)
    for code in ("eng", "pol", "nor"):
        (models / f"{code}.traineddata").write_bytes(b"CORRUPT-SCAN-MODEL-" + code.encode())

    actual = subprocess.run(
        [str(binary), "--tessdata-dir", str(models), "--list-langs"],
        text=True, capture_output=True, check=True,
    )
    assert {"eng", "pol", "nor"}.issubset(set((actual.stdout + actual.stderr).split()))

    monkeypatch.setattr(builder, "VENDOR", vendor)
    monkeypatch.setattr(builder, "CACHE", tmp_path / "isolated-cache")
    # Isolate the release qualification gate from network and the Windows
    # installer. The simulated pinned installer emits an engine plus corrupt
    # bundled models, just as an interrupted/invalid download could.
    def fake_pinned_installer(installer, runtime):
        runtime.mkdir(parents=True, exist_ok=True)
        shutil.copy2(engine, runtime / "tesseract.exe")
        runtime.joinpath("tesseract.exe").chmod(0o755)
        for code in ("eng", "pol", "nor"):
            target = runtime / "tessdata" / f"{code}.traineddata"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"CORRUPT-SCAN-MODEL-" + code.encode())

    monkeypatch.setattr(builder, "extract_runtime_without_installing", fake_pinned_installer)
    monkeypatch.setattr(builder, "download", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="(?i)integrity|model.*mismatch"):
        builder.make_tesseract()


def _blob_sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def test_exact_git_blob_file_integrity_rejects_tampered_cached_model(tmp_path):
    builder = _builder()
    model = tmp_path / "eng.traineddata"
    good = b"fixture-binary-model-\x00\xff" * 15
    model.write_bytes(good)
    pinned = _blob_sha(good)
    builder.verify_git_blob_sha1(model, pinned)
    model.write_bytes(good + b"malicious padding")
    with pytest.raises(RuntimeError, match="integrity"):
        builder.verify_git_blob_sha1(model, pinned)


def test_downloader_validates_new_model_before_installing(tmp_path, monkeypatch):
    import io
    import urllib.request

    builder = _builder()
    model = tmp_path / "pol.traineddata"
    model.write_bytes(b"old corrupt cached model")
    good = b"correct fixture from immutable commit"
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(good)
    )
    builder.download(
        "https://fixture.invalid/pol.traineddata", model,
        expected_git_blob_sha1=_blob_sha(good),
    )
    assert model.read_bytes() == good


def test_downloader_rejects_invalid_remote_bytes_without_overwriting_existing_file(tmp_path, monkeypatch):
    import io
    import urllib.request

    builder = _builder()
    model = tmp_path / "nor.traineddata"
    model.write_bytes(b"previous model left intact until replacement is verified")
    prior = model.read_bytes()
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"bad remote data")
    )
    with pytest.raises(RuntimeError, match="integrity"):
        builder.download(
            "https://fixture.invalid/nor.traineddata", model,
            expected_git_blob_sha1=_blob_sha(b"expected pinned contents"),
        )
    assert model.read_bytes() == prior
