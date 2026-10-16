"""Probe Blender 4.5 Geometry Nodes RNA and evaluate a few constant cases.

Writes /tmp/probe_gn_result.json. Does not modify the GraphMedic repo.
"""

from __future__ import annotations

import json
import traceback

import bpy

TYPES = [
    "NodeGroupInput",
    "NodeGroupOutput",
    "NodeReroute",
    "GeometryNodeDistributePointsOnFaces",
    "GeometryNodeInstanceOnPoints",
    "GeometryNodeRealizeInstances",
    "GeometryNodeMeshIcoSphere",
    "GeometryNodeMeshGrid",
    "GeometryNodePoints",
    "GeometryNodeMeshLine",
    "GeometryNodeJoinGeometry",
    "GeometryNodeStoreNamedAttribute",
    "GeometryNodeInputNamedAttribute",
    "GeometryNodeCaptureAttribute",
    "ShaderNodeMath",
    "FunctionNodeMath",
    "GeometryNodeSimulationInput",
    "GeometryNodeSimulationOutput",
    "GeometryNodeRepeatInput",
    "GeometryNodeRepeatOutput",
    "GeometryNodeViewer",
    "GeometryNodeGroup",
    "ShaderNodeValue",
    "FunctionNodeInputString",
    "GeometryNodeMeshBoolean",
    "GeometryNodeSubdivideMesh",
    "GeometryNodeDeleteGeometry",
    "GeometryNodeTransform",
    "GeometryNodeSetPosition",
    "FunctionNodeCompare",
    "GeometryNodeIndexSwitch",
]


SKIP_PROPS = {
    "rna_type",
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
}


def plain(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    try:
        return [plain(v) for v in value]
    except TypeError:
        return str(value)


def socket_info(sock):
    info = {
        "identifier": sock.identifier,
        "name": sock.name,
        "type": sock.type,
        "bl_idname": getattr(sock, "bl_idname", ""),
        "enabled": bool(getattr(sock, "enabled", True)),
        "is_unavailable": bool(getattr(sock, "is_unavailable", False)),
        "is_output": bool(sock.is_output),
        "hide": bool(getattr(sock, "hide", False)),
    }
    if hasattr(sock, "default_value"):
        try:
            info["default_value"] = plain(sock.default_value)
        except Exception as exc:  # noqa: BLE001
            info["default_error"] = str(exc)
    return info


def describe_node(node):
    props = {}
    for prop in node.bl_rna.properties:
        key = prop.identifier
        if key in SKIP_PROPS or key.startswith("bl_"):
            continue
        entry = {"type": prop.type, "description": prop.description}
        if prop.type == "ENUM":
            entry["items"] = [
                {"identifier": item.identifier, "name": item.name, "description": item.description}
                for item in prop.enum_items
            ]
        if getattr(prop, "is_readonly", False):
            entry["readonly"] = True
        props[key] = entry
    values = {}
    for key, meta in props.items():
        if meta.get("readonly"):
            continue
        if meta["type"] in {"ENUM", "BOOLEAN", "INT", "FLOAT", "STRING"}:
            try:
                values[key] = plain(getattr(node, key))
            except Exception as exc:  # noqa: BLE001
                values[key] = {"error": str(exc)}
    return {
        "bl_idname": node.bl_idname,
        "bl_label": node.bl_label,
        "description": node.bl_rna.description,
        "inputs": [socket_info(sock) for sock in node.inputs],
        "outputs": [socket_info(sock) for sock in node.outputs],
        "properties": props,
        "parameter_values": values,
        "internal_links": [
            [link.from_socket.identifier, link.to_socket.identifier] for link in node.internal_links
        ],
    }


def probe_type(bl_idname):
    tree = bpy.data.node_groups.new("_probe", "GeometryNodeTree")
    try:
        node = tree.nodes.new(bl_idname)
        data = describe_node(node)
        if bl_idname in {"ShaderNodeMath", "FunctionNodeMath"}:
            modes = {}
            operation = next((p for p in node.bl_rna.properties if p.identifier == "operation"), None)
            if operation is not None:
                for item in operation.enum_items:
                    try:
                        node.operation = item.identifier
                    except Exception as exc:  # noqa: BLE001
                        modes[item.identifier] = {"error": str(exc)}
                        continue
                    modes[item.identifier] = {
                        "inputs": [socket_info(sock) for sock in node.inputs],
                        "outputs": [socket_info(sock) for sock in node.outputs],
                    }
            data["operation_sockets"] = modes
        return data
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "traceback": traceback.format_exc()}
    finally:
        bpy.data.node_groups.remove(tree)


def eval_case(setup):
    bpy.ops.mesh.primitive_plane_add()
    obj = bpy.context.active_object
    ng = bpy.data.node_groups.new("EvalCase", "GeometryNodeTree")
    mod = obj.modifiers.new("GN", "NODES")
    mod.node_group = ng
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    out = ng.nodes.new("NodeGroupOutput")
    setup(ng, out)
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    mesh = ev.to_mesh()
    result = {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
    }
    point_cloud = None
    try:
        point_cloud = ev.point_cloud
    except Exception:  # noqa: BLE001
        point_cloud = None
    if point_cloud is not None:
        result["point_cloud_points"] = len(point_cloud.points) if hasattr(point_cloud, "points") else None
    ev.to_mesh_clear()
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.node_groups.remove(ng)
    return result


def grid_case(vx, vy):
    def setup(ng, out):
        grid = ng.nodes.new("GeometryNodeMeshGrid")
        for sock in grid.inputs:
            if sock.name == "Vertices X":
                sock.default_value = vx
            if sock.name == "Vertices Y":
                sock.default_value = vy
        ng.links.new(grid.outputs["Mesh"], out.inputs["Geometry"])

    return eval_case(setup)


def points_case(count):
    def setup(ng, out):
        points = ng.nodes.new("GeometryNodePoints")
        for sock in points.inputs:
            if sock.name == "Count":
                sock.default_value = count
        ng.links.new(points.outputs[0], out.inputs["Geometry"])

    return eval_case(setup)


def main():
    result = {
        "blender_version": bpy.app.version_string,
        "blender_version_tuple": list(bpy.app.version),
        "nodes": {},
        "evaluations": {},
        "errors": [],
    }
    for bl_idname in TYPES:
        result["nodes"][bl_idname] = probe_type(bl_idname)
    for label, fn in {
        "grid_1_2": lambda: grid_case(1, 2),
        "grid_2_2": lambda: grid_case(2, 2),
        "grid_0_4": lambda: grid_case(0, 4),
        "points_0": lambda: points_case(0),
        "points_3": lambda: points_case(3),
    }.items():
        try:
            result["evaluations"][label] = fn()
        except Exception as exc:  # noqa: BLE001
            result["errors"].append({"case": label, "error": str(exc), "traceback": traceback.format_exc()})
    with open("/tmp/probe_gn_result.json", "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print("WROTE /tmp/probe_gn_result.json")
    print("EVAL", json.dumps(result["evaluations"]))
    print("ERRORS", len(result["errors"]))


if __name__ == "__main__":
    main()
