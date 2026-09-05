"""Application entry point. Keep Qt imports here so domain tests stay lightweight."""

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from ndirty.ui.main_window import MainWindow
    from ndirty.infra.logging_setup import configure_logging

    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("NDirty")
    window = MainWindow()
    window.show()
    return application.exec()
