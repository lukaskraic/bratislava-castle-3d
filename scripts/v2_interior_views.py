"""Interior review renders for the V2 interior.  CASTLE_TAG=interior Blender -b out/interior/castle.blend -P scripts/v2_interior_views.py -- [names]"""
import bpy
import json
import os
import sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = os.environ.get('CASTLE_TAG', 'interior')
OUT = os.path.join(ROOT, 'out', TAG, 'renders')
os.makedirs(OUT, exist_ok=True)
nav = json.load(open(os.path.join(ROOT, 'out', TAG, 'probes.json'))).get('nav', {})
mh = nav.get('music_hall', [-30, 0])
sc_, st_ = nav.get('south_room_cam', [-3.5, -31.0]), nav.get('south_room_tgt', [8, -33.5])
VIEWS = {
    'knights_hall': ((-1.0, -32.5, 1.65), (22, -34.5, 2.6), 16),
    'state_room': ((sc_[0], sc_[1], 7.25), (st_[0], st_[1], 7.6), 16),
    'exhibit_2f': ((sc_[0], sc_[1], 12.85), (st_[0], st_[1], 12.9), 16),
    'gallery_3f': ((sc_[0], sc_[1], 18.25), (st_[0], st_[1], 18.6), 16),
    'music_hall': ((mh[0] - 1.5, mh[1] - 3.2, 7.4), (mh[0] + 0.8, mh[1] + 4.0, 8.2), 15),
    'music_chairs': ((mh[0] + 2.4, mh[1] - 3.6, 6.9), (mh[0] - 0.2, mh[1] - 1.6, 6.1), 22),
    'music_wall': ((mh[0] + 1.0, mh[1] - 2.5, 7.3), (mh[0] - 4.0, mh[1] - 0.5, 7.6), 22),
    'entrance': ((-6.2, -40.5, 1.7), (-6.0, -26, 3.0), 16),
    'treasury': ((-40.6, -27.6, 1.65), (-43.2, -30.2, 1.1), 18),
    'cellar': ((-5.0, -31.6, -2.7), (-17.0, -30.2, -0.6), 16),
    'cellar_open': ((-8.5, -32.4, -2.9), (-15.5, -30.2, 0.2), 18),
    'balustrade': ((-29.0, 13.0, 7.4), (-32.5, 14.6, 6.4), 22),
    'cellar_far': ((-12.0, -30.9, -2.85), (6.0, -30.5, -2.6), 18),
    'stairs_well': ((-29.5, 14.2, 1.6), (-35.0, 15.3, 9.0), 14),
    'stairs_up': ((-30.0, 12.6, 7.3), (-37.0, 13.3, 10.5), 15),
}
dr = nav.get('dark_room', [0, 0, 13, 1, 1, 13])
ct = nav.get('crown_top', [0, 0, 24, 1, 1, 24])
cc = nav.get('crown_center', [-42, -29])
VIEWS.update({
    'dark_hall': (tuple(dr[:3]), tuple(dr[3:]), 16),
    'crown_top': (tuple(ct[:3]), tuple(ct[3:]), 16),
    'treasury_dark': ((cc[0] + 3.0, cc[1] - 2.6, 1.6), (cc[0], cc[1], 1.2), 20),
    'armour': (tuple(nav.get('armour_cam', [0, 0, 1.6, 1, 1, 1.4])[:3]), tuple(nav.get('armour_cam', [0, 0, 1.6, 1, 1, 1.4])[3:]), 30),
    'passage_portal': (tuple(nav.get('passage_portal', [0, 0, 1.6, 1, 1, 1.6])[:3]), tuple(nav.get('passage_portal', [0, 0, 1.6, 1, 1, 1.6])[3:]), 16),
    'crown_case': ((cc[0] + 1.1, cc[1] - 0.9, 1.5), (cc[0], cc[1], 1.15), 35),
})
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 960, 540
cam = sc.camera
for nm in (ARGS or list(VIEWS)):
    loc, tgt, lens = VIEWS[nm]
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    sc.render.filepath = os.path.join(OUT, nm + '.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', nm)
