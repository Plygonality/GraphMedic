from dataclasses import dataclass


@dataclass
class Limits:
    """Hard bounds for untrusted graph JSON. Values are inclusive maxima."""

    max_bytes: int = 8 * 1024 * 1024
    max_nodes: int = 20_000
    max_links: int = 50_000
    max_depth: int = 64
    max_files: int = 500
    max_group_visits: int = 64

    def overridden(self, **kwargs: int) -> "Limits":
        data = {
            "max_bytes": self.max_bytes,
            "max_nodes": self.max_nodes,
            "max_links": self.max_links,
            "max_depth": self.max_depth,
            "max_files": self.max_files,
            "max_group_visits": self.max_group_visits,
        }
        data.update(kwargs)
        return Limits(**data)
