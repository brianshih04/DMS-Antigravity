"""Core configuration loader — singleton with hot-reload support."""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

# Load .env at import time (no-op if file absent)
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

_CONFIG_ROOT = Path(__file__).parent.parent / "config"
_SETTINGS_FILE = _CONFIG_ROOT / "settings.yaml"


class _ConfigSignals(QObject):
    config_changed = Signal(dict)


class Config:
    """Singleton configuration manager.

    Access via ``Config.instance()``.  Call ``reload()`` to hot-reload the
    YAML file and fire ``signals.config_changed``.
    """

    _instance: "Config | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self.signals = _ConfigSignals()
        self.reload()

    # ── Singleton ─────────────────────────────────────────────────────────────
    @classmethod
    def instance(cls) -> "Config":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── Loading ───────────────────────────────────────────────────────────────
    def reload(self) -> None:
        """(Re)load settings from disk and emit ``config_changed``."""
        with open(_SETTINGS_FILE, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        # Inject environment variables (take precedence over file)
        api_key_env = os.environ.get("ZHIPU_API_KEY", "").strip()
        if api_key_env:
            data.setdefault("ocr", {})["api_key"] = api_key_env

        local_ep = os.environ.get("LOCAL_OCR_ENDPOINT", "").strip()
        if local_ep:
            data.setdefault("ocr", {})["local_endpoint"] = local_ep

        self._data = data
        self.signals.config_changed.emit(dict(self._data))

    # ── Access ────────────────────────────────────────────────────────────────
    def get(self, key_path: str, default: Any = None) -> Any:
        """Dot-notation accessor, e.g. ``config.get('ocr.mode')``."""
        parts = key_path.split(".")
        node: Any = self._data
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part, None)
            if node is None:
                return default
        return node

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def set(self, key_path: str, value: Any) -> None:
        """Set a value using dot notation (doesn't persist to disk)."""
        parts = key_path.split(".")
        node = self._data
        for part in parts[:-1]:
            if part not in node:
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    def save(self) -> None:
        """Persist current configuration to settings.yaml file."""
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as fh:
            yaml.safe_dump(self._data, fh, default_flow_style=False, sort_keys=False)
        log.info("Configuration saved to %s", _SETTINGS_FILE)

    def all(self) -> dict[str, Any]:
        return dict(self._data)
