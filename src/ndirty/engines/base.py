from dataclasses import dataclass

from PIL import Image


class InpaintError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class InpaintOptions:
    model_size: int = 512
    context_scale: float = 3.0
    minimum_context_pixels: int = 128


class InpaintEngine:
    def inpaint(self, image: Image.Image, mask: Image.Image, options: InpaintOptions | None = None) -> Image.Image:
        raise NotImplementedError
