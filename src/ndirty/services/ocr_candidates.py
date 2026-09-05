from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from rapidocr import RapidOCR

from ndirty.infra.paths import model_path


@dataclass(frozen=True, slots=True)
class TextCandidate:
    points: tuple[tuple[float, float], ...]
    text: str
    confidence: float


class LocalOcrCandidates:
    """Offline OCR. Callers must explicitly confirm candidates before masking."""

    def __init__(self) -> None:
        self._engine: RapidOCR | None = None

    def detect(self, image: Image.Image) -> list[TextCandidate]:
        if self._engine is None:
            self._engine = RapidOCR(params={"Global.model_root_dir": str(model_path("ocr")), "Global.log_level": "error"})
        result = self._engine(np.asarray(image.convert("RGB")))
        if result.boxes is None or result.txts is None or result.scores is None:
            return []
        return [TextCandidate(tuple((float(x), float(y)) for x, y in box), text, float(score)) for box, text, score in zip(result.boxes, result.txts, result.scores) if score >= 0.5]
