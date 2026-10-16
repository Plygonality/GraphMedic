"""Re-export the scatter tree when a real Blender binary is available.

The test is skipped, not mocked, when Blender is absent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from graphmedic.config import Config
from graphmedic.lint import lint_file

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "fixtures" / "blender" / "valid_scatter.json"
CANDIDATES = [
    os.environ.get("GRAPHMEDIC_BLENDER"),
    shutil.which("blender"),
    "/tmp/blender/blender-4.5.14-linux-x64/blender",
]


def _blender() -> str | None:
    for candidate in CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


BLENDER = _blender()


@pytest.mark.skipif(BLENDER is None, reason="Blender is not installed; DCC export was not re-run")
def test_blender_export_matches_the_committed_fixture(tmp_path: Path):
    destination = tmp_path / "valid_scatter.json"
    log = tmp_path / "blender-stdout.txt"
    completed = subprocess.run(
        [BLENDER, "--background", "--python", str(ROOT / "tools" / "export_geometry_nodes.py"), "--", "--out", str(destination)],
        check=False,
        capture_output=True,
        text=True,
    )
    log.write_text(completed.stdout + "\n" + completed.stderr)
    assert completed.returncode == 0, log.read_text()
    assert "BLENDER 4.5.14" in completed.stdout
    fresh = json.loads(destination.read_text())
    committed = json.loads(COMMITTED.read_text())
    assert fresh["application"]["version"] == "4.5.14"
    assert committed["application"]["verified"] is True
    assert committed["application"]["build_hash"] == "62c1db4208e8"
    fresh_nodes = {node["type"]: node for node in fresh["trees"][0]["nodes"]}
    committed_nodes = {node["type"]: node for node in committed["trees"][0]["nodes"]}
    assert set(fresh_nodes) == set(committed_nodes)
    for node_type, node in fresh_nodes.items():
        fresh_inputs = [socket["identifier"] for socket in node["inputs"]]
        committed_inputs = [socket["identifier"] for socket in committed_nodes[node_type]["inputs"]]
        assert fresh_inputs == committed_inputs
    result = lint_file(destination, Config())
    assert result["findings"] == []
    assert "4.5.14" in log.read_text()
