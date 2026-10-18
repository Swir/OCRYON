"""Collect installed dependency notices and a local build inventory."""
from __future__ import annotations

import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    destination = ROOT / "dist" / "OCRYON"
    licenses = destination / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    inventory = []
    for name in ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "PyMuPDF",
                 "Pillow", "python-docx", "lxml", "pytesseract", "packaging", "typing_extensions", "PyInstaller"):
        dist = metadata.distribution(name)
        inventory.append({"name": name, "version": dist.version,
                          "license": dist.metadata.get("License-Expression") or dist.metadata.get("License")})
        for entry in dist.files or ():
            relative = Path(str(entry))
            if ".dist-info" not in str(relative) or not any(word in relative.name.lower() for word in ("license", "copying", "copyright", "notice")):
                continue
            source = Path(dist.locate_file(entry))
            if source.is_file():
                target = licenses / name / relative.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    shutil.copytree(ROOT / "packaging" / "third-party", licenses / "standard-texts", dirs_exist_ok=True)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    shutil.copy2(ROOT / "vendor" / "tesseract" / "doc" / "LICENSE", licenses / "Tesseract-LICENSE.txt")
    shutil.copy2(ROOT / "packaging" / "THIRD-PARTY-NOTICES.txt", destination)
    shutil.copy2(ROOT / "packaging" / "START-HERE.txt", destination)
    shutil.copy2(ROOT / "packaging" / "SOURCE-DEPENDENCIES.json", destination)
    (destination / "DEPENDENCIES.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Include an owner-selected project license when one has been supplied.
    if (ROOT / "LICENSE").is_file():
        shutil.copy2(ROOT / "LICENSE", destination)


if __name__ == "__main__":
    main()
