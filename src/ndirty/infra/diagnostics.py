"""Local-only runtime diagnostics; no image data is read or transmitted."""

import hashlib
import shutil
import sys
from pathlib import Path

import onnxruntime as ort

from ndirty.infra.paths import application_root, model_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def report() -> str:
    """Return a human-readable diagnostics report without any user-image paths."""
    root = application_root()
    lama = model_path("lama", "inpainting_lama_2025jan.onnx")
    disk = shutil.disk_usage(root)
    try:
        lama_hash = _sha256(lama) if lama.is_file() else "缺失"
    except OSError:
        lama_hash = "无法读取"
    return "\n".join(
        (
            "NDirty 0.1.1",
            f"Python：{sys.version.split()[0]}（{sys.maxsize.bit_length() + 1} 位）",
            f"ONNX Runtime：{ort.__version__}",
            f"可用 provider：{', '.join(ort.get_available_providers())}",
            f"应用目录：{root}",
            f"应用目录大小：{_directory_size(root):,} 字节",
            f"磁盘可用空间：{disk.free:,} 字节",
            f"LaMa 模型：{'存在' if lama.is_file() else '缺失'}",
            f"LaMa SHA-256：{lama_hash}",
            "网络：未使用；诊断不会读取或发送图像内容。",
        )
    )
