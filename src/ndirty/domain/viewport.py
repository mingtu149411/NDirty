"""Pure coordinate helpers shared by the canvas and future mask tools."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


def screen_to_image(point: Point, *, scale: float, pan: Point) -> Point:
    """Convert a viewport point to original-image pixels without rounding."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    return Point(x=(point.x - pan.x) / scale, y=(point.y - pan.y) / scale)


def image_to_screen(point: Point, *, scale: float, pan: Point) -> Point:
    if scale <= 0:
        raise ValueError("scale must be positive")
    return Point(x=point.x * scale + pan.x, y=point.y * scale + pan.y)
