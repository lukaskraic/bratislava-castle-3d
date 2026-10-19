"""Podhradie height audit: Blender -b out/main/castle.blend -P scripts/audit_heights.py [-- OUTDIR]

Samples every 1 m along all OSM building footprint edges and highway centre lines in the Podhradie zone
(x 60..450, y -320..150, Blender coords) and reports
  * floating walls  - no wall at walk ground + 0.05 m although the wall exists higher up (gap > 0.15 m)
  * buried facades  - at walk ground + 0.2 m the wall shows a windowed facade material while the house
                      stands on lower ground elsewhere (> 0.8 m), i.e. ground-floor windows cut by the slope
  * road jumps      - top walk surface change between 1 m samples along a highway that differs from the
                      terrain change: |dz_surface| > |dz_terrain| + 0.2 m (kerbs, lips, holes; stairs, bridges excluded)
Writes OUTDIR/audit.txt and OUTDIR/audit_heatmap.png (top-down, red = floating, blue = buried, yellow = jump).
"""
import bpy, json, math, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv and len(sys.argv) > sys.argv.index('--') + 1 \
    else os.path.join(ROOT, 'out', 'main', 'audit')
os.makedirs(OUT, exist_ok=True)
X0, X1, Y0, Y1 = 60.0, 450.0, -320.0, 150.0
LAT0, LON0, R = 48.142319, 17.1001165, 6378137.0


def L(la, lo):
    return (math.radians(lo - LON0) * R * math.cos(math.radians(LAT0)), math.radians(la - LAT0) * R)


dg = bpy.context.evaluated_depsgraph_get()
GROUND = ('Terrain-col', 'Terrain_Centre-col', 'V2City_StreetsWalk', 'V2City_StreetDetail', 'Fort_Paths',
          'Fort_Ramps', 'Ground_Detail', 'Steps', 'Paving', 'Fort_Ground', 'Fort_Descent', 'Fort_Stairs')
BLD = ('V2City_Bld', 'V2City_Podhradie', 'Buildings', 'Fort_Buildings', 'V2City_Landmarks')
FACADE_MATS = ('v2_wall', 'v2_narrow', 'v2_shop', 'v2_modern', 'bldg_wall', 'plaster')
ter = [BVHTree.FromObject(o, dg) for o in bpy.data.objects if o.type == 'MESH' and o.name in ('Terrain-col', 'Terrain_Centre-col')]
gnd = [BVHTree.FromObject(o, dg) for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(GROUND)]
bld = [(BVHTree.FromObject(o, dg), o) for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(BLD)]
DOWN = Vector((0, 0, -1))


def ground(x, y, bs=None):
    best = None
    for b in (bs or gnd):
        h = b.ray_cast(Vector((x, y, 300.0)), DOWN)
        if h[0] is not None and (best is None or h[0].z > best):
            best = h[0].z
    return best


def wall_hit(o, d, maxd=1.2):
    best = None
    for b, ob in bld:
        h = b.ray_cast(o, d, maxd)
        if h[0] is not None and (best is None or h[3] < best[0]):
            mat = ob.material_slots[ob.data.polygons[h[2]].material_index].name if ob.material_slots else ''
            best = (h[3], mat)
    return best


