# Limitations

GraphMedic 0.1 is accurate on a narrow, verified slice. These are the gaps a report will not paper over.

## Version pin

Socket identifiers, enum values, and emptiness predicates come from Blender 4.5.14 LTS, build hash `62c1db4208e8`. Catalog rules (`GM-DOMAIN-*`, `GM-GEO-013`, `GM-PERF-002`, `GM-PERF-003`, and the math/zone parts of analysis) run only when `application.version` is exactly `4.5.14`. A NodeBridge graph that records Blender 4.2.23 still gets structural checks. Domain, empty-generator, and Realize Instances checks return `NOT_EVALUATED` there.

The current Blender API pages also mention later sockets such as `realize_to_point_domain`. Those names are not in the 4.5.14 probe and are not used.

## What is not a definite error

- Custom attribute domains. The 4.5 manual documents automatic interpolation. `GM-DOMAIN-002` warns only when the stored name is exactly `position` and the domain is not `POINT`.
- Named Attribute has no domain property in 4.5.14, so a consumer-domain mismatch is not diagnosed.
- Geometry component class. Probed geometry sockets are all type `GEOMETRY`. Mesh, curve, point, and instance mismatches are not inferred.
- Link type conversion. `GM-STRUCT-004` trusts a host `valid` flag. A capture file that omits `valid` while the socket types differ is `NOT_EVALUATED`, not an invalid link. NodeBridge omits `valid` when the edge is valid, and that omission is treated as true.
- Empty generators. Only constant cases that were evaluated: Grid with a vertex axis of 0, Points Count 0, Mesh Line Count 0 in Total mode. Vertices of 1 are not empty. Density 0 on Distribute Points on Faces was not evaluated and is not flagged.
- Unknown counts. `GM-PERF-003` does not fire when a count is not a constant and has no declared maximum wired from a Group Input.
- Realize Instances that only feeds Group Output. That pattern is common and is not `GM-GEO-013`. The warning is for a realize node upstream of Instance on Points or of another Realize Instances.
- Cycles inside a complete simulation or repeat pair. An SCC that contains both ends of a recognised pair is zone feedback. A type name that merely contains “Simulation”, “Repeat”, or “Zone” without a complete pair makes the rule `NOT_EVALUATED` when that is the only cycle.
- Group-reference cycles that are entangled with a complete zone pair are not separately reported.

## Formats

`gn-as-code`, Houdini HDA-as-code, Unreal PCG-as-code, and shader-as-code are refused. There is no Blender node-editor panel in this release. Lint never starts Blender. The optional export script is a separate bpy process.

`NOT_EVALUATED` does not fail the process. A strict gate that treats unevaluated rules as failures is not in v0.1.

## Other bounds

- Viewer nodes count as live inspection sinks.
- Muted-node bridging uses serialized `internal_links` and is lightly covered.
- Only the built-in name `position` has a domain check.
- Attribute names that are fields rather than constants are `NOT_EVALUATED`.
- Capture Attribute is not treated as a named write.
- `--suggest-fix` prints text. It does not emit a JSON patch and it does not rewrite the graph.
- No telemetry. The SARIF `$schema` URL is a declaration. Lint does not fetch it.
- GitHub code scanning upload is not part of v0.1. Local SARIF is validated on its own.
- `graphmedic doctor` looks for Blender on `PATH` or in `GRAPHMEDIC_BLENDER`. A binary that exists only at a private path is reported as not found.
