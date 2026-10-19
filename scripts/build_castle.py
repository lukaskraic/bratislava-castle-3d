"""Bratislava Castle generator for Blender 5.x.

Run:  Blender -b -P scripts/build_castle.py -- [--no-export] [--fast]

Data sources (see README.md):
  data/castle_local.json  OSM features in local metres (origin = palace centroid)
  data/dmr128.json        ZBGIS DMR 5.0 terrain elevations (m a.s.l.)
  data/ortho4k.jpg        ZBGIS orthophoto, same bbox as the DMR grid
Axes: +X east, +Y north, +Z up. Z = 0 is the palace courtyard / ground-floor level.
"""
import bpy
import bmesh
import json
import math
import os
import random
import sys
from mathutils import Vector, geometry

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import textures  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
FAST = '--fast' in ARGS
WEB = '--web' in ARGS          # lighter build for the browser (Godot web export, WebGL 2)
DATA = os.path.join(ROOT, 'data')
# --tag NAME writes everything to out/NAME/ so parallel workers don't overwrite each other
TAG = ARGS[ARGS.index('--tag') + 1] if '--tag' in ARGS else ''
OUT = os.path.join(ROOT, 'out', TAG) if TAG else os.path.join(ROOT, 'out')
TEX = os.path.join(OUT, 'textures_web' if WEB else 'textures')
os.makedirs(OUT, exist_ok=True)

LAT0, LON0 = 48.142319, 17.1001165
EARTH_R = 6378137.0
random.seed(42)

# ---------------------------------------------------------------- palace params
# Heights (m above courtyard). Sources: SNM brochure (4 storeys + basement),
# reconstruction report (23 m walls W/S wings), Crown Tower 47 m measured from the
# foot of the SW slope (~6 m below courtyard) -> apex ~ +41 m is too tall vs photos of
# the roof line, so we use the visual proportion from photographs (estimate).
FLOOR_Z = [0.0, 5.6, 11.2, 16.6]          # finished floor levels: ground, 1st, 2nd, 3rd
EAVE_Z = 23.0
RIDGE_Z = 31.5   # roof reads lower than the towers in Google Earth
SLAB_T = 0.45
OUTER_T = 1.8                              # outer wall thickness (medieval core is thicker)
COURT_T = 1.1
PART_T = 0.45
CORR_W = 3.6                               # corridor width (inside, courtyard side)
AXIS_SPACING = 5.4                         # window axis spacing (photo ref3: ~11-12 axes per long facade)
# SPEC: small towers one storey above the eaves + steep (~60 deg) spire; Crown Tower two storeys + low tent roof
SMALL_TOWER = dict(shaft_top=30.0, ped_h=2.1, drum_top=35.5, apex=42.5)
CROWN_TOWER = dict(shaft_top=36.4, ped_h=2.4, drum_top=42.6, apex=48.6)   # drum clears the gables (photos 04, 14)

# outer outline lines from OSM way 8160490 / wing parts; inner = courtyard way 1473406795
LINES = {
    'W': ((-47.13, -26.38), (-37.09, 31.83)),
    'N': ((-35.71, 39.64), (16.10, 26.69)),
    'E': ((35.44, -33.44), (47.00, 11.33)),
    'S': ((-38.47, -35.07), (26.61, -39.24)),
}
COURT = [(-28.16, -22.44), (25.21, -26.18), (31.48, 6.65), (-20.75, 20.33)]   # SW, SE, NE, NW (CCW)


def to_local(lat, lon):
    x = math.radians(lon - LON0) * EARTH_R * math.cos(math.radians(LAT0))
    y = math.radians(lat - LAT0) * EARTH_R
    return x, y


def line_x(l1, l2):
    p = geometry.intersect_line_line_2d  # segment-only; do infinite manually
    (x1, y1), (x2, y2) = l1
    (x3, y3), (x4, y4) = l2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
    return Vector((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))


OUTER = [line_x(LINES['W'], LINES['S']), line_x(LINES['S'], LINES['E']),
         line_x(LINES['E'], LINES['N']), line_x(LINES['N'], LINES['W'])]   # SW, SE, NE, NW
INNER = [Vector(p) for p in COURT]
WING_NAMES = ['S', 'E', 'N', 'W']          # wing i lies between OUTER[i]->OUTER[i+1]


# ---------------------------------------------------------------- mesh builder
class MB:
    """Accumulates polygons with per-face material slot and world-projected UVs."""

    def __init__(self, name):
        self.name = name
        self.verts, self.faces, self.mats, self.uvs = [], [], [], []
        self.slots = []

    def slot(self, mat):
        if mat not in self.slots:
            self.slots.append(mat)
        return self.slots.index(mat)

    def poly(self, pts, mat, uv_scale=None, uv=None):
        pts = [Vector(p) for p in pts]
        if len(pts) < 3:
            return
        n = geometry.normal(pts) if len(pts) >= 3 else Vector((0, 0, 1))
        if n.length < 1e-9:
            return
        s = uv_scale or MAT_UV.get(mat, 2.0)
        if uv is None:
            uv = planar_uv(pts, n, s)
        i = len(self.verts)
        self.verts += pts
        self.faces.append(tuple(range(i, i + len(pts))))
        self.mats.append(self.slot(mat))
        self.uvs.append(uv)

    def box(self, base, z0, z1, mat, top=None, bottom=None, sides=None):
        """base: 4 2D points CCW. Optional per-face materials."""
        if z1 - z0 < 1e-4:
            return
        if poly_area(base) < 0:
            base = list(reversed(base))
        b = [Vector((p[0], p[1], z0)) for p in base]
        t = [Vector((p[0], p[1], z1)) for p in base]
        self.poly(t, top or mat)
        self.poly(list(reversed(b)), bottom or mat)
        for k in range(4):
            j = (k + 1) % 4
            self.poly([b[k], b[j], t[j], t[k]], sides or mat)

    def poly_up(self, pts, mat):
        """Single-sided horizontal-ish face guaranteed to face +Z (walkable ramps)."""
        pts = [Vector(p) for p in pts]
        if geometry.normal(pts).z < 0:
            pts.reverse()
        self.poly(pts, mat)

    def build(self, collection=None):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        uvl = me.uv_layers.new(name='UVMap')
        li = 0
        for f, uv in zip(me.polygons, self.uvs):
            for k in range(f.loop_total):
                uvl.data[f.loop_start + k].uv = uv[k]
            li += f.loop_total
        for m in self.slots:
            me.materials.append(MATS[m])
        for f, m in zip(me.polygons, self.mats):
            f.material_index = m
        me.validate()
        ob = bpy.data.objects.new(self.name, me)
        (collection or bpy.context.scene.collection).objects.link(ob)
        return ob


class ChunkMB(MB):
    """Routes faces into spatial tiles so engines can frustum/distance cull them."""

    def __init__(self, name, tile=120.0):
        super().__init__(name)
        self.tile = tile
        self.parts = {}

    def poly(self, pts, mat, uv_scale=None, uv=None):
        c = sum((Vector(p) for p in pts), Vector((0, 0, 0))) / len(pts)
        key = (math.floor(c.x / self.tile), math.floor(c.y / self.tile))
        if key not in self.parts:
            base, suf = (self.name.rsplit('-', 1) + [''])[:2]
            nm = f"{base}_{key[0]}_{key[1]}" + (f"-{suf}" if suf else '')
            self.parts[key] = MB(nm)
        self.parts[key].poly(pts, mat, uv_scale, uv)

    def build(self, collection=None):
        return [m.build(collection) for m in self.parts.values()]


def planar_uv(pts, n, s):
    if abs(n.z) > 0.7:
        return [(p.x / s, p.y / s) for p in pts]
    t = Vector((-n.y, n.x, 0)).normalized()
    return [((p.x * t.x + p.y * t.y) / s, p.z / s) for p in pts]


# cornice profiles: (projection beyond the wall face [m], height above base [m]) from wall to top
PROF_EAVE = [(0.0, 0.0), (0.06, 0.0), (0.06, 0.08), (0.14, 0.12), (0.18, 0.25), (0.26, 0.3), (0.3, 0.42),
             (0.5, 0.48), (0.62, 0.56), (0.66, 0.68), (0.72, 0.72), (0.72, 0.8), (0.0, 0.8)]
PROF_BAND = [(0.0, 0.0), (0.04, 0.02), (0.1, 0.08), (0.12, 0.16), (0.12, 0.24), (0.06, 0.28), (0.0, 0.3)]
PROF_CEIL = [(0.0, 0.0), (0.0, -0.04), (0.05, -0.08), (0.09, -0.16), (0.16, -0.2), (0.22, -0.28), (0.24, -0.34), (0.28, -0.4), (0.28, 0.0)]


def sweep(mb, a, b, prof, z, mat, outward):
    """Extrude a moulding profile along a->b on a wall face; `outward` = unit 2D normal out of the wall.
    Faces are oriented away from the profile's centroid so the moulding is closed and outward-lit."""
    a, b = Vector(a[:2]), Vector(b[:2])
    L = (b - a).length
    if L < 0.05:
        return
    d = (b - a) / L
    co = sum(o for o, h in prof) / len(prof)
    ch = sum(h for o, h in prof) / len(prof)
    P = lambda base, o, h: Vector(((base + outward * o).x, (base + outward * o).y, z + h))
    for (o0, h0), (o1, h1) in zip(prof, prof[1:]):
        quad = [P(a, o0, h0), P(b, o0, h0), P(b, o1, h1), P(a, o1, h1)]
        if (Vector((o1 - o0, h1 - h0))).length < 1e-6:
            continue
        away = Vector(((o0 + o1) / 2 - co, (h0 + h1) / 2 - ch))
        want = Vector((outward.x * away.x, outward.y * away.x, away.y))
        if geometry.normal(quad).dot(want) < 0:
            quad.reverse()
        mb.poly(quad, mat)
    for end, sgn in ((a, -1), (b, 1)):       # end caps
        cap = [P(end, o, h) for o, h in prof]
        if geometry.normal(cap).to_2d().dot(d * sgn) < 0:
            cap.reverse()
        mb.poly(cap, mat)


def oriented_poly(mb, pts, want, mat, **kw):
    """Emit a polygon whose normal agrees with `want` (flips the winding if needed)."""
    pts = [Vector(p) for p in pts]
    if geometry.normal(pts).dot(want) < 0:
        pts.reverse()
    mb.poly(pts, mat, **kw)


def seg_box(mb, a, b, off0, off1, z0, z1, mat, **kw):
    """Box along 2D segment a->b, spanning [off0, off1] along the left normal."""
    a, b = Vector(a[:2]), Vector(b[:2])
    d = (b - a)
    if d.length < 1e-4:
        return
    d.normalize()
    n = Vector((-d.y, d.x))
    pts = [a + n * off0, b + n * off0, b + n * off1, a + n * off1]
    if off1 < off0:
        pts = [pts[1], pts[0], pts[3], pts[2]]
    mb.box(pts, z0, z1, mat, **kw)


def wall(mb, a, b, z0, z1, t, mat, openings=(), off=0.0, mat_in=None):
    """Wall along a->b with thickness t to the LEFT (offset off..off+t).
    openings: (u0, u1, v0, v1) in metres along the wall / absolute z.
    Face material: mat on the a->b outer face, mat_in on the opposite face."""
    a, b = Vector(a[:2]), Vector(b[:2])
    L = (b - a).length
    if L < 0.05:
        return
    d = (b - a) / L
    ops = [(max(0, o[0]), min(L, o[1]), o[2], o[3]) for o in openings if o[1] > 0 and o[0] < L]
    cuts = sorted({0.0, L, *[o[0] for o in ops], *[o[1] for o in ops]})
    for ua, ub in zip(cuts, cuts[1:]):
        if ub - ua < 1e-4:
            continue
        holes = sorted((o[2], o[3]) for o in ops if o[0] <= ua + 1e-6 and o[1] >= ub - 1e-6)
        solids, z = [], z0
        for h0, h1 in holes:
            if h0 > z:
                solids.append((z, min(h0, z1)))
            z = max(z, h1)
        if z < z1:
            solids.append((z, z1))
        pa, pb = a + d * ua, a + d * ub
        for s0, s1 in solids:
            if s1 - s0 > 1e-4:
                n = Vector((-d.y, d.x))
                base = [pa + n * off, pb + n * off, pb + n * (off + t), pa + n * (off + t)]
                bb = [Vector((p.x, p.y, s0)) for p in base]
                tt = [Vector((p.x, p.y, s1)) for p in base]
                mb.poly(tt, mat)                                  # sill / head reveals: facade finish
                mb.poly(list(reversed(bb)), mat)
                mb.poly([bb[0], bb[1], tt[1], tt[0]], mat)        # outer face
                mb.poly([bb[2], bb[3], tt[3], tt[2]], mat_in or mat)  # inner face
                mb.poly([bb[1], bb[2], tt[2], tt[1]], mat)        # jamb reveals
                mb.poly([bb[3], bb[0], tt[0], tt[3]], mat)


def slab(mb, loops, z_top, thk, top, bottom, side):
    """Horizontal slab from polygon loops (first = outer, rest = holes), 2D CCW/any."""
    loops = [[Vector((p[0], p[1], 0)) for p in lp] for lp in loops if len(lp) >= 3]
    for i, lp in enumerate(loops):
        a = poly_area([(v.x, v.y) for v in lp])
        if (i == 0 and a < 0) or (i > 0 and a > 0):
            lp.reverse()
    flat = [v for lp in loops for v in lp]
    tris = geometry.tessellate_polygon([[tuple(v) for v in lp] for lp in loops])
    for tri in tris:
        p = [flat[i] for i in tri]
        if geometry.normal(p).z < 0:
            p.reverse()
        mb.poly([Vector((q.x, q.y, z_top)) for q in p], top)
        mb.poly([Vector((q.x, q.y, z_top - thk)) for q in reversed(p)], bottom)
    for lp in loops:
        for k in range(len(lp)):
            a, b = lp[k], lp[(k + 1) % len(lp)]
            mb.poly([Vector((a.x, a.y, z_top - thk)), Vector((b.x, b.y, z_top - thk)),
                     Vector((b.x, b.y, z_top)), Vector((a.x, a.y, z_top))], side)


def offset_poly(poly, dist):
    """Offset closed polygon (CCW) outward by dist (negative = inward), mitred."""
    poly = [p for i, p in enumerate(poly) if (Vector(p[:2]) - Vector(poly[i - 1][:2])).length > 1e-4]
    n = len(poly)
    lines = []
    for i in range(n):
        a, b = Vector(poly[i][:2]), Vector(poly[(i + 1) % n][:2])
        d = (b - a).normalized()
        nn = Vector((d.y, -d.x))  # right normal = outward for CCW
        lines.append(((a + nn * dist), (b + nn * dist)))
    out = []
    for i in range(n):
        (a0, b0), (a1, b1) = lines[i - 1], lines[i]
        d0, d1 = (b0 - a0), (b1 - a1)
        if abs(d0.x * d1.y - d0.y * d1.x) < 1e-6 * max(d0.length * d1.length, 1e-9):
            out.append(a1)            # collinear neighbours: plain offset point
        else:
            out.append(line_x(lines[i - 1], lines[i]))
    return out


def poly_area(p):
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def dist_to_poly(x, y, poly):
    best = 1e9
    p = Vector((x, y))
    for i in range(len(poly)):
        a, b = Vector(poly[i][:2]), Vector(poly[(i + 1) % len(poly)][:2])
        ab = b - a
        t = max(0, min(1, (p - a).dot(ab) / (ab.length_squared + 1e-12)))
        best = min(best, (a + ab * t - p).length)
    return best


# ---------------------------------------------------------------- materials
MATS = {}
MAT_UV = {}


