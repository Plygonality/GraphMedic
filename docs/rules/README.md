# Rule registry

Twenty-one rules. Each one is registered in `src/graphmedic/rules.py` and has a failing fixture and a passing fixture under `tests/fixtures/rules/`. Confidence is `PROVEN` (the serialized graph entails it), `HIGH_CONFIDENCE` (the manual and the probed data agree, and the failure itself was not cooked), or `HEURISTIC` (a suggestion, not a measured cost).

`graphmedic rules` prints this list. `graphmedic explain GM-STRUCT-002` prints one entry.

## Graph structure

| ID | Severity | Confidence | Title |
| --- | --- | --- | --- |
| GM-STRUCT-001 | error | PROVEN | Missing or duplicate node id |
| GM-STRUCT-002 | error | PROVEN | Dangling link |
| GM-STRUCT-003 | error | PROVEN | Required geometry output |
| GM-STRUCT-004 | error | PROVEN | Host-marked invalid link |
| GM-STRUCT-005 | error | PROVEN | Disconnected required geometry input |
| GM-STRUCT-006 | warning | PROVEN | Unreachable node |
| GM-STRUCT-007 | error | PROVEN | Cyclic dependency |
| GM-STRUCT-008 | error | PROVEN | Non-finite number |
| GM-STRUCT-009 | error | PROVEN | Malformed min, max, or step |
| GM-STRUCT-010 | error | PROVEN | Constant outside its interval |
| GM-STRUCT-011 | error | PROVEN | Broken interface binding |
| GM-STRUCT-012 | warning | PROVEN | Flattened parameter identifier collision |

### GM-STRUCT-001

Every node needs one stable id inside its tree. A blank or repeated id makes diagnostics and diffs ambiguous. Give every node a unique id and export again.

### GM-STRUCT-002

A link must name a node and a socket that exist in the same tree. The message for a missing socket is “Link targets an unknown socket”. Correct the identifier or regenerate the export.

### GM-STRUCT-003

A geometry node tree needs an active Group Output whose geometry input is linked. Without that connection the modifier has no geometry result. A file with no geometry tree leaves the rule `NOT_EVALUATED` only when no geometry tree exists to judge.

### GM-STRUCT-004

A link the host marked `valid: false` is a broken connection. GraphMedic does not invent conversion rules when the flag is absent. Different socket types with `valid` omitted are `NOT_EVALUATED`. `valid: true` across types is a pass. On `nodebridge.graph`, an omitted `valid` means true, because NodeBridge writes the flag only when it is false.

### GM-STRUCT-005

A live, unmuted node with an enabled geometry input, no default, and `optional` not true, and no resolved link, is undriven. Group Output and Viewer are excluded (the output case is GM-STRUCT-003).

### GM-STRUCT-006

A node that cannot reach a Group Output or Viewer does not affect the result. Only resolved, unmuted links count. The rule is skipped when the tree has no output or viewer sink.

### GM-STRUCT-007

A cycle is illegal unless it is the feedback loop of a recognised simulation or repeat zone (`GeometryNodeSimulationInput`/`Output` or `GeometryNodeRepeatInput`/`Output`). A type name that contains Simulation, Repeat, or Zone without a complete pair makes this rule `NOT_EVALUATED` when that is the only cycle. Group-reference cycles are reported.

### GM-STRUCT-008

`NaN` and infinity in parameters, socket defaults, or interface values are not usable geometry values. The number is in the file. It is not the result of a cook. JSON `1e309` becomes infinity on parse and is reported.

### GM-STRUCT-009

A declared interval needs `min` no greater than `max`, and a step above zero. The rule is `NOT_APPLICABLE` when nothing is declared.

### GM-STRUCT-010

A constant that is actually used falls outside the min and max serialized beside it. The comparison uses the interface value when one is set, otherwise the default. Linked inputs are not judged by an unused default. Non-finite values are left to GM-STRUCT-008.

### GM-STRUCT-011

Group Input outputs must exist as interface inputs. Group Output inputs must exist as interface outputs. A `GeometryNodeGroup` whose `group_tree` is missing, and an `interface_values` key that names nothing, are the same class of broken binding.

### GM-STRUCT-012

