"""One-click *Windows-hosted* OCRYON 0.2 development portable builder.

NOT a prebuilt Windows executable. Makes no GitHub, tag, Release or registry
changes. Requires Python 3.12 x64 and internet on the owner's Windows 11 PC.
The user must inspect and execute it on a trusted machine.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "_build_cache"
VENDOR = ROOT / "vendor" / "tesseract"
INSTALLER_URL = (
    "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/"
    "tesseract-ocr-w64-setup-5.5.3.20260724.exe"
)
INSTALLER_SHA256 = "bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4"
MODEL_COMMIT = "87416418657359cb625c412a48b6e1d6d41c29bd"
SEVENZIP_RELEASE = "https://github.com/ip7z/7zip/releases/download/26.04"
SEVENZR_SHA256 = "256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282"
SEVENZIP_SHA256 = "d54bf805f9f3704d1e8db2fa3498ae7ef2df0312b40b558e7c71c734430a665d"
# SHA-1 *Git blob identities* from the immutable tessdata_fast tree above.
# Git hashes include `blob <byte-count>\0`, NOT just the file contents.
# --list-langs only enumerates filenames and accepts corrupt .traineddata.
MODEL_GIT_BLOB_SHA1 = {
    "eng": "bbef4675053b5b468cdb477053e28b1c698ba08e",
    "pol": "2382f568f0ce0c4c0a7f4380a291255514e5e97f",
    "nor": "9209df2c9904c127437c07e16c287cdefd024e7c",
}
PACKAGE = ROOT / "OCRYON-0.2.0-Windows-x64-PORTABLE.zip"


def log(message: str) -> None:
    print(f"[OCRYON BUILDER] {message}", flush=True)


def invoke(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    log("Running: " + " ".join(map(str, args)))
    subprocess.run(args, cwd=cwd, env=env, check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def verify_sha256(path: Path, sha: str) -> None:
    actual = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    if actual.lower() != sha.lower():
        raise RuntimeError(f"SHA256 check failed for {path.name} (file rejected)")


def verify_git_blob_sha1(path: Path, expected_sha1: str) -> None:
    """Verify pinned Git blob identity, including the *exact* model byte count.

    Every cached/downloaded OCR model must match the pinned upstream tree.
    No model data, private paths or OCR text appear in validation errors.
    """
    try:
        with path.open("rb") as source:
            size = os.fstat(source.fileno()).st_size
            digest = hashlib.sha1(f"blob {size}\0".encode("ascii"), usedforsecurity=False)
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise RuntimeError("Pinned OCR language model integrity check failed") from None
    if digest.hexdigest() != expected_sha1.lower():
        raise RuntimeError("Pinned OCR language model integrity check failed")


def download(
    url: str, target: Path, *, expected_sha256: str | None = None,
    expected_git_blob_sha1: str | None = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if expected_sha256 or expected_git_blob_sha1:
            try:
                if expected_sha256:
                    verify_sha256(target, expected_sha256)
                if expected_git_blob_sha1:
                    verify_git_blob_sha1(target, expected_git_blob_sha1)
                return
            except RuntimeError:
                # A stale but nonempty .traineddata is NOT a qualified model.
                # Download into a separate .partial file and validate it.
                pass
        elif target.stat().st_size:
            return
    temp = target.with_suffix(target.suffix + ".partial")
    temp.unlink(missing_ok=True)
    log("Downloading " + target.name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OCRYON-0.2-DEV-builder"})
        with urllib.request.urlopen(req, timeout=120) as resp, temp.open("wb") as output:
            written = 0
            while chunk := resp.read(1024 * 1024):
                written += len(chunk)
                if written > 400 * 1024 * 1024:
                    raise RuntimeError("Download exceeded safe limit")
                output.write(chunk)
        if expected_sha256:
            verify_sha256(temp, expected_sha256)
        if expected_git_blob_sha1:
            verify_git_blob_sha1(temp, expected_git_blob_sha1)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def make_environment() -> Path:
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        log("Creating a dedicated local Python environment")
        venv.EnvBuilder(with_pip=True, clear=False).create(ROOT / ".venv")
    if not python.is_file():
        raise RuntimeError("Python environment creation failed")
    # Pinned packaging tools; application dependencies come from pyproject.toml.
    invoke(str(python), "-m", "pip", "install", "--disable-pip-version-check",
           "-c", "requirements-windows.lock", "-e", ".[dev]", "pyinstaller==6.22.3", "pyinstaller-hooks-contrib==2026.8")
    return python


def extract_runtime_without_installing(installer: Path, runtime: Path) -> None:
    """Unpack the SHA-verified installer without UAC or registry changes."""
    reader = CACHE / "7zr.exe"
    archive = CACHE / "7z2604-x64.exe"
    download(f"{SEVENZIP_RELEASE}/7zr.exe", reader, expected_sha256=SEVENZR_SHA256)
    download(f"{SEVENZIP_RELEASE}/7z2604-x64.exe", archive, expected_sha256=SEVENZIP_SHA256)
    with tempfile.TemporaryDirectory(dir=CACHE, prefix="7zip-extract-") as temporary:
        unpacker = Path(temporary)
        invoke(str(reader), "x", str(archive), f"-o{unpacker}", "-y")
        invoke(str(unpacker / "7z.exe"), "x", str(installer), f"-o{runtime}",
               "-y", "-x!$PLUGINSDIR", "-x!tesseract-uninstall.exe")


def make_tesseract() -> None:
    """Reconstruct the bundled OCR engine ONLY from the pinned installer.

    An old vendor/tesseract.exe alone is not proof of the release's engine
    identity: a stale or replaced binary/DLL can still report all language
    names and silently become part of the new frozen Windows EXE. A new
    release must use a clean installer extraction, never a merged cache.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    VENDOR.parent.mkdir(parents=True, exist_ok=True)
    # Do not follow a link/junction into some unrelated user directory while
    # reading cached models or replacing the vendor directory.
    is_junction = getattr(VENDOR, "is_junction", None)
    if VENDOR.is_symlink() or (is_junction is not None and is_junction()):
        raise RuntimeError("Bundled OCR runtime location is an unsafe link")
    if VENDOR.exists() and not VENDOR.is_dir():
        raise RuntimeError("Bundled OCR runtime location is not a directory")

    installer = CACHE / "tesseract-5.5.3-installer.exe"
    # This SHA pin applies even to an installer already in the local cache.
    download(INSTALLER_URL, installer, expected_sha256=INSTALLER_SHA256)

    # A fresh empty folder is crucial. Reusing a previous install directory,
    # or copying files over an old vendor, preserves arbitrary stale DLLs.
    with tempfile.TemporaryDirectory(
        dir=VENDOR.parent, prefix=".ocryon-runtime-stage-"
    ) as temporary:
        stage = Path(temporary)
        runtime = stage / "installed"
        runtime.mkdir()
        extract_runtime_without_installing(installer, runtime)
        if not (runtime / "tesseract.exe").is_file():
            raise RuntimeError("Pinned Tesseract installer did not create tesseract.exe")
        # Never import an installer-created filesystem link which might reach
        # into private host content at portable-bundle packaging time.
        for entry in runtime.rglob("*"):
            is_junction = getattr(entry, "is_junction", None)
            if entry.is_symlink() or (is_junction is not None and is_junction()):
                raise RuntimeError("Pinned OCR installer yielded an unsafe link")

        candidate = stage / "candidate"
        shutil.copytree(runtime, candidate)
        languages = candidate / "tessdata"
        languages.mkdir(parents=True, exist_ok=True)
        for code in ("eng", "pol", "nor"):
            target = languages / f"{code}.traineddata"
            # Preserve fast offline rebuilds ONLY for byte-exact verified
            # language models. All other stale caches must be replaced.
            previous = VENDOR / "tessdata" / f"{code}.traineddata"
            if previous.is_file() and not previous.is_symlink():
                try:
                    verify_git_blob_sha1(previous, MODEL_GIT_BLOB_SHA1[code])
                except RuntimeError:
                    pass
                else:
                    shutil.copy2(previous, target)
            download(
                f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{MODEL_COMMIT}/{code}.traineddata",
                target, expected_git_blob_sha1=MODEL_GIT_BLOB_SHA1[code],
            )
            verify_git_blob_sha1(target, MODEL_GIT_BLOB_SHA1[code])

        # Check the NEW staged engine, never the old vendor binary. A failed
        # install or broken engine must leave the prior vendor byte-identical.
        subprocess.run(
            [str(candidate / "tesseract.exe"), "--version"],
            cwd=candidate, text=True, capture_output=True, check=True,
        )
        # Exact model hashes were checked above. --list-langs only lists
        # filenames and fails on Unicode Windows directories. The frozen
        # smoke below must additionally recognize a real image in all modes.

        # Directory-level replacement prevents stale DLLs from surviving a
        # successful rebuild. Keep the old directory as a same-volume backup
        # until the new candidate has been installed; roll back on failure.
        # The backup is OUTSIDE TemporaryDirectory: if a Windows antivirus
        # locks the destination AND rollback, context cleanup must not delete
        # the user's previous valid engine. Leave it available for recovery.
        backup = VENDOR.parent / (stage.name + "-previous-vendor")
        had_previous = VENDOR.exists()
        if had_previous:
            VENDOR.rename(backup)
        try:
            candidate.rename(VENDOR)
        except OSError:
            if had_previous:
                try:
                    backup.rename(VENDOR)
                except OSError:
                    raise RuntimeError(
                        "Runtime replacement and recovery failed; the previous engine is in a backup"
                    ) from None
            raise
        else:
            if had_previous:
                shutil.rmtree(backup)

    log("Pinned, freshly installed Tesseract with ENG/PL/NOR available")