def make_mat(name, tex=None, color=(0.8, 0.8, 0.8), rough=0.8, uv=2.0, metal=0.0,
             alpha=1.0, emit=None, spec=0.3, normal=None, nstrength=1.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = spec
    if tex is not None:
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = tex
        nt.links.new(tn.outputs['Color'], bsdf.inputs['Base Color'])
    if normal is not None:
        nn = nt.nodes.new('ShaderNodeTexImage')
        nn.image = normal
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = nstrength
        nt.links.new(nn.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    if alpha < 1:
        bsdf.inputs['Alpha'].default_value = alpha
        try:
            m.surface_render_method = 'BLENDED'
        except Exception:
            m.blend_method = 'BLEND'
    if emit:
        bsdf.inputs['Emission Color'].default_value = (*emit[0], 1)
        bsdf.inputs['Emission Strength'].default_value = emit[1]
    MATS[name] = m
    MAT_UV[name] = uv
    return m


def adjusted_ortho(name='ortho4k.jpg', out='ortho_adj.jpg'):
    """Orthophoto with gamma + saturation correction (aerial imagery is hazy/bright)."""
    import numpy as np
    dst = os.path.join(TEX, out)
    src = bpy.data.images.load(os.path.join(DATA, name))
    w, h = src.size
    px = np.empty(w * h * 4, dtype=np.float32)
    src.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    rgb = px[..., :3]
    lum = rgb.mean(axis=2, keepdims=True)
    rgb = np.clip(lum + (rgb - lum) * 1.35, 0, 1) ** 1.25 * 0.92
    rgb = np.clip(rgb * np.array([1.04, 1.0, 0.9], dtype=np.float32), 0, 1)   # aerial haze is blue
    px[..., :3] = rgb
    if WEB and w > 2048:
        import numpy as np
        f = w // 2048
        px = px[::f, ::f]
        h, w = px.shape[0], px.shape[1]
    img = bpy.data.images.new(out.split('.')[0], w, h)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = dst
    img.file_format = 'JPEG'
    bpy.context.scene.render.image_settings.quality = 88
    img.save()
    bpy.data.images.remove(src)
    return img


def tint_mat(nm, hexc):
    c = textures.col(hexc)
    bs = next(n for n in MATS[nm].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    tn = next(n for n in MATS[nm].node_tree.nodes if n.type == 'TEX_IMAGE' and n.image and not n.image.name.endswith('_n.png'))
    mix = MATS[nm].node_tree.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    MATS[nm].node_tree.links.new(tn.outputs['Color'], mix.inputs['A'])
    mix.inputs['B'].default_value = (*(c / max(c)), 1)
    MATS[nm].node_tree.links.new(mix.outputs['Result'], bs.inputs['Base Color'])


def setup_materials():
    tx = textures.build_all(TEX, n=256 if (FAST or WEB) else 512)
    make_mat('plaster', tx['plaster'], normal=tx.get('plaster_n'), uv=6.0, rough=0.9)
    make_mat('plaster_int', tx['plaster_int'], normal=tx.get('plaster_int_n'), uv=3.0, rough=0.9)
    make_mat('rustica', tx['rustica'], normal=tx.get('rustica_n'), uv=2.4, rough=0.85)
    make_mat('stone', tx['stone'], normal=tx.get('stone_n'), uv=2.0, rough=0.85)
    make_mat('roof', tx['roof'], normal=tx.get('roof_n'), uv=3.0, rough=0.7)
    make_mat('roof_tower', tx['roof_new'], normal=tx.get('roof_new_n'), uv=2.2, rough=0.65)
    make_mat('roof_palace', tx['roof_new'], normal=tx.get('roof_new_n'), uv=3.0, rough=0.7)   # 2010 re-roofing: brighter than the old town
    # the tiles read brick red, not salmon (Earth ge_aerial_n / ge_crown, photos 07, 14)
    tint_mat('roof_palace', '#E87A68')
    tint_mat('roof_tower', '#E87A68')
    make_mat('cobbles', tx['cobbles'], normal=tx.get('cobbles_n'), uv=1.0, rough=0.85)
    make_mat('cobbles_b', tx['cobbles'], normal=tx.get('cobbles_n'), uv=1.0, rough=0.88)
    tint_mat('cobbles_b', '#F0E6D8')
    make_mat('cobbles_c', tx['cobbles'], normal=tx.get('cobbles_n'), uv=1.0, rough=0.82)
    tint_mat('cobbles_c', '#D8DCE0')
    make_mat('rubble', tx['rubble'], normal=tx.get('rubble_n'), uv=4.0, rough=0.95)
    make_mat('parquet', tx['parquet'], normal=tx.get('parquet_n'), uv=2.0, rough=0.45, spec=0.5)
    make_mat('marble', tx['marble'], normal=tx.get('marble_n'), uv=1.6, rough=0.25, spec=0.6)
    make_mat('gravel', tx['gravel'], normal=tx.get('gravel_n'), uv=2.0, rough=1.0)
    make_mat('gravel_red', tx['gravel_red'], normal=tx.get('gravel_red_n'), uv=1.5, rough=1.0)
    make_mat('gravel_white', tx['gravel_white'], normal=tx.get('gravel_white_n'), uv=1.5, rough=1.0)
    make_mat('box_hedge', tx['hedge'], normal=tx.get('hedge_n'), uv=0.8, rough=1.0)
    make_mat('grass', tx['grass'], normal=tx.get('grass_n'), uv=2.0, rough=1.0)
    make_mat('slope_grass', tx['grass'], normal=tx.get('grass_n'), uv=2.5, rough=1.0)
    tint_mat('slope_grass', '#C8C49A')   # dry summer grass of the castle hill (Earth ph_slope_s)
    make_mat('flag_sk', tx['flag_sk'], uv=1.0, rough=0.8)
    MATS['flag_sk'].use_backface_culling = False
    make_mat('hedge', tx['hedge'], normal=tx.get('hedge_n'), uv=1.5, rough=1.0)
    for nm_ in ('paint_land', 'paint_port', 'paint_land2', 'paint_port2', 'paint_still', 'paint_harbour'):
        make_mat(nm_, tx[nm_], uv=1.0, rough=0.35)
    make_mat('bark', tx['bark'], normal=tx.get('bark_n'), uv=1.0, rough=1.0)
    make_mat('foliage', tx['foliage'], uv=2.5, rough=1.0)
    for nm in ('leaves', 'leaves_dark', 'leaves_light', 'leaves_dense', 'grass_tuft'):
        make_mat(nm, tx[nm], uv=1.0, rough=0.8, spec=0.2)
        m = MATS[nm]
        bs = next(n_ for n_ in m.node_tree.nodes if n_.type == 'BSDF_PRINCIPLED')
        tn = next(n_ for n_ in m.node_tree.nodes if n_.type == 'TEX_IMAGE')
        m.node_tree.links.new(tn.outputs['Alpha'], bs.inputs['Alpha'])
        m.use_backface_culling = False
        try:
            m.surface_render_method = 'DITHERED'
        except Exception:
            m.blend_method = 'CLIP'
    make_mat('foliage_dark', tx['foliage'], uv=2.5, rough=1.0)
    tint_mat('foliage_dark', '#9DB08A')
    make_mat('foliage_light', tx['foliage'], uv=2.5, rough=1.0)
    tint_mat('foliage_light', '#F2FFD0')
    make_mat('glass', None, color=(0.035, 0.045, 0.055), rough=0.03, alpha=0.42, spec=1.0)
    MATS['glass'].use_backface_culling = False
    make_mat('frame', None, color=(0.84, 0.82, 0.78), rough=0.6)   # cornices and string courses read white on the photos
    make_mat('door_case', None, color=(0.62, 0.58, 0.52), rough=0.5)
    make_mat('door_int', None, color=(0.72, 0.68, 0.6), rough=0.35)
    make_mat('joinery', None, color=(0.14, 0.065, 0.035), rough=0.45)     # dark brown wooden casements (photo 04)
    make_mat('copper', None, color=(0.33, 0.52, 0.43), rough=0.55, metal=0.3)
    make_mat('door', tx['oak'], normal=tx.get('oak_n'), uv=1.0, rough=0.5)
    make_mat('metal', None, color=(0.25, 0.25, 0.24), rough=0.4, metal=0.9)
    make_mat('granite', None, color=(0.17, 0.17, 0.17), rough=0.45, spec=0.4)
    make_mat('granite_grey', None, color=(0.24, 0.24, 0.235), rough=0.7, spec=0.3)     # Svätopluk drum (photo 07)
    make_mat('gold', None, color=(0.85, 0.65, 0.25), rough=0.3, metal=1.0)
    make_mat('bronze', None, color=(0.085, 0.065, 0.045), rough=0.55, metal=0.75)     # dark brown patina (photo 07)
    make_mat('flag_white', None, color=(0.95, 0.95, 0.95), rough=0.8)
    make_mat('flag_blue', None, color=(0.05, 0.25, 0.65), rough=0.8)
    make_mat('glass_blue', None, color=(0.05, 0.09, 0.12), rough=0.05, spec=0.9, metal=0.2)     # tinted, not a flat blue card (Codex V5: nicholas_00L)
    make_mat('flag_red', None, color=(0.8, 0.08, 0.1), rough=0.8)
    make_mat('room_dark', None, color=(0.07, 0.06, 0.055), rough=0.95)     # unlit room seen through a window
    make_mat('river', None, color=(0.16, 0.22, 0.22), rough=0.08, spec=0.8)
    make_mat('jet', None, color=(0.85, 0.92, 0.95), rough=0.05, alpha=0.45)
    make_mat('water', None, color=(0.08, 0.12, 0.12), rough=0.12, spec=1.0)
    make_mat('invisible', None, color=(1, 1, 1), alpha=0.0)
    make_mat('brick', tx['brick'], normal=tx.get('brick_n'), uv=2.0, rough=0.95)
    make_mat('candle', None, color=(0.93, 0.9, 0.82), rough=0.6)
    make_mat('limestone', tx['stone'], normal=tx.get('stone_n'), uv=1.2, rough=0.75)
    tint_mat('limestone', '#F2EBDD')
    make_mat('zinc', None, color=(0.55, 0.57, 0.58), rough=0.45, metal=0.7)
    make_mat('grime', tx['grime'], uv=1.0, rough=0.9)
    gm = MATS['grime']
    gbs = next(n_ for n_ in gm.node_tree.nodes if n_.type == 'BSDF_PRINCIPLED')
    gtn = next(n_ for n_ in gm.node_tree.nodes if n_.type == 'TEX_IMAGE')
    gm.node_tree.links.new(gtn.outputs['Alpha'], gbs.inputs['Alpha'])
    try:
        gm.surface_render_method = 'BLENDED'
    except Exception:
        gm.blend_method = 'BLEND'
    make_mat('lamp_glass', None, color=(1.0, 0.93, 0.8), rough=0.3, alpha=0.55, emit=((1.0, 0.85, 0.6), 0.6))
    MATS['lamp_glass'].use_backface_culling = False
    make_mat('jewel_red', None, color=(0.6, 0.02, 0.05), rough=0.05, spec=1.0)
    make_mat('jewel_blue', None, color=(0.05, 0.12, 0.55), rough=0.05, spec=1.0)
    make_mat('porcelain', None, color=(0.92, 0.92, 0.9), rough=0.12, spec=0.8)
    make_mat('glass_art', None, color=(0.55, 0.72, 0.78), rough=0.05, alpha=0.5, spec=1.0)
    make_mat('fresco', tx['fresco'], uv=1.0, rough=0.85)
    make_mat('plaque', None, color=(0.85, 0.82, 0.74), rough=0.6)
    make_mat('streaks', tx['streaks'], uv=1.0, rough=0.9)
    sm_ = MATS['streaks']
    sbs = next(n_ for n_ in sm_.node_tree.nodes if n_.type == 'BSDF_PRINCIPLED')
    stn = next(n_ for n_ in sm_.node_tree.nodes if n_.type == 'TEX_IMAGE')
    sm_.node_tree.links.new(stn.outputs['Alpha'], sbs.inputs['Alpha'])
    try:
        sm_.surface_render_method = 'BLENDED'
    except Exception:
        sm_.blend_method = 'BLEND'
    make_mat('surround', tx['plaster'], normal=tx.get('plaster_n'), uv=1.5, rough=0.75, color=(1.0, 0.99, 0.96))   # white stucco surrounds (photo 01)
    tint_mat('surround', '#E8DDCB')
    make_mat('mirror', None, color=(0.85, 0.87, 0.88), rough=0.03, metal=1.0)
    make_mat('carpet', None, color=(0.42, 0.06, 0.07), rough=0.95)
    for nm, hexc in (('wall_f0', '#E2DBCB'), ('wall_f1', '#CDD5C4'), ('wall_f2', '#E0CFB0'), ('wall_f3', '#D5D2DA')):
        make_mat(nm, tx['plaster_int'], normal=tx.get('plaster_int_n'), uv=3.0, rough=0.9)
        tint_mat(nm, hexc)
    make_mat('dado', None, color=(0.55, 0.50, 0.42), rough=0.45)
    make_mat('metal_roof', None, color=(0.32, 0.33, 0.34), rough=0.45, metal=0.6)
    make_mat('concrete', None, color=(0.62, 0.62, 0.6), rough=0.85)
    make_mat('lamp', None, color=(1, 0.95, 0.8), emit=((1, 0.85, 0.6), 2.0))
    ortho = adjusted_ortho()
    make_mat('ortho', ortho, uv=1.0, rough=1.0, spec=0.0)
    if os.path.exists(os.path.join(DATA, 'ortho_far.jpg')):
        make_mat('ortho_far', adjusted_ortho('ortho_far.jpg', 'ortho_far_adj.jpg'), uv=1.0, rough=1.0, spec=0.0)
    for nm, hexc in (('bldg_wall', '#E8E0CF'), ('bldg_wall2', '#EFE6D2'), ('bldg_wall3', '#E5D9BE')):
        make_mat(nm, tx['plaster'], uv=3.0, rough=0.9)
        c = textures.col(hexc)
        bs = next(n for n in MATS[nm].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        mix = MATS[nm].node_tree.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        tn = next(n for n in MATS[nm].node_tree.nodes if n.type == 'TEX_IMAGE')
        MATS[nm].node_tree.links.new(tn.outputs['Color'], mix.inputs['A'])
        mix.inputs['B'].default_value = (*(c / max(c) ), 1)
        MATS[nm].node_tree.links.new(mix.outputs['Result'], bs.inputs['Base Color'])


# ---------------------------------------------------------------- terrain
class Terrain:
    def __init__(self):
        hires = '--hires' in ARGS and os.path.exists(os.path.join(DATA, 'dmr256.json'))
        d = json.load(open(os.path.join(DATA, 'dmr256.json' if hires else 'dmr128.json')))   # DMR 5.0 grid, 2.4 m or 4.8 m
        self.W, self.S, self.E, self.N = d['bbox']
        self.nx, self.ny = d['nx'], d['ny']
        self.z = d['z']   # row 0 = north
        x0, y0 = to_local(self.S, self.W)
        x1, y1 = to_local(self.N, self.E)
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.cz = None
        self.z0 = self.raw(0.0, -3.0)
        print('courtyard reference elevation', self.z0)
        # walkable Old Town / embankment: second, coarser (~5 m) DMR tier around the detailed castle grid
        cp = os.path.join(DATA, 'dmr_centre.json')
        if os.path.exists(cp):
            c = json.load(open(cp))
            if not any(v is None for r in c['z'] for v in r):
                self.cz, self.cnx, self.cny = c['z'], c['nx'], c['ny']
                W_, S_, E_, N_ = c['bbox']
                self.cx0, self.cy0 = to_local(S_, W_)
                self.cx1, self.cy1 = to_local(N_, E_)
                print('centre DMR tier', self.cnx, 'x', self.cny)
            else:
                print('centre DMR incomplete, ignored')
        self.patches = call_v2('v2_fortress', 'terrain_patches', self) or ()   # flat terraces held by walls (v2_fortress)

    def covers(self, x, y):
        """True where h() is backed by survey data (castle grid or the centre tier)."""
        return (self.x0 < x < self.x1 and self.y0 < y < self.y1) or self.in_centre(x, y)

    def in_centre(self, x, y):
        return self.cz is not None and self.cx0 < x < self.cx1 and self.cy0 < y < self.cy1

    def raw_centre(self, x, y):
        fx = min(max((x - self.cx0) / (self.cx1 - self.cx0) * self.cnx - 0.5, 0), self.cnx - 1.001)
        fy = min(max((self.cy1 - y) / (self.cy1 - self.cy0) * self.cny - 0.5, 0), self.cny - 1.001)
        i, j = int(fx), int(fy)
        u, v = fx - i, fy - j
        z = self.cz
        return ((z[j][i] * (1 - u) + z[j][i + 1] * u) * (1 - v) + (z[j + 1][i] * (1 - u) + z[j + 1][i + 1] * u) * v)

    def raw(self, x, y):
        if self.cz is not None:
            # distance inside the detailed grid; blend to the centre tier over the outer 15 m
            m = min(x - self.x0, self.x1 - x, y - self.y0, self.y1 - y)
            if m < 15.0 and self.in_centre(x, y):
                zc = self.raw_centre(x, y)
                if m <= 0:
                    return zc
                t = m / 15.0
                return zc + (self.raw_main(x, y) - zc) * t * t * (3 - 2 * t)
        return self.raw_main(x, y)

    def raw_main(self, x, y):
        fx = (x - self.x0) / (self.x1 - self.x0) * self.nx - 0.5
        fy = (self.y1 - y) / (self.y1 - self.y0) * self.ny - 0.5
        fx = min(max(fx, 0), self.nx - 1.001)
        fy = min(max(fy, 0), self.ny - 1.001)
        i, j = int(fx), int(fy)
        u, v = fx - i, fy - j
        z = self.z
        return ((z[j][i] * (1 - u) + z[j][i + 1] * u) * (1 - v) +
                (z[j + 1][i] * (1 - u) + z[j + 1][i + 1] * u) * v)

    garden = None
    levels = ()
    gbox = (0, 0, 0, 0)
    sharpen = None      # v2_garden: step function along the terrace walls

    def set_garden(self, poly):
        """Baroque garden terraces are level (photos 11, 27); the 2.4 m DMR undulates by +-0.3 m.
        Find the terrace levels as height-histogram peaks; h() then eases nearby heights onto them."""
        if not poly:
            return
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        hs = []
        for yy in range(int(min(ys)), int(max(ys)), 2):
            for xx in range(int(min(xs)), int(max(xs)), 2):
                if point_in_poly(xx, yy, poly):
                    hs.append(self.raw(xx, yy) - self.z0)
        if not hs:
            return
        bins = {}
        for v in hs:
            bins[round(v / 0.25)] = bins.get(round(v / 0.25), 0) + 1
        peaks = [k for k, c in bins.items() if c >= 0.06 * len(hs) and c >= bins.get(k - 1, 0) and c >= bins.get(k + 1, 0)]
        lv = []
        for k in sorted(peaks):
            near_v = [v for v in hs if abs(v - k * 0.25) < 0.4]
            lv.append(sum(near_v) / len(near_v))
        self.garden, self.levels = poly, lv
        self.gbox = (min(xs), max(xs), min(ys), max(ys))
        print('garden terrace levels', [round(v, 2) for v in lv])
        self.sharpen = call_v2('v2_garden', 'terrace_sharpener', self, poly)

    def h(self, x, y):
        """Local height with the palace apron flattened to the courtyard level."""
        for poly, zf, bb in self.patches:
            if bb[0] < x < bb[1] and bb[2] < y < bb[3] and point_in_poly(x, y, poly):
                return zf(x, y)
        zr = self.raw(x, y) - self.z0
        gb = self.gbox
        if self.levels and gb[0] < x < gb[1] and gb[2] < y < gb[3] and point_in_poly(x, y, self.garden):
            k = min(range(len(self.levels)), key=lambda i: abs(self.levels[i] - zr))
            lv = self.levels[k]
            gaps = [abs(lv - self.levels[j]) for j in (k - 1, k + 1) if 0 <= j < len(self.levels)]
            r = min([0.7] + [g / 2 for g in gaps])     # never reaches the midpoint to the next level -> continuous
            dz = abs(lv - zr)
            if dz < r:            # level on the terrace, eased back to the DMR on the slopes between terraces
                t = max(0.0, (dz - r / 2) / (r / 2))
                zr = lv + (zr - lv) * t * t * (3 - 2 * t)
            if self.sharpen:      # v2_garden: terrace walls + stairs (works on the eased heights)
                zr = self.sharpen(x, y, zr)
        if point_in_poly(x, y, OUTER):
            return -0.03
        if point_in_poly(x, y, HONOUR_COURT):
            return -0.03 - 0.02 * max(0.0, -40.0 - y)      # gentle fall away from the palace for drainage
        d = dist_to_poly(x, y, OUTER)
        if d < 5:
            return -0.03
        if d < 18:
            t = (d - 5) / 13
            t = t * t * (3 - 2 * t)
            return -0.03 * (1 - t) + zr * t
        return zr

    def uv(self, x, y):
        return ((x - self.x0) / (self.x1 - self.x0), (y - self.y0) / (self.y1 - self.y0))


def far_height(T):
    """Height sampler on the 3x3 km context DMR (local metres relative to the courtyard)."""
    d = json.load(open(os.path.join(DATA, 'dmr_far.json')))
    W_, S_, E_, N_ = d['bbox']
    nx, ny, z = d['nx'], d['ny'], d['z']
    x0, y0 = to_local(S_, W_)
    x1, y1 = to_local(N_, E_)

    def zf(x, y):
        fx = min(max((x - x0) / (x1 - x0) * nx - 0.5, 0), nx - 1.001)
        fy = min(max((y1 - y) / (y1 - y0) * ny - 0.5, 0), ny - 1.001)
        i, j = int(fx), int(fy)
        u, v = fx - i, fy - j
        return ((z[j][i] * (1 - u) + z[j][i + 1] * u) * (1 - v) + (z[j + 1][i] * (1 - u) + z[j + 1][i + 1] * u) * v) - T.z0
    return zf, min(min(r) for r in z) - T.z0


def build_landmarks(T, coll):
    """Skyline landmarks seen from the castle: St Martin's Cathedral (85 m tower, gilded crown)
    and the SNP Bridge with its leaning pylon and UFO platform (OSM ways 238810163 / 378574918)."""
    if not os.path.exists(os.path.join(DATA, 'dmr_far.json')):
        return []
    zf, zmin = far_height(T)
    mb = MB('Landmarks')
    # --- St Martin's Cathedral: nave 69 x 23 m along E-W, west tower 12 m square
    cx, cy = 335.0, -40.0
    g = zf(cx, cy) - 1.5
    x0, x1, y0, y1 = cx - 34, cx + 35, cy - 11.5, cy + 11.5
    mb.box([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], g - 3, g + 21, 'stone')
    for k in range(8):           # buttresses + tall gothic windows (dark panes)
        xx = x0 + 14 + k * 6.6
        for yy, sg in ((y0, -1), (y1, 1)):
            mb.box([(xx - 0.6, yy), (xx + 0.6, yy), (xx + 0.6, yy + sg * 1.4), (xx - 0.6, yy + sg * 1.4)], g, g + 19, 'stone')
            pane(mb, Vector((xx + 2.0, yy + sg * 0.02)), Vector((xx + 4.4, yy + sg * 0.02)), g + 5, g + 17)
    ridge = g + 36
    for (a, b, c_, d_) in (((x0, y0), (x1, y0), (x1, cy), (x0, cy)), ((x1, y1), (x0, y1), (x0, cy), (x1, cy))):
        mb.poly([Vector((a[0], a[1], g + 21)), Vector((b[0], b[1], g + 21)), Vector((c_[0], c_[1], ridge)), Vector((d_[0], d_[1], ridge))], 'metal_roof')
    mb.poly([Vector((x1, y0, g + 21)), Vector((x1, y1, g + 21)), Vector((x1, cy, ridge))], 'metal_roof')
    tx0, tx1, ty0, ty1 = x0 - 12, x0, cy - 6, cy + 6
    mb.box([(tx0, ty0), (tx1, ty0), (tx1, ty1), (tx0, ty1)], g - 3, g + 50, 'stone')
    oc = Vector((tx0 + 6, cy))
    o8 = [oc + Vector((math.cos(math.pi / 8 + k * math.pi / 4), math.sin(math.pi / 8 + k * math.pi / 4))) * 5 for k in range(8)]
    for k in range(8):
        a, b = o8[k], o8[(k + 1) % 8]
        mb.poly([Vector((a.x, a.y, g + 50)), Vector((b.x, b.y, g + 50)), Vector((b.x, b.y, g + 60)), Vector((a.x, a.y, g + 60))], 'stone')
        mb.poly([Vector((a.x, a.y, g + 60)), Vector((b.x, b.y, g + 60)), Vector((oc.x, oc.y, g + 83))], 'metal_roof')
    ellipsoid(mb, Vector((oc.x, oc.y, g + 84.2)), 0.9, 0.9, 1.0, 0, 0, 'gold', subdiv=2)       # gilded crown replica
    _prism(mb, Vector((oc.x, oc.y, g + 85)), Vector((oc.x, oc.y, g + 86.5)), 0.12, 0.06, 'gold', seg=6)
    # --- SNP Bridge: deck from the Old Town bank to the pylon on the Petrzalka side
    zw = zmin - 1.5 + 0.5
    deck = zw + 12.0
    A, B = Vector((330.0, -97.0)), Vector((337.0, -788.0))
    d = (B - A).normalized()
    nrm = Vector((-d.y, d.x))
    mb.box([A - nrm * 10.5, B - nrm * 10.5, B + nrm * 10.5, A + nrm * 10.5], deck - 1.8, deck, 'concrete')
    for sgn in (-1, 1):
        seg_box(mb, A + nrm * (sgn * 10.3), B + nrm * (sgn * 10.3), -0.15, 0.15, deck, deck + 1.1, 'metal')
    P = Vector((332.0, -607.0))
    top = Vector((P.x, P.y - 22, deck + 84.6))        # pylon leans back toward Petrzalka
    for sgn in (-1, 1):
        foot = P + nrm * (sgn * 12.0)
        _prism(mb, Vector((foot.x, foot.y, deck - 2)), top + Vector((nrm.x, nrm.y, 0)) * (sgn * 2.0), 1.6, 1.1, 'metal', seg=6)
    ellipsoid(mb, top + Vector((0, 0, 1.0)), 15.0, 15.0, 3.2, 0, 0, 'metal', subdiv=2)            # the UFO
    for k in range(7):          # stay cables to the deck
        t = (k + 1) / 8
        q = P + (A - P) * t * 0.85
        for sgn in (-1, 1):
            _prism(mb, top + Vector((nrm.x, nrm.y, 0)) * (sgn * 1.5) - Vector((0, 0, 4 + k * 3)),
                   Vector((q.x, q.y, deck + 1)) + Vector((nrm.x, nrm.y, 0)) * (sgn * 9.5), 0.12, 0.12, 'metal', seg=4)
    return [mb.build(coll)]


def build_far_terrain(T, coll, step=16.0):
    """3x3 km context (Danube, Old Town, bridges) from a coarse DMR + wide orthophoto,
    sunk 1.5 m so the detailed terrain always wins where both exist."""
    fp = os.path.join(DATA, 'dmr_far.json')
    if not os.path.exists(fp) or 'ortho_far' not in MATS:
        return None
    d = json.load(open(fp))
    W_, S_, E_, N_ = d['bbox']
    nx, ny, z = d['nx'], d['ny'], d['z']
    x0, y0 = to_local(S_, W_)
    x1, y1 = to_local(N_, E_)

    def zf(x, y):
        fx = min(max((x - x0) / (x1 - x0) * nx - 0.5, 0), nx - 1.001)
        fy = min(max((y1 - y) / (y1 - y0) * ny - 0.5, 0), ny - 1.001)
        i, j = int(fx), int(fy)
        u, v = fx - i, fy - j
        return ((z[j][i] * (1 - u) + z[j][i + 1] * u) * (1 - v) + (z[j + 1][i] * (1 - u) + z[j + 1][i + 1] * u) * v) - T.z0

    xs = [x0 + k * step for k in range(int((x1 - x0) / step) + 1)]
    ys = [y0 + k * step for k in range(int((y1 - y0) / step) + 1)]
    verts = []
    for y in ys:
        for x in xs:
            inside = T.x0 + 2 < x < T.x1 - 2 and T.y0 + 2 < y < T.y1 - 2
            if T.cz is not None and T.cx0 + 3 < x < T.cx1 - 3 and T.cy0 + 3 < y < T.cy1 - 3:
                verts.append((x, y, T.h(x, y) - 3.0))      # under the walkable centre ground
                continue
            verts.append((x, y, -40.0 if inside else zf(x, y) - 1.5))
    n = len(xs)
    faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(len(ys) - 1) for i in range(n - 1)]
    me = bpy.data.meshes.new('Terrain_Far')
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name='UVMap')
    for f in me.polygons:
        f.use_smooth = True
        for k in range(f.loop_total):
            li = f.loop_start + k
            vx, vy, _ = verts[me.loops[li].vertex_index]
            uvl.data[li].uv = ((vx - x0) / (x1 - x0), (vy - y0) / (y1 - y0))
    me.materials.append(MATS['ortho_far'])
    ob = bpy.data.objects.new('Terrain_Far', me)
    coll.objects.link(ob)
    # Danube surface: the lidar DMR holds the interpolated water level as its minimum
    zw = min(min(r) for r in z) - T.z0 - 1.5 + 0.5
    wm = MB('Danube')
    wm.poly([Vector((x0, y0, zw)), Vector((x1, y0, zw)), Vector((x1, y1, zw)), Vector((x0, y1, zw))], 'river', uv_scale=40)
    wm.build(coll)
    return ob


def build_terrain(T, coll, sink_area=None):
    step = 4.0 if FAST else (3.0 if WEB else 2.0)
    xs = [T.x0 + 1 + k * step for k in range(int((T.x1 - T.x0 - 2) / step) + 1)]
    ys = [T.y0 + 1 + k * step for k in range(int((T.y1 - T.y0 - 2) / step) + 1)]
    me = bpy.data.meshes.new('Terrain')
    verts = [(x, y, T.h(x, y)) for y in ys for x in xs]
    if sink_area:   # under the walk-level paving: keep the coarse terrain safely below it
        # the 0.75 m ground layer follows path trenches / flight carvings narrower than this 2 m grid; the coarse
        # facets poked through it on carved slopes (Codex V5: vienna_05R), so take the lowest ground within 1 m
        def low(x, y):
            return min(T.h(x + dx, y + dy) for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
                                                           (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)))
        verts = [(x, y, low(x, y) - 0.25 if point_in_poly(x, y, sink_area) and not point_in_poly(x, y, OUTER) else z)
                 for x, y, z in verts]
    nx = len(xs)
    inner_cut = offset_poly(OUTER, -0.3)
    under = [point_in_poly(v[0], v[1], inner_cut) for v in verts]
    faces = [f for f in ((j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
             for j in range(len(ys) - 1) for i in range(nx - 1)) if not all(under[k] for k in f)]   # hole under the palace (cellar)
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name='UVMap')
    me.materials.append(MATS['ortho'])
    me.materials.append(MATS['slope_grass'])
    # outside the castle grounds the draped orthophoto reads as a dark glossy sheet at eye level (tree shadows,
    # Fable/Codex V4): the hillside gets a dry-grass ground material instead; the town/castle layers cover the rest
    for f in me.polygons:
        cx_ = sum(verts[i][0] for i in f.vertices) / len(f.vertices)
        cy_ = sum(verts[i][1] for i in f.vertices) / len(f.vertices)
        # inside the castle grounds the walk-level layers cover this terrain; it only shows through their gaps and
        # on carved banks beside flights, where the orthophoto read as dark glossy pits (Codex V5: zamocke_02L/06L)
        grassy = sink_area is not None
        f.material_index = 1 if grassy else 0
        for k in range(f.loop_total):
            li = f.loop_start + k
            v = verts[me.loops[li].vertex_index]
            uvl.data[li].uv = (v[0] / 2.5, v[1] / 2.5) if grassy else T.uv(v[0], v[1])
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new('Terrain-col', me)
    coll.objects.link(ob)
    # skirt down so the edge of the world is not paper-thin
    return ob


def build_centre_terrain(T, coll, step=4.0):
    """Walkable ground of the Old Town and the embankment (outside the detailed castle grid), draped
    on the centre DMR tier and textured with the wide orthophoto; collidable."""
    if T.cz is None or 'ortho_far' not in MATS:
        return None
    d = json.load(open(os.path.join(DATA, 'dmr_far.json')))
    W_, S_, E_, N_ = d['bbox']
    fx0, fy0 = to_local(S_, W_)
    fx1, fy1 = to_local(N_, E_)
    xs = [T.cx0 + 2 + k * step for k in range(int((T.cx1 - T.cx0 - 4) / step) + 1)]
    ys = [T.cy0 + 2 + k * step for k in range(int((T.cy1 - T.cy0 - 4) / step) + 1)]
    inner = lambda x, y: T.x0 + 1 < x < T.x1 - 1 and T.y0 + 1 < y < T.y1 - 1
    verts = [(x, y, T.h(x, y) - (0.06 if inner(x, y) else 0.0)) for y in ys for x in xs]
    nx = len(xs)
    faces = [f for f in ((j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
             for j in range(len(ys) - 1) for i in range(nx - 1)) if not all(inner(*verts[k][:2]) for k in f)]
    me = bpy.data.meshes.new('Terrain_Centre')
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name='UVMap')
    for f in me.polygons:
        f.use_smooth = True
        for k in range(f.loop_total):
            li = f.loop_start + k
            vx, vy, _ = verts[me.loops[li].vertex_index]
            uvl.data[li].uv = ((vx - fx0) / (fx1 - fx0), (vy - fy0) / (fy1 - fy0))
    me.materials.append(MATS['ortho_far'])
    ob = bpy.data.objects.new('Terrain_Centre-col', me)
    coll.objects.link(ob)
    print('centre terrain faces', len(faces))
    return ob


# ---------------------------------------------------------------- palace
def wing_frames():
    """Per wing: outer edge, inner edge, corridor line, inward normal."""
    corr = offset_poly(INNER, CORR_W + COURT_T)      # corridor wall line (room side)
    W = []
    for i in range(4):
        o0, o1 = OUTER[i], OUTER[(i + 1) % 4]
        i0, i1 = INNER[i], INNER[(i + 1) % 4]
        c0, c1 = corr[i], corr[(i + 1) % 4]
        d_in = (i1 - i0).normalized()
        W.append(dict(name=WING_NAMES[i], o=(o0, o1), i=(i0, i1), c=(c0, c1), d=d_in,
                      n=Vector((d_in.y, -d_in.x))))   # n points from courtyard to outside
    return W, corr


def axes_on(a, b, spacing, margin):
    L = (b - a).length
    n = max(1, round((L - 2 * margin) / spacing))
    sp = (L - 2 * margin) / n
    return [margin + sp * (k + 0.5) for k in range(n)], sp


def project_t(p, a, b):
    d = (b - a)
    return (p - a).dot(d) / d.length


def build_palace(T, coll):
    walls = MB('Palace_Walls-col')
    trim = MB('Palace_Trim')
    win = MB('Palace_Windows')
    floors = MB('Palace_Floors-col')
    roof = MB('Palace_Roof-col')
    ramps = MB('Palace_StairRamps-colonly')
    W, corr = wing_frames()
    clad = MB('Palace_WallFinish')
    found = -9.0                              # foundation depth (hidden in terrain)
    win_h = [3.0, 3.1, 3.0, 2.6]              # window opening heights per storey
    sill = [1.1, 1.0, 1.0, 1.0]
    win_w = 1.45
    stories = list(zip(FLOOR_Z, FLOOR_Z[1:] + [EAVE_Z]))

    tower_sq = tower_squares()
    passage = {'S': 0.5, 'N': 0.5}          # S = main gate from the Honour Court; N = to the garden side
    stair_wing, stair_frac = 'W', 0.28         # Theresian staircase room (estimate)
    stair_room = None
    rooms = []                                 # (wing, centre, depth dir, along dir, length, depth, is_stair/passage)
    corridor_pts = []
    corridor_segs = []
    corr_in = offset_poly(INNER, COURT_T)      # courtyard wall, corridor-side face

    for wi, w in enumerate(W):
        o0, o1 = w['o']
        Lo = (o1 - o0).length
        d_o = (o1 - o0) / Lo
        n_o = Vector((-d_o.y, d_o.x))        # inward (left of CCW outer edge)
        ts0, ts1 = TOWER_SIZE[wi], TOWER_SIZE[(wi + 1) % 4]
        fac = FACADES[w['name']]
        span0, span1 = ts0 + fac['margin'], Lo - ts1 - fac['margin']
        nax = fac['n']
        sp = (span1 - span0) / nax
        jr = random.Random(wi * 31)
        ax = [span0 + sp * (k + 0.5) + (jr.uniform(-1, 1) * fac.get('jitter', 0.0)) for k in range(nax)]
        pas_u = passage.get(w['name'])
        pas_axis = min(ax, key=lambda u: abs(u - pas_u * Lo)) if pas_u else None
        # ---- outer wall with windows
        ops = []
        for k, (z0, z1) in enumerate(stories):
            for u in ax:
                if pas_axis is not None and k == 0 and abs(u - pas_axis) < 1e-6:
                    ops.append((u - 1.9, u + 1.9, z0 - 1.5, z0 + 4.6))   # gateway (no sill)
                    continue
                if w['name'] == 'S' and k == 1 and pas_axis is not None and abs(u - pas_axis) < 1e-6:
                    ops.append((u - 0.8, u + 0.8, z0, z0 + 3.6))   # balcony door above the main gate
                    continue
                ai = ax.index(u)
                if k in fac.get('blank', ()) or (k, ai) in fac.get('skip', set()) or (k, ai) in fac.get('blind', set()):
                    continue
                if w['name'] == 'S' and k == 0 and pas_axis is not None and abs(abs(u - pas_axis) - sp) < 1e-6:
                    ops.append((u - 0.95, u + 0.95, z0, z0 + 3.9))   # the two round-headed doors of the risalit
                    continue
                ww_ = fac['w']
                if w['name'] == 'E' and k == 1 and ai == 0:      # modern glazed panel (photo 09)
                    ops.append((u - 1.25, u + 1.25, z0 - 0.3, z0 + 4.4))
                    continue
                ops.append((u - ww_ / 2, u + ww_ / 2, z0 + sill[k], z0 + sill[k] + fac['h'][k]))
            if fac.get('corner') and k > 0:      # narrow corner axes beside the towers (E facade)
                for uc in (ts0 + 1.0, Lo - ts1 - 1.0):
                    ops.append((uc - 0.35, uc + 0.35, z0 + sill[k] + 0.3, z0 + sill[k] + fac['h'][k] - 0.3))
        # the tower shafts own the corners: wing wall runs between them
        wa, wb = o0 + d_o * ts0, o1 - d_o * ts1
        wall(walls, wa, wb, found, EAVE_Z, OUTER_T, 'plaster',
             [(o[0] - ts0, o[1] - ts0, o[2], o[3]) for o in ops], mat_in='plaster_int')
        finish_side(clad, wa, wb, [(o[0] - ts0, o[1] - ts0, o[2], o[3]) for o in ops], OUTER_T)
        # facade trim: stone plinth, cordon bands, window surrounds, cornice
        gaps = sorted((o[0], o[1]) for o in ops if o[1] - o[0] > 3)
        u = ts0
        for g0, g1 in gaps + [(Lo - ts1, Lo - ts1)]:
            if g0 - u > 0.05:
                seg_box(trim, o0 + d_o * u, o0 + d_o * g0, -0.25, 0.05, found, 0.9, 'stone')
            u = g1
        for zc in (FLOOR_Z[1:] if w['name'] == 'S' else FLOOR_Z[1:2]):     # E/N/W read plain (photos 09, 11)
            sweep(trim, wa, wb, PROF_BAND, zc - 0.25, 'frame', -n_o)
        sweep(trim, wa, wb, PROF_EAVE, EAVE_Z - 0.8, 'frame', -n_o)
        # zinc downpipes every 4th bay and a soft grime band above the plinth
        for kk in range(2, len(ax), 4):
            um = (ax[kk - 1] + ax[kk]) / 2 + 0.6
            pp = o0 + d_o * um - n_o * 0.16
            _prism(trim, Vector((pp.x, pp.y, 0.2)), Vector((pp.x, pp.y, EAVE_Z - 0.1)), 0.055, 0.055, 'zinc', seg=8)
            for zb_ in range(2, int(EAVE_Z), 3):
                seg_box(trim, pp - d_o * 0.07, pp + d_o * 0.07, -0.02, 0.17, zb_, zb_ + 0.05, 'zinc')
        # no grime / streak overlays: the render was renewed in 2008-2010 and reads clean white (photos 04, 05, 09)
        if w['name'] == 'S' and pas_axis is not None:     # central risalit of the Honour Court facade
            for kk in range(len(ax)):
                if abs(ax[kk] - pas_axis) > sp * 2.6:
                    continue
                for side_ in (-1, 1):
                    um = ax[kk] + side_ * sp / 2
                    pa_, pb_ = o0 + d_o * (um - 0.42), o0 + d_o * (um + 0.42)
                    seg_box(trim, pa_, pb_, -0.16, 0.02, 0.9, EAVE_Z - 1.0, 'plaster')
                    for zl_, zh_ in ((FLOOR_Z[1] + 0.3, FLOOR_Z[2] - 0.6), (FLOOR_Z[2] + 0.3, FLOOR_Z[3] - 0.6), (FLOOR_Z[3] + 0.3, EAVE_Z - 1.6)):
                        # framed sunk panel on each storey of the pilaster (photo 04)
                        for e0_, e1_ in ((pa_ + d_o * 0.08, pa_ + d_o * 0.14), (pb_ - d_o * 0.14, pb_ - d_o * 0.08)):
                            seg_box(trim, e0_, e1_, -0.21, -0.15, zl_, zh_, 'frame')
                        for zz_ in (zl_, zh_ - 0.06):
                            seg_box(trim, pa_ + d_o * 0.08, pb_ - d_o * 0.08, -0.21, -0.15, zz_, zz_ + 0.06, 'frame')
                    for zc_ in (FLOOR_Z[1] - 0.3, EAVE_Z - 1.3):
                        sweep(trim, pa_ - d_o * 0.08, pb_ + d_o * 0.08, [(0.0, 0.0), (0.2, 0.0), (0.24, 0.06), (0.24, 0.12), (0.28, 0.18),
                                                                       (0.28, 0.3), (0.0, 0.3)], zc_, 'frame', -n_o)
            for o in ops:
                if abs((o[0] + o[1]) / 2 - pas_axis) < sp * 2.6 and o[2] > FLOOR_Z[1] - 0.5 and (o[1] - o[0]) < 3:
                    a_, b_ = o0 + d_o * (o[0] - 0.35), o0 + d_o * (o[1] + 0.35)
                    sweep(trim, a_, b_, [(0.0, 0.0), (0.12, 0.0), (0.18, 0.06), (0.26, 0.14), (0.3, 0.22), (0.0, 0.22)], o[3] + 0.25, 'frame', -n_o)
        for (k_b, ai_b) in fac.get('blind', set()):       # blind windows: painted recess + surround
            if ai_b < len(ax) and k_b < len(stories):
                u_b = ax[ai_b]
                zb0 = stories[k_b][0] + sill[k_b]
                pa_, pb_ = o0 + d_o * (u_b - fac['w'] / 2), o0 + d_o * (u_b + fac['w'] / 2)
                seg_box(trim, pa_, pb_, -0.015, 0.01, zb0, zb0 + fac['h'][k_b], 'plaster_int')
                seg_box(trim, pa_ - d_o * 0.18, pb_ + d_o * 0.18, -0.07, 0.02, zb0 + fac['h'][k_b], zb0 + fac['h'][k_b] + 0.18, 'frame')
        # flat lesenes (pilaster strips) between window axes
        for k in (range(1, len(ax)) if w['name'] == 'S' else ()):
            um = (ax[k - 1] + ax[k]) / 2
            seg_box(trim, o0 + d_o * (um - 0.35), o0 + d_o * (um + 0.35), -0.04, 0.02, 0.9, EAVE_Z - 1.0, 'plaster')
        for o in ops:
            u0, u1, z0, z1 = o
            a, b = o0 + d_o * u0, o0 + d_o * u1
            gate = (u1 - u0) > 3
            if not gate and z0 == FLOOR_Z[1] and w['name'] == 'S':     # balcony door
                window_unit(win, a, b, z0, z1, n_o, OUTER_T * 0.55, door=True)
                seg_box(trim, a - d_o * 0.22, b + d_o * 0.22, -0.3, 0.02, z1, z1 + 0.5, 'frame')
                continue
            fw = 0.22
            # surround
            seg_box(trim, a - d_o * fw, a, -0.08, 0.02, z0 - (0 if gate else 0.15), z1 + fw, 'frame')
            seg_box(trim, b, b + d_o * fw, -0.08, 0.02, z0 - (0 if gate else 0.15), z1 + fw, 'frame')
            seg_box(trim, a - d_o * fw, b + d_o * fw, -0.08, 0.02, z1, z1 + fw, 'frame')
            if not gate:
                seg_box(trim, a - d_o * 0.3, b + d_o * 0.3, -0.18, 0.4, z0 - 0.15, z0, 'stone')  # sill
                storey = max(i_ for i_, zf_ in enumerate(FLOOR_Z) if zf_ <= z0 + 0.01)
                if storey in fac.get('arch', ()) and (u1 - u0) > 1.2:    # segment-arched heads
                    arch_head(walls, a, b, z1, 0.0, OUTER_T * 0.55, 'plaster', rise=(u1 - u0) * 0.22)
                    seg_box(trim, a - d_o * 0.45, b + d_o * 0.45, -0.25, 0.02, z1 + fw, z1 + fw + 0.18, 'frame')
                if storey in fac.get('hood', ()):                         # flat cornice hoods (N facade)
                    seg_box(trim, a - d_o * 0.4, b + d_o * 0.4, -0.22, 0.02, z1 + fw, z1 + fw + 0.14, 'frame')
                is_door = z0 < 0.3 and (u1 - u0) < 2.0
                if is_door and w['name'] == 'S' and pas_axis is not None and abs(abs((u0 + u1) / 2 - pas_axis) - sp) < 0.01:
                    arch_head(walls, a, b, z1, 0.0, OUTER_T, 'plaster')
                    closed_arch_door(win, a, b, z0, z1, n_o, 0.3)     # closed brown double doors (photo 04)
                    continue
                if is_door:
                    arch_head(walls, a, b, z1, 0.0, OUTER_T, 'plaster')
                    door_leaves(win, a, b, n_o, z0, z1, OUTER_T, leaf=(u1 - u0) / 2)
                    continue
                gothic = w['name'] == 'S' and storey == 2 and abs((u0 + u1) / 2 - ax[-2]) < 0.01
                if gothic:     # exposed Gothic tracery window (2nd axis from E, floor 2)
                    gothic_window(trim, win, a, b, z0, z1, n_o)
                    continue
                if w['name'] == 'E' and (u1 - u0) > 2.4:     # modern frameless blue glazing panel (photo 09)
                    a_g, b_g = a + n_o * 0.12, b + n_o * 0.12
                    seg_box(win, a_g, b_g, -0.04, 0.04, z0, z0 + 0.06, 'metal')
                    seg_box(win, a_g, b_g, -0.04, 0.04, z1 - 0.06, z1, 'metal')
                    seg_box(win, a_g, a_g + d_o * 0.06, -0.04, 0.04, z0, z1, 'metal')
                    seg_box(win, b_g - d_o * 0.06, b_g, -0.04, 0.04, z0, z1, 'metal')
                    mg = (a_g + b_g) / 2
                    seg_box(win, mg - d_o * 0.04, mg + d_o * 0.04, -0.05, 0.05, z0, z1, 'metal')          # mullion
                    for zt_ in (z0 + (z1 - z0) * 0.36, z0 + (z1 - z0) * 0.7):                             # transoms
                        seg_box(win, a_g, b_g, -0.05, 0.05, zt_ - 0.04, zt_ + 0.04, 'metal')
                    win.poly([Vector((a_g.x, a_g.y, z0)), Vector((b_g.x, b_g.y, z0)), Vector((b_g.x, b_g.y, z1)), Vector((a_g.x, a_g.y, z1))], 'glass_blue')
                    win.poly([Vector((b_g.x, b_g.y, z0)), Vector((a_g.x, a_g.y, z0)), Vector((a_g.x, a_g.y, z1)), Vector((b_g.x, b_g.y, z1))], 'glass_blue')
                    continue
                window_unit(win, a, b, z0, z1, n_o, 0.32)   # baroque casements sit near the outer face (photos 04, 05)
            else:
                floors.box([a, b, b + n_o * (OUTER_T + 0.6), a + n_o * (OUTER_T + 0.6)], -0.45, 0.0, 'stone')   # threshold
                z0 = 0.0
                arch_head(walls, a, b, z1, 0.0, OUTER_T, 'plaster')
                gm_ = (a + b) / 2
                NAV[f'gate_{w["name"]}_out'] = list(gm_ - n_o * 3.0)
                NAV[f'gate_{w["name"]}_in'] = list(gm_ + n_o * (OUTER_T + 6.0))
                rust_gate(trim, a, b, d_o, z0, z1)
                door_leaves(win, a, b, n_o, z0, z1, OUTER_T)
                if w['name'] == 'S':
                    balcony(trim, floors, (a + b) / 2, d_o, -n_o, hw=min(1.45 * sp, 9.0))

        # ---- courtyard facade
        i0, i1 = w['i']
        Li = (i1 - i0).length
        d_i = (i1 - i0) / Li
        # photos 01/02: a steady rhythm of axes (~10 on the long wings, 6 on the short ones), not isolated triplets
        nax_i = 10 if Li > 45 else 6
        ax_i = [2.6 + (Li - 5.2) * (g + 0.5) / nax_i for g in range(nax_i)]
        ops_i = []
        pas_t = None
        if pas_axis is not None:
            pas_t = project_t(o0 + d_o * pas_axis, i0, i1)
        door_axes = {ax_i[1], ax_i[-2]} if len(ax_i) > 3 else set()      # small doors only
        for k, (z0, z1) in enumerate(stories):
            for u in ax_i:
                if pas_t is not None and k == 0 and abs(u - pas_t) < sp * 0.6:
                    continue
                if k == 0 and u in door_axes:
                    ops_i.append((u - 0.65, u + 0.65, z0, z0 + 2.9))
                elif k == 0:
                    ops_i.append((u - 0.75, u + 0.75, z0 + 1.2, z0 + 1.2 + 2.4))
                else:      # photos 01/02: broad casements filling most of the bay height
                    ops_i.append((u - 0.82, u + 0.82, z0 + sill[k] - 0.15, z0 + sill[k] + [0, 2.85, 2.75, 2.4][k]))
            if pas_t is not None and k == 0:
                ops_i.append((pas_t - 1.9, pas_t + 1.9, z0 - 0.7, z0 + 4.6))
        # courtyard wall: the inner polygon is CCW, the building is to the RIGHT -> walk reversed
        wall(walls, i1, i0, found, EAVE_Z, COURT_T, 'plaster',
             [(Li - o[1], Li - o[0], o[2], o[3]) for o in ops_i], mat_in='plaster_int')
        n_i = Vector((d_i.y, -d_i.x))   # from courtyard into building
        for o in ops_i:
            a, b = i0 + d_i * o[0], i0 + d_i * o[1]
            if o[1] - o[0] >= 3.5:
                arch_head(walls, b, a, o[3], 0.0, COURT_T, 'plaster')
            if o[1] - o[0] >= 3.5:      # passage threshold across the courtyard wall
                floors.box([a - n_i * 0.3, b - n_i * 0.3, b + n_i * (COURT_T + 0.6), a + n_i * (COURT_T + 0.6)], -0.45, 0.0, 'stone')
            if o[1] - o[0] < 3.5:
                if o[2] < 0.3:
                    door_leaves(win, b, a, n_i, o[2], o[3], COURT_T, leaf=(o[1] - o[0]) / 2)
                else:
                    window_unit(win, b, a, o[2], o[3], n_i, 0.28)
                if o[2] > 0.5:
                    seg_box(trim, b + d_i * 0.3, a - d_i * 0.3, -0.15, 0.3, o[2] - 0.12, o[2], 'stone')
            if o[1] - o[0] < 3.5:      # eared stone-colour surround (SPEC)
                fw = 0.17
                seg_box(trim, b + d_i * fw, b, -0.06, 0.02, o[2] - (0 if o[2] < 0.3 else 0.12), o[3], 'surround')
                seg_box(trim, a, a - d_i * fw, -0.06, 0.02, o[2] - (0 if o[2] < 0.3 else 0.12), o[3], 'surround')
                seg_box(trim, b + d_i * (fw + 0.12), a - d_i * (fw + 0.12), -0.06, 0.02, o[3], o[3] + fw, 'surround')
                for e_ in (b + d_i * (fw + 0.12), a - d_i * 0.0):
                    seg_box(trim, e_, e_ - d_i * 0.12, -0.06, 0.02, o[3] - 0.32, o[3], 'surround')
                if FLOOR_Z[1] <= o[2] < FLOOR_Z[2]:                     # floor 1: cornice hoods
                    seg_box(trim, b + d_i * 0.45, a - d_i * 0.45, -0.2, 0.02, o[3] + fw, o[3] + fw + 0.14, 'frame')
            else:
                seg_box(trim, b + d_i * 0.2, a - d_i * 0.2, -0.07, 0.02, o[3], o[3] + 0.2, 'frame')
        sweep(trim, i1 + d_i * 0.6, i0 - d_i * 0.6, PROF_EAVE, EAVE_Z - 0.8, 'frame', -n_i)
        # wall lanterns on iron brackets between ground-floor axes (lit at night)
        for kk in range(3, len(ax_i), 3):        # every third bay
            um = (ax_i[kk - 1] + ax_i[kk]) / 2
            wp = i0 + d_i * um - n_i * 0.05
            arm_end = wp - n_i * 0.55
            _prism(trim, Vector((wp.x, wp.y, 3.6)), Vector((arm_end.x, arm_end.y, 3.6)), 0.02, 0.02, 'metal', seg=6)
            _prism(trim, Vector((wp.x, wp.y, 3.1)), Vector((arm_end.x, arm_end.y, 3.6)), 0.012, 0.012, 'metal', seg=5)
            lantern(trim, arm_end, 3.6, 3.0, r=0.13)
            add_light(bpy.context.scene.collection, 'L_street_wall', (arm_end.x, arm_end.y, 3.2), 70, color=(1.0, 0.78, 0.5))
        for zc in FLOOR_Z[1:]:
            sweep(trim, i1, i0, PROF_BAND, zc - 0.25, 'frame', -n_i)

        # ---- interior: corridor wall + partitions
        c0, c1 = w['c']
        Lc = (c1 - c0).length
        d_c = (c1 - c0) / Lc
        # partition positions: outer-facade midpoints between window axes, every 2nd gap
        parts = []
        pstep = 1 if sp > 6.0 else 2
        for k in range(1, len(ax)):
            if k % pstep:
                continue
            mid = o0 + d_o * ((ax[k - 1] + ax[k]) / 2)
            t = project_t(mid, c0, c1)
            if 1.5 < t < Lc - 1.5:
                parts.append((t, mid))
        if pas_axis is not None:     # make the passage a single bay between two partitions
            mid_p = o0 + d_o * pas_axis
            tp = project_t(mid_p, c0, c1)
            parts = [p for p in parts if abs(p[0] - tp) > 3.2]
            for s in (-1, 1):
                q = o0 + d_o * (pas_axis + s * sp * 0.5)
                parts.append((project_t(q, c0, c1), q))
            parts.sort()
            if w['name'] == 'S':     # the room west of the gate is two bays long: it holds the cellar stair
                west_p = [p for p in parts if (p[1] - mid_p).dot(d_o) < -sp * 0.75]
                if west_p:
                    parts.remove(max(west_p, key=lambda p: (p[1] - mid_p).dot(d_o)))
        ts = [0.0] + [p[0] for p in parts] + [Lc]
        k_stair = (min(range(len(ts) - 1), key=lambda k: abs((ts[k] + ts[k + 1]) / 2 - stair_frac * Lc))
                   if w['name'] == stair_wing else None)
        door_ops = []
        for k, (z0, z1) in enumerate(stories):
            for ta, tb in zip(ts, ts[1:]):
                if tb - ta > 2.2:
                    tm = (ta + tb) / 2
                    hw = 1.9 if (pas_t is not None and k == 0 and abs(tm - project_t(o0 + d_o * pas_axis, c0, c1)) < 2) else 0.8
                    hh = 4.6 if hw > 1 else 3.1
                    if k_stair is not None and abs(tm - (ts[k_stair] + ts[k_stair + 1]) / 2) < 1e-6:
                        hw, hh = 1.5, 4.3       # arched opening into the staircase hall
                    door_ops.append((tm - hw, tm + hw, z0, z0 + hh))
        wall(walls, c0, c1, 0, EAVE_Z, PART_T, 'plaster_int', door_ops, off=-PART_T / 2)
        finish_side(clad, c0, c1, door_ops, -PART_T / 2 - 0.02)
        for o in door_ops:
            if o[1] - o[0] >= 2:
                arch_head(walls, c0 + d_c * o[0], c0 + d_c * o[1], o[3], -PART_T / 2, PART_T, 'plaster_int')
            interior_door(trim, c0, d_c, o, PART_T, leaves=(o[1] - o[0]) < 2, side=-1)

        # Knights' Hall (Rytierska sála): the ground-floor bays east of the main gate form one hall
        tp_gate = project_t(o0 + d_o * pas_axis, c0, c1) if pas_axis is not None else None
        hall_parts = set()
        if w['name'] == 'S' and tp_gate is not None:
            east = sorted((t for t, q in parts if t > tp_gate + sp * 0.8))
            hall_parts = set(east[:2])
            HALL_PARTS.extend(c0 + d_c * t for t in hall_parts)
        for pi, (t, q) in enumerate(parts):
            pc = c0 + d_c * t
            # extend to the outer wall's inner face
            far = line_x((pc, pc + w['n']), (o0 + n_o * OUTER_T, o1 + n_o * OUTER_T))
            plen = (far - pc).length
            is_pass_edge = pas_axis is not None and abs((q - o0).dot(d_o) - pas_axis) < sp * 0.6
            dops = []
            for k, (z0, z1) in enumerate(stories):
                if is_pass_edge and k == 0:
                    continue
                if k == 0 and t in hall_parts:
                    dops.append((0.25, plen - 0.25, -0.1, FLOOR_Z[1] - SLAB_T - 0.9))   # open to the hall, beam above
                    continue
                dp = plen * 0.72
                dops.append((dp - 0.75, dp + 0.75, z0, z0 + 3.2))
            wall(walls, pc, far, 0, EAVE_Z, PART_T, 'plaster_int', dops, off=-PART_T / 2)
            finish_side(clad, pc, far, dops, PART_T / 2)
            finish_side(clad, pc, far, dops, -PART_T / 2 - 0.02)
            dpf = (far - pc).normalized()
            for o in dops:
                if o[1] - o[0] > 3:
                    arch_head(walls, pc + dpf * o[0], pc + dpf * o[1], o[3], -PART_T / 2, PART_T, 'plaster_int')
                    continue
                interior_door(trim, pc, dpf, o, PART_T, leaves=True, side=1 if pi % 2 else -1)

        # stair room
        ti_stair = None
        if w['name'] == stair_wing:
            ti_stair = min(range(len(ts) - 1), key=lambda k: abs((ts[k] + ts[k + 1]) / 2 - stair_frac * Lc))
            stair_room = (w, ts[ti_stair], ts[ti_stair + 1], o0, o1, n_o)
            sd = c0 + d_c * ((ts[ti_stair] + ts[ti_stair + 1]) / 2)
            NAV['stair_door_room'] = list(sd + w['n'] * 1.2)
            NAV['stair_door_corr'] = list(sd - w['n'] * 1.6)
        tp_pass = project_t(o0 + d_o * pas_axis, c0, c1) if pas_axis is not None else None
        if w['name'] == 'W':      # door into the SW corner room (last bay of the west wing)
            tm_last = (ts[-2] + ts[-1]) / 2
            NAV['sw_corner_door_corr'] = list(c0 + d_c * tm_last - w['n'] * 1.6)
            NAV['sw_corner_door_room'] = list(c0 + d_c * tm_last + w['n'] * 1.5)
        for k in range(len(ts) - 1):
            ta, tb = ts[k], ts[k + 1]
            tm = (ta + tb) / 2
            pc = c0 + d_c * tm
            far = line_x((pc, pc + w['n']), (o0 + n_o * OUTER_T, o1 + n_o * OUTER_T))
            special = (k == ti_stair) or (tp_pass is not None and abs(tm - tp_pass) < 2.5)
            far_a = line_x((c0 + d_c * ta, c0 + d_c * ta + w['n']), (o0 + n_o * OUTER_T, o1 + n_o * OUTER_T))
            far_b = line_x((c0 + d_c * tb, c0 + d_c * tb + w['n']), (o0 + n_o * OUTER_T, o1 + n_o * OUTER_T))
            rooms.append(dict(c=(pc + far) / 2, n=w['n'], d=d_c, L=tb - ta, D=(far - pc).length,
                              far_a=far_a, far_b=far_b,
                              stair=k == ti_stair, passage=tp_pass is not None and abs(tm - tp_pass) < 2.5,
                              wall_a=c0 + d_c * ta, wall_b=c0 + d_c * tb, special=special))
        corridor_segs.append((corr_in[wi], corr_in[(wi + 1) % 4], w['n'], CORR_W - PART_T / 2))
        ci0 = w['i'][0] + w['n'] * (COURT_T + CORR_W / 2)
        ci1 = w['i'][1] + w['n'] * (COURT_T + CORR_W / 2)
        Lci = (ci1 - ci0).length
        for k in range(1, int(Lci / 9)):
            corridor_pts.append(ci0.lerp(ci1, k / int(Lci / 9)))

    # ---- floors, ceilings, courtyard
    stair_hole = None
    if stair_room:
        w, ta, tb, o0, o1, n_o = stair_room
        c0, c1 = w['c']
        d_c = (c1 - c0).normalized()
        land = 3.0
        pa = c0 + d_c * (ta + PART_T / 2) + w['n'] * (PART_T / 2 + land)
        pb = c0 + d_c * (tb - PART_T / 2) + w['n'] * (PART_T / 2 + land)
        fa = line_x((pa, pa + w['n']), (o0 + n_o * OUTER_T, o1 + n_o * OUTER_T))
        fb = line_x((pb, pb + w['n']), (o0 + n_o * OUTER_T, o1 + n_o * OUTER_T))
        stair_hole = [pa, pb, fb, fa]
        build_stairs(walls, floors, ramps, trim, pa, pb, fb, fa, w['n'], d_c)

    cellar_hole = build_cellar(walls, floors, trim, ramps, rooms, W, coll)
    slab_out, slab_in = offset_poly(OUTER, -0.4), offset_poly(INNER, 0.4)
    for k, z in enumerate(FLOOR_Z + [EAVE_Z]):
        loops = [slab_out, slab_in]
        if k == 0 and cellar_hole:
            loops = loops + [cellar_hole]
        if stair_hole and 0 < k < len(FLOOR_Z):
            loops = [slab_out, slab_in, stair_hole]
        if k == len(FLOOR_Z):      # Crown Tower stair well through the top ceiling
            ccen = sum(tower_sq[0][1], Vector((0, 0))) / 4
            loops = loops + [circle(ccen, SPIRAL_R + 0.6)]
        top = 'marble' if k == 0 else ('plaster_int' if k == len(FLOOR_Z) else 'parquet')
        slab(floors, loops, z, SLAB_T, top, 'plaster_int', 'plaster_int')
    slab(floors, [INNER], 0.0, 0.6, 'cobbles', 'stone', 'stone')

    # ---- roof (ring hip roof)
    ov = 0.9
    oo = offset_poly(OUTER, ov)
    ii = offset_poly(INNER, -ov)
    ridge = [(OUTER[k] + INNER[k]) / 2 for k in range(4)]
    # move the ridge so slopes get roughly equal pitch per wing
    for k in range(4):
        a = Vector((oo[k].x, oo[k].y, EAVE_Z))
        b = Vector((oo[(k + 1) % 4].x, oo[(k + 1) % 4].y, EAVE_Z))
        c = Vector((ridge[(k + 1) % 4].x, ridge[(k + 1) % 4].y, RIDGE_Z))
        dd = Vector((ridge[k].x, ridge[k].y, RIDGE_Z))
        towers_xy = [[Vector(p) for p in t[1]] for t in tower_sq]
        poly_minus_squares(roof, [a, b, c, dd], towers_xy, 'roof_palace')
        a2 = Vector((ii[(k + 1) % 4].x, ii[(k + 1) % 4].y, EAVE_Z))
        b2 = Vector((ii[k].x, ii[k].y, EAVE_Z))
        poly_minus_squares(roof, [a2, b2, dd, c], towers_xy, 'roof_palace')
        for t_ in (0.3, 0.7):         # brick chimneys on the courtyard slopes (SPEC)
            ei = Vector(ii[k]).lerp(Vector(ii[(k + 1) % 4]), t_)
            er = Vector(ridge[k]).lerp(Vector(ridge[(k + 1) % 4]), t_)
            cp_ = ei.lerp(er, 0.72)
            zc_ = EAVE_Z + (RIDGE_Z - EAVE_Z) * 0.72
            q_ = [cp_ + Vector((-0.45, -0.32)), cp_ + Vector((0.45, -0.32)), cp_ + Vector((0.45, 0.32)), cp_ + Vector((-0.45, 0.32))]
            roof.box(q_, zc_ - 1.0, RIDGE_Z + 1.1, 'plaster')
            roof.box([cp_ + Vector((-0.55, -0.42)), cp_ + Vector((0.55, -0.42)), cp_ + Vector((0.55, 0.42)), cp_ + Vector((-0.55, 0.42))],
                     RIDGE_Z + 1.1, RIDGE_Z + 1.25, 'stone')
        # underside soffits
        roof.poly([Vector((OUTER[(k + 1) % 4].x, OUTER[(k + 1) % 4].y, EAVE_Z - 0.01)),
                   Vector((OUTER[k].x, OUTER[k].y, EAVE_Z - 0.01)),
                   Vector((oo[k].x, oo[k].y, EAVE_Z - 0.01)),
                   Vector((oo[(k + 1) % 4].x, oo[(k + 1) % 4].y, EAVE_Z - 0.01))], 'frame')
        # dormers on the outer slope
        # SPEC dormer counts: S 8, E 6, N 8, W 8 on the outer slopes; courtyard slopes carry dormers too
        build_dormers(roof, win, oo[k], oo[(k + 1) % 4], ridge[k], ridge[(k + 1) % 4], n=[8, 6, 8, 8][k])
        build_dormers(roof, win, ii[(k + 1) % 4], ii[k], ridge[(k + 1) % 4], ridge[k], n=[5, 3, 5, 4][k], gable=True)
        if not FAST and k == 1:      # second, small attic row only on the E slope (photo 15); S/N/W show one row (04, 11)
            build_dormers(roof, win, oo[k], oo[(k + 1) % 4], ridge[k], ridge[(k + 1) % 4], n=[8, 6, 8, 8][k] - 1,
                          lo=0.58, hi=0.72, hw=0.42, h=0.95)
        # ridge and hip tiles (half-round), zinc gutters on both eaves
        R0 = Vector((ridge[k].x, ridge[k].y, RIDGE_Z + 0.06))
        R1 = Vector((ridge[(k + 1) % 4].x, ridge[(k + 1) % 4].y, RIDGE_Z + 0.06))
        if k == 0:      # state flag on the south-wing ridge (seen above the Honour Court in photos)
            fp = R0.lerp(R1, 0.5)
            _prism(trim, fp, fp + Vector((0, 0, 9.0)), 0.07, 0.05, 'frame', seg=8)
            sph_mb_ring(trim, fp.to_2d(), fp.z + 9.0, 0.09, 'gold', seg=6)
            fa_, fb_ = fp.to_2d() + Vector((0.07, 0)), fp.to_2d() + Vector((3.6, 0))
            for i_ in range(24):
                for j_ in range(8):
                    u0, u1, v0, v1 = i_ / 24, (i_ + 1) / 24, j_ / 8, (j_ + 1) / 8
                    Pf = lambda u, v: Vector((fa_.x + (fb_.x - fa_.x) * u, fa_.y, fp.z + 6.4 + 2.4 * v))
                    trim.poly([Pf(u0, v0), Pf(u1, v0), Pf(u1, v1), Pf(u0, v1)], 'flag_sk', uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        if not any(point_in_poly(q.x, q.y, sq_) for q in (R0.lerp(R1, 0.5),) for _, sq_, _p in tower_sq):
            _prism(trim, R0, R1, 0.16, 0.16, 'roof_palace', seg=6)
        for corner in (oo[k], ii[k]):
            _prism(trim, Vector((corner.x, corner.y, EAVE_Z + 0.05)), R0, 0.13, 0.13, 'roof_palace', seg=6)
        for e0, e1, nrm in ((oo[k], oo[(k + 1) % 4], None), (ii[(k + 1) % 4], ii[k], None)):
            _prism(trim, Vector((e0.x, e0.y, EAVE_Z - 0.08)), Vector((e1.x, e1.y, EAVE_Z - 0.08)), 0.09, 0.09, 'zinc', seg=6)

    # ---- towers
    for name, sq, prm in tower_sq:
        build_tower(walls, trim, win, roof, floors, sq, prm, name, ramps)

    # ---- courtyard well (15th c., 80-85 m deep)
    well(trim, Vector((19.3, -7.1)))        # OSM man_made=water_well inside the courtyard

    furn = MB('Palace_Furnishing')
    global SMOOTH
    SMOOTH = MB('Palace_Smooth')
    furnish(furn, rooms, corridor_pts, coll)
    call_v2('v2_interior', 'build', dict(locals()), coll)
    corridor_vaults(SMOOTH, corridor_segs)
    probes = {}
    south = [r for r in rooms if not r['special'] and abs(r['n'].y) > 0.9 and r['n'].y < 0]
    if south:
        r = max(south, key=lambda r: r['L'] * r['D'])
        z = FLOOR_Z[1] + 1.65
        cam = r['c'] - r['n'] * (r['D'] * 0.42) - r['d'] * (r['L'] * 0.42)
        tgt = r['c'] + r['n'] * (r['D'] * 0.5) + r['d'] * (r['L'] * 0.5)
        probes['interior_room'] = [[cam.x, cam.y, z], [tgt.x, tgt.y, z + 0.6]]
    if corridor_pts:
        a, b = corridor_pts[0], corridor_pts[min(3, len(corridor_pts) - 1)]
        probes['interior_corridor'] = [[a.x, a.y, FLOOR_Z[1] + 1.65], [b.x, b.y, FLOOR_Z[1] + 1.5]]
    if stair_hole:
        pa, pb, fb, fa = stair_hole
        c = (pa + pb + fa + fb) / 4
        cam = pa + (pb - pa) * 0.22 - (fa - pa).normalized() * 1.2      # off the central pier, up the open well
        tg = fa + (fb - fa) * 0.6
        probes['stairs'] = [[cam.x, cam.y, FLOOR_Z[1] + 1.65], [tg.x, tg.y, FLOOR_Z[1] + 5.0]]
    ring = offset_poly(INNER, COURT_T + CORR_W / 2)
    NAV['corr_ring'] = [list(v) for v in ring]          # SW, SE, NE, NW corridor centre corners
    sw = tower_sq[0][1]
    cen = sum(sw, Vector((0, 0))) / 4
    for k in range(4):
        m = (sw[k] + sw[(k + 1) % 4]) / 2
        if dist_to_poly(m.x, m.y, OUTER) > 2.0:
            NAV.setdefault('crown_doors', []).append([list(m + (m - cen).normalized() * 1.2), list(m - (m - cen).normalized() * 1.2)])
    NAV['crown_center'] = list(cen)
    probes['nav'] = {k: [float(x) for x in v] if v and not isinstance(v[0], list) else
                     [[float(x) for x in q] if not isinstance(q[0], list) else [[float(y) for y in r] for r in q] for q in v]
                     for k, v in NAV.items()}
    json.dump(probes, open(os.path.join(OUT, 'probes.json'), 'w'))
    furn_col = MB('Palace_Furniture-col')
    exhibits(furn_col, rooms)
    obs = [mb.build(coll) for mb in (walls, trim, win, floors, roof, ramps, furn, clad, furn_col, SMOOTH)]
    rp = bpy.data.objects.get('Palace_StairRamps-colonly')
    if rp:
        rp.display_type = 'WIRE'
        rp.hide_render = True
    return obs


# per-facade composition counted on photos (data/ref/v2/SPEC.md)
FACADES = {
    'S': dict(n=9, w=1.6, h=[2.9, 3.1, 3.0, 2.4], arch=(1, 2), margin=1.4),
    'N': dict(n=9, w=1.55, h=[2.9, 3.0, 2.9, 2.4], hood=(2,), margin=1.4),
    'E': dict(n=6, w=1.55, h=[2.6, 3.0, 2.9, 2.4], arch=(1, 2), blank=(0,), skip={(1, 2)}, corner=True, margin=2.6),
    'W': dict(n=12, w=1.0, h=[1.7, 1.9, 1.9, 1.6], jitter=0.45, blind={(2, 3), (3, 8), (1, 10)}, margin=1.2),
}
TOWER_SIZE = [9.6, 8.4, 8.4, 8.4]    # SW (Crown Tower), SE, NE, NW shaft widths (photo-scaled)
TOWER_PROTRUDE = 0.5


def add_light(coll, name, loc, power, color=(1.0, 0.82, 0.6), radius=0.3):
    ld = bpy.data.lights.new(name, 'POINT')
    ld.energy = power
    ld.color = color
    ld.shadow_soft_size = radius
    try:
        ld.use_shadow = False
    except Exception:
        pass
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    coll.objects.link(ob)
    return ob


def lantern(mb, c, z_ceiling, z_bottom, r=0.17):
    """Hexagonal hanging lantern on a link chain: ribs, frosted panes, caps, finial."""
    h = 0.5
    z0, z1 = z_bottom, z_bottom + h
    k = 0
    z = z1 + 0.18
    while z < z_ceiling - 0.06:         # chain links, alternating orientation
        ang = (k % 2) * math.pi / 2
        u = Vector((math.cos(ang), math.sin(ang), 0)) * 0.018
        _prism(mb, Vector((c.x, c.y, z)) - u, Vector((c.x, c.y, z)) + u, 0.006, 0.006, 'metal', seg=4)
        _prism(mb, Vector((c.x, c.y, z)) + u, Vector((c.x, c.y, z + 0.05)) + u, 0.005, 0.005, 'metal', seg=4)
        _prism(mb, Vector((c.x, c.y, z)) - u, Vector((c.x, c.y, z + 0.05)) - u, 0.005, 0.005, 'metal', seg=4)
        z += 0.055
        k += 1
    hexp = [c + Vector((math.cos(math.pi * j / 3), math.sin(math.pi * j / 3))) * r for j in range(6)]
    for j in range(6):
        a, b = hexp[j], hexp[(j + 1) % 6]
        _prism(mb, Vector((a.x, a.y, z0)), Vector((a.x, a.y, z1)), 0.012, 0.012, 'metal', seg=4)
        mb.poly([Vector((a.x, a.y, z0 + 0.03)), Vector((b.x, b.y, z0 + 0.03)), Vector((b.x, b.y, z1 - 0.03)), Vector((a.x, a.y, z1 - 0.03))], 'lamp_glass')
    ap = Vector((c.x, c.y, z1 + 0.16))
    for j in range(6):
        a, b = hexp[j] + (hexp[j] - c) * 0.25, hexp[(j + 1) % 6] + (hexp[(j + 1) % 6] - c) * 0.25
        mb.poly([Vector((a.x, a.y, z1)), Vector((b.x, b.y, z1)), ap], 'metal')
        mb.poly([Vector((b.x, b.y, z0)), Vector((a.x, a.y, z0)), Vector((c.x, c.y, z0 - 0.09))], 'metal')
    _prism(mb, ap, ap + Vector((0, 0, 0.06)), 0.02, 0.012, 'metal', seg=6)
    ellipsoid(mb, Vector((c.x, c.y, (z0 + z1) / 2)), 0.05, 0.05, 0.08, 0, 0, 'lamp', subdiv=1)


def lathe(mb, c, z, prof, mat, seg=None):
    """Surface of revolution hanging from a ceiling at z: prof = [(radius, dz<=0), ...] from rim to axis."""
    seg = seg or (16 if WEB else 40)
    rings = [[Vector((c.x + r * math.cos(2 * math.pi * k / seg), c.y + r * math.sin(2 * math.pi * k / seg), z + dz))
              for k in range(seg)] for r, dz in prof]
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(seg):
            j = (k + 1) % seg
            quad = [A[k], A[j], B[j], B[k]]
            if geometry.normal(quad).z > 0:
                quad.reverse()
            mb.poly(quad, mat)


def chandelier(mb, c, z, r):
    """Baroque chandelier: turned stem with knops, 8 S-curved arms, drip pans, candles."""
    top = Vector((c.x, c.y, z + 1.62))
    _prism(mb, top, Vector((c.x, c.y, z - 0.45)), 0.025, 0.035, 'gold', seg=6)
    for zz, rr in ((z + 0.9, 0.06), (z + 0.35, 0.09), (z - 0.05, 0.16), (z - 0.4, 0.1)):
        ellipsoid(mb, Vector((c.x, c.y, zz)), rr, rr, rr * 0.8, 0, 0, 'gold', subdiv=1 if rr > 0.12 else 0)
    for k in range(8):
        a = 2 * math.pi * k / 8
        dvec = Vector((math.cos(a), math.sin(a), 0))
        pts = []
        spans = 4 if WEB else 6
        for j in range(spans + 1):             # S-curve: down-out then up to the pan
            t = j / spans
            rad = 0.08 + r * t
            h = -0.12 * math.sin(math.pi * t) + 0.2 * t * t
            pts.append(Vector((c.x, c.y, z - 0.05)) + dvec * rad + Vector((0, 0, h)))
        for p0, p1 in zip(pts, pts[1:]):
            _prism(mb, p0, p1, 0.012, 0.011, 'gold', seg=4)
        tip = pts[-1]
        slab(mb, [circle(tip.to_2d(), 0.06, 6)], tip.z + 0.015, 0.02, 'gold', 'gold', 'gold')   # drip pan
        _prism(mb, tip + Vector((0, 0, 0.015)), tip + Vector((0, 0, 0.17)), 0.013, 0.013, 'candle', seg=4)
        ellipsoid(mb, tip + Vector((0, 0, 0.195)), 0.012, 0.012, 0.025, 0, 0, 'lamp', subdiv=0)


def hang_painting(mb, base, inward, hw, h0, h1, mat):
    """Gilded frame (4 bars) + canvas facing `inward`, centred on wall point `base`."""
    t = Vector((-inward.y, inward.x))           # canvas tangent so the quad normal == inward
    fw = 0.09
    p0, p1 = base - t * hw, base + t * hw
    for q0, q1, z0, z1 in ((p0, p1, h0, h0 + fw), (p0, p1, h1 - fw, h1),
                           (p0, p0 + t * fw, h0, h1), (p1 - t * fw, p1, h0, h1)):
        a, b = q0 + inward * 0.0, q1 + inward * 0.0
        mb.box([a, b, b + inward * 0.07, a + inward * 0.07], z0, z1, 'gold')
    c0, c1 = p0 + t * fw + inward * 0.03, p1 - t * fw + inward * 0.03
    mb.poly([Vector((c0.x, c0.y, h0 + fw)), Vector((c1.x, c1.y, h0 + fw)),
             Vector((c1.x, c1.y, h1 - fw)), Vector((c0.x, c0.y, h1 - fw))], mat,
            uv=[(0, 0), (1, 0), (1, 1), (0, 1)])


FLOOR_TINT = ['wall_f0', 'wall_f1', 'wall_f2', 'wall_f3']


def dado_panels(mb, a, b, z0, ops, off):
    """Raised moulded panel frames on the dado between openings, ~1 m apart."""
    a, b = Vector(a[:2]), Vector(b[:2])
    L = (b - a).length
    if L < 1.2:
        return
    d = (b - a) / L
    sgn = 1 if off >= 0 else -1
    o_face = off + (0.03 if off >= 0 else 0.0)
    lo, hi = (o_face, o_face + 0.018) if sgn > 0 else (o_face - 0.018, o_face)
    blocked = sorted((o[0], o[1]) for o in ops if o[2] < z0 + 0.95)
    u = 0.25
    while u + 0.8 < L - 0.25:
        if any(b0 - 0.1 < u + 0.8 and u < b1 + 0.1 for b0, b1 in blocked):
            u += 0.25
            continue
        p0, p1 = a + d * u, a + d * (u + 0.8)
        for z_a, z_b in ((z0 + 0.18, z0 + 0.22), (z0 + 0.78, z0 + 0.82)):
            seg_box(mb, p0, p1, lo, hi, z_a, z_b, 'door_case')
        seg_box(mb, p0, p0 + d * 0.04, lo, hi, z0 + 0.18, z0 + 0.82, 'door_case')
        seg_box(mb, p1 - d * 0.04, p1, lo, hi, z0 + 0.18, z0 + 0.82, 'door_case')
        u += 1.0


def finish_side(mb, a, b, openings, off):
    """Per-storey wall finish on one face of a wall a->b: dado panelling + tinted plaster."""
    for zi, z0 in enumerate(FLOOR_Z):
        z1 = (FLOOR_Z[zi + 1] if zi + 1 < len(FLOOR_Z) else EAVE_Z) - SLAB_T
        ops = [o for o in openings if o[3] > z0 and o[2] < z1]
        wall(mb, a, b, z0 + 1.05, z1 - 0.42, 0.02, FLOOR_TINT[zi], ops, off=off)
        wall(mb, a, b, z0, z0 + 1.0, 0.03, 'dado', ops, off=off)
        dado_panels(mb, a, b, z0, ops, off)
        wall(mb, a, b, z0 + 1.0, z0 + 1.05, 0.05, 'door_case', ops, off=off if off >= 0 else off - 0.02)
        wall(mb, a, b, z0, z0 + 0.14, 0.05, 'joinery', ops, off=off if off >= 0 else off - 0.02)


def chapel(mb, r, z0):
    """Music Hall in the former palace chapel (north wing, SPEC): white room, organ on a dais
    against the outer wall. Seating and harpsichord come from v2_interior."""
    c, n, d = r['c'], r['n'], r['d']
    q = lambda p, hw, hd: [p - d * hw - n * hd, p + d * hw - n * hd, p + d * hw + n * hd, p - d * hw + n * hd]
    for nm_, col_ in (('ebony', (0.05, 0.04, 0.04)), ('oak_honey', (0.45, 0.2, 0.06)), ('organ_white', (0.88, 0.87, 0.84)), ('dais_grey', (0.36, 0.37, 0.39))):
        if nm_ not in MATS:
            make_mat(nm_, None, color=col_, rough=0.5, spec=0.4)
    back = c + n * (r['D'] * 0.5 - 0.15)                       # curved grey dais (ref31), one 0.15 m step ring
    ax, ay = min(r['L'] * 0.4, 3.4), 2.0
    for grow, top in ((0.35, z0 + 0.15), (0.0, z0 + 0.3)):
        loop = [back + d * ((ax + grow) * math.cos(math.pi * k / 16)) - n * ((ay + grow) * math.sin(math.pi * k / 16)) for k in range(17)]
        if poly_area([(v.x, v.y) for v in loop]) < 0:
            loop.reverse()
        slab(mb, [loop], top, top - z0, 'dais_grey', 'dais_grey', 'dais_grey')
    base = z0 + 0.3
    org = c + n * (r['D'] * 0.5 - 0.6)
    # asymmetric light-oak case (ref31), seen from the audience (looking along +n): tall narrow pipe tower
    # on the LEFT, wider main case right of it; oak lower case with central white panels, gold front pipes
    sl = 1 if d.dot(Vector((-n.y, n.x))) > 0 else -1             # +d is the audience's left when sl > 0
    h_room = (FLOOR_Z[2] - SLAB_T - z0) if len(FLOOR_Z) > 2 else 5.1
    for off, hw, h_top, npipe, prof in ((1.15, 0.5, h_room - 0.62, 9, 'peak'), (-0.35, 1.0, h_room - 1.05, 17, 'vee')):   # organ wall up to the ceiling
        p = org + d * (sl * off)
        mb.box(q(p + n * 0.1, hw, 0.5), base, base + 1.6, 'oak_honey')          # solid cabinet, closed back to the wall
        npan = 2 if hw < 0.6 else 4
        pw_ = (hw - 0.08) / npan
        for k in range(npan):                                                    # pale panels inset in an oak frame
            pc_ = p - n * 0.403 + d * ((k + 0.5) / npan * 2 * (hw - 0.08) - (hw - 0.08))
            mb.box(q(pc_, pw_ - 0.05, 0.003), base + 0.18, base + 1.45, 'organ_white')
            for sx_ in (-1, 1):                                                  # stiles between the panels
                mb.box(q(pc_ - n * 0.012 + d * (sx_ * (pw_ - 0.025)), 0.03, 0.015), base, base + 1.6, 'oak_honey')
        for z_a, z_b in ((base, base + 0.18), (base + 1.45, base + 1.6)):       # top and bottom rails
            mb.box(q(p - n * 0.415, hw, 0.015), z_a, z_b, 'oak_honey')
        mb.box(q(p + n * 0.1, hw + 0.04, 0.54), base + 1.6, base + 1.7, 'oak_honey')
        mb.box(q(p + n * 0.2, hw, 0.42), base + 1.7, base + h_top, 'oak_honey')
        mb.box(q(p - n * 0.2, hw - 0.1, 0.035), base + 1.72, base + h_top - 0.03, 'ebony')   # dark recessed backing behind the pipes
        mb.box(q(p, hw + 0.05, 0.45), base + h_top, base + h_top + 0.12, 'oak_honey')
        for sgn in (-1, 1):                                     # case stiles framing the pipe field
            mb.box(q(p + d * (sgn * (hw - 0.05)) - n * 0.3, 0.05, 0.08), base + 1.7, base + h_top, 'oak_honey')
        for k in range(npipe):
            t = (k + 0.5) / npipe
            pp = p - n * 0.3 + d * (sl * (0.5 - t) * 2 * (hw - 0.14))   # k runs left -> right for the audience
            f = 0.8 + 0.2 * math.sin(math.pi * t) if prof == 'peak' else 0.62 + 0.38 * abs(2 * t - 1)
            hgt = (h_top - 2.15) * f
            pr_ = min(0.034, (hw - 0.14) / npipe * 0.9)
            _prism(mb, Vector((pp.x, pp.y, base + 1.9)), Vector((pp.x, pp.y, base + 1.9 + hgt)), pr_, pr_, 'gold', seg=6)
            _prism(mb, Vector((pp.x, pp.y, base + 1.71)), Vector((pp.x, pp.y, base + 1.9)), 0.01, pr_, 'gold', seg=6)
            if npipe > 8:          # second, shorter rank behind the facade pipes
                pb_ = pp + n * 0.1 + d * (sl * (hw - 0.14) / npipe)
                _prism(mb, Vector((pb_.x, pb_.y, base + 1.9)), Vector((pb_.x, pb_.y, base + 1.9 + hgt * 0.7)), pr_ * 0.8, pr_ * 0.8, 'gold', seg=5)
    pos = org - d * (sl * 1.85) - n * 0.2                       # small positive organ on the right
    mb.box(q(pos, 0.32, 0.3), base, base + 0.9, 'organ_white')
    mb.box(q(pos, 0.34, 0.32), base + 0.9, base + 1.6, 'oak_honey')
    cons = org - d * (sl * 0.35) - n * 0.9                      # console + bench
    mb.box(q(cons, 0.6, 0.25), base, base + 1.0, 'oak_honey', top='ivory')
    mb.box(q(cons - n * 0.55, 0.55, 0.15), base, base + 0.5, 'oak_honey')


def exhibits(mb, rooms):
    """Museum furniture in the state rooms: glass vitrines on plinths and benches."""
    rng = random.Random(11)
    north = [r for r in rooms if not r['special'] and r['n'].y > 0.9]
    chapel_room = max(north, key=lambda r: r['L'] * r['D']) if north else None
    if chapel_room:
        chapel(mb, chapel_room, FLOOR_Z[1])
        NAV['chapel'] = list(chapel_room['c'] - chapel_room['n'] * (chapel_room['D'] * 0.4))
        print('CHAPEL', [round(v, 2) for v in NAV['chapel']], 'altar', [round(v, 2) for v in chapel_room['c'] + chapel_room['n'] * 3])
    for zi in (1, 2):
        z0 = FLOOR_Z[zi]
        for r in rooms:
            if r['special'] or r['L'] < 5 or r['D'] < 6 or (zi == 1 and r is chapel_room):
                continue
            if globals().get('ROOM_ROLES', {}).get((id(r), zi)) in ('music', 'state', 'exhibit_dark'):
                continue      # furnished by v2_interior (instruments / salon furniture)
            c, n, d = r['c'], r['n'], r['d']
            for k in (-1, 1):
                p = c + d * (k * r['L'] * 0.22)
                w2, d2 = 0.6, 0.45
                base = [p - d * w2 - n * d2, p + d * w2 - n * d2, p + d * w2 + n * d2, p - d * w2 + n * d2]
                mb.box(base, z0, z0 + 0.85, 'door', top='joinery')
                inner = [p - d * (w2 - 0.03) - n * (d2 - 0.03), p + d * (w2 - 0.03) - n * (d2 - 0.03),
                         p + d * (w2 - 0.03) + n * (d2 - 0.03), p - d * (w2 - 0.03) + n * (d2 - 0.03)]
                mb.box(inner, z0 + 0.85, z0 + 0.88, 'marble')
                # glass hood (4 panes + lid) and a gilded object inside
                hood = [Vector((q.x, q.y, 0)) for q in inner]
                for j in range(4):
                    qa, qb = hood[j], hood[(j + 1) % 4]
                    mb.poly([Vector((qa.x, qa.y, z0 + 0.88)), Vector((qb.x, qb.y, z0 + 0.88)),
                             Vector((qb.x, qb.y, z0 + 1.5)), Vector((qa.x, qa.y, z0 + 1.5))], 'glass')
                mb.poly([Vector((q.x, q.y, z0 + 1.5)) for q in hood], 'glass')
                for q in hood:                               # brass corner rails + lid rim
                    _prism(mb, Vector((q.x, q.y, z0 + 0.88)), Vector((q.x, q.y, z0 + 1.5)), 0.008, 0.008, 'gold', seg=4)
                for j in range(4):
                    qa, qb = hood[j], hood[(j + 1) % 4]
                    _prism(mb, Vector((qa.x, qa.y, z0 + 1.5)), Vector((qb.x, qb.y, z0 + 1.5)), 0.01, 0.01, 'gold', seg=4)
                lab = p - n * (d2 + 0.02) + d * 0.3                # caption plaque on the plinth front
                seg_box(mb, lab - d * 0.12, lab + d * 0.12, -0.01, 0.0, z0 + 0.6, z0 + 0.72, 'plaque')
                exhibit_object(SMOOTH, p, z0 + 0.88, rng)
            if r['L'] > 7:
                q = c + n * (r['D'] * 0.15)
                mb.box([q - d * 0.9 - n * 0.22, q + d * 0.9 - n * 0.22, q + d * 0.9 + n * 0.22, q - d * 0.9 + n * 0.22],
                       z0 + 0.3, z0 + 0.45, 'carpet', bottom='door')
                for sx in (-0.8, 0.8):
                    for sy in (-0.18, 0.18):
                        lp = q + d * sx + n * sy
                        mb.box([lp - d * 0.03 - n * 0.03, lp + d * 0.03 - n * 0.03, lp + d * 0.03 + n * 0.03, lp - d * 0.03 + n * 0.03],
                               z0, z0 + 0.3, 'gold')


EXHIBITS = {
    'chalice': ([(0.0, 0.0), (0.07, 0.0), (0.07, 0.01), (0.02, 0.03), (0.012, 0.09), (0.03, 0.11), (0.012, 0.13),
                 (0.02, 0.15), (0.065, 0.2), (0.075, 0.27), (0.07, 0.27), (0.06, 0.21), (0.0, 0.19)], 'gold'),
    'vase': ([(0.0, 0.0), (0.06, 0.0), (0.08, 0.04), (0.12, 0.14), (0.11, 0.24), (0.06, 0.31), (0.05, 0.35),
              (0.07, 0.38), (0.068, 0.385), (0.04, 0.36), (0.0, 0.35)], 'porcelain'),
    'goblet': ([(0.0, 0.0), (0.05, 0.0), (0.05, 0.008), (0.008, 0.02), (0.008, 0.1), (0.05, 0.13), (0.06, 0.2),
                (0.055, 0.2), (0.0, 0.14)], 'glass_art'),
}


def lathe_up(mb, c, z, prof, mat, seg=None):
    """Upright surface of revolution: prof = [(radius, height), ...] from axis bottom outward and up."""
    seg = seg or (12 if WEB else 32)
    rings = [[Vector((c.x + r * math.cos(2 * math.pi * k / seg), c.y + r * math.sin(2 * math.pi * k / seg), z + h))
              for k in range(seg)] for r, h in prof]
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(seg):
            j = (k + 1) % seg
            quad = [A[k], A[j], B[j], B[k]]
            out = (A[k] + B[j]) / 2 - Vector((c.x, c.y, (A[k].z + B[j].z) / 2))
            if geometry.normal(quad).dot(out) < 0:
                quad.reverse()
            mb.poly(quad, mat)


def exhibit_object(mb, c, z, rng):
    kind = rng.choice(list(EXHIBITS))
    prof, mat = EXHIBITS[kind]
    lathe_up(mb, c, z, prof, mat, seg=12)


def corridor_vaults(mb, segs, nseg=None, rise=0.85, bay=4.7):
    """Segmental barrel vault over each corridor with transverse arch bands (Baroque corridors)."""
    nseg = nseg or (8 if WEB else 12)
    for a, b, n, W in segs:
        d = (b - a).normalized()
        a, b = a + d * (W + PART_T), b - d * (W + PART_T)     # corner squares keep the flat ceiling
        L = (b - a).length
        for zi, z0 in enumerate(FLOOR_Z):
            z1 = FLOOR_Z[zi + 1] if zi + 1 < len(FLOOR_Z) else EAVE_Z
            zs = z1 - SLAB_T - rise - 0.02
            prof = [(W * (1 - math.cos(math.pi * k / nseg)) / 2, zs + rise * math.sin(math.pi * k / nseg)) for k in range(nseg + 1)]
            for k in range(nseg):
                (o0, h0), (o1, h1) = prof[k], prof[k + 1]
                p0, p1 = a + n * o0, a + n * o1
                q0, q1 = b + n * o0, b + n * o1
                mb.poly([Vector((p1.x, p1.y, h1)), Vector((q1.x, q1.y, h1)), Vector((q0.x, q0.y, h0)), Vector((p0.x, p0.y, h0))], 'plaster_int')
            # spandrel strips above the springing on both walls (close the gap to the flat ceiling)
            for o in (0.0, W):
                pa, pb = a + n * o, b + n * o
                mb.poly([Vector((pa.x, pa.y, zs)), Vector((pb.x, pb.y, zs)), Vector((pb.x, pb.y, z1 - SLAB_T)), Vector((pa.x, pa.y, z1 - SLAB_T))], 'plaster_int')
            for k in range(1, int(L / bay)):
                c = a + d * (k * bay)
                for j in range(nseg):
                    (o0, h0), (o1, h1) = prof[j], prof[j + 1]
                    for sd in (-0.2, 0.2):     # rib sides, facing along the corridor
                        e0, e1 = c + d * sd + n * o0, c + d * sd + n * o1
                        quad = [Vector((e0.x, e0.y, h0 - 0.15)), Vector((e1.x, e1.y, h1 - 0.15)),
                                Vector((e1.x, e1.y, h1)), Vector((e0.x, e0.y, h0))]
                        oriented_poly(mb, quad, Vector((d.x, d.y, 0)) * (1 if sd > 0 else -1), 'frame')
                    a0, a1 = c - d * 0.2 + n * o0, c - d * 0.2 + n * o1
                    b0, b1 = c + d * 0.2 + n * o0, c + d * 0.2 + n * o1
                    mid_o = (o0 + o1) / 2
                    down = Vector((-(n.x) * (mid_o - W / 2), -(n.y) * (mid_o - W / 2), zs - (h0 + h1) / 2 + 0.15)).normalized()
                    oriented_poly(mb, [Vector((a1.x, a1.y, h1 - 0.15)), Vector((b1.x, b1.y, h1 - 0.15)),
                                       Vector((b0.x, b0.y, h0 - 0.15)), Vector((a0.x, a0.y, h0 - 0.15))], down, 'frame')
            # moulded cornice at the springing
            for o, s_ in ((0.0, 1), (W, -1)):
                pa, pb = a + n * o, b + n * o
                mb.box([pa, pb, pb + n * (0.14 * s_), pa + n * (0.14 * s_)], zs - 0.2, zs, 'frame')


def oval_ring(mb, c, n, rx, rz, z, t, mat, seg=20):
    """Vertical oval moulding (stucco cartouche) on a wall: centre c, wall normal n."""
    tng = Vector((-n.y, n.x))
    pts = [(c + tng * (rx * math.cos(2 * math.pi * k / seg)), z + rz * math.sin(2 * math.pi * k / seg)) for k in range(seg + 1)]
    for (p0, z0), (p1, z1) in zip(pts, pts[1:]):
        a0, a1 = p0 + n * 0.0, p1 + n * 0.0
        b0, b1 = p0 + n * t, p1 + n * t
        mb.poly([Vector((b0.x, b0.y, z0)), Vector((b1.x, b1.y, z1)), Vector((b1.x, b1.y, z1 + 0.08)), Vector((b0.x, b0.y, z0 + 0.08))], mat)
        mb.poly([Vector((a0.x, a0.y, z0)), Vector((a1.x, a1.y, z1)), Vector((b1.x, b1.y, z1)), Vector((b0.x, b0.y, z0))], mat)


def c_scroll(mb, c, z, out, up, mat, r0=0.16, turns=1.35, seg=22):
    """Gilded C-scroll (volute) in the wall plane: a tapering spiral tube."""
    pts = []
    for k in range(seg + 1):
        t = k / seg
        r = r0 * (1 - 0.75 * t)
        a = math.pi * 0.5 + turns * 2 * math.pi * t
        p2 = c + out * (r * math.cos(a) * -1)
        pts.append(Vector((p2.x, p2.y, z + up * r * math.sin(a))))
    for k in range(seg):
        _prism(mb, pts[k], pts[k + 1], 0.016 * (1 - 0.6 * k / seg), 0.016 * (1 - 0.6 * (k + 1) / seg), mat, seg=6)


def stair_hall_decor(mb, r, zi, z0, ceil):
    """Theresian staircase hall: pilasters with capitals, gilded cartouches, landing mirror,
    stucco ceiling medallion (refs 21-22)."""
    for wa, fa, sgn in ((r['wall_a'], r['far_a'], 1), (r['wall_b'], r['far_b'], -1)):
        inward = r['d'] * sgn
        face = PART_T / 2 + 0.02
        for t in (0.12, 0.5, 0.88):
            q = wa.lerp(fa, t) + inward * face
            tng = (fa - wa).normalized()
            mb.box([q - tng * 0.32, q + tng * 0.32, q + tng * 0.32 + inward * 0.12, q - tng * 0.32 + inward * 0.12], z0, ceil - 0.55, 'plaster_int')
            sweep(mb, q - tng * 0.42, q + tng * 0.42, [(0.0, 0.0), (0.13, 0.0), (0.15, 0.03), (0.15, 0.06), (0.18, 0.1),
                                                     (0.2, 0.17), (0.22, 0.2), (0.22, 0.24), (0.0, 0.24)], ceil - 0.6, 'frame', inward)
            sweep(mb, q - tng * 0.35, q + tng * 0.35, [(0.0, 0.0), (0.135, 0.0), (0.145, 0.02), (0.0, 0.02)], ceil - 0.62, 'gold', inward)
            mb.box([q - tng * 0.4, q + tng * 0.4, q + tng * 0.4 + inward * 0.18, q - tng * 0.4 + inward * 0.18], z0, z0 + 0.45, 'marble')
        # blind arcade (refs 28-30): round arches spring from the pilasters
        tng = (fa - wa).normalized()
        for t0, t1 in ((0.12, 0.5), (0.5, 0.88)):
            p0 = wa.lerp(fa, t0) + tng * 0.32 + inward * face
            p1 = wa.lerp(fa, t1) - tng * 0.32 + inward * face
            rad = (p1 - p0).length / 2
            zs = ceil - 0.75 - rad
            # full-thickness blind arch: solid spandrels and soffit flush with the pilasters, wall panel above
            lft = Vector((-tng.y, tng.x))
            a_, b_ = (p0, p1) if lft.dot(inward) > 0 else (p1, p0)
            arch_head(mb, a_, b_, zs + rad, 0.0, 0.12, 'plaster_int', seg=14)
            mb.box([p0, p1, p1 + inward * 0.12, p0 + inward * 0.12], zs + rad, ceil - 0.6, 'plaster_int')
            mid = (p0 + p1) / 2
            arc = [mid - tng * (rad * math.cos(math.pi * k / 14)) for k in range(15)]
            pts = [Vector((p.x, p.y, zs + rad * math.sin(math.pi * k / 14))) + inward.to_3d() * 0.125 for k, p in enumerate(arc)]
            for k in range(14):                                      # thin gilded line on the arch face
                _prism(mb, pts[k] + Vector((0, 0, 0.05)), pts[k + 1] + Vector((0, 0, 0.05)), 0.012, 0.012, 'gold', seg=4)
            for p in (pts[0], pts[-1]):      # impost blocks
                mb.box([p.xy - tng * 0.12, p.xy + tng * 0.12, p.xy + tng * 0.12 + inward * 0.1, p.xy - tng * 0.12 + inward * 0.1],
                       zs - 0.14, zs, 'plaster_int')
            kp = pts[7]
            mb.box([kp.xy - tng * 0.1, kp.xy + tng * 0.1, kp.xy + tng * 0.07 + inward * 0.12, kp.xy - tng * 0.07 + inward * 0.12],
                   kp.z - 0.22, kp.z + 0.08, 'gold')       # keystone
    for p0, p1, inward in ((r['wall_a'], r['wall_b'], r['n']), (r['far_a'], r['far_b'], -r['n']),
                           (r['wall_a'], r['far_a'], r['d']), (r['wall_b'], r['far_b'], -r['d'])):
        off = 0.0 if p1 is r['far_b'] and p0 is r['far_a'] else PART_T / 2 + 0.02
        sweep(mb, p0 + inward * off, p1 + inward * off, PROF_CEIL, ceil, 'plaster_int', inward)
        sweep(mb, p0 + inward * (off + 0.005), p1 + inward * (off + 0.005),
              [(0.0, 0.0), (0.03, 0.0), (0.03, 0.025), (0.0, 0.025)], ceil - 0.46, 'gold', inward)
    if zi + 1 < len(FLOOR_Z):      # mirror on the landing wall (mid-level)
        zm = (z0 + FLOOR_Z[zi + 1]) / 2
        q = r['wall_a'].lerp(r['far_a'], 0.88) + r['d'] * (PART_T / 2 + 0.03)
        tng = (r['far_a'] - r['wall_a']).normalized()
        hang_painting(mb, q - tng * 0.0 + r['d'] * 0.0, r['d'], 0.75, zm + 0.9, zm + 3.0, 'mirror')


def ceiling_fresco(mb, r, ceil):
    c, n, d = r['c'], r['n'], r['d']
    hl, hd = r['L'] * 0.32, r['D'] * 0.3
    q = [c - d * hl - n * hd, c + d * hl - n * hd, c + d * hl + n * hd, c - d * hl + n * hd]
    # stucco ceiling instead of a painting (V2 review): inset gilded panel line, central oval cartouche,
    # quarter-round corner panels and rocaille sprigs, all white and gold
    yaw = math.atan2(d.y, d.x)
    hl2, hd2 = hl - 0.35, hd - 0.35
    q2 = [c - d * hl2 - n * hd2, c + d * hl2 - n * hd2, c + d * hl2 + n * hd2, c - d * hl2 + n * hd2]
    for k in range(4):
        a, b = q2[k], q2[(k + 1) % 4]
        inward = (c - (a + b) / 2).normalized()
        seg_box(mb, a, b, -0.02, 0.02, ceil - 0.025, ceil, 'gold')
        cr = q2[k]
        dx, dy = (d if (c - cr).dot(d) > 0 else -d), (n if (c - cr).dot(n) > 0 else -n)
        pts = [cr + dx * (0.9 * math.sin(a_)) + dy * (0.9 * math.cos(a_)) for a_ in (math.pi / 2 * j / 8 for j in range(9))]
        for p0, p1 in zip(pts, pts[1:]):                       # quarter-round corner panel
            seg_box(mb, p0, p1, -0.015, 0.015, ceil - 0.03, ceil, 'gold')
        ellipsoid(mb, Vector(((cr + (dx + dy) * 0.32).x, (cr + (dx + dy) * 0.32).y, ceil - 0.03)), 0.22, 0.07, 0.03,
                  math.atan2((dx + dy).y, (dx + dy).x), 0, 'gold', subdiv=1)
    rx, ry = hl * 0.42, hd * 0.42
    ov = [c + d * (rx * math.cos(2 * math.pi * j / 32)) + n * (ry * math.sin(2 * math.pi * j / 32)) for j in range(33)]
    for p0, p1 in zip(ov, ov[1:]):                            # oval cartouche: stucco roll + gold rim
        _prism(mb, Vector((p0.x, p0.y, ceil - 0.04)), Vector((p1.x, p1.y, ceil - 0.04)), 0.06, 0.06, 'plaster_int', seg=6)
        _prism(mb, Vector((p0.x, p0.y, ceil - 0.095)), Vector((p1.x, p1.y, ceil - 0.095)), 0.015, 0.015, 'gold', seg=4)
    for j in range(4):                                        # rocaille sprigs at the oval's axes
        a_ = math.pi / 2 * j
        p = c + d * ((rx + 0.28) * math.cos(a_)) + n * ((ry + 0.28) * math.sin(a_))
        for s_ in (-0.5, 0.5):
            ellipsoid(mb, Vector((p.x, p.y, ceil - 0.03)), 0.25, 0.08, 0.03, yaw + a_ + math.pi / 2 + s_, 0, 'gold', subdiv=1)
    for rr, hh in ((0.35, 0.06), (0.18, 0.12)):               # central rosette for the chandelier
        slab(mb, [circle(c, rr, 16)], ceil, hh, 'gold' if rr < 0.3 else 'plaster_int', 'gold' if rr < 0.3 else 'plaster_int', 'plaster_int')
    for k in range(4):             # gilded frame + stucco cove around the panel
        a, b = q[k], q[(k + 1) % 4]
        inward = (c - (a + b) / 2).normalized()
        sweep(mb, a - inward * 0.0, b - inward * 0.0, [(0.0, 0.0), (0.0, -0.03), (-0.06, -0.06), (-0.14, -0.08), (-0.22, -0.05),
                                                    (-0.3, 0.0)], ceil, 'plaster_int', -inward)
        sweep(mb, a, b, [(0.0, 0.0), (0.0, -0.02), (0.05, -0.03), (0.06, 0.0)], ceil - 0.005, 'gold', inward)


def furnish(mb, rooms, corridor_pts, coll):
    lc = bpy.data.collections.new('Interior_Lights')
    coll.children.link(lc)
    rng = random.Random(5)
    for zi, z0 in enumerate(FLOOR_Z):
        z1 = FLOOR_Z[zi + 1] if zi + 1 < len(FLOOR_Z) else EAVE_Z
        ceil = z1 - SLAB_T
        for r in rooms:
            if r['stair']:
                stair_hall_decor(mb, r, zi, z0, ceil)
                add_light(lc, f'L_stair_{zi}', (r['c'].x, r['c'].y, ceil - 1.2), 60)
                add_light(lc, f'L_stair_b_{zi}', (r['c'].x, r['c'].y, z0 + 2.6), 60)
                continue
            if r['passage'] and zi == 0:
                add_light(lc, 'L_gate', (r['c'].x, r['c'].y, ceil - 1.0), 60)
                sph_mb_ring(mb, r['c'], ceil - 1.6, 0.3, 'lamp', seg=6)
                continue
            c = r['c']
            hall_ = zi == 0 and any((r['wall_a'] - hp).length < 0.6 or (r['wall_b'] - hp).length < 0.6 for hp in HALL_PARTS)
            for p0, p1, inward, off in ((r['wall_a'], r['wall_b'], r['n'], PART_T / 2 + 0.02), (r['far_a'], r['far_b'], -r['n'], 0.0),
                                        (r['wall_a'], r['far_a'], r['d'], PART_T / 2 + 0.02), (r['wall_b'], r['far_b'], -r['d'], PART_T / 2 + 0.02)):
                if hall_:
                    break     # Knights' Hall: groin vaults from v2_interior, no flat-ceiling cornice
                sweep(mb, p0 + inward * off, p1 + inward * off, PROF_CEIL, ceil, 'plaster_int', inward)
            if 'STATE_ROOMS' not in globals():     # only the two largest south-wing rooms stay furnished state rooms
                south_ = sorted((x for x in rooms if x['n'].y < -0.9 and not x['special'] and not x['stair'] and not x['passage']),
                                key=lambda x: (-x['L'] * x['D'], x['c'].x))
                globals()['STATE_ROOMS'] = {id(x) for x in south_[:2]}
            has_fresco = zi == 1 and id(r) in STATE_ROOMS
            if has_fresco:     # state rooms: painted ceiling in a stucco frame
                ceiling_fresco(mb, r, ceil)
            nch = 2 if r['D'] > 9 else 1
            for j in range(nch):
                cc = c + r['n'] * ((j - (nch - 1) / 2) * r['D'] * 0.45)
                chandelier(SMOOTH, cc, ceil - 1.6, 0.55)
                if has_fresco:
                    lathe(SMOOTH, cc, ceil - 0.01, [(0.22, 0.0), (0.2, -0.03), (0.12, -0.06), (0.05, -0.08), (0.0, -0.09)], 'gold', seg=12)
                if not has_fresco and not hall_:
                    lathe(SMOOTH, cc, ceil, [(1.4, 0.0), (1.38, -0.02), (1.3, -0.035), (1.2, -0.03), (1.05, -0.012), (0.95, -0.012),
                                     (0.88, -0.05), (0.8, -0.075), (0.7, -0.07), (0.6, -0.045), (0.5, -0.04), (0.42, -0.07),
                                     (0.33, -0.12), (0.2, -0.15), (0.08, -0.17), (0.0, -0.18)], 'plaster_int', seg=20)
                add_light(lc, f'L_room_{zi}', (cc.x, cc.y, ceil - 1.5), 60)
            # paintings on both partition walls (room side), centred in the depth
            for wa, sgn in ((r['wall_a'], 1), (r['wall_b'], -1)):
                if sum(1 for r2 in rooms if (r2['n'] - r['n']).length < 1e-6 and
                       min((r2['wall_a'] - wa).length, (r2['wall_b'] - wa).length) < 0.05) < 2:
                    continue          # open corner of an L-shaped corner room: no wall to hang on
                if zi == 0 and any((wa - hp).length < 0.6 for hp in HALL_PARTS):
                    continue          # this partition is an open arcade in the Knights' Hall
                if zi == 0 and any(r2['passage'] and min((r2['wall_a'] - wa).length, (r2['wall_b'] - wa).length) < 0.05 for r2 in rooms):
                    continue          # gate passage wall: the Gothic portal is exposed there (v2_interior)
                inward = r['d'] * sgn
                # partition doors sit at 72 % of the depth (+-0.75 m): hang between the corridor wall and the door
                free0, free1 = 0.5, r['D'] * 0.72 - 0.75 - 0.35
                if free1 - free0 < 1.4:
                    continue
                w2 = min(rng.uniform(0.7, 1.2), (free1 - free0) / 2)
                base = wa + r['n'] * ((free0 + free1) / 2) + inward * (PART_T / 2 + 0.005)
                h0 = z0 + 1.5
                h1 = h0 + rng.uniform(1.2, 1.9)
                choice = (rng.choice(('paint_land', 'paint_land2', 'paint_harbour', 'paint_still')) if w2 > 0.95
                          else rng.choice(('paint_port', 'paint_port2')))
                hang_painting(mb, base, inward, w2, h0, h1, choice)
        if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v2_interior.py')):   # V2 hangs them on the vault-bay rhythm
            continue
        for p in corridor_pts:
            lantern(mb, p, ceil - 0.02, ceil - 1.05)
            add_light(lc, f'L_corr_{zi}', (p.x, p.y, ceil - 0.6), 25)


def _clip_half(poly, a, b, keep_left):
    """Sutherland-Hodgman clip of a 3D polygon by the vertical half-plane of 2D line a->b."""
    def side(p):
        return (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)
    out = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        sp, sq = side(p), side(q)
        pin, qin = (sp >= 0) == keep_left or sp == 0, (sq >= 0) == keep_left or sq == 0
        if pin:
            out.append(p)
        if (sp > 0) != (sq > 0) and sp != 0 and sq != 0:
            t = sp / (sp - sq)
            out.append(p.lerp(q, t))
    return out


def poly_minus_squares(mb, poly, squares, mat):
    """Emit convex `poly` minus convex vertical prisms (tower shafts): pieces stay planar."""
    pieces = [poly]
    for sq in squares:
        if poly_area(sq) < 0:
            sq = list(reversed(sq))
        nxt = []
        for pc in pieces:
            rest = pc
            for i in range(len(sq)):
                a, b = sq[i], sq[(i + 1) % len(sq)]
                outside = _clip_half(rest, a, b, keep_left=False)
                if len(outside) >= 3 and abs(poly_area([(v.x, v.y) for v in outside])) > 1e-4:
                    nxt.append(outside)
                rest = _clip_half(rest, a, b, keep_left=True)
                if len(rest) < 3:
                    break
        pieces = nxt
    for pc in pieces:
        mb.poly(pc, mat)


CELLAR_Z = -4.6


def build_cellar(walls, floors, trim, ramps, rooms, W, coll):
    """Brick-vaulted cellar under the south wing (15th c. cellars, ref25) with a straight
    stone stair down from the ground-floor room west of the main gate."""
    if 'brick_old' not in MATS:          # aged, irregular brick for the cellar (ref 37)
        import numpy as np_
        rgb_, hgt_ = textures.brick_old(512 if WEB else 1024, np_.random.default_rng(37))
        make_mat('brick_old', textures._save(os.path.join(TEX, 'brick_old.png'), rgb_),
                 normal=textures._save(os.path.join(TEX, 'brick_old_n.png'), textures.normal_from(np_.repeat(hgt_[..., None], 3, -1), 7), 'Non-Color'),
                 uv=2.0, rough=0.97)
    if 'brick_old2' not in MATS:         # re-laid patches: darker, damper, different staining
        import numpy as np_
        rgb_, hgt_ = textures.brick_old(512 if WEB else 1024, np_.random.default_rng(73))
        rgb_ = np_.clip(rgb_ * np_.array([0.84, 0.8, 0.76]) * (0.85 + 0.3 * textures.fbm(rgb_.shape[0], np_.random.default_rng(5), octaves=(1, 2, 4)))[..., None], 0, 1)
        make_mat('brick_old2', textures._save(os.path.join(TEX, 'brick_old2.png'), rgb_),
                 normal=textures._save(os.path.join(TEX, 'brick_old2_n.png'), textures.normal_from(np_.repeat(hgt_[..., None], 3, -1), 8), 'Non-Color'),
                 uv=2.0, rough=0.97)
    for nm_, args_ in (('flags_old', ('#6F6A60', 4, '#4A463F')), ('ashlar_old', ('#958C7C', 3, '#625C52'))):
        if nm_ not in MATS:              # weathered irregular floor flags / ashlar skirting
            import numpy as np_
            rgb_, hgt_ = textures.flags_old(512 if WEB else 1024, np_.random.default_rng(41), *args_)
            make_mat(nm_, textures._save(os.path.join(TEX, nm_ + '.png'), rgb_),
                     normal=textures._save(os.path.join(TEX, nm_ + '_n.png'), textures.normal_from(np_.repeat(hgt_[..., None], 3, -1), 6), 'Non-Color'),
                     uv=3.0, rough=0.95)
    w = next(x for x in W if x['name'] == 'S')
    o0, o1 = w['o']
    Lo = (o1 - o0).length
    d_o = (o1 - o0) / Lo
    n_o = Vector((-d_o.y, d_o.x))
    i0, i1 = w['i']
    ts0, ts1 = TOWER_SIZE[0] + 0.9, TOWER_SIZE[1] + 0.9
    A = lambda t: o0 + d_o * (ts0 + (Lo - ts0 - ts1) * t) + n_o * (OUTER_T + 0.04)   # just inside the outer wall face
    def B(t):
        a = A(t)
        q = i0 + (i1 - i0).normalized() * project_t(a, i0, i1)
        return q + w['n'] * (COURT_T + 0.04)
    # stair down from the room west of the gate passage
    cand = [r for r in rooms if not r['special'] and r['n'].dot(w['n']) > 0.95]
    gate_c = o0 + d_o * (Lo / 2)
    west = [r for r in cand if (r['c'] - gate_c).dot(d_o) < 0 and r['L'] > 27 * 0.3 + 1.8]
    if not west:
        return None
    r = max(west, key=lambda r: (r['c'] - gate_c).dot(d_o))
    d, n = r['d'], r['n']
    nst = 27
    rise, tread, fw = (0.0 - CELLAR_Z) / nst, 0.3, 1.8
    run = nst * tread
    start = r['wall_b'] - d * (PART_T / 2 + 0.5 + run) + n * 1.4      # top of the flight, descends towards wall_b
    hole = [start - d * 0.05 - n * 0.05, start + d * (run + 0.05) - n * 0.05,
            start + d * (run + 0.05) + n * (fw + 0.05), start - d * 0.05 + n * (fw + 0.05)]
    hole_ccw = hole if poly_area([(v.x, v.y) for v in hole]) > 0 else list(reversed(hole))   # offset_poly grows CCW loops only
    stair_zone = offset_poly(hole_ccw, 0.6)
    over_stair = lambda q: point_in_poly(q.x, q.y, stair_zone)
    lc = bpy.data.collections.new('Cellar_Lights')
    coll.children.link(lc)
    zf, rise_v = CELLAR_Z, 1.9
    zs = -0.5 - rise_v                                                           # vault springing
    nl, nseg = 24, 20
    secs = []
    for i in range(nl + 1):
        t = i / nl
        a, b = A(t), B(t)
        prof = [a.lerp(b, (1 - math.cos(math.pi * k / nseg)) / 2) for k in range(nseg + 1)]
        hz = [zs + rise_v * math.sin(math.pi * k / nseg) for k in range(nseg + 1)]
        secs.append((a, b, prof, hz))
    arc = []
    for (a, b, prof, hz) in secs:
        acc_ = [0.0]
        for k in range(nseg):
            acc_.append(acc_[-1] + (Vector((prof[k + 1].x, prof[k + 1].y, hz[k + 1])) - Vector((prof[k].x, prof[k].y, hz[k]))).length)
        arc.append(acc_)
    along = [0.0]
    for i in range(1, len(secs)):
        along.append(along[-1] + (secs[i][0] - secs[i - 1][0]).length)
    for i, ((a0, b0, p0, h0), (a1, b1, p1, h1)) in enumerate(zip(secs, secs[1:])):
        for k in range(nseg):
            if over_stair((p0[k] + p1[k + 1]) / 2):
                continue
            uvq = [(along[i] / 2.0, arc[i][k] / 2.0), (along[i] / 2.0, arc[i][k + 1] / 2.0),
                   (along[i + 1] / 2.0, arc[i + 1][k + 1] / 2.0), (along[i + 1] / 2.0, arc[i + 1][k] / 2.0)]
            walls.poly([Vector((p0[k].x, p0[k].y, h0[k])), Vector((p0[k + 1].x, p0[k + 1].y, h0[k + 1])),
                        Vector((p1[k + 1].x, p1[k + 1].y, h1[k + 1])), Vector((p1[k].x, p1[k].y, h1[k]))],
                       'brick_old2' if (i // 3 + (k > nseg // 2)) % 3 == 1 else 'brick_old', uv=uvq)   # patches of re-laid brick
        hall_c = (a0 + b0 + a1 + b1) / 4
        for e0, e1 in ((a0, a1), (b0, b1)):           # brick side walls below the springing (facing the hall)
            m_ = (e0 + e1) / 2
            oriented_poly(walls, [Vector((e0.x, e0.y, zf)), Vector((e1.x, e1.y, zf)), Vector((e1.x, e1.y, zs)), Vector((e0.x, e0.y, zs))],
                          Vector(((hall_c - m_).x, (hall_c - m_).y, 0)), 'brick_old', uv_scale=2.0)
    for (a, b, prof, hz), inward_ in ((secs[0], secs[1][0] - secs[0][0]), (secs[-1], secs[-2][0] - secs[-1][0])):       # end walls
        for k in range(nseg):
            oriented_poly(walls, [Vector((prof[k].x, prof[k].y, zf)), Vector((prof[k + 1].x, prof[k + 1].y, zf)),
                                  Vector((prof[k + 1].x, prof[k + 1].y, hz[k + 1])), Vector((prof[k].x, prof[k].y, hz[k]))],
                          Vector((inward_.x, inward_.y, 0)), 'brick_old', uv_scale=2.0)
    arch_idx, i_ = [], 2
    for step_ in [3, 5, 4, 3, 6, 4, 5, 3, 4, 5] * 3:   # irregular bay rhythm (repairs of different periods)
        if i_ >= nl - 1:
            break
        arch_idx.append(i_)
        i_ += step_
    for i in arch_idx:                                 # transverse brick arches + stone base course
        a, b, prof, hz = secs[i]
        dd = (secs[i + 1][0] - a).normalized()
        for k in range(nseg):
            q0, q1 = prof[k], prof[k + 1]
            if over_stair((q0 + q1) / 2):
                continue
            h0_, h1_ = hz[k] - 0.42, hz[k + 1] - 0.42          # fuller transverse arch masses
            for sd in (-0.45, 0.45):
                f0, f1 = q0 + dd * sd, q1 + dd * sd
                face = [Vector((f0.x, f0.y, h0_)), Vector((f1.x, f1.y, h1_)), Vector((f1.x, f1.y, hz[k + 1])), Vector((f0.x, f0.y, hz[k]))]
                oriented_poly(trim, face, Vector((dd.x, dd.y, 0)) * (1 if sd > 0 else -1), 'brick_old')
            u0, u1 = q0 - dd * 0.45, q1 - dd * 0.45
            v0, v1 = q0 + dd * 0.45, q1 + dd * 0.45
            ctr2 = (a + b) / 2
            mq = (q0 + q1) / 2
            down = Vector(((ctr2 - mq).x, (ctr2 - mq).y, zs - (h0_ + h1_) / 2)).normalized()
            oriented_poly(trim, [Vector((u1.x, u1.y, h1_)), Vector((v1.x, v1.y, h1_)), Vector((v0.x, v0.y, h0_)), Vector((u0.x, u0.y, h0_))], down, 'brick_old')
        add_light(lc, 'L_cellar', ((a.x + b.x) / 2, (a.y + b.y) / 2, zs + 1.2), 45, color=(1.0, 0.7, 0.4))
        m = a.lerp(b, 0.5)
        lantern(trim, m, zs + rise_v - 0.05, zs + 0.85)
    quad = [A(0), A(1), B(1), B(0)]
    slab(floors, [quad], zf, 0.4, 'flags_old', 'stone', 'stone')
    for e0, e1, inward in ((A(0), A(1), (B(0) - A(0)).normalized()), (B(0), B(1), (A(0) - B(0)).normalized())):
        L = (e1 - e0).length
        dd = (e1 - e0) / L
        rng_f = random.Random(35)
        u = 0.0
        while u < L - 0.4:                  # irregular masonry footings along the walls (refs 35/37), not a continuous dado
            w_ = rng_f.uniform(0.5, 1.4)
            p0, p1 = e0 + dd * u, e0 + dd * min(L, u + w_)
            u += w_ + (rng_f.uniform(0.15, 0.9) if rng_f.random() < 0.35 else 0.0)
            if over_stair((p0 + p1) / 2):
                continue
            dep, hgt = rng_f.uniform(0.25, 0.5), rng_f.uniform(0.3, 0.75)
            floors.box([p0, p1, p1 + inward * dep, p0 + inward * dep], zf, zf + hgt, 'rubble' if rng_f.random() < 0.6 else 'ashlar_old')
            if rng_f.random() < 0.5:        # stepped top course
                q0, q1 = p0 + dd * 0.08, p1 - dd * 0.08
                floors.box([q0, q1, q1 + inward * (dep * 0.6), q0 + inward * (dep * 0.6)], zf + hgt, zf + hgt + rng_f.uniform(0.12, 0.3), 'rubble')
    for k in range(nst):
        q0 = start + d * (k * tread)
        zt = -(k + 1) * rise
        floors.box([q0, q0 + d * tread, q0 + d * tread + n * fw, q0 + n * fw], zt - 0.35, zt, 'stone')
    ramps.poly_up([Vector((start.x, start.y, 0.0)), Vector(((start + n * fw).x, (start + n * fw).y, 0.0)),
                   Vector(((start + n * fw + d * run).x, (start + n * fw + d * run).y, zf)),
                   Vector(((start + d * run).x, (start + d * run).y, zf))], 'stone')
    for e0, e1 in ((hole[1], hole[2]), (hole[2], hole[3]), (hole[0], hole[1])):    # railing on three sides
        L = (e1 - e0).length
        dd = (e1 - e0) / L
        for k in range(int(L / 0.25) + 1):
            m = e0 + dd * (k * L / max(1, int(L / 0.25)))
            seg_box(trim, m - dd * 0.02, m + dd * 0.02, -0.02, 0.02, 0.0, 0.95, 'metal')
        seg_box(trim, e0, e1, -0.04, 0.04, 0.95, 1.02, 'gold')
        seg_box(floors, e0, e1, -0.03, 0.03, 0.0, 1.0, 'invisible')
    dc = (r['wall_a'] + r['wall_b']) / 2
    NAV['cellar_room_corr'] = list(dc - n * 1.6)
    NAV['cellar_room_in'] = list(dc + n * 1.2)
    NAV['cellar_top'] = list(start + n * (fw / 2) - d * 1.6)
    NAV['cellar_step1'] = list(start + n * (fw / 2) + d * 0.4)
    NAV['cellar_mid'] = list(start + n * (fw / 2) + d * (run / 2))
    NAV['cellar_low'] = list(start + n * (fw / 2) + d * (run - 0.4))
    NAV['cellar_bottom'] = list(start + n * (fw / 2) + d * (run + 1.2))
    globals()['CELLAR_INFO'] = dict(secs=secs, along=along, arc=arc, zone=stair_zone, hole=hole_ccw, zs=zs, rise=rise_v, arches=arch_idx)   # v2_interior: brick reveals
    return hole


def tower_squares():
    """Square tower shafts at the palace corners, protruding slightly from both facades.
    SW = Crown Tower (Korunná veža, 13th c.); others 17th c. Proportions measured from
    photographs: shaft ~8 m above eave, pediments, octagonal drum, octagonal spire."""
    out = []
    for k in range(4):
        c = OUTER[k]
        e1 = (OUTER[(k + 1) % 4] - c).normalized()
        e2 = (OUTER[k - 1] - c).normalized()
        s, p = TOWER_SIZE[k], TOWER_PROTRUDE
        c0 = c - e1 * p - e2 * p
        sq = [c0, c0 + e1 * (s + p), c0 + e1 * (s + p) + e2 * (s + p), c0 + e2 * (s + p)]
        if poly_area(sq) < 0:
            sq = [sq[0], sq[3], sq[2], sq[1]]
        out.append((['SW', 'SE', 'NE', 'NW'][k], sq, CROWN_TOWER if k == 0 else SMALL_TOWER))
    return out


SPIRAL_R = 2.4


def circle(c, r, n=20):
    return [Vector((c.x + r * math.cos(2 * math.pi * k / n), c.y + r * math.sin(2 * math.pi * k / n))) for k in range(n)]


def spiral_stair(floors, trim, ramps, c, z0, z1, r_out=SPIRAL_R, r_in=0.35, per_turn=18):
    """Stone newel stair (Crown Tower ascent) with helical collision ramp."""
    nst = max(8, round((z1 - z0) / 0.18))
    rise = (z1 - z0) / nst
    da = 2 * math.pi / per_turn
    for k in range(nst):
        a0, a1 = k * da, (k + 1) * da
        p = lambda a, r: c + Vector((math.cos(a), math.sin(a))) * r
        zt = z0 + (k + 1) * rise
        wedge = [p(a0, r_in), p(a0, r_out), p(a1, r_out), p(a1, r_in)]
        floors.box(wedge, zt - 0.3, zt, 'stone', top='marble')
        q0, q1, q2, q3 = p(a0, r_in), p(a0, r_out), p(a1, r_out), p(a1, r_in)
        za, zb = z0 + (k + 1) * rise, min(z1, z0 + (k + 2) * rise)   # through the nosings, not under the treads
        ramps.poly_up([Vector((q0.x, q0.y, za)), Vector((q1.x, q1.y, za)), Vector((q2.x, q2.y, zb)), Vector((q3.x, q3.y, zb))], 'stone')
        # rope handrail posts on the outer edge every 3 steps
        if k % 3 == 0:
            hp = p((a0 + a1) / 2, r_out - 0.1)
            seg_box(trim, hp - Vector((0.03, 0)), hp + Vector((0.03, 0)), -0.03, 0.03, zt, zt + 0.95, 'metal')
    floors.box([c + Vector((-r_in, -r_in)), c + Vector((r_in, -r_in)), c + Vector((r_in, r_in)), c + Vector((-r_in, r_in))],
               z0, z1 + 1.0, 'stone')     # newel


def treasury_vitrine(col, mb, c):
    q = lambda r: [c + Vector((-r, -r)), c + Vector((r, -r)), c + Vector((r, r)), c + Vector((-r, r))]
    """Holy Crown replica (ref 34) on a crimson cushion in a tall glass case on a dark plinth."""
    col.box(q(0.55), 0.0, 0.95, 'door', top='joinery')
    mb.box(q(0.36), 0.95, 1.05, 'carpet')                                    # velvet cushion
    z = 1.05
    R = 0.115
    ellipsoid(mb, Vector((c.x, c.y, z + 0.1)), R * 0.92, R * 0.92, 0.1, 0, 0, 'carpet', subdiv=2)   # crimson cap
    for k in range(16):      # gold band of enamel plates with alternating jewels
        a0, a1 = 2 * math.pi * k / 16, 2 * math.pi * (k + 1) / 16
        p0 = c + Vector((math.cos(a0), math.sin(a0))) * R
        p1 = c + Vector((math.cos(a1), math.sin(a1))) * R
        seg_box(mb, p1, p0, -0.004, 0.006, z + 0.02, z + 0.085, 'gold')
        pm = (p0 + p1) / 2 + ((p0 + p1) / 2 - c).normalized() * 0.008
        ellipsoid(mb, Vector((pm.x, pm.y, z + 0.052)), 0.011, 0.011, 0.014, 0, 0, 'jewel_red' if k % 2 == 0 else 'jewel_blue', subdiv=1)
        if k % 2 == 0:       # gabled and rounded plates rising above the band
            ap = c + Vector((math.cos(a0 + math.pi / 16), math.sin(a0 + math.pi / 16))) * R
            mb.poly([Vector((p0.x, p0.y, z + 0.085)), Vector((p1.x, p1.y, z + 0.085)), Vector((ap.x, ap.y, z + (0.15 if k % 4 == 0 else 0.125)))], 'gold')
            mb.poly([Vector((p1.x, p1.y, z + 0.085)), Vector((p0.x, p0.y, z + 0.085)), Vector((ap.x, ap.y, z + (0.15 if k % 4 == 0 else 0.125)))], 'gold')
    for ang in (0.0, math.pi / 2):       # two crossing gold straps over the cap
        u = Vector((math.cos(ang), math.sin(ang), 0))
        pts = [Vector((c.x, c.y, z + 0.085)) + u * (R * math.cos(t)) + Vector((0, 0, 0.12 * math.sin(t)))
               for t in (math.pi * j / 10 for j in range(11))]
        for p0, p1 in zip(pts, pts[1:]):
            _prism(mb, p0, p1, 0.012, 0.012, 'gold', seg=4)
    tip = Vector((c.x, c.y, z + 0.215))
    ellipsoid(mb, tip, 0.02, 0.02, 0.02, 0, 0, 'gold', subdiv=1)
    _prism(mb, tip, tip + Vector((0.035, 0.0, 0.1)), 0.008, 0.008, 'gold', seg=4)   # the famous bent cross
    _prism(mb, tip + Vector((0.0, -0.028, 0.07)), tip + Vector((0.04, 0.028, 0.08)), 0.006, 0.006, 'gold', seg=4)
    for sgn in (-1, 1):                  # pendilia: three chains on each side ending in trefoils
        for j in range(3):
            a = math.pi / 2 + sgn * math.pi / 2 + (j - 1) * 0.25
            hp = c + Vector((math.cos(a), math.sin(a))) * (R + 0.006)
            top_, bot_ = Vector((hp.x, hp.y, z + 0.03)), Vector((hp.x, hp.y, z - 0.09))
            _prism(mb, top_, bot_, 0.003, 0.003, 'gold', seg=4)
            ellipsoid(mb, bot_, 0.009, 0.009, 0.012, 0, 0, 'gold', subdiv=0)
    g = q(0.42)
    for j in range(4):
        a, b = g[j], g[(j + 1) % 4]
        mb.poly([Vector((a.x, a.y, 0.95)), Vector((b.x, b.y, 0.95)), Vector((b.x, b.y, 1.95)), Vector((a.x, a.y, 1.95))], 'glass')
        _prism(mb, Vector((a.x, a.y, 0.95)), Vector((a.x, a.y, 1.95)), 0.008, 0.008, 'metal', seg=4)
    mb.poly([Vector((p.x, p.y, 1.95)) for p in g], 'glass')
    col.box(q(0.43), 0.95, 1.95, 'invisible')


def build_tower(walls, trim, win, roof, floors, sq, prm, name, ramps=None):
    top, ped_h, drum_top, apex = prm['shaft_top'], prm['ped_h'], prm['drum_top'], prm['apex']
    cen = sum(sq, Vector((0, 0))) / 4
    found = -9.0
    for k in range(4):
        a, b = sq[k], sq[(k + 1) % 4]
        L = (b - a).length
        d = (b - a) / L
        n = Vector((-d.y, d.x))
        mid = (a + b) / 2
        outer_face = dist_to_poly(mid.x, mid.y, OUTER) < 2.0 and not point_in_poly(mid.x, mid.y, offset_poly(OUTER, -2.0))
        ops = []
        if outer_face:          # small, nearly square tower windows (photos 04, 14)
            hw_, hh_ = (0.36, 0.95) if name == 'SW' else (0.42, 1.25)
            for z in FLOOR_Z:
                ops.append((L / 2 - hw_, L / 2 + hw_, z + 1.9, z + 1.9 + hh_))
        else:
            for z in FLOOR_Z:     # doorways from the corner rooms of the wings
                ops.append((L / 2 - 0.8, L / 2 + 0.8, z, z + 3.2))
        view = name == 'SW'          # Crown Tower viewing room: low sills you can look out of
        for z in ((EAVE_Z + 0.95, EAVE_Z + 4.8) if view else (EAVE_Z + 1.8, EAVE_Z + 4.8)):
            ops.append((L / 2 - (0.65 if view else 0.42), L / 2 + (0.65 if view else 0.42), z, z + (1.8 if view else 1.2)))
        wall(walls, a, b, found, top, 0.9, 'plaster', ops, mat_in='plaster_int')
        for o in ops:
            if o[2] < EAVE_Z and not outer_face:
                continue
            window_unit(win, a + d * o[0], a + d * o[1], o[2], o[3], n, 0.45)
            seg_box(trim, a + d * (o[0] - 0.18), a + d * (o[1] + 0.18), -0.07, 0.02, o[3], o[3] + 0.18, 'frame')
            seg_box(trim, a + d * (o[0] - 0.18), a + d * o[0], -0.07, 0.02, o[2], o[3], 'frame')
            seg_box(trim, a + d * o[1], a + d * (o[1] + 0.18), -0.07, 0.02, o[2], o[3], 'frame')
            seg_box(trim, a + d * (o[0] - 0.25), a + d * (o[1] + 0.25), -0.15, 0.3, o[2] - 0.12, o[2], 'stone')
        # rusticated quoins on both vertical edges, alternating long/short blocks
        z, j = 0.9 if outer_face else EAVE_Z, 0
        while z < top - 0.6:
            w = 1.25 if j % 2 == 0 else 0.75
            for e0, e1v in ((a, a + d * w), (b - d * w, b)):
                seg_box(trim, e0, e1v, -0.08, 0.02, z, z + 0.62, 'rustica')
            z += 0.68
            j += 1
        # cornice at the shaft top + pediment (tympanon) with copper capping
        seg_box(trim, a - d * 0.45, b + d * 0.45, -0.45, 0.02, top - 0.55, top, 'frame')
        seg_box(trim, a - d * 0.25, b + d * 0.25, -0.25, 0.02, top - 0.9, top - 0.55, 'frame')
        A, B = a - n * 0.3, b - n * 0.3
        M = (A + B) / 2
        tri = [Vector((A.x, A.y, top)), Vector((B.x, B.y, top)), Vector((M.x, M.y, top + ped_h))]
        back = [v + Vector((n.x, n.y, 0)) * 1.2 for v in tri]
        roof.poly(tri, 'plaster')
        roof.poly(list(reversed(back)), 'plaster')
        for (p0, p1) in ((0, 2), (2, 1)):
            q0, q1 = tri[p0], tri[p1]
            up = Vector((0, 0, 0.18))
            out_n = Vector((-n.x, -n.y, 0)) * 0.25
            roof.poly([q0 + out_n + up, q1 + out_n + up, q1 + Vector((n.x, n.y, 0)) * 1.6 + up,
                       q0 + Vector((n.x, n.y, 0)) * 1.6 + up], 'frame')      # plain white raking cornice (photo 14)
    # copper hip between the pediments up to the drum
    rd = 0.40 * min((sq[1] - sq[0]).length, (sq[3] - sq[0]).length)
    hip_top = top + ped_h * 0.75
    for k in range(4):
        a = sq[k] - (cen - sq[k]).normalized() * 0.3
        b = sq[(k + 1) % 4] - (cen - sq[(k + 1) % 4]).normalized() * 0.3
        ia = cen + (a - cen).normalized() * rd * 1.05
        ib = cen + (b - cen).normalized() * rd * 1.05
        roof.poly([Vector((a.x, a.y, top)), Vector((b.x, b.y, top)), Vector((ib.x, ib.y, hip_top)),
                   Vector((ia.x, ia.y, hip_top))], 'copper')
    # octagonal drum with oculi + cornice
    oct8 = [cen + Vector((math.cos(math.pi / 8 + k * math.pi / 4), math.sin(math.pi / 8 + k * math.pi / 4))) * rd for k in range(8)]
    for k in range(8):
        a, b = oct8[k], oct8[(k + 1) % 8]
        L = (b - a).length
        zo = drum_top - 2.3                              # an oculus on every face of the drum
        ops = [(L / 2 - 0.36, L / 2 + 0.36, zo - 0.36, zo + 0.36)]
        wall(walls, a, b, top - 0.5, drum_top, 0.4, 'plaster', ops, mat_in='plaster_int')
        d = (b - a) / L
        n = Vector((-d.y, d.x))
        mid_ = a + d * (L / 2)
        oval_ring(trim, mid_ - n * 0.02, -n, 0.45, 0.45, zo, 0.07, 'frame')
        for o in ops:
            arch_head(walls, a + d * o[0], a + d * o[1], o[3], 0.0, 0.4, 'plaster')
            pane(win, a + d * o[0] + n * 0.2, a + d * o[1] + n * 0.2, o[2], o[3])
        seg_box(trim, a - d * 0.2, b + d * 0.2, -0.35, 0.02, drum_top - 0.4, drum_top, 'frame')
        seg_box(trim, a, b, -0.12, 0.02, drum_top - 1.4, drum_top - 1.2, 'frame')
    slab(floors, [oct8], drum_top - 0.3, 0.3, 'plaster_int', 'plaster_int', 'frame')
    if name == 'SW':    # treasury on the ground floor: crown-jewel replica in a vitrine (jewels kept here 1552-1783)
        treasury_vitrine(floors, trim, cen)
        add_light(bpy.context.scene.collection, 'L_treasury', (cen.x, cen.y, 3.2), 55, color=(1.0, 0.92, 0.8))
    if name == 'SW' and ramps is not None:
        slab(floors, [sq, circle(cen, SPIRAL_R + 0.6)], EAVE_Z + 0.02, 0.3, 'parquet', 'plaster_int', 'plaster_int')
        spiral_stair(floors, trim, ramps, cen, FLOOR_Z[3], EAVE_Z + 0.02)
        print('CROWN_TOWER_CENTER', round(cen.x, 2), round(cen.y, 2))
        hole = circle(cen, SPIRAL_R + 0.6)
        for k in range(len(hole)):      # guard rail around the stair well at the viewing level
            seg_box(trim, hole[k], hole[(k + 1) % len(hole)], -0.04, 0.04, EAVE_Z + 0.95, EAVE_Z + 1.02, 'metal')
            if k % 2 == 0:
                seg_box(trim, hole[k] - Vector((0.025, 0)), hole[k] + Vector((0.025, 0)), -0.025, 0.025, EAVE_Z, EAVE_Z + 0.95, 'metal')
        add_light(bpy.context.scene.collection, 'L_crown_tower', (cen.x, cen.y, EAVE_Z + 3.5), 60)
    else:
        slab(floors, [sq], EAVE_Z + 0.02, 0.3, 'parquet', 'plaster_int', 'plaster_int')
    slab(floors, [sq], top - 0.3, 0.3, 'parquet', 'plaster_int', 'plaster_int')
    # octagonal spire
    oo = [cen + (p - cen) * 1.12 for p in oct8]
    ap = Vector((cen.x, cen.y, apex))
    for k in range(8):
        a = Vector((oo[k].x, oo[k].y, drum_top - 0.15))
        b = Vector((oo[(k + 1) % 8].x, oo[(k + 1) % 8].y, drum_top - 0.15))
        roof.poly([a, b, ap], 'roof_tower', uv_scale=2.0)
    sph_mb_ring(trim, cen, apex - 0.1, 0.32, 'gold')
    seg_box(trim, cen - Vector((0.04, 0)), cen + Vector((0.04, 0)), -0.04, 0.04, apex, apex + 2.0, 'metal')


def sph_mb_ring(mb, c, z, r, mat, seg=8):
    for k in range(seg):
        for j in range(seg // 2):
            a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
            b0, b1 = math.pi * j / (seg // 2) - math.pi / 2, math.pi * (j + 1) / (seg // 2) - math.pi / 2

            def P(a, b):
                return Vector((c.x + r * math.cos(b) * math.cos(a), c.y + r * math.cos(b) * math.sin(a), z + r + r * math.sin(b)))
            mb.poly([P(a0, b0), P(a1, b0), P(a1, b1), P(a0, b1)], mat)


def window_unit(mb, a, b, z0, z1, n_in, depth, door=False):
    """Historic casement window recessed `depth` into the wall: 80 mm outer frame, two sashes
    (55 mm, set 40 mm back), transom, 25 mm glazing bars, glass behind the bars, inner sill board."""
    a = Vector(a[:2]) + n_in * depth
    b = Vector(b[:2]) + n_in * depth
    d = (b - a).normalized()
    W = (b - a).length
    fw, ft = 0.08, 0.1
    # outer frame
    seg_box(mb, a, b, -ft / 2, ft / 2, z0, z0 + fw, 'joinery')
    seg_box(mb, a, b, -ft / 2, ft / 2, z1 - fw, z1, 'joinery')
    seg_box(mb, a, a + d * fw, -ft / 2, ft / 2, z0, z1, 'joinery')
    seg_box(mb, b - d * fw, b, -ft / 2, ft / 2, z0, z1, 'joinery')
    zt = z0 + (z1 - z0) * 0.72
    seg_box(mb, a, b, -ft / 2, ft / 2, zt - fw / 2, zt + fw / 2, 'joinery')          # transom
    m = (a + b) / 2
    seg_box(mb, m - d * 0.03, m + d * 0.03, -ft / 2, ft / 2, z0, zt, 'joinery')       # meeting stile
    if door:   # solid lower panels of a glazed door
        seg_box(mb, a + d * fw, b - d * fw, -0.03, 0.03, z0 + fw, z0 + 0.9, 'joinery')
        z0 = z0 + 0.9
    sw, so = 0.055, 0.04
    # sashes, set back
    for p0, p1, za, zb in ((a + d * fw, m - d * 0.03, z0 + fw, zt - fw / 2), (m + d * 0.03, b - d * fw, z0 + fw, zt - fw / 2),
                           (a + d * fw, b - d * fw, zt + fw / 2, z1 - fw)):
        seg_box(mb, p0, p1, so - 0.025, so + 0.025, za, za + sw, 'joinery')
        seg_box(mb, p0, p1, so - 0.025, so + 0.025, zb - sw, zb, 'joinery')
        seg_box(mb, p0, p0 + d * sw, so - 0.025, so + 0.025, za, zb, 'joinery')
        seg_box(mb, p1 - d * sw, p1, so - 0.025, so + 0.025, za, zb, 'joinery')
    # glazing bars
    gb = 0.025
    for fx in (0.25, 0.75):
        p = a + d * (W * fx)
        seg_box(mb, p - d * gb / 2, p + d * gb / 2, so - 0.015, so + 0.015, z0 + fw, zt - fw / 2, 'joinery')
    for fz in (1 / 3, 2 / 3):
        zz = z0 + fw + (zt - fw / 2 - z0 - fw) * fz
        seg_box(mb, a + d * fw, b - d * fw, so - 0.015, so + 0.015, zz - gb / 2, zz + gb / 2, 'joinery')
    pane(mb, a + d * fw + Vector((-d.y, d.x)) * (so + 0.025), b - d * fw + Vector((-d.y, d.x)) * (so + 0.025), z0 + fw, z1 - fw)
    if not door and z0 > 0.5:     # interior oak sill board
        seg_box(mb, a - d * 0.05, b + d * 0.05, ft / 2, ft / 2 + 0.32, z0 - 0.03, z0 + 0.01, 'door')


def window_simple(mb, a, b, z0, z1, n_in, depth):
    """Cheap window for surrounding buildings: frame, cross bars, glass, all in two depths."""
    a = Vector(a[:2]) + n_in * depth
    b = Vector(b[:2]) + n_in * depth
    d = (b - a).normalized()
    fw = 0.07
    seg_box(mb, a, b, -0.04, 0.04, z0, z0 + fw, 'frame')
    seg_box(mb, a, b, -0.04, 0.04, z1 - fw, z1, 'frame')
    seg_box(mb, a, a + d * fw, -0.04, 0.04, z0, z1, 'frame')
    seg_box(mb, b - d * fw, b, -0.04, 0.04, z0, z1, 'frame')
    m = (a + b) / 2
    seg_box(mb, m - d * 0.025, m + d * 0.025, -0.03, 0.03, z0, z1, 'frame')
    zt = z0 + (z1 - z0) * 0.68
    seg_box(mb, a, b, -0.03, 0.03, zt - 0.025, zt + 0.025, 'frame')
    pane(mb, a + Vector((-d.y, d.x)) * 0.05, b + Vector((-d.y, d.x)) * 0.05, z0, z1)


def pane(mb, a, b, z0, z1):
    """Single double-sided glass quad (no compounding alpha)."""
    mb.poly([Vector((a.x, a.y, z0)), Vector((b.x, b.y, z0)), Vector((b.x, b.y, z1)), Vector((a.x, a.y, z1))], 'glass')


def interior_door(mb, a0, d, o, t, leaves=True, side=1):
    """Casing on both wall faces + two panelled leaves opened 90 deg on one side.
    Wall runs from a0 along d, centred on its axis with thickness t."""
    u0, u1, z0, z1 = o
    n = Vector((-d.y, d.x))
    a, b = a0 + d * u0, a0 + d * u1
    cw = 0.14
    for sgn in (-1, 1):
        f0, f1 = sgn * (t / 2), sgn * (t / 2 + 0.05)
        lo, hi = min(f0, f1), max(f0, f1)
        seg_box(mb, a - d * cw, a, lo, hi, z0, z1 + cw, 'door_case')
        seg_box(mb, b, b + d * cw, lo, hi, z0, z1 + cw, 'door_case')
        seg_box(mb, a - d * cw, b + d * cw, lo, hi, z1, z1 + cw, 'door_case')
        seg_box(mb, a - d * (cw + 0.1), b + d * (cw + 0.1), lo, hi, z1 + cw, z1 + cw + 0.12, 'door_case')
    if not leaves:
        return
    lw = (u1 - u0) / 2
    face = side * (t / 2)
    for hinge, sgn_d in ((a, 1), (b, -1)):
        h = hinge + n * face
        e = h + n * (side * lw)
        ld = (e - h).normalized()
        seg_box(mb, h + d * (sgn_d * 0.0), e, -0.025 * sgn_d, 0.025 * sgn_d, z0 + 0.01, z1 - 0.02, 'door_int')
        # recessed fields framed by 15 mm bolection mouldings on both faces
        for pz0, pz1 in ((z0 + 0.25, z0 + (z1 - z0) * 0.42), (z0 + (z1 - z0) * 0.5, z1 - 0.25)):
            p0, p1 = h + ld * 0.12, e - ld * 0.12
            for o0, o1 in ((-0.04, -0.025), (0.025, 0.04)):
                seg_box(mb, p0, p1, o0, o1, pz0, pz0 + 0.035, 'door_case')
                seg_box(mb, p0, p1, o0, o1, pz1 - 0.035, pz1, 'door_case')
                seg_box(mb, p0, p0 + ld * 0.035, o0, o1, pz0, pz1, 'door_case')
                seg_box(mb, p1 - ld * 0.035, p1, o0, o1, pz0, pz1, 'door_case')
        for hz in (z0 + 0.3, (z0 + z1) / 2, z1 - 0.35):        # hinge barrels
            hb = h + ld * 0.0
            _prism(mb, Vector((hb.x, hb.y, hz - 0.07)), Vector((hb.x, hb.y, hz + 0.07)), 0.012, 0.012, 'gold', seg=6)
        hp = e - ld * 0.09
        for sgn2 in (-1, 1):
            esc = hp + Vector((d.x, d.y)) * 0.0
            base_ = Vector((esc.x, esc.y, z0 + 1.05)) + Vector((-ld.y, ld.x, 0)) * (0.03 * sgn2)
            _prism(mb, base_ - Vector((0, 0, 0.06)), base_ + Vector((0, 0, 0.06)), 0.018, 0.018, 'gold', seg=4)   # escutcheon
            lever_end = base_ + Vector((-ld.y, ld.x, 0)) * (0.05 * sgn2) - Vector((ld.x, ld.y, 0)) * 0.11
            _prism(mb, base_ + Vector((-ld.y, ld.x, 0)) * (0.01 * sgn2), lever_end, 0.009, 0.008, 'gold', seg=5)


def gothic_window(trim, win, a, b, z0, z1, n_o):
    """Exposed Gothic tracery window: stone frame, central mullion, two lancets under a pointed head."""
    d = (b - a).normalized()
    m = (a + b) / 2
    w = (b - a).length
    seg_box(trim, a - d * 0.2, a, -0.1, 0.25, z0, z1, 'stone')
    seg_box(trim, b, b + d * 0.2, -0.1, 0.25, z0, z1, 'stone')
    seg_box(trim, m - d * 0.07, m + d * 0.07, 0.0, 0.25, z0, z1 - 0.15, 'stone')
    seg_box(trim, a - d * 0.25, b + d * 0.25, -0.12, 0.3, z0 - 0.15, z0, 'stone')
    for k in range(10):          # pointed head: two arcs meeting at the apex
        t0, t1 = k / 10, (k + 1) / 10
        for side in (-1, 1):
            p0 = m + d * (side * w / 2 * math.cos(t0 * math.pi / 2.4))
            p1 = m + d * (side * w / 2 * math.cos(t1 * math.pi / 2.4))
            h0, h1 = z1 - 0.8 + 0.8 * math.sin(t0 * math.pi / 2), z1 - 0.8 + 0.8 * math.sin(t1 * math.pi / 2)
            _prism(trim, Vector((p0.x, p0.y, h0)) + Vector((n_o.x, n_o.y, 0)) * 0.1, Vector((p1.x, p1.y, h1)) + Vector((n_o.x, n_o.y, 0)) * 0.1, 0.07, 0.07, 'stone', seg=5)
    oval_ring(trim, m + n_o * 0.12, -n_o, 0.22, 0.22, z1 - 0.55, 0.05, 'stone')
    pane(win, a + n_o * 0.3, b + n_o * 0.3, z0 + 0.05, z1 - 0.05)


def closed_arch_door(mb, a, b, z0, z1, n_in, depth, seg=12):
    """Closed round-headed double door: oak leaves with raised panels and a fanlight bar,
    set `depth` into the wall; the head follows arch_head's semicircle."""
    a = Vector(a[:2]) + n_in * depth
    b = Vector(b[:2]) + n_in * depth
    W = (b - a).length
    d = (b - a) / W
    r = W / 2
    zs = z1 - min(r, 1.6)
    mid = (a + b) / 2
    arc = [(mid - d * (r * math.cos(math.pi * k / seg)), zs + min(r, 1.6) * math.sin(math.pi * k / seg)) for k in range(seg + 1)]
    for off, flip in ((0.0, False), (0.08, True)):
        face = [Vector(((a + n_in * off).x, (a + n_in * off).y, z0))] + \
               [Vector(((p + n_in * off).x, (p + n_in * off).y, h)) for p, h in arc] + [Vector(((b + n_in * off).x, (b + n_in * off).y, z0))]
        if geometry.normal(face).to_2d().dot(n_in) > 0:
            face.reverse()
        mb.poly(list(reversed(face)) if flip else face, 'door')
    for k in range(seg):                                   # frame following the head
        (p0, h0), (p1, h1) = arc[k], arc[k + 1]
        _prism(mb, Vector((p0.x, p0.y, h0)) - Vector((n_in.x, n_in.y, 0)) * 0.03, Vector((p1.x, p1.y, h1)) - Vector((n_in.x, n_in.y, 0)) * 0.03,
               0.05, 0.05, 'joinery', seg=4)
    seg_box(mb, a, b, -0.05, 0.05, zs - 0.06, zs + 0.04, 'joinery')          # transom under the fanlight
    seg_box(mb, mid - d * 0.03, mid + d * 0.03, -0.05, 0.05, z0, zs, 'joinery')
    for side in (-1, 1):                                   # three raised panels per leaf
        c0 = mid + d * (side * r / 2)
        pw = r * 0.62
        for j, (pz0, pz1) in enumerate(((z0 + 0.25, z0 + 0.95), (z0 + 1.15, zs - 0.9), (zs - 0.7, zs - 0.2))):
            seg_box(mb, c0 - d * (pw / 2), c0 + d * (pw / 2), -0.03, 0.03, pz0, pz1, 'door')
    for side in (-1, 1):
        hp = mid + d * (side * 0.12) - n_in * 0.05
        _prism(mb, Vector((hp.x, hp.y, z0 + 1.05)), Vector((hp.x, hp.y, z0 + 1.35)), 0.018, 0.018, 'gold', seg=5)


def door_leaves(mb, a, b, n_in, z0, z1, depth, leaf=1.6):
    """Opened gate leaves folded against the reveal."""
    a = Vector(a[:2]) + n_in * (depth * 0.5)
    b = Vector(b[:2]) + n_in * (depth * 0.5)
    for p, s in ((a, 1), (b, -1)):
        seg_box(mb, p, p + n_in * leaf, -0.08 * s, 0.0, z0, z1 - 0.3, 'door')


def balcony(trim, floors, c, d, out, hw=4.6):
    """Stone balcony across the three central axes of the risalit (photo 04), on rusticated pillars."""
    dep, z = 1.5, FLOOR_Z[1]          # shallow, carried by the facade (photos 04-06), not a portico
    p0, p1 = c - d * hw, c + d * hw
    floors.box([p0, p1, p1 + out * dep, p0 + out * dep], z - 0.45, z, 'stone', top='marble')
    trim.box([p0 - d * 0.1 + out * (-0.02), p1 + d * 0.1, p1 + d * 0.1 + out * (dep + 0.15), p0 - d * 0.1 + out * (dep + 0.15)],
             z - 0.75, z - 0.45, 'frame')
    for sgn, off_ in ((-1, hw - 0.6), (1, hw - 0.6), (-1, 2.55), (1, 2.55)):
        q = c + d * (sgn * off_)
        # facade pilaster up to the balcony + a stepped stone console under the slab
        trim.box([q - d * 0.4, q + d * 0.4, q + d * 0.4 + out * 0.28, q - d * 0.4 + out * 0.28], -0.5, z - 0.75, 'rustica')
        for (dz0, dz1, reach, hw_) in ((-1.9, -1.35, 0.55, 0.3), (-1.35, -0.75, dep - 0.05, 0.34)):
            trim.box([q - d * hw_, q + d * hw_, q + d * hw_ + out * reach, q - d * hw_ + out * reach], z + dz0, z + dz1, 'stone')
    # balustrade: rail + balusters along the three open sides
    rail = [(p0 + out * dep, p1 + out * dep), (p0, p0 + out * dep), (p1, p1 + out * dep)]
    for a, b in rail:
        L = (b - a).length
        dd = (b - a) / L
        nrm = Vector((-dd.y, dd.x))
        floors.box([a - nrm * 0.12, b - nrm * 0.12, b + nrm * 0.12, a + nrm * 0.12], z + 0.9, z + 1.05, 'stone')
        for k in range(int(L / 0.32)):
            m = a + dd * (0.16 + k * 0.32)
            trim.box([m - dd * 0.06 - nrm * 0.06, m + dd * 0.06 - nrm * 0.06, m + dd * 0.06 + nrm * 0.06, m - dd * 0.06 + nrm * 0.06],
                     z, z + 0.9, 'stone')
        floors.box([a - nrm * 0.05, b - nrm * 0.05, b + nrm * 0.05, a + nrm * 0.05], z, z + 0.9, 'invisible')


def arch_head(mb, a, b, z_top, off, t, mat, seg=12, rise=None):
    """Turn the top of a rectangular opening a-b (wall thickness t to the LEFT from `off`)
    into a round arch: fills the spandrels between the arc and the lintel at z_top."""
    a, b = Vector(a[:2]), Vector(b[:2])
    w = (b - a).length
    d = (b - a) / w
    n = Vector((-d.y, d.x))
    r = w / 2
    rise = min(r, 1.6) if rise is None else min(rise, r)   # semicircle, or segmental when given
    zs = z_top - rise
    mid = (a + b) / 2
    pts = []
    for k in range(seg + 1):
        th = math.pi * k / seg
        pts.append((mid - d * (r * math.cos(th)), zs + rise * math.sin(th)))
    for k in range(seg):
        (p0, h0), (p1, h1) = pts[k], pts[k + 1]
        for o_, flip in ((off, False), (off + t, True)):
            q0, q1 = p0 + n * o_, p1 + n * o_
            quad = [Vector((q0.x, q0.y, h0)), Vector((q1.x, q1.y, h1)), Vector((q1.x, q1.y, z_top)), Vector((q0.x, q0.y, z_top))]
            mb.poly(list(reversed(quad)) if flip else quad, mat)
        f0, f1 = p0 + n * off, p1 + n * off
        g0, g1 = p0 + n * (off + t), p1 + n * (off + t)
        mb.poly([Vector((f1.x, f1.y, h1)), Vector((f0.x, f0.y, h0)), Vector((g0.x, g0.y, h0)), Vector((g1.x, g1.y, h1))], mat)   # soffit


def fountain(mb, poly, T):
    """Baroque basin from an OSM water polygon: moulded rim, water, rock-pile centre with jets."""
    if poly_area(poly) < 0:
        poly = list(reversed(poly))
    c = sum((Vector(p) for p in poly), Vector((0, 0))) / len(poly)
    z = T.h(c.x, c.y)
    outer = [Vector(p) for p in poly]
    inner = offset_poly(outer, -0.55)
    slab(mb, [outer, inner], z + 0.55, 0.9, 'marble', 'stone', 'marble')
    slab(mb, [offset_poly(outer, 0.08), outer], z + 0.15, 0.4, 'stone', 'stone', 'stone')
    slab(mb, [inner], z + 0.35, 0.6, 'water', 'stone', 'stone')
    rr = random.Random(int(c.x * 10) + int(c.y * 7))
    for k in range(42):        # irregular limestone mound
        a = rr.uniform(0, 2 * math.pi)
        rad = 1.15 * math.sqrt(rr.random())
        hz = z + 0.35 + (1.0 - rad / 1.15) * 0.75 + rr.uniform(-0.05, 0.1)
        sz = rr.uniform(0.16, 0.4)
        ellipsoid(mb, Vector((c.x + math.cos(a) * rad, c.y + math.sin(a) * rad, hz)), sz * rr.uniform(0.9, 1.4),
                  sz * rr.uniform(0.8, 1.2), sz * rr.uniform(0.55, 0.85), rr.uniform(0, 3.1), rr.uniform(-0.3, 0.3), 'limestone', subdiv=1)
    for k in range(len(outer)):    # rounded coping lip
        p0, p1 = outer[k], outer[(k + 1) % len(outer)]
        nrm2 = Vector(((p1 - p0).y, -(p1 - p0).x)).normalized()
        sweep(mb, p0, p1, [(0.0, 0.0), (0.03, 0.04), (0.06, 0.1), (0.06, 0.16), (0.03, 0.2), (0.0, 0.22), (-0.55, 0.22), (-0.55, 0.0)],
              z + 0.55, 'limestone', nrm2)
    # water jets: central plume + arcs from the rock pile (non-colliding, see fountain_jets mesh)
    rim = max((Vector(p) - c).length for p in poly) - 1.2
    for k in range(8):
        a = 2 * math.pi * k / 8
        dvec = Vector((math.cos(a), math.sin(a)))
        nrm = Vector((-dvec.y, dvec.x))
        pts = []
        jh = random.uniform(0.8, 1.3)
        reach = random.uniform(0.45, 0.62)
        for j in range(11):
            t = j / 10
            pr = c + dvec * (0.6 + t * rim * reach)
            pts.append(Vector((pr.x, pr.y, z + 1.1 + jh * math.sin(math.pi * t) - 0.75 * t)))
        for j in range(10):
            _prism(JETS, pts[j], pts[j + 1], 0.012 + 0.004 * j / 10, 0.012 + 0.004 * (j + 1) / 10, 'jet', seg=6)
        for dj in range(6):      # droplets scattering at the impact point
            q = pts[-1] + Vector((random.uniform(-0.12, 0.12), random.uniform(-0.12, 0.12), random.uniform(0.0, 0.25)))
            ellipsoid(JETS, q, 0.012, 0.012, 0.02, 0, 0, 'jet', subdiv=0)
    _prism(JETS, Vector((c.x, c.y, z + 1.0)), Vector((c.x, c.y, z + 2.3)), 0.03, 0.015, 'jet', seg=8)


def rust_gate(mb, a, b, d, z0, z1):
    """Rusticated stone portal with keystone."""
    for k in range(int((z1 - z0) / 0.6)):
        w = 0.7 if k % 2 else 0.45
        seg_box(mb, a - d * w, a, -0.18, 0.02, z0 + k * 0.6, z0 + k * 0.6 + 0.55, 'rustica')
        seg_box(mb, b, b + d * w, -0.18, 0.02, z0 + k * 0.6, z0 + k * 0.6 + 0.55, 'rustica')
    seg_box(mb, a - d * 0.7, b + d * 0.7, -0.22, 0.02, z1, z1 + 0.7, 'rustica')
    m = (a + b) / 2
    seg_box(mb, m - d * 0.3, m + d * 0.3, -0.3, 0.02, z1 - 0.3, z1 + 0.9, 'stone')


def build_dormers(roof, win, a, b, ra, rb, n=10, lo=0.22, hi=0.48, hw=0.8, h=1.9, gable=False):
    """Small Baroque dormers on the slope; lo/hi = foot and back of the dormer as fraction eave->ridge
    (the palace has a second row of small attic dormers higher up, photo 15)."""
    A = Vector((a.x, a.y, EAVE_Z))
    B = Vector((b.x, b.y, EAVE_Z))
    L = (B - A).length
    d = (B - A) / L
    n = n if not FAST else 3
    for k in range(n):
        t = (k + 0.5) / n * 0.8 + 0.1
        foot = A + (B - A) * t
        # point on slope 35% towards the ridge
        rp = Vector((ra.x, ra.y, RIDGE_Z)).lerp(Vector((rb.x, rb.y, RIDGE_Z)), t)
        s0 = foot.lerp(rp, lo)
        s1 = foot.lerp(rp, hi)
        p = [s0 - d * hw, s0 + d * hw]
        q = [Vector((s1.x, s1.y, s0.z)) - d * hw, Vector((s1.x, s1.y, s0.z)) + d * hw]
        top0, top1 = s0.z + h, s0.z + h + 0.7
        # front
        roof.poly([p[0], p[1], p[1] + Vector((0, 0, h)), p[0] + Vector((0, 0, h))], 'plaster')
        mid0 = (p[0] + p[1]) / 2
        back = Vector((q[0].x - p[0].x, q[0].y - p[0].y, 0))
        if gable:          # courtyard dormers: triangular pediment and pitched roof (photo 01)
            g0, g1 = p[0] + Vector((0, 0, h)), p[1] + Vector((0, 0, h))
            gt = mid0 + Vector((0, 0, h + 0.75 * hw))
            roof.poly([g0, g1, gt], 'plaster')
            for j, s in ((0, -1), (1, 1)):
                pts = [p[j], q[j], q[j] + Vector((0, 0, h)), p[j] + Vector((0, 0, h))]
                if s < 0:
                    pts.reverse()
                roof.poly(pts, 'plaster')
            e0, e1, et = g0 - d * 0.12 - back.normalized() * 0.15, g1 + d * 0.12 - back.normalized() * 0.15, gt - back.normalized() * 0.15
            roof.poly([e0 + Vector((0, 0, 0.05)), et + Vector((0, 0, 0.08)), et + back + Vector((0, 0, 0.08)), e0 + back + Vector((0, 0, 0.05))], 'roof_palace')
            roof.poly([et + Vector((0, 0, 0.08)), e1 + Vector((0, 0, 0.05)), e1 + back + Vector((0, 0, 0.05)), et + back + Vector((0, 0, 0.08))], 'roof_palace')
            bn = back.to_2d().normalized()
            gm, dd2 = mid0.to_2d(), d.to_2d()
            roof.box([gm - dd2 * (hw + 0.1) - bn * 0.15, gm + dd2 * (hw + 0.1) - bn * 0.15, gm + dd2 * (hw + 0.1) + bn * 0.05,
                      gm - dd2 * (hw + 0.1) + bn * 0.05], g0.z - 0.03, g0.z + 0.09, 'frame')
            nrm = Vector((-d.y, d.x, 0))
            wa = p[0].to_2d() + d.to_2d() * 0.32
            wb = p[1].to_2d() - d.to_2d() * 0.32
            window_unit(win, wb, wa, s0.z + 0.13 * h, s0.z + h - 0.1 * h, nrm.to_2d() * -1, 0.05)
            continue
        # segmental (round-topped) dormer head, as on the palace today
        arc = [mid0 - d * (hw * math.cos(math.pi * k / 10)) + Vector((0, 0, h + 0.29 * h * math.sin(math.pi * k / 10))) for k in range(11)]
        for k in range(10):
            zb = p[0].z + h
            roof.poly([Vector((arc[k].x, arc[k].y, zb)), Vector((arc[k + 1].x, arc[k + 1].y, zb)), arc[k + 1], arc[k]], 'plaster')
        # sides
        for j, s in ((0, -1), (1, 1)):
            pts = [p[j], q[j], q[j] + Vector((0, 0, h)), p[j] + Vector((0, 0, h))]
            if s < 0:
                pts.reverse()
            roof.poly(pts, 'plaster')
        # barrel roof following the segmental head
        back = Vector((q[0].x - p[0].x, q[0].y - p[0].y, 0))
        for k in range(10):
            a0 = arc[k] + Vector((0, 0, 0.08)) - d * 0.12 * math.cos(math.pi * k / 10)
            a1 = arc[k + 1] + Vector((0, 0, 0.08)) - d * 0.12 * math.cos(math.pi * (k + 1) / 10)
            roof.poly([a1, a0, a0 + back, a1 + back], 'roof_palace')
        nrm = Vector((-d.y, d.x, 0))
        wa = p[0].to_2d() + d.to_2d() * 0.35
        wb = p[1].to_2d() - d.to_2d() * 0.35
        window_unit(win, wb, wa, s0.z + 0.13 * h, s0.z + h - 0.1 * h, nrm.to_2d() * -1, 0.05)


def build_stairs(walls, floors, ramps, trim, pa, pb, fb, fa, n, d):
    """Switchback grand staircase (Theresian staircase stand-in) per storey.
    pa-pb: corridor-side edge of the hole, fa-fb: outer side. Flight 1 runs along +n on
    the pa side, landing at the far end, flight 2 returns on the pb side."""
    width = (pb - pa).length
    depth = (fa - pa).length
    gap = max(0.5, min(1.5, width - 2 * 1.9))      # open well between the flights (refs 28/29), flights >= 1.9 m
    globals()['STAIR_GAP'] = gap
    fw = (width - gap) / 2
    land = 2.6
    run = depth - land - 0.1
    for k in range(len(FLOOR_Z)):
        z0 = FLOOR_Z[k]
        z1 = FLOOR_Z[k + 1] if k + 1 < len(FLOOR_Z) else None
        if z1 is None:
            break
        zm = (z0 + z1) / 2
        nsteps = max(8, round((zm - z0) / 0.16))
        rise = (zm - z0) / nsteps
        tread = run / nsteps
        # landing at far end (mid-level) spanning both flights
        l0 = pa + n * run
        slab(floors, [[l0, l0 + d * width, l0 + d * width + n * (land + 0.1), l0 + n * (land + 0.1)]],
             zm, 0.35, 'marble', 'plaster_int', 'marble')
        for s in range(nsteps):
            # flight 1 (up along +n) next to pa, starting at the corridor landing
            q0 = pa + n * (s * tread)
            base = [q0, q0 + d * fw, q0 + d * fw + n * tread, q0 + n * tread]
            floors.box(base, z0 + s * rise - 0.35, z0 + (s + 1) * rise, 'marble', top='marble', bottom='plaster_int')
            cm = q0 + d * (fw / 2)
            trim.box([cm - d * fw * 0.32, cm + d * fw * 0.32, cm + d * fw * 0.32 + n * tread, cm - d * fw * 0.32 + n * tread],
                     z0 + (s + 1) * rise, z0 + (s + 1) * rise + 0.012, 'carpet')
            trim.box([cm - d * fw * 0.32 - n * 0.012, cm + d * fw * 0.32 - n * 0.012, cm + d * fw * 0.32, cm - d * fw * 0.32],
                     z0 + s * rise, z0 + (s + 1) * rise + 0.012, 'carpet')          # riser: continuous runner
            # flight 2 (up along -n) next to pb, from the landing back to the corridor side
            r0 = pa + d * (width - fw) + n * (run - (s + 1) * tread)
            base2 = [r0, r0 + d * fw, r0 + d * fw + n * tread, r0 + n * tread]
            floors.box(base2, zm + s * rise - 0.35, zm + (s + 1) * rise, 'marble', top='marble', bottom='plaster_int')
            cm2 = r0 + d * (fw / 2)
            trim.box([cm2 - d * fw * 0.32, cm2 + d * fw * 0.32, cm2 + d * fw * 0.32 + n * tread, cm2 - d * fw * 0.32 + n * tread],
                     zm + (s + 1) * rise, zm + (s + 1) * rise + 0.012, 'carpet')
            rf = cm2 + n * tread
            trim.box([rf - d * fw * 0.32, rf + d * fw * 0.32, rf + d * fw * 0.32 + n * 0.012, rf - d * fw * 0.32 + n * 0.012],
                     zm + s * rise, zm + (s + 1) * rise + 0.012, 'carpet')
        # collision ramps
        a0 = pa
        ramps.poly_up([Vector((a0.x, a0.y, z0 + rise)), Vector(((a0 + d * fw).x, (a0 + d * fw).y, z0 + rise)),
                    Vector(((a0 + d * fw + n * run).x, (a0 + d * fw + n * run).y, zm)),
                    Vector(((a0 + n * run).x, (a0 + n * run).y, zm))], 'stone')
        b0 = pa + d * (width - fw)
        ramps.poly_up([Vector(((b0 + n * run).x, (b0 + n * run).y, zm + rise)),
                    Vector(((b0 + d * fw + n * run).x, (b0 + d * fw + n * run).y, zm + rise)),
                    Vector(((b0 + d * fw).x, (b0 + d * fw).y, z1)), Vector((b0.x, b0.y, z1))], 'stone')
        # balustrade between flights and on the open side
        mid = pa + d * (width / 2)
        for corner in (pa + n * run + d * (fw + 0.25), pa + n * run + d * (width - fw - 0.25)):   # pillars under the landing
            floors.box([corner - d * 0.25 - n * 0.25, corner + d * 0.25 - n * 0.25, corner + d * 0.25 + n * 0.25,
                        corner - d * 0.25 + n * 0.25], z0, zm - 0.35, 'marble')
        for side, (za_, zb_) in ((pa + d * fw, (z0, zm)), (pa + d * (width - fw), (z1, zm))):
            a_, b_ = side, side + n * run
            sloped_prism(ramps, a_, b_, za_, zb_, -0.09, 0.09, -0.3, 0.95, 'stone')       # collision-only guard; visible pierced balustrade: v2_interior
        for base_, (za_, zb_) in ((pa, (z0, zm)), (pa + d * (width - fw), (z1, zm))):
            q0_, q1_ = base_, base_ + d * fw
            e0_, e1_ = q0_ + n * run, q1_ + n * run
            zz0, zz1 = za_ - 0.35 - rise, zb_ - 0.35 - rise
            floors.poly([Vector((q1_.x, q1_.y, zz0)), Vector((q0_.x, q0_.y, zz0)),
                         Vector((e0_.x, e0_.y, zz1)), Vector((e1_.x, e1_.y, zz1))], 'plaster_int')   # soffit
            sg = 1 if Vector((-n.y, n.x)).dot(d) > 0 else -1          # stucco panel frame on the soffit
            for edge, (o0_, o1_) in ((q0_, (0.0, 0.16)), (q1_, (-0.16, 0.0)), (q0_, (0.3, 0.34)), (q1_, (-0.34, -0.3))):
                lo_, hi_ = sorted((o0_ * sg, o1_ * sg))
                gold_ = abs(o0_) > 0.2 or abs(o1_) > 0.2
                sloped_prism(trim, edge, edge + n * run, zz0, zz1, lo_, hi_, -0.09 if not gold_ else -0.03, -0.004,
                             'gold' if gold_ else 'plaster_int')
    # lantern / chandelier
    c = (pa + pb + fa + fb) / 4
    seg_box(trim, c - d * 0.02, c + d * 0.02, -0.02, 0.02, EAVE_Z - 6, EAVE_Z, 'metal')
    sph_mb_ring(trim, c, EAVE_Z - 7.2, 0.6, 'gold')


def sloped_prism(mb, a, b, za, zb, off0, off1, hb, ht, mat):
    """Prism along a->b whose bottom/top follow the line za->zb (stair strings, handrails)."""
    a, b = Vector(a[:2]), Vector(b[:2])
    d = (b - a).normalized()
    n = Vector((-d.y, d.x))
    P = lambda p, o, z: Vector(((p + n * o).x, (p + n * o).y, z))
    bot = [P(a, off0, za + hb), P(b, off0, zb + hb), P(b, off1, zb + hb), P(a, off1, za + hb)]
    top = [P(a, off0, za + ht), P(b, off0, zb + ht), P(b, off1, zb + ht), P(a, off1, za + ht)]
    mb.poly(top, mat)
    mb.poly(list(reversed(bot)), mat)
    for k in range(4):
        j = (k + 1) % 4
        mb.poly([bot[k], bot[j], top[j], top[k]], mat)


def well(mb, c):
    r, h = 1.4, 0.9
    seg = 16
    for k in range(seg):
        a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        p0 = c + Vector((math.cos(a0), math.sin(a0))) * r
        p1 = c + Vector((math.cos(a1), math.sin(a1))) * r
        q0 = c + Vector((math.cos(a0), math.sin(a0))) * (r - 0.35)
        q1 = c + Vector((math.cos(a1), math.sin(a1))) * (r - 0.35)
        mb.box([p0, p1, q1, q0], -1.0, h, 'stone')
        mb.poly([Vector((q1.x, q1.y, -0.6)), Vector((q0.x, q0.y, -0.6)), Vector((c.x, c.y, -0.6))], 'water')
    for s in (-1, 1):            # small square stone portal beside the curb (SPEC)
        p = c + Vector((s * (r + 0.05), 0.0))
        mb.box([p - Vector((0.17, 0.17)), p + Vector((0.17, -0.17)), p + Vector((0.17, 0.17)), p + Vector((-0.17, 0.17))], -0.2, h + 1.6, 'stone')
    mb.box([c + Vector((-r - 0.3, -0.2)), c + Vector((r + 0.3, -0.2)), c + Vector((r + 0.3, 0.2)), c + Vector((-r - 0.3, 0.2))], h + 1.6, h + 1.95, 'stone')
    _prism(mb, Vector((c.x, c.y, h + 1.55)), Vector((c.x, c.y, h + 0.6)), 0.01, 0.01, 'metal', seg=4)


# ---------------------------------------------------------------- other buildings
NAV = {}
HONOUR_COURT = [(-34.0, -80.0), (32.0, -80.0), (36.0, -41.5), (-40.0, -38.0)]
HALL_PARTS = []
SMOOTH = None
def points_all():
    return json.load(open(os.path.join(DATA, 'castle_local.json'))).get('points', [])


REPLACED_IDS = set()      # OSM ids rebuilt by a V2 module (generic extrusion/wall skipped)
PALACE_IDS = set(range(244267968, 244267982)) | {8160490, 1473406795}


def feature_height(t):
    if 'height' in t:
        try:
            return float(t['height'].split()[0])
        except ValueError:
            pass
    lv = t.get('building:levels')
    try:
        return float(lv) * 3.3 + 1.0 if lv else 7.0
    except ValueError:
        return 7.0


def passage_split(pts, passages, T):
    """A way tagged tunnel=building_passage running along a building edge (OSM draws the line ~1 m outside the
    outline, e.g. the Nicholas stairs under the NR SR chancellery, Codex V5 nicholas_04B): the ground storey steps
    back behind the passage, the upper storeys overhang it on piers. Returns (ground_pts, upper_pts, z_ceiling,
    piers) or None."""
    for line, half in passages:
        for a, b in zip(line, line[1:]):
            L = (b - a).length
            if L < 6.0:          # short passages are gate/arch openings modelled elsewhere
                continue
            d = (b - a) / L
            nn = Vector((-d.y, d.x))
            near = [i for i, p in enumerate(pts) if -0.6 <= (Vector(p) - a).dot(d) <= L + 0.6
                    and abs((Vector(p) - a).dot(nn)) < half + 1.2]
            if len(near) < 2:
                continue
            span = [(Vector(pts[i]) - a).dot(d) for i in near]
            if max(span) - min(span) < 0.6 * L:      # the facade must actually run along the passage
                continue
            ctr = Vector((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
            s = 1.0 if (ctr - a).dot(nn) > 0 else -1.0          # side of the line the building stands on
            ground, upper = [], []
            for i, p in enumerate(pts):
                v = Vector(p)
                if i in near:
                    off = (v - a).dot(nn)
                    ground.append(tuple(v + nn * (s * (half + 0.25) - off)))
                    upper.append(tuple(v + nn * (-s * (half + 0.6) - off)))
                else:
                    ground.append(tuple(v))
                    upper.append(tuple(v))
            # the passage itself (vault, ramps) is v2_fortress's; the building only lifts its floor clear above the
            # walking surface: 3.6 m over the highest point of the ramp/steps/terrain along it (walktest)
            walk = surface_bvh(('Fort_Ramps', 'Fort_Paths', 'Fort_Gates', 'Steps'))
            z_top = -1e9
            for k in range(int(L / 0.5) + 5):
                q = a + d * (k * 0.5 - 1.0)
                zt_ = T.h(q.x, q.y)
                zs_ = surface_z(walk, q.x, q.y, zt_, up=4.0, down=1.0)
                z_top = max(z_top, zt_, zs_ if zs_ is not None and zs_ < zt_ + 3.0 else zt_)
            return ground, upper, z_top + 3.6, [], d, nn * -s
    return None


def build_city(T, feats, coll):
    bmb = ChunkMB('Buildings-col')
    passages = []
    for f in feats:
        if f['kind'] == 'road' and f['tags'].get('tunnel') == 'building_passage':
            try:
                wdt = float(f['tags'].get('width', '').split()[0])
            except (ValueError, IndexError):
                wdt = 2.8 if f['tags'].get('highway') == 'steps' else 3.0
            passages.append(([Vector(q[:2]) for q in f['pts']], wdt / 2))
    rmb = ChunkMB('Building_Roofs-col')
    wmb = ChunkMB('Walls-col')
    parts = [f for f in feats if f['kind'] == 'part' and f['id'] not in PALACE_IDS]
    part_cent = [(sum(p[0] for p in f['pts']) / len(f['pts']), sum(p[1] for p in f['pts']) / len(f['pts'])) for f in parts]
    count = 0
    all_polys = [f['pts'] for f in feats if f.get('kind') in ('building', 'part')] + [list(map(tuple, OUTER))]
    pav_join = MB('Pavilion_Windows')
    near_join = ChunkMB('City_Windows', tile=80.0)
    for f in feats:
        if f['id'] in PALACE_IDS or f['id'] in REPLACED_IDS or f.get('kind') not in ('building', 'part'):
            continue
        pts = f['pts'][:-1] if f['closed'] and f['pts'][0] == f['pts'][-1] else f['pts']
        if len(pts) < 3:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        if point_in_poly(cx, cy, OUTER) or math.hypot(cx, cy) > 330:
            continue
        if f['kind'] == 'building' and any(point_in_poly(px, py, pts) for px, py in part_cent):
            continue   # drawn by its parts
        t = f['tags']
        if t.get('building') in ('roof', 'carport') or t.get('location') == 'underground' or t.get('parking') == 'underground':
            continue
        if poly_area(pts) < 0:
            pts = list(reversed(pts))
        hs = [T.h(p[0], p[1]) for p in pts]
        # foundations reach the lowest ground just outside the walls too: carved approaches (Vienna gate pavilion,
        # Codex V5 vienna_01B) left the wall foot hanging over the cut
        hs_out = [T.h(p[0] + (p[0] - cx) / max(1e-6, math.hypot(p[0] - cx, p[1] - cy)) * 1.5,
                      p[1] + (p[1] - cy) / max(1e-6, math.hypot(p[0] - cx, p[1] - cy)) * 1.5) for p in pts]
        base = min(hs + hs_out) - 1.5
        ground = max(hs)
        h = feature_height(t)
        if f['id'] == 369605106:          # Garden Pavilion under the N facade (photos 11, 12): one tall storey, hipped roof
            gp_ = [(17.03, 26.47), (43.51, 19.74), (45.1, 28.0), (19.62, 34.98)]
            g0_ = min(T.h(x_, y_) for x_, y_ in gp_)
            top_ = g0_ + 6.6
            facade_walls(bmb, gp_, g0_ - 1.5, top_, 'plaster', g0_, near + [list(map(tuple, OUTER))], floor_h=9.0,
                         win=(1.35, 3.1, 1.1), spacing=3.0, joinery=pav_join, arched=True)
            for i_ in range(4):
                a_, b_ = Vector(gp_[i_]), Vector(gp_[(i_ + 1) % 4])
                d_ = (b_ - a_).normalized()
                sweep(bmb, a_ - d_ * 0.3, b_ + d_ * 0.3, PROF_EAVE, top_ - 0.8, 'frame', Vector((d_.y, -d_.x)))
                seg_box(bmb, a_, b_, -0.1, 0.0, g0_ - 0.3, g0_ + 0.7, 'stone')
            roof_generic(rmb, [(x_ + (x_ - 31.3) * 0.05, y_ + (y_ - 27.3) * 0.05) for x_, y_ in gp_], top_, 3.6, 'hipped', mat='roof_palace')
            count += 1
            continue
        pavilion = f['id'] in (115596648, 115596652)      # Honour Court entrance pavilions (photo ref3)
        if pavilion:
            t = dict(t, **{'roof:shape': 'pavilion'})
            h = 5.4
        minh = float(t.get('min_height', 0) or 0)
        wall_top = ground + h - (float(t.get('roof:height', 0) or 0) if 'height' in t else 0)
        if 'height' not in t:
            wall_top = max(min(hs) + h, max(hs) + 0.65 * h)   # slope: uphill side keeps most of its storeys
        wmat = ['bldg_wall', 'bldg_wall2', 'bldg_wall3'][f['id'] % 3]
        if t.get('building:colour', '').lower() in ('white', '#ffffff'):
            wmat = 'plaster'
        zb = base if minh == 0 else min(hs) + minh
        near = [q for q in all_polys if q is not f['pts'] and abs(q[0][0] - cx) < 80 and abs(q[0][1] - cy) < 80]
        if pavilion:
            facade_walls(bmb, pts, zb, wall_top, 'plaster', min(hs), near, floor_h=6.0, win=(1.3, 2.4, 0.9),
                         spacing=2.7, joinery=pav_join)
            pcx = sum(p_.x for p_ in OUTER) / 4
            for i_ in range(len(pts)):                    # balustraded terrace roof (photo 04/05)
                a_, b_ = Vector(pts[i_]), Vector(pts[(i_ + 1) % len(pts)])
                m_ = (a_ + b_) / 2
                if dist_to_poly(m_.x, m_.y, OUTER) < 8.0:     # connecting stretch at the facade: pierced balustrade
                    balustrade(bmb, a_, b_, wall_top - 0.3, wall_top)
                else:                                          # main block: broad solid attic (photos 05, 06)
                    seg_box(bmb, a_, b_, -0.3, 0.3, wall_top - 0.3, wall_top + 0.6, 'plaster')      # lower attic (Codex 9)
                    seg_box(bmb, a_, b_, -0.36, 0.36, wall_top + 0.6, wall_top + 0.72, 'frame')
                L_ = (b_ - a_).length
                if L_ < 0.5:
                    continue
                d_ = (b_ - a_) / L_
                out_ = Vector((d_.y, -d_.x))
                sweep(bmb, a_ - d_ * 0.3, b_ + d_ * 0.3, PROF_EAVE, wall_top - 1.15, 'plaster', out_)
                # grey sheet-metal cornice cap sloping out over the moulding (photo 05)
                e0, e1 = a_ - d_ * 0.5 + out_ * 0.5, b_ + d_ * 0.5 + out_ * 0.5          # cap projection 0.5 m (Codex 9)
                i0, i1 = a_ - d_ * 0.3 + out_ * 0.3, b_ + d_ * 0.3 + out_ * 0.3
                bmb.poly([Vector((e0.x, e0.y, wall_top - 0.62)), Vector((e1.x, e1.y, wall_top - 0.62)),
                          Vector((i1.x, i1.y, wall_top - 0.3)), Vector((i0.x, i0.y, wall_top - 0.3))], 'metal_roof')
                bmb.poly([Vector((e1.x, e1.y, wall_top - 0.62)), Vector((e0.x, e0.y, wall_top - 0.62)),
                          Vector((e0.x, e0.y, wall_top - 0.72)), Vector((e1.x, e1.y, wall_top - 0.72))], 'metal_roof')
                for c_ in (a_, b_):                       # corner pilaster strips
                    seg_box(bmb, c_ - d_ * 0.35 if c_ is b_ else c_, c_ if c_ is b_ else c_ + d_ * 0.35, -0.08, 0.0,
                            min(hs) + 0.6, wall_top - 1.15, 'plaster')
                seg_box(bmb, a_, b_, -0.12, 0.0, min(hs) - 0.3, min(hs) + 0.6, 'plaster')   # plinth
            # trophy group on the terrace corner next to the palace, facing the Honour Court axis
            top2 = sorted(pts, key=lambda q: -q[1])[:2]
            tc = min(top2, key=lambda q: abs(q[0] - pcx))
            tdir = Vector((pcx - tc[0], 0)).normalized() if abs(pcx - tc[0]) > 1 else Vector((1, 0))
            trophy(bmb, Vector(tc) + tdir * 1.2 + Vector((0, -1.0)), wall_top - 0.3, Vector((0, -1)), ped=1.45)
            roof_generic(rmb, pts, wall_top + 0.2, 1.1, 'hipped', mat='metal_roof')
            count += 1
            continue
        close = math.hypot(cx, cy) < 130 and not WEB
        ps = passage_split(pts, [(l_, h_) for l_, h_ in passages if dist_to_poly(l_[0].x, l_[0].y, pts) < 4.0
                                 or dist_to_poly(l_[-1].x, l_[-1].y, pts) < 4.0], T)
        if ps:
            gpts, upts, zc_, piers, d_, out_ = ps
            print('passage under building', f['id'], 'ceiling', round(zc_, 1))
            facade_walls(bmb, gpts, zb, zc_, wmat, min(hs), near, simple_join=near_join if close else None, ground_fn=T.h)
            facade_walls(bmb, upts, zc_, wall_top, wmat, zc_, near, simple_join=near_join if close else None)
            soffit = [Vector((x_, y_, zc_)) for x_, y_ in upts]
            for tri in geometry.tessellate_polygon([[tuple(v) for v in soffit]]):
                q_ = [soffit[tri[0]], soffit[tri[1]], soffit[tri[2]]]
                if geometry.normal(q_).z > 0:
                    q_.reverse()                      # faces down into the passage
                bmb.poly(q_, 'plaster')
            for c_ in piers:                          # arcade piers on the outer line
                zp_ = T.h(c_.x, c_.y)
                bmb.box([tuple(c_ + d_ * sx * 0.3 + out_ * sy * 0.3) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))],
                        zp_ - 1.0, zc_, wmat)
            pts = upts
        else:
            facade_walls(bmb, pts, zb, wall_top, wmat, min(hs), near, simple_join=near_join if close else None, ground_fn=T.h)
        shape = t.get('roof:shape', 'hipped' if t.get('building') not in ('garage', 'service', 'retail', 'industrial') else 'flat')
        rh = float(t.get('roof:height', 0) or 0) or (0.0 if shape == 'flat' else min(6.0, 0.35 * min_width(pts)))
        if f['id'] == 115596633:      # long range E of the garden: a row of transverse roof bays (Google Earth)
            A0, B0, B1, A1 = Vector((79.9, 103.0)), Vector((144.5, 117.8)), Vector((142.4, 129.5)), Vector((79.3, 114.9))
            B0 = min((Vector(q_) for q_ in pts), key=lambda v: (v - B0).length)     # overhang over the passage stairs
            nb = max(1, int((B0 - A0).length / 9.5))
            for k_ in range(nb):
                t0_, t1_ = k_ / nb, (k_ + 1) / nb
                q_ = [A0.lerp(B0, t0_), A0.lerp(B0, t1_), A1.lerp(B1, t1_), A1.lerp(B1, t0_)]
                roof_generic(rmb, [(v.x, v.y) for v in q_], wall_top, 4.2, 'hipped')
        else:
            roof_generic(rmb, pts, wall_top, rh, shape)
        if rh > 1.5 and shape != 'flat':        # brick chimneys with stone caps
            rng_c = random.Random(f['id'])
            for _ in range(rng_c.randint(1, 2)):
                ccx = cx + rng_c.uniform(-0.25, 0.25) * min_width(pts)
                ccy = cy + rng_c.uniform(-0.25, 0.25) * min_width(pts)
                if point_in_poly(ccx, ccy, pts):
                    q = [(ccx - 0.35, ccy - 0.3), (ccx + 0.35, ccy - 0.3), (ccx + 0.35, ccy + 0.3), (ccx - 0.35, ccy + 0.3)]
                    rmb.box(q, wall_top, wall_top + rh + 0.9, 'bldg_wall2')
                    rmb.box([(x_ - 0.05 * (1 if x_ > ccx else -1), y_ - 0.05 * (1 if y_ > ccy else -1)) for x_, y_ in q],
                            wall_top + rh + 0.9, wall_top + rh + 1.02, 'stone')
        count += 1
    garden_poly = next((f['pts'] for f in feats if f['tags'].get('name') == 'Baroková záhrada'), None)
    steps = [f for f in feats if f['kind'] == 'road' and f['tags'].get('highway') == 'steps']
    smb = MB('Steps-col')
    step_lines = []
    for f in steps:
        try:
            wdt = float(f['tags'].get('width', '2.5').split()[0])
        except ValueError:
            wdt = 2.5
        pts = [Vector(p) for p in f['pts']]
        if math.hypot(*pts[0]) > 320:
            continue
        step_lines.append((pts, wdt))
        if f['id'] not in REPLACED_IDS:      # V2 modules build some flights themselves (garden terrace stairs)
            build_steps(smb, T, pts, wdt)
    near_steps = lambda q: any(min(dist_seg(q, a, b) for a, b in zip(pl, pl[1:])) < w / 2 + 0.4 for pl, w in step_lines)
    for f in feats:
        if f['kind'] != 'wall' or f['id'] in REPLACED_IDS:
            continue
        t = f['tags']
        h = 2.2 if t.get('barrier') == 'retaining_wall' else 3.0
        th = 0.9 if t.get('barrier') == 'retaining_wall' else 1.2
        pts = f['pts']
        for a, b in zip(pts, pts[1:]):
            A, B = Vector(a), Vector(b)
            L = (B - A).length
            n = max(1, int(L / 3))
            dd = (B - A).normalized() if L > 1e-6 else Vector((1, 0))
            nn = Vector((-dd.y, dd.x))
            for k in range(n):
                p0, p1 = A.lerp(B, k / n), A.lerp(B, (k + 1) / n)
                pm = (p0 + p1) / 2
                if near_steps(pm):
                    continue      # opening where a staircase passes through
                # retaining / bastion walls: top follows the higher side, foot the lower side
                sides = [T.h(*(pm + nn * 3.5)), T.h(*(pm - nn * 3.5)), T.h(p0.x, p0.y), T.h(p1.x, p1.y)]
                lo, hi = min(sides), max(sides)
                if hi - lo > 1.5:          # retaining / bastion wall: parapet above the upper terrace
                    top = hi + 1.0
                else:                      # free-standing: low garden wall, castle curtain a bit higher
                    top = hi + (2.4 if t.get('wall') == 'castle_wall' else 1.1)
                if garden_poly and point_in_poly(pm.x, pm.y, offset_poly(garden_poly, 2.0)):
                    balustrade(wmb, p0, p1, lo, hi)
                    continue
                seg_box(wmb, p0, p1, -th / 2, th / 2, lo - 1.5, top, 'rubble')
                seg_box(wmb, p0, p1, -th / 2 - 0.1, th / 2 + 0.1, top, top + 0.25, 'stone')
    print('city buildings', count)
    return [o for m in (bmb, rmb, wmb) for o in m.build(coll)] + [smb.build(coll), pav_join.build(coll)] + near_join.build(coll)


def trophy(mb, c, z0, face, ped=0.55):
    """Baroque stone trophy of arms (Honour Court pavilions, photo 05): plinth, cartouche shield,
    plumed helmet, crossed standards and a cannon barrel, all in white stone."""
    side = Vector((-face.y, face.x))
    z = z0 + ped - 0.55
    mb.box([c + side * 0.8 - face * 0.5, c - side * 0.8 - face * 0.5, c - side * 0.8 + face * 0.5, c + side * 0.8 + face * 0.5],
           z0, z + 0.55, 'marble')
    mb.box([c + side * 0.9 - face * 0.6, c - side * 0.9 - face * 0.6, c - side * 0.9 + face * 0.6, c + side * 0.9 + face * 0.6],
           z + 0.45, z + 0.58, 'marble')
    zc = z + 1.35
    yaw = math.atan2(face.y, face.x)
    F = Vector((face.x, face.y, 0))
    S = Vector((side.x, side.y, 0))
    base3 = Vector((c.x, c.y, 0))
    ellipsoid(mb, base3 + Vector((0, 0, zc - 0.1)) - F * 0.1, 0.2, 0.42, 0.6, yaw, 0.0, 'marble')             # cuirass
    ellipsoid(mb, base3 + Vector((0, 0, zc - 0.05)) + F * 0.28, 0.08, 0.62, 0.72, yaw, 0.0, 'marble')         # oval cartouche shield
    ellipsoid(mb, base3 + Vector((0, 0, zc + 0.72)), 0.22, 0.2, 0.24, yaw, 0.0, 'marble')                      # helmet
    ellipsoid(mb, base3 + Vector((0, 0, zc + 0.56)) + F * 0.18, 0.12, 0.2, 0.05, yaw, 0.3, 'marble')          # visor brim
    ellipsoid(mb, base3 + Vector((0, 0, zc + 1.2)) - F * 0.2, 0.42, 0.14, 0.32, yaw, -0.6, 'marble')          # plume
    # mantle draped behind the arms: a fan of folded cloth strips spreading sideways and down (photo 05)
    top_m = base3 + Vector((0, 0, zc + 0.55)) - F * 0.25
    # one continuous pleated fan (adjacent folds share edges): separate strips read as floating cards (Codex V5: vienna_00)
    ring_in, ring_out = [], []
    for k_ in range(10):
        ang = math.radians(-78 + k_ * 17.33)
        dirv = S * math.sin(ang) - Vector((0, 0, 1)) * math.cos(ang)
        ring_in.append(top_m + dirv * 0.25)
        ring_out.append(top_m + dirv * (1.25 + 0.12 * (k_ % 2)) - F * (0.07 if k_ % 2 else -0.07))
    for k_ in range(9):
        q = [ring_in[k_], ring_out[k_], ring_out[k_ + 1], ring_in[k_ + 1]]
        mb.poly(q, 'marble')
        mb.poly(list(reversed(q)), 'marble')
    for sg in (-1, 1):                                                                                     # cannon barrels at the foot
        _prism(mb, base3 + Vector((0, 0, z + 0.75)) + S * sg * 0.3, base3 + Vector((0, 0, z + 0.95)) + S * sg * 1.05 + F * 0.25,
               0.13, 0.09, 'marble', seg=8)
    for sg in (-1, 1):
        base_ = Vector((c.x, c.y, z + 0.55)) + Vector((side.x, side.y, 0)) * sg * 0.25
        tip = Vector((c.x, c.y, z + 2.9)) + Vector((side.x, side.y, 0)) * sg * 1.1
        _prism(mb, base_, tip, 0.055, 0.045, 'marble', seg=6)
        fd = (tip - base_).normalized()
        f0 = tip - fd * 0.15
        f1 = tip - fd * 0.8
        out = Vector((side.x, side.y, 0)) * sg * 0.75
        # the flag cloth hangs from the staff as one drooping, folded sheet: folds share their edges
        cols = [(o, Vector((0, 0, -0.3 * o)) + F * (0.08 if k_ % 2 else -0.08) * (k_ > 0)) for k_, o in enumerate((0.0, 0.33, 0.66, 1.0))]
        for (o0, d0), (o1, d1) in zip(cols, cols[1:]):
            q0, q1 = f0 + out * o0 + d0, f1 + out * o0 + d0
            r0, r1 = f0 + out * o1 + d1, f1 + out * o1 + d1
            mb.poly([q0, q1, r1, r0], 'marble')
            mb.poly([q1, q0, r0, r1], 'marble')
    bar0 = Vector((c.x, c.y, z + 0.75)) - Vector((side.x, side.y, 0)) * 0.7 + Vector((face.x, face.y, 0)) * 0.3
    _prism(mb, bar0, bar0 + Vector((side.x, side.y, 0)) * 1.4, 0.17, 0.11, 'marble', seg=8)


def balustrade(mb, a, b, lo, hi):
    """White stone balustrade on a retaining wall (garden terraces)."""
    seg_box(mb, a, b, -0.3, 0.3, lo - 1.0, hi, 'plaster')
    seg_box(mb, a, b, -0.32, 0.32, hi, hi + 0.18, 'marble')
    L = (b - a).length
    d = (b - a).normalized()
    for k in range(int(L / 0.28)):
        m = a + d * (0.14 + k * 0.28)
        seg_box(mb, m - d * 0.06, m + d * 0.06, -0.07, 0.07, hi + 0.18, hi + 0.82, 'marble')
    seg_box(mb, a, b, -0.06, 0.06, hi + 0.18, hi + 0.82, 'invisible')
    seg_box(mb, a, b, -0.2, 0.2, hi + 0.82, hi + 0.97, 'marble')


def dist_seg(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / (ab.length_squared + 1e-12)))
    return (a + ab * t - p).length


def build_steps(mb, T, pts, wdt):
    """Stone flight along an OSM highway=steps line, risers <= 0.17 m, with cheek walls."""
    total = sum((b - a).length for a, b in zip(pts, pts[1:]))
    if total < 0.8:
        return
    z_a, z_b = T.h(*pts[0]), T.h(*pts[-1])
    dz = z_b - z_a
    n = max(2, int(math.ceil(abs(dz) / 0.17)))
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        L = (b - a).length
        if L < 1e-3:
            continue
        d = (b - a) / L
        k0 = int(acc / total * n)
        k1 = int((acc + L) / total * n)
        for k in range(k0, max(k1, k0 + 1)):
            t0 = max(0.0, k / n * total - acc)
            t1 = min(L, (k + 1) / n * total - acc)
            if t1 - t0 < 0.05:
                continue
            ztop = z_a + dz * ((k + 1) / n if dz > 0 else k / n)
            seg_box(mb, a + d * t0, a + d * t1, -wdt / 2, wdt / 2, min(z_a, z_b) - 1.2, ztop + 0.03, 'stone', top='stone')
        acc += L
    # low cheek walls
    for a, b in zip(pts, pts[1:]):
        za, zb = T.h(*a), T.h(*b)
        for sgn in (-1, 1):
            d = (b - a).normalized()
            nn = Vector((-d.y, d.x))
            sloped_prism(mb, a + nn * sgn * (wdt / 2 + 0.15), b + nn * sgn * (wdt / 2 + 0.15), za, zb, -0.15, 0.15, -1.0, 0.75, 'rubble')


def min_width(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    # oriented: use area / longest edge
    area = abs(poly_area(pts))
    longest = max((Vector(pts[i]) - Vector(pts[i - 1])).length for i in range(len(pts)))
    return max(3.0, min(area / max(longest, 1e-3), max(xs) - min(xs), max(ys) - min(ys)))


def facade_walls(mb, pts, z0, z1, mat, ground, others=(), floor_h=3.3, win=(1.1, 1.6, 0.9), spacing=3.2,
                 joinery=None, simple_join=None, arched=False, ground_fn=None):
    """Extruded walls with recessed window grid (geometry, so it reads in any engine).
    joinery: MB for full casement units (used on the few representative buildings)."""
    ww, wh, wsill = win
    n = len(pts)
    for i in range(n):
        a, b = Vector(pts[i]), Vector(pts[(i + 1) % n])
        L = (b - a).length
        ops = []
        dd_ = (b - a).normalized() if L > 0 else Vector((1, 0))
        probe = (a + b) / 2 + Vector((dd_.y, -dd_.x)) * 1.2     # just outside this facade
        party = any(point_in_poly(probe.x, probe.y, o) for o in others)
        # on a slope each façade starts its window grid at its own (uphill) ground, so no window row is buried
        g_edge = max(ground, ground_fn(a.x, a.y), ground_fn(b.x, b.y)) if ground_fn else ground
        if L > 3.0 and z1 - g_edge > 3 and not party:
            nax = max(1, int(L / spacing))
            sp = L / nax
            fl = max(1, int((z1 - g_edge - 0.6) / floor_h))
            for f in range(fl):
                zz = g_edge + wsill + f * floor_h
                for k in range(nax):
                    u = sp * (k + 0.5)
                    ops.append((u - ww / 2, u + ww / 2, zz, zz + wh))
        # walls go CCW, building interior to the left -> thickness to the left
        wall(mb, a, b, z0, z1, 0.5, mat, ops, mat_in=mat)
        d = (b - a).normalized() if L > 0 else Vector((1, 0))
        nn = Vector((-d.y, d.x))
        for o in ops:
            p, q = a + d * o[0], a + d * o[1]
            if joinery is not None:
                window_unit(joinery, p, q, o[2], o[3], nn, 0.22)
            elif simple_join is not None:
                window_simple(simple_join, p, q, o[2], o[3], nn, 0.2)
            else:
                pane(mb, p + nn * 0.25, q + nn * 0.25, o[2], o[3])
            # the town blocks are hollow shells: behind the glass a dark room, not fragments of the far walls,
            # roof and floor slab (Codex V5: nicholas_03L)
            pb, qb = p - d * 0.25 + nn * 0.75, q + d * 0.25 + nn * 0.75
            bq = [Vector((pb.x, pb.y, o[2] - 0.3)), Vector((qb.x, qb.y, o[2] - 0.3)), Vector((qb.x, qb.y, o[3] + 0.3)), Vector((pb.x, pb.y, o[3] + 0.3))]
            mb.poly(bq, 'room_dark')
            mb.poly(list(reversed(bq)), 'room_dark')
            seg_box(mb, p - d * 0.12, q + d * 0.12, -0.12, 0.2, o[2] - 0.1, o[2], 'stone')      # sill
            if arched:
                arch_head(mb, p, q, o[3], 0.0, 0.5, mat)
                seg_box(mb, p - d * 0.15, p, -0.06, 0.02, o[2], o[3] - (q - p).length / 2, 'frame')
                seg_box(mb, q, q + d * 0.15, -0.06, 0.02, o[2], o[3] - (q - p).length / 2, 'frame')
        seg_box(mb, a, b, -0.25, 0.02, z1 - 0.35, z1, 'frame')
    slab(mb, [pts], z1 - 0.02, 0.3, 'plaster_int', 'plaster_int', 'plaster_int')


def seg_box_ring(mb, pts, z0, z1, t, mat):
    n = len(pts)
    for i in range(n):
        seg_box(mb, pts[i], pts[(i + 1) % n], -0.02, t, z0, z1, mat)


def roof_distfield(mb, pts, z, h, mat, pitch=42.0, cell=0.5, overhang=0.45):
    """Hip roof over an arbitrary outline: height grows with the distance to the nearest wall
    (the straight-skeleton roof), capped at h -> each wing of a U/L-shaped block gets its own ridge."""
    import numpy as np
    P = np.array([(p[0], p[1]) for p in pts], dtype=np.float64)
    x0, y0 = P.min(0) - overhang - cell
    x1, y1 = P.max(0) + overhang + cell
    nx, ny = int((x1 - x0) / cell) + 1, int((y1 - y0) / cell) + 1
    XX, YY = np.meshgrid(x0 + np.arange(nx + 1) * cell, y0 + np.arange(ny + 1) * cell)
    dmin = np.full(XX.shape, 1e9)
    for i in range(len(P)):
        ax, ay = P[i]
        bx, by = P[(i + 1) % len(P)]
        dx, dy = bx - ax, by - ay
        t = np.clip(((XX - ax) * dx + (YY - ay) * dy) / (dx * dx + dy * dy + 1e-12), 0, 1)
        dmin = np.minimum(dmin, np.hypot(XX - ax - t * dx, YY - ay - t * dy))
    sd = np.where(_pip_mask(XX, YY, [tuple(p) for p in P]), dmin, -dmin)
    k = math.tan(math.radians(pitch))
    Z = z + np.clip(sd, -overhang, h / k) * k
    ctr = (sd[:-1, :-1] + sd[1:, :-1] + sd[:-1, 1:] + sd[1:, 1:]) / 4
    for j, i in zip(*np.nonzero(ctr > -overhang)):
        q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
        mb.poly([Vector((XX[b_, a_], YY[b_, a_], Z[b_, a_])) for a_, b_ in q], mat)


def roof_generic(mb, pts, z, h, shape, mat='roof'):
    if h <= 0.05 or shape == 'flat':
        slab(mb, [pts], z + 0.15, 0.2, 'gravel', 'plaster_int', 'frame')
        return
    if shape != 'pyramidal' and len(pts) > 12:      # complex (often concave) outline: hip roof per wing
        roof_distfield(mb, pts, z, h, mat)
        return
    if shape == 'pyramidal' or len(pts) > 12:
        c = Vector((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), z + h))
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            mb.poly([Vector((a[0], a[1], z)), Vector((b[0], b[1], z)), c], mat)
        return
    # hipped / gabled / mansard: inset the outline and lift it (straight-skeleton-lite)
    inset = min(h / 1.1, 0.45 * min_width(pts))
    try:
        inn = offset_poly(pts, -inset)
    except ZeroDivisionError:
        inn = None
    if not inn or poly_area([tuple(v) for v in inn]) <= 0.5 or any((Vector(inn[i]) - Vector(pts[i])).length > 3 * inset for i in range(len(pts))):
        c = Vector((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), z + h))
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            mb.poly([Vector((a[0], a[1], z)), Vector((b[0], b[1], z)), c], mat)
        return
    zt = z + h
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        c, d = inn[(i + 1) % len(pts)], inn[i]
        mb.poly([Vector((a[0], a[1], z)), Vector((b[0], b[1], z)), Vector((c.x, c.y, zt)), Vector((d.x, d.y, zt))], mat)
    slab(mb, [[(v.x, v.y) for v in inn]], zt, 0.01, 'roof', 'roof', mat)


# ---------------------------------------------------------------- vegetation from orthophoto
def load_ortho_px():
    img = bpy.data.images.load(os.path.join(DATA, 'ortho4k.jpg'), check_existing=True)
    w, h = img.size
    import numpy as np
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)[..., :3], w, h      # row 0 = south (Blender)


_SURF = {}
WALK_SURF = ('Fort_Paths', 'V2City_StreetsWalk', 'Steps')     # finished walking surfaces of the V2 modules / V1 steps
TRUNKS = []                                                     # trunk positions placed by build_vegetation


def surface_bvh(prefixes):
    """BVH over the already built meshes whose names start with prefixes (world space), so later layers can sit
    on / avoid what the V2 modules paved instead of guessing from the terrain."""
    key = tuple(prefixes)
    if key not in _SURF:
        from mathutils.bvhtree import BVHTree
        verts, polys = [], []
        for o in bpy.data.objects:
            if o.type != 'MESH' or not o.name.startswith(key):
                continue
            mw = o.matrix_world
            b0 = len(verts)
            verts += [mw @ v.co for v in o.data.vertices]
            polys += [[b0 + i for i in p.vertices] for p in o.data.polygons]
        _SURF[key] = BVHTree.FromPolygons(verts, polys) if polys else None
    return _SURF[key]


def surface_z(bvh, x, y, z_ref, up=1.0, down=0.6):
    """Top of bvh at (x, y) within [z_ref - down, z_ref + up], or None."""
    if bvh is None:
        return None
    hit = bvh.ray_cast(Vector((x, y, z_ref + up)), Vector((0, 0, -1)), up + down)
    return hit[0].z if hit[0] is not None else None


def build_vegetation(T, feats, coll, points=()):
    import numpy as np
    px, w, h = load_ortho_px()
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    lum = (r + g + b) / 3
    green = (g > r * 1.04) & (g > b * 1.08) & (lum < 0.42)
    canopy = (g > r * 1.02) & (lum < 0.30)          # crowns are darker than sunlit lawn
    garden = next((f for f in feats if f['tags'].get('name') == 'Baroková záhrada'), None)
    bpolys = [f['pts'] for f in feats if f['kind'] in ('building', 'part')]
    # mapped lawns are open grass (Google Earth / photo 09): their dark-green orthophoto pixels are lawn, not canopy;
    # only OSM-mapped trees stand on them
    lawns = [(f['pts'], min(p[0] for p in f['pts']), max(p[0] for p in f['pts']), min(p[1] for p in f['pts']), max(p[1] for p in f['pts']))
             for f in feats if f['kind'] == 'area' and f['tags'].get('landuse') in ('grass', 'flowerbed')]

    gpts_ = (garden['pts'] if poly_area(garden['pts']) > 0 else list(reversed(garden['pts']))) if garden else None
    garden_zone = offset_poly(gpts_, 14.0) if garden else None

    def on_lawn(x, y):          # only the lawns on the castle terraces; the slopes below the walls are wooded (Earth)
        if dist_to_poly(x, y, OUTER) > 90.0:
            return False
        return any(x0 <= x <= x1 and y0 <= y <= y1 and point_in_poly(x, y, q) for q, x0, x1, y0, y1 in lawns)

    def pix(x, y):
        u, v = T.uv(x, y)
        return int(min(w - 1, max(0, u * w))), int(min(h - 1, max(0, v * h)))

    def in_building(x, y):
        for p in bpolys:
            xs = [q[0] for q in p]
            ys = [q[1] for q in p]
            if min(xs) - 1 <= x <= max(xs) + 1 and min(ys) - 1 <= y <= max(ys) + 1 and point_in_poly(x, y, p):
                return True
        return point_in_poly(x, y, offset_poly(OUTER, 3))

    # --- hedges of the Baroque parterre (hornbeam), from dark-green ortho pixels
    hmb = MB('Hedges-col')
    if garden and False:     # superseded by build_garden()
        gp = garden['pts']
        xs = [q[0] for q in gp]
        ys = [q[1] for q in gp]
        cell = 0.4
        bed = (g > r * 1.03) & (g > b * 1.05)
        y = min(ys)
        while y < max(ys):
            x = min(xs)
            run = None
            while x < max(xs) + cell:
                inside = point_in_poly(x, y, gp)
                i, j = pix(x, y)
                if inside:
                    here = bed[j, i]
                    nb = bed[max(0, j - 2):j + 3, max(0, i - 2):i + 3]
                    win = bool(here) and not nb.all()        # bed boundary -> box hedge border
                else:
                    win = False
                if win and run is None:
                    run = x
                if (not win) and run is not None:
                    z = T.h((run + x) / 2, y)
                    hmb.box([(run, y), (x, y), (x, y + cell), (run, y + cell)], z - 0.3, z + 0.45, 'hedge')
                    run = None
                x += cell
            y += cell
    out = [hmb.build(coll)]

    # --- trees: sample dark-green canopy on a jittered grid outside buildings
    tmb = ChunkMB('Trees_Foliage')
    trunk = ChunkMB('Trees_Trunks-col')
    branches = ChunkMB('Trees_Branches')
    step = 12.0 if FAST else (10.0 if WEB else 7.0)
    n = 0
    # walkers' lines: no orthophoto tree may stand on a mapped footway / steps / path
    walk_lines = [[Vector(q[:2]) for q in f['pts']] for f in feats if f['kind'] == 'road'
                  and f['tags'].get('highway') in ('footway', 'steps', 'path', 'pedestrian', 'service', 'living_street')]
    walk_grid = {}
    for wl in walk_lines:
        for a_, b_ in zip(wl, wl[1:]):
            for k in range(int((b_ - a_).length / 2.0) + 1):
                q = a_.lerp(b_, k / max(1, int((b_ - a_).length / 2.0)))
                walk_grid.setdefault((int(q.x // 4), int(q.y // 4)), []).append((a_, b_))

    def on_walk(x, y, r=2.2):
        # path half-width + trunk radius can straddle a 4 m cell, so look at the neighbours too
        cx, cy = int(x // 4), int(y // 4)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for a_, b_ in walk_grid.get((cx + dx, cy + dy), ()):
                    if dist_seg(Vector((x, y)), a_, b_) < r:
                        return True
        return False
    plazas = [(f['pts'], min(p[0] for p in f['pts']), max(p[0] for p in f['pts']), min(p[1] for p in f['pts']), max(p[1] for p in f['pts']))
              for f in feats if f['kind'] == 'road' and f['tags'].get('area') == 'yes']
    benches = [Vector((p['x'], p['y'])) for p in points if p['kind'] == 'bench']
    ribbons = surface_bvh(('Fort_Paths',))
    walks = surface_bvh(WALK_SURF)

    def on_paving(x, y, bvh, r=0.8):     # trunk circle touches an already paved path / street (Codex V5: vienna_05L)
        z0 = T.h(x, y)
        return any(surface_z(bvh, x + dx, y + dy, z0, up=1.5, down=1.0) is not None
                   for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r)))

    def blocked(x, y, osm):
        if any((bq - Vector((x, y))).length < 1.6 for bq in benches if abs(bq.x - x) < 2):
            return True
        if on_paving(x, y, ribbons):
            return True
        # orthophoto canopy trees never stand on paving or plazas; mapped street trees may stand in city pavements
        return not osm and (on_paving(x, y, walks, 0.5) or
                            any(x0 <= x <= x1 and y0 <= y <= y1 and point_in_poly(x, y, q) for q, x0, x1, y0, y1 in plazas))
    osm_trees = [Vector((p['x'], p['y'])) for p in points if p['kind'] == 'tree']
    # mapped trees standing on a walked path/steps (OSM point slightly off) are dropped from the pedestrian corridor
    n_osm0 = len(osm_trees)
    osm_trees = [c for c in osm_trees if (garden and point_in_poly(c.x, c.y, garden['pts'])) or
                 not (on_walk(c.x, c.y, 2.6) or blocked(c.x, c.y, True))]
    TRUNKS[:] = []
    n_blk = []
    # own generator: the shared one is consumed by the V2 modules, so any change there reshuffled the whole
    # canopy (tree count 942 -> 1115 between two builds with identical vegetation rules)
    vrng, hrng = random.Random(1773), random.Random(1774)     # jitter / heights
    for c in osm_trees:
        in_garden = garden and point_in_poly(c.x, c.y, garden['pts'])
        tree(tmb, trunk, c, T.h(c.x, c.y), hrng.uniform(9, 15), topiary=bool(in_garden), branches=branches)
        TRUNKS.append(c)
        n += 1
    y = T.y0 + 5
    while y < T.y1 - 5:
        x = T.x0 + 5
        while x < T.x1 - 5:
            jx, jy = x + vrng.uniform(-2.5, 2.5), y + vrng.uniform(-2.5, 2.5)
            if math.hypot(jx, jy) < 320:
                i, j = pix(jx, jy)
                patch = green[max(0, j - 6):j + 7, max(0, i - 6):i + 7]
                # the lawns hugging the palace (E/N, photo 09) are open; shaded grass there reads as canopy
                if patch.size and patch.mean() > 0.6 and not in_building(jx, jy) and not point_in_poly(jx, jy, HONOUR_COURT) and \
                        dist_to_poly(jx, jy, OUTER) > 22.0 and \
                        not (garden and point_in_poly(jx, jy, garden_zone)) and \
                        (not on_lawn(jx, jy) or canopy[max(0, j - 6):j + 7, max(0, i - 6):i + 7].mean() > 0.5) and \
                        not on_walk(jx, jy) and \
                        all((c - Vector((jx, jy))).length > 5.0 for c in osm_trees if abs(c.x - jx) < 6) and \
                        not (blocked(jx, jy, False) and n_blk.append(1) is None):
                    in_garden = garden and point_in_poly(jx, jy, garden['pts'])
                    if in_garden:
                        x += step
                        continue    # garden trees come from OSM (clipped lindens in rows)
                    tree(tmb, trunk, Vector((jx, jy)), T.h(jx, jy), hrng.uniform(8, 16), branches=branches)
                    TRUNKS.append(Vector((jx, jy)))
                    n += 1
            x += step
        y += step
    print('trees', n, 'mapped', len(osm_trees), 'of', n_osm0, '| canopy rejected on paving/bench', len(n_blk))
    out += tmb.build(coll) + trunk.build(coll) + branches.build(coll)
    return out


def _prism(mb, a, b, ra, rb, mat, seg=6):
    """Tapered 6-sided branch/trunk from 3D point a to b."""
    d = (b - a)
    if d.length < 1e-4:
        return
    d.normalize()
    up = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((1, 0, 0))
    u = d.cross(up).normalized()
    v = d.cross(u)
    ring = lambda c, r: [c + (u * math.cos(2 * math.pi * k / seg) + v * math.sin(2 * math.pi * k / seg)) * r for k in range(seg)]
    A, B = ring(a, ra), ring(b, rb)
    for k in range(seg):
        j = (k + 1) % seg
        mb.poly([A[k], A[j], B[j], B[k]], mat, uv_scale=1.0)


def _leaf_cluster(mb, c, size, mat, rng):
    """Three crossed leaf cards around c (random orientation) - reads as foliage from any side."""
    for k in range(3):
        a = rng.uniform(0, math.pi)
        tilt = rng.uniform(-0.6, 0.6)
        u = Vector((math.cos(a), math.sin(a), 0))
        v = Vector((-math.sin(a) * math.sin(tilt), math.cos(a) * math.sin(tilt), math.cos(tilt)))
        if k == 2:
            u = Vector((math.cos(a), math.sin(a), rng.uniform(-0.5, 0.5))).normalized()
        hs = size / 2
        q = [c - u * hs - v * hs, c + u * hs - v * hs, c + u * hs + v * hs, c - u * hs + v * hs]
        mb.poly(q, mat, uv=[(0, 0), (1, 0), (1, 1), (0, 1)])


TREE_RNG = random.Random(99)


def tree(fol, trk, c, z, h, topiary=False, branches=None):
    rng = TREE_RNG
    if not topiary:
        br = branches if branches is not None else trk
        tone = rng.choice(('leaves', 'leaves', 'leaves_dark', 'leaves_light'))
        r0 = 0.14 + h * 0.016
        ht = h * rng.uniform(0.32, 0.42)
        base = Vector((c.x, c.y, z - 0.4))
        top = Vector((c.x + rng.uniform(-0.3, 0.3), c.y + rng.uniform(-0.3, 0.3), z + ht))
        _prism(trk, base, top, r0, r0 * 0.75, 'bark', seg=12)
        shape = rng.choice(('round', 'round', 'broad', 'tall'))
        crown_c = Vector((top.x, top.y, z + h * (0.62 if shape != 'tall' else 0.66)))
        R = h * {'round': rng.uniform(0.27, 0.34), 'broad': rng.uniform(0.34, 0.42), 'tall': rng.uniform(0.18, 0.23)}[shape]
        zs_ = {'round': 1.0, 'broad': 0.7, 'tall': 1.8}[shape]
        tips = []

        def in_crown(p):         # branch tips stay inside the crown ellipsoid: leaf clumps on tips that overshot
            q = p - crown_c      # it floated above / beside the crown (Codex V5: nicholas_01B, vienna_01)
            s = math.sqrt((q.x / R) ** 2 + (q.y / R) ** 2 + (q.z / (R * zs_)) ** 2)
            return crown_c + q * (0.9 / s) if s > 0.9 else p
        for k in range(rng.randint(5, 7)):
            az = rng.uniform(0, 2 * math.pi)
            el = rng.uniform(0.45, 1.05)
            L = h * rng.uniform(0.32, 0.45)
            s0 = top + Vector((0, 0, rng.uniform(-0.6, 0.4)))
            dvec = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
            e = in_crown(s0 + dvec * L)
            _prism(br, s0, e, r0 * 0.5, 0.04, 'bark', seg=5)
            tips.append(e)
            for j in range(1 if WEB else 2):      # secondary branches
                m = s0.lerp(e, rng.uniform(0.45, 0.7))
                az2 = az + rng.uniform(-0.9, 0.9)
                d2 = Vector((math.cos(az2) * 0.7, math.sin(az2) * 0.7, rng.uniform(0.2, 0.8))).normalized()
                e2 = in_crown(m + d2 * L * rng.uniform(0.35, 0.5))
                _prism(br, m, e2, r0 * 0.22, 0.02, 'bark', seg=4)
                tips.append(e2)
        for t in tips:
            _leaf_cluster(fol, t, R * rng.uniform(0.5, 0.7), tone, rng)
        for k in range(10 if WEB else 22):      # fill the crown volume
            a = rng.uniform(0, 2 * math.pi)
            rr = R * math.sqrt(rng.random()) * 0.85
            p = crown_c + Vector((math.cos(a) * rr, math.sin(a) * rr, rng.uniform(-0.55, 0.55) * R * zs_))
            _leaf_cluster(fol, p, R * rng.uniform(0.45, 0.65), tone, rng)
        return
    _tree_topiary(fol, trk, c, z, rng)


def _tree_topiary(fol, trk, c, z, rng):
    """Clipped silver linden of the Baroque garden: straight stem, dense round crown ~2.6 m across (Earth/ref 27)."""
    _prism(trk, Vector((c.x, c.y, z - 0.3)), Vector((c.x, c.y, z + 2.4)), 0.09, 0.07, 'bark', seg=10)
    cc = Vector((c.x, c.y, z + 3.35))
    for k in range(3):       # short forks into the clipped crown
        a = 2 * math.pi * k / 3 + rng.uniform(0, 1)
        _prism(trk, Vector((c.x, c.y, z + 2.3)), cc + Vector((math.cos(a) * 0.5, math.sin(a) * 0.5, 0.1)), 0.05, 0.025, 'bark', seg=6)
    icosphere(fol, cc, 0.78, 'foliage_dark', smooth=True, subdiv=2)
    for k in range(6 if WEB else 26):      # inner layer hides the core
        u, v = rng.uniform(-1, 1), rng.uniform(0, 2 * math.pi)
        dvec = Vector((math.sqrt(1 - u * u) * math.cos(v), math.sqrt(1 - u * u) * math.sin(v), u))
        _leaf_cluster(fol, cc + dvec * rng.uniform(0.5, 0.7), 0.42, 'leaves_dense', rng)
    for k in range(18 if WEB else 80):      # dense small leaf cards hide the core: a compact clipped ball (ref 27)
        u, v = rng.uniform(-1, 1), rng.uniform(0, 2 * math.pi)
        dvec = Vector((math.sqrt(1 - u * u) * math.cos(v), math.sqrt(1 - u * u) * math.sin(v), u))
        _leaf_cluster(fol, cc + dvec * rng.uniform(0.8, 0.92), 0.26, 'leaves_dense', rng)


_ICO = None


def _subdivide(vs, fs):
    vs = list(vs)
    cache = {}

    def mid(i, j):
        k = (min(i, j), max(i, j))
        if k not in cache:
            vs.append((vs[i] + vs[j]).normalized())
            cache[k] = len(vs) - 1
        return cache[k]
    out = []
    for a, b, c in fs:
        ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
        out += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
    return vs, out


def icosphere(mb, c, r, mat, smooth=False, subdiv=0):
    global _ICO
    if _ICO is None:
        t = (1 + 5 ** 0.5) / 2
        v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
             (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
        f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
             (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
             (8, 6, 7), (9, 8, 1)]
        _ICO = ([Vector(p).normalized() for p in v], f)
    vs, fs = _ICO
    for _ in range(subdiv):
        vs, fs = _subdivide(vs, fs)
    sq = Vector((random.uniform(0.85, 1.15), random.uniform(0.85, 1.15), random.uniform(0.7, 0.95)))
    jit = [vs[i] * r * ((0.97 + 0.06 * random.random()) if smooth else (0.85 + 0.3 * random.random())) for i in range(len(vs))]
    pv = [Vector((c.x + p.x * sq.x, c.y + p.y * sq.y, c.z + p.z * sq.z)) for p in jit]
    for tri in fs:
        mb.poly([pv[i] for i in tri], mat, uv_scale=2.5)


def build_ground_detail(T, feats, coll):
    """Walk-level surfaces inside the castle grounds: paving / gravel / lawn classified from the
    orthophoto, draped 3 cm over the terrain (the blurry ortho stays only for the distance)."""
    import numpy as np
    px, w, h = load_ortho_px()
    area = next((f['pts'] for f in feats if f['tags'].get('name') == 'Bratislavský hrad'), None)
    if not area:
        return []
    area = offset_poly(area, 25.0)      # include the approaches just outside the castle grounds
    bpolys = [f['pts'] for f in feats if f['kind'] in ('building', 'part') and f['tags'].get('location') != 'underground'
              and f['tags'].get('parking') != 'underground' and f['tags'].get('building') not in ('roof', 'carport')]
    fp_json = os.path.join(DATA, 'ref', 'fortress', 'flight_footprints.json')
    # v2_fortress flights carry their own treads: no draped paving over them, only a lawn underlay (terrain is carved
    # below the treads) so the bank beside a flight's edge is not a hole into the coarse terrain
    flights = json.load(open(fp_json)) if os.path.exists(fp_json) else []
    garden_poly = next((f['pts'] for f in feats if f['tags'].get('name') == 'Baroková záhrada'), None)
    grass_polys = [(f['pts'], (min(p[0] for p in f['pts']), max(p[0] for p in f['pts']), min(p[1] for p in f['pts']), max(p[1] for p in f['pts'])))
                   for f in feats if f['kind'] == 'area' and (f['tags'].get('landuse') == 'grass' or f['tags'].get('landuse') == 'flowerbed')]
    mb = ChunkMB('Ground_Detail-col', tile=60.0)
    xs = [p[0] for p in area]
    ys = [p[1] for p in area]
    cell = 3.0 if FAST else (1.5 if WEB else 0.75)
    mats = {0: 'cobbles', 1: 'gravel', 2: 'grass', 3: 'gravel_white', 4: 'grass'}
    gx0_, gy0_ = min(xs), min(ys)
    NX, NY = int((max(xs) - gx0_) / cell) + 1, int((max(ys) - gy0_) / cell) + 1
    C = np.full((NY, NX), -1, dtype=np.int8)
    cut_ = np.zeros((NY, NX), dtype=bool)
    ramps_ = surface_bvh(('Fort_Ramps',))
    vsteps_ = surface_bvh(('Steps',))      # V1 flights sunk into a cut (S terrace steps 37409855, castle hunt c28)
    floors_ = surface_bvh(('Fort_Buildings', 'Fort_Gates', 'Fort_Walls'))
    near = {}
    for j in range(NY):
        for i in range(NX):
            cx, cy = gx0_ + (i + 0.5) * cell, gy0_ + (j + 0.5) * cell
            if not point_in_poly(cx, cy, area) or point_in_poly(cx, cy, offset_poly(OUTER, 0.5)):
                continue
            key = (int(cx // 60), int(cy // 60))
            if key not in near:
                near[key] = [q for q in bpolys if abs(q[0][0] - cx) < 90 and abs(q[0][1] - cy) < 90]
            if any(point_in_poly(cx, cy, q) for q in near[key]):
                continue
            if any(point_in_poly(cx, cy, q) for q in flights):
                cut_[j, i] = True    # flights carry their own treads; nothing draped over or beside them (walktest)
                continue
            th_ = T.h(cx, cy)
            on_floor_ = False
            for ox_, oy_ in ((0, 0), (cell, 0), (-cell, 0), (0, cell), (0, -cell)):
                hf_ = floors_.ray_cast(Vector((cx + ox_, cy + oy_, th_ + 0.6)), Vector((0, 0, -1)), 1.6) if floors_ else (None,)
                on_floor_ |= hf_[0] is not None and hf_[1].z > 0.7
            if on_floor_:
                continue     # a fortress court / terrace floor is the ground here (riding-school court: this layer
                             # lay 0.3 m above it as a jagged cobble band, castle hunt c53)
            zr_ = surface_z(ramps_, cx, cy, T.h(cx, cy), up=0.5, down=3.0)
            zv_ = surface_z(vsteps_, cx, cy, T.h(cx, cy), up=0.3, down=3.0)
            if (zr_ is not None and zr_ < T.h(cx, cy) - 0.05) or (zv_ is not None and zv_ < T.h(cx, cy) - 0.25):
                cut_[j, i] = True    # a flight's walking surface lies below the terrain here: carved, keep it open
                continue
            u, v = T.uv(cx, cy)
            pi_, pj_ = int(u * w), int(v * h)
            patch = px[max(0, pj_ - 3):pj_ + 4, max(0, pi_ - 3):pi_ + 4].reshape(-1, 3).mean(0)
            r, g, b = patch
            sat = max(patch) - min(patch)
            if garden_poly and point_in_poly(cx, cy, garden_poly):
                C[j, i] = 3
            elif any(gb_[0] <= cx <= gb_[1] and gb_[2] <= cy <= gb_[3] and point_in_poly(cx, cy, gq) for gq, gb_ in grass_polys):
                C[j, i] = 1      # under an OSM lawn: gravel bed; the lawn itself is draped from the polygon below
            elif sat < 0.06:
                C[j, i] = 0
            elif r > b * 1.08:
                C[j, i] = 1
            else:
                C[j, i] = 0
    grown_ = cut_ | np.roll(cut_, 1, 0) | np.roll(cut_, -1, 0) | np.roll(cut_, 1, 1) | np.roll(cut_, -1, 1)
    C[grown_] = -1           # also the cells whose corners would slope over the cut edge (Ground_Detail above stairs)
    # paving only where OSM maps a way / plaza (or the palace apron and Honour Court): shaded slopes under the
    # trees read as grey in the orthophoto but are lawn and woodland floor (photos 15, 16, 18)
    GX, GY = np.meshgrid(gx0_ + (np.arange(NX) + 0.5) * cell, gy0_ + (np.arange(NY) + 0.5) * cell)
    paved = np.zeros((NY, NX), dtype=bool)
    plaza = np.zeros((NY, NX), dtype=bool)       # mapped paved areas (not just buffered way lines)
    rw_mask = np.zeros((NY, NX), dtype=bool)     # buffers of ways v2_fortress already draws as kerbed ribbons
    street_m = np.zeros((NY, NX), dtype=bool)    # every mapped way (not steps) + 0.5 m: always paved
    ribbons = surface_bvh(('Fort_Paths',))

    def ribboned(f):
        pl = [Vector(q[:2]) for q in f['pts']]
        L = sum((b - a).length for a, b in zip(pl, pl[1:]))
        if ribbons is None or L < 1.0:
            return False
        hits = 0
        for frac in (0.25, 0.5, 0.75):
            tgt, acc = frac * L, 0.0
            for a, b in zip(pl, pl[1:]):
                sl = (b - a).length
                if acc + sl >= tgt:
                    q = a.lerp(b, (tgt - acc) / max(sl, 1e-9))
                    hits += surface_z(ribbons, q.x, q.y, T.h(q.x, q.y), up=1.5, down=1.5) is not None
                    break
                acc += sl
        return hits >= 2
    for f in feats:
        if f['kind'] != 'road':
            continue
        t = f['tags']
        hw = t.get('highway')
        if f.get('closed') and t.get('area') == 'yes':
            plaza |= _pip_mask(GX, GY, f['pts'])
            continue
        # same half-widths as v2_fortress.ground_paths (+ its 0.15 m kerb) so paving and kerbs share one footprint
        try:
            half = float(str(t.get('width', '')).split()[0]) / 2 + 0.15
        except (ValueError, IndexError):
            half = {'steps': 1.4, 'footway': 1.15, 'path': 0.75, 'pedestrian': 1.95, 'service': 1.95,
                    'living_street': 2.4, 'track': 1.4}.get(hw, 3.5)
        m_way = np.zeros((NY, NX), dtype=bool)
        for (ax_, ay_), (bx_, by_) in zip(f['pts'], f['pts'][1:]):
            dx_, dy_ = bx_ - ax_, by_ - ay_
            L2 = dx_ * dx_ + dy_ * dy_ + 1e-9
            tt = np.clip(((GX - ax_) * dx_ + (GY - ay_) * dy_) / L2, 0, 1)
            d2_ = (GX - ax_ - tt * dx_) ** 2 + (GY - ay_ - tt * dy_) ** 2
            m_way |= d2_ < half ** 2
            if hw != 'steps':
                street_m |= d2_ < (half + 0.5) ** 2
        if hw != 'steps' and ribboned(f):     # V1 flights keep their paved bed (treads alone floated on lawn)
            rw_mask |= m_way
        else:
            paved |= m_way
    rw_mask &= ~paved
    paved |= rw_mask
    plaza |= _pip_mask(GX, GY, HONOUR_COURT) | _pip_mask(GX, GY, offset_poly(OUTER, 14.0))
    paved |= plaza
    C[(C == 0) & ~paved] = 2
    C[(C == 1) & ~paved] = 2
    C[(C == 2) & paved] = 0        # no orthophoto grass confetti on mapped plazas/paths; real lawns are the OSM polygons
    # majority filter (3x3) removes isolated cells and single-cell fingers
    Cs = C.copy()
    for j in range(1, NY - 1):
        for i in range(1, NX - 1):
            if C[j, i] < 0 or C[j, i] == 4:
                continue
            blk = C[j - 1:j + 2, i - 1:i + 2].ravel()
            blk = blk[(blk >= 0) & (blk != 4)]
            if not len(blk):
                continue
            vals, cnt = np.unique(blk, return_counts=True)
            if cnt.max() >= 6:
                Cs[j, i] = vals[cnt.argmax()]
    C = Cs
    # The fortress path ribbons (v2_fortress.ground_paths, kerbed, +7 cm) are the real paths. Coarse cells of this
    # layer beside them stuck out past the kerbs as cobble teeth, and lawn slivers were left between a ribbon and
    # a paved landing (Codex V5: nicholas_01L, nicholas_06L). Under a ribbon: lawn (paving on mapped plazas);
    # just outside its kerb: lawn unless a plaza is mapped there; small lawn scraps boxed in by paving: paving.
    if ribbons is not None:
        R = np.zeros((NY, NX), dtype=bool)
        for j, i in zip(*np.nonzero(C >= 0)):
            cx, cy = gx0_ + (i + 0.5) * cell, gy0_ + (j + 0.5) * cell
            R[j, i] = surface_z(ribbons, cx, cy, T.h(cx, cy), up=1.5, down=1.5) is not None
        lawn_m = np.zeros((NY, NX), dtype=bool)
        for gq, gb_ in grass_polys:
            lawn_m |= _pip_mask(GX, GY, gq)
        # paving of a path the fortress draws itself: only its ribbon stays (no teeth past the kerbs)
        C[((C == 0) | (C == 1)) & rw_mask & ~R & ~plaza] = 2

        def grow(m, k):
            for _ in range(k):
                m = m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
            return m
        hard = (C == 0) | (C == 1) | R
        closed = ~grow(~grow(hard, 2), 2)          # gaps up to ~3 m between paved surfaces
        C[closed & (C == 2) & ~R & ~lawn_m] = 0
        C[R & (C >= 0) & ~plaza & (C != 3) & (C != 4)] = 2
        C[R & (C >= 0) & plaza & (C != 3) & (C != 4)] = 0
        print('ground detail: ribbon cells', int(R.sum()), 'ribbon-way cells', int(rw_mask.sum()))

    # a mapped street is never lawn: the city leaves its own street paving out where this layer lies, so lawn here
    # turned Beblavého into grass from wall to wall (final V5 build); flight footprints stay open (C < 0)
    C[(C >= 0) & (C != 3) & (C != 4) & street_m] = 0
    def corner(i, j):        # class at lattice corner (i, j): majority of the up-to-4 adjacent cells
        blk = C[max(0, j - 1):j + 1, max(0, i - 1):i + 1].ravel()
        blk = blk[blk >= 0]
        if not len(blk):
            return -1
        vals, cnt = np.unique(blk, return_counts=True)
        return vals[cnt.argmax()]
    CC = np.array([[corner(i, j) for i in range(NX + 1)] for j in range(NY + 1)], dtype=np.int8)
    zc = {}

    def P(i, j):
        k = (i, j)
        if k not in zc:
            x_, y_ = gx0_ + i * cell, gy0_ + j * cell
            zc[k] = Vector((x_, y_, T.h(x_, y_) + 0.03))
        return zc[k]
    for j in range(NY):
        for i in range(NX):
            k = C[j, i]
            if k < 0:
                continue
            c00, c10, c11, c01 = CC[j, i], CC[j, i + 1], CC[j + 1, i + 1], CC[j + 1, i]
            q = [P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)]
            mk = mats[int(k)]
            if k == 0:     # big-scale stone tint patches break the texture repetition
                vv = (math.sin(i * cell * 0.21 + 1.3) + math.sin(j * cell * 0.17 + i * cell * 0.05) + math.sin((i + j) * cell * 0.09)) / 3
                mk = 'cobbles' if vv < -0.2 else ('cobbles_b' if vv < 0.25 else 'cobbles_c')
            if c00 == c10 == c11 == c01 == k:
                mb.poly(q, mk)
                continue
            ctr = sum(q, Vector((0, 0, 0))) / 4
            for (ca, pa_), (cb, pb_) in (((c00, q[0]), (c10, q[1])), ((c10, q[1]), (c11, q[2])),
                                         ((c11, q[2]), (c01, q[3])), ((c01, q[3]), (c00, q[0]))):
                kk = ca if ca == cb and ca >= 0 else k
                mb.poly([pa_, pb_, ctr], mk if kk == k else mats[int(kk)])
    # underlay: coarse paving under everything so no orthophoto shows through gaps at building edges
    base = ChunkMB('Ground_Base-col', tile=60.0)
    area_buf = offset_poly(area, 6.0)
    y = min(ys) - 6
    while y < max(ys):
        x = min(xs)
        while x < max(xs):
            cx, cy = x + 1.5, y + 1.5
            ii_, jj_ = int((cx - gx0_) / cell), int((cy - gy0_) / cell)
            # underlay only where this layer really paves (not under lawn left beside the fortress ribbons, where the
            # coarse 3 m facets poked through the grass, castle hunt c65)
            on_paved = 0 <= ii_ < NX and 0 <= jj_ < NY and paved[jj_, ii_] and C[jj_, ii_] in (0, 1, 3)
            # underlay only beneath paving: on lawns its coarse 3 m facets poked through as grey strips (Earth review)
            q = [(x, y), (x + 3, y), (x + 3, y + 3), (x, y + 3)]
            # no underlay over or at the edge of a fortress flight / carved stair (it stood 1 m above the treads)
            near_cut = any(0 <= int((qx - gx0_) / cell) < NX and 0 <= int((qy - gy0_) / cell) < NY and
                           grown_[int((qy - gy0_) / cell), int((qx - gx0_) / cell)] for qx, qy in q + [(cx, cy)]) or \
                any(point_in_poly(qx, qy, fq) for fq in flights for qx, qy in q + [(cx, cy)])
            if on_paved and not near_cut and point_in_poly(cx, cy, area_buf) and not point_in_poly(cx, cy, OUTER):
                inside_garden = garden_poly and point_in_poly(cx, cy, garden_poly)
                base.poly([Vector((qx, qy, T.h(qx, qy) - 0.02)) for qx, qy in q], 'gravel_white' if inside_garden else 'cobbles')
            x += 3.0
        y += 3.0
    # OSM lawns as draped polygons: exact outlines (photo 09) instead of grid-triangle teeth
    lmb = ChunkMB('Ground_Lawns-col', tile=60.0)
    steps_bvh_ = surface_bvh(('Steps',))
    for gq, gb_ in grass_polys:
        cx_, cy_ = (gb_[0] + gb_[1]) / 2, (gb_[2] + gb_[3]) / 2
        if not point_in_poly(cx_, cy_, area) or (garden_poly and point_in_poly(cx_, cy_, garden_poly)):
            continue
        loop = [Vector((p[0], p[1], 0)) for p in gq]
        if len(loop) > 3 and (loop[0] - loop[-1]).length < 1e-3:
            loop = loop[:-1]
        try:
            tris = geometry.tessellate_polygon([[tuple(v) for v in loop]])
        except Exception:
            continue
        stack = [[loop[t[0]], loop[t[1]], loop[t[2]]] for t in tris]
        while stack:
            tri = stack.pop()
            e = [(tri[k] - tri[(k + 1) % 3]).length for k in range(3)]
            k = max(range(3), key=lambda i_: e[i_])
            if e[k] > 2.0:              # split the longest edge so the lawn follows the terrain
                m_ = (tri[k] + tri[(k + 1) % 3]) / 2
                stack.append([tri[k], m_, tri[(k + 2) % 3]])
                stack.append([m_, tri[(k + 1) % 3], tri[(k + 2) % 3]])
                continue
            q = [Vector((v.x, v.y, T.h(v.x, v.y) + 0.05)) for v in tri]
            ctr_ = (tri[0] + tri[1] + tri[2]) / 3
            zr_ = surface_z(ramps_, ctr_.x, ctr_.y, T.h(ctr_.x, ctr_.y), up=0.5, down=3.0)
            on_steps_ = surface_z(steps_bvh_, ctr_.x, ctr_.y, T.h(ctr_.x, ctr_.y), up=0.6, down=3.0) is not None
            if on_steps_ or (zr_ is not None and zr_ < T.h(ctr_.x, ctr_.y) - 0.05):
                continue     # OSM lawn drawn across a flight (S terrace steps 37409855 buried under grass)
            if geometry.normal(q).z < 0:
                q.reverse()
            lmb.poly(q, 'grass')
    return mb.build(coll) + base.build(coll) + lmb.build(coll)


GARDEN_ORTHO_BBOX = (17.10005, 48.14236, 17.10120, 48.14390)   # W, S, E, N of data/garden_ortho.png


def _pip_mask(xx, yy, poly):
    import numpy as np
    inside = np.zeros(xx.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = ((y1 > yy) != (y2 > yy)) & (xx < (x2 - x1) * (yy - y1) / (y2 - y1 + 1e-12) + x1)
        inside ^= cond
    return inside


def _components(mask):
    """4-connected components of a bool grid as lists of (j, i)."""
    import numpy as np
    seen = np.zeros(mask.shape, dtype=bool)
    ny, nx = mask.shape
    comps = []
    for j0, i0 in zip(*np.nonzero(mask)):
        if seen[j0, i0]:
            continue
        comp = [(j0, i0)]
        seen[j0, i0] = True
        k = 0
        while k < len(comp):
            j, i = comp[k]
            k += 1
            for jj, ii in ((j - 1, i), (j + 1, i), (j, i - 1), (j, i + 1)):
                if 0 <= jj < ny and 0 <= ii < nx and mask[jj, ii] and not seen[jj, ii]:
                    seen[jj, ii] = True
                    comp.append((jj, ii))
        comps.append(comp)
    return comps


def _drop_small(mask, min_cells):
    """Remove 4-connected components smaller than min_cells from a bool grid."""
    import numpy as np
    out = mask.copy()
    seen = np.zeros(mask.shape, dtype=bool)
    ny, nx = mask.shape
    for j0, i0 in zip(*np.nonzero(mask)):
        if seen[j0, i0]:
            continue
        comp = [(j0, i0)]
        seen[j0, i0] = True
        k = 0
        while k < len(comp):
            j, i = comp[k]
            k += 1
            for jj, ii in ((j - 1, i), (j + 1, i), (j, i - 1), (j, i + 1)):
                if 0 <= jj < ny and 0 <= ii < nx and mask[jj, ii] and not seen[jj, ii]:
                    seen[jj, ii] = True
                    comp.append((jj, ii))
        if len(comp) < min_cells:
            for j, i in comp:
                out[j, i] = False
    return out


def _runs(row):
    """Start/end indices of True runs in a 1D bool array."""
    import numpy as np
    d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def build_garden(T, feats, points, coll):
    """Baroque garden (1778-80 design, rebuilt 2016) traced from a 5 cm/px orthophoto:
    box-hedge broderie, lawn panels, crushed-brick beds; clipped lindens come from OSM trees."""
    import numpy as np
    gp = next((f['pts'] for f in feats if f['tags'].get('name') == 'Baroková záhrada'), None)
    path = os.path.join(DATA, 'garden_ortho.png')
    if not gp or not os.path.exists(path):
        return []
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[..., :3]          # row 0 = south
    W_, S_, E_, N_ = GARDEN_ORTHO_BBOX
    gx0, gy0 = to_local(S_, W_)
    gx1, gy1 = to_local(N_, E_)
    cell = 0.25 if FAST else (0.2 if WEB else 0.1)
    nx, ny = int((gx1 - gx0) / cell), int((gy1 - gy0) / cell)
    # resample to the cell grid (box filter) and smooth a bit
    ys = ((np.arange(ny) + 0.5) / ny * h).astype(int)
    xs = ((np.arange(nx) + 0.5) / nx * w).astype(int)
    sm = px.copy()
    for ax in (0, 1):
        sm = (np.roll(sm, 1, ax) + sm + np.roll(sm, -1, ax)) / 3
    g = sm[ys][:, xs]
    r_, g_, b_ = g[..., 0], g[..., 1], g[..., 2]
    lum = g.mean(-1)
    XX, YY = np.meshgrid(gx0 + (np.arange(nx) + 0.5) * cell, gy0 + (np.arange(ny) + 0.5) * cell)
    inside = _pip_mask(XX, YY, offset_poly(gp, -0.3))
    greenish = (g_ > r_ * 1.04) & (g_ > b_ * 1.04)
    dark = inside & greenish & (lum < 0.33)
    red = inside & (r_ > g_ * 1.12) & (r_ > b_ * 1.3) & ~greenish
    trees = [Vector((p['x'], p['y'])) for p in points if p['kind'] == 'tree' and point_in_poly(p['x'], p['y'], gp)]

    def disc_dilate(m, k):
        out = m.copy()
        for dy in range(-k, k + 1):
            for dx in range(-k, k + 1):
                if dx * dx + dy * dy <= k * k:
                    out |= np.roll(np.roll(m, dy, 0), dx, 1)
        return out
    # clipped ball lindens are dark discs ~3 m across, box hedges dark bands < 1.5 m: a 0.8 m opening separates them
    tree_core = ~disc_dilate(~dark, 8)
    tree_blob = disc_dilate(tree_core, 8)
    hedge = dark & ~tree_blob
    lawn = inside & greenish & ~dark & ~disc_dilate(tree_blob, 3)     # sunlit crown edges read as lawn
    extra_trees = []
    for comp in _components(tree_core):
        if len(comp) < 30:
            continue
        cj = sum(j for j, i in comp) / len(comp)
        ci = sum(i for j, i in comp) / len(comp)
        c = Vector((gx0 + (ci + 0.5) * cell, gy0 + (cj + 0.5) * cell))
        if all((c - t).length > 2.0 for t in trees + extra_trees):
            extra_trees.append(c)
    # drop specks
    def clean(m, k=2):
        cnt = sum(np.roll(np.roll(m, dy, 0), dx, 1).astype(np.int8) for dy in range(-k, k + 1) for dx in range(-k, k + 1))
        return m & (cnt >= (2 * k + 1) ** 2 * 0.35)
    def dilate(m, k=1):
        out = m.copy()
        for dy in range(-k, k + 1):
            for dx in range(-k, k + 1):
                out |= np.roll(np.roll(m, dy, 0), dx, 1)
        return out

    def erode(m, k=1):
        return ~dilate(~m, k)
    hedge = erode(dilate(hedge, 1), 1) & inside          # close small breaks in the box borders
    lawn = dilate(erode(lawn, 2), 2) & inside & ~hedge     # drop thin shadow streaks
    red = dilate(erode(red, 1), 1) & inside & ~hedge
    hedge, lawn, red = clean(hedge), clean(lawn), clean(red)
    # straighten the traced borders: blur + re-threshold
    hf = hedge.astype(np.float32)
    for _ in range(2):
        acc = np.zeros_like(hf)
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                acc += np.roll(np.roll(hf, dy, 0), dx, 1)
        hf = acc / 25.0
    hedge = (hf > 0.5) & inside
    # OSM footways and steps through the garden stay open (the visitors' paths; the tracing smears shade over them)
    for f in feats:
        if f['kind'] != 'road' or f['tags'].get('highway') not in ('footway', 'steps', 'path', 'pedestrian'):
            continue
        for (ax_, ay_), (bx_, by_) in zip(f['pts'], f['pts'][1:]):
            if not (point_in_poly(ax_, ay_, gp) or point_in_poly(bx_, by_, gp)):
                continue
            dx_, dy_ = bx_ - ax_, by_ - ay_
            L2 = dx_ * dx_ + dy_ * dy_ + 1e-9
            t_ = np.clip(((XX - ax_) * dx_ + (YY - ay_) * dy_) / L2, 0, 1)
            rr = 1.3 if f['tags'].get('highway') == 'steps' else 0.5      # keep the path centre line free, hedges may flank it
            near_path = (XX - ax_ - t_ * dx_) ** 2 + (YY - ay_ - t_ * dy_) ** 2 < rr ** 2
            hedge &= ~near_path
            lawn &= ~near_path
            red &= ~near_path
    hedge = _drop_small(hedge, 60)                       # isolated scraps < 0.6 m2 (thin broderie lines must survive)
    lawn = _drop_small(lawn & ~hedge, 80)
    # box hedges are at most ~0.6 m wide; wider dark patches (with their rims) are shaded lawn -> opening
    # mapped lawn panels (OSM landuse=grass) are lawn inside; only their rim may carry a box hedge
    for f in feats:
        if f['kind'] == 'area' and f['tags'].get('landuse') == 'grass' and point_in_poly(*f['pts'][0][:2], offset_poly(gp, 3.0)):
            pq = f['pts'] if poly_area(f['pts']) > 0 else list(reversed(f['pts']))
            try:
                core_p = offset_poly(pq, -0.4)      # lawn up to the swept box border (v2_garden.hedges)
            except ZeroDivisionError:
                continue
            if poly_area(core_p) <= 0.5:
                continue
            m_ = _pip_mask(XX, YY, core_p)
            hedge &= ~m_
            lawn |= m_ & inside
    wide_h = dilate(erode(hedge, 5), 5) & hedge
    lawn = (lawn | wide_h) & inside
    hedge = hedge & ~wide_h
    red &= ~hedge
    hmb = ChunkMB('Garden_Hedges-col', tile=40.0)
    smb = ChunkMB('Garden_Beds', tile=40.0)
    zgrid = {}

    def zat(x, y):
        k = (round(x), round(y))
        if k not in zgrid:
            zgrid[k] = T.h(x, y)
        return zgrid[k]
    zcache = {}

    def zv(x, y):        # shared per-vertex terrain sample (keyed on the 0.1 m lattice) -> no cracks
        k = (round(x * 10), round(y * 10))
        if k not in zcache:
            zcache[k] = T.h(x, y)
        return zcache[k]
    # beds: interior cells as merged row runs, boundary cells chamfered from corner-majority classes
    lawn = dilate(erode(lawn, 1), 1) & inside & ~hedge          # drop single-cell lawn specks
    import v2_garden                                             # clean outlines: blur + re-threshold, no islands
    lawn = _drop_small(v2_garden.smooth_mask(lawn) & inside & ~hedge, 250)
    red = _drop_small(v2_garden.smooth_mask(red) & inside & ~hedge & ~lawn, 150)
    for f in feats:      # broderie beds (OSM flowerbeds): crushed-brick ground between the box scrolls (ref 17)
        if f['kind'] == 'area' and f['tags'].get('landuse') == 'flowerbed' and point_in_poly(*f['pts'][0][:2], gp):
            m_ = _pip_mask(XX, YY, offset_poly(f['pts'] if poly_area(f['pts']) > 0 else list(reversed(f['pts'])), -0.4))
            if f['id'] in v2_garden.broderie_ids(feats, gp):      # parametric scrolls there: plain brick ground
                lawn &= ~m_
                red |= m_
            else:
                red |= m_ & ~lawn
    G = np.zeros((ny, nx), dtype=np.int8)
    G[lawn] = 1
    G[red & ~lawn] = 2
    pad = np.pad(G, 1)
    win4 = [pad[0:-1, 0:-1], pad[0:-1, 1:], pad[1:, 0:-1], pad[1:, 1:]]          # corners (ny+1, nx+1)
    cnt = [sum((wv == k).astype(np.int8) for wv in win4) for k in (0, 1, 2)]
    CG = np.argmax(np.stack(cnt), axis=0).astype(np.int8)
    bed_mat = {1: ('grass', 0.13), 2: ('gravel_red', 0.12)}      # clear of the 2 cm paving draped by build_ground_detail
    core = (CG[:-1, :-1] == G) & (CG[:-1, 1:] == G) & (CG[1:, :-1] == G) & (CG[1:, 1:] == G)
    for j in range(ny):
        y0, y1 = gy0 + j * cell, gy0 + (j + 1) * cell
        for kcls in (1, 2):
            mat, hz = bed_mat[kcls]
            for a_, b_ in _runs((G[j] == kcls) & core[j]):
                for a2 in range(a_, b_, 30):
                    b2 = min(b_, a2 + 30)
                    xa, xb = gx0 + a2 * cell, gx0 + b2 * cell
                    smb.poly([Vector((q[0], q[1], zv(q[0], q[1]) + hz)) for q in ((xa, y0), (xb, y0), (xb, y1), (xa, y1))], mat)
        for i in np.nonzero(~core[j] & ((G[j] > 0) | (CG[j, :-1] > 0) | (CG[j, 1:] > 0) | (CG[j + 1, :-1] > 0) | (CG[j + 1, 1:] > 0)))[0]:
            x0_, x1_ = gx0 + i * cell, gx0 + (i + 1) * cell
            cs = [CG[j, i], CG[j, i + 1], CG[j + 1, i + 1], CG[j + 1, i]]
            ps = [(x0_, y0), (x1_, y0), (x1_, y1), (x0_, y1)]
            ctr = ((x0_ + x1_) / 2, (y0 + y1) / 2)
            for e in range(4):
                ca, cb = cs[e], cs[(e + 1) % 4]
                kk = ca if ca == cb else G[j, i]
                if kk == 0:
                    continue
                mat, hz = bed_mat[int(kk)]
                tri = [ps[e], ps[(e + 1) % 4], ctr]
                smb.poly([Vector((q[0], q[1], zv(q[0], q[1]) + hz)) for q in tri], mat)
    # clipped box hedges (photo 11): flat top + vertical faces along a marching-squares contour of the
    # (blurred) mask, so curved hedges run smooth instead of in 10 cm voxel steps
    HH = 0.48
    # no hedges on the terrace banks: the DMR smears each retaining wall into a slope and the hedge became a tilted sheet
    for j, i in zip(*np.nonzero(hedge)):
        x_, y_ = gx0 + (i + 0.5) * cell, gy0 + (j + 0.5) * cell
        if max(abs(zv(x_ + 0.4, y_) - zv(x_ - 0.4, y_)), abs(zv(x_, y_ + 0.4) - zv(x_, y_ - 0.4))) > 0.16:
            hedge[j, i] = False
    # broderie (OSM flowerbeds) is dwarf box ~0.25 m high: taller hedges merge into one mass at eye level
    low = np.zeros(hedge.shape, dtype=bool)
    for f in feats:
        if f['kind'] == 'area' and f['tags'].get('landuse') == 'flowerbed':
            low |= _pip_mask(XX, YY, offset_poly(f['pts'] if poly_area(f['pts']) > 0 else list(reversed(f['pts'])), 0.5))

    # clipped box hedges as continuous flat-topped strips swept along the skeleton of the traced mask (refs 17/27)
    fringe = ChunkMB('Garden_HedgeLeaves', tile=40.0)
    v2_garden.hedges(globals(), hmb, hedge, low, gx0, gy0, cell, zv, HH, feats, gp)
    v2_garden.planters(globals(), hmb, hedge | lawn | red, gx0, gy0, cell, zv, gp, feats, trees + extra_trees)
    print('garden cells: hedge', int(hedge.sum()), 'lawn', int(lawn.sum()), 'red', int(red.sum()), 'lindens', len(trees))
    tufts = ChunkMB('Grass_Tufts', tile=40.0)
    rngt = random.Random(3)
    lj, li = np.nonzero(erode(lawn, 2))
    pick = [] if WEB else rngt.sample(range(len(lj)), min(len(lj), int(lawn.sum() * cell * cell * 2.5)))
    for k in pick:
        x_, y_ = gx0 + (li[k] + rngt.random()) * cell, gy0 + (lj[k] + rngt.random()) * cell
        grass_tuft(tufts, Vector((x_, y_)), zat(x_, y_) + 0.06, rngt)
    # statues on pedestals (OSM artwork nodes inside the garden)
    st = MB('Garden_Statues-col')
    for p in points:
        if p['kind'] == 'statue' and point_in_poly(p['x'], p['y'], gp):
            garden_statue(st, Vector((p['x'], p['y'])), T.h(p['x'], p['y']))
    tobs = tufts.build(coll)
    for ob in tobs:      # sky-facing normals: thin vertical cards otherwise shade almost black
        me = ob.data
        me.normals_split_custom_set_from_vertices([(0.0, 0.0, 1.0)] * len(me.vertices))
    # the many clipped lindens OSM does not map, from the orthophoto crown blobs (photo 17: a dense grid)
    extra_trees += v2_garden.fill_tree_grid(globals(), trees, extra_trees, dark, gx0, gy0, cell, gp, feats)
    gfol, gtrk = ChunkMB('Trees_Foliage_Garden', tile=40.0), ChunkMB('Trees_Trunks_Garden-col', tile=40.0)
    rng_g = random.Random(11)
    for c in extra_trees:
        _tree_topiary(gfol, gtrk, c, zat(c.x, c.y), rng_g)
    print('garden ortho lindens', len(extra_trees))
    return (hmb.build(coll) + smb.build(coll) + [st.build(coll)] + tobs + fringe.build(coll)
            + gfol.build(coll) + gtrk.build(coll))


def grass_tuft(mb, c, z, rng, h=0.22):
    """Two crossed alpha cards of grass blades."""
    a = rng.uniform(0, math.pi)
    for k in range(2):
        u = Vector((math.cos(a + k * math.pi / 2), math.sin(a + k * math.pi / 2), 0)) * rng.uniform(0.12, 0.2)
        p0, p1 = Vector((c.x, c.y, z)) - u, Vector((c.x, c.y, z)) + u
        mb.poly([p0, p1, p1 + Vector((0, 0, h)), p0 + Vector((0, 0, h))], 'grass_tuft', uv=[(0, 0), (1, 0), (1, 1), (0, 1)])


def garden_statue(mb, c, z):
    """Baroque putto/vase group on a moulded pedestal (white sandstone)."""
    sq = lambda r: [c + Vector((-r, -r)), c + Vector((r, -r)), c + Vector((r, r)), c + Vector((-r, r))]
    mb.box(sq(0.55), z - 0.2, z + 0.25, 'marble')
    mb.box(sq(0.42), z + 0.25, z + 1.35, 'marble')
    mb.box(sq(0.52), z + 1.35, z + 1.5, 'marble')
    icosphere(mb, Vector((c.x, c.y, z + 1.85)), 0.38, 'marble', smooth=True, subdiv=1)
    icosphere(mb, Vector((c.x, c.y, z + 2.35)), 0.22, 'marble', smooth=True, subdiv=1)
    mb.box(sq(0.12), z + 1.5, z + 2.2, 'marble')


# ---------------------------------------------------------------- street furniture / monuments (OSM nodes)
def ellipsoid(mb, c, sx, sy, sz, yaw, pitch, mat, subdiv=2):
    """Smooth ellipsoid (sculpture masses): local x forward, rotated by pitch then yaw."""
    global _ICO
    if _ICO is None:
        icosphere(MB('_tmp'), Vector((0, 0, 0)), 1, mat)
    vs, fs = _ICO
    for _ in range(subdiv):
        vs, fs = _subdivide(vs, fs)
    cy, sy_, cp, sp_ = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    out = []
    for v in vs:
        x, y, zz = v.x * sx, v.y * sy, v.z * sz
        x, zz = x * cp - zz * sp_, x * sp_ + zz * cp
        x, y = x * cy - y * sy_, x * sy_ + y * cy
        out.append(c + Vector((x, y, zz)))
    for f in fs:
        mb.poly([out[i] for i in f], mat, uv_scale=1.0)


def equestrian(mb, base, yaw, rear=math.radians(32)):
    """Svätopluk (Ján Kulich, 2010): the horse rears on its hind legs, forelegs folded high, the rider
    upright with the sword raised (photos 04, 06, 07). Masses in a local frame (x forward), body pitched up
    about the hind hip."""
    f = Vector((math.cos(yaw), math.sin(yaw), 0))
    sd = Vector((-f.y, f.x, 0))
    pv_f, pv_u = -0.8, 1.55                                 # hind hip: pivot of the rearing body
    ca, sa = math.cos(rear), math.sin(rear)

    def R(fw, up):                                          # body point after rearing
        df, du = fw - pv_f, up - pv_u
        return pv_f + df * ca - du * sa, pv_u + df * sa + du * ca

    def P(fw, sw, up, body=True):
        if body:
            fw, up = R(fw, up)
        return base + f * fw + sd * sw + Vector((0, 0, up))
    B = 'bronze'
    E = lambda c, sx, sy, sz, pitch=0.0, sub=2: ellipsoid(mb, c, sx, sy, sz, yaw, pitch + rear, B, subdiv=sub)
    E(P(0, 0, 1.75), 1.05, 0.42, 0.5)                                  # barrel
    E(P(0.75, 0, 1.85), 0.45, 0.4, 0.48)                               # chest
    E(P(-0.75, 0, 1.85), 0.52, 0.44, 0.52)                             # hindquarters
    E(P(1.05, 0, 2.35), 0.58, 0.22, 0.3, 1.05)                         # neck, arched up
    E(P(1.35, 0, 2.85), 0.36, 0.15, 0.17, -0.55)                       # head
    E(P(1.0, 0, 2.6), 0.4, 0.06, 0.22, 1.05)                           # mane
    for sgn in (1, -1):                                                # ears
        _prism(mb, P(1.3, sgn * 0.07, 3.05), P(1.28, sgn * 0.09, 3.25), 0.035, 0.008, B, seg=5)
    # hind legs carry the weight: hock bent, hooves planted on the drum under the hips
    for sw, st in ((0.22, 0.0), (-0.22, 0.25)):
        hip = P(-0.75, sw, 1.5)
        hoof = base + f * (-0.55 + st) + sd * sw + Vector((0, 0, 0.06))
        hock = hip.lerp(hoof, 0.55) - f * 0.35
        E(hip.lerp(hock, 0.3), 0.26, 0.18, 0.4, 0.0, 1)
        _prism(mb, hip, hock, 0.18, 0.11, B, seg=8)
        _prism(mb, hock, hoof, 0.1, 0.085, B, seg=8)
        ellipsoid(mb, hoof, 0.11, 0.1, 0.07, 0, 0, B, subdiv=1)
    # forelegs folded in the air
    for sw, lift in ((0.2, 0.0), (-0.2, 0.15)):
        sh = P(0.75, sw, 1.5)
        knee = sh + f * (0.42 + lift) + Vector((0, 0, -0.05 + lift))
        hoof = knee + f * 0.05 + Vector((0, 0, -0.45))
        _prism(mb, sh, knee, 0.16, 0.11, B, seg=8)
        _prism(mb, knee, hoof, 0.1, 0.085, B, seg=8)
        ellipsoid(mb, hoof, 0.1, 0.09, 0.07, 0, 0, B, subdiv=1)
    _prism(mb, P(-1.25, 0, 1.95), P(-1.45, 0, 0.9, body=False), 0.1, 0.05, B, seg=5)   # tail sweeping down
    # rider sits upright on the pitched back: torso, cloak, helmet, shield, raised sword
    seat = P(0.0, 0, 2.25)
    up = Vector((0, 0, 1))
    ellipsoid(mb, seat + up * 0.4 + f * 0.05, 0.24, 0.28, 0.42, yaw, 0.15, B)
    ellipsoid(mb, seat + up * 0.25 - f * 0.25, 0.32, 0.36, 0.48, yaw, -0.2, B)       # cloak over the croup
    ellipsoid(mb, seat + up * 0.95 + f * 0.1, 0.13, 0.12, 0.15, yaw, 0.0, B)        # head
    ellipsoid(mb, seat + up * 1.06 + f * 0.1, 0.15, 0.14, 0.1, yaw, 0.0, B)         # helmet
    ellipsoid(mb, seat + sd * 0.0, 0.42, 0.46, 0.09, yaw, rear, B)                  # saddle cloth
    for sgn in (1, -1):
        knee_ = seat + f * 0.3 + sd * (sgn * 0.42) - up * 0.15
        _prism(mb, seat + sd * (sgn * 0.2), knee_, 0.08, 0.06, B, seg=5)                 # thighs gripping
        _prism(mb, knee_, knee_ - up * 0.5 + f * 0.05, 0.06, 0.05, B, seg=6)             # boots
    sh_r = seat + up * 0.62 + sd * 0.28
    hand = sh_r + up * 0.6 + f * 0.15 + sd * 0.12
    _prism(mb, sh_r, hand, 0.08, 0.06, B, seg=6)                                    # sword arm raised
    _prism(mb, hand, hand + up * 1.15 + f * 0.1, 0.045, 0.02, B, seg=4)             # sword
    ellipsoid(mb, seat + up * 0.45 - sd * 0.4 + f * 0.1, 0.3, 0.05, 0.38, yaw, 0.0, B)   # shield


def build_props(T, points, coll):
    mb = MB('Props')
    col = MB('Props_Solid-col')
    walks = surface_bvh(WALK_SURF)
    lamps = [Vector((q['x'], q['y'])) for q in points if q['kind'] == 'lamp']
    for p in points:
        c = Vector((p['x'], p['y']))
        if point_in_poly(c.x, c.y, OUTER):
            continue
        z = T.h(c.x, c.y)
        # stand on the finished paving (fortress path ribbons, city streets, steps), not on the bare terrain under it:
        # benches on the raised path ribbons had buried legs (Codex V5: vienna_01R); castle ground layer is +3 cm
        zs = surface_z(walks, c.x, c.y, z, up=1.0, down=0.4)
        z = zs if zs is not None else z + 0.03
        k = p['kind']
        if k == 'bench' and (any((t - c).length < 1.5 for t in TRUNKS if abs(t.x - c.x) < 2) or
                             any((lq - c).length < 1.2 for lq in lamps if abs(lq.x - c.x) < 2)):
            continue        # no bench through a trunk or a lamp post
        if k == 'bench':
            for sl in range(4):         # seat slats 60 mm with 10 mm gaps (collidable)
                o0 = -0.22 + sl * 0.11
                seg_box(col, c - Vector((0.9, 0)), c + Vector((0.9, 0)), o0, o0 + 0.095, z + 0.42, z + 0.46, 'door')
            for sl in range(3):         # backrest slats
                zz = z + 0.55 + sl * 0.12
                seg_box(mb, c - Vector((0.9, 0)), c + Vector((0.9, 0)), 0.2, 0.235, zz, zz + 0.09, 'door')
            for sx in (-0.75, 0.75):
                seg_box(mb, c + Vector((sx - 0.04, 0)), c + Vector((sx + 0.04, 0)), -0.2, 0.2, z, z + 0.42, 'metal')
        elif k == 'lamp' and c.length < 130:
            # castle grounds: modern 6 m masts with short arms, each ending in a small downlight head (photo 04)
            seg_box(col, c - Vector((0.07, 0)), c + Vector((0.07, 0)), -0.07, 0.07, z - 0.3, z + 6.3, 'invisible')
            _prism(mb, Vector((c.x, c.y, z)), Vector((c.x, c.y, z + 6.3)), 0.075, 0.05, 'metal', seg=8)
            for j, (hz, ang) in enumerate(((3.3, 0.3), (4.1, 3.4), (4.8, 1.9), (5.5, 5.0), (6.1, 0.9))):
                hz += z     # arm heights are above the mast foot, not absolute
                dv = Vector((math.cos(ang), math.sin(ang)))
                tip = c + dv * 0.42
                _prism(mb, Vector((c.x, c.y, hz)), Vector((tip.x, tip.y, hz + 0.08)), 0.022, 0.018, 'metal', seg=5)
                _prism(mb, Vector((tip.x, tip.y, hz - 0.02)), Vector((tip.x, tip.y, hz + 0.16)), 0.09, 0.09, 'metal', seg=8)
                _prism(mb, Vector((tip.x, tip.y, hz - 0.035)), Vector((tip.x, tip.y, hz - 0.015)), 0.07, 0.07, 'lamp', seg=8)
            add_light(coll, 'L_street', (c.x, c.y, z + 4.6), 110, color=(1.0, 0.85, 0.65))
        elif k == 'lamp':
            seg_box(col, c - Vector((0.06, 0)), c + Vector((0.06, 0)), -0.06, 0.06, z - 0.3, z + 3.6, 'metal')
            seg_box(mb, c - Vector((0.18, 0)), c + Vector((0.18, 0)), -0.18, 0.18, z + 3.6, z + 4.1, 'lamp')
            seg_box(mb, c - Vector((0.24, 0)), c + Vector((0.24, 0)), -0.24, 0.24, z + 4.1, z + 4.2, 'metal')
            add_light(coll, 'L_street', (c.x, c.y, z + 3.75), 90, color=(1.0, 0.8, 0.55))
        elif k == 'flagpole':
            try:                 # OSM height (the national mast W of the castle is 30 m with a big flag, Earth)
                hp = float(str(p['tags'].get('height', '12')).split()[0])
            except (ValueError, IndexError):
                hp = 12.0
            sc_ = hp / 12.0
            rr_ = 0.07 * (1 + 0.6 * (sc_ - 1))
            seg_box(col, c - Vector((rr_, 0)), c + Vector((rr_, 0)), -rr_, rr_, z - 0.3, z + hp, 'frame')
            if hp > 20:          # national mast: painted red / white bands (Earth)
                nb_ = int(hp / 2.5)
                for k_ in range(nb_):
                    seg_box(mb, c - Vector((rr_ + 0.01, 0)), c + Vector((rr_ + 0.01, 0)), -rr_ - 0.01, rr_ + 0.01,
                            z + k_ * hp / nb_, z + (k_ + 1) * hp / nb_, 'flag_red' if k_ % 2 == 0 else 'flag_white')
            fa, fb = c + Vector((rr_, 0)), c + Vector((3.0 * sc_, 0))
            z0f, z1f = z + hp - 2.0 * sc_, z + hp
            nu, nv = 24, 8          # subdivided so the engine can animate it (wind shader in Godot)
            for i in range(nu):
                for j in range(nv):
                    u0, u1, v0, v1 = i / nu, (i + 1) / nu, j / nv, (j + 1) / nv
                    P = lambda u, v: Vector((fa.x + (fb.x - fa.x) * u, fa.y + (fb.y - fa.y) * u, z0f + (z1f - z0f) * v))
                    mb.poly([P(u0, v0), P(u1, v0), P(u1, v1), P(u0, v1)], 'flag_sk',
                            uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        elif k == 'statue':
            nm = p['tags'].get('name', '')
            big = nm == 'Svätopluk'
            w = 1.1 if big else 0.7
            ph = 2.6 if big else 1.2
            if big:   # equestrian Svätopluk (bronze) on a smooth round granite drum (photos 04, 06)
                # round truncated cone of grey speckled granite, ~4.3 m, inscription side to the court (photo 07)
                ph = 4.3
                n_ = 28
                lo_ = [Vector((c.x + 1.75 * math.cos(2 * math.pi * k_ / n_), c.y + 1.75 * math.sin(2 * math.pi * k_ / n_), z - 1.5)) for k_ in range(n_)]
                hi_ = [Vector((c.x + 1.3 * math.cos(2 * math.pi * k_ / n_), c.y + 1.3 * math.sin(2 * math.pi * k_ / n_), z + ph)) for k_ in range(n_)]
                for k_ in range(n_):
                    col.poly([lo_[k_], lo_[(k_ + 1) % n_], hi_[(k_ + 1) % n_], hi_[k_]], 'granite_grey')
                col.poly(hi_, 'bronze')        # bronze top plate (photo 07)
                col.box([c + Vector((-2.4, -2.4)), c + Vector((2.4, -2.4)), c + Vector((2.4, 2.4)), c + Vector((-2.4, 2.4))],
                        z - 0.2, z + 0.03, 'granite_grey')     # low granite base slab
                # the rider faces south, out over the Honour court toward the city (photos 06, 07)
                equestrian(col, Vector((c.x, c.y, z + ph)), math.radians(-90))
            else:
                col.box([c + Vector((-w * 1.6, -w)), c + Vector((w * 1.6, -w)), c + Vector((w * 1.6, w)), c + Vector((-w * 1.6, w))],
                        z - 1.5, z + ph, 'stone')
                col.box([c + Vector((-0.3, -0.3)), c + Vector((0.3, -0.3)), c + Vector((0.3, 0.3)), c + Vector((-0.3, 0.3))], z + 1.2, z + 3.0, 'stone')
        elif k in ('well', 'fountain'):
            well(col, c)
    return [mb.build(coll), col.build(coll)]


JETS = MB('Fountain_Jets')


def build_fountains(T, feats, coll):
    mb = MB('Fountains-col')
    for f in feats:
        t = f['tags']
        if f['kind'] == 'area' and t.get('natural') == 'water' and abs(poly_area(f['pts'])) < 500:
            pts = f['pts'][:-1] if f['pts'][0] == f['pts'][-1] else f['pts']
            fountain(mb, pts, T)
    MATS['jet'].use_backface_culling = False
    return [mb.build(coll), JETS.build(coll)]


# ---------------------------------------------------------------- scene
def setup_scene(coll):
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    try:
        sc.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        sc.render.engine = 'BLENDER_EEVEE'
    world = bpy.data.worlds.new('Sky')
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    nt = world.node_tree
    bg = next(n for n in nt.nodes if n.type == 'BACKGROUND')
    try:
        sky = nt.nodes.new('ShaderNodeTexSky')
        sky.sun_elevation = math.radians(35)
        sky.sun_rotation = math.radians(220)
        nt.links.new(sky.outputs['Color'], bg.inputs['Color'])
        bg.inputs['Strength'].default_value = 0.16
    except Exception as e:
        print('sky node failed', e)
        bg.inputs['Color'].default_value = (0.55, 0.7, 0.9, 1)
    sun_d = bpy.data.lights.new('Sun', 'SUN')
    sun_d.energy = 4.2
    sun_d.color = (1.0, 0.93, 0.82)
    sun_d.angle = math.radians(1.0)
    sun = bpy.data.objects.new('Sun', sun_d)
    sun.rotation_euler = (math.radians(55), 0, math.radians(220 - 180))
    coll.objects.link(sun)
    # spawn: in front of the west (main) gate in the Honour Court
    sp = bpy.data.objects.new('Spawn', None)
    W, _ = wing_frames()
    w = next(x for x in W if x['name'] == 'S')
    o0, o1 = w['o']
    mid = (o0 + o1) / 2
    d = (o1 - o0).normalized()
    n_out = Vector((d.y, -d.x))
    p = mid + n_out * 22
    sp.location = (p.x, p.y, 0.2)
    coll.objects.link(sp)
    cam_d = bpy.data.cameras.new('Camera')
    cam_d.lens = 22
    cam = bpy.data.objects.new('Camera', cam_d)
    cam.location = (p.x, p.y, 1.65)
    look = Vector((mid.x, mid.y, 6)) - Vector(cam.location)
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    coll.objects.link(cam)
    sc.camera = cam
    try:
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except Exception:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    sc.view_settings.view_transform = 'AgX' if 'AgX' in [i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items] else 'Filmic'


def call_v2(module, func, *args, **kw):
    """V2 extension modules (scripts/v2_*.py) get this script's globals as H for helpers."""
    import importlib
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError:
        return None
    importlib.reload(mod)
    fn = getattr(mod, func, None)
    if not fn:
        return None
    try:
        return fn(globals(), *args, **kw)
    except Exception:            # a broken work-in-progress module must not stop the whole build
        import traceback
        print('V2 MODULE FAILED', module)
        traceback.print_exc()
        return None


def back_blind_windows(coll):
    """Palace windows with no modelled room behind them showed the sky through the building as a bright blue
    pane (Codex V5: nicholas_00L, E wing stair hall, attic dormers): give those an interior wall 0.35 m behind."""
    from mathutils.bvhtree import BVHTree
    objs = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('Palace')]
    verts, polys = [], []
    for o in objs:
        mw = o.matrix_world
        b0 = len(verts)
        verts += [mw @ v.co for v in o.data.vertices]
        polys += [[b0 + i for i in p.vertices] for p in o.data.polygons]
    if not polys:
        return []
    bvh = BVHTree.FromPolygons(verts, polys)
    walls = [o for o in objs if o.name.startswith('Palace_Walls')]
    ctr = sum((o.matrix_world @ Vector(b) for o in walls for b in o.bound_box), Vector()) / max(1, 8 * len(walls))
    mb = MB('Palace_WindowBacking')
    n = 0
    for o in objs:
        if not o.name.startswith('Palace_Windows'):
            continue
        mw = o.matrix_world
        for p in o.data.polygons:
            m = o.data.materials[p.material_index] if o.data.materials else None
            if not m or not m.name.startswith('glass') or p.area < 0.3:
                continue
            c = mw @ p.center
            nrm = (mw.to_3x3() @ p.normal).normalized()
            d = nrm if nrm.dot(Vector((ctr.x - c.x, ctr.y - c.y, 0))) > 0 else -nrm
            if bvh.ray_cast(c + d * 0.05, d, 20.0)[0] is not None:
                continue
            q = [mw @ o.data.vertices[i].co + d * 0.35 for i in p.vertices]
            mb.poly(q, 'plaster_int')
            mb.poly(list(reversed(q)), 'plaster_int')
            n += 1
    print('blind windows backed', n)
    return mb.build(coll)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    setup_materials()
    coll = bpy.data.collections.new('BratislavaCastle')
    bpy.context.scene.collection.children.link(coll)
    T = Terrain()
    feats = json.load(open(os.path.join(DATA, 'castle_local.json')))['features']
    T.set_garden(next((f['pts'] for f in feats if f['tags'].get('name') == 'Baroková záhrada'), None))
    castle_area = next((f['pts'] for f in feats if f['tags'].get('name') == 'Bratislavský hrad'), None)
    build_terrain(T, coll, offset_poly(castle_area, 24.0) if castle_area else None)
    build_far_terrain(T, coll)
    build_centre_terrain(T, coll)
    build_landmarks(T, coll)
    build_palace(T, coll)
    back_blind_windows(coll)
    # V2 modules run first: they may add OSM way ids to REPLACED_IDS so build_city skips them
    call_v2('v2_fortress', 'build', T, feats, points_all(), coll)
    call_v2('v2_city', 'build', T, feats, points_all(), coll)
    build_city(T, feats, coll)
    points = json.load(open(os.path.join(DATA, 'castle_local.json'))).get('points', [])
    build_vegetation(T, feats, coll, points)
    build_props(T, points, coll)
    build_ground_detail(T, feats, coll)
    build_fountains(T, feats, coll)
    build_garden(T, feats, points, coll)
    call_v2('walk_routes', 'build', T, OUT)
    setup_scene(coll)
    import bmesh as _bm
    for ob in list(coll.objects):
        if ob.type == 'MESH' and ob.name.startswith(('Trees_Foliage', 'Trees_Trunks', 'Garden_Hedges', 'Props_Solid', 'Garden_Statues', 'Palace_Smooth')):
            bm = _bm.new()
            bm.from_mesh(ob.data)
            _bm.ops.remove_doubles(bm, verts=bm.verts, dist=0.004)
            bm.to_mesh(ob.data)
            bm.free()
    for ob in coll.objects:
        if ob.type == 'MESH':
            for p in ob.data.polygons:
                p.use_smooth = ob.name.startswith(('Terrain', 'Trees_Foliage', 'Trees_Trunks', 'Garden_Hedges', 'Props_Solid', 'Garden_Statues', 'Palace_Smooth'))
            if ob.name.startswith('Palace_Smooth'):
                try:
                    ob.data.set_sharp_from_angle(angle=math.radians(40))   # keep rims and moulding breaks crisp
                except Exception as e:
                    print('sharp-from-angle unavailable', e)
    if not WEB:
        blend = os.path.join(OUT, 'castle.blend')
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        print('saved', blend)
    if '--split' in ARGS:
        # web: the castle (with the ground the player can reach on foot) loads first, the Old Town follows
        # as a separately downloaded pack; Terrain_Centre stays in the first part so nobody falls through
        def is_city(ob):
            return ob.name.startswith(('V2City_', 'V2LM_'))
        for part, sel in (('castle', lambda ob: not is_city(ob)), ('city', is_city)):
            bpy.ops.object.select_all(action='DESELECT')
            for ob in coll.objects:
                if sel(ob):
                    ob.select_set(True)
            glb = os.path.join(OUT, part + '.glb')
            bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', export_cameras=False, use_selection=True,
                                      export_lights=True, export_extras=False, export_apply=True)
            print('exported', glb, os.path.getsize(glb) // 1024, 'KiB')
    elif '--no-export' not in ARGS:
        glb = os.path.join(OUT, 'castle_web.glb' if WEB else 'castle.glb')
        bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', export_cameras=False,
                                  export_lights=True, export_extras=False, export_apply=True)
        print('exported', glb, os.path.getsize(glb) // 1024, 'KiB')
    stats = {ob.name: len(ob.data.polygons) for ob in coll.objects if ob.type == 'MESH'}
    print('objects', len(stats), 'polys', sum(stats.values()))
    groups = {}
    for k_, v_ in stats.items():
        g_ = k_.split('_')[0] + '_' + (k_.split('_')[1] if '_' in k_ else '')
        groups[g_] = groups.get(g_, 0) + v_
    print('TOP', sorted(groups.items(), key=lambda kv: -kv[1])[:14])


main()
