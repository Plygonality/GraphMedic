# Scatter, three ways

One Geometry Nodes tree, exported from Blender 4.5.14 LTS (hash `62c1db4208e8`), then copied into two derived files. No Blender screenshot was captured. The terminal transcripts below are from `graphmedic lint` on those files.

The tree is `Scatter`. Interface sockets: Geometry in `Socket_0`, Density `Socket_1` (0..100, default 4), Seed `Socket_2` (0..100000, default 7), Geometry out `Socket_3`. Nodes in the baseline: Group Input, Distribute Points on Faces, Ico Sphere, Instance on Points, Group Output.

## Valid baseline

`fixtures/blender/valid_scatter.json` is the bpy export (`application.verified: true`). The same graph is `examples/geometry_nodes/valid_scatter.json` and `graphs/valid_scatter.json`.

```text
examples/geometry_nodes/valid_scatter.json  linted  blender 4.5.14
  No findings.
  Coverage  PASS 13  FAIL 0  NOT_APPLICABLE 8  NOT_EVALUATED 0  suppressed 0
```

Exit code 0. Thirteen rules ran and found nothing. Eight did not apply because this file has no dangling id, no invalid link, no attribute nodes, no realize node, no divide, no empty generator, no nested groups, and flattening is off.

## Structurally broken

`examples/geometry_nodes/broken_scatter.json` is the export with one field edited. The link that used to enter Group Output `Socket_3` now targets `MissingSocket`, and the host `valid` flag on that link is false. Blender did not author the defect. `application.verified` is false.

| Node | What is wrong | Corrective action |
| --- | --- | --- |
| Group Output, socket `MissingSocket` | `GM-STRUCT-002` error, PROVEN. The link from Instance on Points names a socket the node does not have. | Point the link at `Socket_3`, the geometry output that the interface actually declares. |
| Group Output, socket `Socket_3` | `GM-STRUCT-003` error, PROVEN. The modifier geometry output has no incoming link. | Same repair. One restored link satisfies both rules. |
| Group Input, Distribute Points on Faces, Ico Sphere, Instance on Points | `GM-STRUCT-006` warning, PROVEN. A dangling link does not count as a resolved connection, so none of these nodes can reach an output. | Restoring `Socket_3` makes the chain reachable again. The warnings are a consequence of the broken link, not four separate wiring mistakes. |

```text
error [PROVEN] GM-STRUCT-002: Link targets an unknown socket
  at Scatter Group Output MissingSocket
error [PROVEN] GM-STRUCT-003: Required geometry output is unlinked
  at Scatter Group Output Socket_3
warning [PROVEN] GM-STRUCT-006: Node cannot reach an output
  at Scatter Distribute Points on Faces
warning [PROVEN] GM-STRUCT-006: Node cannot reach an output
  at Scatter Group Input
warning [PROVEN] GM-STRUCT-006: Node cannot reach an output
  at Scatter Ico Sphere
warning [PROVEN] GM-STRUCT-006: Node cannot reach an output
  at Scatter Instance on Points
Coverage  PASS 9  FAIL 3  NOT_APPLICABLE 9  NOT_EVALUATED 0  suppressed 0
```

Exit code 1 (`--fail-on error`).

### Re-lint after the repair

`examples/geometry_nodes/broken_scatter_fixed.json` is the broken file with `to_socket` set back to `Socket_3`.

```text
examples/geometry_nodes/broken_scatter_fixed.json  linted  blender 4.5.14
  No findings.
  Coverage  PASS 13  FAIL 0  NOT_APPLICABLE 8  NOT_EVALUATED 0  suppressed 0
```

Exit code 0. GM-STRUCT-002, GM-STRUCT-003, and the four GM-STRUCT-006 warnings are gone.

## Inefficient but connected

`examples/geometry_nodes/inefficient_scatter.json` (also `graphs/inefficient_scatter.json`) keeps the scatter and then:

1. Realize Instances consumes Instance on Points.
2. Instance Pebbles instances a second ico sphere on that realized geometry.
3. Dense Grid joins in with Vertices X = 500 and Vertices Y = 500.

The graph still has a linked Group Output. With `graphmedic.toml` (`budgets.max_points = 100000`) lint reports no errors.

| Node | Finding | Corrective action |
| --- | --- | --- |
| Realize Instances | `GM-GEO-013` warning, HEURISTIC. It sits upstream of Instance Pebbles. The 4.5 manual says realizing many instances of complex geometry can become much more expensive. This is not a measured timing. | Move Realize Instances to after Instance Pebbles, or drop the second instance stage if the realized mesh is the result you want. |
| Dense Grid | `GM-PERF-003` warning, HEURISTIC. `500 * 500 = 250000` exceeds the point budget of 100000. The bound is the serialized vertex defaults, not a cook. | Lower Vertices X or Vertices Y, or raise `budgets.max_points` when the density is intentional. |

```text
warning [HEURISTIC] GM-GEO-013: Realize Instances occurs upstream of a replicated branch; potentially expensive at high counts
  at Scatter Realize Instances
warning [HEURISTIC] GM-PERF-003: Grid Vertices X * Vertices Y bound 250000 exceeds the point budget 100000
  at Scatter Dense Grid
Coverage  PASS 15  FAIL 2  NOT_APPLICABLE 4  NOT_EVALUATED 0  suppressed 0
```

Exit code 0 on `--fail-on error`. Exit code 1 if you pass `--fail-on warning`.

## Coverage, definite checks versus suggestions

Counts are for one file each, GraphMedic 0.1.0, 21 rules.

| File | Proven failures | Heuristic suggestions | Pass | Not applicable | Not evaluated |
| --- | --- | --- | --- | --- | --- |
| valid scatter | 0 | 0 | 13 | 8 | 0 |
| broken scatter | 2 errors and 4 warnings, all PROVEN | 0 | 9 | 9 | 0 |
| inefficient scatter | 0 | 2 warnings (GM-GEO-013, GM-PERF-003) | 15 | 4 | 0 |

`NOT_APPLICABLE` means the rule’s precondition is absent (no realize node, no attribute, flattening not requested). `NOT_EVALUATED` would mean the file does not carry the semantics the rule needs. None of these three files hit that state, because they are Blender 4.5.14 captures. A NodeBridge 4.2.23 graph still lints structurally, and the catalog rules return `NOT_EVALUATED` instead of borrowing 4.5.14 socket facts.

Machine-readable copies of a combined run:

```bash
graphmedic demo --out build/demo
```

That writes `demo.txt`, `demo.json`, `demo.sarif`, and `demo.html`. The HTML file does not load a remote stylesheet.
