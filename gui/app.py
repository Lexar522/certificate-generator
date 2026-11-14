"""Точка входу редактора сертифікатів (PySide6)."""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from core.exceptions import CertificateError
from gui.main_window import MainWindow
from gui.theme import apply_theme

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("Сертифікати")
    apply_theme(app)

    try:
        window = MainWindow(TEMPLATES_DIR, OUTPUT_DIR)
    except CertificateError as exc:
        QMessageBox.critical(None, "Не вдалося запустити", str(exc))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
