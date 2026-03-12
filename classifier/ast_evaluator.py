"""Boolean AST evaluator for classification rules.

Recursively evaluates AND/OR/NOT/LEAF nodes against a features dict.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from classifier.rule_parser import AndNode, ASTNode, LeafNode, NotNode, OrNode

log = logging.getLogger(__name__)

# Features type: {"attr": {...}, "text": {...}, "struct": {...}}
Features = dict[str, dict[str, Any]]


class ASTEvaluator:
    """Evaluates a rule condition tree against extracted document features."""

    def evaluate(self, node: ASTNode, features: Features) -> bool:
        if isinstance(node, AndNode):
            return all(self.evaluate(c, features) for c in node.children)
        if isinstance(node, OrNode):
            return any(self.evaluate(c, features) for c in node.children)
        if isinstance(node, NotNode):
            return not self.evaluate(node.child, features)  # type: ignore[arg-type]
        if isinstance(node, LeafNode):
            return self._eval_leaf(node, features)
        log.error("Unknown AST node type: %s", type(node))
        return False

    @staticmethod
    def _eval_leaf(node: LeafNode, features: Features) -> bool:
        ns = features.get(node.namespace, {})
        value = ns.get(node.field_key)
        target = node.value
        op = node.operator.lower()

        try:
            if op == "eq":
                return value == target
            if op == "neq":
                return value != target
            if op == "gt":
                return float(value) > float(target)  # type: ignore[arg-type]
            if op == "lt":
                return float(value) < float(target)  # type: ignore[arg-type]
            if op == "gte":
                return float(value) >= float(target)  # type: ignore[arg-type]
            if op == "lte":
                return float(value) <= float(target)  # type: ignore[arg-type]
            if op == "contains":
                return str(target) in str(value)
            if op == "regex":
                return bool(re.search(str(target), str(value or ""), re.IGNORECASE))
            if op == "exists":
                return value is not None
        except (TypeError, ValueError) as exc:
            log.debug("Leaf eval error (%s %s %s): %s", node.field_key, op, target, exc)
            return False

        log.warning("Unknown operator: %r", op)
        return False
