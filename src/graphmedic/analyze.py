"""Reachability, cycles, group depth, and constant propagation.

Cycles are classified per tree from socket links. Group-tree references are
a separate graph so a self-referential group cannot recurse without a bound.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from graphmedic.catalog import Catalog
from graphmedic.model import Document, Node, Tree
from graphmedic.values import exactly_zero, is_number


@dataclass
class ResolvedLink:
    tree: str
    index: int
    from_id: str
    from_socket: str
    to_id: str
    to_socket: str
    valid: bool | None
    muted: bool
    from_node: str
    to_node: str
    known: bool


@dataclass
class Analysis:
    paths: dict[str, tuple[str, ...]]
    live: set[tuple[str, str]]
    sinks: set[tuple[str, str]]
    sccs: list[list[tuple[str, str]]]
    group_cycles: list[list[str]]
    constants: dict[tuple[str, str, str], Any]
    links: list[ResolvedLink]
    group_depth: int | None
    catalog_applies: bool
    catalog_reason: str


def analyze(document: Document, catalog: Catalog) -> Analysis:
    applies = catalog.applies_to(document.version_tuple) and document.host == "blender"
    reason = ""
    if document.host != "blender":
        reason = "catalog checks are verified for Blender geometry nodes only"
    elif not applies:
        found = ".".join(str(part) for part in document.version_tuple) if document.version_tuple else "unknown"
        reason = (
            f"socket and domain checks were verified on Blender {catalog.version}; "
            f"this graph reports {found}"
        )
    paths, group_cycles, depth = _group_paths(document)
    links = _resolve_links(document)
    live, sinks = _liveness(document, links, catalog)
    sccs = _cycles(document, links)
    constants = _constants(document, links, catalog if applies else None)
    return Analysis(
        paths=paths,
        live=live,
        sinks=sinks,
        sccs=sccs,
        group_cycles=group_cycles,
        constants=constants,
        links=links,
        group_depth=depth,
        catalog_applies=applies,
        catalog_reason=reason,
    )


def _group_paths(document: Document) -> tuple[dict[str, tuple[str, ...]], list[list[str]], int | None]:
    children: dict[str, list[str]] = defaultdict(list)
    for tree in document.trees:
        for node in tree.nodes:
            if node.group_tree:
                children[tree.name].append(node.group_tree)
    paths: dict[str, tuple[str, ...]] = {}
    cycles: list[list[str]] = []
    stack: list[str] = []
    visiting: set[str] = set()

    def walk(name: str, path: tuple[str, ...]) -> None:
        if name in visiting:
            loop = stack[stack.index(name):] + [name]
            cycles.append(loop)
            return
        if name in paths:
            return
        visiting.add(name)
        stack.append(name)
        paths[name] = path
        for child in children.get(name, []):
            if child == name or child in stack:
                loop = stack[stack.index(child):] + [child] if child in stack else [name, child]
                cycles.append(loop)
                continue
            if any(tree.name == child for tree in document.trees):
                walk(child, path + (child,))
        stack.pop()
        visiting.remove(name)

    walk(document.root, (document.root,))
    for tree in document.trees:
        paths.setdefault(tree.name, (tree.name,))
    depth: int | None = 0
    if cycles:
        depth = None
    else:
        seen: set[str] = set()

        def height(name: str) -> int:
            if name in seen:
                return 0
            seen.add(name)
            kids = [child for child in children.get(name, []) if any(tree.name == child for tree in document.trees)]
            if not kids:
                return 0
            return 1 + max(height(child) for child in kids)

        depth = height(document.root)
    unique_cycles: list[list[str]] = []
    for cycle in cycles:
        if cycle not in unique_cycles:
            unique_cycles.append(cycle)
    return paths, unique_cycles, depth


def _resolve_links(document: Document) -> list[ResolvedLink]:
    resolved: list[ResolvedLink] = []
    for tree in document.trees:
        grouped = tree.by_id()
        for link in tree.links:
            sources = grouped.get(link.from_node, [])
            targets = grouped.get(link.to_node, [])
            source = sources[0] if sources else None
            target = targets[0] if targets else None
            known = bool(
                source
                and target
                and source.socket(link.from_socket, output=True)
                and target.socket(link.to_socket, output=False)
            )
            resolved.append(
                ResolvedLink(
                    tree=tree.name,
                    index=link.index,
                    from_id=source.internal_id if source else "",
                    from_socket=link.from_socket,
                    to_id=target.internal_id if target else "",
                    to_socket=link.to_socket,
                    valid=link.valid,
                    muted=link.muted,
                    from_node=link.from_node,
                    to_node=link.to_node,
                    known=known,
                )
            )
    return resolved


def _liveness(document: Document, links: list[ResolvedLink], catalog: Catalog) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    sinks: set[tuple[str, str]] = set()
    edges: dict[str, list[tuple[str, str]]] = defaultdict(list)
    reverse: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for tree in document.trees:
        for node in tree.nodes:
            if _is_sink(node, catalog):
                sinks.add((tree.name, node.internal_id))
        by_internal = tree.by_internal()
        incoming: dict[str, list[ResolvedLink]] = defaultdict(list)
        outgoing: dict[str, list[ResolvedLink]] = defaultdict(list)
        for link in links:
            if link.tree != tree.name or not link.known or link.muted or link.valid is False:
                continue
            incoming[link.to_id].append(link)
            outgoing[link.from_id].append(link)
            source = by_internal.get(link.from_id)
            target = by_internal.get(link.to_id)
            if source and target and not source.muted and not target.muted:
                edges[tree.name].append((link.from_id, link.to_id))
        for node in tree.nodes:
            if not node.muted:
                continue
            for in_socket, out_socket in node.internal_links:
                sources = [link.from_id for link in incoming[node.internal_id] if link.to_socket == in_socket]
                targets = [link.to_id for link in outgoing[node.internal_id] if link.from_socket == out_socket]
                for source_id in sources:
                    edges[tree.name].append((source_id, node.internal_id))
                for target_id in targets:
                    edges[tree.name].append((node.internal_id, target_id))
    for tree_name, pairs in edges.items():
        for source, target in pairs:
            reverse[tree_name].append((target, source))
    live: set[tuple[str, str]] = set()
    for tree in document.trees:
        start = [node_id for tree_name, node_id in sinks if tree_name == tree.name]
        queue = deque(start)
        seen = set(start)
        while queue:
            current = queue.popleft()
            live.add((tree.name, current))
            for _target, source in reverse[tree.name]:
                if _target == current and source not in seen:
                    seen.add(source)
                    queue.append(source)
    return live, sinks


def _is_sink(node: Node, catalog: Catalog) -> bool:
    if node.type in catalog.viewer_types():
        return True
    if node.type not in catalog.output_types():
        return False
    active = node.parameters.get("is_active_output", True)
    return active is not False


def _cycles(document: Document, links: list[ResolvedLink]) -> list[list[tuple[str, str]]]:
    found: list[list[tuple[str, str]]] = []
    for tree in document.trees:
        node_ids = [node.internal_id for node in tree.nodes]
        edges = []
        self_loops = set()
        for link in links:
            if link.tree != tree.name or not link.known or link.muted or link.valid is False:
                continue
            edges.append((link.from_id, link.to_id))
            if link.from_id == link.to_id:
                self_loops.add(link.from_id)
        for component in _strongly_connected(node_ids, edges):
            members = set(component)
            has_edge = any(source in members and target in members and source != target for source, target in edges)
            has_self = any(node_id in self_loops for node_id in members)
            if len(component) > 1 or has_self or (len(component) == 1 and has_edge):
                if len(component) > 1 or has_self:
                    found.append([(tree.name, node_id) for node_id in component])
    return found


def _strongly_connected(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Iterative Tarjan. Recursion is bounded by an explicit stack, not CPython's call stack."""
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        adjacency[source].append(target)
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    frames: list[tuple[str, int]] = []

    def push(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        frames.append((node, 0))

    for start in nodes:
        if start in indices:
            continue
        push(start)
        while frames:
            node, cursor = frames[-1]
            neighbours = adjacency.get(node, [])
            if cursor < len(neighbours):
                frames[-1] = (node, cursor + 1)
                nxt = neighbours[cursor]
                if nxt not in indices:
                    push(nxt)
                elif nxt in on_stack:
                    low[node] = min(low[node], indices[nxt])
                continue
            frames.pop()
            if frames:
                parent = frames[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == indices[node]:
                component: list[str] = []
                while True:
                    item = stack.pop()
                    on_stack.remove(item)
                    component.append(item)
                    if item == node:
                        break
                components.append(component)
    return components


def _constants(document: Document, links: list[ResolvedLink], catalog: Catalog | None) -> dict[tuple[str, str, str], Any]:
    constants: dict[tuple[str, str, str], Any] = {}
    by_target: dict[tuple[str, str, str], list[ResolvedLink]] = defaultdict(list)
    for link in links:
        if link.known and not link.muted and link.valid is not False:
            by_target[(link.tree, link.to_id, link.to_socket)].append(link)
    for tree in document.trees:
        produced = _produced_order(tree, links)
        interface_values = _interface_constants(tree)
        for node in produced:
            incoming: dict[str, Any] = {}
            known_inputs = True
            for socket in node.inputs:
                if not socket.enabled:
                    continue
                key = (tree.name, node.internal_id, socket.identifier)
                feeds = by_target.get(key, [])
                if not feeds:
                    if socket.default is not None:
                        incoming[socket.identifier] = socket.default
                        constants[key] = socket.default
                    else:
                        known_inputs = False
                    continue
                values = []
                for feed in feeds:
                    source_key = (tree.name, feed.from_id, feed.from_socket)
                    if source_key not in constants:
                        values = []
                        break
                    values.append(constants[source_key])
                if len(values) == 1 or (values and all(item == values[0] for item in values)):
                    incoming[socket.identifier] = values[0]
                    constants[key] = values[0]
                else:
                    known_inputs = False
            _seed_output_constants(tree, node, constants, interface_values, incoming, known_inputs, catalog)
    return constants


def _produced_order(tree: Tree, links: list[ResolvedLink]) -> list[Node]:
    nodes = {node.internal_id: node for node in tree.nodes}
    indegree = {node.internal_id: 0 for node in tree.nodes}
    succ: dict[str, list[str]] = defaultdict(list)
    for link in links:
        if link.tree != tree.name or not link.known or link.muted or link.valid is False:
            continue
        if link.from_id == link.to_id:
            continue
        succ[link.from_id].append(link.to_id)
        indegree[link.to_id] = indegree.get(link.to_id, 0) + 1
    ready = deque([node_id for node_id, degree in indegree.items() if degree == 0])
    ordered: list[Node] = []
    seen = set()
    while ready:
        current = ready.popleft()
        if current in seen or current not in nodes:
            continue
        seen.add(current)
        ordered.append(nodes[current])
        for nxt in succ[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    return ordered


def _interface_constants(tree: Tree) -> dict[str, Any]:
    values = {}
    for item in tree.interface:
        if item.in_out == "INPUT" and item.current is not None:
            values[item.identifier] = item.current
    return values


def _seed_output_constants(
    tree: Tree,
    node: Node,
    constants: dict[tuple[str, str, str], Any],
    interface_values: dict[str, Any],
    incoming: dict[str, Any],
    known_inputs: bool,
    catalog: Catalog | None,
) -> None:
    if node.type == "NodeGroupInput":
        for socket in node.outputs:
            if socket.identifier in interface_values:
                constants[(tree.name, node.internal_id, socket.identifier)] = interface_values[socket.identifier]
            elif socket.default is not None:
                constants[(tree.name, node.internal_id, socket.identifier)] = socket.default
        return
    if catalog is not None:
        spec = catalog.data["value_nodes"].get(node.type)
        if spec:
            output = spec["output"]
            if spec["source"] == "output_default":
                socket = node.socket(output, output=True)
                if socket and socket.default is not None:
                    constants[(tree.name, node.internal_id, output)] = socket.default
            elif spec["source"] == "parameter":
                if spec["parameter"] in node.parameters:
                    constants[(tree.name, node.internal_id, output)] = node.parameters[spec["parameter"]]
            return
        math_spec = catalog.data["math_divide"]
        if node.type == math_spec["node_type"] and known_inputs:
            operation = str(node.parameters.get(math_spec["operation_property"], "ADD"))
            left = incoming.get("Value")
            right = incoming.get("Value_001")
            if is_number(left) and is_number(right):
                result = _math(operation, float(left), float(right))
                if result is not None:
                    constants[(tree.name, node.internal_id, "Value")] = result


def _math(operation: str, left: float, right: float) -> float | None:
    if operation == "ADD":
        return left + right
    if operation == "SUBTRACT":
        return left - right
    if operation == "MULTIPLY":
        return left * right
    if operation == "DIVIDE":
        if exactly_zero(right):
            return None
        return left / right
    return None


