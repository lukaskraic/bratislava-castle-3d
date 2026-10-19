"""Main-thread V2 check views: CASTLE_TAG=main Blender -b out/main/castle.blend -P scripts/v2_main_views.py -- names"""
import bpy, os, sys
from mathutils import Vector
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'out', os.environ.get('CASTLE_TAG', 'main'), 'renders')
os.makedirs(OUT, exist_ok=True)
VIEWS = {
    'risalit': ((-4, -70, 3.0), (-6, -38, 9), 32),
    'east_facade': ((95, -10, 2.0), (40, -12, 10), 26),
    'west_facade': ((-95, 5, 0.0), (-42, 0, 8), 26),
    'tower_crown': ((-75, -70, 10), (-44, -31, 36), 40),
    'tower_ne': ((75, 55, 15), (45, 17, 35), 40),
}
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 960, 540
cam = sc.camera
for nm in (sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else VIEWS):
    loc, tgt, lens = VIEWS[nm]
    dg = bpy.context.evaluated_depsgraph_get()
    hit, p, *_ = sc.ray_cast(dg, Vector((loc[0], loc[1], 200)), Vector((0, 0, -1)))
    loc = (loc[0], loc[1], (p.z if hit else 0) + 1.7 + loc[2])
    cam.data.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, nm + '.png')
    bpy.ops.render.render(write_still=True)