def make_icon(python: Path) -> Path:
    invoke(str(python), "tools/build_rc_icon.py")
    icon = ROOT / "build" / "ocryon.ico"
    source = ROOT / "build" / "ocryon.png"
    # Pillow belongs to the dedicated Windows venv, not the builder's host.
    icon_script = (
        "from PIL import Image; "
        "image=Image.open(r'build/ocryon.png'); "
        "image.save(r'build/ocryon.ico', format='ICO', "
        "sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    )
    invoke(str(python), "-c", icon_script)
    if not icon.is_file():
        raise RuntimeError("Could not create original OCRYON icon")
    return icon


def build_executable(python: Path, icon: Path) -> Path:
    # A build host may have unrelated ICU/Qt DLLs on PATH (for example from
    # Poppler). Qt 6 uses Windows' ICU; collecting a different icuuc.dll makes
    # the frozen QtCore fail even though source imports work.
    build_env = os.environ.copy()
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    build_env["PATH"] = os.pathsep.join(map(str, [python.parent, windows / "System32", windows]))
    invoke(
        str(python), "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "OCRYON", "--paths", "src", "--icon", str(icon),
        "--version-file", "packaging/windows-version.txt",
        "--add-data", "src\\ocryon\\assets\\ocryon.svg;ocryon\\assets",
        "--add-data", "build\\ocryon.png;ocryon\\assets",
        "src\\ocryon\\__main__.py",
        env=build_env,
    )
    exe = ROOT / "dist" / "OCRYON" / "OCRYON.exe"
    if not exe.is_file() or exe.stat().st_size < 50_000:
        raise RuntimeError("Windows OCRYON.exe was not produced correctly")
    # Tesseract runs as a separate process. Keep its complete runtime private
    # rather than letting PyInstaller hoist its DLLs into Qt's search path.
    shutil.copytree(VENDOR, exe.parent / "_internal" / "vendor" / "tesseract")
    return exe


def native_smoke(exe: Path) -> None:
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "windows")
    env["OCRYON_TESSERACT"] = str(ROOT / "nonexistent-host-tesseract.exe")
    env["TESSDATA_PREFIX"] = str(ROOT / "nonexistent-host-tessdata")
    for mode in ("--self-test", "--self-test-unicode", "--self-test-qt", "--self-test-ui"):
        log(f"Native Windows frozen test {mode}")
        result = subprocess.run(
            [str(exe), mode], cwd=exe.parent, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=180, check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Windows frozen qualification failed: {mode} exit={result.returncode}")
    log("Frozen OCR, real Unicode PDF, and native Qt/QThread checks passed")
    # A separate windowed startup smoke: terminated only after it stays live.
    log("Native GUI startup smoke")
    process = subprocess.Popen([str(exe)], cwd=exe.parent, env=env)
    try:
        time.sleep(6)
        if process.poll() is not None:
            raise RuntimeError(f"GUI exited during startup, exit={process.returncode}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=8)


def package(exe: Path) -> None:
    """Stage a fully verified portable archive before replacing any prior build.

    A disk-full/AV/access error while zipping must NEVER truncate a previously
    qualified Windows portable. The staged file lives on the same filesystem,
    so the final archive replace is atomic; the SHA sidecar is written from
    the complete staged archive and installed immediately afterward.
    """
    root = exe.parent
    # Never follow filesystem links or reparse-point junctions when building a
    # distributable archive. zipfile.write() dereferences file symlinks and
    # would silently copy private files OUTSIDE the frozen application tree.
    # The frozen PyInstaller onedir bundle should consist of ordinary files.
    def safe_portable_entry(path: Path) -> None:
        is_junction = getattr(path, "is_junction", None)
        if path.is_symlink() or (is_junction is not None and is_junction()):
            raise RuntimeError("Portable source contains an unsafe link")
        if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
            raise RuntimeError("Portable source points outside the frozen build")

    safe_portable_entry(root)
    with tempfile.TemporaryDirectory(
        dir=ROOT, prefix=".ocryon-portable-build-"
    ) as temporary:
        stage = Path(temporary)
        candidate = stage / PACKAGE.name
        staged_checksum = stage / (PACKAGE.name + ".sha256")
        expected_names = []
        with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path in sorted(root.rglob("*")):
                safe_portable_entry(path)
                if path.is_file():
                    arcname = path.relative_to(root).as_posix()
                    expected_names.append(arcname)
                    z.write(path, arcname)

        # Verify BOTH CRC and complete frozen source inventory before any
        # mutation of the previously working output.
        with zipfile.ZipFile(candidate) as z:
            if (
                z.testzip() is not None
                or "OCRYON.exe" not in z.namelist()
                or z.namelist() != expected_names
            ):
                raise RuntimeError("Portable ZIP integrity check failed")
        sha = hashlib.file_digest(candidate.open("rb"), "sha256").hexdigest()
        staged_checksum.write_text(
            f"{sha}  {PACKAGE.name}\n", encoding="ascii"
        )
        # A previous qualified ZIP stays byte-identical until the new one is
        # closed, readable, CRC-verified and checksum-staged.
        os.replace(candidate, PACKAGE)
        os.replace(staged_checksum, ROOT / (PACKAGE.name + ".sha256"))

    log(f"BUILD SUCCESS: {PACKAGE}")
    log(f"SHA256: {sha}")
    log("Extract the ZIP entirely, then launch OCRYON.exe. No installer required.")


def main() -> int:
    try:
        if sys.platform != "win32" or sys.maxsize <= 2**32:
            raise RuntimeError("This builder requires real 64-bit Windows (Windows 11 recommended)")
        if sys.version_info[:2] != (3, 12):
            raise RuntimeError("Install 64-bit Python 3.12 and run via `py -3.12`")
        os.chdir(ROOT)
        for required in ("src/ocryon/app.py", "src/ocryon/ui/main_window.py", "src/ocryon/ui/qt_qualification.py", "pyproject.toml"):
            if not (ROOT / required).is_file():
                raise RuntimeError(f"Source incomplete: {required}")
        py = make_environment()
        make_tesseract()
        icon = make_icon(py)
        exe = build_executable(py, icon)
        native_smoke(exe)
        invoke(str(py), "tools/bundle_notices.py")
        package(exe)
        return 0
    except Exception as exc:
        log(f"BUILD NOT QUALIFIED: {type(exc).__name__}: {exc}")
        log("No Windows EXE is claimed as tested until all frozen checks pass.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
