"""Image document loading and validation, independent of the Qt UI."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

SUPPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})
MAX_IMAGE_PIXELS = 100_000_000


class ImageLoadError(ValueError):
    """An input image could not be safely opened for local editing."""


def is_supported_image_path(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def validate_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ImageLoadError("图像尺寸无效。")
    if width * height > MAX_IMAGE_PIXELS:
        raise ImageLoadError(
            f"图像包含 {width * height:,} 像素，超过当前 {MAX_IMAGE_PIXELS:,} 像素上限。"
            "请使用尺寸更小的副本后再导入；NDirty 不会自动缩小原图。"
        )


@dataclass(frozen=True, slots=True)
class ImageDocument:
    """An immutable record of a locally opened source image."""

    source_path: Path
    image: Image.Image
    width: int
    height: int

    @property
    def display_name(self) -> str:
        return self.source_path.name

    @property
    def size_label(self) -> str:
        return f"{self.width} × {self.height} px"


def open_image_document(path: Path) -> ImageDocument:
    """Decode an approved local image without ever writing to its source path."""

    if not path.is_file():
        raise ImageLoadError("找不到所选图像文件。")
    if not is_supported_image_path(path):
        supported = "、".join(sorted(suffix.removeprefix(".").upper() for suffix in SUPPORTED_SUFFIXES))
        raise ImageLoadError(f"不支持该文件格式。可导入：{supported}。")

    try:
        with Image.open(path) as opened:
            width, height = opened.size
            validate_dimensions(width, height)
            opened.load()
            image = opened.convert("RGB")
    except (OSError, UnidentifiedImageError) as error:
        raise ImageLoadError("无法读取该图像。文件可能已损坏或格式不受支持。") from error

    return ImageDocument(source_path=path.resolve(), image=image, width=width, height=height)
