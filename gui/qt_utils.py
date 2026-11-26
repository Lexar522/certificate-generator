"""Конвертація Pillow → Qt та намальовані іконки (без зовнішніх файлів)."""

import math
from collections.abc import Callable

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

from gui import theme

ICON_SIZE = 32
TYPE_COLORS = {
    "text": "#0071E3",
    "image": "#34C759",
    "watermark": "#AF52DE",
    "qr": "#FF9500",
    "shape": "#FF2D55",
    "frame": "#C69214",
}
TYPE_NAMES = {
    "text": "Текст",
    "image": "Зображення",
    "watermark": "Водяний знак",
    "qr": "QR-код",
    "shape": "Фігура",
    "frame": "Рамка",
}


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())  # copy: QImage не володіє буфером bytes


def placeholder_pixmap(width: int, height: int, caption: str, color: str | None = None) -> QPixmap:
    """Пунктирна рамка з підписом — для змінних зображень і шарів з помилкою."""
    pixmap = QPixmap(max(1, width), max(1, height))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    accent = QColor(color or theme.ACCENT)
    fill = QColor(accent)
    fill.setAlpha(28)
    stroke = max(2.0, min(width, height) / 60)
    pen = QPen(accent, stroke, Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(fill)
    inset = stroke
    radius = min(width, height) / 10
    painter.drawRoundedRect(QRectF(inset, inset, width - 2 * inset, height - 2 * inset), radius, radius)
    font = QFont(theme.pick_font_family())
    font.setPixelSize(max(10, int(min(height / 5, width / max(6, len(caption) * 0.6)))))
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(accent)
    painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, caption)
    painter.end()
    return pixmap


def _round_pen(color: QColor, width: float) -> QPen:
    return QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _paint_icon(draw: Callable[[QPainter, float], None], size: int = ICON_SIZE) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)  # 2x для чіткості на HiDPI
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw(painter, size * 2)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def type_icon(kind: str) -> QIcon:
    color = QColor(TYPE_COLORS.get(kind, theme.TEXT_SECONDARY))

    def draw(painter: QPainter, s: float) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(0, 0, s, s), s * 0.24, s * 0.24)
        painter.setPen(_round_pen(QColor("white"), s * 0.07))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        _GLYPHS[kind](painter, s)

    return _paint_icon(draw)


def _glyph_text(painter: QPainter, s: float) -> None:
    painter.drawLine(QPointF(s * 0.28, s * 0.3), QPointF(s * 0.72, s * 0.3))
    painter.drawLine(QPointF(s * 0.5, s * 0.3), QPointF(s * 0.5, s * 0.74))


def _glyph_image(painter: QPainter, s: float) -> None:
    painter.drawRoundedRect(QRectF(s * 0.22, s * 0.26, s * 0.56, s * 0.48), s * 0.06, s * 0.06)
    path = QPainterPath(QPointF(s * 0.26, s * 0.68))
    path.lineTo(s * 0.42, s * 0.5)
    path.lineTo(s * 0.54, s * 0.62)
    path.lineTo(s * 0.62, s * 0.54)
    path.lineTo(s * 0.74, s * 0.68)
    painter.drawPath(path)
    painter.setBrush(QColor("white"))
    painter.drawEllipse(QPointF(s * 0.63, s * 0.38), s * 0.04, s * 0.04)


def _glyph_watermark(painter: QPainter, s: float) -> None:
    path = QPainterPath(QPointF(s * 0.5, s * 0.2))
    path.cubicTo(s * 0.5, s * 0.2, s * 0.26, s * 0.48, s * 0.26, s * 0.6)
    path.arcTo(QRectF(s * 0.26, s * 0.36, s * 0.48, s * 0.48), 180, 180)
    path.cubicTo(s * 0.74, s * 0.48, s * 0.5, s * 0.2, s * 0.5, s * 0.2)
    painter.drawPath(path)


def _glyph_qr(painter: QPainter, s: float) -> None:
    for x, y in ((0.22, 0.22), (0.56, 0.22), (0.22, 0.56)):
        painter.drawRoundedRect(QRectF(s * x, s * y, s * 0.22, s * 0.22), s * 0.03, s * 0.03)
    painter.setBrush(QColor("white"))
    painter.drawRect(QRectF(s * 0.6, s * 0.6, s * 0.14, s * 0.14))


