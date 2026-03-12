"""File router — evaluates rules and performs rename + move actions."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from classifier.ast_evaluator import ASTEvaluator, Features
from classifier.rule_parser import ActionDef, RuleDefinition, RuleParser
from core.config import Config
from core.signals import AppSignals

log = logging.getLogger(__name__)


class FileRouter:
    """Evaluates classification rules and dispatches file-system actions."""

    def __init__(self) -> None:
        cfg = Config.instance()
        rules_file = cfg.get("classification.rules_file", "./config/default_rules.yaml")
        self._rules: list[RuleDefinition] = RuleParser().parse_file(rules_file)
        self._evaluator = ASTEvaluator()
        self._signals = AppSignals.instance()

    def route(self, src_path: str, features: Features) -> str | None:
        """Apply the first matching rule to *src_path*.  Returns dest path or None."""
        if not Config.instance().get("classification.enabled", True):
            return None

        for rule in self._rules:
            if self._evaluator.evaluate(rule.condition, features):
                log.info("Rule matched: %s (%s)", rule.name, rule.rule_id)
                dest = self._apply_actions(src_path, rule.actions, features)
                self._signals.classification_done.emit(src_path, dest or src_path, rule.rule_id)
                return dest

        log.debug("No rule matched for: %s", src_path)
        return None

    # ── Action dispatch ────────────────────────────────────────────────────────
    def _apply_actions(
        self,
        src_path: str,
        actions: list[ActionDef],
        features: Features,
    ) -> str:
        current = src_path
        for action in actions:
            if action.action_type == "rename":
                current = self._rename(current, action.rename_template, features)
            elif action.action_type == "move":
                current = self._move(current, action.target_directory)
            elif action.action_type == "copy":
                self._copy(current, action.target_directory)
            elif action.action_type == "tag":
                pass  # future: write EXIF/XMP metadata
        return current

    @staticmethod
    def _render_template(template: str, features: Features) -> str:
        """Interpolate ``{field}`` references from all namespaces."""
        ctx: dict[str, Any] = {}
        for ns in features.values():
            ctx.update(ns)
        try:
            rendered = template.format_map(ctx)
        except (KeyError, ValueError) as exc:
            log.warning("Template render failed %r: %s", template, exc)
            rendered = template
        # Sanitize for filename use
        safe = "".join(c if c.isalnum() or c in "-_. " else "_" for c in rendered)
        return safe.strip() or "unnamed"

    def _rename(self, src: str, template: str, features: Features) -> str:
        if not template:
            return src
        p = Path(src)
        new_stem = self._render_template(template, features)
        dest = p.parent / (new_stem + p.suffix)
        if dest == p:
            return src
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            p.rename(dest)
            log.info("Renamed: %s → %s", p.name, dest.name)
        except OSError as exc:
            log.error("Rename failed: %s", exc)
            return src
        return str(dest)

    @staticmethod
    def _move(src: str, target_dir: str) -> str:
        if not target_dir:
            return src
        dest_dir = Path(target_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(src).name
        try:
            shutil.move(src, str(dest))
            log.info("Moved: %s → %s", src, dest)
        except shutil.Error as exc:
            log.error("Move failed: %s", exc)
            return src
        return str(dest)

    @staticmethod
    def _copy(src: str, target_dir: str) -> None:
        if not target_dir:
            return
        dest_dir = Path(target_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, str(dest_dir / Path(src).name))
        except shutil.Error as exc:
            log.error("Copy failed: %s", exc)
