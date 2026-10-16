import json
from pathlib import Path

import pytest

from graphmedic.config import Config, load_config
from graphmedic.lint import lint_file

ROOT = Path(__file__).parent / "fixtures" / "rules"
EXPECTED = {
    "pass": "PASS",
    "fail": "FAIL",
    "unknown": "NOT_EVALUATED",
    "open": "NOT_EVALUATED",
    "unspecified": "NOT_APPLICABLE",
    "custom": "PASS",
    "one": "PASS",
}


@pytest.mark.parametrize("path", sorted(ROOT.glob("*.json")), ids=lambda path: path.name)
def test_rule_fixture(path: Path):
    rule_id, kind = path.name[: -len(".json")].rsplit(".", 1)
    config_path = path.with_suffix(".toml")
    config = load_config(config_path) if config_path.exists() else Config()
    result = lint_file(path, config)
    assert result["status"] == "linted", result["error"]
    detail = next(item for item in result["coverage"]["details"] if item["rule_id"] == rule_id)
    assert detail["status"] == EXPECTED[kind]


def test_open_pipeline_is_not_a_false_attribute_error():
    result = lint_file(ROOT / "GM-DOMAIN-001.open.json", Config())
    assert not any(item["rule_id"] == "GM-DOMAIN-001" for item in result["findings"])
    detail = next(item for item in result["coverage"]["details"] if item["rule_id"] == "GM-DOMAIN-001")
    assert detail["reason"] == "UNVERIFIABLE_ATTRIBUTE_SOURCE"


def test_unknown_conversion_is_not_branded_invalid():
    result = lint_file(ROOT / "GM-STRUCT-004.unknown.json", Config())
    assert not any(item["rule_id"] == "GM-STRUCT-004" for item in result["findings"])


def test_known_implicit_conversion_passes():
    result = lint_file(ROOT / "GM-STRUCT-004.pass.json", Config())
    detail = next(item for item in result["coverage"]["details"] if item["rule_id"] == "GM-STRUCT-004")
    assert detail["status"] == "PASS"


def test_grid_vertex_count_of_one_is_not_empty():
    result = lint_file(ROOT / "GM-DOMAIN-003.one.json", Config())
    assert not any(item["rule_id"] == "GM-DOMAIN-003" for item in result["findings"])


def test_custom_attribute_domain_is_not_a_mismatch():
    result = lint_file(ROOT / "GM-DOMAIN-002.custom.json", Config())
    assert not any(item["rule_id"] == "GM-DOMAIN-002" for item in result["findings"])


def test_unknown_count_does_not_exceed_a_budget():
    result = lint_file(ROOT / "GM-PERF-003.unknown.json", load_config(ROOT / "GM-PERF-003.unknown.toml"))
    assert not any(item["rule_id"] == "GM-PERF-003" for item in result["findings"])


def test_flatten_collision_is_ignored_until_flattening_is_requested():
    result = lint_file(ROOT / "GM-STRUCT-012.unspecified.json", Config())
    assert not any(item["rule_id"] == "GM-STRUCT-012" for item in result["findings"])


def test_non_finite_exponent_is_detected():
    payload = json.loads((ROOT / "GM-STRUCT-008.fail.json").read_text())
    assert payload["trees"][0]["nodes"][0]["parameters"]["level"] == float("inf")


def test_same_label_in_two_groups_keeps_both_paths(tmp_path: Path):
    document = {
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
                    {"id": "Math", "type": "ShaderNodeMath", "inputs": [], "outputs": [{"identifier": "Value", "type": "VALUE"}], "parameters": {}},
                    {"id": "Call", "type": "GeometryNodeGroup", "group_tree": "Leaf", "inputs": [], "outputs": [], "parameters": {}},
                    {
                        "id": "Group Output",
                        "type": "NodeGroupOutput",
                        "inputs": [{"identifier": "Socket_1", "type": "GEOMETRY"}],
                        "outputs": [],
                        "parameters": {"is_active_output": True},
                    },
                ],
                "links": [],
            },
            {
                "name": "Leaf",
                "bl_idname": "GeometryNodeTree",
                "kind": "geometry",
                "is_group": True,
                "interface": [],
                "nodes": [
                    {"id": "Math", "type": "ShaderNodeMath", "inputs": [], "outputs": [{"identifier": "Value", "type": "VALUE"}], "parameters": {}},
                    {
                        "id": "Group Output",
                        "type": "NodeGroupOutput",
                        "inputs": [{"identifier": "Socket_1", "type": "GEOMETRY"}],
                        "outputs": [],
                        "parameters": {"is_active_output": True},
                    },
                ],
                "links": [],
            },
        ],
    }
    path = tmp_path / "groups.json"
    path.write_text(json.dumps(document))
    result = lint_file(path, Config())
    dead = [item for item in result["findings"] if item["rule_id"] == "GM-STRUCT-006" and item["node_id"] == "Math"]
    assert {tuple(item["graph_path"]) for item in dead} == {("Main",), ("Main", "Leaf")}
