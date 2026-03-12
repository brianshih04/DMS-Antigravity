"""Watchdog-based folder observer manager.

Manages one :class:`watchdog.observers.Observer` that can monitor multiple
directories.  File-creation events feed into the :class:`FileStabilizer`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from core.signals import AppSignals
from watcher.file_stabilizer import FileStabilizer

log = logging.getLogger(__name__)

WATCHED_EXTENSIONS = {".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".png", ".pdf"}


class _StabilizingHandler(FileSystemEventHandler):
    """Routes new-file events to the :class:`FileStabilizer`."""

    def __init__(self, stabilizer: FileStabilizer) -> None:
        super().__init__()
        self._stabilizer = stabilizer

    def _check(self, path: str) -> None:
        ext = Path(path).suffix.lower()
        if ext in WATCHED_EXTENSIONS:
            log.debug("Queuing for stabilization: %s", path)
            self._stabilizer.watch(path)

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._check(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._check(event.dest_path)


class WatchManager:
    """Manage watchdog observer and watched directories.

    Call :meth:`start` after configuring folders with :meth:`add_folder`.
    """

    def __init__(self) -> None:
        self._observer = Observer()
        self._stabilizer = FileStabilizer()
        self._signals = AppSignals.instance()
        self._handler = _StabilizingHandler(self._stabilizer)
        self._watches: dict[str, object] = {}

        # Propagate stabilized files to the central signal bus
        self._stabilizer.file_ready.connect(self._signals.file_ready)
        self._stabilizer.file_ready.connect(
            lambda p: log.info("File stable and ready: %s", p)
        )

    # ── Folder management ─────────────────────────────────────────────────────
    def add_folder(self, path: str, recursive: bool = False) -> None:
        """Register *path* for monitoring (must be called before or after start)."""
        folder = Path(path)
        folder.mkdir(parents=True, exist_ok=True)
        key = str(folder.resolve())
        if key in self._watches:
            return
        watch = self._observer.schedule(
            self._handler, str(folder), recursive=recursive
        )
        self._watches[key] = watch
        log.info("Watching folder: %s  (recursive=%s)", key, recursive)

    def remove_folder(self, path: str) -> None:
        key = str(Path(path).resolve())
        watch = self._watches.pop(key, None)
        if watch is not None:
            self._observer.unschedule(watch)

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if not self._observer.is_alive():
            self._observer.start()
            log.info("WatchManager observer started.")

    def stop(self) -> None:
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join()
            log.info("WatchManager observer stopped.")

    @property
    def watched_folders(self) -> list[str]:
        return list(self._watches.keys())
