"""Write the positive and negative rule fixtures. Run from the repository root."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "rules"


def sock(identifier, type_name, **extra):
    payload = {"identifier": identifier, "name": extra.pop("name", identifier), "type": type_name}
    payload.update(extra)
    return payload


def node(node_id, node_type, inputs=None, outputs=None, parameters=None, group_tree=None):
    payload = {
        "id": node_id,
        "type": node_type,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "parameters": parameters or {},
    }
    if group_tree:
        payload["group_tree"] = group_tree
    return payload


def link(source, source_socket, target, target_socket, valid=True):
    payload = {
        "from_node": source,
        "from_socket": source_socket,
        "to_node": target,
        "to_socket": target_socket,
        "muted": False,
    }
    if valid is not None:
        payload["valid"] = valid
    return payload


def tree(name, nodes, links, interface=None, values=None, group=False):
    payload = {
        "name": name,
        "bl_idname": "GeometryNodeTree",
        "kind": "geometry",
        "is_group": group,
        "interface": interface or [],
        "nodes": nodes,
        "links": links,
    }
    if values:
        payload["interface_values"] = values
    return payload


def document(trees, root="Main", **flags):
    payload = {
        "format": "blender.geometry_nodes.capture",
        "format_version": 1,
        "application": {"name": "Blender", "version": "4.5.14", "verified": False},
        "root": root,
        "trees": trees,
    }
    if "closed" in flags and flags["closed"] is not None:
        payload["closed_attribute_pipeline"] = flags["closed"]
    if flags.get("flatten"):
        payload["flatten_interfaces"] = True
    return payload


def iface(identifier, name, direction, type_name, **extra):
    payload = {"identifier": identifier, "name": name, "in_out": direction, "type": type_name}
    payload.update(extra)
    return payload


def spine():
    interface = [
        iface("Socket_0", "Geometry", "INPUT", "NodeSocketGeometry"),
        iface("Socket_1", "Geometry", "OUTPUT", "NodeSocketGeometry"),
    ]
    nodes = [
        node("Group Input", "NodeGroupInput", outputs=[sock("Socket_0", "GEOMETRY")]),
        node(
            "Group Output",
            "NodeGroupOutput",
            inputs=[sock("Socket_1", "GEOMETRY")],
            parameters={"is_active_output": True},
        ),
    ]
    links = [link("Group Input", "Socket_0", "Group Output", "Socket_1")]
    return interface, nodes, links


def write(name, payload, raw=None):
    path = ROOT / name
    if raw is not None:
        path.write_text(raw)
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    interface, nodes, links = spine()
    base = document([tree("Main", nodes, links, interface)])
    write("GM-STRUCT-001.pass.json", base)
    dup_nodes = [
        node("Box", "GeometryNodeMeshGrid", inputs=[sock("Vertices X", "INT", default=2), sock("Vertices Y", "INT", default=2)]),
        node("Box", "GeometryNodeMeshGrid", inputs=[sock("Vertices X", "INT", default=2), sock("Vertices Y", "INT", default=2)]),
    ]
    write("GM-STRUCT-001.fail.json", document([tree("Main", dup_nodes, [], interface)]))

    write("GM-STRUCT-002.pass.json", base)
    bad_links = links + [link("Group Input", "Socket_0", "Group Output", "MissingSocket")]
    write("GM-STRUCT-002.fail.json", document([tree("Main", nodes, bad_links, interface)]))

    write("GM-STRUCT-003.pass.json", base)
    write("GM-STRUCT-003.fail.json", document([tree("Main", [nodes[0]], [], interface)]))

    math = node(
        "Math",
        "ShaderNodeMath",
        inputs=[sock("Value", "VALUE", default=1), sock("Value_001", "VALUE", default=2)],
        outputs=[sock("Value", "VALUE")],
        parameters={"operation": "ADD"},
    )
    offset = node(
        "Set Position",
        "GeometryNodeSetPosition",
        inputs=[sock("Geometry", "GEOMETRY"), sock("Offset", "VECTOR", default=[0, 0, 0])],
        outputs=[sock("Geometry", "GEOMETRY")],
    )
    nodes_004 = nodes + [math, offset]
    links_004 = [
        link("Group Input", "Socket_0", "Set Position", "Geometry"),
        link("Math", "Value", "Set Position", "Offset", valid=True),
        link("Set Position", "Geometry", "Group Output", "Socket_1"),
    ]
    write("GM-STRUCT-004.pass.json", document([tree("Main", nodes_004, links_004, interface)]))
    links_bad = [dict(item) for item in links_004]
    links_bad[1]["valid"] = False
    write("GM-STRUCT-004.fail.json", document([tree("Main", nodes_004, links_bad, interface)]))
    links_unknown = []
    for item in links_004:
        copied = dict(item)
        if copied["to_socket"] == "Offset":
            copied.pop("valid")
        links_unknown.append(copied)
    write("GM-STRUCT-004.unknown.json", document([tree("Main", nodes_004, links_unknown, interface)]))

    distribute = node(
        "Distribute",
        "GeometryNodeDistributePointsOnFaces",
        inputs=[sock("Mesh", "GEOMETRY"), sock("Density", "VALUE", default=4)],
        outputs=[sock("Points", "GEOMETRY")],
    )
    linked = [
        link("Group Input", "Socket_0", "Distribute", "Mesh"),
        link("Distribute", "Points", "Group Output", "Socket_1"),
    ]
    write("GM-STRUCT-005.pass.json", document([tree("Main", nodes + [distribute], linked, interface)]))
    write(
        "GM-STRUCT-005.fail.json",
        document([tree("Main", nodes + [distribute], [link("Distribute", "Points", "Group Output", "Socket_1")], interface)]),
    )

    write("GM-STRUCT-006.pass.json", base)
    orphan = node("Orphan", "ShaderNodeMath", inputs=[sock("Value", "VALUE", default=1)], outputs=[sock("Value", "VALUE")])
    write("GM-STRUCT-006.fail.json", document([tree("Main", nodes + [orphan], links, interface)]))

    sim_in = node(
        "Sim In",
        "GeometryNodeSimulationInput",
        outputs=[sock("Item_0", "GEOMETRY"), sock("Delta Time", "VALUE")],
    )
    sim_out = node(
        "Sim Out",
        "GeometryNodeSimulationOutput",
        inputs=[sock("Item_0", "GEOMETRY"), sock("Skip", "BOOLEAN", default=False)],
        outputs=[sock("Item_0", "GEOMETRY")],
    )
    sim_links = [
        link("Sim In", "Item_0", "Sim Out", "Item_0"),
        link("Sim Out", "Item_0", "Sim In", "Item_0"),
        link("Sim Out", "Item_0", "Group Output", "Socket_1"),
    ]
    write("GM-STRUCT-007.pass.json", document([tree("Main", [sim_in, sim_out, nodes[1]], sim_links, interface)]))
    cycle_a = node("A", "ShaderNodeMath", inputs=[sock("Value", "VALUE", default=1)], outputs=[sock("Value", "VALUE")])
    cycle_b = node("B", "ShaderNodeMath", inputs=[sock("Value", "VALUE", default=1)], outputs=[sock("Value", "VALUE")])
    write(
        "GM-STRUCT-007.fail.json",
        document(
            [
                tree(
                    "Main",
                    [cycle_a, cycle_b, nodes[1]],
                    [link("A", "Value", "B", "Value"), link("B", "Value", "A", "Value")],
                    interface,
                )
            ]
        ),
    )
    bake = node("Bake", "GeometryNodeBakeZone", inputs=[sock("In", "GEOMETRY")], outputs=[sock("Out", "GEOMETRY")])
    write(
        "GM-STRUCT-007.unknown.json",
        document([tree("Main", [bake, nodes[1]], [link("Bake", "Out", "Bake", "In")], interface)]),
    )

    write("GM-STRUCT-008.pass.json", base)
    inf_doc = document(
        [
            tree(
                "Main",
                [node("Wide", "ShaderNodeMath", parameters={"INFTOKEN": 0}, inputs=[sock("Value", "VALUE", default=1)], outputs=[sock("Value", "VALUE")]), nodes[1]],
                [],
                interface,
            )
        ]
    )
    raw = json.dumps(inf_doc, indent=2).replace('"INFTOKEN": 0', '"level": 1e309')
    write("GM-STRUCT-008.fail.json", inf_doc, raw=raw + "\n")

    ok_interface = [
        iface("Socket_0", "Geometry", "INPUT", "NodeSocketGeometry"),
        iface("Socket_1", "Density", "INPUT", "NodeSocketFloat", default=4, min_value=0, max_value=10, step=0.1),
        iface("Socket_2", "Geometry", "OUTPUT", "NodeSocketGeometry"),
    ]
    group_in = node("Group Input", "NodeGroupInput", outputs=[sock("Socket_0", "GEOMETRY"), sock("Socket_1", "VALUE", default=4)])
    group_out = node("Group Output", "NodeGroupOutput", inputs=[sock("Socket_2", "GEOMETRY")], parameters={"is_active_output": True})
    write(
        "GM-STRUCT-009.pass.json",
        document([tree("Main", [group_in, group_out], [link("Group Input", "Socket_0", "Group Output", "Socket_2")], ok_interface)]),
    )
    bad_interface = [
        iface("Socket_0", "Geometry", "INPUT", "NodeSocketGeometry"),
        iface("Socket_1", "Density", "INPUT", "NodeSocketFloat", default=4, min_value=5, max_value=1, step=0),
        iface("Socket_2", "Geometry", "OUTPUT", "NodeSocketGeometry"),
    ]
    write(
        "GM-STRUCT-009.fail.json",
        document([tree("Main", [group_in, group_out], [link("Group Input", "Socket_0", "Group Output", "Socket_2")], bad_interface)]),
    )
    write(
        "GM-STRUCT-010.pass.json",
        document([tree("Main", [group_in, group_out], [link("Group Input", "Socket_0", "Group Output", "Socket_2")], ok_interface)]),
    )
    outside = [
        iface("Socket_0", "Geometry", "INPUT", "NodeSocketGeometry"),
        iface("Socket_1", "Density", "INPUT", "NodeSocketFloat", value=150, min_value=0, max_value=100),
        iface("Socket_2", "Geometry", "OUTPUT", "NodeSocketGeometry"),
    ]
    write(
        "GM-STRUCT-010.fail.json",
        document([tree("Main", [group_in, group_out], [link("Group Input", "Socket_0", "Group Output", "Socket_2")], outside)]),
    )

    child_interface = [iface("Socket_9", "Geometry", "OUTPUT", "NodeSocketGeometry")]
    child_nodes = [node("Group Output", "NodeGroupOutput", inputs=[sock("Socket_9", "GEOMETRY")], parameters={"is_active_output": True})]
    parent_nodes = nodes + [node("Call", "GeometryNodeGroup", group_tree="Child")]
    write(
        "GM-STRUCT-011.pass.json",
        document([tree("Main", parent_nodes, links, interface), tree("Child", child_nodes, [], child_interface, group=True)]),
    )
    missing = nodes + [node("Call", "GeometryNodeGroup", group_tree="Missing")]
    write("GM-STRUCT-011.fail.json", document([tree("Main", missing, links, interface)]))

    flat_a = [iface("Socket_A", "Radius", "INPUT", "NodeSocketFloat", default=1)]
    flat_b = [iface("Socket_B", "Radius", "INPUT", "NodeSocketFloat", default=1)]
    write(
        "GM-STRUCT-012.pass.json",
        document(
            [
                tree("Main", [node("Call", "GeometryNodeGroup", group_tree="Other")], [], flat_a),
                tree("Other", [], [], flat_b, group=True),
            ],
            flatten=True,
        ),
    )
    clash_b = [iface("Socket_A", "Other Radius", "INPUT", "NodeSocketFloat", default=2)]
    write(
        "GM-STRUCT-012.fail.json",
        document(
            [
                tree("Main", [node("Call", "GeometryNodeGroup", group_tree="Other")], [], flat_a),
                tree("Other", [], [], clash_b, group=True),
            ],
            flatten=True,
        ),
    )
    write(
        "GM-STRUCT-012.unspecified.json",
        document(
            [
                tree("Main", [node("Call", "GeometryNodeGroup", group_tree="Other")], [], flat_a),
                tree("Other", [], [], clash_b, group=True),
            ]
        ),
    )

    store = node(
        "Store",
        "GeometryNodeStoreNamedAttribute",
        inputs=[sock("Geometry", "GEOMETRY"), sock("Name", "STRING", default="density"), sock("Value", "VALUE", default=1)],
        outputs=[sock("Geometry", "GEOMETRY")],
        parameters={"domain": "POINT", "data_type": "FLOAT"},
    )
    read = node(
        "Read",
        "GeometryNodeInputNamedAttribute",
        inputs=[sock("Name", "STRING", default="density")],
        outputs=[sock("Attribute", "VALUE")],
    )
    attr_links = [link("Group Input", "Socket_0", "Store", "Geometry"), link("Store", "Geometry", "Group Output", "Socket_1")]
    write("GM-DOMAIN-001.pass.json", document([tree("Main", nodes + [store, read], attr_links, interface)], closed=True))
    write(
        "GM-DOMAIN-001.fail.json",
        document([tree("Main", nodes + [read], links, interface)], closed=True),
    )
    write("GM-DOMAIN-001.open.json", document([tree("Main", nodes + [read], links, interface)], closed=False))

    position_point = node(
        "Store",
        "GeometryNodeStoreNamedAttribute",
        inputs=[sock("Geometry", "GEOMETRY"), sock("Name", "STRING", default="position")],
        outputs=[sock("Geometry", "GEOMETRY")],
        parameters={"domain": "POINT"},
    )
    position_face = node(
        "Store",
        "GeometryNodeStoreNamedAttribute",
        inputs=[sock("Geometry", "GEOMETRY"), sock("Name", "STRING", default="position")],
        outputs=[sock("Geometry", "GEOMETRY")],
        parameters={"domain": "FACE"},
    )
    custom_face = node(
        "Store",
        "GeometryNodeStoreNamedAttribute",
        inputs=[sock("Geometry", "GEOMETRY"), sock("Name", "STRING", default="mask")],
        outputs=[sock("Geometry", "GEOMETRY")],
        parameters={"domain": "FACE"},
    )
    write(
        "GM-DOMAIN-002.pass.json",
        document([tree("Main", nodes + [position_point], [link("Group Input", "Socket_0", "Store", "Geometry"), link("Store", "Geometry", "Group Output", "Socket_1")], interface)]),
    )
    write(
        "GM-DOMAIN-002.fail.json",
        document([tree("Main", nodes + [position_face], [link("Group Input", "Socket_0", "Store", "Geometry"), link("Store", "Geometry", "Group Output", "Socket_1")], interface)]),
    )
    write(
        "GM-DOMAIN-002.custom.json",
        document([tree("Main", nodes + [custom_face], [link("Group Input", "Socket_0", "Store", "Geometry"), link("Store", "Geometry", "Group Output", "Socket_1")], interface)]),
    )

    points = lambda count: node(
        "Points",
        "GeometryNodePoints",
        inputs=[sock("Count", "INT", default=count)],
        outputs=[sock("Geometry", "GEOMETRY")],
    )
    write(
        "GM-DOMAIN-003.pass.json",
        document([tree("Main", nodes + [points(4)], [link("Points", "Geometry", "Group Output", "Socket_1")], interface)]),
    )
    write(
        "GM-DOMAIN-003.fail.json",
        document([tree("Main", nodes + [points(0)], [link("Points", "Geometry", "Group Output", "Socket_1")], interface)]),
    )
    grid_one = node(
        "Grid",
        "GeometryNodeMeshGrid",
        inputs=[sock("Vertices X", "INT", default=1), sock("Vertices Y", "INT", default=2)],
        outputs=[sock("Mesh", "GEOMETRY")],
    )
    write(
        "GM-DOMAIN-003.one.json",
        document([tree("Main", nodes + [grid_one], [link("Grid", "Mesh", "Group Output", "Socket_1")], interface)]),
    )

    def math_div(divisor):
        return node(
            "Math",
            "ShaderNodeMath",
            inputs=[sock("Value", "VALUE", default=1), sock("Value_001", "VALUE", default=divisor)],
            outputs=[sock("Value", "VALUE")],
            parameters={"operation": "DIVIDE"},
        )

    write("GM-DOMAIN-004.pass.json", document([tree("Main", nodes + [math_div(2)], links, interface)]))
    write("GM-DOMAIN-004.fail.json", document([tree("Main", nodes + [math_div(0)], links, interface)]))

    realize = node(
        "Realize",
        "GeometryNodeRealizeInstances",
        inputs=[sock("Geometry", "GEOMETRY"), sock("Selection", "BOOLEAN", default=True)],
        outputs=[sock("Geometry", "GEOMETRY")],
    )
    instance = node(
        "Instance",
        "GeometryNodeInstanceOnPoints",
        inputs=[sock("Points", "GEOMETRY"), sock("Instance", "GEOMETRY")],
        outputs=[sock("Instances", "GEOMETRY")],
    )
    write(
        "GM-GEO-013.pass.json",
        document(
            [
                tree(
                    "Main",
                    nodes + [realize],
                    [link("Group Input", "Socket_0", "Realize", "Geometry"), link("Realize", "Geometry", "Group Output", "Socket_1")],
                    interface,
                )
            ]
        ),
    )
    write(
        "GM-GEO-013.fail.json",
        document(
            [
                tree(
                    "Main",
                    nodes + [realize, instance],
                    [
                        link("Group Input", "Socket_0", "Realize", "Geometry"),
                        link("Realize", "Geometry", "Instance", "Points"),
                        link("Group Input", "Socket_0", "Instance", "Instance"),
                        link("Instance", "Instances", "Group Output", "Socket_1"),
                    ],
                    interface,
                )
            ]
        ),
    )
    write("GM-PERF-002.pass.json", document([tree("Main", nodes + [realize], [link("Group Input", "Socket_0", "Realize", "Geometry"), link("Realize", "Geometry", "Group Output", "Socket_1")], interface)]))
    realize_b = node(
        "Realize B",
        "GeometryNodeRealizeInstances",
        inputs=[sock("Geometry", "GEOMETRY"), sock("Selection", "BOOLEAN", default=True)],
        outputs=[sock("Geometry", "GEOMETRY")],
    )
    join = node("Join", "GeometryNodeJoinGeometry", inputs=[sock("Geometry", "GEOMETRY")], outputs=[sock("Geometry", "GEOMETRY")])
    write(
        "GM-PERF-002.fail.json",
        document(
            [
                tree(
                    "Main",
                    nodes + [realize, realize_b, join],
                    [
                        link("Group Input", "Socket_0", "Realize", "Geometry"),
                        link("Group Input", "Socket_0", "Realize B", "Geometry"),
                        link("Realize", "Geometry", "Join", "Geometry"),
                        link("Realize B", "Geometry", "Join", "Geometry"),
                        link("Join", "Geometry", "Group Output", "Socket_1"),
                    ],
                    interface,
                )
            ]
        ),
    )

    write(
        "GM-PERF-003.pass.json",
        document([tree("Main", nodes + [points(10)], [link("Points", "Geometry", "Group Output", "Socket_1")], interface)]),
    )
    write(
        "GM-PERF-003.fail.json",
        document([tree("Main", nodes + [points(1_000_000)], [link("Points", "Geometry", "Group Output", "Socket_1")], interface)]),
    )
    mystery = node("Mystery", "GeometryNodeMeshGrid", inputs=[], outputs=[sock("UV Map", "VECTOR")])
    unknown_points = node(
        "Points",
        "GeometryNodePoints",
        inputs=[sock("Count", "INT")],
        outputs=[sock("Geometry", "GEOMETRY")],
    )
    write(
        "GM-PERF-003.unknown.json",
        document(
            [
                tree(
                    "Main",
                    nodes + [mystery, unknown_points],
                    [link("Mystery", "UV Map", "Points", "Count"), link("Points", "Geometry", "Group Output", "Socket_1")],
                    interface,
                )
            ]
        ),
    )
    (ROOT / "GM-PERF-003.pass.toml").write_text("[budgets]\nmax_points = 1000\n")
    (ROOT / "GM-PERF-003.fail.toml").write_text("[budgets]\nmax_points = 100\n")
    (ROOT / "GM-PERF-003.unknown.toml").write_text("[budgets]\nmax_points = 100\n")

    write("GM-PERF-004.pass.json", base)
    chain = []
    for index in range(10):
        name = f"G{index}"
        body = []
        if index < 9:
            body.append(node("Call", "GeometryNodeGroup", group_tree=f"G{index + 1}"))
        chain.append(tree(name, body, [], group=index > 0))
    write("GM-PERF-004.fail.json", document(chain, root="G0"))

    used = [
        iface("Socket_0", "Geometry", "INPUT", "NodeSocketGeometry"),
        iface("Socket_1", "Geometry", "OUTPUT", "NodeSocketGeometry"),
    ]
    write("GM-PERF-005.pass.json", document([tree("Main", nodes, links, used)]))
    unused = used + [iface("Socket_2", "Seed", "INPUT", "NodeSocketInt", default=1)]
    group_in_seed = node(
        "Group Input",
        "NodeGroupInput",
        outputs=[sock("Socket_0", "GEOMETRY"), sock("Socket_2", "INT", default=1)],
    )
    write(
        "GM-PERF-005.fail.json",
        document([tree("Main", [group_in_seed, nodes[1]], links, unused)]),
    )
    print(f"wrote {len(list(ROOT.glob('*.json')))} fixtures")


if __name__ == "__main__":
    main()
