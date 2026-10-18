"""A portable OCR release must not package files outside its frozen dist tree."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import zipfile

import pytest


def _builder():
    script = Path(__file__).resolve().parents[1] / "tools" / "build_on_windows_preview.py"
    spec = importlib.util.spec_from_file_location("ocryon_portable_source_boundary", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portable_refuses_external_symlink_without_touching_qualified_zip(tmp_path, monkeypatch):
    builder = _builder()
    root = tmp_path / "build"
    frozen = root / "dist" / "OCRYON"
    frozen.mkdir(parents=True)
    exe = frozen / "OCRYON.exe"
    exe.write_bytes(b"TEST ONLY: Windows executable stand-in")

    # This file is NOT part of the build, but a pre-existing symlink to a
    # private local user's document would leak its full contents into public
    # portable distribution if zipfile.write() follows the symlink.
    private = tmp_path / "private-account-data.txt"
    private.write_text("TEST SECRET ACCOUNT DATA - MUST NEVER SHIP", encoding="utf-8")
    alias = frozen / "_internal" / "cached_model.dat"
    alias.parent.mkdir()
    try:
        alias.symlink_to(private)
    except (OSError, NotImplementedError):
        pytest.skip("Host cannot create file symlinks")

    candidate = root / "OCRYON-0.2.0-DEV-Windows-x64-PORTABLE.zip"
    with zipfile.ZipFile(candidate, "w") as z:
        z.writestr("OCRYON.exe", b"PREVIOUS GOOD BUILD")
    prior = candidate.read_bytes()
    sidecar = candidate.with_name(candidate.name + ".sha256")
    prior_hash = hashlib.sha256(prior).hexdigest()
    sidecar.write_text(f"{prior_hash}  {candidate.name}\n", encoding="ascii")
    prior_sidecar = sidecar.read_bytes()

    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "PACKAGE", candidate)
    with pytest.raises(RuntimeError, match="outside the frozen build|unsafe link"):
        builder.package(exe)
    assert candidate.read_bytes() == prior
    assert sidecar.read_bytes() == prior_sidecar
