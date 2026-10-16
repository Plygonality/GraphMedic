"""Version-aware metadata recorded from a real Blender 4.5.14 probe."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class Catalog:
    data: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.data["version"])

    @property
    def version_tuple(self) -> tuple[int, ...]:
        return tuple(self.data["version_tuple"])

    def applies_to(self, version: tuple[int, ...] | None) -> bool:
        return version == self.version_tuple

    def output_types(self) -> set[str]:
        return set(self.data["output_node_types"])

    def viewer_types(self) -> set[str]:
        return set(self.data["viewer_node_types"])

    def zone_pairs(self) -> list[tuple[str, str]]:
        return [tuple(pair) for pair in self.data["zone_pairs"]]

    def ignore_sockets(self) -> set[str]:
        return set(self.data["ignore_socket_identifiers"])


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    raw = resources.files("graphmedic").joinpath("data/blender-4.5.14.json").read_text(encoding="utf-8")
    return Catalog(json.loads(raw))
