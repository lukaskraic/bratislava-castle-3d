"""Landmark check renders, framed like the reference photos in data/ref/landmarks/.
CASTLE_TAG=lm Blender -b out/lm/castle.blend -P scripts/v2_landmark_views.py -- [names]"""
import bpy, os, sys
from mathutils import Vector
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'out', os.environ.get('CASTLE_TAG', 'lm'), 'renders')
os.makedirs(OUT, exist_ok=True)
# name: (camera xyz, target xyz, lens-ish fov deg, relative) – relative: z values above the ground below
VIEWS = {
    # Most SNP side view from upstream, ~35 m above the river (snp_side_view_a.jpg)
    'lm_snp_side': ((150, -455, -30), (345, -600, -25), 55, False),
    # from Rybne nam. along the bridge axis (snp_pylon_ufo_closeup.jpg)
    'lm_snp_rybne': ((336, -78, 1.7), (331, -620, 55), 30, True),
    # pylon head and UFO close
    'lm_snp_ufo': ((250, -540, -10), (330, -622, 22), 30, False),
    # on the deck, walking south
    'lm_snp_deck': ((331, -300, -52), (331, -620, -20), 50, False),
    # under the deck on the embankment promenade
    'lm_snp_under': ((300, -305, 1.7), (345, -330, 9), 60, True),
    # Dom from the south lawn (dom_south_facade.jpg)
    'lm_dom_s': ((415, -125, -22), (362, -38, -35), 50, False),
    # Dom from the north, Rudnayovo nam. (dom_north_facade.jpg)
    'lm_dom_n': ((372, 22, 1.7), (362, -38, 22), 55, True),
    # Dom tower from Staromestska side / west
    'lm_dom_w': ((285, -75, 2.0), (337, -45, 40), 50, True),
    # Dom choir from the east (dom_east_choir.jpg)
    'lm_dom_e': ((450, -10, 1.7), (385, -35, 15), 50, True),
    'lm_dom_tower': ((265, -135, -25), (337, -45, -5), 50, False),
    'lm_dom_air': ((470, -170, 60), (365, -38, 0), 40, True),
    # Michalska gate from the south along Michalska (michalska_brana photos)
    'lm_michal_s': ((489, 245, 1.7), (494, 313, 25), 45, True),
    # Michalska gate from the north (barbican side)
    'lm_michal_n': ((500, 380, 1.7), (494, 313, 25), 45, True),
    # Old Town Hall from Hlavne nam.
    'lm_townhall': ((600, 112, 1.7), (650, 140, 26), 62, True),
    'lm_primate': ((735, 212, 1.7), (712, 180, 12), 60, True),
    'lm_snd': ((680, 0, 1.7), (744, 5, 12), 55, True),
    'lm_klarisky': ((360, 120, -30), (390, 162, -35), 55, False),
    'lm_reduta': ((700, -95, 1.7), (735, -140, 12), 60, True),
    'lm_reduta_s': ((672, -238, -46), (735, -172, -52), 55, False),
}
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(VIEWS)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 960, 540
try:
    sc.eevee.taa_render_samples = 12
except Exception:
    pass
cam = sc.camera
cam.data.clip_end = 12000


def ground(x, y):
    dg = bpy.context.evaluated_depsgraph_get()
    o = Vector((x, y, 400))
    q = None
    for _ in range(40):
        hit, q, nrm, _i, ob, _m = sc.ray_cast(dg, o, Vector((0, 0, -1)))
        if not hit:
            return 0.0
        if ob.name.startswith(('Terrain', 'Ground', 'V2City_Streets', 'V2City_StreetDetail', 'Courtyard', 'Paving', 'V2City_Quay')):
            return q.z
        o = Vector((q.x, q.y, q.z - 0.05))
    return q.z


import math
for nm in args:
    c, t, fov, rel = VIEWS[nm]
    if rel:
        c = (c[0], c[1], ground(c[0], c[1]) + c[2])
        t = (t[0], t[1], ground(c[0], c[1]) + t[2])
    cam.location = c
    cam.rotation_euler = (Vector(t) - Vector(c)).to_track_quat('-Z', 'Y').to_euler()
    cam.data.angle = math.radians(fov)
    sc.render.filepath = os.path.join(OUT, nm + '.png')
    bpy.ops.render.render(write_still=True)
    print('RENDER', nm, [round(v, 1) for v in c])
