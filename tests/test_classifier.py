"""Tests for the boolean classification rule engine."""
from __future__ import annotations

import pytest

from classifier.ast_evaluator import ASTEvaluator
from classifier.rule_parser import AndNode, LeafNode, NotNode, OrNode, RuleParser


SAMPLE_FEATURES = {
    "attr": {
        "size_bytes": 2_000_000,
        "extension": "jpg",
        "filename": "invoice_001",
        "ctime_iso": "2024-01-15T10:00:00+00:00",
        "mtime_iso": "2024-01-15T10:00:00+00:00",
    },
    "text": {
        "full_text": "Invoice INV-2024-0001 from Acme Corp total 1500.00",
    },
    "struct": {
        "date": "2024-01-15",
        "invoice_number": "INV-2024-0001",
        "total_amount": "1500.00",
        "vendor_name": "Acme Corp",
        "stamp_detected": False,
    },
}

ev = ASTEvaluator()


# ── AND ────────────────────────────────────────────────────────────────────

def test_and_both_match():
    node = AndNode(children=[
        LeafNode(namespace="attr", field_key="extension", operator="eq", value="jpg"),
        LeafNode(namespace="text", field_key="full_text", operator="contains", value="Invoice"),
    ])
    assert ev.evaluate(node, SAMPLE_FEATURES) is True


def test_and_one_fails():
    node = AndNode(children=[
        LeafNode(namespace="attr", field_key="extension", operator="eq", value="jpg"),
        LeafNode(namespace="attr", field_key="extension", operator="eq", value="pdf"),
    ])
    assert ev.evaluate(node, SAMPLE_FEATURES) is False


# ── OR ─────────────────────────────────────────────────────────────────────

def test_or_one_matches():
    node = OrNode(children=[
        LeafNode(namespace="attr", field_key="extension", operator="eq", value="pdf"),
        LeafNode(namespace="attr", field_key="extension", operator="eq", value="jpg"),
    ])
    assert ev.evaluate(node, SAMPLE_FEATURES) is True


def test_or_neither_matches():
    node = OrNode(children=[
        LeafNode(namespace="attr", field_key="extension", operator="eq", value="pdf"),
        LeafNode(namespace="attr", field_key="extension", operator="eq", value="bmp"),
    ])
    assert ev.evaluate(node, SAMPLE_FEATURES) is False


# ── NOT ────────────────────────────────────────────────────────────────────

def test_not_negates_true():
    node = NotNode(child=LeafNode(
        namespace="struct", field_key="stamp_detected", operator="eq", value=True
    ))
    assert ev.evaluate(node, SAMPLE_FEATURES) is True  # stamp_detected=False → NOT False = True


def test_not_negates_false():
    node = NotNode(child=LeafNode(
        namespace="attr", field_key="extension", operator="eq", value="jpg"
    ))
    assert ev.evaluate(node, SAMPLE_FEATURES) is False  # ext=jpg → NOT True = False


# ── Composite ──────────────────────────────────────────────────────────────

def test_nested_and_or_not():
    """AND( OR(ext=jpg, ext=pdf), NOT(stamp=True), text REGEX invoice )"""
    node = AndNode(children=[
        OrNode(children=[
            LeafNode(namespace="attr", field_key="extension", operator="eq", value="jpg"),
            LeafNode(namespace="attr", field_key="extension", operator="eq", value="pdf"),
        ]),
        NotNode(child=LeafNode(
            namespace="struct", field_key="stamp_detected", operator="eq", value=True
        )),
        LeafNode(namespace="text", field_key="full_text", operator="regex", value=r"INV-\d+"),
    ])
    assert ev.evaluate(node, SAMPLE_FEATURES) is True


# ── LEAF operators ─────────────────────────────────────────────────────────

def test_leaf_gt():
    node = LeafNode(namespace="attr", field_key="size_bytes", operator="gt", value=1_000_000)
    assert ev.evaluate(node, SAMPLE_FEATURES) is True


def test_leaf_lte():
    node = LeafNode(namespace="attr", field_key="size_bytes", operator="lte", value=1_000_000)
    assert ev.evaluate(node, SAMPLE_FEATURES) is False


def test_leaf_exists():
    node = LeafNode(namespace="struct", field_key="invoice_number", operator="exists", value=None)
    assert ev.evaluate(node, SAMPLE_FEATURES) is True


def test_leaf_not_exists():
    feats = {**SAMPLE_FEATURES, "struct": {**SAMPLE_FEATURES["struct"], "invoice_number": None}}
    node = LeafNode(namespace="struct", field_key="invoice_number", operator="exists", value=None)
    assert ev.evaluate(node, feats) is False


# ── Rule parser ────────────────────────────────────────────────────────────

def test_rule_parser_loads_yaml(tmp_path):
    rules_yaml = tmp_path / "rules.yaml"
    rules_yaml.write_text("""
version: "1.0"
rules:
  - id: r1
    name: Test Rule
    priority: 1
    enabled: true
    condition:
      op: LEAF
      namespace: attr
      field: extension
      operator: eq
      value: jpg
    actions:
      - type: move
        target_directory: ./output/Test
""")
    parser = RuleParser()
    rules = parser.parse_file(str(rules_yaml))
    assert len(rules) == 1
    assert rules[0].rule_id == "r1"
    assert isinstance(rules[0].condition, LeafNode)


def test_rule_parser_skips_disabled(tmp_path):
    rules_yaml = tmp_path / "rules.yaml"
    rules_yaml.write_text("""
version: "1.0"
rules:
  - id: r1
    name: Active
    priority: 1
    enabled: true
    condition: {op: LEAF, namespace: attr, field: extension, operator: eq, value: jpg}
    actions: []
  - id: r2
    name: Disabled
    priority: 2
    enabled: false
    condition: {op: LEAF, namespace: attr, field: extension, operator: eq, value: pdf}
    actions: []
""")
    rules = RuleParser().parse_file(str(rules_yaml))
    assert len(rules) == 1
    assert rules[0].rule_id == "r1"
