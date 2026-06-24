import asyncio
import json

HOST = '127.0.0.1'
PORT = 9876

async def send(tool, params={}):
    reader, writer = await asyncio.open_connection(HOST, PORT, limit=16*1024*1024)
    req = json.dumps({'id': 'phase_4_run', 'tool': tool, 'params': params}) + '\n'
    writer.write(req.encode())
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=120.0)
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass
    return json.loads(line)

async def main():
    print("=== STARTING FASE 4 (FIXED) ===")
    
    # Python script to model the crane, parent objects correctly, and write keyframe animations
    crane_script = """
import bpy
import bmesh
import math
from mathutils import Vector

# Helper to set origin
def set_obj_origin(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

# 1. SETUP CRANE MATERIAL
def get_or_create_material(name, hex_color, metallic=0.0, roughness=0.8):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        hex_val = hex_color.lstrip('#')
        rgba = [int(hex_val[i:i+2], 16)/255.0 for i in (0, 2, 4)] + [1.0]
        bsdf.inputs['Base Color'].default_value = rgba
        bsdf.inputs['Metallic'].default_value = metallic
        bsdf.inputs['Roughness'].default_value = roughness
        mat.diffuse_color = rgba
    return mat

crane_yellow = get_or_create_material("Crane_Yellow", "#d49e1e", metallic=0.4, roughness=0.4)
crane_grey = get_or_create_material("Crane_Grey", "#3a3b3c", metallic=0.8, roughness=0.3)
cable_black = get_or_create_material("Crane_Cable", "#050505", metallic=0.0, roughness=0.9)

# Delete existing crane objects if any to avoid duplicates
for obj in list(bpy.data.objects):
    if "Port_Crane_" in obj.name:
        bpy.data.objects.remove(obj, do_unlink=True)

# 2. CREATE GANTRY ROOT (Empty placed at 0,0,0)
gantry = bpy.data.objects.new("Port_Crane_Gantry", None)
gantry.location = (0.0, 0.0, 0.0)
bpy.context.scene.collection.objects.link(gantry)

# 3. CREATE CRANE PARTS
# Legs (4 towers)
legs = []
leg_coords = [
    (-3.5, -18.5), (3.5, -18.5), # front legs
    (-3.5, -35.5), (3.5, -35.5)  # back legs
]
for idx, (lx, ly) in enumerate(leg_coords):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    leg = bpy.context.object
    leg.name = f"Port_Crane_Leg_{idx+1}"
    leg.scale = (1.5, 1.5, 38.0)
    leg.location = (lx, ly, 21.0) # Z from 2.0 to 40.0. Center Z = 21.0
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    set_obj_origin(leg)
    leg.data.materials.append(crane_yellow)
    leg.parent = gantry
    legs.append(leg)
    
    # Wheel bogie
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    bogie = bpy.context.object
    bogie.name = f"Port_Crane_Bogie_{idx+1}"
    bogie.scale = (3.5, 2.5, 1.5)
    bogie.location = (lx, ly, 1.25) # Z from 0.5 to 2.0
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bogie.data.materials.append(crane_grey)
    bogie.parent = gantry

# Horizontal Boom
bpy.ops.mesh.primitive_cube_add(size=1.0)
boom = bpy.context.object
boom.name = "Port_Crane_Boom"
boom.scale = (4.0, 62.0, 3.0)
boom.location = (0.0, -27.0, 40.0)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
set_obj_origin(boom)
boom.data.materials.append(crane_yellow)
boom.parent = gantry

# A-Frame Peak (Towers on top)
bpy.ops.mesh.primitive_cube_add(size=1.0)
apeak = bpy.context.object
apeak.name = "Port_Crane_AFrame"
apeak.scale = (4.0, 4.0, 12.0)
apeak.location = (0.0, -27.0, 47.5) # Z from 41.5 to 53.5
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
set_obj_origin(apeak)
apeak.data.materials.append(crane_yellow)
apeak.parent = gantry

# Trolley (parented to gantry)
bpy.ops.mesh.primitive_cube_add(size=1.0)
trolley = bpy.context.object
trolley.name = "Port_Crane_Trolley"
trolley.scale = (3.0, 4.0, 1.0)
trolley.parent = gantry
trolley.location = (0.0, -27.0, 38.0) # local location
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
set_obj_origin(trolley)
trolley.data.materials.append(crane_grey)

# Spreader (parented to trolley)
bpy.ops.mesh.primitive_cube_add(size=1.0)
spreader = bpy.context.object
spreader.name = "Port_Crane_Spreader"
spreader.scale = (6.06, 2.44, 0.5)
spreader.parent = trolley
spreader.location = (0.0, 0.0, -1.0) # local location (World Z = 37)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
set_obj_origin(spreader)
spreader.data.materials.append(crane_yellow)

# Cables (4 cylinders stretching dynamically between trolley and spreader)
cables = []
cable_offsets = [
    (-2.5, -1.0), (2.5, -1.0),
    (-2.5, 1.0), (2.5, 1.0)
]
for idx, (cx, cy) in enumerate(cable_offsets):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=1.0)
    cab = bpy.context.object
    cab.name = f"Port_Crane_Cable_{idx+1}"
    cab.parent = trolley
    cab.location = (cx, cy, -0.5)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    set_obj_origin(cab)
    cab.data.materials.append(cable_black)
    cables.append((cab, cx, cy))

# 4. ANIMATION DATA GENERATION
gantry.animation_data_create()
trolley.animation_data_create()
spreader.animation_data_create()

container_to_move = bpy.data.objects.get("Port_StorageContainer_06")
if container_to_move:
    container_to_move.animation_data_create()

# Keyframes
keyframes_gantry = [
    (1, 0.0),
    (40, -46.0),
    (60, -46.0),
    (80, -46.0),
    (140, 8.0),
    (160, 8.0),
    (180, 8.0),
    (220, 0.0)
]

keyframes_trolley = [
    (1, -27.0),
    (40, -32.0),
    (60, -32.0),
    (80, -32.0),
    (140, 6.0),
    (160, 6.0),
    (180, 6.0),
    (220, -27.0)
]

# Spreader local Z location (relative to trolley Z = 38.0)
keyframes_spreader = [
    (1, -1.0),     # World Z = 37.0
    (40, -1.0),    # World Z = 37.0
    (60, -30.57),  # World Z = 7.43
    (80, -13.0),   # World Z = 25.0
    (140, -13.0),  # World Z = 25.0
    (160, -24.92), # World Z = 13.08
    (180, -1.0),   # World Z = 37.0
    (220, -1.0)    # World Z = 37.0
]

# Set keyframes
for frame, x in keyframes_gantry:
    gantry.location.x = x
    gantry.keyframe_insert(data_path="location", index=0, frame=frame)

for frame, y in keyframes_trolley:
    trolley.location.y = y
    trolley.keyframe_insert(data_path="location", index=1, frame=frame)

for frame, z_rel in keyframes_spreader:
    spreader.location.z = z_rel
    spreader.keyframe_insert(data_path="location", index=2, frame=frame)

# Animate Cables (scale and local location)
for cab, cx, cy in cables:
    cab.animation_data_create()
    for frame, z_rel in keyframes_spreader:
        length = abs(z_rel) - 0.25
        cab.scale = (1.0, 1.0, length)
        cab.location = (cx, cy, z_rel / 2)
        cab.keyframe_insert(data_path="scale", index=2, frame=frame)
        cab.keyframe_insert(data_path="location", index=2, frame=frame)

# Animate Cargo Container (Port_StorageContainer_06)
if container_to_move:
    keyframes_container = [
        (1, -46.0, -32.0, 5.885),
        (60, -46.0, -32.0, 5.885),
        (80, -46.0, -32.0, 23.705),
        (140, 8.0, 6.0, 23.705),
        (160, 8.0, 6.0, 11.785),
        (220, 8.0, 6.0, 11.785)
    ]
    for frame, cx, cy, cz in keyframes_container:
        container_to_move.location = (cx, cy, cz)
        container_to_move.keyframe_insert(data_path="location", frame=frame)

# Set scene frame range
bpy.context.scene.frame_start = 1
bpy.context.scene.frame_end = 220
bpy.context.scene.frame_current = 1
"""
    res_crane = await send("execute_python", {"code": crane_script})
    if not res_crane.get("success"):
        print("Failed to dispatch command:", res_crane)
        return
    
    result = res_crane["result"]
    if result.get("errors"):
        print("PYTHON EXECUTION ERROR inside Blender:")
        print(result["errors"])
        print(result.get("traceback", ""))
        return
    
    print("Crane and animation generated successfully.")

    # 5. VERIFY KEYFRAMES
    print("Verifying animation positions at keyframes...")
    frames_to_check = [1, 60, 140, 160]
    for frame in frames_to_check:
        print(f"\n--- Checking Frame {frame} ---")
        frame_script = f"""
import bpy
bpy.context.scene.frame_set({frame})
gantry = bpy.data.objects.get("Port_Crane_Gantry")
trolley = bpy.data.objects.get("Port_Crane_Trolley")
spreader = bpy.data.objects.get("Port_Crane_Spreader")
container = bpy.data.objects.get("Port_StorageContainer_06")

import json
res = {{
    "gantry_world_loc": list(gantry.matrix_world.translation) if gantry else None,
    "trolley_world_loc": list(trolley.matrix_world.translation) if trolley else None,
    "spreader_world_loc": list(spreader.matrix_world.translation) if spreader else None,
    "container_world_loc": list(container.matrix_world.translation) if container else None
}}
print(json.dumps(res))
"""
        res_frame = await send("execute_python", {"code": frame_script})
        if res_frame.get("success"):
            stdout = res_frame["result"]["stdout"].strip()
            try:
                coords = json.loads(stdout.splitlines()[-1])
                print(f"Gantry World Location: {coords['gantry_world_loc']}")
                print(f"Trolley World Location: {coords['trolley_world_loc']}")
                print(f"Spreader World Location: {coords['spreader_world_loc']}")
                print(f"Container World Location: {coords['container_world_loc']}")
            except Exception as e:
                print("Failed to parse coordinates from stdout:", stdout, e)
        else:
            print("Failed to set frame:", res_frame)
            
    print("=== FASE 4 COMPLETED ===")

if __name__ == '__main__':
    asyncio.run(main())
