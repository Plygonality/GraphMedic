"""Read untrusted graph JSON into the analysis view.

Supported:
- blender.geometry_nodes.capture version 1, a direct bpy dump
- nodebridge.graph version 1, read-only, without NodeBridge's compiler

gn-as-code, hda-as-code, pcg-as-code, and shader-as-code are recognised and
refused. Their schemas were not available to verify, so they do not lint as
a clean graph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graphmedic.errors import InputError, UnsupportedFormatError
from graphmedic.limits import Limits
from graphmedic.model import Document, InterfaceSocket, Link, Node, Socket, Tree
from graphmedic.values import as_optional_number

CAPTURE = "blender.geometry_nodes.capture"
NODEBRIDGE = "nodebridge.graph"

UNSUPPORTED_FORMATS = {
    "gn-as-code": (
        "The gn-as-code repository could not be resolved, so its JSON schema was not "
        "verified. GraphMedic will not guess a mapping."
    ),
    "gn_as_code": (
        "The gn-as-code repository could not be resolved, so its JSON schema was not "
        "verified. GraphMedic will not guess a mapping."
    ),
    "hda-as-code": (
        "The HDA-as-code repository could not be resolved. Houdini graphs are unsupported "
        "until a real hou export can be checked."
    ),
    "pcg-as-code": (
        "The Pcg-as-code repository could not be resolved. Unreal PCG graphs are unsupported "
        "until a pinned editor schema is available."
    ),
    "shader-as-code": "Shader-as-code is a future domain and is not part of GraphMedic v0.1.",
    "nodebridge.semantic": (
        "nodebridge.semantic is a compiler IR. GraphMedic reads nodebridge.graph structure "
        "and does not run NodeBridge translation."
    ),
}

_NODEBRIDGE_TYPES = {
    "bool": "BOOLEAN",
    "int": "INT",
    "float": "VALUE",
    "vector2": "VECTOR",
    "vector3": "VECTOR",
    "vector4": "VECTOR",
    "color": "RGBA",
    "rotation": "ROTATION",
    "matrix": "MATRIX",
    "string": "STRING",
    "menu": "MENU",
    "geometry": "GEOMETRY",
    "mesh": "GEOMETRY",
    "curve": "GEOMETRY",
    "points": "GEOMETRY",
    "instances": "GEOMETRY",
    "material": "MATERIAL",
    "object": "OBJECT",
    "collection": "COLLECTION",
    "image": "IMAGE",
    "texture": "TEXTURE",
    "shader": "SHADER",
    "any": "UNKNOWN",
}

_BLENDER_CLASSES = {
    "VALUE",
    "INT",
    "BOOLEAN",
    "VECTOR",
    "RGBA",
    "ROTATION",
    "MATRIX",
    "STRING",
    "MENU",
    "GEOMETRY",
    "OBJECT",
    "COLLECTION",
    "MATERIAL",
    "IMAGE",
    "TEXTURE",
    "SHADER",
    "CUSTOM",
}

_INTERFACE_PREFIXES = (
    ("NodeSocketFloat", "VALUE"),
    ("NodeSocketInt", "INT"),
    ("NodeSocketBool", "BOOLEAN"),
    ("NodeSocketVector", "VECTOR"),
    ("NodeSocketColor", "RGBA"),
    ("NodeSocketRotation", "ROTATION"),
    ("NodeSocketMatrix", "MATRIX"),
    ("NodeSocketString", "STRING"),
    ("NodeSocketMenu", "MENU"),
    ("NodeSocketGeometry", "GEOMETRY"),
    ("NodeSocketObject", "OBJECT"),
    ("NodeSocketCollection", "COLLECTION"),
    ("NodeSocketMaterial", "MATERIAL"),
    ("NodeSocketImage", "IMAGE"),
    ("NodeSocketTexture", "TEXTURE"),
    ("NodeSocketShader", "SHADER"),
)

ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".bz2", ".xz"}


def type_class(raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        return "UNKNOWN"
    mapped = _NODEBRIDGE_TYPES.get(raw)
    if mapped:
        return mapped
    upper = raw.upper()
    if upper in _BLENDER_CLASSES:
        return upper
    for prefix, kind in _INTERFACE_PREFIXES:
        if raw == prefix or raw.startswith(prefix):
            return kind
    return "UNKNOWN"


def parse_version(text: str | None) -> tuple[int, ...] | None:
    if not text:
        return None
    numbers: list[int] = []
    current = ""
    for char in text:
        if char.isdigit():
            current += char
        elif current:
            numbers.append(int(current))
            current = ""
            if len(numbers) == 3:
                break
    if current and len(numbers) < 3:
        numbers.append(int(current))
    if len(numbers) >= 2:
        return tuple(numbers[:3])
    return None


def _depth(text: str, limit: int) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
            if depth > limit:
                raise InputError(
                    f"JSON nesting exceeds the limit of {limit}",
                    code="GM-INPUT-002",
                )
        elif char in "}]":
            depth = max(0, depth - 1)


def read_json(path: Path, limits: Limits) -> tuple[Any, str]:
    if path.suffix.lower() in ARCHIVE_SUFFIXES or path.name.lower().endswith(".tar.gz"):
        raise InputError(
            f"Refusing to expand archive {path.name}",
            code="GM-INPUT-008",
        )
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise InputError(f"Cannot read {path}: {exc}", code="GM-INPUT-006") from exc
    if size > limits.max_bytes:
        raise InputError(
            f"{path.name} is {size} bytes, above the limit of {limits.max_bytes}",
            code="GM-INPUT-002",
        )
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise InputError(f"{path.name} is not UTF-8 text: {exc}", code="GM-INPUT-001") from exc
    _depth(text, limits.max_depth)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"Malformed JSON in {path.name}: {exc.msg} at line {exc.lineno}", code="GM-INPUT-001") from exc
    return data, text


def load_path(path: Path, limits: Limits) -> Document:
    data, text = read_json(path, limits)
    document = load_data(data, source=str(path), text=text, limits=limits)
    _assign_lines(text, document)
    return document


def load_data(data: Any, *, source: str, text: str = "", limits: Limits | None = None) -> Document:
    limits = limits or Limits()
    if not isinstance(data, dict):
        raise InputError("A graph file must be a JSON object", code="GM-INPUT-001")
    fmt = data.get("format")
    if isinstance(fmt, str) and fmt in UNSUPPORTED_FORMATS:
        raise UnsupportedFormatError(UNSUPPORTED_FORMATS[fmt], code="GM-INPUT-003")
    if fmt == NODEBRIDGE:
        document = _load_nodebridge(data, source)
    elif fmt == CAPTURE or _looks_like_capture(data):
        if fmt not in (None, CAPTURE):
            raise UnsupportedFormatError(
                f"Unrecognised graph format {fmt!r}. Supported formats are {CAPTURE!r} and {NODEBRIDGE!r}.",
                code="GM-INPUT-003",
            )
        document = _load_capture(data, source)
    elif isinstance(fmt, str):
        raise UnsupportedFormatError(
            f"Unrecognised graph format {fmt!r}. No adapter is registered for it.",
            code="GM-INPUT-003",
        )
    else:
        raise UnsupportedFormatError(
            "The file has no verified graph format. GraphMedic does not treat unknown JSON as a healthy graph.",
            code="GM-INPUT-003",
        )
    _enforce_size(document, limits)
    if text:
        _assign_lines(text, document)
    return document


def _looks_like_capture(data: dict) -> bool:
    if data.get("format") not in (None, CAPTURE):
        return False
    trees = data.get("trees")
    if isinstance(trees, list) and trees and isinstance(trees[0], dict):
        sample = trees[0]
        return "nodes" in sample and ("bl_idname" in sample or sample.get("kind") == "geometry")
    return isinstance(data.get("nodes"), list) and isinstance(data.get("links"), list) and (
        data.get("bl_idname") == "GeometryNodeTree" or data.get("kind") == "geometry"
    )


def _enforce_size(document: Document, limits: Limits) -> None:
    nodes = sum(len(tree.nodes) for tree in document.trees)
    links = sum(len(tree.links) for tree in document.trees)
    if nodes > limits.max_nodes or links > limits.max_links:
        raise InputError(
            f"Graph has {nodes} nodes and {links} links, above the configured limit",
            code="GM-INPUT-002",
        )


def _load_capture(data: dict, source: str) -> Document:
    version = data.get("format_version", 1)
    if version != 1:
        raise UnsupportedFormatError(
            f"blender.geometry_nodes.capture version {version} is not supported",
            code="GM-INPUT-003",
        )
    application = data.get("application") or {}
    if not isinstance(application, dict):
        raise InputError("application must be an object", code="GM-INPUT-001")
    version_text = str(application.get("version") or "")
    trees = _tree_payloads(data)
    parsed = [_tree_from_capture(item) for item in trees]
    root = str(data.get("root") or (parsed[0].name if parsed else ""))
    if not any(tree.name == root for tree in parsed):
        raise InputError(f"Root tree {root!r} is not in the file", code="GM-INPUT-001")
    _reject_duplicate_tree_names(parsed)
    return Document(
        format=CAPTURE,
        format_version=1,
        adapter="blender.geometry_nodes.capture",
        host="blender",
        version=version_text,
        version_tuple=parse_version(version_text),
        root=root,
        trees=parsed,
        closed_attribute_pipeline=_optional_bool(data.get("closed_attribute_pipeline")),
        flatten_interfaces=bool(data.get("flatten_interfaces", False)),
        source_path=source,
        metadata=_metadata(data),
        valid_omitted_means=None,
    )


def _load_nodebridge(data: dict, source: str) -> Document:
    version = data.get("format_version", 1)
    if version != 1:
        raise UnsupportedFormatError(f"nodebridge.graph version {version} is not supported", code="GM-INPUT-003")
    source_info = data.get("source") or {}
    if not isinstance(source_info, dict):
        raise InputError("nodebridge source must be an object", code="GM-INPUT-001")
    application = str(source_info.get("application") or "")
    if "Blender" not in application and application:
        raise UnsupportedFormatError(
            f"nodebridge.graph application {application!r} is not a verified Blender export",
            code="GM-INPUT-003",
        )
    trees = data.get("trees")
    if not isinstance(trees, list) or not trees:
        raise InputError("nodebridge.graph requires a trees array", code="GM-INPUT-001")
    parsed = [_tree_from_nodebridge(item) for item in trees]
    root = str(data.get("root") or parsed[0].name)
    if not any(tree.name == root for tree in parsed):
        raise InputError(f"Root tree {root!r} is not in the file", code="GM-INPUT-001")
    _reject_duplicate_tree_names(parsed)
    kind = parsed[0].kind if parsed else ""
    return Document(
        format=NODEBRIDGE,
        format_version=1,
        adapter="nodebridge.graph",
        host="blender" if kind == "geometry" or "Blender" in application else "unknown",
        version=application,
        version_tuple=parse_version(application),
        root=root,
        trees=parsed,
        closed_attribute_pipeline=_optional_bool(data.get("closed_attribute_pipeline")),
        flatten_interfaces=bool(data.get("flatten_interfaces", False)),
        source_path=source,
        metadata={"nodebridge_source": source_info},
        valid_omitted_means=True,
    )


def _tree_payloads(data: dict) -> list[dict]:
    trees = data.get("trees")
    if trees is None:
        return [data]
    if not isinstance(trees, list) or not trees:
        raise InputError("trees must be a non-empty array", code="GM-INPUT-001")
    for item in trees:
        if not isinstance(item, dict):
            raise InputError("each tree must be an object", code="GM-INPUT-001")
    return trees


def _reject_duplicate_tree_names(trees: list[Tree]) -> None:
    seen: set[str] = set()
    for tree in trees:
        if tree.name in seen:
            raise InputError(f"Duplicate tree name {tree.name!r}", code="GM-INPUT-009")
        seen.add(tree.name)


def _tree_from_capture(data: dict) -> Tree:
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise InputError("A tree is missing its name", code="GM-INPUT-001")
    bl_idname = str(data.get("bl_idname") or "GeometryNodeTree")
    kind = str(data.get("kind") or ("geometry" if bl_idname == "GeometryNodeTree" else "unknown"))
    return Tree(
        name=name,
        bl_idname=bl_idname,
        kind=kind,
        is_group=bool(data.get("is_group", False)),
        nodes=_nodes(data.get("nodes"), valid_default=None),
        links=_links(data.get("links"), omitted_valid=None),
        interface=_interface(data.get("interface")),
        interface_values=_interface_values(data.get("interface_values")),
    )


def _tree_from_nodebridge(data: dict) -> Tree:
    if not isinstance(data, dict):
        raise InputError("each tree must be an object", code="GM-INPUT-001")
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise InputError("A tree is missing its name", code="GM-INPUT-001")
    kind = str(data.get("kind") or "geometry")
    bl_idname = {
        "geometry": "GeometryNodeTree",
        "shader": "ShaderNodeTree",
        "compositor": "CompositorNodeTree",
    }.get(kind, "UnknownNodeTree")
    return Tree(
        name=name,
        bl_idname=bl_idname,
        kind=kind,
        is_group=bool(data.get("is_group", False)),
        nodes=_nodes(data.get("nodes"), valid_default=None),
        links=_links(data.get("links", data.get("edges")), omitted_valid=True),
        interface=_interface(data.get("interface")),
        interface_values=_interface_values(data.get("interface_values")),
    )


def _nodes(payload: Any, *, valid_default: bool | None) -> list[Node]:
    del valid_default
    if payload is None:
        payload = []
    if not isinstance(payload, list):
        raise InputError("nodes must be an array", code="GM-INPUT-001")
    nodes: list[Node] = []
    seen: dict[str, int] = {}
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise InputError(f"node {index} must be an object", code="GM-INPUT-001")
        node_id = raw.get("id", "")
        if node_id is None:
            node_id = ""
        if not isinstance(node_id, str):
            raise InputError(f"node {index} id must be a string", code="GM-INPUT-001")
        count = seen.get(node_id, 0)
        seen[node_id] = count + 1
        internal = node_id if node_id and count == 0 else f"{node_id}#{index}"
        node_type = raw.get("type", "")
        if not isinstance(node_type, str):
            raise InputError(f"node {node_id or index} type must be a string", code="GM-INPUT-001")
        parameters = raw.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise InputError(f"node {node_id or index} parameters must be an object", code="GM-INPUT-001")
        group_tree = raw.get("group_tree")
        if group_tree is not None and not isinstance(group_tree, str):
            raise InputError(f"node {node_id or index} group_tree must be a string", code="GM-INPUT-001")
        location = raw.get("location")
        point = None
        if isinstance(location, list) and len(location) >= 2:
            try:
                point = (float(location[0]), float(location[1]))
            except (TypeError, ValueError):
                point = None
        internal_links = []
        for pair in raw.get("internal_links") or []:
            if isinstance(pair, list) and len(pair) == 2 and all(isinstance(item, str) for item in pair):
                internal_links.append((pair[0], pair[1]))
        nodes.append(
            Node(
                id=node_id,
                internal_id=internal,
                type=node_type,
                inputs=_sockets(raw.get("inputs"), output=False, owner=node_id or str(index)),
                outputs=_sockets(raw.get("outputs"), output=True, owner=node_id or str(index)),
                parameters=dict(parameters),
                label=str(raw.get("label") or ""),
                muted=bool(raw.get("muted", False)),
                group_tree=group_tree,
                internal_links=internal_links,
                location=point,
            )
        )
    return nodes


def _sockets(payload: Any, *, output: bool, owner: str) -> list[Socket]:
    if payload is None:
        payload = []
    if not isinstance(payload, list):
        raise InputError(f"sockets on {owner} must be an array", code="GM-INPUT-001")
    sockets: list[Socket] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise InputError(f"socket {index} on {owner} must be an object", code="GM-INPUT-001")
        identifier = raw.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise InputError(f"socket {index} on {owner} is missing an identifier", code="GM-INPUT-001")
        enabled = bool(raw.get("enabled", True)) and not bool(raw.get("is_unavailable", False))
        optional = raw.get("optional")
        sockets.append(
            Socket(
                identifier=identifier,
                name=str(raw.get("name") or identifier),
                type_name=str(raw.get("type") or ""),
                type_class=type_class(raw.get("type")),
                is_output=output,
                default=raw.get("default", raw.get("default_value")),
                enabled=enabled,
                optional=optional if isinstance(optional, bool) else None,
                min_value=as_optional_number(raw.get("min_value")),
                max_value=as_optional_number(raw.get("max_value")),
                step=as_optional_number(raw.get("step")),
            )
        )
    return sockets


def _links(payload: Any, *, omitted_valid: bool | None) -> list[Link]:
    if payload is None:
        payload = []
    if not isinstance(payload, list):
        raise InputError("links must be an array", code="GM-INPUT-001")
    links: list[Link] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise InputError(f"link {index} must be an object", code="GM-INPUT-001")
        if "from" in raw or "to" in raw:
            pair_from = raw.get("from")
            pair_to = raw.get("to")
            if (
                not isinstance(pair_from, list)
                or not isinstance(pair_to, list)
                or len(pair_from) != 2
                or len(pair_to) != 2
            ):
                raise InputError(f"link {index} from/to must be [node, socket] pairs", code="GM-INPUT-001")
            from_node, from_socket = pair_from
            to_node, to_socket = pair_to
        else:
            from_node = raw.get("from_node")
            from_socket = raw.get("from_socket")
            to_node = raw.get("to_node")
            to_socket = raw.get("to_socket")
        if not all(isinstance(item, str) for item in (from_node, from_socket, to_node, to_socket)):
            raise InputError(f"link {index} is missing a node or socket id", code="GM-INPUT-001")
        if "valid" in raw:
            if not isinstance(raw["valid"], bool):
                raise InputError(f"link {index} valid must be a boolean", code="GM-INPUT-001")
            valid: bool | None = raw["valid"]
        else:
            valid = omitted_valid
        links.append(
            Link(
                from_node=from_node,
                from_socket=from_socket,
                to_node=to_node,
                to_socket=to_socket,
                valid=valid,
                muted=bool(raw.get("muted", False)),
                index=index,
            )
        )
    return links


def _interface(payload: Any) -> list[InterfaceSocket]:
    if payload is None:
        payload = []
    if not isinstance(payload, list):
        raise InputError("interface must be an array", code="GM-INPUT-001")
    items: list[InterfaceSocket] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise InputError(f"interface item {index} must be an object", code="GM-INPUT-001")
        if raw.get("item_type") not in (None, "SOCKET"):
            continue
        identifier = raw.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise InputError(f"interface item {index} is missing an identifier", code="GM-INPUT-001")
        direction = str(raw.get("in_out") or "").upper()
        if direction not in {"INPUT", "OUTPUT"}:
            raise InputError(f"interface item {identifier} has in_out {direction!r}", code="GM-INPUT-001")
        type_name = str(raw.get("type") or raw.get("socket_type") or "")
        items.append(
            InterfaceSocket(
                identifier=identifier,
                name=str(raw.get("name") or identifier),
                in_out=direction,
                type_name=type_name,
                type_class=type_class(type_name),
                default=raw.get("default", raw.get("default_value")),
                value=raw.get("value"),
                min_value=as_optional_number(raw.get("min_value", raw.get("min"))),
                max_value=as_optional_number(raw.get("max_value", raw.get("max"))),
                step=as_optional_number(raw.get("step")),
            )
        )
    return items


def _interface_values(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise InputError("interface_values must be an object", code="GM-INPUT-001")
    return dict(payload)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise InputError("closed_attribute_pipeline must be a boolean", code="GM-INPUT-001")


def _metadata(data: dict) -> dict[str, Any]:
    kept = {}
    for key in ("capture", "comment"):
        if key in data:
            kept[key] = data[key]
    return kept


def _assign_lines(text: str, document: Document) -> None:
    for tree in document.trees:
        for node in tree.nodes:
            if not node.id:
                continue
            for token in (f'"id": "{node.id}"', f'"id":"{node.id}"'):
                index = text.find(token)
                if index >= 0:
                    node.line = text.count("\n", 0, index) + 1
                    break
        for link in tree.links:
            link.line = None
