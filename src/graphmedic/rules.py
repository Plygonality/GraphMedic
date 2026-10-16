"""Registered diagnostics. Each rule returns one coverage status.

FAIL means at least one finding. NOT_EVALUATED means the graph does not
carry the semantics the rule needs. NOT_APPLICABLE means the rule's
precondition is absent. PASS means the rule ran and found nothing.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from graphmedic.analyze import Analysis
from graphmedic.catalog import Catalog
from graphmedic.model import Diagnostic, Document, Node, Tree
from graphmedic.values import exactly_equal, is_number, non_finite_token, walk_numbers


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    confidence: str
    summary: str
    why: str
    fix: str
    references: tuple[str, ...]


@dataclass
class Evaluation:
    rule: Rule
    status: str
    findings: list[Diagnostic]
    reason: str = ""


def _rules() -> list[Rule]:
    manual = "https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/"
    api = "https://docs.blender.org/api/4.5/"
    return [
        Rule(
            "GM-STRUCT-001",
            "Missing or duplicate node id",
            "error",
            "PROVEN",
            "Every node needs one stable id inside its tree.",
            "Diagnostics, suppressions, and diffs identify nodes by that id. A blank or repeated id makes the location ambiguous.",
            "Give every node a unique id and export the graph again.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-002",
            "Dangling link",
            "error",
            "PROVEN",
            "A link must name a node and a socket that exist in the same tree.",
            "The serialized endpoint is not on the node, so the connection cannot carry a value.",
            "Correct the socket identifier or regenerate the graph export.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-003",
            "Required geometry output",
            "error",
            "PROVEN",
            "A geometry node tree needs an active Group Output whose geometry input is linked.",
            "Without that connection the modifier has no geometry result.",
            "Link the finished geometry into the active Group Output.",
            (manual + "introduction.html",),
        ),
        Rule(
            "GM-STRUCT-004",
            "Host-marked invalid link",
            "error",
            "PROVEN",
            "A link the host explicitly marked invalid is a broken connection.",
            "Blender records is_valid on the link. GraphMedic does not invent conversion rules when that flag is absent.",
            "Reconnect the sockets in Blender and export again, or remove the link.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-005",
            "Disconnected required geometry input",
            "error",
            "PROVEN",
            "A live node with an enabled geometry input, no default, and no link is not driven.",
            "The input is not marked optional and the export gives it no fallback value.",
            "Connect a geometry source or mark the socket optional in the export if the host treats it as optional.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-006",
            "Unreachable node",
            "warning",
            "PROVEN",
            "A node that cannot reach a Group Output or Viewer does not affect the result.",
            "Only resolved, unmuted links count. Simulation and repeat zones stay reachable when their outputs are connected.",
            "Connect the node to the result or remove it.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-007",
            "Cyclic dependency",
            "error",
            "PROVEN",
            "A cycle is illegal unless it is the feedback loop of a recognised simulation or repeat zone.",
            "Blender 4.5 evaluates simulation and repeat zones as paired Input and Output nodes. Other cycles have no defined cook order.",
            "Break the cycle, or place the feedback inside a simulation or repeat zone.",
            (
                "https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/simulation/simulation_zone.html",
                "https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/utilities/repeat_zone.html",
            ),
        ),
        Rule(
            "GM-STRUCT-008",
            "Non-finite number",
            "error",
            "PROVEN",
            "NaN and infinity in serialized parameters are not usable geometry values.",
            "The number is present in the file. It is not the result of evaluating the graph.",
            "Replace the value with a finite number and export again.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-009",
            "Malformed min, max, or step",
            "error",
            "PROVEN",
            "A declared interval needs min no greater than max, and a step above zero.",
            "The export itself contains the contradictory declaration.",
            "Fix the interface or socket min, max, and step.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-010",
            "Constant outside its interval",
            "error",
            "PROVEN",
            "A constant that is actually used falls outside the min and max serialized beside it.",
            "The comparison uses the interface value when one is set, otherwise the default. Linked inputs are not judged by an unused default.",
            "Move the value inside the interval or widen the interval.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-011",
            "Broken interface binding",
            "error",
            "PROVEN",
            "Group sockets, group-node references, and interface value keys must name something the file contains.",
            "The binding is part of the serialized tree, so the mismatch does not depend on a DCC session.",
            "Regenerate the group interface or point the group node at a tree that exists in the file.",
            (api,),
        ),
        Rule(
            "GM-STRUCT-012",
            "Flattened parameter identifier collision",
            "warning",
            "PROVEN",
            "When the file asks for flattened interfaces, exported input identifiers must be unique.",
            "Identical labels in different groups are fine. The same identifier is not, once the file says those interfaces are flattened together.",
            "Give each flattened input its own identifier, or turn flattening off.",
            (api,),
        ),
        Rule(
            "GM-DOMAIN-001",
            "Named attribute read without a local write",
            "error",
            "PROVEN",
            "On a closed pipeline, a constant Named Attribute name needs a Store Named Attribute with the same name.",
            "An open pipeline can legally read attributes created outside the graph. That case is UNVERIFIABLE_ATTRIBUTE_SOURCE, not an error.",
            "Store the attribute in the graph, or leave closed_attribute_pipeline unset if the name comes from the input geometry.",
            ("https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/attribute/store_named_attribute.html",),
        ),
        Rule(
            "GM-DOMAIN-002",
            "Built-in attribute domain conflict",
            "warning",
            "HIGH_CONFIDENCE",
            "Store Named Attribute cannot change the domain of the built-in position attribute.",
            "The 4.5 manual says built-in domains cannot be changed, and position lives on the point domain. Custom attributes are interpolated between domains, so a domain difference on a custom name is not an error.",
            "Store position on the POINT domain, or store the data under a new name.",
            (
                "https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/attribute/store_named_attribute.html",
                "https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/attributes_reference.html",
            ),
        ),
        Rule(
            "GM-DOMAIN-003",
            "Empty constant generator",
            "warning",
            "PROVEN",
            "A generator whose verified constant settings produce no elements is an empty source.",
            "The predicate comes from evaluating those node settings in Blender 4.5.14, not from an expression interpreter.",
            "Raise the count or vertex values, or remove the generator.",
            (
                "https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/mesh/primitives/grid.html",
                "https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/point/points.html",
            ),
        ),
        Rule(
            "GM-DOMAIN-004",
            "Static division by zero",
            "error",
            "PROVEN",
            "A Math node set to Divide whose divisor socket is the constant 0 has no numeric result.",
            "In Blender 4.5.14 the divisor of ShaderNodeMath DIVIDE is the socket Value_001.",
            "Change the divisor or the operation.",
            ("https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/utilities/math/math.html",),
        ),
        Rule(
            "GM-GEO-013",
            "Realize Instances upstream of instancing",
            "warning",
            "HEURISTIC",
            "Realize Instances ahead of Instance on Points, or ahead of another Realize Instances, duplicates geometry before a replicated branch.",
            "The Blender 4.5 manual says realizing many instances of complex geometry can become much more expensive. This check does not estimate a runtime.",
            "Move Realize Instances to the end of the instance chain, after the last Instance on Points.",
            ("https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/instances/realize_instances.html",),
        ),
        Rule(
            "GM-PERF-002",
            "Duplicated expensive node",
            "warning",
            "HEURISTIC",
            "Two reachable Realize Instances nodes with the same parameters and the same literal inputs repeat the same work.",
            "Only node types whose manual describes a real cost are eligible. The finding is a suggestion, not a measured regression.",
            "Keep one of the nodes and share its output.",
            ("https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/instances/realize_instances.html",),
        ),
        Rule(
            "GM-PERF-003",
            "Count bound over budget",
            "warning",
            "HEURISTIC",
            "A constant point or vertex product, or a declared maximum wired to that count, is above budgets.max_points.",
            "Counts that are not constant and have no declared maximum are left unevaluated. They do not become a budget finding.",
            "Lower the count or raise budgets.max_points if the cost is intentional.",
            ("https://docs.blender.org/manual/en/4.5/modeling/geometry_nodes/point/points.html",),
        ),
        Rule(
            "GM-PERF-004",
            "Deep group nesting",
            "note",
            "HEURISTIC",
            "Group chains deeper than style.max_group_depth are hard to inspect.",
            "This is a maintainability note. It is not a claim about cook time.",
            "Collapse a few levels or raise style.max_group_depth.",
            (),
        ),
        Rule(
            "GM-PERF-005",
            "Unused exposed parameter",
            "note",
            "PROVEN",
            "An interface input that the Group Input node never links is not read by the tree.",
            "The check runs only when the tree actually has an interface definition.",
            "Link the socket or remove it from the interface.",
            (api,),
        ),
    ]


RULES: dict[str, Rule] = {rule.id: rule for rule in _rules()}
_CHECKS: dict[str, Callable[[Context], Evaluation]] = {}


@dataclass
class Context:
    document: Document
    analysis: Analysis
    catalog: Catalog
    max_group_depth: int
    max_points: int | None


def register(rule_id: str) -> Callable[[Callable[[Context], Evaluation]], Callable[[Context], Evaluation]]:
    def wrap(fn: Callable[[Context], Evaluation]) -> Callable[[Context], Evaluation]:
        _CHECKS[rule_id] = fn
        return fn

    return wrap


def evaluate_all(ctx: Context, *, enabled: set[str] | None, disabled: set[str]) -> list[Evaluation]:
    results = []
    for rule_id, rule in RULES.items():
        if rule_id in disabled or (enabled is not None and rule_id not in enabled):
            results.append(Evaluation(rule, "NOT_APPLICABLE", [], "disabled by config"))
            continue
        results.append(_CHECKS[rule_id](ctx))
    return results


def _emit(
    ctx: Context,
    rule: Rule,
    *,
    message: str,
    tree: Tree | None = None,
    node: Node | None = None,
    socket: str | None = None,
    related: tuple[str, ...] = (),
    evidence: dict[str, Any] | None = None,
    why: str | None = None,
    fix: str | None = None,
    severity: str | None = None,
    confidence: str | None = None,
) -> Diagnostic:
    version = ctx.catalog.version if rule.id.startswith(("GM-DOMAIN", "GM-GEO", "GM-PERF-002", "GM-PERF-003")) else None
    applicability: dict[str, Any] = {"host": ctx.document.host or "unknown"}
    if version and ctx.analysis.catalog_applies:
        applicability["minimum_verified_version"] = version
    elif ctx.document.version:
        applicability["graph_version"] = ctx.document.version
    return Diagnostic(
        rule_id=rule.id,
        severity=severity or rule.severity,
        confidence=confidence or rule.confidence,
        status="FAIL",
        message=message,
        graph_path=ctx.analysis.paths.get(tree.name, (tree.name,)) if tree else (),
        node_id=node.id if node and node.id else None,
        socket=socket,
        related_nodes=related,
        evidence=evidence or {},
        why=why or rule.why,
        fix=fix or rule.fix,
        applicability=applicability,
        line=node.line if node else None,
    )


def _need_catalog(ctx: Context, rule: Rule) -> Evaluation | None:
    if ctx.analysis.catalog_applies:
        return None
    return Evaluation(rule, "NOT_EVALUATED", [], ctx.analysis.catalog_reason or "verified node catalog does not apply")


def _finish(rule: Rule, findings: list[Diagnostic], *, empty_status: str = "PASS", reason: str = "") -> Evaluation:
    if findings:
        return Evaluation(rule, "FAIL", findings, reason)
    return Evaluation(rule, empty_status, [], reason)


@register("GM-STRUCT-001")
def rule_node_ids(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-001"]
    findings = []
    for tree in ctx.document.trees:
        counts: dict[str, list[Node]] = defaultdict(list)
        for node in tree.nodes:
            counts[node.id].append(node)
        for node_id, nodes in counts.items():
            if node_id == "":
                for node in nodes:
                    findings.append(
                        _emit(ctx, rule, message="Node is missing a stable id", tree=tree, node=node, evidence={"internal_id": node.internal_id})
                    )
            elif len(nodes) > 1:
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Node id is duplicated",
                        tree=tree,
                        node=nodes[0],
                        related=tuple(node.id for node in nodes[1:]),
                        evidence={"id": node_id, "count": len(nodes)},
                    )
                )
    return _finish(rule, findings)


@register("GM-STRUCT-002")
def rule_dangling(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-002"]
    findings = []
    if not any(tree.links for tree in ctx.document.trees):
        return Evaluation(rule, "NOT_APPLICABLE", [], "the graph has no links")
    for tree in ctx.document.trees:
        grouped = tree.by_id()
        for link in tree.links:
            sources = grouped.get(link.from_node, [])
            targets = grouped.get(link.to_node, [])
            if not sources or not targets:
                missing = link.to_node if not targets else link.from_node
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Link references an unknown node",
                        tree=tree,
                        node=sources[0] if sources else (targets[0] if targets else None),
                        socket=link.to_socket,
                        evidence={"link_index": link.index, "missing_node": missing},
                    )
                )
                continue
            source = sources[0]
            target = targets[0]
            if source.socket(link.from_socket, output=True) is None:
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Link targets an unknown socket",
                        tree=tree,
                        node=source,
                        socket=link.from_socket,
                        related=(target.id,),
                        evidence={"link_index": link.index, "end": "from"},
                    )
                )
            if target.socket(link.to_socket, output=False) is None:
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Link targets an unknown socket",
                        tree=tree,
                        node=target,
                        socket=link.to_socket,
                        related=(source.id,),
                        evidence={"link_index": link.index, "end": "to"},
                    )
                )
    return _finish(rule, findings)


@register("GM-STRUCT-003")
def rule_output(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-003"]
    findings = []
    applicable = False
    for tree in ctx.document.trees:
        if tree.bl_idname != "GeometryNodeTree" and tree.kind != "geometry":
            continue
        applicable = True
        outputs = [node for node in tree.nodes if node.type in ctx.catalog.output_types()]
        active = [node for node in outputs if node.parameters.get("is_active_output", True) is not False]
        if not active:
            findings.append(
                _emit(
                    ctx,
                    rule,
                    message="Geometry tree has no active Group Output",
                    tree=tree,
                    evidence={"output_nodes": len(outputs)},
                )
            )
            continue
        linked = _linked_sockets(ctx, tree.name)
        for node in active:
            geometry = [socket for socket in node.inputs if socket.enabled and socket.type_class == "GEOMETRY" and socket.identifier != "__extend__"]
            if not geometry:
                findings.append(_emit(ctx, rule, message="Active Group Output has no geometry socket", tree=tree, node=node))
                continue
            for socket in geometry:
                if (node.internal_id, socket.identifier) not in linked:
                    findings.append(
                        _emit(
                            ctx,
                            rule,
                            message="Required geometry output is unlinked",
                            tree=tree,
                            node=node,
                            socket=socket.identifier,
                            evidence={"socket_name": socket.name},
                        )
                    )
    if not applicable:
        return Evaluation(rule, "NOT_EVALUATED", [], "v0.1 checks the required output of GeometryNodeTree only")
    return _finish(rule, findings)


@register("GM-STRUCT-004")
def rule_invalid_link(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-004"]
    findings = []
    saw_link = False
    unknown = False
    for tree in ctx.document.trees:
        for link in ctx.analysis.links:
            if link.tree != tree.name or not link.known:
                continue
            saw_link = True
            if link.valid is False:
                target = _node(tree, link.to_id)
                source = _node(tree, link.from_id)
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Host marked this link invalid",
                        tree=tree,
                        node=target,
                        socket=link.to_socket,
                        related=(source.id,) if source and source.id else (),
                        evidence={"link_index": link.index, "valid": False},
                    )
                )
            elif link.valid is None:
                source = _node(tree, link.from_id)
                target = _node(tree, link.to_id)
                if source and target:
                    out_socket = source.socket(link.from_socket, output=True)
                    in_socket = target.socket(link.to_socket, output=False)
                    if out_socket and in_socket and out_socket.type_class != in_socket.type_class and "UNKNOWN" not in (out_socket.type_class, in_socket.type_class):
                        unknown = True
    if findings:
        return Evaluation(rule, "FAIL", findings, "one or more links omit a host validity flag" if unknown else "")
    if unknown:
        return Evaluation(
            rule,
            "NOT_EVALUATED",
            [],
            "a link joins different socket types and the file does not say whether the host accepted it",
        )
    if not saw_link:
        return Evaluation(rule, "NOT_APPLICABLE", [], "the graph has no resolved links")
    return Evaluation(rule, "PASS", [])


@register("GM-STRUCT-005")
def rule_required_input(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-005"]
    findings = []
    applicable = False
    skip_types = ctx.catalog.output_types() | ctx.catalog.viewer_types()
    for tree in ctx.document.trees:
        linked = _linked_sockets(ctx, tree.name)
        for node in tree.nodes:
            if node.type in skip_types or node.muted:
                continue
            if (tree.name, node.internal_id) not in ctx.analysis.live:
                continue
            for socket in node.inputs:
                if socket.identifier == "__extend__" or not socket.enabled or socket.optional is True:
                    continue
                if socket.type_class != "GEOMETRY" or socket.default is not None:
                    continue
                applicable = True
                if (node.internal_id, socket.identifier) not in linked:
                    findings.append(
                        _emit(
                            ctx,
                            rule,
                            message="Required geometry input is disconnected",
                            tree=tree,
                            node=node,
                            socket=socket.identifier,
                            evidence={"socket_name": socket.name},
                        )
                    )
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if not applicable:
        return Evaluation(rule, "NOT_APPLICABLE", [], "no live node has an enabled geometry input without a default")
    return Evaluation(rule, "PASS", [])


@register("GM-STRUCT-006")
def rule_dead(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-006"]
    findings = []
    for tree in ctx.document.trees:
        if not any(_is_output(node, ctx) for node in tree.nodes):
            continue
        for node in tree.nodes:
            if node.type == "NodeFrame" or (tree.name, node.internal_id) in ctx.analysis.sinks:
                continue
            if (tree.name, node.internal_id) not in ctx.analysis.live:
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Node cannot reach an output",
                        tree=tree,
                        node=node,
                        evidence={"node_type": node.type},
                    )
                )
    return _finish(rule, findings)


@register("GM-STRUCT-007")
def rule_cycles(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-007"]
    findings = []
    unevaluated: list[str] = []
    pairs = ctx.catalog.zone_pairs()
    markers = tuple(ctx.catalog.data["unrecognised_zone_markers"])
    for component in ctx.analysis.sccs:
        tree_name = component[0][0]
        tree = ctx.document.tree(tree_name)
        if tree is None:
            continue
        nodes = [_node(tree, internal) for _, internal in component]
        typed = [node for node in nodes if node is not None]
        types = {node.type for node in typed}
        if any(set(pair) <= types for pair in pairs):
            continue
        if any(any(marker in node.type for marker in markers) for node in typed):
            unevaluated.append(", ".join(sorted(types)))
            continue
        anchor = typed[0] if typed else None
        findings.append(
            _emit(
                ctx,
                rule,
                message="Cyclic dependency outside a simulation or repeat zone",
                tree=tree,
                node=anchor,
                related=tuple(node.id for node in typed if node.id),
                evidence={"nodes": [node.id or node.internal_id for node in typed]},
            )
        )
    for cycle in ctx.analysis.group_cycles:
        root = ctx.document.root_tree
        findings.append(
            _emit(
                ctx,
                rule,
                message="Group references form a cycle",
                tree=root,
                evidence={"group_cycle": cycle},
                why="Nested group expansion would not terminate.",
                fix="Remove the group reference that points back at an ancestor.",
            )
        )
    if findings:
        reason = ""
        if unevaluated:
            reason = "unrecognised zone construct not classified as an illegal cycle: " + "; ".join(unevaluated)
        return Evaluation(rule, "FAIL", findings, reason)
    if unevaluated:
        return Evaluation(
            rule,
            "NOT_EVALUATED",
            [],
            "unrecognised zone construct: " + "; ".join(unevaluated),
        )
    return Evaluation(rule, "PASS", [])


@register("GM-STRUCT-008")
def rule_non_finite(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-008"]
    findings = []
    for tree in ctx.document.trees:
        for node in tree.nodes:
            for path, value in walk_numbers(node.parameters):
                token = non_finite_token(value)
                if token:
                    findings.append(
                        _emit(
                            ctx,
                            rule,
                            message=f"Non-finite value {token} in parameters",
                            tree=tree,
                            node=node,
                            evidence={"path": list(path), "value": token},
                        )
                    )
            for socket in node.inputs + node.outputs:
                for label, number in (("default", socket.default), ("min_value", socket.min_value), ("max_value", socket.max_value), ("step", socket.step)):
                    token = non_finite_token(number)
                    if token:
                        findings.append(
                            _emit(
                                ctx,
                                rule,
                                message=f"Non-finite value {token} on socket {label}",
                                tree=tree,
                                node=node,
                                socket=socket.identifier,
                                evidence={"field": label, "value": token},
                            )
                        )
        for item in tree.interface:
            for label, number in (("default", item.default), ("value", item.value), ("min_value", item.min_value), ("max_value", item.max_value), ("step", item.step)):
                token = non_finite_token(number)
                if token:
                    findings.append(
                        _emit(
                            ctx,
                            rule,
                            message=f"Non-finite value {token} on interface {label}",
                            tree=tree,
                            socket=item.identifier,
                            evidence={"field": label, "value": token, "interface": True},
                        )
                    )
    return _finish(rule, findings)


@register("GM-STRUCT-009")
def rule_intervals(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-009"]
    findings = []
    saw = False
    for tree in ctx.document.trees:
        for node in tree.nodes:
            for socket in node.inputs:
                saw = _interval_findings(ctx, rule, findings, tree, node, socket.identifier, socket.min_value, socket.max_value, socket.step) or saw
        for item in tree.interface:
            saw = _interval_findings(ctx, rule, findings, tree, None, item.identifier, item.min_value, item.max_value, item.step) or saw
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if not saw:
        return Evaluation(rule, "NOT_APPLICABLE", [], "no min, max, or step is declared")
    return Evaluation(rule, "PASS", [])


def _interval_findings(ctx, rule, findings, tree, node, socket, low, high, step) -> bool:
    saw = low is not None or high is not None or step is not None
    if is_number(low) and is_number(high) and non_finite_token(low) is None and non_finite_token(high) is None and float(low) > float(high):
        findings.append(
            _emit(ctx, rule, message="Declared minimum is greater than maximum", tree=tree, node=node, socket=socket, evidence={"min_value": low, "max_value": high})
        )
    if step is not None and non_finite_token(step) is None and is_number(step) and float(step) <= 0:
        findings.append(_emit(ctx, rule, message="Declared step is not positive", tree=tree, node=node, socket=socket, evidence={"step": step}))
    return saw


@register("GM-STRUCT-010")
def rule_outside(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-010"]
    findings = []
    saw = False
    for tree in ctx.document.trees:
        linked = _linked_sockets(ctx, tree.name)
        for node in tree.nodes:
            for socket in node.inputs:
                if (node.internal_id, socket.identifier) in linked:
                    continue
                if socket.min_value is None and socket.max_value is None:
                    continue
                saw = True
                _range_finding(ctx, rule, findings, tree, node, socket.identifier, socket.default, socket.min_value, socket.max_value)
        for item in tree.interface:
            if item.min_value is None and item.max_value is None:
                continue
            saw = True
            _range_finding(ctx, rule, findings, tree, None, item.identifier, item.current, item.min_value, item.max_value)
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if not saw:
        return Evaluation(rule, "NOT_APPLICABLE", [], "no used value has a declared interval")
    return Evaluation(rule, "PASS", [])


def _range_finding(ctx, rule, findings, tree, node, socket, value, low, high) -> None:
    if not is_number(value) or non_finite_token(value):
        return
    number = float(value)
    below = low is not None and non_finite_token(low) is None and number < float(low)
    above = high is not None and non_finite_token(high) is None and number > float(high)
    if below or above:
        findings.append(
            _emit(
                ctx,
                rule,
                message="Constant value is outside the declared interval",
                tree=tree,
                node=node,
                socket=socket,
                evidence={"value": value, "min_value": low, "max_value": high},
            )
        )


@register("GM-STRUCT-011")
def rule_bindings(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-011"]
    findings = []
    names = {tree.name for tree in ctx.document.trees}
    applicable = False
    for tree in ctx.document.trees:
        inputs = {item.identifier for item in tree.interface if item.in_out == "INPUT"}
        outputs = {item.identifier for item in tree.interface if item.in_out == "OUTPUT"}
        labels = {item.name for item in tree.interface}
        if tree.interface:
            applicable = True
        for node in tree.nodes:
            if node.type == "NodeGroupInput":
                for socket in node.outputs:
                    if socket.identifier == "__extend__":
                        continue
                    if socket.identifier not in inputs:
                        findings.append(
                            _emit(
                                ctx,
                                rule,
                                message="Group Input socket is not in the interface",
                                tree=tree,
                                node=node,
                                socket=socket.identifier,
                            )
                        )
            if node.type in ctx.catalog.output_types():
                for socket in node.inputs:
                    if socket.identifier == "__extend__":
                        continue
                    if socket.identifier not in outputs:
                        findings.append(
                            _emit(
                                ctx,
                                rule,
                                message="Group Output socket is not in the interface",
                                tree=tree,
                                node=node,
                                socket=socket.identifier,
                            )
                        )
            if node.type == "GeometryNodeGroup" or (node.group_tree and node.type not in {"NodeGroupInput", "NodeGroupOutput"}):
                applicable = True
                if not node.group_tree or node.group_tree not in names:
                    findings.append(
                        _emit(
                            ctx,
                            rule,
                            message="Group node references a tree that is not in the file",
                            tree=tree,
                            node=node,
                            evidence={"group_tree": node.group_tree},
                        )
                    )
        for key in tree.interface_values:
            applicable = True
            if key not in inputs and key not in labels and key not in outputs:
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Interface value names a parameter that is not in the interface",
                        tree=tree,
                        socket=key,
                        evidence={"key": key},
                    )
                )
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if not applicable:
        return Evaluation(rule, "NOT_APPLICABLE", [], "the graph has no interface or group reference to check")
    return Evaluation(rule, "PASS", [])


@register("GM-STRUCT-012")
def rule_flatten(ctx: Context) -> Evaluation:
    rule = RULES["GM-STRUCT-012"]
    if not ctx.document.flatten_interfaces:
        return Evaluation(rule, "NOT_APPLICABLE", [], "flatten_interfaces is not set, so nested identifiers are not merged")
    seen: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for tree in ctx.document.trees:
        if tree.name != ctx.document.root and tree.name not in _reachable_groups(ctx):
            continue
        for item in tree.interface:
            if item.in_out != "INPUT":
                continue
            seen[item.identifier].append((tree.name, item.name))
    findings = []
    for identifier, owners in sorted(seen.items()):
        if len(owners) > 1:
            first = ctx.document.tree(owners[0][0])
            findings.append(
                _emit(
                    ctx,
                    rule,
                    message="Flattened interface identifier is used in more than one group",
                    tree=first,
                    socket=identifier,
                    related=tuple(name for name, _label in owners),
                    evidence={"identifier": identifier, "owners": [{"tree": name, "name": label} for name, label in owners]},
                )
            )
    return _finish(rule, findings)


@register("GM-DOMAIN-001")
def rule_attributes(ctx: Context) -> Evaluation:
    rule = RULES["GM-DOMAIN-001"]
    blocked = _need_catalog(ctx, rule)
    if blocked:
        return blocked
    store_type = ctx.catalog.data["attribute_store"]["node_type"]
    read_type = ctx.catalog.data["attribute_read"]["node_type"]
    name_socket = ctx.catalog.data["attribute_read"]["name_socket"]
    reads: list[tuple[Tree, Node, str | None]] = []
    writes: set[str] = set()
    unverifiable = False
    for tree in ctx.document.trees:
        for node in tree.nodes:
            if node.type == store_type:
                name = _name_constant(ctx, tree, node, ctx.catalog.data["attribute_store"]["name_socket"])
                if name:
                    writes.add(name)
                elif _socket_present(node, ctx.catalog.data["attribute_store"]["name_socket"]):
                    unverifiable = True
            elif node.type == read_type:
                name = _name_constant(ctx, tree, node, name_socket)
                reads.append((tree, node, name))
                if not name:
                    unverifiable = True
    if not reads and not any(node.type == store_type for tree in ctx.document.trees for node in tree.nodes):
        return Evaluation(rule, "NOT_APPLICABLE", [], "the graph has no named attribute nodes")
    if ctx.document.closed_attribute_pipeline is not True:
        return Evaluation(rule, "NOT_EVALUATED", [], "UNVERIFIABLE_ATTRIBUTE_SOURCE")
    findings = []
    for tree, node, name in reads:
        if not name:
            continue
        if name not in writes:
            findings.append(
                _emit(
                    ctx,
                    rule,
                    message=f"Named attribute {name!r} is read without a graph-local write",
                    tree=tree,
                    node=node,
                    socket=name_socket,
                    evidence={"name": name},
                )
            )
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if unverifiable:
        return Evaluation(rule, "NOT_EVALUATED", [], "an attribute name is not a constant, so its source cannot be checked")
    return Evaluation(rule, "PASS", [])


@register("GM-DOMAIN-002")
def rule_builtin_domain(ctx: Context) -> Evaluation:
    rule = RULES["GM-DOMAIN-002"]
    blocked = _need_catalog(ctx, rule)
    if blocked:
        return blocked
    spec = ctx.catalog.data["attribute_store"]
    builtins = ctx.catalog.data["builtin_attribute_domains"]
    stores = [node for tree in ctx.document.trees for node in tree.nodes if node.type == spec["node_type"]]
    if not stores:
        return Evaluation(rule, "NOT_APPLICABLE", [], "the graph does not store a named attribute")
    findings = []
    missing_domain = False
    for tree in ctx.document.trees:
        for node in tree.nodes:
            if node.type != spec["node_type"]:
                continue
            name = _name_constant(ctx, tree, node, spec["name_socket"])
            if name not in builtins:
                continue
            domain = node.parameters.get(spec["domain_property"])
            if not isinstance(domain, str) or not domain:
                missing_domain = True
                continue
            expected = builtins[name]
            if domain != expected:
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message=f"Built-in attribute {name!r} is stored on {domain}, not {expected}",
                        tree=tree,
                        node=node,
                        evidence={"name": name, "domain": domain, "expected_domain": expected},
                        why=rule.why,
                    )
                )
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if missing_domain:
        return Evaluation(rule, "NOT_EVALUATED", [], "a built-in attribute is stored without a domain property")
    return Evaluation(rule, "PASS", [])


@register("GM-DOMAIN-003")
def rule_empty(ctx: Context) -> Evaluation:
    rule = RULES["GM-DOMAIN-003"]
    blocked = _need_catalog(ctx, rule)
    if blocked:
        return blocked
    specs = ctx.catalog.data["empty_generators"]
    present = False
    findings = []
    for tree in ctx.document.trees:
        for node in tree.nodes:
            for spec in specs:
                if node.type != spec["node_type"]:
                    continue
                if not _parameters_match(node, spec):
                    continue
                present = True
                if spec["kind"] == "socket_equals":
                    value = _input_constant(ctx, tree, node, spec["socket"])
                    if value is None:
                        continue
                    if exactly_equal(value, spec["equals"]):
                        findings.append(
                            _emit(
                                ctx,
                                rule,
                                message=spec["message"],
                                tree=tree,
                                node=node,
                                socket=spec["socket"],
                                evidence={"value": value, "evaluation": spec["evidence"]},
                            )
                        )
                elif spec["kind"] == "any_socket_equals":
                    for socket_name in spec["sockets"]:
                        value = _input_constant(ctx, tree, node, socket_name)
                        if value is not None and exactly_equal(value, spec["equals"]):
                            findings.append(
                                _emit(
                                    ctx,
                                    rule,
                                    message=spec["message"].format(socket=socket_name),
                                    tree=tree,
                                    node=node,
                                    socket=socket_name,
                                    evidence={"value": value, "evaluation": spec["evidence"]},
                                )
                            )
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if not present:
        return Evaluation(rule, "NOT_APPLICABLE", [], "no verified empty-capable generator is in the graph")
    return Evaluation(rule, "PASS", [])


@register("GM-DOMAIN-004")
def rule_divide(ctx: Context) -> Evaluation:
    rule = RULES["GM-DOMAIN-004"]
    blocked = _need_catalog(ctx, rule)
    if blocked:
        return blocked
    spec = ctx.catalog.data["math_divide"]
    nodes = [node for tree in ctx.document.trees for node in tree.nodes if node.type == spec["node_type"]]
    if not nodes:
        return Evaluation(rule, "NOT_APPLICABLE", [], "the graph has no Math node")
    findings = []
    unknown = False
    for tree in ctx.document.trees:
        for node in tree.nodes:
            if node.type != spec["node_type"]:
                continue
            operation = str(node.parameters.get(spec["operation_property"], ""))
            if operation != spec["operation_value"]:
                continue
            value = _input_constant(ctx, tree, node, spec["divisor_socket"])
            if value is None:
                unknown = True
                continue
            if exactly_equal(value, 0):
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Math Divide divisor is the constant 0",
                        tree=tree,
                        node=node,
                        socket=spec["divisor_socket"],
                        evidence={"operation": operation, "divisor": value},
                    )
                )
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if unknown:
        return Evaluation(rule, "NOT_EVALUATED", [], "a Divide node's divisor is not a constant")
    return Evaluation(rule, "PASS", [])


@register("GM-GEO-013")
def rule_realize(ctx: Context) -> Evaluation:
    rule = RULES["GM-GEO-013"]
    blocked = _need_catalog(ctx, rule)
    if blocked:
        return blocked
    realize = ctx.catalog.data["realize_node_type"]
    instancing = ctx.catalog.data["instance_on_points_type"]
    if not any(node.type == realize for tree in ctx.document.trees for node in tree.nodes):
        return Evaluation(rule, "NOT_APPLICABLE", [], "the graph does not realize instances")
    findings = []
    for tree in ctx.document.trees:
        by_internal = tree.by_internal()
        succ: dict[str, set[str]] = defaultdict(set)
        for link in ctx.analysis.links:
            if link.tree == tree.name and link.known and not link.muted and link.valid is not False:
                succ[link.from_id].add(link.to_id)
        realizes = [node for node in tree.nodes if node.type == realize and (tree.name, node.internal_id) in ctx.analysis.live]
        for node in realizes:
            downstream = _descendants(node.internal_id, succ)
            replicated = [
                by_internal[item].id
                for item in downstream
                if item in by_internal and by_internal[item].type in {instancing, realize}
            ]
            if replicated:
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message="Realize Instances occurs upstream of a replicated branch; potentially expensive at high counts",
                        tree=tree,
                        node=node,
                        related=tuple(replicated),
                        evidence={"downstream": replicated},
                    )
                )
    return _finish(rule, findings)


@register("GM-PERF-002")
def rule_duplicate_expensive(ctx: Context) -> Evaluation:
    rule = RULES["GM-PERF-002"]
    blocked = _need_catalog(ctx, rule)
    if blocked:
        return blocked
    expensive = {item["node_type"]: item for item in ctx.catalog.data["expensive_nodes"]}
    findings = []
    for tree in ctx.document.trees:
        grouped: dict[tuple, list[Node]] = defaultdict(list)
        for node in tree.nodes:
            if node.type not in expensive or (tree.name, node.internal_id) not in ctx.analysis.live:
                continue
            signature = (
                node.type,
                tuple(sorted((str(key), repr(value)) for key, value in node.parameters.items())),
                tuple(sorted(_literal_inputs(ctx, tree, node))),
            )
            grouped[signature].append(node)
        for signature, nodes in grouped.items():
            if len(nodes) < 2:
                continue
            info = expensive[signature[0]]
            findings.append(
                _emit(
                    ctx,
                    rule,
                    message=f"Duplicated {nodes[0].type} nodes share identical literal inputs",
                    tree=tree,
                    node=nodes[0],
                    related=tuple(node.id for node in nodes[1:]),
                    evidence={"count": len(nodes), "reason": info["reason"], "reference": info["reference"]},
                    why=info["reason"],
                )
            )
    if not any(node.type in expensive for tree in ctx.document.trees for node in tree.nodes):
        return Evaluation(rule, "NOT_APPLICABLE", [], "no catalogued expensive node is present")
    return _finish(rule, findings)


@register("GM-PERF-003")
def rule_budget(ctx: Context) -> Evaluation:
    rule = RULES["GM-PERF-003"]
    if ctx.max_points is None:
        return Evaluation(rule, "NOT_APPLICABLE", [], "budgets.max_points is not set")
    blocked = _need_catalog(ctx, rule)
    if blocked:
        return blocked
    findings = []
    unknown = False
    saw = False
    for tree in ctx.document.trees:
        for node in tree.nodes:
            if (tree.name, node.internal_id) not in ctx.analysis.live:
                continue
            for spec in ctx.catalog.data["count_bounds"]:
                if node.type != spec["node_type"] or not _parameters_match(node, spec):
                    continue
                saw = True
                bound, certain = _bound(ctx, tree, node, spec)
                if bound is None:
                    unknown = True
                    continue
                if bound > ctx.max_points:
                    why = (
                        f"{spec['label']} is a serialized constant, so the count is known before a cook."
                        if certain
                        else "The interface maximum is wired directly into the count socket, so the declared upper bound is known."
                    )
                    findings.append(
                        _emit(
                            ctx,
                            rule,
                            message=f"{spec['label']} bound {bound:g} exceeds the point budget {ctx.max_points}",
                            tree=tree,
                            node=node,
                            evidence={"bound": bound, "budget": ctx.max_points, "exact": certain},
                            why=why,
                        )
                    )
    if findings:
        return Evaluation(rule, "FAIL", findings)
    if unknown or not saw:
        return Evaluation(rule, "NOT_EVALUATED", [], "no point or vertex count can be bounded from constants")
    return Evaluation(rule, "PASS", [])


@register("GM-PERF-004")
def rule_depth(ctx: Context) -> Evaluation:
    rule = RULES["GM-PERF-004"]
    if ctx.analysis.group_depth is None:
        return Evaluation(rule, "NOT_EVALUATED", [], "group references cycle, so nesting depth is not a finite number")
    depth = ctx.analysis.group_depth
    if depth > ctx.max_group_depth:
        root = ctx.document.root_tree
        return Evaluation(
            rule,
            "FAIL",
            [
                _emit(
                    ctx,
                    rule,
                    message=f"Group nesting depth {depth} exceeds the limit {ctx.max_group_depth}",
                    tree=root,
                    evidence={"depth": depth, "limit": ctx.max_group_depth},
                )
            ],
        )
    return Evaluation(rule, "PASS", [], f"depth {depth} is within {ctx.max_group_depth}")


@register("GM-PERF-005")
def rule_unused_params(ctx: Context) -> Evaluation:
    rule = RULES["GM-PERF-005"]
    if not any(tree.interface for tree in ctx.document.trees):
        return Evaluation(rule, "NOT_APPLICABLE", [], "no tree exposes an interface")
    findings = []
    for tree in ctx.document.trees:
        inputs = [item for item in tree.interface if item.in_out == "INPUT"]
        if not inputs:
            continue
        used = set()
        for link in tree.links:
            source = tree.by_id().get(link.from_node, [])
            if source and source[0].type == "NodeGroupInput":
                used.add(link.from_socket)
        for item in inputs:
            if item.identifier not in used:
                findings.append(
                    _emit(
                        ctx,
                        rule,
                        message=f"Exposed parameter {item.name!r} is not linked from Group Input",
                        tree=tree,
                        socket=item.identifier,
                        evidence={"name": item.name},
                    )
                )
    return _finish(rule, findings)


def _linked_sockets(ctx: Context, tree_name: str) -> set[tuple[str, str]]:
    return {
        (link.to_id, link.to_socket)
        for link in ctx.analysis.links
        if link.tree == tree_name and link.known and not link.muted and link.valid is not False
    }


def _node(tree: Tree, internal_id: str) -> Node | None:
    return tree.by_internal().get(internal_id)


def _is_output(node: Node, ctx: Context) -> bool:
    return node.type in ctx.catalog.output_types() or node.type in ctx.catalog.viewer_types()


def _reachable_groups(ctx: Context) -> set[str]:
    return set(ctx.analysis.paths)


def _socket_present(node: Node, identifier: str) -> bool:
    return node.socket(identifier, output=False) is not None or node.socket(identifier, output=True) is not None


def _name_constant(ctx: Context, tree: Tree, node: Node, socket_name: str) -> str | None:
    value = _input_constant(ctx, tree, node, socket_name)
    if isinstance(value, str) and value:
        return value
    return None


def _input_constant(ctx: Context, tree: Tree, node: Node, socket_name: str) -> Any:
    socket = node.socket(socket_name, output=False)
    if socket is None:
        return None
    return ctx.analysis.constants.get((tree.name, node.internal_id, socket.identifier))


def _parameters_match(node: Node, spec: dict) -> bool:
    expected = spec.get("when_parameter")
    if not expected:
        return True
    defaults = spec.get("default_parameters") or {}
    for key, value in expected.items():
        actual = node.parameters.get(key, defaults.get(key))
        if actual != value:
            return False
    return True


def _descendants(start: str, succ: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(succ.get(start, ()))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(succ.get(current, ()))
    return seen


def _literal_inputs(ctx: Context, tree: Tree, node: Node) -> list[tuple[str, str]]:
    items = []
    linked = {link.to_socket: link for link in ctx.analysis.links if link.tree == tree.name and link.to_id == node.internal_id and link.known}
    for socket in node.inputs:
        if not socket.enabled:
            continue
        feed = linked.get(socket.identifier)
        if feed is None:
            items.append((socket.identifier, repr(socket.default)))
        else:
            constant = ctx.analysis.constants.get((tree.name, feed.from_id, feed.from_socket))
            if constant is None:
                items.append((socket.identifier, f"link:{feed.from_node}:{feed.from_socket}"))
            else:
                items.append((socket.identifier, repr(constant)))
    return items


def _bound(ctx: Context, tree: Tree, node: Node, spec: dict) -> tuple[float | None, bool]:
    if spec["kind"] == "socket":
        value = _input_constant(ctx, tree, node, spec["socket"])
        if is_number(value) and non_finite_token(value) is None:
            return float(value), True
        upper = _interface_max(ctx, tree, node, spec["socket"])
        if upper is not None:
            return upper, False
        return None, False
    if spec["kind"] == "product":
        numbers = []
        for socket_name in spec["sockets"]:
            value = _input_constant(ctx, tree, node, socket_name)
            if not is_number(value) or non_finite_token(value):
                return None, False
            numbers.append(float(value))
        product = 1.0
        for number in numbers:
            product *= number
        return product, True
    return None, False


def _interface_max(ctx: Context, tree: Tree, node: Node, socket_name: str) -> float | None:
    feeds = [
        link
        for link in ctx.analysis.links
        if link.tree == tree.name and link.to_id == node.internal_id and link.to_socket == socket_name and link.known
    ]
    if len(feeds) != 1:
        return None
    source = _node(tree, feeds[0].from_id)
    if source is None or source.type != "NodeGroupInput":
        return None
    for item in tree.interface:
        if item.identifier == feeds[0].from_socket and item.max_value is not None and non_finite_token(item.max_value) is None:
            return float(item.max_value)
    return None
