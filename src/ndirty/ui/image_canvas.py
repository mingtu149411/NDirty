from pathlib import Path

from PIL import Image, ImageChops
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QMouseEvent, QPainterPath, QPen, QPixmap, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsScene, QGraphicsView

from ndirty.domain.document import ImageDocument, is_supported_image_path
from ndirty.domain.mask import MaskEditor


class ImageCanvas(QGraphicsView):
    """Original-image canvas with an editable red inpainting-mask overlay."""

    image_dropped = Signal(Path)
    zoom_changed = Signal(float)
    mask_changed = Signal()
    history_changed = Signal(bool, bool)
    smart_box_selected = Signal(object)

    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        super().__init__(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._result_item: QGraphicsPixmapItem | None = None
        self._mask_item: QGraphicsPixmapItem | None = None
        self._preview_item: QGraphicsPathItem | None = None
        self._candidate_items: list[QGraphicsPolygonItem] = []
        self._smart_candidate_item: QGraphicsPixmapItem | None = None
        self._smart_candidate_mask: Image.Image | None = None
        self._editor: MaskEditor | None = None
        self._tool = "brush"
        self._brush_radius = 16
        self._overlay_alpha = 120
        self._drawing = False
        self._start: tuple[float, float] | None = None
        self._last: tuple[float, float] | None = None
        self._lasso_points: list[tuple[float, float]] = []
        self._space_down = False
        self.setAcceptDrops(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)

    @property
    def mask(self) -> Image.Image | None:
        return self._editor.mask.copy() if self._editor is not None else None

    def set_document(self, document: ImageDocument) -> None:
        self._scene.clear()
        self._candidate_items.clear()
        self._smart_candidate_item = None
        self._smart_candidate_mask = None
        self._pixmap_item = self._scene.addPixmap(QPixmap.fromImage(ImageQt(document.image)))
        self._result_item = self._scene.addPixmap(QPixmap())
        self._result_item.setZValue(0.5)
        self._result_item.setVisible(False)
        self._mask_item = self._scene.addPixmap(QPixmap())
        self._mask_item.setZValue(1)
        self._editor = MaskEditor((document.width, document.height))
        self._scene.setSceneRect(QRectF(0, 0, document.width, document.height))
        self._refresh_mask_overlay()
        self.fit_image()
        self._emit_history()

    def set_mask(self, mask: Image.Image) -> None:
        if self._editor is None:
            raise ValueError("open an image before setting a mask")
        self._editor = MaskEditor(mask.size, mask)
        self._refresh_mask_overlay()
        self._emit_history()

    def set_result(self, image: Image.Image) -> None:
        if self._editor is None or image.size != self._editor.mask.size or self._result_item is None:
            raise ValueError("result size must match the opened image")
        self._result_item.setPixmap(QPixmap.fromImage(ImageQt(image.convert("RGB"))))
        self._result_item.setVisible(True)
        if self._mask_item is not None:
            self._mask_item.setVisible(False)

    def show_original(self) -> None:
        if self._result_item is not None:
            self._result_item.setVisible(False)
        if self._mask_item is not None:
            self._mask_item.setVisible(True)

    def show_result(self) -> None:
        if self._result_item is not None and not self._result_item.pixmap().isNull():
            self._result_item.setVisible(True)
        if self._mask_item is not None:
            self._mask_item.setVisible(False)

    def set_result_opacity(self, opacity: int) -> None:
        if self._result_item is not None:
            self._result_item.setOpacity(max(0, min(255, opacity)) / 255)

    def set_tool(self, tool: str) -> None:
        if tool not in {"brush", "eraser", "rectangle", "lasso", "smart_box"}:
            raise ValueError(f"unknown tool: {tool}")
        self._tool = tool

    def set_text_candidates(self, candidates) -> None:  # type: ignore[no-untyped-def]
        self.clear_candidates()
        for candidate in candidates:
            polygon = QPolygonF([QPointF(x, y) for x, y in candidate.points])
            item = self._scene.addPolygon(polygon, QPen(QColor("#ffca28"), 2))
            item.setZValue(3)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            item.setData(0, candidate)
            self._candidate_items.append(item)

    def apply_selected_candidates(self) -> int:
        if self._editor is None:
            return 0
        selected = [item for item in self._candidate_items if item.isSelected()]
        if not selected:
            return 0
        self._editor.begin_action()
        for item in selected:
            candidate = item.data(0)
            self._editor.fill_polygon(list(candidate.points), 255)
        changed = self._editor.commit_action()
        self.clear_candidates()
        self._after_edit(changed)
        return len(selected) if changed else 0

    def clear_candidates(self) -> None:
        for item in self._candidate_items:
            self._scene.removeItem(item)
        self._candidate_items.clear()

    def invert_candidate_selection(self) -> int:
        for item in self._candidate_items:
            item.setSelected(not item.isSelected())
        return len(self._candidate_items)

    def set_smart_candidate(self, mask: Image.Image) -> None:
        if self._editor is None or mask.size != self._editor.mask.size:
            raise ValueError("智能选区尺寸必须与当前图像一致")
        self.clear_smart_candidate()
        self._smart_candidate_mask = mask.convert("L").copy()
        alpha = self._smart_candidate_mask.point(lambda pixel: pixel * 110 // 255)
        overlay = Image.new("RGBA", mask.size, (0, 188, 212, 0))
        overlay.putalpha(alpha)
        self._smart_candidate_item = self._scene.addPixmap(QPixmap.fromImage(ImageQt(overlay)))
        self._smart_candidate_item.setZValue(2)

    def apply_smart_candidate(self) -> bool:
        if self._editor is None or self._smart_candidate_mask is None:
            return False
        combined = ImageChops.lighter(self._editor.mask, self._smart_candidate_mask)
        changed = combined.tobytes() != self._editor.mask.tobytes()
        if changed:
            self._editor.replace_mask(combined)
        self.clear_smart_candidate()
        self._after_edit(changed)
        return changed

    def clear_smart_candidate(self) -> None:
        if self._smart_candidate_item is not None:
            self._scene.removeItem(self._smart_candidate_item)
            self._smart_candidate_item = None
        self._smart_candidate_mask = None

    def set_brush_radius(self, radius: int) -> None:
        self._brush_radius = max(1, radius)

    def set_overlay_alpha(self, alpha: int) -> None:
        self._overlay_alpha = max(0, min(255, alpha))
        self._refresh_mask_overlay()

    def import_mask(self, mask: Image.Image) -> None:
        if self._editor is None:
            raise ValueError("open an image before importing a mask")
        self._editor.replace_mask(mask)
        self._refresh_mask_overlay()
        self.mask_changed.emit()
        self._emit_history()

    def export_mask(self, path: Path) -> None:
        if self._editor is None:
            raise ValueError("open an image before exporting a mask")
        self._editor.mask.save(path, format="PNG")

    def clear_mask(self) -> bool:
        if self._editor is None:
            return False
        changed = self._editor.clear()
        self._after_edit(changed)
        return changed

    def undo(self) -> bool:
        if self._editor is None:
            return False
        changed = self._editor.undo()
        self._after_edit(changed)
        return changed

    def redo(self) -> bool:
        if self._editor is None:
            return False
        changed = self._editor.redo()
        self._after_edit(changed)
        return changed

    def fit_image(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self._emit_zoom()

    def zoom_100(self) -> None:
        self.resetTransform()
        self._emit_zoom()

    def zoom_in(self) -> None:
        self._zoom_by(1.2)

    def zoom_out(self) -> None:
        self._zoom_by(1 / 1.2)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap_item is None:
            event.ignore()
            return
        self._zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._editor is None or event.button() != Qt.MouseButton.LeftButton or self._space_down:
            super().mousePressEvent(event)
            return
        point = self._image_point(event)
        if point is None:
            return
        self._drawing = True
        self._start = self._last = point
        self._lasso_points = [point]
        if self._tool in {"brush", "eraser"}:
            self._editor.begin_action()
            self._editor.draw_brush(point, point, self._brush_radius, 255 if self._tool == "brush" else 0)
            self._refresh_mask_overlay()
        else:
            self._begin_preview(point)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._drawing or self._editor is None:
            super().mouseMoveEvent(event)
            return
        point = self._image_point(event)
        if point is None:
            return
        if self._tool in {"brush", "eraser"} and self._last is not None:
            self._editor.draw_brush(self._last, point, self._brush_radius, 255 if self._tool == "brush" else 0)
            self._refresh_mask_overlay()
        elif self._tool in {"rectangle", "smart_box"} and self._start is not None:
            self._update_rectangle_preview(self._start, point)
        elif self._tool == "lasso":
            self._lasso_points.append(point)
            self._update_lasso_preview()
        self._last = point
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._drawing or self._editor is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        point = self._image_point(event) or self._last
        changed = False
        if point is not None:
            if self._tool in {"brush", "eraser"}:
                changed = self._editor.commit_action()
            elif self._tool == "rectangle" and self._start is not None:
                self._editor.begin_action()
                self._editor.fill_rectangle(self._start, point, 255)
                changed = self._editor.commit_action()
            elif self._tool == "smart_box" and self._start is not None:
                self.smart_box_selected.emit((int(self._start[0]), int(self._start[1]), int(point[0]), int(point[1])))
            elif self._tool == "lasso":
                self._editor.begin_action()
                self._editor.fill_polygon(self._lasso_points, 255)
                changed = self._editor.commit_action()
        self._drawing = False
        self._start = self._last = None
        self._lasso_points = []
        self._clear_preview()
        self._after_edit(changed)
        event.accept()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._first_supported_drop_path(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._first_supported_drop_path(event)
        if path is None:
            event.ignore()
            return
        self.image_dropped.emit(path)
        event.acceptProposedAction()

    def current_zoom_percent(self) -> float:
        return self.transform().m11() * 100

    def _image_point(self, event: QMouseEvent) -> tuple[float, float] | None:
        if self._editor is None:
            return None
        point = self.mapToScene(event.position().toPoint())
        width, height = self._editor.mask.size
        if not (0 <= point.x() < width and 0 <= point.y() < height):
            return None
        return point.x(), point.y()

    def _after_edit(self, changed: bool) -> None:
        if changed:
            self._refresh_mask_overlay()
            self.mask_changed.emit()
        self._emit_history()

    def _refresh_mask_overlay(self) -> None:
        if self._editor is None or self._mask_item is None:
            return
        alpha = self._editor.mask.point(lambda pixel: pixel * self._overlay_alpha // 255)
        overlay = Image.new("RGBA", self._editor.mask.size, (255, 0, 0, 0))
        overlay.putalpha(alpha)
        self._mask_item.setPixmap(QPixmap.fromImage(ImageQt(overlay)))

    def _begin_preview(self, point: tuple[float, float]) -> None:
        self._preview_item = self._scene.addPath(QPainterPath())
        self._preview_item.setZValue(2)
        self._preview_item.setPen(QPen(QColor("#ffd54f"), 2))
        self._preview_item.setBrush(Qt.BrushStyle.NoBrush)
        self._update_rectangle_preview(point, point)

    def _update_rectangle_preview(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        if self._preview_item is None:
            return
        path = QPainterPath()
        path.addRect(QRectF(min(start[0], end[0]), min(start[1], end[1]), abs(end[0] - start[0]), abs(end[1] - start[1])))
        self._preview_item.setPath(path)

    def _update_lasso_preview(self) -> None:
        if self._preview_item is None or not self._lasso_points:
            return
        path = QPainterPath()
        path.moveTo(*self._lasso_points[0])
        for point in self._lasso_points[1:]:
            path.lineTo(*point)
        self._preview_item.setPath(path)

    def _clear_preview(self) -> None:
        if self._preview_item is not None:
            self._scene.removeItem(self._preview_item)
            self._preview_item = None

    def _zoom_by(self, factor: float) -> None:
        next_scale = self.transform().m11() * factor
        if 0.02 <= next_scale <= 32:
            self.scale(factor, factor)
            self._emit_zoom()

    def _emit_zoom(self) -> None:
        self.zoom_changed.emit(self.current_zoom_percent())

    def _emit_history(self) -> None:
        self.history_changed.emit(self._editor.can_undo if self._editor else False, self._editor.can_redo if self._editor else False)

    @staticmethod
    def _first_supported_drop_path(event: QDragEnterEvent | QDropEvent) -> Path | None:
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = Path(urls[0].toLocalFile())
        return path if is_supported_image_path(path) else None
