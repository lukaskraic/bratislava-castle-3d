"""Render V2 city check views: CASTLE_TAG=city Blender -b out/city/castle.blend -P scripts/v2_city_views.py"""
import bpy, os, sys
from mathutils import Vector
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'out', os.environ.get('CASTLE_TAG', 'city'), 'renders')
os.makedirs(OUT, exist_ok=True)
VIEWS = {
    'city_oldtown': ((55, -10, 14), (520, 230, 10), 30),
    'city_danube': ((-40, -110, 12), (330, -560, 40), 28),
    'city_aerial': ((-500, -700, 420), (350, 50, 0), 30),
    'city_cathedral': ((150, -70, 25), (340, -45, 50), 35),
    'city_michael': ((455, 270, -52), (494, 313, -30), 26),
    'city_ref18': ((-430, 420, 230), (120, -200, -40), 26),
    'city_street': ((0, 0, 0), (0, 0, 0), 22),
    'city_castle_from_town': ((0, 0, 0), (0, 0, 0), 30),
    'city_cathedral_close': ((285, -120, -50), (340, -45, -10), 24),
    'city_river_top': ((300, -450, 1600), (300, -449, 0), 30),
    'city_oldtown_air': ((790, 320, 0), (655, 160, -62), 30),
    'city_sky_s': ((0, -40, 45), (500, -3000, -50), 26),
    'city_sky_e': ((0, 0, 45), (2500, 300, -20), 26),
    'city_sky_n': ((0, 0, 45), (-400, 4400, 250), 26),
    'city_aerial_e': ((-320, -260, 330), (1500, 300, -40), 22),
    'city_far_top': ((300, -500, 9000), (300, -499, 0), 40),
    'city_embankment': ((0, 0, 0), (0, 0, 0), 24),
    'city_zamocka': ((0, 0, 0), (0, 0, 0), 22),
    'eye_c2d04': ((0, 0, 0), (0, 0, 0), 24),
    'eye_c2d18': ((0, 0, 0), (0, 0, 0), 24),
    'eye_kapitulska_low': ((0, 0, 0), (0, 0, 0), 24),
    'eye_beb_down': ((0, 0, 0), (0, 0, 0), 22),
    'eye_hviezd': ((0, 0, 0), (0, 0, 0), 22),
    'eye_snd': ((0, 0, 0), (0, 0, 0), 22),
    'eye_dom': ((362, -8, -56.6), (380, -35, -46), 18),
    'eye_townhall': ((615, 128, -64), (655, 145, -52), 24),
    'eye_dom_s': ((330, -95, -55), (345, -60, -50), 22),
    'eye_zamocke_foot': ((0, 0, 0), (0, 0, 0), 20),
    'eye_palisady': ((0, 0, 0), (0, 0, 0), 20),
    'eye_mudronova': ((0, 0, 0), (0, 0, 0), 20),
    'eye_zamocka_w': ((0, 0, 0), (0, 0, 0), 20),
    'eye_beblaveho': ((0, 0, 0), (0, 0, 0), 20),
    'eye_nabrezie_castle': ((0, 0, 0), (0, 0, 0), 20),
    'eye_zizkova': ((0, 0, 0), (0, 0, 0), 20),
    'city_gate_walk': ((0, 0, 0), (0, 0, 0), 18),
    'city_fountain': ((0, 0, 0), (0, 0, 0), 22),
    'city_promenade': ((0, 0, 0), (0, 0, 0), 22),
    'city_kapitulska': ((0, 0, 0), (0, 0, 0), 22),
    'city_tower_ne': ((-43, -34, 60), (700, 300, -40), 26),
    'city_snp_side': ((-150, -560, -50), (330, -620, 0), 26),
    'city_podhradie': ((0, 0, 0), (0, 0, 0), 22),
    'city_crown_se': ((-43.2, -33.6, 24.9), (300, -380, -45), 24),
    'city_crown_sw': ((-43.2, -33.6, 24.9), (-287, -582, -60), 22),
    'city_crown_e': ((-43.2, -33.6, 24.9), (500, 60, -30), 24),
    'city_honour_danube': ((0, 0, 0), (0, 0, 0), 24),
    'city_townhall': ((0, 0, 0), (0, 0, 0), 24),
    'city_primate': ((0, 0, 0), (0, 0, 0), 24),
    'city_michalska': ((0, 0, 0), (0, 0, 0), 24),
}
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(VIEWS)
GE = {}
_gp = os.path.join(ROOT, 'data', 'ref', 'earth', 'views.json')
if os.path.exists(_gp):
    import json
    GE = json.load(open(_gp))      # Google Earth reference cameras (local metres), 45 deg vertical FOV
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 960, 540
try:
    sc.eevee.taa_render_samples = 12