When the file sets `flatten_interfaces` true, exported input identifiers must be unique across reachable trees. Identical display names with different identifiers do not collide. When flattening is not requested the rule is `NOT_APPLICABLE`.

## Domain and numeric facts

| ID | Severity | Confidence | Title |
| --- | --- | --- | --- |
| GM-DOMAIN-001 | error | PROVEN | Named attribute read without a local write |
| GM-DOMAIN-002 | warning | HIGH_CONFIDENCE | Built-in attribute domain conflict |
| GM-DOMAIN-003 | warning | PROVEN | Empty constant generator |
| GM-DOMAIN-004 | error | PROVEN | Static division by zero |

### GM-DOMAIN-001

On a closed pipeline (`closed_attribute_pipeline: true`), a constant Named Attribute name needs a Store Named Attribute with the same name. An open pipeline returns `NOT_EVALUATED` with reason `UNVERIFIABLE_ATTRIBUTE_SOURCE`. A non-constant name is `NOT_EVALUATED`. No attribute nodes means `NOT_APPLICABLE`. Capture Attribute is not a named write.

### GM-DOMAIN-002

Store Named Attribute cannot change the domain of the built-in `position` attribute. The 4.5 manual says built-in domains cannot be changed, and position lives on points. A custom name such as `mask` on `FACE` is a pass. A missing domain on a built-in store is `NOT_EVALUATED`. This warning was not confirmed by cooking the failing graph.

### GM-DOMAIN-003

A generator whose verified constant settings produce no elements:

- Grid `Vertices X` or `Vertices Y` equal to 0. A value of 1 is not empty. Blender 4.5.14 evaluation: `(0,0)` and `(0,3)` yield 0 vertices; `(1,1)` yields 1; `(1,2)` and `(2,1)` yield 2.
- Points `Count` 0. Count 1 yields 1 vertex after `GeometryNodePointsToVertices`.
- Mesh Line `Count` 0 when `count_mode` is `TOTAL` (the default). `RESOLUTION` is not flagged.

### GM-DOMAIN-004

`ShaderNodeMath` with `operation` `DIVIDE` and socket `Value_001` constant 0. An unknown divisor is `NOT_EVALUATED`. An omitted operation is not treated as divide.

## Performance and style

| ID | Severity | Confidence | Title |
| --- | --- | --- | --- |
| GM-GEO-013 | warning | HEURISTIC | Realize Instances upstream of instancing |
| GM-PERF-002 | warning | HEURISTIC | Duplicated expensive node |
| GM-PERF-003 | warning | HEURISTIC | Count bound over budget |
| GM-PERF-004 | note | HEURISTIC | Deep group nesting |
| GM-PERF-005 | note | PROVEN | Unused exposed parameter |

### GM-GEO-013

Realize Instances ahead of Instance on Points, or ahead of another Realize Instances, duplicates geometry before a replicated branch. The message is “Realize Instances occurs upstream of a replicated branch; potentially expensive at high counts”. The 4.5 manual says realizing many instances can become much more expensive. This check does not estimate a runtime. A realize node that only feeds Group Output is a pass. No realize node means `NOT_APPLICABLE`. Requires the 4.5.14 catalog.

### GM-PERF-002

Two reachable Realize Instances nodes with the same parameters and the same literal inputs. Only node types whose manual describes a real cost are eligible. The finding is a suggestion, not a measured regression.

### GM-PERF-003

A constant point or vertex product, or a declared maximum wired straight from a Group Input into a count socket, is above `budgets.max_points`. Grid uses `Vertices X * Vertices Y`. No budget means `NOT_APPLICABLE`. An unbounded count is `NOT_EVALUATED` and produces no finding.

### GM-PERF-004

Group-reference depth above `style.max_group_depth` (default 8) is hard to inspect. Depth is the number of group-node hops. This is not a cook-time claim. A cyclic group walk is `NOT_EVALUATED`.

### GM-PERF-005

An interface input whose identifier is never the source socket of a Group Input link is unused. The check runs only when the tree has an interface definition.

## References

Blender 4.5 manual pages cited by the rules:

- Geometry Nodes introduction, simulation zone, repeat zone
- Store Named Attribute and the attributes reference
- Grid, Points, Math, Realize Instances

API index: `https://docs.blender.org/api/4.5/`
