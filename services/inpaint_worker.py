from PIL import Image
from PySide6.QtCore import QThread, Signal

from ndirty.engines.base import InpaintEngine


class InpaintWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, engine: InpaintEngine, image: Image.Image, mask: Image.Image) -> None:
        super().__init__()
        self._engine = engine
        self._image = image.copy()
        self._mask = mask.copy()

    def run(self) -> None:
        try:
            self.completed.emit(self._engine.inpaint(self._image, self._mask))
        except Exception as error:
            self.failed.emit(str(error))
