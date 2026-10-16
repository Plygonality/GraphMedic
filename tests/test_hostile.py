import json
from pathlib import Path

from graphmedic.cli import main
from graphmedic.errors import InputError
from graphmedic.limits import Limits
from graphmedic.parse import load_path


def test_malformed_json(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text('{"trees": ')
    assert main(["lint", str(path)]) == 2


def test_deep_json_is_rejected(tmp_path: Path):
    path = tmp_path / "deep.json"
    path.write_text("[" * 80 + "]" * 80)
    try:
        load_path(path, Limits(max_depth=8))
    except InputError as exc:
        assert exc.code == "GM-INPUT-002"
    else:
        raise AssertionError("deep JSON was accepted")


def test_too_many_nodes(tmp_path: Path):
    nodes = [{"id": f"N{i}", "type": "ShaderNodeMath", "inputs": [], "outputs": [], "parameters": {}} for i in range(6)]
    path = tmp_path / "wide.json"
    path.write_text(
        json.dumps(
            {
                "format": "blender.geometry_nodes.capture",
                "format_version": 1,
                "application": {"version": "4.5.14"},
                "root": "Main",
                "trees": [{"name": "Main", "bl_idname": "GeometryNodeTree", "kind": "geometry", "nodes": nodes, "links": []}],
            }
        )
    )
    try:
        load_path(path, Limits(max_nodes=3))
    except InputError as exc:
        assert exc.code == "GM-INPUT-002"
    else:
        raise AssertionError("oversized graph was accepted")


def test_archive_is_not_expanded(tmp_path: Path):
    archive = tmp_path / "graphs.zip"
    archive.write_bytes(b"PK\x03\x04not-really")
    assert main(["lint", str(archive)]) == 2


def test_symlink_outside_the_directory_is_not_read(tmp_path: Path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"format": "gn-as-code", "secret": "do-not-read"}))
    folder = tmp_path / "graphs"
    folder.mkdir()
    (folder / "escape.json").symlink_to(outside)
    (folder / "local.json").write_text((Path(__file__).resolve().parents[1] / "examples/geometry_nodes/valid_scatter.json").read_text())
    assert main(["lint", str(folder), "--recursive"]) == 2
    report = folder / "out.json"
    assert main(["lint", str(folder), "--recursive", "--format", "json", "--out", str(report), "--fail-on", "none"]) == 2
    payload = json.loads(report.read_text())
    escaped = next(item for item in payload["files"] if item["path"].endswith("escape.json"))
    assert escaped["error"]["code"] == "GM-INPUT-005"
    assert "do-not-read" not in json.dumps(payload)


def test_group_reference_cycle_is_bounded(tmp_path: Path):
    path = tmp_path / "cycle.json"
    path.write_text(
        json.dumps(
            {
                "format": "blender.geometry_nodes.capture",
                "format_version": 1,
                "application": {"version": "4.5.14"},
                "root": "A",
                "trees": [
                    {
                        "name": "A",
                        "bl_idname": "GeometryNodeTree",
                        "kind": "geometry",
                        "nodes": [{"id": "ToB", "type": "GeometryNodeGroup", "group_tree": "B", "inputs": [], "outputs": [], "parameters": {}}],
                        "links": [],
                    },
                    {
                        "name": "B",
                        "bl_idname": "GeometryNodeTree",
                        "kind": "geometry",
                        "nodes": [{"id": "ToA", "type": "GeometryNodeGroup", "group_tree": "A", "inputs": [], "outputs": [], "parameters": {}}],
                        "links": [],
                    },
                ],
            }
        )
    )
    result = load_path(path, Limits())
    from graphmedic.analyze import analyze
    from graphmedic.catalog import load_catalog
    from graphmedic.rules import Context, evaluate_all

    analysis = analyze(result, load_catalog())
    evaluations = evaluate_all(Context(result, analysis, load_catalog(), 8, None), enabled=None, disabled=set())
    cycle = next(item for item in evaluations if item.rule.id == "GM-STRUCT-007")
    assert cycle.status == "FAIL"
    assert analysis.group_depth is None
