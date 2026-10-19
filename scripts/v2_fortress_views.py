"""Fortress preview renders.  CASTLE_TAG=fortress Blender -b out/fortress/castle.blend -P scripts/v2_fortress_views.py -- [names]"""
import bpy
import os
import sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'out', os.environ.get('CASTLE_TAG', 'fortress'), 'renders')
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []

# name: (camera xy, camera z or None = eye height above ground, look-at xyz, lens)
VIEWS = {
    'f_vienna': ((-129, -16), None, (-120, -31, -2.5), 24),
    'f_vienna_in': ((-109, -44), -4.5, (-120, -31, -2.5), 24),
    'f_leopold': ((-68, -104), None, (-49, -111, -5.5), 24),
    'f_leopold_exit': ((-14, -107), None, (-27, -112, -8), 24),
    'f_bastion': ((-30, -72), 14, (-36, -118, -6), 24),
    'f_bastion_s': ((-45, -178), None, (-35, -110, -6), 26),
    'f_sigismund': ((168, -127), None, (142, -123, -18), 24),
    'f_nicholas': ((162, 119), None, (138, 113, -8), 24),
    'f_riding': ((45, 95), 1.5, (0, 60, 5), 24),
    'f_riding_low': ((30, 74), None, (4, 52, 8), 22),
    'f_terr_s': ((44, 104), None, (34, 66, 0.0), 24),
    'f_terr_n': ((24, 58), None, (44, 100, -3.0), 24),
    'f_terr_air': ((75, 40), 26, (38, 86, -4), 28),
    'f_terr_wall': ((56, 93), None, (40, 82, -3.0), 24),
    'f_apse': ((40, 112), None, (46, 160, -3.5), 24),
    'f_fountain': ((36, 112), None, (43, 123, -4.0), 26),
    'f_sterr': ((5, -160), 25, (2, -95, -6), 30),
    'f_sterr_low': ((-5, -108), None, (0, -88, -4), 24),
    'ge_aerial_s': ((0, -260), 120, (0, 0, 15), 30),
    'f_westcourt': ((-140, -60), 60, (-75, 10, -3), 30),
    'f_wc_in': ((-72, -20), None, (-80, 30, 2), 24),
    'ge_aerial_sw': ((-190, -170), 110, (0, 0, 15), 30),
    'f_slope_se': ((95, -185), 30, (60, -115, -18), 30),
    'f_paths_w': ((-150, -120), 45, (-80, -60, -8), 30),
    'ge_aerial_n': ((20, 280), 120, (20, 40, 5), 30),
    'ge_aerial_ne': ((190, 200), 110, (10, 10, 10), 30),
    'ge_aerial_nw': ((-190, 190), 110, (10, 20, 10), 30),
    'f_wedge': ((-6, 128), 4, (14, 110, -4), 26),
    'ge_aerial_e': ((260, -10), 100, (0, 0, 10), 30),
    'f_ruins': ((90, -60), 18, (70, -22, -2), 30),
    'f_epark': ((55, -75), 35, (55, -12, -2), 30),
    'f_court_top': ((0, -130), 60, (0, -62, -2), 30),
    'f_court_eye': ((-20, -84), None, (5, -50, 2), 24),
    'f_wc_arc': ((-62, -10), None, (-90, 5, -0.5), 26),
    'f_epath': ((80, 20), 12, (60, 10, -4), 28),
    'f_riding_n': ((8, 100), 2.0, (-2, 82, 3), 26),
    'f_house_s': ((25, -150), 8, (22, -122, -8), 30),
    'f_dormer': ((-75, 5), 6, (-96, 12, 9), 24),
    'f_court_edge': ((22, -70), None, (34, -86, -4), 24),
    'f_nich_mouth': ((121, 106), None, (133, 114, -6), 24),
    'f_lamps': ((58, -40), None, (72, 5, -1), 24),
    'f_ivy': ((70, -150), None, (50, -122, -14), 26),
    'f_flag': ((-112, -62), None, (-136, -43, 6), 24),
    'f_zstairs': ((278, -66), None, (245, -84, -38), 26),
    'f_dubcek': ((-124, -22), None, (-140, -44, -6), 26),
    'f_bench': ((50, -38), None, (66, -10, 0.5), 24),
    'f_vgate': ((44, -62), None, (30, -59, 2), 26),
    'f_vgate_w': ((-50, -53), None, (-30, -52, 2), 26),
    'f_passage': ((-62, -107), None, (-40, -111.5, -8), 26),
    'f_lawnfence': ((22, 44), None, (14, 30, 0), 26),
    'f_court_s': ((-8, -84), None, (-6, -45, 6), 22),
    'gs_vienna_gate': ((-154.9, -48.8), 20, (-119.9, -18.8, -6), 30),
    'gs_zamocke_schody': ((228.5, 50.7), -17, (258.5, 25.7, -45), 30),
    'e_vienna': ((-134, -42), None, (-120, -31, -3), 26),
    'e_sig_down': ((152, -124), None, (185, -114, -32), 26),
    'e_zstairs': ((233, -86), None, (262, -80, -44), 26),
    'e_nich_out': ((152, 118), None, (138, 114, -7), 26),
    'f_north': ((70, 222), None, (65, 174, -2), 26),
    'f_garden_n': ((22, 112), None, (62, 170, 5), 22),
    'f_ref15': ((-250, 60), 140, (30, 90, 0), 30),
    'f_ref16': ((-190, 170), 115, (-10, -10, 0), 30),
    'f_luginsland': ((180, 110), None, (150, 134, -3), 24),
    'f_house': ((42, -100), None, (20, -121, -12), 24),
    'f_aerial': ((-90, -220), 90, (0, -80, -10), 28),
    'f_aerial_n': ((60, 330), 160, (40, 60, -10), 28),
}


def ground(x, y):
    hide = [o for o in bpy.data.objects if o.name.startswith('Trees_Foliage')]
    for o in hide:
        o.hide_viewport = True
    dg = bpy.context.evaluated_depsgraph_get()
    hit, p, *_ = bpy.context.scene.ray_cast(dg, Vector((x, y, 200)), Vector((0, 0, -1)))
    for o in hide:
        o.hide_viewport = False
    return p.z if hit else 0.0


def main():
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.render.resolution_percentage = 100
    try:
        sc.eevee.taa_render_samples = 16
    except Exception:
        pass
    cam = sc.camera
    if not os.environ.get('FORT_TREES'):      # trees hide the masonry in most views
        for o in bpy.data.objects:
            if o.name.startswith('Trees'):
                o.hide_render = True
    for nm in ARGS or list(VIEWS):
        (x, y), z, tgt, lens = VIEWS[nm]
        loc = Vector((x, y, ground(x, y) + 1.7 if z is None else z))
        cam.data.lens = lens
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - loc).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(OUT, nm + '.png')
        bpy.ops.render.render(write_still=True)
        print('rendered', nm, tuple(round(c, 1) for c in loc))


main()