def _glyph_shape(painter: QPainter, s: float) -> None:
    painter.drawRoundedRect(QRectF(s * 0.22, s * 0.22, s * 0.34, s * 0.34), s * 0.04, s * 0.04)
    painter.drawEllipse(QRectF(s * 0.4, s * 0.4, s * 0.38, s * 0.38))


def _glyph_frame(painter: QPainter, s: float) -> None:
    painter.drawRoundedRect(QRectF(s * 0.2, s * 0.24, s * 0.6, s * 0.52), s * 0.04, s * 0.04)
    painter.drawRect(QRectF(s * 0.3, s * 0.34, s * 0.4, s * 0.32))


_GLYPHS = {
    "text": _glyph_text,
    "image": _glyph_image,
    "watermark": _glyph_watermark,
    "qr": _glyph_qr,
    "shape": _glyph_shape,
    "frame": _glyph_frame,
}


def line_icon(name: str, color: str | None = None) -> QIcon:
    """Лінійні іконки для панелей інструментів."""
    pen_color = QColor(color or theme.TEXT_SECONDARY)

    def draw(painter: QPainter, s: float) -> None:
        painter.setPen(_round_pen(pen_color, s * 0.075))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        _LINE_GLYPHS[name](painter, s)

    return _paint_icon(draw, 18)


def _undo(painter: QPainter, s: float, mirror: bool = False) -> None:
    if mirror:
        painter.translate(s, 0)
        painter.scale(-1, 1)
    path = QPainterPath(QPointF(s * 0.3, s * 0.42))
    path.lineTo(s * 0.62, s * 0.42)
    path.arcTo(QRectF(s * 0.46, s * 0.42, s * 0.34, s * 0.34), 90, -180)
    path.lineTo(s * 0.4, s * 0.76)
    painter.drawPath(path)
    painter.drawLine(QPointF(s * 0.3, s * 0.42), QPointF(s * 0.44, s * 0.28))
    painter.drawLine(QPointF(s * 0.3, s * 0.42), QPointF(s * 0.44, s * 0.56))


def _eye(painter: QPainter, s: float, closed: bool = False) -> None:
    path = QPainterPath(QPointF(s * 0.14, s * 0.5))
    path.quadTo(s * 0.5, s * 0.1, s * 0.86, s * 0.5)
    path.quadTo(s * 0.5, s * 0.9, s * 0.14, s * 0.5)
    painter.drawPath(path)
    painter.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.12, s * 0.12)
    if closed:
        painter.drawLine(QPointF(s * 0.2, s * 0.8), QPointF(s * 0.8, s * 0.2))


def _plus(painter: QPainter, s: float) -> None:
    painter.drawLine(QPointF(s * 0.5, s * 0.22), QPointF(s * 0.5, s * 0.78))
    painter.drawLine(QPointF(s * 0.22, s * 0.5), QPointF(s * 0.78, s * 0.5))


def _minus(painter: QPainter, s: float) -> None:
    painter.drawLine(QPointF(s * 0.22, s * 0.5), QPointF(s * 0.78, s * 0.5))


def _arrow(painter: QPainter, s: float, up: bool) -> None:
    tip, base = (0.22, 0.78) if up else (0.78, 0.22)
    painter.drawLine(QPointF(s * 0.5, s * tip), QPointF(s * 0.5, s * base))
    wing = 0.2 if up else -0.2
    painter.drawLine(QPointF(s * 0.5, s * tip), QPointF(s * 0.3, s * (tip + wing)))
    painter.drawLine(QPointF(s * 0.5, s * tip), QPointF(s * 0.7, s * (tip + wing)))


def _duplicate(painter: QPainter, s: float) -> None:
    painter.drawRoundedRect(QRectF(s * 0.2, s * 0.2, s * 0.42, s * 0.42), s * 0.08, s * 0.08)
    painter.drawRoundedRect(QRectF(s * 0.38, s * 0.38, s * 0.42, s * 0.42), s * 0.08, s * 0.08)


