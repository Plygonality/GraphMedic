"""Command line interface. The README lists these commands and no others."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from graphmedic import __version__
from graphmedic.config import load_config
from graphmedic.errors import ConfigError, GraphMedicError, InputError
from graphmedic.lint import lint_targets
from graphmedic.reporting import render_html, render_json, render_sarif, render_text
from graphmedic.rules import RULES

DEMO_FILES = (
    "examples/geometry_nodes/valid_scatter.json",
    "examples/geometry_nodes/broken_scatter.json",
    "examples/geometry_nodes/inefficient_scatter.json",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="graphmedic",
        description="Static diagnostics for procedural node graphs. GraphMedic does not cook the graph or modify it.",
    )
    parser.add_argument("--version", action="version", version=f"graphmedic {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    lint = commands.add_parser("lint", help="Lint one graph file or, with --recursive, a directory of JSON graphs")
    lint.add_argument("path", help="Graph JSON file, or a directory when --recursive is set")
    lint.add_argument("--format", choices=("text", "json", "sarif", "html"), default="text")
    lint.add_argument("--out", help="Write the report to this path instead of stdout")
    lint.add_argument("--recursive", action="store_true", help="Lint every .json file under a directory. Directory symlinks are not followed")
    lint.add_argument("--config", help="Path to graphmedic.toml")
    lint.add_argument("--fail-on", choices=("error", "warning", "note", "none"), help="Exit 1 when a finding reaches this severity. Default: error, or the config file")
    lint.add_argument("--suggest-fix", action="store_true", help="Print proposed fixes. Does not modify the graph")

    rules = commands.add_parser("rules", help="List every registered rule")
    rules.add_argument("--format", choices=("text", "json"), default="text")
    commands.add_parser("list-rules", help="Alias for rules")

    explain = commands.add_parser("explain", help="Show one rule's rationale and remedy")
    explain.add_argument("rule_id")

    validate = commands.add_parser("validate-config", help="Check graphmedic.toml and exit 2 when a rule id or field is wrong")
    validate.add_argument("path", nargs="?", default="graphmedic.toml")

    commands.add_parser("doctor", help="Show the local runtime, verified catalog, and adapters. Makes no network calls")

    demo = commands.add_parser("demo", help="Lint the three bundled geometry-node examples into a directory")
    demo.add_argument("--out", required=True, help="Directory for the demo reports")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return _dispatch(args)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 0
    except (ConfigError, InputError, GraphMedicError) as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        print(f"GM-INTERNAL-001: {exc}", file=sys.stderr)
        return 4


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "lint":
        return _lint(args)
    if args.command in {"rules", "list-rules"}:
        return _rules(args.format if args.command == "rules" else "text")
    if args.command == "explain":
        return _explain(args.rule_id)
    if args.command == "validate-config":
        load_config(Path(args.path))
        print(f"config ok: {args.path}")
        return 0
    if args.command == "doctor":
        _doctor()
        return 0
    if args.command == "demo":
        return _demo(Path(args.out))
    print(f"GM-INPUT-001: unknown command {args.command}", file=sys.stderr)
    return 2


def _lint(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config) if args.config else None)
    if args.fail_on:
        config.fail_on = args.fail_on
    report = lint_targets([Path(args.path)], config, recursive=args.recursive, suggest=args.suggest_fix)
    rendered = _render(report, args.format)
    if args.out:
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return report["exit_code"]


def _render(report: dict, fmt: str) -> str:
    if fmt == "json":
        return render_json(report)
    if fmt == "sarif":
        return render_sarif(report)
    if fmt == "html":
        return render_html(report)
    return render_text(report)


def _rules(fmt: str) -> int:
    if fmt == "json":
        import json

        payload = [
            {
                "rule_id": rule.id,
                "severity": rule.severity,
                "confidence": rule.confidence,
                "title": rule.title,
                "summary": rule.summary,
            }
            for rule in RULES.values()
        ]
        print(json.dumps(payload, indent=2))
        return 0
    print(f"{'rule':<16} {'severity':<9} {'confidence':<16} title")
    for rule in RULES.values():
        print(f"{rule.id:<16} {rule.severity:<9} {rule.confidence:<16} {rule.title}")
    return 0


def _explain(rule_id: str) -> int:
    rule = RULES.get(rule_id)
    if rule is None:
        print(f"GM-CONFIG-002: Unknown rule id {rule_id}", file=sys.stderr)
        return 2
    print(rule.id)
    print(rule.title)
    print(f"severity: {rule.severity}")
    print(f"confidence: {rule.confidence}")
    print()
    print(rule.summary)
    print()
    print(f"why: {rule.why}")
    print(f"fix: {rule.fix}")
    if rule.references:
        print("references:")
        for reference in rule.references:
            print(f"  {reference}")
    return 0


def _doctor() -> None:
    blender = os.environ.get("GRAPHMEDIC_BLENDER") or shutil.which("blender")
    print(f"graphmedic {__version__}")
    print(f"python {sys.version.split()[0]}")
    print("catalog blender 4.5.14")
    print("adapters blender.geometry_nodes.capture, nodebridge.graph")
    print("unsupported gn-as-code, hda-as-code, pcg-as-code, shader-as-code")
    print(f"blender {'found ' + blender if blender else 'not found'}")
    print("network not used")
    print("rules " + str(len(RULES)))


def _demo(out: Path) -> int:
    missing = [item for item in DEMO_FILES if not Path(item).is_file()]
    if missing:
        raise InputError("Demo graphs are missing: " + ", ".join(missing), code="GM-INPUT-006")
    out.mkdir(parents=True, exist_ok=True)
    config = load_config(Path("graphmedic.toml") if Path("graphmedic.toml").is_file() else None)
    config.fail_on = "none"
    report = lint_targets([Path(item) for item in DEMO_FILES], config, recursive=False, suggest=True)
    (out / "demo.txt").write_text(render_text(report), encoding="utf-8")
    (out / "demo.json").write_text(render_json(report), encoding="utf-8")
    (out / "demo.sarif").write_text(render_sarif(report), encoding="utf-8")
    (out / "demo.html").write_text(render_html(report), encoding="utf-8")
    print(f"wrote {out / 'demo.txt'}")
    print(f"wrote {out / 'demo.json'}")
    print(f"wrote {out / 'demo.sarif'}")
    print(f"wrote {out / 'demo.html'}")
    return 0
