import cv2
import numpy as np
from PIL import Image


def grabcut_candidate(image: Image.Image, rectangle: tuple[int, int, int, int]) -> Image.Image:
    """Produce a local foreground candidate; the caller must ask user confirmation."""
    rgb = np.asarray(image.convert("RGB"))
    x1, y1, x2, y2 = rectangle
    x, y = max(0, min(x1, x2)), max(0, min(y1, y2))
    width, height = min(rgb.shape[1] - x, abs(x2 - x1)), min(rgb.shape[0] - y, abs(y2 - y1))
    if width < 2 or height < 2:
        raise ValueError("智能选区框过小。")
    labels = np.zeros(rgb.shape[:2], np.uint8)
    background, foreground = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(rgb, labels, (x, y, width, height), background, foreground, 3, cv2.GC_INIT_WITH_RECT)
    selected = np.where((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    return Image.fromarray(selected, "L")
