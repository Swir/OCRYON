"""Install, qualify and remove only a fresh isolated OCRYON test installation."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile
import winreg

from native_rc_acceptance import _check_frozen

APP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{573CF662-76A6-4D06-95D2-230D617919A3}_is1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("installer", type=Path)
    parser.add_argument("--expected-exe", required=True, type=Path)
    parser.add_argument("--logs", required=True, type=Path)
    args = parser.parse_args()
    args.logs.mkdir(parents=True, exist_ok=True)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_KEY):
            raise RuntimeError("An OCRYON 0.2 installation exists; refusing to replace it during acceptance")
    except FileNotFoundError:
        pass
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryDirectory(prefix="OCRYON_install_test_") as temporary:
        root = Path(temporary).resolve()
        destination = root / "Zażółć_Ålesund" / "OCRYON"
        if not destination.resolve().is_relative_to(root) or destination.exists():
            raise RuntimeError("Installer test destination is not new and isolated")
        sentinel = root / "outside-installation.txt"
        sentinel.write_text("Preserve this independent file.", encoding="utf-8")
        subprocess.run([str(args.installer.resolve()), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/SP-",
                        "/NORESTART", "/CURRENTUSER", "/NOICONS", "/TASKS=",
                        f"/DIR={destination}", f"/LOG={args.logs.resolve() / 'install.log'}"],
                       check=True, timeout=180, creationflags=flags)
        exe = destination / "OCRYON.exe"
        uninstaller = destination / "unins000.exe"
        try:
            if hashlib.sha256(exe.read_bytes()).digest() != hashlib.sha256(args.expected_exe.read_bytes()).digest():
                raise AssertionError("Installed EXE differs from qualified portable EXE")
            _check_frozen(exe)
            print("PASS: installed binary identity, OCR, Unicode exports, Qt lifecycle and GUI workflow")
        finally:
            if uninstaller.is_file() and uninstaller.resolve().is_relative_to(root):
                subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                f"/LOG={args.logs.resolve() / 'uninstall.log'}"],
                               check=True, timeout=90, creationflags=flags)
        if exe.exists() or not sentinel.is_file():
            raise AssertionError("Installer removal did not preserve the isolated boundary")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_KEY):
            raise AssertionError("Test uninstall registry entry remains")
    except FileNotFoundError:
        pass
    print("PASS: uninstall removed the test installation and preserved the outside sentinel")


if __name__ == "__main__":
    main()
