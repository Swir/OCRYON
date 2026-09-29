from __future__ import annotations

from pathlib import Path
import sys


def asset_path(name: str) -> Path:
    source = Path(__file__).resolve().parent / "assets" / name
    if source.exists():
        return source

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "ocryon" / "assets" / name

    return source
