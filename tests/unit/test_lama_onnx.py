from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ndirty.engines.base import InpaintError, InpaintOptions
from ndirty.engines.lama_onnx import LamaOnnxEngine


class FakeSession:
    def run(self, _outputs, inputs):
        assert inputs["image"].shape == (1, 3, 512, 512)
        assert inputs["mask"].shape == (1, 1, 512, 512)
        output = np.zeros((1, 3, 512, 512), dtype=np.float32)
        output[:, 0, :, :] = 255  # BGR blue -> RGB blue after conversion
        return [output]


def test_lama_composites_generated_pixels_only_inside_mask(tmp_path: Path) -> None:
    engine = LamaOnnxEngine(tmp_path / "unused.onnx")
    engine._session = FakeSession()  # type: ignore[assignment]
    image = Image.new("RGB", (4, 4), "red")
    mask = Image.new("L", (4, 4), 0)
    mask.putpixel((1, 1), 255)

    result = engine.inpaint(image, mask)

    assert result.getpixel((1, 1)) == (0, 0, 255)
    assert result.getpixel((0, 0)) == (255, 0, 0)


def test_lama_reports_missing_model_before_creating_session(tmp_path: Path) -> None:
    engine = LamaOnnxEngine(tmp_path / "missing.onnx")
    image = Image.new("RGB", (4, 4), "red")
    mask = Image.new("L", (4, 4), 255)
    with pytest.raises(InpaintError, match="未找到"):
        engine.inpaint(image, mask)


def test_lama_extracts_a_square_context_region_for_small_masks() -> None:
    image = Image.new("RGB", (1600, 900), "red")
    mask = Image.new("L", image.size, 0)
    mask.putpixel((800, 450), 255)

    region, region_mask, _box = LamaOnnxEngine._extract_context_region(image, mask, InpaintOptions())

    assert region.size == (128, 128)
    assert region_mask.size == (128, 128)
    assert region_mask.getbbox() is not None
