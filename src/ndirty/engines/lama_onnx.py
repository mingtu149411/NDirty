from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from ndirty.engines.base import InpaintEngine, InpaintError, InpaintOptions
from ndirty.infra.paths import model_path


class LamaOnnxEngine(InpaintEngine):
    """CPU-only local inference for the bundled OpenCV LaMa ONNX model."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or model_path("lama", "inpainting_lama_2025jan.onnx")
        self._session: ort.InferenceSession | None = None

    def inpaint(self, image: Image.Image, mask: Image.Image, options: InpaintOptions | None = None) -> Image.Image:
        if image.size != mask.size:
            raise InpaintError("原图与蒙版尺寸不一致。")
        if mask.getbbox() is None:
            raise InpaintError("请先在图像上标记需要补全的区域。")
        session = self._get_session()
        settings = options or InpaintOptions()
        size = settings.model_size
        original = image.convert("RGB")
        region, region_mask, region_box = self._extract_context_region(original, mask.convert("L"), settings)
        input_image = region.resize((size, size), Image.Resampling.LANCZOS)
        input_mask = region_mask.resize((size, size), Image.Resampling.NEAREST)
        bgr = np.asarray(input_image, dtype=np.float32)[:, :, ::-1] / 255.0
        image_blob = np.ascontiguousarray(bgr.transpose(2, 0, 1)[None])
        mask_blob = np.ascontiguousarray((np.asarray(input_mask) > 0).astype(np.float32)[None, None])
        try:
            output = session.run(None, {"image": image_blob, "mask": mask_blob})[0]
        except Exception as error:  # onnxruntime errors vary by provider/version
            raise InpaintError(f"LaMa 推理失败：{error}") from error
        if output.ndim != 4 or output.shape[1] != 3:
            raise InpaintError("LaMa 模型输出格式不受支持。")
        generated_bgr = np.clip(output[0].transpose(1, 2, 0), 0, 255).astype(np.uint8)
        generated_region = Image.fromarray(generated_bgr[:, :, ::-1], "RGB").resize(region.size, Image.Resampling.LANCZOS)
        return self._composite_region(original, mask.convert("L"), generated_region, region_box)

    @staticmethod
    def _extract_context_region(
        image: Image.Image, mask: Image.Image, options: InpaintOptions
    ) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
        left, top, right, bottom = mask.getbbox() or (0, 0, *image.size)
        masked_span = max(right - left, bottom - top)
        side = max(options.minimum_context_pixels, int(masked_span * options.context_scale))
        side = min(max(image.size), side)
        center_x, center_y = (left + right) / 2, (top + bottom) / 2
        region_left = int(round(center_x - side / 2))
        region_top = int(round(center_y - side / 2))
        region_box = (region_left, region_top, region_left + side, region_top + side)
        image_array = np.asarray(image)
        pad_left, pad_top = max(0, -region_left), max(0, -region_top)
        pad_right = max(0, region_box[2] - image.width)
        pad_bottom = max(0, region_box[3] - image.height)
        pad_mode = "reflect" if image.width > 1 and image.height > 1 else "edge"
        padded_image = np.pad(image_array, ((pad_top, pad_bottom), (pad_left, pad_right), (0, 0)), mode=pad_mode)
        padded_mask = np.pad(np.asarray(mask), ((pad_top, pad_bottom), (pad_left, pad_right)), mode="constant")
        crop_left, crop_top = region_left + pad_left, region_top + pad_top
        crop_right, crop_bottom = crop_left + side, crop_top + side
        return (
            Image.fromarray(padded_image[crop_top:crop_bottom, crop_left:crop_right], "RGB"),
            Image.fromarray(padded_mask[crop_top:crop_bottom, crop_left:crop_right], "L"),
            region_box,
        )

    @staticmethod
    def _composite_region(
        original: Image.Image, mask: Image.Image, generated_region: Image.Image, region_box: tuple[int, int, int, int]
    ) -> Image.Image:
        left, top, right, bottom = region_box
        source_left, source_top = max(left, 0), max(top, 0)
        source_right, source_bottom = min(right, original.width), min(bottom, original.height)
        target_box = (source_left, source_top, source_right, source_bottom)
        generated_box = (source_left - left, source_top - top, source_right - left, source_bottom - top)
        result = original.copy()
        generated_crop = generated_region.crop(generated_box)
        mask_crop = mask.crop(target_box)
        original_crop = original.crop(target_box)
        result.paste(Image.composite(generated_crop, original_crop, mask_crop), target_box)
        return result

    def _get_session(self) -> ort.InferenceSession:
        if self._session is not None:
            return self._session
        if not self.path.is_file():
            raise InpaintError(f"未找到 LaMa 模型：{self.path}。请检查 models\\lama 目录。")
        try:
            session_options = ort.SessionOptions()
            session_options.log_severity_level = 3
            available = set(ort.get_available_providers())
            providers = [provider for provider in ("CUDAExecutionProvider", "CPUExecutionProvider") if provider in available]
            if "CPUExecutionProvider" not in providers:
                raise InpaintError("当前 ONNX Runtime 不提供 CPUExecutionProvider，无法进行本地补全。")
            self._session = ort.InferenceSession(str(self.path), sess_options=session_options, providers=providers)
        except Exception as error:
            raise InpaintError(f"无法加载 LaMa 模型：{error}") from error
        return self._session
