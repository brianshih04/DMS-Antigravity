"""Loads and validates classification rules from JSON/YAML, returns an AST.

Rule schema reference: .agent/skills/rule_engine_ast.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# ── AST Node types ────────────────────────────────────────────────────────────

@dataclass
class ASTNode:
    op: str  # AND | OR | NOT | LEAF


@dataclass
class AndNode(ASTNode):
    children: list[ASTNode] = field(default_factory=list)
    op: str = "AND"


@dataclass
class OrNode(ASTNode):
    children: list[ASTNode] = field(default_factory=list)
    op: str = "OR"


@dataclass
class NotNode(ASTNode):
    child: ASTNode | None = None
    op: str = "NOT"


@dataclass
class LeafNode(ASTNode):
    namespace: str = ""     # attr | text | struct
    field_key: str = ""     # e.g. "extension", "full_text"
    operator: str = ""      # eq | neq | gt | lt | gte | lte | contains | regex | exists
    value: Any = None
    op: str = "LEAF"


@dataclass
class ActionDef:
    action_type: str                    # rename | move | copy | tag
    rename_template: str = ""
    target_directory: str = ""


@dataclass
class RuleDefinition:
    rule_id: str
    name: str
    priority: int
    enabled: bool
    condition: ASTNode
    actions: list[ActionDef]


# ── Parser ────────────────────────────────────────────────────────────────────

class RuleParser:
    """Parses a rules YAML/JSON file into a list of :class:`RuleDefinition`."""

    def parse_file(self, path: str) -> list[RuleDefinition]:
        p = Path(path)
        with open(p, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) if p.suffix in {".yaml", ".yml"} else json.load(fh)

        if not raw or "rules" not in raw:
            log.warning("Rules file %s has no 'rules' key.", path)
            return []

        rules: list[RuleDefinition] = []
        for r in raw["rules"]:
            if not r.get("enabled", True):
                continue
            try:
                rules.append(self._parse_rule(r))
            except (KeyError, TypeError, ValueError) as exc:
                log.error("Rule parse error (id=%s): %s", r.get("id", "?"), exc)

        rules.sort(key=lambda r: r.priority)
        return rules

    def _parse_rule(self, r: dict) -> RuleDefinition:
        actions = [self._parse_action(a) for a in r.get("actions", [])]
        return RuleDefinition(
            rule_id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            priority=int(r.get("priority", 999)),
            enabled=bool(r.get("enabled", True)),
            condition=self._parse_node(r["condition"]),
            actions=actions,
        )

    def _parse_node(self, node: dict) -> ASTNode:
        op = str(node["op"]).upper()
        if op == "AND":
            return AndNode(children=[self._parse_node(c) for c in node["children"]])
        if op == "OR":
            return OrNode(children=[self._parse_node(c) for c in node["children"]])
        if op == "NOT":
            return NotNode(child=self._parse_node(node["child"]))
        if op == "LEAF":
            return LeafNode(
                namespace=node["namespace"],
                field_key=node["field"],
                operator=node["operator"],
                value=node.get("value"),
            )
        raise ValueError(f"Unknown AST op: {op!r}")

    @staticmethod
    def _parse_action(a: dict) -> ActionDef:
        return ActionDef(
            action_type=a["type"],
            rename_template=a.get("rename_template", ""),
            target_directory=a.get("target_directory", ""),
        )
