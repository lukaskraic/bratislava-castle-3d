"""Render preview views of out/castle.blend.  Blender -b out/castle.blend -P scripts/render_views.py -- [names]"""
import bpy
import math
import os
import sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'out', 'renders')
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []

VIEWS = {
    # name: (camera location, look-at, lens)
    'aerial_sw': ((-170, -150, 110), (0, 0, 10), 30),
    'aerial_ne': ((160, 170, 120), (0, 0, 5), 30),
    'south_facade': ((10, -120, 8), (0, -30, 14), 28),
    'west_gate': ((-75, 5, 1.7), (-40, 3, 8), 24),
    'courtyard': ((-12, -15, 1.7), (25, 5, 10), 18),
    'interior_corridor': (None, None, 18),
    'interior_room': (None, None, 18),
    'stairs': (None, None, 16),
    'garden': ((40, 120, 3), (20, 40, 8), 24),
    'match_ref3': ((-38, -78, 1.7), (-8, -38, 16), 20),
    'match_ref9': ((28, 78, 1.7), (2, 10, 14), 26),
    'match_ref6': ((95, -95, -22), (20, -30, 20), 45),
    'garden_top': ((40.5, 94.0, 170), (40.5, 94.01, 0), 40),
    'garden_eye': ((40, 60, 1.7), (42, 130, 2), 22),
    'broderie': ((14, 28, 3.2), (24, 44, -1), 28),
    'statue': ((-13.5, -79.5, 0), (-7.6, -70.0, 0), 30),
    'landmarks': ((-60, 30, 45), (330, -330, -20), 30),
    'honor_court': ((-14, -98, 1.8), (-5, -40, 14), 22),
}


def look(cam, loc, tgt):
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


def interior_points():
    import json
    pf = os.path.join(ROOT, 'out', 'probes.json')
    if os.path.exists(pf):
        return {k: tuple(map(tuple, v)) for k, v in json.load(open(pf)).items()}
    pts = {
        'interior_corridor': ((-27.3, 6.0, 7.25), (-29.5, -14.0, 7.0)),
        'interior_room': ((-10.0, -31.0, 7.25), (8.0, -33.0, 7.6)),
    }
    rp = bpy.data.objects.get('Palace_StairRamps-colonly')
    if rp:
        bb = [rp.matrix_world @ Vector(c) for c in rp.bound_box]
        c = sum(bb, Vector()) / 8
        lo = min(v.z for v in bb)
        pts['stairs'] = ((c.x + 4.5, c.y + 1.0, lo + 1.7), (c.x - 2.0, c.y - 1.0, lo + 4.0))
    return pts


def ground(loc):
    """Eye height above whatever surface is below (terrain, paving, stairs)."""
    fol = [o for o in bpy.data.objects if o.name.startswith('Trees_Foliage')]
    for o in fol:
        o.hide_viewport = True
    dg = bpy.context.evaluated_depsgraph_get()
    hit, p, *_ = bpy.context.scene.ray_cast(dg, Vector((loc[0], loc[1], 200)), Vector((0, 0, -1)))
    for o in fol:
        o.hide_viewport = False
    return (loc[0], loc[1], (p.z if hit else 0) + 1.7)


def main():
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.render.resolution_percentage = 100
    try:
        sc.eevee.taa_render_samples = 16
    except Exception:
        pass
    cam = sc.camera
    names = ARGS or list(VIEWS)
    ip = interior_points()
    for nm in names:
        loc, tgt, lens = VIEWS[nm]
        if loc is None:
            if nm not in ip:
                continue
            loc, tgt = ip[nm]
        cam.data.lens = lens
        if nm.startswith('match_') or nm in ('honor_court', 'west_gate', 'garden', 'south_facade', 'garden_eye', 'broderie', 'statue'):
            loc = ground(loc)
        if nm == 'statue':
            tgt = (tgt[0], tgt[1], loc[2] + 3.0)
        look(cam, loc, tgt)
        sc.render.filepath = os.path.join(OUT, nm + '.png')
        bpy.ops.render.render(write_still=True)
        print('rendered', nm)


main()
