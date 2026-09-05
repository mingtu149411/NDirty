import sys
from pathlib import Path


def application_root() -> Path:
    """Locate bundled resources in PyInstaller and the editable source tree."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[3]


def model_path(*parts: str) -> Path:
    return application_root().joinpath("models", *parts)