def _fit(painter: QPainter, s: float) -> None:
    for x, y, dx, dy in ((0.2, 0.2, 1, 1), (0.8, 0.2, -1, 1), (0.2, 0.8, 1, -1), (0.8, 0.8, -1, -1)):
        painter.drawLine(QPointF(s * x, s * y), QPointF(s * (x + 0.18 * dx), s * y))
        painter.drawLine(QPointF(s * x, s * y), QPointF(s * x, s * (y + 0.18 * dy)))


def _refresh(painter: QPainter, s: float) -> None:
    painter.drawArc(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56), 30 * 16, 300 * 16)
    painter.drawLine(QPointF(s * 0.74, s * 0.18), QPointF(s * 0.75, s * 0.36))
    painter.drawLine(QPointF(s * 0.75, s * 0.36), QPointF(s * 0.57, s * 0.36))


def _info(painter: QPainter, s: float) -> None:
    painter.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.34, s * 0.34)
    painter.drawLine(QPointF(s * 0.5, s * 0.46), QPointF(s * 0.5, s * 0.66))
    painter.drawPoint(QPointF(s * 0.5, s * 0.34))


def _lock(painter: QPainter, s: float, open_: bool = False) -> None:
    painter.drawRoundedRect(QRectF(s * 0.26, s * 0.46, s * 0.48, s * 0.36), s * 0.06, s * 0.06)
    shackle = QRectF(s * 0.34, s * 0.18, s * 0.32, s * 0.4)
    if open_:
        shackle.translate(s * 0.14, -s * 0.04)
    painter.drawArc(shackle, 0, 180 * 16)
    painter.drawLine(QPointF(shackle.left(), shackle.center().y()), QPointF(shackle.left(), s * 0.46 if not open_ else shackle.center().y()))
    painter.drawLine(QPointF(shackle.right(), shackle.center().y()), QPointF(shackle.right(), s * 0.46))


def _sun(painter: QPainter, s: float) -> None:
    painter.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.16, s * 0.16)
    for i in range(8):
        angle = math.radians(i * 45)
        inner, outer = s * 0.27, s * 0.38
        painter.drawLine(
            QPointF(s * 0.5 + inner * math.cos(angle), s * 0.5 + inner * math.sin(angle)),
            QPointF(s * 0.5 + outer * math.cos(angle), s * 0.5 + outer * math.sin(angle)),
        )


def _moon(painter: QPainter, s: float) -> None:
    path = QPainterPath()
    path.addEllipse(QPointF(s * 0.48, s * 0.52), s * 0.3, s * 0.3)
    bite = QPainterPath()
    bite.addEllipse(QPointF(s * 0.66, s * 0.36), s * 0.24, s * 0.24)
    painter.drawPath(path.subtracted(bite))


def _sliders(painter: QPainter, s: float) -> None:
    for y, knob in ((0.3, 0.64), (0.5, 0.36), (0.7, 0.58)):
        painter.drawLine(QPointF(s * 0.18, s * y), QPointF(s * 0.82, s * y))
        painter.setBrush(painter.pen().color())
        painter.drawEllipse(QPointF(s * knob, s * y), s * 0.06, s * 0.06)
        painter.setBrush(Qt.BrushStyle.NoBrush)


def _new_page(painter: QPainter, s: float) -> None:
    painter.drawRoundedRect(QRectF(s * 0.24, s * 0.16, s * 0.52, s * 0.68), s * 0.06, s * 0.06)
    painter.drawLine(QPointF(s * 0.5, s * 0.36), QPointF(s * 0.5, s * 0.64))
    painter.drawLine(QPointF(s * 0.36, s * 0.5), QPointF(s * 0.64, s * 0.5))


_LINE_GLYPHS: dict[str, Callable[[QPainter, float], None]] = {
    "undo": _undo,
    "redo": lambda p, s: _undo(p, s, mirror=True),
    "eye": _eye,
    "eye-off": lambda p, s: _eye(p, s, closed=True),
    "plus": _plus,
    "minus": _minus,
    "up": lambda p, s: _arrow(p, s, up=True),
    "down": lambda p, s: _arrow(p, s, up=False),
    "duplicate": _duplicate,
    "fit": _fit,
    "refresh": _refresh,
    "info": _info,
    "lock": _lock,
    "unlock": lambda p, s: _lock(p, s, open_=True),
    "sun": _sun,
    "moon": _moon,
    "sliders": _sliders,
    "new-page": _new_page,
}
