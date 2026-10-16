"""The published docs name the rules and commands the package actually ships."""

from pathlib import Path

from graphmedic.cli import build_parser
from graphmedic.rules import RULES

ROOT = Path(__file__).resolve().parents[1]


def test_readme_lists_every_command():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    commands = set(build_parser()._subparsers._group_actions[0].choices)
    assert commands == {
        "lint",
        "rules",
        "list-rules",
        "explain",
        "validate-config",
        "doctor",
        "demo",
    }
    for name in commands:
        assert f"graphmedic {name}" in readme or f"`{name}`" in readme


def test_rule_registry_covers_every_rule():
    registry = (ROOT / "docs" / "rules" / "README.md").read_text(encoding="utf-8")
    for rule_id in RULES:
        assert rule_id in registry


def test_exit_codes_are_documented():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for code in ("0", "1", "2", "3", "4"):
        assert code in readme
    assert "NOT_EVALUATED" in readme
