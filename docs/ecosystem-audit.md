# Ecosystem audit

Recorded 2026-10-16 from the repositories this environment could actually read. GraphMedic does not modify any of them. The installable package and its fixtures do not import them.

## What resolved

`gh repo list Plygonality` returned these public repositories:

| Repository | Role relative to GraphMedic |
| --- | --- |
| [GraphMedic](https://github.com/Plygonality/GraphMedic) | This tool. The remote already existed with a one-paragraph README. |
| [NodeBridge](https://github.com/Plygonality/NodeBridge) 0.3.0, MIT, no runtime dependencies | Read-only `nodebridge.graph` v1 adapter. The compiler is not imported. |
| [Plygon-mcp](https://github.com/Plygonality/Plygon-mcp) MIT, also Siddharth Ahuja 2025 for the blender-mcp pattern (`THIRD_PARTY.md`) | Local Blender and Houdini inspection bridges. Not used for lint. |
| InstanceTrace, RomanArtifactLens, RomanRecover, WCSScene, ParityForge, OrbitWeaver, Plygonality | Unrelated public projects. Not integrated. |

NodeBridge was cloned and read at tag/tree corresponding to version 0.3.0 in `pyproject.toml`. Plygon-mcp was cloned and read for licence and purpose only.

## What did not resolve

`gh repo view` returned `Could not resolve to a Repository` for:

- `Plygonality/gn-as-code`
- `Plygonality/HDA-as-code`
- `Plygonality/Pcg-as-code`
- `Plygonality/Shader-as-code`
- `Plygonality/Collection-linter`
- `Plygonality/Blend-ci`

Those names are recognised in the parser so a file that claims them fails with `GM-INPUT-003` (exit 3). GraphMedic does not guess their JSON. It does not implement a second collection or object validator, and it does not call Blend-ci.

## NodeBridge graph contract that the adapter uses

Source: `src/nodebridge/ir/serialization.py` and `src/nodebridge/ir/graph.py` in the public tree.

- Document `format` is `nodebridge.graph`, `format_version` 1.
- Trees carry `edges`, not `links`. Each edge is `{from: [node, socket], to: [node, socket]}`.
- `GraphEdge.as_dict` writes `valid` only when it is false. `from_dict` uses `data.get("valid", True)`. The GraphMedic reader does the same: omitted `valid` on this format means true.
- `format: nodebridge.semantic` is a compiler IR (`SemanticGraph`). GraphMedic refuses it and does not run translation, Kahn topo from NodeBridge, or the conversion tables in `ir/types.py`.
- The published scatter example `examples/scatter/scatter.graph.json` records `source.application` `Blender 4.2.23 LTS` and root `ScatterRocks`. After reading `edges`, GraphMedic reports zero findings. Catalog rules are `NOT_EVALUATED` because the version is not 4.5.14.
- NodeBridge’s own support matrix is a translator confidence table for Houdini and Unreal. It is not a lint rule set, and it was not copied.

The optional test `tests/test_adapters.py` imports that scatter file only when a local checkout is present at `/tmp/audit/NodeBridge/...`. CI does not have that checkout, so the test skips. It is not a mock of a production DCC run.

## Plygon-mcp

Licence MIT. `THIRD_PARTY.md` attributes the localhost TCP + FastMCP pattern to ahujasid/blender-mcp (Siddharth Ahuja, MIT, 2025). The project inspects and edits scenes. GraphMedic lint does not talk to it and does not require it.

## Blender, verified here

Blender 4.5.14 LTS, hash `62c1db4208e8`, built 2026-09-15, was run on this machine. `download.blender.org` returned a Cloudflare 403; the binary came from the NLUUG mirror and is not committed.

- `tools/export_geometry_nodes.py` built a Geometry Nodes scatter and wrote `fixtures/blender/valid_scatter.json`. Stdout is `fixtures/blender/export.log` (`BLENDER 4.5.14 LTS`, `NODES 5`, `LINKS 6`). `application.verified` is true. The note in the file says this is a direct bpy dump because gn-as-code was not available.
- `tools/probe_geometry_nodes.py`, `tools/probe_geometry_evaluation.py`, and `tools/probe_link_validity.py` read RNA and evaluated a few constant graphs. The compact numbers are `fixtures/blender/probe-summary.json`. They feed `src/graphmedic/data/blender-4.5.14.json`.
- Link probe, re-run the same day: VALUE→VECTOR `is_valid` true, INT→VALUE true, GEOMETRY→VALUE false.
- `FunctionNodeMath` raised `Node type FunctionNodeMath undefined`. Math is `ShaderNodeMath`. DIVIDE enables `Value` and `Value_001`; `Value_002` stays disabled. The divisor identifier is `Value_001`.
- Realize Instances inputs: Geometry, Selection, Realize All, Depth. Output: Geometry.
- Store Named Attribute domain enum: POINT, EDGE, FACE, CORNER, CURVE, INSTANCE, LAYER. Named Attribute has a Name input and no domain property.
- Grid evaluation disagreed with treating “vertices smaller than two” as emptiness. Only a 0 on either axis yielded 0 vertices. The rule follows the evaluation.
- Simulation and repeat zones were paired with `pair_with_output`. Both `simulation_paired` and `repeat_paired` were true.

`tests/test_blender.py` re-runs the exporter when `GRAPHMEDIC_BLENDER`, `blender` on `PATH`, or the local 4.5.14 binary is present. Otherwise it skips. It does not mock `bpy`.

Manual pages used as rule references, for 4.5: Geometry Nodes introduction, simulation zone, repeat zone, Store Named Attribute, attributes reference (automatic interpolation; position is the point-domain built-in), Grid, Points, Math, Realize Instances. API index: `https://docs.blender.org/api/4.5/`.

## Houdini and Unreal

SideFX documents attributes on vertices, points, primitives, and detail (`https://www.sidefx.com/docs/houdini/model/attributes.html`). Epic documents PCG graphs, debugging, and metadata domains (`https://dev.epicgames.com/documentation/en-us/unreal-engine/procedural-content-generation-overview` and the PCG node reference). Neither HDA-as-code nor Pcg-as-code could be resolved, and no `hou` or Unreal editor session was available. No Houdini or PCG rule is implemented. GraphMedic does not invent a `hou` module or a PCG C++ API.

## Dependency licences

| Piece | Licence | Needed to lint |
| --- | --- | --- |
| GraphMedic | MIT | yes |
| Python standard library (`tomllib`, `json`, `argparse`) | PSF | yes |
| NodeBridge (optional reader target) | MIT | no |
| Plygon-mcp | MIT | no |
| pytest, ruff, jsonschema, build | their own OSI licences, dev only | no |
| OASIS SARIF 2.1.0 schema, vendored | OASIS, not relicensed | tests only |

No runtime package is downloaded during `graphmedic lint`.
