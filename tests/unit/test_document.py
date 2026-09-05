from pathlib import Path

import pytest
from PIL import Image

from ndirty.domain.document import (
    ImageLoadError,
    MAX_IMAGE_PIXELS,
    is_supported_image_path,
    open_image_document,
    validate_dimensions,
)


def test_supported_extensions_are_case_insensitive() -> None:
    assert is_supported_image_path(Path("photo.JPEG"))
    assert is_supported_image_path(Path("photo.webp"))
    assert not is_supported_image_path(Path("photo.tiff"))


def test_open_image_document_reads_metadata_without_rewriting_source(tmp_path: Path) -> None:
    source = tmp_path / "示例 图片.png"
    Image.new("RGB", (4, 3), "red").save(source)
    original_bytes = source.read_bytes()
    document = open_image_document(source)
    assert document.source_path == source.resolve()
    assert (document.width, document.height) == (4, 3)
    assert document.image.mode == "RGB"
    assert source.read_bytes() == original_bytes


def test_unsupported_file_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "image.tiff"
    source.write_bytes(b"not an image")
    with pytest.raises(ImageLoadError, match="不支持"):
        open_image_document(source)


def test_oversized_dimensions_are_rejected_without_resizing() -> None:
    with pytest.raises(ImageLoadError, match="超过"):
        validate_dimensions(MAX_IMAGE_PIXELS + 1, 1)
