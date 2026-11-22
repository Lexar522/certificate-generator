"""Вікно «Генерація для групи»: таблиця → відповідність колонок → файли сертифікатів."""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.batch import (
    ISSUE_DATE_SYNONYMS,
    BatchItem,
    BatchProfile,
    BatchReport,
    build_items,
    load_profile,
    save_profile,
    suggest_columns,
    suggest_special_column,
)
from core.exceptions import CertificateError
from core.table_source import TableData
from core.template_catalog import InputField, describe_inputs
from gui import theme
from gui.batch_workers import BackgroundTask, generate_task, load_table_task
from gui.document import EditorDocument
from gui.widgets import Section, Segmented, Switch, hbox

logger = logging.getLogger(__name__)

NOT_USED = "— не використовувати —"
AUTO_ID = "Автоматично (префікс + номер)"
EDITOR_DATE = "Дата з редактора"
MAX_PREVIEW_ROWS = 500
ERROR_TINT = QColor(215, 0, 21, 28)
MAPPING_CAPTION_WIDTH = 150
GENERATE_BUTTON_MIN_WIDTH = 240


class BatchDialog(QDialog):
    def __init__(
        self,
        doc: EditorDocument,
        project_root: Path,
        parent: QWidget | None = None,
        initial_source: str | None = None,
    ) -> None:
        """initial_source — таблиця, перетягнута на полотно; має пріоритет над збереженою в профілі."""
        super().__init__(parent)
        self.setWindowTitle("Генерація для групи")
        self.resize(1180, 780)
        self._doc = doc
        self._project_root = project_root
        self._inputs = describe_inputs(doc.config)
        self._table: TableData | None = None
        self._items: tuple[BatchItem, ...] = ()
        self._task: BackgroundTask | None = None
        self._field_boxes: dict[str, QComboBox] = {}

        try:
            self._profile = load_profile(doc.template_dir)
        except CertificateError as exc:
            QMessageBox.warning(self, "Профіль", f"{exc}\n\nБуде використано налаштування за замовчуванням.")
            self._profile = BatchProfile()

        self._build_ui()
        self._apply_profile_to_output_controls()
        source = initial_source or self._profile.source
        if source:
            self._source.setText(source)
            self._load_source()

    # ------------------------------------------------------------------ #
    # Розмітка
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(14)

        title = QLabel("Генерація для групи")
        title.setObjectName("PanelTitle")
        subtitle = QLabel(
            "Підтягніть Google Таблицю або CSV, зіставте колонки з полями сертифіката — "
            "і програма створить сертифікат для кожного рядка."
        )
        subtitle.setObjectName("Caption")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        columns.addWidget(self._build_settings_column(), 0)
        columns.addWidget(self._build_preview_column(), 1)
        root.addLayout(columns, 1)
        root.addLayout(self._build_footer())

    def _build_settings_column(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(430)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)

        source = Section("Джерело даних")
        self._source = QLineEdit()
        self._source.setPlaceholderText("https://docs.google.com/spreadsheets/d/… або шлях до .csv")
        self._source.returnPressed.connect(self._load_source)
        source.add_full(self._source)
        browse = QPushButton("CSV-файл…")
        browse.clicked.connect(self._browse_csv)
        self._load_button = QPushButton("Завантажити")
        self._load_button.setObjectName("Accent")
        self._load_button.clicked.connect(self._load_source)
        source.add_full(hbox(QWidget(), browse, self._load_button))
        self._source_status = QLabel("Таблицю ще не завантажено")
        self._source_status.setObjectName("Hint")
        self._source_status.setWordWrap(True)
        source.add_full(self._source_status)
        hint = QLabel(
            "Google Таблиця: «Поділитися» → «Усі, хто має посилання» (Читач). "
            "Перший рядок — назви колонок."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        source.add_full(hint)
        layout.addWidget(source)

        self._mapping = Section("Відповідність колонок", caption_width=MAPPING_CAPTION_WIDTH)
        for field in self._inputs.text_fields + self._inputs.image_fields:
            self._field_boxes[field.id] = self._mapping_box()
            caption = f"{field.label} *" if field.required else field.label
            self._mapping.add_row(caption, self._field_boxes[field.id])
        self._id_box = self._mapping_box(first=AUTO_ID)
        self._mapping.add_row("ID сертифіката", self._id_box)
        self._prefix = QLineEdit()
        self._prefix.setPlaceholderText("CERT")
        self._prefix.textEdited.connect(self._recompute)
        self._mapping.add_row("Префікс ID", self._prefix)
        self._date_box = self._mapping_box(first=EDITOR_DATE)
        self._mapping.add_row("Дата видачі", self._date_box)
        layout.addWidget(self._mapping)

        output = Section("Результат")
        self._output_dir = QLineEdit()
        choose = QPushButton("…")
        choose.setFixedWidth(36)
        choose.clicked.connect(self._choose_output_dir)
        output.add_row("Папка", hbox(self._output_dir, choose))
        self._format = Segmented([("pdf", "PDF"), ("jpg", "JPG"), ("png", "PNG")])
        self._format.changed.connect(self._set_format)
        output.add_row("Формат", self._format)
        self._pattern = QLineEdit()
        output.add_row("Назва файлу", self._pattern)
        names = ", ".join("{" + field.id + "}" for field in self._inputs.text_fields)
        pattern_hint = QLabel(f"Можна використати: {names}, {{certificate_id}}")
        pattern_hint.setObjectName("Hint")
        pattern_hint.setWordWrap(True)
        output.add_full(pattern_hint)
        self._merge = Switch()
        output.add_row("Також один спільний PDF", self._merge)
        layout.addWidget(output)
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _build_preview_column(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        heading = QLabel("ПОПЕРЕДНІЙ ПЕРЕГЛЯД")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        self._summary = QLabel("Завантажте таблицю, щоб побачити рядки")
        self._summary.setObjectName("Caption")
        layout.addWidget(self._summary)

        self._preview = QTableWidget()
        self._preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._preview.verticalHeader().setVisible(False)
        self._preview.setAlternatingRowColors(False)
        self._preview.setShowGrid(False)
        self._preview.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._preview, 1)
        return container

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.hide()
        self._progress_label = QLabel()
        self._progress_label.setObjectName("Caption")
        footer.addWidget(self._progress, 1)
        footer.addWidget(self._progress_label)
        footer.addStretch(0)

        save = QPushButton("Зберегти налаштування")
        save.setToolTip("Зберегти в batch.json шаблону — для повторного запуску або команди batch.py")
        save.clicked.connect(self._save_profile)
        self._close_button = QPushButton("Закрити")
        self._close_button.clicked.connect(self._close_or_cancel)
        self._generate_button = QPushButton("Згенерувати")
        self._generate_button.setObjectName("Accent")
        self._generate_button.setEnabled(False)
        self._generate_button.setMinimumWidth(GENERATE_BUTTON_MIN_WIDTH)
        self._generate_button.clicked.connect(self._generate)
        for button in (save, self._close_button, self._generate_button):
            footer.addWidget(button)
        return footer

    def _mapping_box(self, first: str = NOT_USED) -> QComboBox:
        box = QComboBox()
        box.addItem(first, None)
        box.setMinimumWidth(170)
        box.currentIndexChanged.connect(self._recompute)
        return box

    # ------------------------------------------------------------------ #
    # Профіль ↔ контроли
    # ------------------------------------------------------------------ #

    def _apply_profile_to_output_controls(self) -> None:
        profile = self._profile
        self._prefix.setText(profile.id_prefix)
        self._output_dir.setText(profile.output_dir)
        self._format_value = profile.output_format
        self._format.set_value(profile.output_format)
        self._pattern.setText(profile.filename_pattern)
        self._merge.setChecked(profile.merge_pdf)

    def _set_format(self, value: str) -> None:
        self._format_value = value

    def _current_profile(self) -> BatchProfile:
        columns = {
            field_id: box.currentData()
            for field_id, box in self._field_boxes.items()
            if box.currentData() is not None
        }
        try:
            return BatchProfile(
                source=self._source.text().strip(),
                columns=columns,
                certificate_id_column=self._id_box.currentData(),
                id_prefix=self._prefix.text().strip() or "CERT",
                issue_date_column=self._date_box.currentData(),
                output_dir=self._output_dir.text().strip() or "output/batch",
                output_format=self._format_value,
                filename_pattern=self._pattern.text().strip() or "{certificate_id}",
                merge_pdf=self._merge.isChecked(),
            )
        except ValueError as exc:
            raise CertificateError(f"Некоректні налаштування: {exc}") from exc

    def _fill_mapping_boxes(self, table: TableData) -> None:
        saved = {k: v for k, v in self._profile.columns.items() if v in table.headers}
        suggested = suggest_columns(self._inputs, table.headers) | saved
        boxes = list(self._field_boxes.items()) + [("__id__", self._id_box), ("__date__", self._date_box)]
        specials = {
            # ID не підбираємо автоматично: колонка «№» дала б однакові ID у різних групах.
            "__id__": self._pick(self._profile.certificate_id_column, table),
            "__date__": self._pick(self._profile.issue_date_column, table) or suggest_special_column(table.headers, ISSUE_DATE_SYNONYMS),
        }
        for key, box in boxes:
            box.blockSignals(True)
            first_text = box.itemText(0)
            box.clear()
            box.addItem(first_text, None)
            for header in table.headers:
                box.addItem(header, header)
            target = specials.get(key) if key.startswith("__") else suggested.get(key)
            box.setCurrentIndex(max(0, box.findData(target)) if target else 0)
            box.blockSignals(False)

    @staticmethod
    def _pick(header: str | None, table: TableData) -> str | None:
        return header if header and header in table.headers else None

    # ------------------------------------------------------------------ #
    # Завантаження таблиці
    # ------------------------------------------------------------------ #

    def _browse_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Таблиця CSV", str(self._project_root), "CSV (*.csv *.tsv *.txt)")
        if path:
            self._source.setText(path)
            self._load_source()

    def _load_source(self) -> None:
        source = self._source.text().strip()
        if not source or (self._task and self._task.is_running()):
            return
        self._source_status.setText("Завантаження…")
        self._load_button.setEnabled(False)
        self._task = load_table_task(source, self._project_root, self)
        self._task.finished.connect(self._on_table_loaded)
        self._task.failed.connect(self._on_load_failed)
        self._task.start()

    def _on_table_loaded(self, table: TableData) -> None:
        self._load_button.setEnabled(True)
        self._table = table
        self._source_status.setText(f"✓ Завантажено {len(table.rows)} рядків · {len(table.headers)} колонок")
        self._source_status.setToolTip("Колонки: " + ", ".join(table.headers))
        self._fill_mapping_boxes(table)
        self._recompute()

    def _on_load_failed(self, message: str) -> None:
        self._load_button.setEnabled(True)
        self._source_status.setText(f"⚠ {message}")
        self._source_status.setStyleSheet(f"color: {theme.DANGER};")

    # ------------------------------------------------------------------ #
    # Перегляд
    # ------------------------------------------------------------------ #

    def _recompute(self) -> None:
        if self._table is None:
            return
        self._source_status.setStyleSheet("")
        try:
            profile = self._current_profile()
            self._items = build_items(
                self._table, profile, self._doc.template_dir.name, self._inputs, self._doc.state.issue_date
            )
        except CertificateError as exc:
            self._items = ()
            self._summary.setText(f"⚠ {exc}")
            self._generate_button.setEnabled(False)
            return
        self._render_preview()

    def _render_preview(self) -> None:
        fields: list[InputField] = list(self._inputs.text_fields + self._inputs.image_fields)
        headers = ["Рядок", "Статус", "ID"] + [field.label for field in fields]
        self._preview.clear()
        self._preview.setColumnCount(len(headers))
        self._preview.setHorizontalHeaderLabels(headers)
        shown = self._items[:MAX_PREVIEW_ROWS]
        self._preview.setRowCount(len(shown))

        for row, item in enumerate(shown):
            data = item.data
            values = [str(item.row_number), "✓ Готово" if data else f"⚠ {item.error}", data.certificate_id if data else ""]
            for field in fields:
                source = (data.images if field.id in {f.id for f in self._inputs.image_fields} else data.fields) if data else {}
                values.append(source.get(field.id, ""))
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if data is None:
                    cell.setBackground(ERROR_TINT)
                    cell.setToolTip(item.error)
                    if column == 1:
                        cell.setForeground(QColor(theme.DANGER))
                elif column == 1:
                    cell.setForeground(QColor(theme.SUCCESS))
                self._preview.setItem(row, column, cell)

        header = self._preview.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        ready = sum(1 for item in self._items if item.data is not None)
        broken = len(self._items) - ready
        summary = f"{ready} готові до генерації"
        if broken:
            summary += f" · {broken} з помилками (буде пропущено)"
        self._summary.setText(summary)
        self._generate_button.setEnabled(ready > 0)
        self._generate_button.setText(f"Згенерувати {ready} сертифікат{_plural(ready)}")

    # ------------------------------------------------------------------ #
    # Генерація
    # ------------------------------------------------------------------ #

    def _choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Папка для сертифікатів", str(self._resolved_output_dir()))
        if path:
            self._output_dir.setText(path)

    def _resolved_output_dir(self) -> Path:
        path = Path(self._output_dir.text().strip() or "output/batch").expanduser()
        return path if path.is_absolute() else self._project_root / path

    def _save_profile(self) -> None:
        try:
            path = save_profile(self._doc.template_dir, self._current_profile())
        except CertificateError as exc:
            QMessageBox.warning(self, "Помилка", str(exc))
            return
        self._progress_label.setText(f"Налаштування збережено: {path.name}")

    def _generate(self) -> None:
        try:
            profile = self._current_profile()
        except CertificateError as exc:
            QMessageBox.warning(self, "Помилка", str(exc))
            return
        broken = [item for item in self._items if item.data is None]
        if broken:
            answer = QMessageBox.question(
                self,
                "Є рядки з помилками",
                f"{len(broken)} рядк{_plural(len(broken), 'и', 'ів')} буде пропущено. Продовжити?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._save_profile_silently(profile)
        output_dir = self._resolved_output_dir()
        self._task = generate_task(self._items, self._doc.template_dir, self._doc.config, output_dir, profile, self)
        self._task.progress.connect(self._on_progress)
        self._task.finished.connect(lambda report: self._on_generated(report, output_dir))
        self._task.failed.connect(self._on_generation_failed)
        self._set_busy(True)
        self._task.start()

    def _save_profile_silently(self, profile: BatchProfile) -> None:
        try:
            save_profile(self._doc.template_dir, profile)
        except CertificateError as exc:
            # Генерацію не зупиняємо, але повідомляємо: без профілю batch.py не повторить запуск.
            logger.warning("Профіль не збережено: %s", exc)
            self._progress_label.setText("⚠ Налаштування не збережено")

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.setMaximum(total)
        self._progress.setValue(done)
        self._progress_label.setText(f"{done} з {total}")

    def _on_generated(self, report: BatchReport, output_dir: Path) -> None:
        self._set_busy(False)
        lines = [f"Створено сертифікатів: {len(report.created)}"]
        if report.merged_pdf:
            lines.append(f"Спільний PDF: {report.merged_pdf.name}")
        if report.cancelled:
            lines.append("Генерацію скасовано.")
        if report.failed:
            lines.append(f"\nПропущено рядків: {len(report.failed)}")
            lines.extend(f"  • рядок {row}: {error}" for row, error in report.failed[:10])
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information if not report.failed else QMessageBox.Icon.Warning)
        box.setWindowTitle("Готово")
        box.setText("\n".join(lines))
        open_button = box.addButton("Відкрити папку", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Готово", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))

    def _on_generation_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.warning(self, "Не вдалося згенерувати", message)

    def _set_busy(self, busy: bool) -> None:
        self._progress.setVisible(busy)
        self._progress.setValue(0)
        self._generate_button.setEnabled(not busy)
        self._close_button.setText("Скасувати" if busy else "Закрити")
        if not busy:
            self._progress_label.clear()

    def _close_or_cancel(self) -> None:
        if self._task is not None and self._task.is_running():
            self._task.cancel()
            self._progress_label.setText("Скасування…")
            return
        self.accept()

    def done(self, result: int) -> None:
        if self._task is not None and self._task.is_running():
            self._task.cancel()
            self._task.wait()
        super().done(result)


def _plural(count: int, few: str = "и", many: str = "ів") -> str:
    """Українські закінчення: 1 сертифікат, 2 сертифікати, 5 сертифікатів."""
    if count % 10 == 1 and count % 100 != 11:
        return ""
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return few
    return many
