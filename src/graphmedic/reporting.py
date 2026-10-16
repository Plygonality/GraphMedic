"""Text, JSON, SARIF 2.1.0, and a self-contained HTML summary."""

from __future__ import annotations

import json
from html import escape
from typing import Any

from graphmedic import __version__
from graphmedic.model import Diagnostic
from graphmedic.rules import RULES, Evaluation
from graphmedic.values import json_ready

SEVERITY_RANK = {"error": 3, "warning": 2, "note": 1}


def coverage_counts(rows: list[Evaluation]) -> dict[str, int]:
    counts = {"pass": 0, "fail": 0, "not_applicable": 0, "not_evaluated": 0}
    for row in rows:
        key = {
            "PASS": "pass",
            "FAIL": "fail",
            "NOT_APPLICABLE": "not_applicable",
            "NOT_EVALUATED": "not_evaluated",
        }[row.status]
        counts[key] += 1
    return counts


def render_text(report: dict[str, Any]) -> str:
    lines = [f"GraphMedic {report['graphmedic_version']}", ""]
    for item in report["files"]:
        lines.append(f"{item['path']}  {item['status']}  {item.get('host') or '-'} {item.get('version') or ''}".rstrip())
        if item.get("error"):
            lines.append(f"  {item['error']['code']}: {item['error']['message']}")
        findings = item.get("findings") or []
        if item["status"] == "linted" and not findings:
            lines.append("  No findings.")
        for finding in findings:
            path = " / ".join(finding["graph_path"])
            where = " ".join(part for part in (path, finding.get("node_id") or "", finding.get("socket") or "") if part)
            lines.append(
                f"  {finding['severity']} [{finding['confidence']}] {finding['rule_id']}: {finding['message']}"
            )
            if where:
                lines.append(f"    at {where}")
            lines.append(f"    why: {finding['why']}")
            lines.append(f"    fix: {finding['fix']}")
        if item.get("suppressed"):
            lines.append(f"  Suppressed: {len(item['suppressed'])}")
            for finding in item["suppressed"]:
                lines.append(f"    {finding['rule_id']} {finding.get('node_id') or ''} ({finding['suppression_reason']})")
        if item.get("coverage"):
            counts = item["coverage"]["counts"]
            lines.append(
                "  Coverage  "
                f"PASS {counts['pass']}  FAIL {counts['fail']}  "
                f"NOT_APPLICABLE {counts['not_applicable']}  NOT_EVALUATED {counts['not_evaluated']}  "
                f"suppressed {item['coverage']['suppressed']}"
            )
            for detail in item["coverage"]["details"]:
                if detail["status"] == "NOT_EVALUATED":
                    lines.append(f"    not evaluated  {detail['rule_id']}  {detail['reason']}")
        lines.append("")
    totals = report["totals"]
    lines.append(
        "Totals  "
        f"files {totals['files']}  findings {totals['findings']}  "
        f"errors {totals['errors']}  warnings {totals['warnings']}  notes {totals['notes']}  "
        f"suppressed {totals['suppressed']}"
    )
    if report.get("suggestions"):
        lines.append("")
        lines.append("Suggestions (not applied)")
        for suggestion in report["suggestions"]:
            lines.append(f"  - {suggestion}")
    lines.append("")
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_html(report: dict[str, Any]) -> str:
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'><head><meta charset='utf-8'>",
        "<title>GraphMedic report</title>",
        "<style>",
        "body{font:16px/1.45 Georgia,serif;margin:2rem;color:#1c1915;background:#f7f4ee}",
        "h1{font-weight:500;letter-spacing:-.02em}",
        "table{border-collapse:collapse;width:100%;background:white}",
        "th,td{border:1px solid #ddd;padding:.4rem .6rem;text-align:left;vertical-align:top}",
        "th{background:#efeae2}",
        ".error{color:#8d1d1d}.warning{color:#8a4b08}.note{color:#24516a}",
        "code{font-family:ui-monospace,monospace}",
        "</style></head><body>",
        f"<h1>GraphMedic {escape(report['graphmedic_version'])}</h1>",
        "<p>Definite failures and heuristic suggestions are separate. A rule that cannot see enough of the graph is not evaluated, and that is not a clean pass.</p>",
    ]
    for item in report["files"]:
        parts.append(f"<h2>{escape(item['path'])}</h2>")
        if item.get("error"):
            parts.append(f"<p><strong>{escape(item['error']['code'])}</strong> {escape(item['error']['message'])}</p>")
        if item.get("coverage"):
            counts = item["coverage"]["counts"]
            parts.append("<table><thead><tr><th>Status</th><th>Rules</th><th>Meaning</th></tr></thead><tbody>")
            rows = [
                ("PASS", counts["pass"], "The check ran and the graph did not match it."),
                ("FAIL", counts["fail"], "At least one location matched. Read the confidence column before treating it as a proven defect."),
                ("NOT_APPLICABLE", counts["not_applicable"], "The graph does not contain the construct this check is about."),
                ("NOT_EVALUATED", counts["not_evaluated"], "The file does not carry enough verified semantics. This is not a bill of health."),
            ]
            for name, count, meaning in rows:
                parts.append(f"<tr><td>{name}</td><td>{count}</td><td>{escape(meaning)}</td></tr>")
            parts.append("</tbody></table>")
        findings = item.get("findings") or []
        if findings:
            parts.append("<h3>Findings</h3><table><thead><tr><th>Rule</th><th>Confidence</th><th>Where</th><th>What to do</th></tr></thead><tbody>")
            for finding in findings:
                where = " / ".join(finding["graph_path"])
                if finding.get("node_id"):
                    where = f"{where} · {finding['node_id']}"
                if finding.get("socket"):
                    where = f"{where} · {finding['socket']}"
                parts.append(
                    "<tr>"
                    f"<td class='{escape(finding['severity'])}'><code>{escape(finding['rule_id'])}</code><br>{escape(finding['message'])}</td>"
                    f"<td>{escape(finding['confidence'])}</td>"
                    f"<td>{escape(where)}</td>"
                    f"<td>{escape(finding['fix'])}</td>"
                    "</tr>"
                )
            parts.append("</tbody></table>")
        elif item["status"] == "linted":
            parts.append("<p>No findings.</p>")
    parts.append("</body></html>\n")
    return "".join(parts)