data = json.load(open(os.path.join(ROOT, 'data', 'v2', 'city', 'buildings.json')))
misc = json.load(open(os.path.join(ROOT, 'data', 'v2', 'city', 'misc.json')))
floating, buried, jumps = [], [], []
n_wall = n_road = 0
for e in data['elements']:
    t = e.get('tags', {})
    if 'building' not in t and 'building:part' not in t:
        continue
    if t.get('building') in ('roof', 'carport', 'construction'):
        continue                                    # no walls of its own
    if _ := t.get('min_height'):
        continue
    gs = [e['geometry']] if e['type'] == 'way' and e.get('geometry') else \
        [m['geometry'] for m in e.get('members', []) if m.get('geometry') and m.get('role') == 'outer']
    for g in gs:
        p = [L(q['lat'], q['lon']) for q in g if q]
        if len(p) < 3:
            continue
        cx, cy = sum(a for a, b in p) / len(p), sum(b for a, b in p) / len(p)
        if not (X0 < cx < X1 and Y0 < cy < Y1):
            continue
        area = 0.5 * sum(p[i][0] * p[i - 1][1] - p[i - 1][0] * p[i][1] for i in range(len(p)))
        sgn = 1 if area > 0 else -1                 # CCW -> outward = right normal
        samples = []
        for a, b in zip(p, p[1:] + p[:1]):
            A, B = Vector(a), Vector(b)
            Ln = (B - A).length
            if Ln < 1.0:
                continue
            d = (B - A) / Ln
            out = Vector((d.y, -d.x)) * sgn
            for k in range(int(Ln)):
                q = A + d * (k + 0.5)
                o = q + out * 0.6
                z = ground(o.x, o.y)
                if z is None:
                    continue
                samples.append((q, out, z))
        if not samples:
            continue
        zmin = min(s[2] for s in samples)
        for q, out, z in samples:
            o = q + out * 0.6
            n_wall += 1
            lo = wall_hit(Vector((o.x, o.y, z + 0.05)), Vector((-out.x, -out.y, 0)))
            if lo is None:
                hi = wall_hit(Vector((o.x, o.y, z + 1.5)), Vector((-out.x, -out.y, 0)))
                if hi is not None:
                    floating.append((q.x, q.y, e['id']))
                continue
            mid = wall_hit(Vector((o.x, o.y, z + 0.2)), Vector((-out.x, -out.y, 0)))
            if mid is not None and mid[1].startswith(FACADE_MATS) and z - zmin > 0.8:
                buried.append((q.x, q.y, e['id'], round(z - zmin, 2)))
for e in misc['elements']:
    t = e.get('tags', {})
    if e['type'] != 'way' or not t.get('highway') or not e.get('geometry'):
        continue
    if t.get('highway') == 'steps' or t.get('bridge') or 'schody' in t.get('name', '').lower() or t.get('tunnel') or (t.get('layer') or '0').startswith('-'):
        continue
    p = [L(q['lat'], q['lon']) for q in e['geometry']]
    prev = tprev = None
    for a, b in zip(p, p[1:]):
        A, B = Vector(a), Vector(b)
        Ln = (B - A).length
        for k in range(max(1, int(Ln))):
            q = A.lerp(B, k / max(1, int(Ln)))
            if not (X0 < q.x < X1 and Y0 < q.y < Y1):
                prev = tprev = None
                continue
            z = ground(q.x, q.y)
            tz = ground(q.x, q.y, ter)
            n_road += 1
            # a step = surface change not explained by the terrain slope (lidar terrain is smooth at 1 m)
            if prev is not None and z is not None and tz is not None and tprev is not None and \
                    abs(z - prev) > abs(tz - tprev) + 0.2:
                jumps.append((q.x, q.y, e['id'], round(z - prev, 2)))
            prev, tprev = z, tz

with open(os.path.join(OUT, 'audit.txt'), 'w') as f:
    f.write(f'wall samples {n_wall}  floating {len(floating)}  buried {len(buried)}\n')
    f.write(f'road samples {n_road}  jumps>0.2m {len(jumps)}\n')
    for name, lst in (('FLOATING', floating), ('BURIED', buried), ('JUMP', jumps)):
        for r_ in lst:
            f.write(name + ' ' + ' '.join(str(round(v, 1)) if isinstance(v, float) else str(v) for v in r_) + '\n')
print('AUDIT wall samples', n_wall, 'floating', len(floating), 'buried', len(buried), '| road samples', n_road, 'jumps', len(jumps))

try:
    import numpy as np
    W, Hh = int(X1 - X0), int(Y1 - Y0)
    img = np.ones((Hh, W, 4), dtype=np.float32) * np.array((0.15, 0.15, 0.15, 1.0), dtype=np.float32)
    for lst, col in ((buried, (0.2, 0.4, 1.0)), (jumps, (1.0, 0.9, 0.1)), (floating, (1.0, 0.1, 0.1))):
        for r_ in lst:
            i, j = int(r_[0] - X0), int(r_[1] - Y0)
            img[max(0, j - 1):j + 2, max(0, i - 1):i + 2, :3] = col
    im = bpy.data.images.new('audit_heatmap', W, Hh)
    im.pixels.foreach_set(img.ravel())
    im.filepath_raw = os.path.join(OUT, 'audit_heatmap.png')
    im.file_format = 'PNG'
    im.save()
except Exception as ex:
    print('heatmap failed', ex)
