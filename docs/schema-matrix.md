# Supported schema and node matrix

One page for GraphMedic 0.1. A check runs only when the cell says it does. “Structural” means the rule uses ids, links, and interface records and does not need the 4.5.14 catalog.

## Formats

| Format | Adapter | Structural rules | Catalog rules (domain, empty generators, realize, count budget) |
| --- | --- | --- | --- |
| `blender.geometry_nodes.capture` v1, version `4.5.14` | yes | yes | yes |
| `blender.geometry_nodes.capture` v1, any other version | yes | yes | `NOT_EVALUATED` |
| `nodebridge.graph` v1, Blender source, version `4.5.14` | yes | yes | yes |
| `nodebridge.graph` v1, other Blender version (the published scatter is 4.2.23) | yes | yes | `NOT_EVALUATED` |
| `nodebridge.semantic` | refused, exit 3 | — | — |
| `gn-as-code`, `gn_as_code` | refused, exit 3 | — | — |
| `hda-as-code` | refused, exit 3 | — | — |
| `pcg-as-code` | refused, exit 3 | — | — |
| `shader-as-code` | refused, exit 3 | — | — |
| JSON with no `format` | refused, exit 3 | — | — |

NodeBridge edges use `{from: [node, socket], to: [node, socket]}`. `valid` is written only when false, so an omitted flag is true. Capture files leave an omitted `valid` as unknown.

## Nodes with verified 4.5.14 behaviour

Probed in Blender 4.5.14 LTS. Evidence: `fixtures/blender/probe-summary.json` and `src/graphmedic/data/blender-4.5.14.json`.

| Node | What is used | What is not claimed |
| --- | --- | --- |
| `NodeGroupInput`, `NodeGroupOutput` | Interface socket ids. Active output defaults to true. `__extend__` is ignored. | — |
| `GeometryNodeViewer` | Counts as an inspection sink for reachability. | Not a required modifier output. |
| `GeometryNodeGroup` | `group_tree` must name a tree in the file. | Group interface is not flattened unless `flatten_interfaces` is true. |
| `GeometryNodeSimulationInput` / `Output` | A paired zone is legal feedback. | An unpaired marker is `NOT_EVALUATED`, not a generic cycle error by itself. |
| `GeometryNodeRepeatInput` / `Output` | Same pairing rule. | — |
| `ShaderNodeMath` | `DIVIDE` divisor is `Value_001`. Constant 0 is `GM-DOMAIN-004`. | Omitted `operation` is not treated as divide. `FunctionNodeMath` does not exist in this build. |
| `GeometryNodeMeshGrid` | Vertex axis equal to 0 is empty. Product of the two vertex counts is a point-budget bound. | Vertices of 1 still produce a vertex. The manual sentence “smaller than two” is not the emptiness predicate. |
| `GeometryNodePoints` | Count 0 is empty. Count is a budget bound. | Point clouds are not read through `to_mesh()` alone. The probe converted through `GeometryNodePointsToVertices`. |
| `GeometryNodeMeshLine` | Count 0 in `count_mode` `TOTAL` (the default) is empty and is a budget bound. | `RESOLUTION` mode is not flagged. |
| `GeometryNodeRealizeInstances` | Inputs: Geometry, Selection, Realize All, Depth. Upstream of `GeometryNodeInstanceOnPoints` or of another realize is `GM-GEO-013`. Two live copies with the same literals are `GM-PERF-002`. | No runtime estimate. A realize that only feeds the group output is not this warning. |
| `GeometryNodeInstanceOnPoints` | Downstream target for `GM-GEO-013`. | No instance-count estimate from this node. |
| `GeometryNodeStoreNamedAttribute` | Constant `Name`. Domain enum includes POINT, EDGE, FACE, CORNER, CURVE, INSTANCE, LAYER. | Only `position` has a built-in domain check. |
| `GeometryNodeInputNamedAttribute` | Constant `Name` compared with stores on a closed pipeline. | No domain socket. Non-constant names are `NOT_EVALUATED`. |
| `ShaderNodeValue`, `FunctionNodeInputString` | Constant sources when the catalog applies. | — |

## Rules that do not need that catalog

`GM-STRUCT-001` through `GM-STRUCT-012`, `GM-PERF-004`, and `GM-PERF-005` use the serialized graph. They still refuse to invent a conversion, a flattening, or a closed attribute pipeline when the file does not say so. Those cases are `NOT_EVALUATED` or `NOT_APPLICABLE`, as each rule’s summary describes.
