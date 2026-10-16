import json
from pathlib import Path

import pytest

from graphmedic.config import Config
from graphmedic.lint import lint_file

NODEBRIDGE = Path("/tmp/audit/NodeBridge/examples/scatter/scatter.graph.json")


def test_nodebridge_omitted_validity_is_the_format_default(tmp_path: Path):
    path = tmp_path / "bridge.json"
    path.write_text(
        json.dumps(
            {
                "format": "nodebridge.graph",
                "format_version": 1,
                "root": "Scatter",
                "source": {"application": "Blender 4.2.23 LTS"},
                "trees": [
                    {
                        "name": "Scatter",
                        "kind": "geometry",
                        "interface": [
                            {"identifier": "Socket_0", "name": "Geometry", "in_out": "INPUT", "type": "geometry"},
                            {"identifier": "Socket_1", "name": "Geometry", "in_out": "OUTPUT", "type": "geometry"},
                        ],
                        "nodes": [
                            {"id": "Group Input", "type": "NodeGroupInput", "inputs": [], "outputs": [{"identifier": "Socket_0", "name": "Geometry", "type": "geometry"}]},
                            {"id": "Group Output", "type": "NodeGroupOutput", "inputs": [{"identifier": "Socket_1", "name": "Geometry", "type": "geometry"}], "outputs": [], "parameters": {"is_active_output": True}},
                        ],
                        "edges": [{"from": ["Group Input", "Socket_0"], "to": ["Group Output", "Socket_1"]}],
                    }
                ],
            }
        )
    )
    result = lint_file(path, Config())
    assert result["adapter"] == "nodebridge.graph"
    assert result["host"] == "blender"
    detail = next(item for item in result["coverage"]["details"] if item["rule_id"] == "GM-STRUCT-004")
    assert detail["status"] == "PASS"
    assert result["findings"] == []


def test_gn_as_code_is_unsupported_rather_than_healthy(tmp_path: Path):
    path = tmp_path / "gn.json"
    path.write_text(json.dumps({"format": "gn-as-code", "nodes": []}))
    result = lint_file(path, Config())
    assert result["status"] == "unsupported"
    assert result["error"]["code"] == "GM-INPUT-003"
    assert result["findings"] == []


def test_hda_and_pcg_are_unsupported(tmp_path: Path):
    for fmt in ("hda-as-code", "pcg-as-code", "shader-as-code"):
        path = tmp_path / f"{fmt}.json"
        path.write_text(json.dumps({"format": fmt}))
        result = lint_file(path, Config())
        assert result["status"] == "unsupported"


@pytest.mark.skipif(not NODEBRIDGE.is_file(), reason="NodeBridge scatter fixture is not available in this environment")
def test_published_nodebridge_scatter_has_no_structural_findings():
    result = lint_file(NODEBRIDGE, Config())
    assert result["status"] == "linted"
    assert result["version"].startswith("Blender 4.2.23")
    assert result["findings"] == []
    unevaluated = [item["rule_id"] for item in result["coverage"]["details"] if item["status"] == "NOT_EVALUATED"]
    assert "GM-GEO-013" in unevaluated
