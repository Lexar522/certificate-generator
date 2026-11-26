"""Довідка гарячих клавіш (Ctrl+/)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gui import theme
from gui.widgets import Section

SHORTCUTS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Файл", (
        ("Ctrl+S", "Зберегти шаблон"),
        ("Ctrl+E", "Експорт сертифіката"),
        ("Ctrl+G", "Генерація для групи"),
        ("Ctrl+N", "Новий шаблон"),
        ("Ctrl+Shift+R", "Розмір полотна"),
    )),
    ("Редагування", (
        ("Ctrl+Z / Ctrl+Shift+Z", "Скасувати / повторити"),
        ("Ctrl+C / Ctrl+V", "Копіювати / вставити шар (і між шаблонами)"),
        ("Ctrl+D", "Дублювати шар"),
        ("Ctrl+L", "Заблокувати / розблокувати шар"),
        ("Delete, Backspace", "Видалити шар"),
        ("Enter, подвійний клік", "Редагувати текст"),
    )),
    ("Полотно", (
        ("Стрілки / Shift+стрілки", "Зсув на 1 / 10 px"),
        ("Тягнути за кут", "Змінити розмір"),
        ("Ctrl+колесо, Ctrl+= / Ctrl+-", "Масштаб"),
        ("Ctrl+0", "Вмістити сторінку"),
        ("Пробіл + перетягування", "Панорамування"),
        ("Перетягнути файл", "Зображення → шар, з Shift → фон; CSV → генерація для групи"),
        ("Esc", "Зняти виділення"),
    )),
)


def _key_label(keys: str) -> QLabel:
    label = QLabel(keys)
    label.setStyleSheet(
        f"background: {theme.CONTROL_FILL}; border: 1px solid {theme.HAIRLINE}; border-radius: 6px;"
        "padding: 2px 8px; font-weight: 600;"
    )
    return label


class ShortcutsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Гарячі клавіші")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(14)
        title = QLabel("Гарячі клавіші")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        for group, rows in SHORTCUTS:
            section = Section(group)
            grid = QWidget()
            grid_layout = QGridLayout(grid)
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setHorizontalSpacing(14)
            grid_layout.setVerticalSpacing(8)
            for row, (keys, action) in enumerate(rows):
                grid_layout.addWidget(_key_label(keys), row, 0, Qt.AlignmentFlag.AlignLeft)
                description = QLabel(action)
                description.setWordWrap(True)
                grid_layout.addWidget(description, row, 1)
            grid_layout.setColumnStretch(1, 1)
            section.add_full(grid)
            layout.addWidget(section)

        close = QPushButton("Готово")
        close.setObjectName("Accent")
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
