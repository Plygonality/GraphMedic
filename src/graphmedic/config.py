"""Project configuration. Unknown rule ids are errors, not silent skips."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from graphmedic.errors import ConfigError
from graphmedic.limits import Limits
from graphmedic.rules import RULES

SEVERITIES = {"error", "warning", "note"}
FAIL_LEVELS = {"error", "warning", "note", "none"}


@dataclass
class Suppression:
    rule_id: str
    path: str
    reason: str
    graph: str | None = None


@dataclass
class Config:
    fail_on: str = "error"
    max_points: int | None = None
    max_group_depth: int = 8
    severity: dict[str, str] = field(default_factory=dict)
    disable: set[str] = field(default_factory=set)
    enable: set[str] | None = None
    suppress: list[Suppression] = field(default_factory=list)
    limits: Limits = field(default_factory=Limits)
    source: str | None = None


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}", code="GM-CONFIG-001")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Malformed TOML in {path.name}: {exc}", code="GM-CONFIG-001") from exc
    if not isinstance(data, dict):
        raise ConfigError("Config root must be a table", code="GM-CONFIG-001")
    known = {"version", "fail_on", "budgets", "style", "limits", "rules", "suppress"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(f"Unknown config keys: {', '.join(unknown)}", code="GM-CONFIG-001")
    if "version" in data and data["version"] != 1:
        raise ConfigError(f"Unsupported config version {data['version']!r}", code="GM-CONFIG-001")
    config = Config(source=str(path))
    if "fail_on" in data:
        if data["fail_on"] not in FAIL_LEVELS:
            raise ConfigError("fail_on must be error, warning, note, or none", code="GM-CONFIG-001")
        config.fail_on = data["fail_on"]
    budgets = _table(data.get("budgets"), "budgets")
    if "max_points" in budgets:
        config.max_points = _positive_int(budgets["max_points"], "budgets.max_points")
    _reject_unknown(budgets, {"max_points"}, "budgets")
    style = _table(data.get("style"), "style")
    if "max_group_depth" in style:
        config.max_group_depth = _positive_int(style["max_group_depth"], "style.max_group_depth", allow_zero=True)
    _reject_unknown(style, {"max_group_depth"}, "style")
    limits = _table(data.get("limits"), "limits")
    _reject_unknown(limits, {"max_bytes", "max_nodes", "max_links", "max_depth", "max_files"}, "limits")
    overridden = {}
    for key in ("max_bytes", "max_nodes", "max_links", "max_depth", "max_files"):
        if key in limits:
            overridden[key] = _positive_int(limits[key], f"limits.{key}")
    if overridden:
        config.limits = config.limits.overridden(**overridden)
    rules = _table(data.get("rules"), "rules")
    _reject_unknown(rules, {"disable", "enable", "severity"}, "rules")
    if "disable" in rules:
        config.disable = set(_rule_list(rules["disable"], "rules.disable"))
    if "enable" in rules:
        config.enable = set(_rule_list(rules["enable"], "rules.enable"))
    severity = _table(rules.get("severity"), "rules.severity")
    for rule_id, level in severity.items():
        _known_rule(rule_id, "rules.severity")
        if level not in SEVERITIES:
            raise ConfigError(f"Severity for {rule_id} must be error, warning, or note", code="GM-CONFIG-001")
        config.severity[rule_id] = level
    suppress = data.get("suppress", [])
    if not isinstance(suppress, list):
        raise ConfigError("suppress must be an array of tables", code="GM-CONFIG-001")
    for index, item in enumerate(suppress):
        if not isinstance(item, dict):
            raise ConfigError(f"suppress entry {index} must be a table", code="GM-CONFIG-001")
        _reject_unknown(item, {"rule_id", "path", "reason", "graph"}, f"suppress[{index}]")
        rule_id = item.get("rule_id")
        scope = item.get("path")
        reason = item.get("reason")
        if not isinstance(rule_id, str) or not isinstance(scope, str) or not isinstance(reason, str):
            raise ConfigError(
                f"suppress entry {index} needs rule_id, path, and reason",
                code="GM-CONFIG-002",
            )
        _known_rule(rule_id, f"suppress[{index}]")
        if not scope.strip() or not reason.strip():
            raise ConfigError(f"suppress entry {index} needs a path and a written reason", code="GM-CONFIG-002")
        graph = item.get("graph")
        if graph is not None and not isinstance(graph, str):
            raise ConfigError(f"suppress[{index}].graph must be a string", code="GM-CONFIG-001")
        config.suppress.append(Suppression(rule_id=rule_id, path=scope.strip(), reason=reason.strip(), graph=graph))
    return config


def _table(value, label: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a table", code="GM-CONFIG-001")
    return value


def _reject_unknown(table: dict, allowed: set[str], label: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(f"Unknown {label} keys: {', '.join(unknown)}", code="GM-CONFIG-001")


def _positive_int(value, label: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or (value == 0 and not allow_zero):
        raise ConfigError(f"{label} must be a positive integer", code="GM-CONFIG-001")
    return value


def _rule_list(value, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{label} must be an array of rule ids", code="GM-CONFIG-001")
    for rule_id in value:
        _known_rule(rule_id, label)
    return value


def _known_rule(rule_id: str, label: str) -> None:
    if rule_id not in RULES:
        raise ConfigError(f"Unknown rule id {rule_id} in {label}", code="GM-CONFIG-002")
