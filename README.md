# GraphMedic

GraphMedic reads an exported procedural graph and reports defects before a DCC cook. A dangling socket, a missing modifier output, and a Realize Instances node sitting in front of another instance chain are different kinds of problem. The report says which one it found, where it sits, and whether the claim is proven or only a heuristic.

It does not cook geometry, rewrite the graph, or replace Blender’s node warnings. Offline lint needs Python 3.11+ and a JSON export. Blender is optional and is used only to refresh the verified fixture.

## 60-second demo

```bash
pip install -e ".[dev]"
graphmedic demo --out build/demo
graphmedic lint examples/geometry_nodes/valid_scatter.json --format text
graphmedic lint examples/geometry_nodes/broken_scatter.json --format json --out reports/broken.json
graphmedic lint examples/geometry_nodes/broken_scatter.json --format sarif --out reports/broken.sarif
graphmedic lint graphs/ --recursive --config graphmedic.toml --fail-on error
graphmedic rules
graphmedic explain GM-STRUCT-002
graphmedic doctor
```

The valid scatter was exported from Blender 4.5.14 LTS (hash `62c1db4208e8`). Lint exits 0:

```text
GraphMedic 0.1.0

examples/geometry_nodes/valid_scatter.json  linted  blender 4.5.14
  No findings.
  Coverage  PASS 13  FAIL 0  NOT_APPLICABLE 8  NOT_EVALUATED 0  suppressed 0

Totals  files 1  findings 0  errors 0  warnings 0  notes 0  suppressed 0
```

`broken_scatter.json` is that same export with the last link aimed at `MissingSocket`. Lint exits 1. Restoring the link to `Socket_3` (`broken_scatter_fixed.json`) clears every finding. `inefficient_scatter.json` still connects, and with `graphmedic.toml` it exits 0 on `--fail-on error` while reporting two heuristic warnings. The node-by-node annotation is in [docs/demo/annotations.md](docs/demo/annotations.md). No Blender screenshot was captured.

```text
error [PROVEN] GM-STRUCT-002: Link targets an unknown socket
  at Scatter Group Output MissingSocket
warning [HEURISTIC] GM-GEO-013: Realize Instances occurs upstream of a replicated branch; potentially expensive at high counts
  at Scatter Realize Instances
```

## What a finding contains

```json
{
  "rule_id": "GM-STRUCT-002",
  "severity": "error",
  "confidence": "PROVEN",
  "status": "FAIL",
  "message": "Link targets an unknown socket",
  "graph_path": ["Scatter"],
  "node_id": "Group Output",
  "socket": "MissingSocket",
  "related_nodes": ["Instance on Points"],
  "evidence": {"end": "to", "link_index": 5},
  "why": "The serialized endpoint is not on the node, so the connection cannot carry a value.",
  "fix": "Correct the socket identifier or regenerate the graph export.",
  "applicability": {"graph_version": "4.5.14", "host": "blender"}
}
```

Every rule also returns a coverage status: `PASS`, `FAIL`, `NOT_APPLICABLE`, or `NOT_EVALUATED`. A rule that cannot see the semantics it needs is not a clean pass.

## Install

```bash
pip install -e ".[dev]"
```

Optional, pinned to the 0.1.0 tag:

```bash
pip install "graphmedic @ git+https://github.com/Plygonality/GraphMedic.git@v0.1.0"
```

Runtime dependencies: none. Dev extras: pytest, ruff, jsonschema, build. The console script is `graphmedic`. `python -m graphmedic` is the same entry point.

## Commands

`graphmedic --help` lists these and no others.