except Exception:
    pass
cam = sc.camera
cam.data.clip_end = 12000
REL = {   # camera / target heights relative to the surface below (ray cast)
    'city_street': ((620, 140, 1.7), (565, 118, 5), 20),
    'city_gate_walk': ((492.5, 290, 1.7), (490, 335, 3.0), 18),
    'city_fountain': ((600, 112, 1.7), (625, 126, 3.0), 22),
    'city_promenade': ((420, -292, 1.7), (520, -290, 2.5), 22),
    'eye_palisady': ((-130, 20, 1.7), (-105, 90, 4), 20),
    'eye_mudronova': ((-205, 0, 1.7), (-190, 60, 4), 20),
    'eye_zamocka_w': ((-80, 210, 1.7), (-95, 130, 3), 20),
    'eye_beblaveho': ((210, -100, 1.7), (260, -60, 3), 20),
    'eye_nabrezie_castle': ((-60, -262, 1.7), (80, -275, 3), 20),
    'eye_zizkova': ((-330, -150, 1.7), (-200, -210, 3), 20),
    'eye_zamocke_foot': ((250, -75, 1.7), (215, -95, 3), 20),
    'eye_snd': ((690, 0, 1.7), (744, 5, 10), 22),
    'eye_hviezd': ((700, -40, 1.7), (660, -105, 5), 22),
    'eye_beb_down': ((266, -28, 1.7), (245, -70, -4), 22),
    'eye_kapitulska_low': ((300, -90, 1.7), (340, -30, 8), 24),
    'eye_c2d04': ((263.2, -139.3, 1.7), (280, -110, 2), 24),
    'eye_c2d18': ((415.8, -299.6, 1.7), (430, -330, 1.0), 24),
    'city_zamocka': ((100, 272, 1.7), (190, 252, 2.5), 22),
    'city_kapitulska': ((345, 160, 1.7), (372, 95, 4), 22),
    'city_embankment': ((140, -262, 1.7), (450, -280, 6), 24),
    'city_podhradie': ((-60, -60, 25), (200, -260, -30), 22),
    'city_honour_danube': ((5, -72, 1.7), (260, -560, -45), 22),
    'city_townhall': ((605, 108, 1.7), (650, 138, 22), 22),
    'city_primate': ((712, 215, 1.7), (688, 182, 14), 16),
    'city_michalska': ((489, 245, 1.7), (494, 313, 22), 22),
    'city_castle_from_town': ((520, -20, 3.0), (0, 0, 75), 30),
    'city_michael': ((450, 262, 6), (494, 313, 26), 24),
    'city_cathedral_close': ((270, -130, 8), (340, -45, 40), 22),
}


def snap(p):
    """Height of the walkable ground below p: skips roofs, trees and other non-ground hits."""
    dg = bpy.context.evaluated_depsgraph_get()
    o = Vector((p[0], p[1], 400))
    for _ in range(40):
        hit, q, nrm, _i, ob, _m = sc.ray_cast(dg, o, Vector((0, 0, -1)))
        if not hit:
            return (p[0], p[1], p[2])
        if ob.name.startswith(('Terrain', 'Ground', 'V2City_Streets', 'V2City_StreetDetail', 'Courtyard', 'Paving')):
            return (p[0], p[1], q.z + p[2])
        o = Vector((q.x, q.y, q.z - 0.05))
    return (p[0], p[1], q.z + p[2])


for nm in args:
    if nm in GE:
        cam.location = GE[nm]['cam']
        cam.rotation_euler = (Vector(GE[nm]['tgt']) - Vector(GE[nm]['cam'])).to_track_quat('-Z', 'Y').to_euler()
        cam.data.sensor_fit = 'VERTICAL'
        cam.data.angle_y = 0.7854
        sc.render.filepath = os.path.join(OUT, nm + '.png')
        bpy.ops.render.render(write_still=True)
        cam.data.sensor_fit = 'AUTO'
        print('rendered', nm)
        continue
    loc, tgt, lens = VIEWS[nm]
    if nm in REL:
        l2, t2, lens = REL[nm]
        g = snap((l2[0], l2[1], 0))[2]
        loc = (l2[0], l2[1], g + l2[2])
        tgt = (t2[0], t2[1], g + t2[2])
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    sc.render.filepath = os.path.join(OUT, nm + '.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', nm)
