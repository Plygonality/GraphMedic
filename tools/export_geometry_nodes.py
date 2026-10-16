"""Export a Geometry Nodes scatter tree from the running Blender.

Run with:
  blender --background --python tools/export_geometry_nodes.py -- --out fixtures/blender/valid_scatter.json

This is a bpy dump. It is not the gn-as-code serializer: that repository was
not available when GraphMedic v0.1 was built.
"""

from __future__ import annotations

import json
import sys

import bpy

SKIP = {
    "inputs",
    "outputs",
    "internal_links",
    "location",
    "location_absolute",
    "name",
    "label",
    "parent",
    "select",
    "hide",
    "mute",
    "show_options",
    "show_preview",
    "show_texture",
    "width",
    "height",
    "dimensions",
    "width_hidden",
    "color",
    "use_custom_color",
    "color_tag",
    "warning_propagation",
    "panel_states",
    "type",
    "node_tree",
}


def plain(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    try:
        return [plain(item) for item in value]
    except TypeError:
        return None


def socket_payload(socket):
    if socket.identifier == "__extend__":
        return None
    payload = {
        "identifier": socket.identifier,
        "name": socket.name,
        "type": socket.type,
        "bl_idname": socket.bl_idname,
        "enabled": bool(getattr(socket, "enabled", True)),
    }
    if getattr(socket, "is_unavailable", False):
        payload["is_unavailable"] = True
    if hasattr(socket, "default_value"):
        payload["default"] = plain(socket.default_value)
    return payload


def parameters(node):
    values = {}
    for prop in node.bl_rna.properties:
        key = prop.identifier
        if key in SKIP or key.startswith("bl_") or getattr(prop, "is_readonly", False):
            continue
        if prop.type not in {"ENUM", "BOOLEAN", "INT", "FLOAT", "STRING"}:
            continue
        try:
            values[key] = plain(getattr(node, key))
        except Exception:
            continue
    if hasattr(node, "is_active_output"):
        values["is_active_output"] = bool(node.is_active_output)
    return values


def dump_tree(tree):
    interface = []
    for item in tree.interface.items_tree:
        if getattr(item, "item_type", "") != "SOCKET":
            continue
        entry = {
            "identifier": item.identifier,
            "name": item.name,
            "in_out": item.in_out,
            "socket_type": item.socket_type,
            "type": item.socket_type,
        }
        for key in ("default_value", "min_value", "max_value"):
            if hasattr(item, key):
                entry[key] = plain(getattr(item, key))
        interface.append(entry)
    nodes = []
    for node in tree.nodes:
        nodes.append(
            {
                "id": node.name,
                "name": node.name,
                "type": node.bl_idname,
                "label": node.label,
                "inputs": [item for item in (socket_payload(sock) for sock in node.inputs) if item],
                "outputs": [item for item in (socket_payload(sock) for sock in node.outputs) if item],
                "parameters": parameters(node),
                "location": [round(float(node.location[0]), 3), round(float(node.location[1]), 3)],
            }
        )
    links = []
    for link in tree.links:
        links.append(
            {
                "from_node": link.from_node.name,
                "from_socket": link.from_socket.identifier,
                "to_node": link.to_node.name,
                "to_socket": link.to_socket.identifier,
                "valid": bool(link.is_valid),
                "muted": bool(link.is_muted),
            }
        )
    return {
        "name": tree.name,
        "bl_idname": tree.bl_idname,
        "kind": "geometry",
        "is_group": False,
        "interface": interface,
        "nodes": nodes,
        "links": links,
    }


def build():
    bpy.ops.mesh.primitive_plane_add(size=2)
    obj = bpy.context.active_object
    obj.name = "ScatterGround"
    tree = bpy.data.node_groups.new("Scatter", "GeometryNodeTree")
    modifier = obj.modifiers.new("Scatter", "NODES")
    modifier.node_group = tree
    geometry_in = tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    density = tree.interface.new_socket(name="Density", in_out="INPUT", socket_type="NodeSocketFloat")
    density.default_value = 4.0
    density.min_value = 0.0
    density.max_value = 100.0
    seed = tree.interface.new_socket(name="Seed", in_out="INPUT", socket_type="NodeSocketInt")
    seed.default_value = 7
    seed.min_value = 0
    seed.max_value = 100000
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_in = tree.nodes.new("NodeGroupInput")
    group_out = tree.nodes.new("NodeGroupOutput")
    distribute = tree.nodes.new("GeometryNodeDistributePointsOnFaces")
    ico = tree.nodes.new("GeometryNodeMeshIcoSphere")
    ico.inputs["Radius"].default_value = 0.2
    ico.inputs["Subdivisions"].default_value = 1
    instance = tree.nodes.new("GeometryNodeInstanceOnPoints")
    group_in.location = (-600, 0)
    distribute.location = (-300, 80)
    ico.location = (-300, -220)
    instance.location = (40, 0)
    group_out.location = (340, 0)
    tree.links.new(group_in.outputs[geometry_in.identifier], distribute.inputs["Mesh"])
    tree.links.new(group_in.outputs[density.identifier], distribute.inputs["Density"])
    tree.links.new(group_in.outputs[seed.identifier], distribute.inputs["Seed"])
    tree.links.new(distribute.outputs["Points"], instance.inputs["Points"])
    tree.links.new(ico.outputs["Mesh"], instance.inputs["Instance"])
    tree.links.new(instance.outputs["Instances"], group_out.inputs["Geometry"])
    return obj, tree


def main():
    out = "fixtures/blender/valid_scatter.json"
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if "--out" in args:
            out = args[args.index("--out") + 1]
    _obj, tree = build()
    document = {
        "format": "blender.geometry_nodes.capture",
        "format_version": 1,
        "application": {
            "name": "Blender",
            "version": ".".join(str(part) for part in bpy.app.version),
            "version_string": bpy.app.version_string,
            "build_hash": bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash),
            "verified": True,
        },
        "capture": {
            "tool": "tools/export_geometry_nodes.py",
            "host_run": True,
            "note": "Direct bpy dump from Blender. gn-as-code was not available, so this is not that serializer.",
        },
        "closed_attribute_pipeline": False,
        "flatten_interfaces": False,
        "root": tree.name,
        "trees": [dump_tree(tree)],
    }
    text = json.dumps(document, indent=2) + "\n"
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"EXPORTED {out}")
    print(f"BLENDER {bpy.app.version_string}")
    print(f"HASH {document['application']['build_hash']}")
    print(f"NODES {len(document['trees'][0]['nodes'])}")
    print(f"LINKS {len(document['trees'][0]['links'])}")


if __name__ == "__main__":
    main()