| Command | Role |
| --- | --- |
| `graphmedic lint PATH` | Lint one JSON file. A directory requires `--recursive`. |
| `graphmedic rules` | List registered rules. `--format json` is available. |
| `graphmedic list-rules` | Same list as `rules`, text only. |
| `graphmedic explain RULE` | Print one rule’s rationale and remedy. Unknown ids exit 2. |
| `graphmedic validate-config [PATH]` | Check `graphmedic.toml`. Default path is `graphmedic.toml`. |
| `graphmedic doctor` | Local version, catalog, adapters. No network calls. |
| `graphmedic demo --out DIR` | Lint the three bundled examples into text, JSON, SARIF, and HTML. Exits 0. |

`lint` options: `--format {text,json,sarif,html}`, `--out`, `--recursive`, `--config`, `--fail-on {error,warning,note,none}`, `--suggest-fix`.

`--suggest-fix` prints proposed remedies. It does not modify the file. There is no automatic rewrite.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Lint finished and no finding met the fail threshold. |
| 1 | Lint finished and a finding met the fail threshold. |
| 2 | Invalid configuration or malformed input. |
| 3 | The file’s host format has no verified adapter. |
| 4 | An internal exception escaped a rule or report writer. |

Priority when several apply: invalid input (2), then threshold findings (1), then an unsupported format (3), then success (0). `NOT_EVALUATED` does not change the exit code. The default threshold is `error`. `graphmedic demo` forces `fail_on = none` and exits 0.

## Configuration

`graphmedic.toml` version 1. Unknown keys and unknown rule ids fail validation.

```toml
version = 1
fail_on = "error"

[budgets]
max_points = 100000

[style]
max_group_depth = 8

[limits]
max_nodes = 20000
max_bytes = 8000000
max_depth = 64
max_files = 500

[rules]
disable = []

[[suppress]]
rule_id = "GM-STRUCT-006"
path = "examples/geometry_nodes/broken_scatter.json"
reason = "The dangling output already explains these unreachable nodes."
```

A suppression needs `rule_id`, `path`, and a non-empty `reason`. `graph` is optional and must match a tree on the finding’s path. Suppressed findings stay in the report and in the suppressed count. An unknown suppression id fails `validate-config`.

## Formats GraphMedic will read

| `format` | v0.1 |
| --- | --- |
| `blender.geometry_nodes.capture` version 1 | Read. Direct bpy dump. Catalog checks apply only for Blender 4.5.14. |
| `nodebridge.graph` version 1 | Read. Links live under `edges`. An omitted `valid` flag means true, matching NodeBridge 0.3.0. Catalog checks stay `NOT_EVALUATED` unless the source version is 4.5.14. |
| `gn-as-code`, `hda-as-code`, `pcg-as-code`, `shader-as-code`, `nodebridge.semantic` | Recognised and refused (exit 3). Their schemas were not available to verify. |

Unknown JSON is also exit 3. It is not reported as a healthy graph.

## Safety bounds

Untrusted JSON is data. Lint does not call `eval`, run embedded scripts, start Blender, or open a network connection. Defaults: 8 MB, 20,000 nodes, 50,000 links, JSON depth 64, 500 files, group-walk depth 64. Directory symlinks are not followed. A file symlink that leaves its parent directory is rejected. Archives (`.zip`, `.tar`, `.gz`, and the other archive suffixes) are rejected.

Reports are deterministic aside from nothing: JSON is canonical (`sort_keys`, indent 2) and contains no timestamp. SARIF 2.1.0 is checked in tests against the vendored OASIS schema.

## Layout

`src/graphmedic/` holds adapters (`parse.py`), the analysis view (`model.py`), traversal (`analyze.py`), rules, config, reports, and the CLI. The 21-rule registry is [docs/rules/README.md](docs/rules/README.md). Host support and the node subset are [docs/schema-matrix.md](docs/schema-matrix.md). What was actually readable in sibling repositories is [docs/ecosystem-audit.md](docs/ecosystem-audit.md). Known gaps are [docs/limitations.md](docs/limitations.md).

## Licence

MIT. See [LICENSE](LICENSE). The vendored SARIF schema remains an OASIS document; see [schemas/README.md](schemas/README.md).
