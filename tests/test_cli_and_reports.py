import json
from pathlib import Path

import jsonschema

from graphmedic.cli import build_parser, main
from graphmedic.config import Config
from graphmedic.lint import lint_file, lint_targets

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "sarif-schema-2.1.0.json").read_text())
VALID = ROOT / "examples" / "geometry_nodes" / "valid_scatter.json"
BROKEN = ROOT / "examples" / "geometry_nodes" / "broken_scatter.json"
INEFFICIENT = ROOT / "examples" / "geometry_nodes" / "inefficient_scatter.json"
FIXED = ROOT / "examples" / "geometry_nodes" / "broken_scatter_fixed.json"


def test_valid_reference_has_no_findings():
    result = lint_file(VALID, Config())
    assert result["findings"] == []
    assert result["coverage"]["counts"]["fail"] == 0
    assert result["coverage"]["counts"]["not_evaluated"] == 0
    assert result["version"] == "4.5.14"


def test_broken_graph_names_the_socket_and_the_fix_clears_it():
    broken = lint_file(BROKEN, Config())
    rules = {item["rule_id"] for item in broken["findings"]}
    assert "GM-STRUCT-002" in rules
    assert "GM-STRUCT-003" in rules
    socket = next(item for item in broken["findings"] if item["rule_id"] == "GM-STRUCT-002")
    assert socket["socket"] == "MissingSocket"
    assert socket["confidence"] == "PROVEN"
    fixed = lint_file(FIXED, Config())
    assert fixed["findings"] == []


def test_inefficient_graph_is_heuristic_only():
    config = Config(max_points=100000)
    result = lint_file(INEFFICIENT, config)
    assert result["findings"]
    assert all(item["severity"] != "error" for item in result["findings"])
    assert any(item["rule_id"] == "GM-GEO-013" and item["confidence"] == "HEURISTIC" for item in result["findings"])
    assert any(item["rule_id"] == "GM-PERF-003" for item in result["findings"])


def test_json_report_is_byte_stable(tmp_path: Path):
    first = main(["lint", str(VALID), "--format", "json", "--out", str(tmp_path / "a.json")])
    second = main(["lint", str(VALID), "--format", "json", "--out", str(tmp_path / "b.json")])
    assert first == second == 0
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    payload = json.loads((tmp_path / "a.json").read_text())
    assert "timestamp" not in payload


def test_sarif_validates_and_keeps_stable_ids(tmp_path: Path):
    assert main(["lint", str(BROKEN), "--format", "sarif", "--out", str(tmp_path / "broken.sarif")]) == 1
    payload = json.loads((tmp_path / "broken.sarif").read_text())
    jsonschema.Draft4Validator(SCHEMA).validate(payload)
    result = next(item for item in payload["runs"][0]["results"] if item["ruleId"] == "GM-STRUCT-002")
    assert result["partialFingerprints"]["graphmedic/v1"]
    assert result["locations"][0]["logicalLocations"][0]["name"] == "Group Output"


def test_suggest_fix_does_not_modify_the_graph(tmp_path: Path):
    source = tmp_path / "graph.json"
    source.write_text(BROKEN.read_text())
    before = source.read_bytes()
    assert main(["lint", str(source), "--suggest-fix", "--format", "text"]) == 1
    assert source.read_bytes() == before


def test_exit_codes(tmp_path: Path, monkeypatch):
    assert main(["lint", str(VALID)]) == 0
    assert main(["lint", str(BROKEN)]) == 1
    assert main(["lint", str(BROKEN), "--fail-on", "none"]) == 0
    malformed = tmp_path / "bad.json"
    malformed.write_text("{")
    assert main(["lint", str(malformed)]) == 2
    unsupported = tmp_path / "gn.json"
    unsupported.write_text(json.dumps({"format": "gn-as-code", "format_version": 1}))
    assert main(["lint", str(unsupported)]) == 3
    monkeypatch.setattr("graphmedic.cli.lint_targets", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    assert main(["lint", str(VALID)]) == 4


def test_directory_traversal_and_recursive_gate(tmp_path: Path):
    assert main(["lint", str(ROOT / "graphs")]) == 2
    assert main(["lint", str(ROOT / "graphs"), "--recursive", "--config", str(ROOT / "graphmedic.toml"), "--fail-on", "error"]) == 0
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["lint", str(empty), "--recursive"]) == 2


def test_suppression_requires_a_real_rule_and_is_reported(tmp_path: Path):
    graph = tmp_path / "broken_scatter.json"
    graph.write_text(BROKEN.read_text())
    config = tmp_path / "graphmedic.toml"
    config.write_text(
        "\n".join(
            [
                "version = 1",
                "[[suppress]]",
                'rule_id = "GM-STRUCT-006"',
                f'path = "{graph.name}"',
                'reason = "These nodes are only unreachable because the final socket is being repaired."',
            ]
        )
    )
    report = tmp_path / "out.json"
    assert main(["lint", str(graph), "--config", str(config), "--format", "json", "--out", str(report)]) == 1
    payload = json.loads(report.read_text())
    assert payload["totals"]["suppressed"] == 4
    assert not any(item["rule_id"] == "GM-STRUCT-006" for item in payload["files"][0]["findings"])
    bad = tmp_path / "bad.toml"
    bad.write_text('[[suppress]]\nrule_id = "GM-NOPE"\npath = "a.json"\nreason = "because"\n')
    assert main(["validate-config", str(bad)]) == 2
    assert main(["validate-config", str(ROOT / "graphmedic.toml")]) == 0


def test_commands_match_the_parser():
    parser = build_parser()
    help_text = parser.format_help()
    for command in ("lint", "rules", "list-rules", "explain", "validate-config", "doctor", "demo"):
        assert command in help_text
    assert main(["rules"]) == 0
    assert main(["explain", "GM-STRUCT-002"]) == 0
    assert main(["explain", "GM-NO-SUCH"]) == 2
    assert main(["doctor"]) == 0
    assert main(["--help"]) == 0


def test_demo_writes_reports(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(ROOT)
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    for name in ("demo.txt", "demo.json", "demo.sarif", "demo.html"):
        assert (out / name).is_file()
    html = (out / "demo.html").read_text()
    assert "http://" not in html
    assert "https://" not in html
    sarif = json.loads((out / "demo.sarif").read_text())
    jsonschema.Draft4Validator(SCHEMA).validate(sarif)


def test_embedded_code_is_not_executed(tmp_path: Path):
    path = tmp_path / "code.json"
    path.write_text(
        json.dumps(
            {
                "format": "blender.geometry_nodes.capture",
                "format_version": 1,
                "application": {"name": "Blender", "version": "4.5.14"},
                "root": "Main",
                "trees": [
                    {
                        "name": "Main",
                        "bl_idname": "GeometryNodeTree",
                        "kind": "geometry",
                        "interface": [],
                        "nodes": [
                            {
                                "id": "Script",
                                "type": "ShaderNodeMath",
                                "inputs": [],
                                "outputs": [],
                                "parameters": {"code": "raise SystemExit(9)"},
                            }
                        ],
                        "links": [],
                    }
                ],
            }
        )
    )
    result = lint_targets([path], Config(), recursive=False, suggest=False)
    assert result["exit_code"] == 0 or result["files"][0]["status"] == "linted"
