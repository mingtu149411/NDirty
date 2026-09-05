from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QStackedWidget,
)
from PySide6.QtCore import Qt

from ndirty.domain.document import ImageDocument, ImageLoadError, open_image_document
from ndirty.domain.project import ProjectError, load_project, save_project
from ndirty.engines.lama_onnx import LamaOnnxEngine
from ndirty.services.export_image import export_image
from ndirty.services.inpaint_worker import InpaintWorker
from ndirty.services.ocr_candidates import LocalOcrCandidates
from ndirty.services.smart_selection import grabcut_candidate
from ndirty.infra.diagnostics import report as diagnostics_report
from ndirty.ui.image_canvas import ImageCanvas


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.document: ImageDocument | None = None
        self.project_path: Path | None = None
        self.result_image: Image.Image | None = None
        self.inpaint_worker: InpaintWorker | None = None
        self.ocr = LocalOcrCandidates()
        self.is_dirty = False
        self.setWindowTitle("NDirty — 未打开图像")
        self.resize(1100, 760)
        self._create_canvas()
        self._create_actions()
        self._create_toolbar()
        self._create_workflow_dock()
        self._create_advanced_menu()
        self._create_status_bar()
        self.setAcceptDrops(True)

    def open_image_dialog(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "打开本地图像", "", "图像文件 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if selected:
            self.open_image(Path(selected))

    def open_image(self, path: Path) -> bool:
        try:
            document = open_image_document(path)
        except ImageLoadError as error:
            QMessageBox.warning(self, "无法打开图像", str(error))
            return False
        self.document = document
        self.project_path = None
        self.canvas.set_document(document)
        self.result_image = None
        self.is_dirty = False
        self._set_document_status(document)
        self.workspace.setCurrentWidget(self.canvas)
        self._refresh_workflow()
        return True

    def open_project_dialog(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "打开 NDirty 项目", "", "NDirty 项目 (*.ndirty)")
        if selected:
            self.open_project(Path(selected))

    def open_project(self, project_path: Path) -> bool:
        try:
            project = load_project(project_path)
        except ProjectError as error:
            QMessageBox.warning(self, "无法打开项目", str(error))
            return False
        source_path = project.source_path
        if not source_path.is_file():
            selected, _ = QFileDialog.getOpenFileName(self, "原图已移动，请重新定位", "", "图像文件 (*.png *.jpg *.jpeg *.webp *.bmp)")
            if not selected:
                return False
            source_path = Path(selected)
        if not self.open_image(source_path) or self.document is None:
            return False
        if project.mask.size != (self.document.width, self.document.height):
            QMessageBox.warning(self, "无法打开项目", "项目蒙版尺寸与原图不一致。")
            return False
        self.canvas.set_mask(project.mask)
        self.project_path = project_path
        self.is_dirty = False
        self.privacy_status.setText("项目已恢复；仅本地处理，未上传图像")
        self._refresh_workflow()
        return True

    def save_project_dialog(self) -> None:
        if self.document is None or self.canvas.mask is None:
            QMessageBox.information(self, "无法保存项目", "请先打开图像。")
            return
        destination = self.project_path
        if destination is None:
            selected, _ = QFileDialog.getSaveFileName(self, "保存 NDirty 项目", "", "NDirty 项目 (*.ndirty)")
            if not selected:
                return
            destination = Path(selected).with_suffix(".ndirty")
        try:
            save_project(destination, source_path=self.document.source_path, mask=self.canvas.mask)
        except ProjectError as error:
            QMessageBox.warning(self, "无法保存项目", str(error))
            return
        self.project_path = destination
        self.is_dirty = False
        self.privacy_status.setText("项目已保存；仅本地处理，未上传图像")

    def import_mask_dialog(self) -> None:
        if self.document is None:
            QMessageBox.information(self, "无法导入蒙版", "请先打开图像。")
            return
        selected, _ = QFileDialog.getOpenFileName(self, "导入蒙版", "", "PNG 蒙版 (*.png)")
        if not selected:
            return
        try:
            with Image.open(selected) as loaded:
                mask = loaded.convert("L").copy()
            if mask.size != (self.document.width, self.document.height):
                raise ValueError("蒙版尺寸必须与原图完全一致。")
            self.canvas.import_mask(mask)
        except (OSError, UnidentifiedImageError, ValueError) as error:
            QMessageBox.warning(self, "无法导入蒙版", str(error))

    def export_mask_dialog(self) -> None:
        if self.document is None:
            return
        selected, _ = QFileDialog.getSaveFileName(self, "导出蒙版", "mask.png", "PNG 蒙版 (*.png)")
        if not selected:
            return
        try:
            self.canvas.export_mask(Path(selected).with_suffix(".png"))
        except OSError as error:
            QMessageBox.warning(self, "无法导出蒙版", str(error))

    def clear_mask_confirmed(self) -> None:
        if self.document is None:
            return
        answer = QMessageBox.question(self, "清空蒙版", "确定清空当前全部蒙版吗？此操作可以通过撤销恢复。")
        if answer == QMessageBox.StandardButton.Yes:
            self.canvas.clear_mask()

    def generate_result(self) -> None:
        if self.document is None or self.canvas.mask is None:
            QMessageBox.information(self, "无法补全", "请先打开图像并标记需要补全的区域。")
            return
        if self.canvas.mask.getbbox() is None:
            QMessageBox.information(self, "无法补全", "请先在图像上标记需要补全的区域。")
            return
        self.inpaint_worker = InpaintWorker(LamaOnnxEngine(), self.document.image, self.canvas.mask)
        self.inpaint_worker.completed.connect(self._on_result_ready)
        self.inpaint_worker.failed.connect(self._on_result_failed)
        self.inpaint_worker.finished.connect(self._on_worker_finished)
        self.generate_action.setEnabled(False)
        self.cancel_action.setEnabled(True)
        self.workflow_generate.setEnabled(False)
        self.workflow_steps[2].setText("3. 正在本地补全图像…")
        self.privacy_status.setText("正在本地执行 LaMa 补全…")
        self.inpaint_worker.start()

    def detect_text_candidates(self) -> None:
        if self.document is None:
            QMessageBox.information(self, "无法检测", "请先打开图像。")
            return
        try:
            candidates = self.ocr.detect(self.document.image)
        except Exception as error:
            QMessageBox.warning(self, "文字检测失败", str(error))
            return
        self.canvas.set_text_candidates(candidates)
        self.privacy_status.setText(f"检测到 {len(candidates)} 个文字候选；点击框选中后再应用。")

    def apply_text_candidates(self) -> None:
        count = self.canvas.apply_selected_candidates()
        self.privacy_status.setText(f"已将 {count} 个候选合并为蒙版。" if count else "请先点击选择至少一个候选框。")

    def invert_text_candidates(self) -> None:
        count = self.canvas.invert_candidate_selection()
        self.privacy_status.setText(f"已反选 {count} 个文字候选。" if count else "当前没有文字候选可反选。")

    def clear_text_candidates(self) -> None:
        self.canvas.clear_candidates()
        self.privacy_status.setText("已清除文字候选，未修改蒙版。")

    def create_smart_candidate(self, rectangle: object) -> None:
        if self.document is None or not isinstance(rectangle, tuple) or len(rectangle) != 4:
            return
        try:
            candidate = grabcut_candidate(self.document.image, rectangle)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "智能选区失败", str(error))
            return
        if candidate.getbbox() is None:
            self.privacy_status.setText("未找到可用前景；请框得更紧一些后重试。")
            return
        self.canvas.set_smart_candidate(candidate)
        self.privacy_status.setText("已生成青色智能选区预览；检查后点击“应用智能选区”。")

    def apply_smart_candidate(self) -> None:
        if self.canvas.apply_smart_candidate():
            self.privacy_status.setText("已将智能选区合并为蒙版。")
        else:
            self.privacy_status.setText("当前没有可应用的智能选区，或它未新增蒙版区域。")

    def clear_smart_candidate(self) -> None:
        self.canvas.clear_smart_candidate()
        self.privacy_status.setText("已清除智能选区预览，未修改蒙版。")

    def cancel_generation(self) -> None:
        if self.inpaint_worker is not None:
            self.inpaint_worker.requestInterruption()
            self.privacy_status.setText("已请求取消；当前推理步骤完成后不会应用结果。")
            self.cancel_action.setEnabled(False)

    def export_result_dialog(self) -> None:
        if self.result_image is None or self.document is None:
            QMessageBox.information(self, "无法导出", "请先生成补全结果。")
            return
        default = str(self.document.source_path.with_name(f"{self.document.source_path.stem}_ndirty.png"))
        selected, _ = QFileDialog.getSaveFileName(self, "导出补全结果", default, "PNG 图像 (*.png);;JPEG 图像 (*.jpg *.jpeg)")
        if not selected:
            return
        destination = Path(selected)
        if destination.resolve() == self.document.source_path.resolve():
            QMessageBox.warning(self, "无法导出", "为保护原图，导出文件不能覆盖输入图片。")
            return
        if not destination.suffix:
            destination = destination.with_suffix(".png")
        try:
            export_image(self.result_image, destination)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法导出", str(error))
            return
        self.privacy_status.setText(f"已导出结果：{destination.name}")

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.canvas.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.canvas.dropEvent(event)

    def _create_canvas(self) -> None:
        self.canvas = ImageCanvas()
        self.canvas.image_dropped.connect(self.open_image)
        self.canvas.zoom_changed.connect(self._show_zoom)
        self.canvas.history_changed.connect(self._update_history_actions)
        self.canvas.mask_changed.connect(self._mark_dirty)
        self.canvas.smart_box_selected.connect(self.create_smart_candidate)
        self.workspace = QStackedWidget()
        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setContentsMargins(80, 60, 80, 60)
        welcome_layout.addStretch(1)
        eyebrow = QLabel("NDIRTY · 本地图像补全")
        eyebrow.setStyleSheet("color: #4fc3f7; font-weight: bold;")
        title = QLabel("从一张图片开始，完成遮挡区域。")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")
        description = QLabel("1. 导入图片  →  2. 涂抹遮挡区域  →  3. 补全图像  →  4. 导出结果\n\n无需先保存或导入蒙版；项目保存仅用于日后继续编辑。全部处理都在本机离线完成，原图不会被覆盖。")
        description.setWordWrap(True)
        start = QPushButton("导入图片开始")
        start.setMinimumHeight(42)
        start.setStyleSheet("font-size: 16px; font-weight: bold;")
        start.clicked.connect(self.open_image_dialog)
        welcome_layout.addWidget(eyebrow)
        welcome_layout.addWidget(title)
        welcome_layout.addWidget(description)
        welcome_layout.addSpacing(20)
        welcome_layout.addWidget(start, 0, Qt.AlignmentFlag.AlignLeft)
        welcome_layout.addStretch(2)
        self.workspace.addWidget(welcome)
        self.workspace.addWidget(self.canvas)
        self.setCentralWidget(self.workspace)

    def _create_actions(self) -> None:
        self.open_action = QAction("打开图像", self, shortcut=QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_image_dialog)
        self.open_project_action = QAction("打开项目", self)
        self.open_project_action.triggered.connect(self.open_project_dialog)
        self.save_project_action = QAction("保存项目", self, shortcut=QKeySequence.StandardKey.Save)
        self.save_project_action.triggered.connect(self.save_project_dialog)
        self.undo_action = QAction("撤销", self, shortcut=QKeySequence.StandardKey.Undo, enabled=False)
        self.undo_action.triggered.connect(self.canvas.undo)
        self.redo_action = QAction("重做", self, shortcut=QKeySequence.StandardKey.Redo, enabled=False)
        self.redo_action.triggered.connect(self.canvas.redo)
        self.import_mask_action = QAction("导入蒙版", self)
        self.import_mask_action.triggered.connect(self.import_mask_dialog)
        self.export_mask_action = QAction("导出蒙版", self)
        self.export_mask_action.triggered.connect(self.export_mask_dialog)
        self.clear_mask_action = QAction("清空蒙版", self)
        self.clear_mask_action.triggered.connect(self.clear_mask_confirmed)
        self.generate_action = QAction("补全图像", self)
        self.generate_action.triggered.connect(self.generate_result)
        self.cancel_action = QAction("取消补全", self, enabled=False)
        self.cancel_action.triggered.connect(self.cancel_generation)
        self.show_original_action = QAction("原图", self)
        self.show_original_action.triggered.connect(self.canvas.show_original)
        self.show_result_action = QAction("结果", self)
        self.show_result_action.triggered.connect(self.canvas.show_result)
        self.export_result_action = QAction("导出结果", self)
        self.export_result_action.triggered.connect(self.export_result_dialog)
        self.detect_text_action = QAction("检测文字", self)
        self.detect_text_action.triggered.connect(self.detect_text_candidates)
        self.apply_text_action = QAction("应用候选", self)
        self.apply_text_action.triggered.connect(self.apply_text_candidates)
        self.invert_text_action = QAction("反选候选", self)
        self.invert_text_action.triggered.connect(self.invert_text_candidates)
        self.clear_text_action = QAction("清除文字候选", self)
        self.clear_text_action.triggered.connect(self.clear_text_candidates)
        self.apply_smart_action = QAction("应用智能选区", self)
        self.apply_smart_action.triggered.connect(self.apply_smart_candidate)
        self.clear_smart_action = QAction("清除智能选区", self)
        self.clear_smart_action.triggered.connect(self.clear_smart_candidate)
        self.diagnostics_action = QAction("本地诊断", self)
        self.diagnostics_action.triggered.connect(self.show_diagnostics)
        self.fit_action = QAction("适配窗口", self, triggered=self.canvas.fit_image)
        self.zoom_100_action = QAction("100%", self, triggered=self.canvas.zoom_100)
        self.zoom_in_action = QAction("放大", self, shortcut=QKeySequence.StandardKey.ZoomIn, triggered=self.canvas.zoom_in)
        self.zoom_out_action = QAction("缩小", self, shortcut=QKeySequence.StandardKey.ZoomOut, triggered=self.canvas.zoom_out)
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_actions: dict[str, QAction] = {}
        for name, label in (("brush", "画笔"), ("eraser", "橡皮"), ("rectangle", "矩形"), ("lasso", "套索"), ("smart_box", "智能框选")):
            action = QAction(label, self, checkable=True)
            action.setData(name)
            action.triggered.connect(lambda checked=False, tool=name: self.canvas.set_tool(tool))
            self.tool_group.addAction(action)
            self.tool_actions[name] = action
        self.tool_actions["brush"].setChecked(True)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("主要操作", self)
        toolbar.setMovable(False)
        for action in (self.open_action, self.undo_action, self.redo_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        for action in self.tool_actions.values():
            toolbar.addAction(action)
        self.brush_size = QSpinBox()
        self.brush_size.setRange(1, 512)
        self.brush_size.setValue(16)
        self.brush_size.setPrefix("笔刷 ")
        self.brush_size.setSuffix(" px")
        self.brush_size.valueChanged.connect(self.canvas.set_brush_radius)
        toolbar.addWidget(self.brush_size)
        self.overlay_opacity = QSlider(Qt.Orientation.Horizontal)
        self.overlay_opacity.setRange(0, 255)
        self.overlay_opacity.setValue(120)
        self.overlay_opacity.setToolTip("蒙版显示透明度")
        self.overlay_opacity.valueChanged.connect(self.canvas.set_overlay_alpha)
        toolbar.addWidget(self.overlay_opacity)
        toolbar.addSeparator()
        for action in (self.clear_mask_action, self.generate_action, self.cancel_action, self.show_original_action, self.show_result_action, self.export_result_action, self.fit_action, self.zoom_100_action):
            toolbar.addAction(action)
        self.result_opacity = QSlider(Qt.Orientation.Horizontal)
        self.result_opacity.setRange(0, 255)
        self.result_opacity.setValue(255)
        self.result_opacity.setToolTip("结果/原图叠加对比")
        self.result_opacity.valueChanged.connect(self.canvas.set_result_opacity)
        toolbar.addWidget(self.result_opacity)
        self.addToolBar(toolbar)

    def _create_workflow_dock(self) -> None:
        dock = QDockWidget("快速流程", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        heading = QLabel("四步完成补全")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        hint = QLabel("无需先保存蒙版。保存项目只用于下次继续编辑。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #777;")
        self.workflow_steps: list[QLabel] = []
        for text in ("1. 导入一张本地图像", "2. 用画笔涂红需要补全的区域", "3. 补全图像", "4. 检查并导出结果"):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setMargin(8)
            label.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Plain)
            self.workflow_steps.append(label)
            layout.addWidget(label)
        self.workflow_open = QPushButton("1. 导入图片")
        self.workflow_open.clicked.connect(self.open_image_dialog)
        self.workflow_generate = QPushButton("3. 补全图像")
        self.workflow_generate.setMinimumHeight(42)
        self.workflow_generate.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.workflow_generate.clicked.connect(self.generate_result)
        self.workflow_export = QPushButton("4. 导出结果")
        self.workflow_export.clicked.connect(self.export_result_dialog)
        layout.insertWidget(2, self.workflow_open)
        layout.insertWidget(5, self.workflow_generate)
        layout.addWidget(self.workflow_export)
        layout.addStretch(1)
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.workflow_dock = dock
        self._refresh_workflow()

    def _create_advanced_menu(self) -> None:
        menu = self.menuBar().addMenu("项目与辅助工具")
        for action in (self.open_project_action, self.save_project_action, self.import_mask_action, self.export_mask_action):
            menu.addAction(action)
        menu.addSeparator()
        for action in (self.detect_text_action, self.apply_text_action, self.invert_text_action, self.clear_text_action, self.apply_smart_action, self.clear_smart_action):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.diagnostics_action)

    def _create_status_bar(self) -> None:
        status = QStatusBar(self)
        self.file_status = QLabel("未打开图像")
        self.zoom_status = QLabel("100%")
        self.privacy_status = QLabel("仅本地处理，未上传图像")
        status.addWidget(self.file_status, 1)
        status.addPermanentWidget(self.zoom_status)
        status.addPermanentWidget(self.privacy_status)
        self.setStatusBar(status)

    def _set_document_status(self, document: ImageDocument) -> None:
        self.setWindowTitle(f"NDirty — {document.display_name}")
        self.file_status.setText(f"{document.display_name} · {document.size_label}")
        self.privacy_status.setText("仅本地处理，未上传图像")

    def _mark_dirty(self) -> None:
        if self.document is not None:
            self.is_dirty = True
        if self.result_image is not None:
            self.result_image = None
            self.canvas.show_original()
            self.privacy_status.setText("蒙版已修改；请重新补全以获得新结果。")
        self._refresh_workflow()

    def _refresh_workflow(self) -> None:
        opened = self.document is not None
        has_mask = opened and self.canvas.mask is not None and self.canvas.mask.getbbox() is not None
        has_result = self.result_image is not None
        if not hasattr(self, "workflow_steps"):
            return
        self.workflow_steps[0].setText("1. 已导入图片" if opened else "1. 导入一张本地图像")
        self.workflow_steps[1].setText("2. 已标记遮挡区域" if has_mask else "2. 用画笔涂红需要补全的区域")
        self.workflow_steps[2].setText("3. 已生成补全结果" if has_result else "3. 补全图像")
        self.workflow_steps[3].setText("4. 可导出结果" if has_result else "4. 检查并导出结果")
        self.workflow_open.setText("重新导入图片" if opened else "1. 导入图片")
        self.workflow_generate.setEnabled(bool(has_mask) and self.inpaint_worker is None)
        self.workflow_export.setEnabled(has_result)

    def show_diagnostics(self) -> None:
        QMessageBox.information(self, "NDirty 本地诊断", diagnostics_report())

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self.is_dirty:
            event.accept()
            return
        answer = QMessageBox.question(self, "未保存的蒙版", "当前蒙版修改尚未保存为 .ndirty 项目。仍要退出吗？")
        if answer == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

    def _show_zoom(self, percent: float) -> None:
        self.zoom_status.setText(f"{percent:.0f}%")

    def _update_history_actions(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_action.setEnabled(can_undo)
        self.redo_action.setEnabled(can_redo)

    def _on_result_ready(self, image: object) -> None:
        if self.inpaint_worker is None or self.inpaint_worker.isInterruptionRequested():
            return
        if not isinstance(image, Image.Image):
            self._on_result_failed("推理结果类型无效。")
            return
        self.result_image = image
        self.canvas.set_result(image)
        self.privacy_status.setText("补全完成；可使用原图/结果和透明度滑杆对比。")
        self._refresh_workflow()

    def _on_result_failed(self, message: str) -> None:
        self.privacy_status.setText("本地补全失败。")
        QMessageBox.warning(self, "补全失败", message)

    def _on_worker_finished(self) -> None:
        self.generate_action.setEnabled(True)
        self.cancel_action.setEnabled(False)
        worker = self.inpaint_worker
        self.inpaint_worker = None
        if worker is not None:
            worker.deleteLater()
        self._refresh_workflow()
