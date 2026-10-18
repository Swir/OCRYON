"""Regression: an interrupted Windows portable pack must not destroy last good ZIP."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest


def _builder():
    script = Path(__file__).resolve().parents[1] / "tools" / "build_on_windows_preview.py"
    spec = importlib.util.spec_from_file_location("ocryon_windows_builder_atomic", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _environment(tmp_path: Path, monkeypatch):
    builder = _builder()
    root = tmp_path / "ocryon"
    dist = root / "dist" / "OCRYON"
    dist.mkdir(parents=True)
    exe = dist / "OCRYON.exe"
    exe.write_bytes(b"TEST ONLY: not an executable")
    (dist / "_internal").mkdir()
    (dist / "_internal" / "engine.dat").write_bytes(b"engine fixture")
    portable = root / "OCRYON-0.2.0-DEV-Windows-x64-PORTABLE.zip"
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "PACKAGE", portable)
    return builder, exe, portable


def test_failed_zip_write_preserves_previous_qualified_artifacts(tmp_path, monkeypatch):
    builder, exe, portable = _environment(tmp_path, monkeypatch)
    # This is an existing verified output from an earlier build, not part of
    # the new candidate. Never overwrite it if the NEW build cannot complete.
    with zipfile.ZipFile(portable, "w") as z:
        z.writestr("OCRYON.exe", b"previous build")
    previous = portable.read_bytes()
    sha_sidecar = portable.with_name(portable.name + ".sha256")
    checksum = hashlib.sha256(previous).hexdigest()
    sha_sidecar.write_text(f"{checksum}  {portable.name}\n", encoding="ascii")
    previous_sidecar = sha_sidecar.read_bytes()

    with patch.object(zipfile.ZipFile, "write", side_effect=OSError("simulated disk failure")):
        with pytest.raises(OSError, match="simulated disk failure"):
            builder.package(exe)

    assert portable.read_bytes() == previous
    assert sha_sidecar.read_bytes() == previous_sidecar
    assert zipfile.ZipFile(portable).testzip() is None


def test_success_replaces_portable_with_verified_complete_build(tmp_path, monkeypatch):
    builder, exe, portable = _environment(tmp_path, monkeypatch)
    with zipfile.ZipFile(portable, "w") as z:
        z.writestr("OCRYON.exe", b"previous build")

    builder.package(exe)
    with zipfile.ZipFile(portable) as z:
        assert z.testzip() is None
        assert z.read("OCRYON.exe") == exe.read_bytes()
        assert z.read("_internal/engine.dat") == b"engine fixture"
    actual_hash = hashlib.sha256(portable.read_bytes()).hexdigest()
    assert (portable.parent / (portable.name + ".sha256")).read_text(
        encoding="ascii"
    ) == f"{actual_hash}  {portable.name}\n"
