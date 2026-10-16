import json
import bpy

tree = bpy.data.node_groups.new("Links", "GeometryNodeTree")
math = tree.nodes.new("ShaderNodeMath")
math.operation = "DIVIDE"
setpos = tree.nodes.new("GeometryNodeSetPosition")
grid = tree.nodes.new("GeometryNodeMeshGrid")
value = tree.nodes.new("ShaderNodeValue")
value.outputs[0].default_value = 0.25

cases = {}
link = tree.links.new(math.outputs["Value"], setpos.inputs["Offset"])
cases["float_to_vector"] = {"valid": link.is_valid, "from": math.outputs["Value"].type, "to": setpos.inputs["Offset"].type}
link2 = tree.links.new(grid.outputs["Mesh"], math.inputs["Value"])
cases["geometry_to_float"] = {"valid": link2.is_valid, "from": grid.outputs["Mesh"].type, "to": math.inputs["Value"].type}
link3 = tree.links.new(value.outputs["Value"], math.inputs["Value_001"])
cases["float_to_float"] = {"valid": link3.is_valid}

# integer interface into float density
tree.interface.new_socket(name="Count", in_out="INPUT", socket_type="NodeSocketInt")
gi = tree.nodes.new("NodeGroupInput")
dist = tree.nodes.new("GeometryNodeDistributePointsOnFaces")
# group input outputs depend on interface; create a float too
tree.interface.new_socket(name="Density", in_out="INPUT", socket_type="NodeSocketFloat")
link4 = tree.links.new(gi.outputs["Count"], dist.inputs["Density"])
cases["int_to_float"] = {"valid": link4.is_valid, "from": gi.outputs["Count"].type, "to": dist.inputs["Density"].type}

print(json.dumps(cases))