def render_sarif(report: dict[str, Any]) -> str:
    rules = []
    for rule in RULES.values():
        rules.append(
            {
                "id": rule.id,
                "name": rule.title,
                "shortDescription": {"text": rule.summary},
                "fullDescription": {"text": rule.why},
                "defaultConfiguration": {"level": _sarif_level(rule.severity)},
                "help": {"text": rule.fix},
                "properties": {
                    "confidence": rule.confidence,
                    "tags": [rule.confidence],
                },
            }
        )
    results = []
    for item in report["files"]:
        for finding in item.get("findings") or []:
            location: dict[str, Any] = {
                "physicalLocation": {
                    "artifactLocation": {"uri": _uri(item["path"])},
                }
            }
            if finding.get("line"):
                location["physicalLocation"]["region"] = {"startLine": finding["line"]}
            else:
                location["physicalLocation"]["region"] = {"charOffset": 0, "charLength": 0}
            logical_name = finding.get("node_id") or finding["rule_id"]
            qualified = "/".join([*finding["graph_path"], logical_name])
            location["logicalLocations"] = [
                {"name": logical_name, "fullyQualifiedName": qualified, "kind": "member"}
            ]
            result = {
                "ruleId": finding["rule_id"],
                "level": _sarif_level(finding["severity"]),
                "kind": "fail",
                "message": {"text": finding["message"]},
                "locations": [location],
                "properties": json_ready(
                    {
                        "confidence": finding["confidence"],
                        "why": finding["why"],
                        "fix": finding["fix"],
                        "graphPath": finding["graph_path"],
                        "nodeId": finding["node_id"],
                        "socket": finding["socket"],
                        "relatedNodes": finding["related_nodes"],
                        "evidence": finding["evidence"],
                        "applicability": finding["applicability"],
                    }
                ),
            }
            fingerprint = "|".join(
                [
                    finding["rule_id"],
                    item["path"],
                    "/".join(finding["graph_path"]),
                    finding.get("node_id") or "",
                    finding.get("socket") or "",
                    finding["message"],
                ]
            )
            result["partialFingerprints"] = {"graphmedic/v1": fingerprint}
            results.append(result)
    payload = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "GraphMedic",
                        "version": __version__,
                        "informationUri": "https://github.com/Plygonality/GraphMedic",
                        "rules": rules,
                    }
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "exitCode": report["exit_code"],
                    }
                ],
                "properties": {
                    "coverage": report["totals"],
                    "files": [
                        {
                            "path": item["path"],
                            "status": item["status"],
                            "error": item.get("error"),
                            "coverage": item.get("coverage"),
                        }
                        for item in report["files"]
                    ],
                },
            }
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sarif_level(severity: str) -> str:
    if severity == "error":
        return "error"
    if severity == "warning":
        return "warning"
    return "note"


def _uri(path: str) -> str:
    return path.replace("\\", "/")


def finding_sort(finding: Diagnostic) -> tuple:
    return finding.sort_key()
