import os
import tempfile
from pathlib import Path

from PIL import Image


def export_image(image: Image.Image, destination: Path, *, quality: int = 95) -> None:
    """Write a result through a sibling temporary file before replacing target."""
    suffix = destination.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("仅支持导出 PNG 或 JPEG。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=f".{destination.stem}-", suffix=suffix, dir=destination.parent, delete=False)
    temp_path = Path(handle.name)
    handle.close()
    try:
        if suffix == ".png":
            image.convert("RGB").save(temp_path, format="PNG")
        else:
            image.convert("RGB").save(temp_path, format="JPEG", quality=quality, optimize=True)
        os.replace(temp_path, destination)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
