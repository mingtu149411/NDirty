"""Portable .ndirty project persistence. Source images remain outside the project."""

import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image


class ProjectError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NDirtyProject:
    source_path: Path
    source_sha256: str
    mask: Image.Image


def save_project(path: Path, *, source_path: Path, mask: Image.Image) -> None:
    """Atomically save only metadata and mask; never copy the source image."""
    if mask.mode != "L":
        mask = mask.convert("L")
    metadata = {"format_version": 1, "source_path": str(source_path.resolve()), "source_sha256": _sha256(source_path), "mask_size": list(mask.size)}
    mask_data = BytesIO()
    mask.save(mask_data, format="PNG")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_handle = tempfile.NamedTemporaryFile(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent, delete=False)
    temp_path = Path(temp_handle.name)
    temp_handle.close()
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            archive.writestr("mask.png", mask_data.getvalue())
        os.replace(temp_path, path)
    except OSError as error:
        temp_path.unlink(missing_ok=True)
        raise ProjectError("无法保存项目文件。请检查目标目录写入权限和磁盘空间。") from error


def load_project(path: Path) -> NDirtyProject:
    try:
        with zipfile.ZipFile(path) as archive:
            metadata = json.loads(archive.read("project.json"))
            with Image.open(BytesIO(archive.read("mask.png"))) as image:
                mask = image.convert("L").copy()
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        raise ProjectError("无法读取 .ndirty 项目。文件可能损坏或格式不兼容。") from error
    source_path = Path(metadata.get("source_path", ""))
    expected_size = tuple(metadata.get("mask_size", []))
    if len(expected_size) != 2 or mask.size != expected_size:
        raise ProjectError("项目蒙版尺寸无效。")
    return NDirtyProject(source_path, str(metadata.get("source_sha256", "")), mask)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
