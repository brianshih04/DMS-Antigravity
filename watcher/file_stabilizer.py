"""File I/O stabilizer — ensures a file is fully written before dispatch.

Polls (size, mtime) every POLL_INTERVAL_MS milliseconds until the file
has been stable for STABLE_COUNT_REQUIRED consecutive checks, then emits
the ``file_ready`` signal.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

POLL_INTERVAL_MS: int = 250      # milliseconds between polls
STABLE_COUNT_REQUIRED: int = 2   # consecutive stable polls before dispatch

_IGNORED_SUFFIXES = {".tmp", ".part", ".crdownload", ".download"}


def _should_skip(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in _IGNORED_SUFFIXES


class FileStabilizer(QObject):
    """Monitors a file until I/O is complete, then emits ``file_ready(path)``."""

    file_ready = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._active: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def watch(self, path: str) -> None:
        """Begin stability-watching *path* in a daemon thread."""
        if _should_skip(path):
            return
        with self._lock:
            if path in self._active:
                return  # already watching
            t = threading.Thread(
                target=self._poll,
                args=(path,),
                daemon=True,
                name=f"stabilizer-{Path(path).name}",
            )
            self._active[path] = t
        t.start()

    def _poll(self, path: str) -> None:
        interval = POLL_INTERVAL_MS / 1000.0
        prev_size: int = -1
        prev_mtime: float = -1.0
        stable_count: int = 0

        while True:
            try:
                stat = os.stat(path)
            except (FileNotFoundError, PermissionError):
                break  # file gone or inaccessible — abort

            size = stat.st_size
            mtime = stat.st_mtime

            if size == 0:
                # Wait for the writer to produce content
                stable_count = 0
            elif size == prev_size and mtime == prev_mtime:
                stable_count += 1
                if stable_count >= STABLE_COUNT_REQUIRED:
                    with self._lock:
                        self._active.pop(path, None)
                    self.file_ready.emit(path)
                    return
            else:
                stable_count = 0

            prev_size = size
            prev_mtime = mtime
            time.sleep(interval)

        with self._lock:
            self._active.pop(path, None)
