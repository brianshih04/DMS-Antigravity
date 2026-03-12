"""QRunnable-based generic worker for QThreadPool."""
from __future__ import annotations

import sys
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """Signals for :class:`BaseWorker`.

    Must be a QObject subclass (QRunnable is not).
    """
    finished = Signal()
    error = Signal(tuple)    # (exc_type, exc_value, traceback_str)
    result = Signal(object)
    progress = Signal(int)   # 0‒100


class BaseWorker(QRunnable):
    """Generic worker that runs *fn(*args, **kwargs)* in a thread-pool thread.

    Usage::

        worker = BaseWorker(my_func, arg1, key=value)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(
                *self.args,
                progress_callback=self.signals.progress,
                **self.kwargs,
            )
        except TypeError:
            # Function doesn't accept progress_callback — call without it
            try:
                result = self.fn(*self.args, **self.kwargs)
            except Exception:
                tb = traceback.format_exc()
                self.signals.error.emit((
                    sys.exc_info()[0],
                    sys.exc_info()[1],
                    tb,
                ))
                return
        except Exception:
            tb = traceback.format_exc()
            self.signals.error.emit((
                sys.exc_info()[0],
                sys.exc_info()[1],
                tb,
            ))
            return
        finally:
            self.signals.finished.emit()

        self.signals.result.emit(result)
