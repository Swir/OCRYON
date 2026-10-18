"""The frozen Windows acceptance must test Unicode exports inside the EXE."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from ocryon.core import unicode_qualification


def test_unicode_selftest_fails_closed_without_leaking_private_errors(monkeypatch, capsys):
    def invalid_export():
        raise RuntimeError("C:/private/Zażółć/secret_document.pdf")

    monkeypatch.setattr(unicode_qualification, "_verify_unicode_round_trip", invalid_export)
    assert unicode_qualification.run_unicode_selftest() == 25
    output = capsys.readouterr().out
    assert "UNICODE SELFTEST FAIL" in output
    assert "secret_document" not in output


def test_native_frozen_gate_executes_five_modes_and_real_unicode_exports(tmp_path, monkeypatch):
    location = Path(__file__).resolve().parents[1] / "tools/native_rc_acceptance.py"
    spec = importlib.util.spec_from_file_location("_ocryon_native_rc_acceptance", location)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    exe = tmp_path / "OCRYON.exe"
    exe.write_bytes(b"stand-in executable; never run it in this Linux contract test")
    seen = []

    def run(argv, **kwargs):
        seen.append(argv[1])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    module._check_frozen(exe)
    assert seen == ["--self-test", "--self-test-unicode", "--self-test-qt", "--self-test-ui"]

    def failure(argv, **kwargs):
        return SimpleNamespace(returncode=25 if argv[1] == "--self-test-unicode" else 0)

    monkeypatch.setattr(module.subprocess, "run", failure)
    with pytest.raises(AssertionError, match="--self-test-unicode"):
        module._check_frozen(exe)


def test_frozen_qt_gate_fails_closed_when_cancel_lifecycle_breaks(monkeypatch, capsys):
    """Windows GUI proof cannot be faked by a successful startup-only smoke."""
    from ocryon.ui import qt_qualification

    def fail_qt():
        raise RuntimeError("C:/secret-user-document.pdf")

    monkeypatch.setattr(qt_qualification, "check_qt_lifecycle", fail_qt)
    assert qt_qualification.run_qt_selftest() == 26
    output = capsys.readouterr().out
    assert "QT SELFTEST FAIL" in output
    assert "secret-user-document" not in output


def test_executable_dispatch_keeps_gui_qa_isolated_from_headless_ocr(monkeypatch):
    """Only --self-test-qt may import Qt; headless commands stay lightweight."""
    import ast
    entry = Path(__file__).resolve().parents[1] / "src/ocryon/__main__.py"
    content = entry.read_text(encoding="utf-8")
    assert '["--self-test-qt"]' in content
    assert 'from ocryon.ui.qt_qualification import run_qt_selftest' in content
    assert content.index('if sys.argv[1:] == ["--self-test-qt"]:') > content.index('if sys.argv[1:] == ["--self-test-unicode"]:')
    ast.parse(content)
