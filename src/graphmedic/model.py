"""Minimal analysis view. This is not an authored interchange format."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Socket:
    identifier: str
    name: str
    type_name: str
    type_class: str
    is_output: bool
    default: Any = None
    enabled: bool = True
    optional: bool | None = None
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None


@dataclass
class Node:
    id: str
    internal_id: str
    type: str
    inputs: list[Socket]
    outputs: list[Socket]
    parameters: dict[str, Any]
    label: str = ""
    muted: bool = False
    group_tree: str | None = None
    internal_links: list[tuple[str, str]] = field(default_factory=list)
    location: tuple[float, float] | None = None
    line: int | None = None

    def socket(self, identifier: str, *, output: bool) -> Socket | None:
        pool = self.outputs if output else self.inputs
        for item in pool:
            if item.identifier == identifier:
                return item
        return None


@dataclass
class Link:
    from_node: str
    from_socket: str
    to_node: str
    to_socket: str
    valid: bool | None
    muted: bool
    index: int
    line: int | None = None


@dataclass
class InterfaceSocket:
    identifier: str
    name: str
    in_out: str
    type_name: str
    type_class: str
    default: Any = None
    value: Any = None
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None

    @property
    def current(self) -> Any:
        return self.default if self.value is None else self.value


@dataclass
class Tree:
    name: str
    bl_idname: str
    kind: str
    is_group: bool
    nodes: list[Node]
    links: list[Link]
    interface: list[InterfaceSocket]
    interface_values: dict[str, Any] = field(default_factory=dict)

    def by_internal(self) -> dict[str, Node]:
        return {node.internal_id: node for node in self.nodes}

    def by_id(self) -> dict[str, list[Node]]:
        grouped: dict[str, list[Node]] = {}
        for node in self.nodes:
            grouped.setdefault(node.id, []).append(node)
        return grouped


@dataclass
class Document:
    format: str
    format_version: int
    adapter: str
    host: str
    version: str
    version_tuple: tuple[int, ...] | None
    root: str
    trees: list[Tree]
    closed_attribute_pipeline: bool | None
    flatten_interfaces: bool
    source_path: str
    metadata: dict[str, Any] = field(default_factory=dict)
    valid_omitted_means: bool | None = None

    def tree(self, name: str) -> Tree | None:
        for item in self.trees:
            if item.name == name:
                return item
        return None

    @property
    def root_tree(self) -> Tree | None:
        return self.tree(self.root)


@dataclass(frozen=True)
class Diagnostic:
    rule_id: str
    severity: str
    confidence: str
    status: str
    message: str
    graph_path: tuple[str, ...]
    node_id: str | None
    socket: str | None
    related_nodes: tuple[str, ...]
    evidence: dict[str, Any]
    why: str
    fix: str
    applicability: dict[str, Any]
    file: str = ""
    line: int | None = None

    def sort_key(self) -> tuple:
        return (
            self.file,
            self.rule_id,
            self.graph_path,
            self.node_id or "",
            self.socket or "",
            self.message,
            self.line or 0,
        )

    def to_dict(self) -> dict[str, Any]:
        from graphmedic.values import json_ready

        payload = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "status": self.status,
            "message": self.message,
            "graph_path": list(self.graph_path),
            "node_id": self.node_id,
            "socket": self.socket,
            "related_nodes": list(self.related_nodes),
            "evidence": json_ready(self.evidence),
            "why": self.why,
            "fix": self.fix,
            "applicability": json_ready(self.applicability),
            "file": self.file,
        }
        if self.line is not None:
            payload["line"] = self.line
        return payload
