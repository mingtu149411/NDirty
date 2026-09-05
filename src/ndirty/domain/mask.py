"""Editable single-channel masks with bounded, patch-based undo history."""

from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw


@dataclass(frozen=True, slots=True)
class MaskPatch:
    box: tuple[int, int, int, int]
    before: Image.Image
    after: Image.Image


class MaskEditor:
    """Owns a L-mode mask. History stores only the modified bounding rectangle."""

    def __init__(self, size: tuple[int, int], mask: Image.Image | None = None, history_limit: int = 50) -> None:
        if mask is not None and mask.size != size:
            raise ValueError("mask size must match image size")
        self.mask = mask.convert("L").point(lambda value: 255 if value >= 128 else 0) if mask is not None else Image.new("L", size, 0)
        self._history_limit = history_limit
        self._undo: list[MaskPatch] = []
        self._redo: list[MaskPatch] = []
        self._active_before: Image.Image | None = None
        self._active_box: tuple[int, int, int, int] | None = None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def begin_action(self) -> None:
        if self._active_box is not None:
            raise RuntimeError("an edit action is already active")
        self._active_before = None
        self._active_box = None

    def draw_brush(self, start: tuple[float, float], end: tuple[float, float], radius: int, value: int) -> None:
        radius = max(1, int(radius))
        box = self._expand_box(
            (min(start[0], end[0]) - radius, min(start[1], end[1]) - radius,
             max(start[0], end[0]) + radius + 1, max(start[1], end[1]) + radius + 1)
        )
        self._capture_before(box)
        draw = ImageDraw.Draw(self.mask)
        draw.line([start, end], fill=value, width=radius * 2)
        for point in (start, end):
            draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=value)

    def fill_rectangle(self, start: tuple[float, float], end: tuple[float, float], value: int) -> None:
        box = self._expand_box((min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]) + 1, max(start[1], end[1]) + 1))
        self._capture_before(box)
        ImageDraw.Draw(self.mask).rectangle(box, fill=value)

    def fill_polygon(self, points: list[tuple[float, float]], value: int) -> None:
        if len(points) < 3:
            return
        xs, ys = zip(*points)
        box = self._expand_box((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
        self._capture_before(box)
        ImageDraw.Draw(self.mask).polygon(points, fill=value)

    def clear(self) -> bool:
        self.begin_action()
        self._capture_before((0, 0, *self.mask.size))
        self.mask.paste(0, (0, 0, *self.mask.size))
        return self.commit_action()

    def commit_action(self) -> bool:
        if self._active_box is None or self._active_before is None:
            self._active_box = None
            self._active_before = None
            return False
        after = self.mask.crop(self._active_box)
        changed = ImageChops.difference(self._active_before, after).getbbox() is not None
        if changed:
            self._undo.append(MaskPatch(self._active_box, self._active_before, after))
            if len(self._undo) > self._history_limit:
                self._undo.pop(0)
            self._redo.clear()
        self._active_box = None
        self._active_before = None
        return changed

    def undo(self) -> bool:
        if not self._undo:
            return False
        patch = self._undo.pop()
        self.mask.paste(patch.before, patch.box)
        self._redo.append(patch)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        patch = self._redo.pop()
        self.mask.paste(patch.after, patch.box)
        self._undo.append(patch)
        return True

    def replace_mask(self, mask: Image.Image) -> bool:
        if mask.size != self.mask.size:
            raise ValueError("mask size must match image size")
        self.begin_action()
        self._capture_before((0, 0, *self.mask.size))
        self.mask = mask.convert("L").copy()
        return self.commit_action()

    def _capture_before(self, requested: tuple[float, float, float, float]) -> None:
        box = self._normalize_box(requested)
        if box is None:
            return
        if self._active_box is None:
            self._active_box = box
            self._active_before = self.mask.crop(box)
            return
        combined = self._union_box(self._active_box, box)
        if combined == self._active_box:
            return
        current_before = self.mask.crop(combined)
        offset = (self._active_box[0] - combined[0], self._active_box[1] - combined[1])
        current_before.paste(self._active_before, offset)
        self._active_box = combined
        self._active_before = current_before

    def _expand_box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        normalized = self._normalize_box(box)
        if normalized is None:
            return (0, 0, 0, 0)
        return normalized

    def _normalize_box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int] | None:
        width, height = self.mask.size
        left = max(0, min(width, int(box[0])))
        top = max(0, min(height, int(box[1])))
        right = max(0, min(width, int(box[2]) + 1))
        bottom = max(0, min(height, int(box[3]) + 1))
        return (left, top, right, bottom) if left < right and top < bottom else None

    @staticmethod
    def _union_box(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return min(first[0], second[0]), min(first[1], second[1]), max(first[2], second[2]), max(first[3], second[3])
