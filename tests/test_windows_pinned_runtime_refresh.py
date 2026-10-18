"""Windows release packaging must never trust an arbitrary cached OCR executable.

Tests exercise the builder's real filesystem/process checks using shell executables
as cross-platform stand-ins for the installed Tesseract binary. They are NOT
native Windows executable qualification.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


def _builder():
    path = Path(__file__).resolve().parents[1] / "tools" / "build_on_windows_preview.py"
    spec = importlib.util.spec_from_file_location("ocryon_runtime_integrity", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _program(path: Path, label: str, *, succeeds: bool = True) -> None:
    script = ("# Python test fixture\n" + ("print('eng\\npol\\nnor')\n" if succeeds else "raise SystemExit(9)\n")
              + f"# provenance={label}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script, encoding="ascii")
    path.chmod(0o755)


def _fixture(tmp_path: Path, monkeypatch, *, installer_succeeds: bool = True, binary_succeeds: bool = True):
    builder = _builder()
    proxy = SimpleNamespace(**vars(subprocess))
    original_run = subprocess.run
    proxy.run = lambda argv, **kwargs: original_run(
        [sys.executable, str(argv[0]), *argv[1:]], **kwargs
    )
    monkeypatch.setattr(builder, "subprocess", proxy)
    vendor = tmp_path / "vendor" / "tesseract"
    vendor.mkdir(parents=True)
    old_binary = vendor / "tesseract.exe"
    _program(old_binary, "STALE-UNVERIFIED", succeeds=True)
    (vendor / "untrusted.dll").write_bytes(b"STALE LOCAL DLL")
    old_binary_bytes = old_binary.read_bytes()
    old_dll_bytes = (vendor / "untrusted.dll").read_bytes()

    cache = tmp_path / "_build_cache"
    monkeypatch.setattr(builder, "VENDOR", vendor)
    monkeypatch.setattr(builder, "CACHE", cache)
    expected_models = {code: b"trusted-model:" + code.encode("ascii") for code in ("eng", "pol", "nor")}
    monkeypatch.setattr(builder, "MODEL_GIT_BLOB_SHA1", {
        code: _git_blob_sha(data) for code, data in expected_models.items()
    })
    def downloader(url: str, target: Path, **kwargs):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.name.endswith("-installer.exe"):
            assert kwargs.get("expected_sha256") == builder.INSTALLER_SHA256
            target.write_bytes(b"PINNED TESSERACT INSTALLER FIXTURE")
        else:
            assert kwargs.get("expected_git_blob_sha1") == builder.MODEL_GIT_BLOB_SHA1[target.stem]
            target.write_bytes(expected_models[target.stem])

    monkeypatch.setattr(builder, "download", downloader)
    installed = []
    def installer_command(installer, install_dir):
        installed.append((installer, install_dir))
        if not installer_succeeds:
            raise OSError("Simulated installer abort")
        install_dir.mkdir(parents=True, exist_ok=True)
        _program(install_dir / "tesseract.exe", "PINNED-INSTALLER", succeeds=binary_succeeds)
        (install_dir / "trusted.dll").write_bytes(b"CLEAN DLL FROM INSTALLER")
    monkeypatch.setattr(builder, "extract_runtime_without_installing", installer_command)
    return builder, vendor, old_binary_bytes, old_dll_bytes, installed


def test_stale_vendor_executable_and_dll_are_replaced_from_pinned_installer(tmp_path, monkeypatch):
    builder, vendor, stale_exe, _, installs = _fixture(tmp_path, monkeypatch)
    builder.make_tesseract()
    assert len(installs) == 1, "Cached binary must never bypass the SHA-pinned installer"
    assert vendor.joinpath("tesseract.exe").read_bytes() != stale_exe
    assert b"PINNED-INSTALLER" in vendor.joinpath("tesseract.exe").read_bytes()
    assert vendor.joinpath("trusted.dll").read_bytes() == b"CLEAN DLL FROM INSTALLER"
    assert not vendor.joinpath("untrusted.dll").exists(), "Old DLL must not leak into new release"


def test_failed_pinned_runtime_install_preserves_previous_vendor(tmp_path, monkeypatch):
    builder, vendor, old_exe, old_dll, installs = _fixture(tmp_path, monkeypatch, installer_succeeds=False)
    with pytest.raises(OSError, match="Simulated installer abort"):
        builder.make_tesseract()
    assert len(installs) == 1
    assert vendor.joinpath("tesseract.exe").read_bytes() == old_exe
    assert vendor.joinpath("untrusted.dll").read_bytes() == old_dll


def test_staged_nonworking_binary_never_replaces_existing_vendor(tmp_path, monkeypatch):
    builder, vendor, old_exe, old_dll, installs = _fixture(tmp_path, monkeypatch, binary_succeeds=False)
    with pytest.raises(subprocess.CalledProcessError):
        builder.make_tesseract()
    assert len(installs) == 1
    assert vendor.joinpath("tesseract.exe").read_bytes() == old_exe
    assert vendor.joinpath("untrusted.dll").read_bytes() == old_dll
