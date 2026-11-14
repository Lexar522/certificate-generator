"""Фонові задачі для пакетної генерації: завантаження таблиці та рендер сертифікатів."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from core.batch import BatchItem, BatchProfile, run_batch
from core.exceptions import CertificateError
from core.models import TemplateConfig
from core.table_source import load_table


class Worker(QObject):
    """Виконує job(worker) у фоновому потоці; job може повідомляти прогрес і перевіряти скасування."""

    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, job: Callable[["Worker"], object]) -> None:
        super().__init__()
        self._job = job
        self.cancel_requested = False

    def run(self) -> None:
        try:
            self.done.emit(self._job(self))
        except CertificateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 — помилка у фоновому потоці має дійти до UI
            self.failed.emit(f"Неочікувана помилка: {exc!r}")


class BackgroundTask(QObject):
    """Запускає Worker в окремому QThread; сигнали доходять у потік UI автоматично."""

    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, job: Callable[[Worker], object], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = Worker(job)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.done.connect(self.finished)
        self._worker.failed.connect(self.failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self._worker.cancel_requested = True

    def is_running(self) -> bool:
        return self._thread.isRunning()

    def wait(self) -> None:
        self._thread.quit()
        self._thread.wait()


def load_table_task(source: str, base_dir: Path, parent: QObject) -> BackgroundTask:
    return BackgroundTask(lambda _worker: load_table(source, base_dir), parent)


def generate_task(
    items: tuple[BatchItem, ...],
    template_dir: Path,
    config: TemplateConfig,
    output_dir: Path,
    profile: BatchProfile,
    parent: QObject,
) -> BackgroundTask:
    def job(worker: Worker):
        return run_batch(
            items,
            template_dir,
            config,
            output_dir,
            profile,
            on_progress=worker.progress.emit,
            is_cancelled=lambda: worker.cancel_requested,
        )

    return BackgroundTask(job, parent)
