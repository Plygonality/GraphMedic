"""Follow-up probes that need evaluated geometry and zone pairing."""

from __future__ import annotations

import json
import traceback

import bpy


def plain(value):
    if value is None or isinstance(value, (bool, int, str, float)):
        return value
    try:
        return [plain(item) for item in value]
    except TypeError:
        return str(value)


def sock(socket):
    return {
        "identifier": socket.identifier,
        "name": socket.name,
        "type": socket.type,
        "enabled": bool(getattr(socket, "enabled", True)),
        "unavailable": bool(getattr(socket, "is_unavailable", False)),
        "default": plain(getattr(socket, "default_value", None)) if hasattr(socket, "default_value") else None,
    }


def fresh_object(name):
    bpy.ops.mesh.primitive_plane_add()
    obj = bpy.context.active_object
    obj.name = name
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    mod = obj.modifiers.new("GN", "NODES")
    mod.node_group = ng
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    out = ng.nodes.new("NodeGroupOutput")
    return obj, ng, out


def mesh_counts(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    mesh = ev.to_mesh()
    counts = {"vertices": len(mesh.vertices), "edges": len(mesh.edges), "polygons": len(mesh.polygons)}
    ev.to_mesh_clear()
    info = {"type": type(ev.data).__name__}
    for attr in ("pointcloud", "point_cloud", "curves"):
        if hasattr(ev, attr):
            value = getattr(ev, attr)
            info[attr] = None if value is None else type(value).__name__
    counts["eval"] = info
    return counts


def cleanup(obj, ng):
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.node_groups.remove(ng)


def run(label, fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "traceback": traceback.format_exc()}


def grid(vx, vy):
    obj, ng, out = fresh_object("Grid")
    grid = ng.nodes.new("GeometryNodeMeshGrid")
    grid.inputs["Vertices X"].default_value = vx
    grid.inputs["Vertices Y"].default_value = vy
    ng.links.new(grid.outputs["Mesh"], out.inputs["Geometry"])
    counts = mesh_counts(obj)
    cleanup(obj, ng)
    return counts


def points(count):
    obj, ng, out = fresh_object("Points")
    pts = ng.nodes.new("GeometryNodePoints")
    pts.inputs["Count"].default_value = count
    converted = None
    try:
        to_verts = ng.nodes.new("GeometryNodePointsToVertices")
        ng.links.new(pts.outputs[0], to_verts.inputs[0])
        ng.links.new(to_verts.outputs[0], out.inputs["Geometry"])
        converted = "GeometryNodePointsToVertices"
    except Exception as exc:  # noqa: BLE001
        ng.links.new(pts.outputs[0], out.inputs["Geometry"])
        converted = f"direct:{exc}"
    counts = mesh_counts(obj)
    counts["conversion"] = converted
    cleanup(obj, ng)
    return counts


def mesh_line(count):
    obj, ng, out = fresh_object("Line")
    line = ng.nodes.new("GeometryNodeMeshLine")
    line.inputs["Count"].default_value = count
    ng.links.new(line.outputs["Mesh"], out.inputs["Geometry"])
    counts = mesh_counts(obj)
    cleanup(obj, ng)
    return counts


def math_divide():
    tree = bpy.data.node_groups.new("Math", "GeometryNodeTree")
    node = tree.nodes.new("ShaderNodeMath")
    node.operation = "DIVIDE"
    data = {
        "inputs": [sock(item) for item in node.inputs],
        "outputs": [sock(item) for item in node.outputs],
        "operation": node.operation,
    }
    node.inputs[0].default_value = 1.0
    node.inputs[1].default_value = 0.0
    data["divisor_identifier"] = node.inputs[1].identifier
    data["dividend_identifier"] = node.inputs[0].identifier
    bpy.data.node_groups.remove(tree)
    return data


def zone_pair():
    tree = bpy.data.node_groups.new("Zone", "GeometryNodeTree")
    sim_in = tree.nodes.new("GeometryNodeSimulationInput")
    sim_out = tree.nodes.new("GeometryNodeSimulationOutput")
    before = {"in": [sock(s) for s in sim_in.outputs], "out": [sock(s) for s in sim_out.inputs]}
    paired = None
    try:
        sim_in.pair_with_output(sim_out)
        paired = True
    except Exception as exc:  # noqa: BLE001
        paired = str(exc)
    after = {
        "paired": paired,
        "in_inputs": [sock(s) for s in sim_in.inputs],
        "in_outputs": [sock(s) for s in sim_in.outputs],
        "out_inputs": [sock(s) for s in sim_out.inputs],
        "out_outputs": [sock(s) for s in sim_out.outputs],
        "state_items_in": len(getattr(sim_in, "state_items", [])),
        "state_items_out": len(getattr(sim_out, "state_items", [])),
    }
    rep_in = tree.nodes.new("GeometryNodeRepeatInput")
    rep_out = tree.nodes.new("GeometryNodeRepeatOutput")
    rep = None
    try:
        rep_in.pair_with_output(rep_out)
        rep = True
    except Exception as exc:  # noqa: BLE001
        rep = str(exc)
    after["repeat_paired"] = rep
    after["repeat_in_outputs"] = [sock(s) for s in rep_in.outputs]
    after["repeat_out_inputs"] = [sock(s) for s in rep_out.inputs]
    bpy.data.node_groups.remove(tree)
    return {"before": before, "after": after}


def interface_and_group_input():
    tree = bpy.data.node_groups.new("Iface", "GeometryNodeTree")
    geo = tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    density = tree.interface.new_socket(name="Density", in_out="INPUT", socket_type="NodeSocketFloat")
    density.default_value = 4.0
    density.min_value = 0.0
    density.max_value = 100.0
    out = tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = tree.nodes.new("NodeGroupInput")
    go = tree.nodes.new("NodeGroupOutput")
    data = {
        "interface": [],
        "group_input_outputs": [sock(s) for s in gi.outputs],
        "group_output_inputs": [sock(s) for s in go.inputs],
        "group_output_active": go.is_active_output,
    }
    for item in tree.interface.items_tree:
        if item.item_type != "SOCKET":
            data["interface"].append({"item_type": item.item_type, "name": item.name})
            continue
        entry = {
            "identifier": item.identifier,
            "name": item.name,
            "in_out": item.in_out,
            "socket_type": item.socket_type,
            "item_type": item.item_type,
        }
        for key in ("default_value", "min_value", "max_value", "subtype", "description"):
            if hasattr(item, key):
                entry[key] = plain(getattr(item, key))
        data["interface"].append(entry)
    link = tree.links.new(gi.outputs[0], go.inputs[0])
    data["link"] = {
        "from_node": link.from_node.name,
        "from_socket": link.from_socket.identifier,
        "to_node": link.to_node.name,
        "to_socket": link.to_socket.identifier,
        "is_valid": bool(link.is_valid),
        "is_muted": bool(link.is_muted),
    }
    bad = None
    try:
        tree.links.new(gi.outputs[0], go.inputs[0])
    except Exception as exc:  # noqa: BLE001
        bad = str(exc)
    data["second_link_error"] = bad
    bpy.data.node_groups.remove(tree)
    return data


def main():
    result = {
        "grids": {f"{x}_{y}": run(f"{x}_{y}", lambda x=x, y=y: grid(x, y)) for x, y in [(0, 0), (0, 3), (1, 1), (1, 2), (2, 1), (2, 2)]},
        "points": {str(n): run(str(n), lambda n=n: points(n)) for n in (0, 1, 4)},
        "mesh_line": {str(n): run(str(n), lambda n=n: mesh_line(n)) for n in (0, 1, 2)},
        "math_divide": run("math", math_divide),
        "zones": run("zones", zone_pair),
        "interface": run("interface", interface_and_group_input),
    }
    with open("/tmp/probe_gn2_result.json", "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps({k: result[k] for k in ("grids", "points", "mesh_line")}, indent=2))
    print("MATH", json.dumps(result["math_divide"]))
    print("ZONES paired", result["zones"].get("after", result["zones"]))


if __name__ == "__main__":
    main()
