"""Спливаючі сповіщення внизу полотна (як HUD у macOS) з необов'язковою кнопкою дії."""

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QWidget

TOAST_MS = {"info": 2600, "success": 3200, "error": 6000}
ICONS = {"info": "ℹ", "success": "✓", "error": "⚠"}
ICON_COLORS = {"info": "#8EC5FF", "success": "#5BE37D", "error": "#FF8A80"}
BOTTOM_OFFSET = 28
MAX_TOAST_WIDTH = 560


class Toast(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("Toast")
        self.setStyleSheet(
            """
            QWidget#Toast { background: rgba(28, 28, 30, 0.92); border-radius: 14px; }
            QWidget#Toast QLabel { color: white; background: transparent; }
            QWidget#Toast QPushButton {
                background: rgba(255,255,255,0.16); color: white; border: none;
                border-radius: 8px; padding: 4px 12px; font-weight: 600;
            }
            QWidget#Toast QPushButton:hover { background: rgba(255,255,255,0.26); }
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 10, 10)
        layout.setSpacing(10)
        self._icon = QLabel()
        self._text = QLabel()
        self._text.setWordWrap(True)
        self._text.setMaximumWidth(MAX_TOAST_WIDTH - 140)
        self._action = QPushButton()
        self._action.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action.clicked.connect(self._run_action)
        layout.addWidget(self._icon)
        layout.addWidget(self._text, 1)
        layout.addWidget(self._action)
        self._callback: Callable[[], None] | None = None

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        host.installEventFilter(self)
        self.hide()

    def show_message(
        self,
        text: str,
        level: str = "info",
        action_text: str | None = None,
        action: Callable[[], None] | None = None,
    ) -> None:
        self._icon.setText(ICONS.get(level, ""))
        self._icon.setStyleSheet(f"color: {ICON_COLORS.get(level, 'white')}; font-size: 15px; font-weight: 700;")
        self._text.setText(text)
        # Без цього QLabel з переносом стискається до найвужчого слова.
        text_width = self._text.fontMetrics().horizontalAdvance(text) + 4
        self._text.setMinimumWidth(min(text_width, MAX_TOAST_WIDTH - 160))
        self._callback = action
        self._action.setVisible(bool(action_text and action))
        self._action.setText(action_text or "")
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity() if self.isVisible() else 0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(TOAST_MS.get(level, 3000) + (2500 if action else 0))

    def _run_action(self) -> None:
        callback = self._callback
        self._fade_out()
        if callback is not None:
            callback()

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._opacity.opacity() <= 0.01:
            self.hide()

    def _reposition(self) -> None:
        width = min(self.sizeHint().width(), MAX_TOAST_WIDTH, self._host.width() - 40)
        self.resize(width, self.heightForWidth(width) if self.hasHeightForWidth() else self.sizeHint().height())
        self.move((self._host.width() - self.width()) // 2, self._host.height() - self.height() - BOTTOM_OFFSET)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 — Qt API
        if watched is self._host and event.type() == QEvent.Type.Resize and self.isVisible():
            self._reposition()
        return False
