"""Run the registered rules and build a deterministic report."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from graphmedic import __version__
from graphmedic.analyze import analyze
from graphmedic.catalog import load_catalog
from graphmedic.config import Config
from graphmedic.errors import InputError, UnsupportedFormatError
from graphmedic.model import Diagnostic
from graphmedic.parse import load_path
from graphmedic.reporting import coverage_counts
from graphmedic.rules import Context as RuleContext
from graphmedic.rules import Evaluation, evaluate_all

SEVERITY_RANK = {"error": 3, "warning": 2, "note": 1, "none": 0}


def lint_targets(paths: list[Path], config: Config, *, recursive: bool, suggest: bool) -> dict[str, Any]:
    files = []
    for path in paths:
        files.extend(collect_files(path, recursive=recursive, config=config))
    results = [lint_file(path, config) for path in files]
    report = assemble(results, config)
    if suggest:
        report["suggestions"] = [
            f"{finding['rule_id']} {finding.get('node_id') or finding['file']}: {finding['fix']}"
            for item in report["files"]
            for finding in item.get("findings") or []
        ]
    return report


def collect_files(path: Path, *, recursive: bool, config: Config) -> list[Path]:
    if not path.exists() and not path.is_symlink():
        raise InputError(f"Path not found: {path}", code="GM-INPUT-006")
    if path.is_symlink() and path.is_file():
        return [path]
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise InputError(f"Path not found: {path}", code="GM-INPUT-006")
    if not recursive:
        raise InputError(f"{path} is a directory; pass --recursive to lint the graphs inside it", code="GM-INPUT-007")
    root = path.resolve()
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = sorted(name for name in dirnames if not (current / name).is_symlink())
        for name in sorted(filenames):
            candidate = current / name
            if candidate.suffix.lower() != ".json":
                continue
            found.append(candidate)
            if len(found) > config.limits.max_files:
                raise InputError(
                    f"More than {config.limits.max_files} JSON files under {path}",
                    code="GM-INPUT-002",
                )
    if not found:
        raise InputError(f"No JSON graphs under {path}", code="GM-INPUT-010")
    del root
    return found


def lint_file(path: Path, config: Config) -> dict[str, Any]:
    display = display_path(path)
    outside = _symlink_escapes(path)
    if outside:
        return _failed(display, "invalid", "GM-INPUT-005", f"Refusing to read {display}; the symlink leaves the walked directory")
    try:
        document = load_path(path, config.limits)
    except UnsupportedFormatError as exc:
        return _failed(display, "unsupported", exc.code, str(exc))
    except InputError as exc:
        return _failed(display, "invalid", exc.code, str(exc))
    catalog = load_catalog()
    analysis = analyze(document, catalog)
    ctx = RuleContext(
        document=document,
        analysis=analysis,
        catalog=catalog,
        max_group_depth=config.max_group_depth,
        max_points=config.max_points,
    )
    evaluations = evaluate_all(ctx, enabled=config.enable, disabled=config.disable)
    kept: list[Diagnostic] = []
    suppressed: list[dict[str, Any]] = []
    coverage_details = []
    suppressed_count = 0
    for evaluation in evaluations:
        surviving = []
        for finding in evaluation.findings:
            finding = replace(finding, file=display, severity=config.severity.get(finding.rule_id, finding.severity))
            reason = _suppression_reason(finding, display, config)
            if reason:
                payload = finding.to_dict()
                payload["suppression_reason"] = reason
                suppressed.append(payload)
                suppressed_count += 1
            else:
                surviving.append(finding)
        status = evaluation.status
        if evaluation.status == "FAIL" and not surviving:
            status = "PASS"
        kept.extend(surviving)
        coverage_details.append(
            {
                "rule_id": evaluation.rule.id,
                "status": status,
                "reason": evaluation.reason,
                "findings": len(surviving),
            }
        )
    kept.sort(key=lambda item: item.sort_key())
    suppressed.sort(key=lambda item: (item["rule_id"], item.get("node_id") or "", item.get("socket") or ""))
    adjusted = [
        Evaluation(evaluation.rule, detail["status"], [], detail["reason"])
        for evaluation, detail in zip(evaluations, coverage_details, strict=True)
    ]
    return {
        "path": display,
        "status": "linted",
        "format": document.format,
        "adapter": document.adapter,
        "host": document.host,
        "version": document.version,
        "error": None,
        "findings": [item.to_dict() for item in kept],
        "suppressed": suppressed,
        "coverage": {
            "counts": coverage_counts(adjusted),
            "suppressed": suppressed_count,
            "details": coverage_details,
        },
    }


def assemble(files: list[dict[str, Any]], config: Config) -> dict[str, Any]:
    findings = [finding for item in files for finding in item.get("findings") or []]
    report = {
        "report_version": 1,
        "graphmedic_version": __version__,
        "fail_on": config.fail_on,
        "files": files,
        "totals": {
            "files": len(files),
            "findings": len(findings),
            "errors": sum(1 for finding in findings if finding["severity"] == "error"),
            "warnings": sum(1 for finding in findings if finding["severity"] == "warning"),
            "notes": sum(1 for finding in findings if finding["severity"] == "note"),
            "suppressed": sum(len(item.get("suppressed") or []) for item in files),
            "unsupported": sum(1 for item in files if item["status"] == "unsupported"),
            "invalid": sum(1 for item in files if item["status"] == "invalid"),
        },
    }
    report["exit_code"] = exit_code(report, config.fail_on)
    return report


def exit_code(report: dict[str, Any], fail_on: str) -> int:
    if report["totals"]["invalid"]:
        return 2
    threshold = SEVERITY_RANK[fail_on]
    if any(SEVERITY_RANK[finding["severity"]] >= threshold and threshold > 0 for item in report["files"] for finding in item.get("findings") or []):
        return 1
    if report["totals"]["unsupported"]:
        return 3
    return 0


def display_path(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path.as_posix()
    return relative.as_posix()


def _suppression_reason(finding: Diagnostic, display: str, config: Config) -> str | None:
    for item in config.suppress:
        if item.rule_id != finding.rule_id:
            continue
        if not _path_matches(display, item.path):
            continue
        if item.graph and item.graph not in finding.graph_path:
            continue
        return item.reason
    return None


def _path_matches(display: str, scope: str) -> bool:
    scope = scope.replace("\\", "/").lstrip("./")
    return display == scope or display.endswith("/" + scope)


def _symlink_escapes(path: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        root = path.parent.resolve()
        target = path.resolve()
    except OSError:
        return True
    return not (target == root or root in target.parents)


def _failed(path: str, status: str, code: str, message: str) -> dict[str, Any]:
    return {
        "path": path,
        "status": status,
        "format": None,
        "adapter": None,
        "host": None,
        "version": None,
        "error": {"code": code, "message": message},
        "findings": [],
        "suppressed": [],
        "coverage": None,
    }
