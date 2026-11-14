"""Вікно «Про програму»."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from core import about
from gui import theme

LOGO_SIZE = 96


def app_logo(size: int = LOGO_SIZE) -> QPixmap:
    """Іконка застосунку: сертифікат зі стрічкою на синьому градієнті."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size * scale

    gradient = QLinearGradient(0, 0, 0, s)
    gradient.setColorAt(0, QColor("#3A8DFF"))
    gradient.setColorAt(1, QColor("#0057D9"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0, 0, s, s), s * 0.225, s * 0.225)

    painter.setBrush(QColor("white"))
    painter.drawRoundedRect(QRectF(s * 0.2, s * 0.24, s * 0.6, s * 0.44), s * 0.04, s * 0.04)
    painter.setPen(QPen(QColor("#B8C7DD"), s * 0.025, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for y in (0.36, 0.44, 0.52):
        painter.drawLine(QPointF(s * 0.3, s * y), QPointF(s * 0.7, s * y))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFB800"))
    painter.drawEllipse(QRectF(s * 0.56, s * 0.56, s * 0.2, s * 0.2))
    ribbon = [(0.58, 0.72), (0.62, 0.86), (0.66, 0.78), (0.70, 0.86), (0.74, 0.72)]
    painter.drawPolygon(QPolygonF([QPointF(s * x, s * y) for x, y in ribbon]))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Про програму")
        self.setFixedWidth(380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 30, 32, 24)
        layout.setSpacing(6)

        logo = QLabel()
        logo.setPixmap(app_logo())
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addSpacing(10)

        title = QLabel(about.APP_NAME)
        title.setObjectName("PanelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        version = QLabel(f"Версія {about.APP_VERSION}")
        version.setObjectName("Hint")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        layout.addSpacing(14)

        for text, name in (
            (about.ORIGIN, "Caption"),
            (f"студентом {about.AUTHOR_INSTRUMENTAL}" + (f", група {about.GROUP}" if about.GROUP else ""), None),
            (about.UNIVERSITY, None),
            (str(about.YEAR), "Hint"),
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if name:
                label.setObjectName(name)
            else:
                label.setStyleSheet(f"font-weight: 600; color: {theme.TEXT};")
            layout.addWidget(label)

        layout.addSpacing(18)
        close = QPushButton("Готово")
        close.setObjectName("Accent")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
