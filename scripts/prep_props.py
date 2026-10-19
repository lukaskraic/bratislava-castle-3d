"""Bake the CC0 street props (data/assets/cc0/*.glb) into static, real-scale GLBs for Godot.

Characters come rigged in a T-pose; they are frozen in an idle/walk frame, the armature is
applied and dropped. Every prop is scaled to real size, its origin set to the bottom centre
and its long axis turned to +X (cars) so the game can place them by heading.

Run: Blender -b -P scripts/prep_props.py
"""
import bpy, os, json
from mathutils import Vector, Matrix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data', 'assets', 'cc0')
DST = os.path.join(ROOT, 'godot', 'models', 'props')
os.makedirs(DST, exist_ok=True)

# target size: cars as (length, width, height) – the low-poly packs are toy-proportioned, so cars are
# scaled per axis to real European cars; people uniformly by height (m).
# business_man / casual ship without animation (T-pose) and are left out.
SIZE = {'car_a': (4.3, 1.78, 1.42), 'car_b': (4.5, 1.80, 1.45), 'car_suv': (4.6, 1.86, 1.68),
        'car_hatch': (4.0, 1.75, 1.50), 'car_wagon': (4.6, 1.80, 1.50),
        'man': 1.78, 'man_suit': 1.80, 'woman_casual': 1.66, 'woman_dress': 1.64}



def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def bake(name, pose='idle', out_name=None):
    clear()
    bpy.ops.import_scene.gltf(filepath=os.path.join(SRC, name + '.glb'))
    # the character packs carry a stray helper sphere without material
    for o in list(bpy.context.scene.objects):
        if o.type == 'MESH' and not o.data.materials:
            bpy.data.objects.remove(o, do_unlink=True)
    scene = bpy.context.scene
    arms = [o for o in scene.objects if o.type == 'ARMATURE']
    for a in arms:
        acts = sorted(bpy.data.actions, key=lambda ac: 0 if ac.name.lower().endswith('_' + pose) else 9)
        if acts:
            a.animation_data_create()
            a.animation_data.action = acts[0]
            f0, f1 = acts[0].frame_range
            scene.frame_set(int(f0 + (f1 - f0) * (0.3 if pose == 'walk' else 0.1)))
    dg = bpy.context.evaluated_depsgraph_get()
    meshes = [o for o in scene.objects if o.type == 'MESH']
    baked = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        me.transform(o.matrix_world)
        nob = bpy.data.objects.new(o.name + '_b', me)
        scene.collection.objects.link(nob)
        baked.append(nob)
    for o in list(scene.objects):
        if o not in baked:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in baked:
        o.select_set(True)
    bpy.context.view_layer.objects.active = baked[0]
    if len(baked) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    me = ob.data
    lo = Vector([min(v.co[i] for v in me.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in me.vertices) for i in range(3)])
    ext = hi - lo
    car = name.startswith('car')
    if car and ext.y > ext.x:   # long axis -> +X
        me.transform(Matrix.Rotation(-1.5707963, 4, 'Z'))
        lo = Vector([min(v.co[i] for v in me.vertices) for i in range(3)])
        hi = Vector([max(v.co[i] for v in me.vertices) for i in range(3)])
        ext = hi - lo
    c = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    if car:
        sv = Vector([SIZE[name][i] / ext[i] for i in range(3)])
    else:
        sv = Vector([SIZE[name] / ext.z] * 3)
    me.transform(Matrix.Diagonal(sv.to_4d()) @ Matrix.Translation(-c))
    out = os.path.join(DST, (out_name or name) + '.glb')
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False, export_animations=False,
                              export_skins=False, export_morph=False)
    return {'tris': sum(len(p.vertices) - 2 for p in me.polygons), 'size': [round(ext[i] * sv[i], 2) for i in range(3)]}


report = {}
for n in SIZE:
    report[n] = bake(n)
    if not n.startswith('car'):
        report[n + '_walk'] = bake(n, 'walk', n + '_walk')
print('PROPS', json.dumps(report))
