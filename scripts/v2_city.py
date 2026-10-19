"""V2 surroundings: Old Town / Podhradie / Danube ring (330-1250 m from the palace) from OSM.

Called from build_castle.main() before build_city:  build(H, T, feats, points, coll)
H = build_castle globals (helpers, materials, terrain samplers).

Builds
  * 3D buildings and building:parts with heights, roof shapes and colours from OSM tags,
    windowed facade textures (one texture, tinted materials), chunked for culling;
  * landmarks with custom tops: St Martin's Cathedral tower (gilded crown), Michael's Gate
    (copper baroque cupola + St Michael), and the SNP Bridge (deck, leaning A-pylon, UFO, stays);
  * the Danube surface from the OSM riverbank multipolygon at river level;
  * other bridges from highway/railway ways tagged bridge=yes (deck + piers);
  * draped street ribbons (asphalt / setts).
Data: data/v2/city/buildings.json, data/v2/city/misc.json (Overpass "out geom").
"""
import json
import math
import os
import random

R_MIN, R_MAX = 330.0, 1250.0
R_BUILD = 1700.0        # buildings use the whole downloaded square (corners ~1.7 km)
FLOOR_H = 3.2
R_TREE_NEAR = 600.0   # beyond: thinned trees with a single low-poly crown
R_ROAD_NEAR = 90.0   # streets outside the castle walls (Vienna Gate / Palisady junction) start here
GRADED_STREETS = ('Žižkova', 'Beblavého', 'Vydrica')
PODHRADIE_R = 460.0  # V4 detail focus: castle-hill foot down to the embankment
R_NEAR = 130.0       # Podhradie: V2 takes over V1 build_city from here out
R_DETAIL = 600.0      # beyond: tiny parts dropped, outlines simplified


def _load(H, name):
    p = os.path.join(H['DATA'], 'v2', 'city', name)
    return json.load(open(p)) if os.path.exists(p) else {'elements': []}


def _ring_xy(H, geom):
    to_local = H['to_local']
    return [to_local(g['lat'], g['lon']) for g in geom if g]


def _area(p):
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def _clean(p):
    if len(p) > 1 and abs(p[0][0] - p[-1][0]) < 1e-6 and abs(p[0][1] - p[-1][1]) < 1e-6:
        p = p[:-1]
    out = []
    for q in p:
        if not out or math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) > 0.05:
            out.append(q)
    if _area(out) < 0:
        out.reverse()
    return out


def _simplify(p, tol):
    """Drop vertices that sit within tol of the chord of their neighbours (far, low-detail rings)."""
    pts = list(p)
    changed = True
    while changed and len(pts) > 4:
        changed = False
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            if L > 1e-6 and abs((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / L < tol:
                pts.pop(i)
                changed = True
                break
    return pts


def _assemble(H, members, role='outer'):
    """Chain member ways (out geom) into closed rings."""
    segs = [_ring_xy(H, m['geometry']) for m in members if m.get('role', 'outer') == role and m.get('geometry')]
    rings = []
    segs = [s for s in segs if len(s) >= 2]
    while segs:
        ring = segs.pop(0)
        changed = True
        while changed and math.hypot(ring[0][0] - ring[-1][0], ring[0][1] - ring[-1][1]) > 0.5:
            changed = False
            for i, s in enumerate(segs):
                if math.hypot(s[0][0] - ring[-1][0], s[0][1] - ring[-1][1]) < 0.5:
                    ring += s[1:]
                elif math.hypot(s[-1][0] - ring[-1][0], s[-1][1] - ring[-1][1]) < 0.5:
                    ring += list(reversed(s))[1:]
                elif math.hypot(s[-1][0] - ring[0][0], s[-1][1] - ring[0][1]) < 0.5:
                    ring = s[:-1] + ring
                elif math.hypot(s[0][0] - ring[0][0], s[0][1] - ring[0][1]) < 0.5:
                    ring = list(reversed(s))[:-1] + ring
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def _num(v, default=None):
    if v is None:
        return default
    try:
        return float(str(v).split()[0].replace(',', '.').rstrip('m'))
    except ValueError:
        return default


def _hex(c):
    named = {'white': '#F2F0EA', 'yellow': '#E8D9A0', 'beige': '#E3D6BB', 'grey': '#A8A8A4', 'gray': '#A8A8A4',
             'red': '#B04A32', 'brown': '#7A4B32', 'black': '#3A3A3A', 'green': '#5C8A70', 'orange': '#D08040',
             'cream': '#EFE6CF', 'pink': '#E3B8A8', 'blue': '#8094A8'}
    if not c:
        return None
    c = c.strip().lower()
    if c in named:
        c = named[c]
    if c.startswith('#') and len(c) in (4, 7):
        if len(c) == 4:
            c = '#' + ''.join(ch * 2 for ch in c[1:])
        try:
            return tuple(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
        except ValueError:
            return None
    return None


WALL_PALETTE = [('v2_wall_white', '#EFEBE2'), ('v2_wall_cream', '#EAD8B2'), ('v2_wall_ochre', '#E3C07A'),
                ('v2_wall_pink', '#E8BDA4'), ('v2_wall_grey', '#C2BDB2'), ('v2_wall_green', '#C3D2AC'),
                ('v2_wall_blue', '#BFCCD9'), ('v2_wall_yellow', '#EDD488'), ('v2_wall_modern', '#D7D9DA')]
ROOF_PALETTE = [('v2_roof_red', '#B8553A'), ('v2_roof_brown', '#8A5442'), ('v2_roof_dark', '#5A5652'),
                ('v2_roof_copper', '#5E9C82'), ('v2_roof_grey', '#8D8E8C')]


OLD_TOWN_WEIGHTS = {'v2_wall_white': 4.5, 'v2_wall_cream': 3.0, 'v2_wall_ochre': 0.8, 'v2_wall_yellow': 1.0,
                    'v2_wall_pink': 2, 'v2_wall_green': 0.8, 'v2_wall_grey': 0.3, 'v2_wall_blue': 0.6}


def _nearest(pal, rgb, rng, core=False):
    if rgb is None and core and pal is WALL_PALETTE:     # Old Town: pastel yellow / ochre / pink / white mix
        names = list(OLD_TOWN_WEIGHTS)
        return rng.choices(names, weights=[OLD_TOWN_WEIGHTS[k] for k in names])[0]
    if rgb is None:
        return pal[rng.randrange(len(pal) - 1)][0] if pal is WALL_PALETTE else pal[0][0]
    best, bd = pal[0][0], 9
    for nm, hx in pal:
        c = tuple(int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5))
        dd = sum((a - b) ** 2 for a, b in zip(c, rgb))
        if dd < bd:
            best, bd = nm, dd
    return best


def _materials(H):
    import numpy as np
    tx = H['textures']
    MATS, make_mat, tint_mat = H['MATS'], H['make_mat'], H['tint_mat']
    if 'v2_wall' in MATS:
        return
    rng = np.random.default_rng(31)
    n = 256
    # one facade bay (3.2 m x 3.2 m): plaster, window with light surround, dark glazing, sill shadow
    rgb = tx.plaster(n, rng, base='#F2EEE6', var=0.05)
    y, x = np.mgrid[0:n, 0:n] / n
    win = (x > 0.32) & (x < 0.68) & (y > 0.28) & (y < 0.78)
    surround = (x > 0.29) & (x < 0.71) & (y > 0.25) & (y < 0.81) & ~win
    rgb[surround] = rgb[surround] * 1.05
    glass = np.stack([0.16 + 0.1 * y, 0.19 + 0.1 * y, 0.22 + 0.1 * y], -1)
    rgb[win] = glass[win]
    bars = win & ((np.abs(x - 0.5) < 0.012) | (np.abs(y - 0.62) < 0.012))
    rgb[bars] = (0.85, 0.84, 0.8)
    rgb[(y > 0.2) & (y < 0.25) & (x > 0.29) & (x < 0.71)] *= 0.7
    rgb[(y < 0.03)] *= 0.92          # cordon line between storeys
    img = tx._save(os.path.join(H['TEX'], 'v2_facade.png'), np.clip(rgb, 0, 1))
    # Podhradie burgher-house bay: two tall narrow casements per 3.2 m bay with stone surrounds and sills
    rgb2 = tx.plaster(n, rng, base='#F2EEE6', var=0.05)
    glass2 = np.stack([0.24 + 0.14 * y, 0.28 + 0.14 * y, 0.32 + 0.15 * y], -1)          # lighter, sky-tinted
    for x0_, x1_ in ((0.14, 0.38), (0.62, 0.86)):
        w2 = (x > x0_) & (x < x1_) & (y > 0.2) & (y < 0.84)
        s2 = (x > x0_ - 0.04) & (x < x1_ + 0.04) & (y > 0.16) & (y < 0.88) & ~w2
        rgb2[s2] = (0.93, 0.92, 0.89)                                                    # white stucco surround
        rgb2[w2] = glass2[w2]
        bars2 = w2 & ((np.abs(x - (x0_ + x1_) / 2) < 0.01) | (np.abs(y - 0.41) < 0.009) | (np.abs(y - 0.63) < 0.009))
        rgb2[bars2] = (0.9, 0.89, 0.86)                                                  # 6-pane casement
        rgb2[(y > 0.13) & (y < 0.17) & (x > x0_ - 0.05) & (x < x1_ + 0.05)] *= 0.72
    rgb2[(y < 0.03)] *= 0.92
    _vc_material(H, 'v2_narrow', tx._save(os.path.join(H['TEX'], 'v2_facade_narrow.png'), np.clip(rgb2, 0, 1)), 1.0, 0.9)
    _vc_material(H, 'v2_wall', img, 1.0, 0.9)
    # shop storey, two bays per tile: framed shop window with sign fascia | door + narrow window
    rgb = tx.plaster(n, rng, base='#F2EEE6', var=0.05)
    rgb = np.concatenate([rgb, rgb[:, ::-1]], 1)
    y, x = np.mgrid[0:n, 0:2 * n] / n
    x = x / 2
    frame = np.array((0.17, 0.13, 0.10))
    glass = np.stack([0.13 + 0.12 * y, 0.15 + 0.12 * y, 0.17 + 0.13 * y], -1)
    glass[y < 0.32] = glass[y < 0.32] * 0.6 + np.array((0.36, 0.30, 0.22)) * 0.4      # lit display
    glass[(y > 0.1) & (y < 0.3) & (((x * 20) % 1) < 0.6)] = (0.55, 0.42, 0.3)          # goods on the display shelf
    glass[(y > 0.42) & (y < 0.44)] = (0.4, 0.38, 0.33)                                   # shelf / transom bar
    glass[np.abs((x - 0.05) - (y - 0.1) * 0.35 - 0.12) < 0.025] *= 1.6                  # sky reflection streak
    for x0, x1, y0, y1 in ((0.05, 0.45, 0.07, 0.74), (0.58, 0.77, 0.0, 0.70), (0.83, 0.95, 0.14, 0.70)):
        out_ = (x > x0 - 0.015) & (x < x1 + 0.015) & (y > max(0, y0 - 0.015)) & (y < y1 + 0.015)
        in_ = (x > x0) & (x < x1) & (y > y0) & (y < y1)
        rgb[out_] = frame
        rgb[in_] = glass[in_]
    door = (x > 0.59) & (x < 0.76) & (y < 0.69)
    rgb[door & (y < 0.45)] = frame * 1.25                                                # wooden lower door leaf
    rgb[door & (np.abs(x - 0.675) < 0.006)] = frame
    rgb[(x > 0.04) & (x < 0.46) & (y > 0.79) & (y < 0.9)] = (0.20, 0.27, 0.24)          # shop sign fascia
    for k in range(9):                                                                   # gilt sign lettering
        lx = 0.08 + k * 0.038
        rgb[(x > lx) & (x < lx + 0.024) & (y > 0.815) & (y < 0.875) & ((k % 4) != 3)] = (0.85, 0.72, 0.4)
    rgb[(y < 0.05)] = rgb[(y < 0.05)] * 0.55 + 0.25                                      # stone plinth
    rgb[(y > 0.95)] *= 0.8                                                               # cornice shadow
    shop = tx._save(os.path.join(H['TEX'], 'v2_shop.png'), np.clip(rgb[::-1], 0, 1))   # row 0 = bottom (v = 0)
    _vc_material(H, 'v2_shop', shop, 1.0, 0.6)
    # modern facade storey: ribbon glazing with slim mullions over a light spandrel band
    rgb = np.ones((n, n, 3)) * 0.9 + rng.normal(0, 0.01, (n, n, 1))
    y, x = np.mgrid[0:n, 0:n] / n                  # row 0 = top (v = 1)
    band = (y > 0.12) & (y < 0.72)
    rgb[band] = np.stack([0.15 + 0.18 * (y - 0.12), 0.19 + 0.18 * (y - 0.12), 0.23 + 0.2 * (y - 0.12)], -1)[band]
    rgb[band & ((x % 0.5) < 0.02)] = 0.55
    rgb[(y > 0.72) & (y < 0.76)] = 0.6                # sill shadow line
    _vc_material(H, 'v2_modern', tx._save(os.path.join(H['TEX'], 'v2_modern.png'), np.clip(rgb, 0, 1)), 1.0, 0.4)
    for nm, hx in WALL_PALETTE + [('v2_wall_primate', '#EDBBAA'), ('v2_wall_bluechurch', '#A8C8E8')]:
        _tint(nm.replace('v2_wall_', 'v2_modern_'), 'v2_modern', hx, 1.0)
        _tint(nm.replace('v2_wall_', 'v2_shop_'), 'v2_shop', hx, 1.7)
        _tint(nm, 'v2_wall', hx, 1.3)
        _tint(nm.replace('v2_wall_', 'v2_narrow_'), 'v2_narrow', hx, 1.2)          # softer pastels (Earth)
    make_mat('v2_render_ochre', H['MATS']['plaster'].node_tree.nodes['Image Texture'].image
             if 'Image Texture' in H['MATS']['plaster'].node_tree.nodes else None, uv=3.0, rough=0.9)
    tint_mat('v2_render_ochre', '#E4BE68')      # Old Town Hall tower: yellow-ochre render (Earth gs_hlavne_nam)
    make_mat('v2_render_blue', H['MATS']['plaster'].node_tree.nodes['Image Texture'].image
             if 'Image Texture' in H['MATS']['plaster'].node_tree.nodes else None, uv=3.0, rough=0.9)
    tint_mat('v2_render_blue', '#9CC0E6')
    make_mat('v2_hat', None, color=(0.42, 0.07, 0.06), rough=0.5)
    _vc_material(H, 'v2_car', tx._save(os.path.join(H['TEX'], 'v2_white.png'), np.ones((4, 4, 3)) * 0.9), 1.0, 0.35)
    make_mat('v2_void', None, color=(0.09, 0.065, 0.045), rough=1.0, spec=0.0)
    make_mat('v2_garagedoor', None, color=(0.36, 0.2, 0.15), rough=0.7)
    make_mat('v2_lampglass', None, color=(0.95, 0.88, 0.7), rough=0.3, emit=((1.0, 0.85, 0.6), 0.6))     # passage darkness
    make_mat('v2_rubble', H['MATS']['stone'].node_tree.nodes['Image Texture'].image
             if 'Image Texture' in H['MATS']['stone'].node_tree.nodes else None, uv=1.6, rough=0.95)
    tint_mat('v2_rubble', '#6E6152')                # dark weathered brown-grey city-wall rubble
    make_mat('v2_iron', None, color=(0.04, 0.06, 0.05), rough=0.45, metal=0.6)      # painted cast iron
    make_mat('v2_timber', None, color=(0.33, 0.2, 0.11), rough=0.7)
    pb = np.ones((n, n, 3)) * np.array((0.62, 0.6, 0.5))                                  # mottled plane-tree bark
    blot = tx.fbm(n, rng, octaves=(6, 12, 24))
    pb[blot > 0.55] = np.array((0.78, 0.76, 0.62))
    pb[blot < 0.3] = np.array((0.45, 0.43, 0.33))
    make_mat('v2_planebark', tx._save(os.path.join(H['TEX'], 'v2_planebark.png'), np.clip(pb, 0, 1)), uv=1.5, rough=0.9)
    if True:
        n = 128
        rng_ = np.random.default_rng(3)
        y, x = np.mgrid[0:n, 0:n] / n
        rgb = np.ones((n, n, 3)) * 0.66 + rng_.normal(0, 0.02, (n, n, 1))
        for k in range(4):                       # 4 x 4 slabs of 0.5 m per 2 m tile, staggered rows
            off = 0.125 * (k % 2)
            rgb[(np.abs(y - k / 4) < 0.008)] = 0.45
            rgb[(np.abs(((x + off) * 4) % 1) < 0.03) & (y >= k / 4) & (y < (k + 1) / 4)] = 0.47
        H['make_mat']('v2_slabs', H['textures']._save(os.path.join(H['TEX'], 'v2_slabs.png'), np.clip(rgb, 0, 1)), uv=2.0, rough=0.85)
        make_mat('v2_squareslab', H['MATS']['v2_slabs'].node_tree.nodes['Image Texture'].image
                 if 'Image Texture' in H['MATS']['v2_slabs'].node_tree.nodes else None, uv=2.0, rough=0.85)
        tint_mat('v2_squareslab', '#D9CBB0')            # Hlavne nam.: large beige limestone slabs (Earth)
    # leaded glass: dark tinted quarries in a diamond lead lattice, two stone mullions
    yy, xx = np.mgrid[0:n, 0:n] / n
    lg = np.stack([0.07 + 0.05 * rng.random((n, n)), 0.09 + 0.05 * rng.random((n, n)), 0.13 + 0.06 * rng.random((n, n))], -1)
    lead = (np.abs(((xx + yy) * 10) % 1 - 0.5) > 0.46) | (np.abs(((xx - yy) * 10) % 1 - 0.5) > 0.46)
    lg[lead] = (0.03, 0.03, 0.03)
    lg[(np.abs(xx - 1 / 3) < 0.025) | (np.abs(xx - 2 / 3) < 0.025)] = (0.72, 0.7, 0.64)
    lg[np.abs(yy - 0.5) < 0.015] = (0.72, 0.7, 0.64)                                  # transom
    make_mat('v2_leaded', tx._save(os.path.join(H['TEX'], 'v2_leaded.png'), np.clip(lg, 0, 1)), uv=1.0, rough=0.2)
    roof_img = next(n_.image for n_ in MATS['roof'].node_tree.nodes if n_.type == 'TEX_IMAGE')
    # neutral (luminance) copy of the tile texture: the vertex colour carries the roof colour, so dark
    # slate, grey flat roofs and copper no longer all read as red tiles
    w_, h_ = roof_img.size
    px = np.empty(w_ * h_ * 4, dtype=np.float32)
    roof_img.pixels.foreach_get(px)
    px = px.reshape(h_, w_, 4)[..., :3]
    lum = px @ np.array([0.3, 0.55, 0.15])
    lum = np.clip(lum / max(lum.mean(), 1e-3) * 0.75, 0, 1)
    grey = tx._save(os.path.join(H['TEX'], 'v2_roof_neutral.png'), np.repeat(lum[::-1, :, None], 3, 2))
    _vc_material(H, 'v2_roof', grey, 1.2, 0.75)      # ~1 m tile repeat (no 'golf balls')
    _vc_material(H, 'v2_flat', None, 2.0, 0.9, src='gravel')          # flat roofs: gravel / membrane, not tiles
    for nm, hx in ROOF_PALETTE + [('v2_roof_bluechurch', '#3E78B8'), ('v2_roof_crimson', '#A2463A'), ('v2_roof_salmon', '#BC7058')]:
        TINT[nm] = ('v2_roof', tuple(min(1.0, _lin(int(hx[i:i + 2], 16) / 255) / 0.6) for i in (1, 3, 5)))   # vertex colours are linear
    TINT['v2_roof_grey'] = ('v2_flat', (0.62, 0.62, 0.6))
    # one leaves material for all city trees; the three V1 leaf tones become vertex colours
    _vc_material(H, 'leaves_v2city', None, 1.0, 0.8, src='leaves')
    for nm, hx in (('leaves', '#E6F0E0'), ('leaves_dark', '#A9BCA4'), ('leaves_light', '#FFFFEC')):
        _tint(nm, 'leaves_v2city', hx)
    # asphalt + setts for streets
    a = tx.fbm(n, rng, octaves=(16, 64, 128)) * 0.18 + 0.28
    make_mat('v2_asphalt', tx._save(os.path.join(H['TEX'], 'v2_asphalt.png'), np.stack([a, a, a * 1.02], -1)), uv=4.0, rough=0.9)
    make_mat('v2_paint', None, color=(0.86, 0.86, 0.83), rough=0.6)
    make_mat('v2_copper', None, color=(0.33, 0.56, 0.47), rough=0.5, metal=0.4)
    make_mat('v2_slate', None, color=(0.22, 0.26, 0.27), rough=0.55, metal=0.2)
    # pale weathered limestone ashlar (St Martin): 0.6 m courses of staggered blocks, rain streaks, grime
    yy, xx = np.mgrid[0:n, 0:n] / n
    ash = np.ones((n, n, 3)) * np.array((0.90, 0.85, 0.74)) + tx.fbm(n, rng, octaves=(8, 32, 96))[..., None] * 0.06 - 0.03
    ash *= (1.0 - 0.07 * np.clip(tx.fbm(n, rng, octaves=(4, 16))[..., None] * 2 - 0.6, 0, 1) * (yy[..., None] * 0.6 + 0.4))
    for k in range(4):
        ash[np.abs(yy - k / 4) < 0.006] *= 0.72
        off = 0.25 * (k % 2)
        ash[(np.abs(((xx + off) * 2) % 1) < 0.008) & (yy >= k / 4) & (yy < (k + 1) / 4)] *= 0.72
    make_mat('v2_stone_church', tx._save(os.path.join(H['TEX'], 'v2_ashlar.png'), np.clip(ash, 0, 1)), uv=1.5, rough=0.85)


TINT = {}          # tinted material name -> (shared base material, vertex colour)
NEAR_SPLIT = 700.0  # chunks beyond this distance are larger and named *Far* (no shadow casting)


def _vc_material(H, name, image, uv, rough, src=None):
    """Base colour = image x vertex colour (glTF COLOR_0), so many tints share one material/surface."""
    MATS = H['MATS']
    if src is not None:
        m = MATS[src].copy()
        m.name = name
        MATS[name] = m
        H['MAT_UV'][name] = uv
    else:
        H['make_mat'](name, image, uv=uv, rough=rough)
        m = MATS[name]
    nt = m.node_tree
    bs = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tn = next(n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and not n.image.name.endswith('_n.png'))
    va = nt.nodes.new('ShaderNodeVertexColor')
    va.layer_name = 'Col'
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    nt.links.new(tn.outputs['Color'], mix.inputs['A'])
    nt.links.new(va.outputs['Color'], mix.inputs['B'])
    nt.links.new(mix.outputs['Result'], bs.inputs['Base Color'])


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _tint(name, base, hexc, sat=1.0):
    """sat > 1 pushes pastel tints further from white (they wash out under the blue sky light)."""
    c = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    mx = max(c)
    TINT[name] = (base, tuple(max(0.3, 1.0 - (1.0 - v / mx) * sat) for v in c))


def _cmb_class(H):
    MB = H['MB']

    class CMB(MB):
        """MB with a per-face vertex colour (written to the 'Col' corner attribute)."""

        def __init__(self, name):
            super().__init__(name)
            self.cols = []

        def build(self, collection=None):
            ob = super().build(collection)
            me = ob.data
            if len(me.polygons) != len(self.cols):
                return ob                 # validate() dropped faces; keep the mesh uncoloured
            import numpy as np
            ca = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
            tot = np.array([f.loop_total for f in me.polygons])
            rgba = np.repeat(np.array([(*c, 1.0) for c in self.cols], dtype=np.float32), tot, axis=0)
            ca.data.foreach_set('color', rgba.ravel())
            return ob
    return CMB


class VChunk:
    """Spatial chunks sized by distance from the palace (small near, large far -> few draw calls);
    tinted materials are folded into shared vertex-coloured base materials."""

    def __init__(self, H, name, far_name, near_tile=350.0, far_tile=700.0, walk_name=None, walk_tile=300.0):
        import types
        self.CMB = _cmb_class(H)
        self.name, self.far_name = name, far_name
        self.walk_name, self.walk_tile = walk_name, walk_tile      # walkable centre: own '-col' chunks
        self.near_tile, self.far_tile = near_tile, far_tile
        self.parts = {}
        self.box = types.MethodType(H['MB'].box, self)
        self.poly_up = types.MethodType(H['MB'].poly_up, self)

    def poly(self, pts, mat, uv_scale=None, uv=None):
        n = len(pts)
        cx = sum(p[0] for p in pts) / n
        cy = sum(p[1] for p in pts) / n
        walk = self.walk_name is not None and in_walk(cx, cy)
        far = 'w' if walk else math.hypot(cx, cy) > NEAR_SPLIT
        t = self.walk_tile if walk else (self.far_tile if far else self.near_tile)
        key = (far, math.floor(cx / t), math.floor(cy / t))
        if key not in self.parts:
            base, suf = (self.walk_name if walk else (self.far_name if far is True else self.name)).split('|')
            self.parts[key] = self.CMB(f"{base}_{key[1]}_{key[2]}{suf}")
        part = self.parts[key]
        base, col = TINT.get(mat, (mat, (1.0, 1.0, 1.0)))
        k = len(part.faces)
        part.poly(pts, base, uv_scale, uv)
        if len(part.faces) > k:
            part.cols.append(col)

    def build(self, collection=None):
        return [m.build(collection) for m in self.parts.values()]


EDGE_BAND = 60.0
WALK = [None]          # walkable centre (local bbox) - lon 17.0950..17.1150, lat 48.1360..48.1485


LIFT = {'pave': 0.3, 'road': 0.42, 'tram': 0.47, 'walk': 0.56}          # above the coarse far terrain
LIFT_WALK = {'pave': 0.08, 'road': 0.12, 'tram': 0.13, 'walk': 0.2}    # walkable centre: every edge <= 0.2 m


def lift(x, y, kind):
    return (LIFT_WALK if in_walk(x, y) else LIFT)[kind]


PASS = {}          # 2 m grid of points on tagged building passages (span reserved on facades)
CUTS = []          # (footprint, datum) of walk-zone houses: terrain cut flat around them
CARRIAGE = {}      # 10 m grid -> (a, b, half width) of motor carriageways
TREES_AT = {}      # walk-zone tree positions (5 m spacing)
DECKS = []         # (a, b, half width) of bridge decks
FORTBV = []        # BVHs of fortress / castle ground meshes
FORTBV_G = []
FENCES = []        # fence segment midpoints (benches keep clear)
RIBS = []          # (a, b, half width) of walk-zone road ribbons: terrain kept under them
GHOSTS = []        # walk-through building outlines (no collision): passage openings drawn on them
FLIGHTS = []       # fortress stair-flight footprints (data/ref/fortress/flight_footprints.json)
HWYW = {}          # 8 m grid -> (x, y, half street width incl. sidewalks)
HWY = {}           # 2 m grid -> sample points along every walkable highway in the walk zone


def _hwy_index(H, misc):
    """Points every 0.75 m along all ways people walk (streets, footways, steps, passages)."""
    srcs = [misc, _load(H, 'street.json')]
    for src in srcs:
        for e in src['elements']:
            t = e.get('tags', {})
            if e['type'] != 'way' or not t.get('highway') or not e.get('geometry'):
                continue
            if (_num(t.get('layer'), 0) or 0) < 0 or t.get('tunnel') in ('yes', 'culvert'):
                continue
            pts = _ring_xy(H, e['geometry'])
            for a, b in zip(pts, pts[1:]):
                if not (in_walk(*a) or in_walk(*b)):
                    continue
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                n = max(1, int(L / 0.75))
                hw = t.get('highway')
                rr = (ROAD_W.get(hw, 4.0) / 2 + 2.6) if hw in ROAD_W and hw not in ('pedestrian',) else \
                    (6.0 if hw == 'pedestrian' and t.get('name') else 3.5)     # named pedestrian streets: wall to wall
                for k in range(n + 1):
                    x, y = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
                    HWY.setdefault((int(x // 2), int(y // 2)), []).append((x, y))
                    if k % 2 == 0:
                        HWYW.setdefault((int(x // 8), int(y // 8)), []).append((x, y, rr))


def _in_street(x, y):
    for gx in (int(x // 8) - 1, int(x // 8), int(x // 8) + 1):
        for gy in (int(y // 8) - 1, int(y // 8), int(y // 8) + 1):
            for px, py, rr in HWYW.get((gx, gy), ()):
                if (px - x) ** 2 + (py - y) ** 2 < rr * rr:
                    return True
    return False


def _passage_edge(a, b, ghost=False):
    """Does a passage (tagged, or any walk line through a walk-through shell) cross this facade edge?"""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for k in range(int(L / 0.7) + 1):
        x, y = a[0] + (b[0] - a[0]) * k * 0.7 / max(L, 1e-6), a[1] + (b[1] - a[1]) * k * 0.7 / max(L, 1e-6)
        for px, py in PASS.get((int(x // 2), int(y // 2)), ()):
            if (px - x) ** 2 + (py - y) ** 2 < 1.0:
                return True
        if ghost and _hwy_near(x, y, 0.8):
            return True
    return False


def _clip_cell_to_street(*corners):
    """Cell (CCW corners) intersected with the street band: walk the edges in 0.5 m steps, keep inside
    points and bisect the in/out transitions (the band edge cuts the cell)."""
    out = []
    n = len(corners)
    for i in range(n):
        a, b = corners[i], corners[(i + 1) % n]
        steps = 2
        prev = None
        for k in range(steps):
            t = k / steps
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            ins = _in_street(*p)
            if prev is not None and ins != prev[1]:
                lo, hi = prev[0], p
                for _ in range(6):
                    mid = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
                    if _in_street(*mid) == prev[1]:
                        lo = mid
                    else:
                        hi = mid
                out.append(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2))
            if ins:
                out.append(p)
            prev = (p, ins)
        # transition at the corner b
        if prev is not None and _in_street(*b) != prev[1]:
            lo, hi = prev[0], b
            for _ in range(6):
                mid = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
                if _in_street(*mid) == prev[1]:
                    lo = mid
                else:
                    hi = mid
            out.append(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2))
    return out


def _hwy_hits(poly, pip):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    for gx in range(int(min(xs) // 2), int(max(xs) // 2) + 1):
        for gy in range(int(min(ys) // 2), int(max(ys) // 2) + 1):
            for x, y in HWY.get((gx, gy), ()):
                if pip(x, y, poly):
                    return True
    return False


def _hwy_near(x, y, r):
    for gx in range(int((x - r) // 2), int((x + r) // 2) + 1):
        for gy in range(int((y - r) // 2), int((y + r) // 2) + 1):
            for px, py in HWY.get((gx, gy), ()):
                if (px - x) ** 2 + (py - y) ** 2 < r * r:
                    return True
    return False


PRECINCT = [None, None]     # (castle precinct polygon offset outward, point_in_poly)


def in_precinct(x, y):
    poly, pip = PRECINCT
    return poly is not None and pip(x, y, poly)


def in_walk(x, y):
    w = WALK[0]
    return w is not None and w[0] < x < w[2] and w[1] < y < w[3]


def _edge_blend(T, x, y, zfar):
    """Just outside the detailed-terrain box the coarse far DMR can sit metres off the lidar terrain
    (steep castle-hill foot, the SNP ramp): blend from the detailed edge height to the far DMR over 60 m."""
    if getattr(T, 'cz', None) is not None:      # surveyed area = castle grid + centre tier (union box)
        bx0, by0, bx1, by1 = min(T.x0, T.cx0), min(T.y0, T.cy0), max(T.x1, T.cx1), max(T.y1, T.cy1)
    else:
        bx0, by0, bx1, by1 = T.x0, T.y0, T.x1, T.y1
    cx_ = min(max(x, bx0 + 5), bx1 - 5)
    cy_ = min(max(y, by0 + 5), by1 - 5)
    dd = math.hypot(x - cx_, y - cy_)
    if dd >= EDGE_BAND:
        return zfar
    k = dd / EDGE_BAND
    k = k * k * (3 - 2 * k)
    return (T.h(cx_, cy_) - 0.3) * (1 - k) + zfar * k


class Ground:
    """Displayed terrain height: detailed terrain inside its bbox, sunk far DMR outside."""

    def __init__(self, H, T):
        self.T = T
        self.zf, self.zmin = H['far_height'](T)
        self.V = H['Vector']
        self.DOWN = H['Vector']((0, 0, -1))

    def inside(self, x, y):
        T = self.T
        if hasattr(T, 'covers'):                  # detailed DMR incl. the walkable centre (dmr_centre.json)
            return T.covers(x, y)
        return T.x0 + 4 < x < T.x1 - 4 and T.y0 + 4 < y < T.y1 - 4

    def attach_meshes(self, names):
        """Sample the actual collidable terrain meshes (they are lowered under paving etc.), so walk
        surfaces sit exactly on what the player stands on."""
        import bpy
        from mathutils.bvhtree import BVHTree
        dg = bpy.context.evaluated_depsgraph_get()
        self.bvh = [BVHTree.FromObject(bpy.data.objects[n], dg) for n in names if bpy.data.objects.get(n)]

    def __call__(self, x, y):
        if self.inside(x, y):
            if getattr(self, 'bvh', None):
                best = None
                for b in self.bvh:
                    hit = b.ray_cast(self.V((x, y, 800.0)), self.DOWN)
                    if hit[0] is not None and (best is None or hit[0].z > best):
                        best = hit[0].z
                if best is not None:
                    return best
            return self.T.h(x, y)
        return _edge_blend(self.T, x, y, self.zf(x, y) - 1.5)

    @property
    def water(self):
        return self.zmin - 1.5 + 0.5


SHOPFRONTS = []     # (a, b, ground, tiles) of every shop storey: awnings / signs / steps in _shop_dressing
SHOP_H = 3.8         # shop storey height (shop window + fascia) on Old Town pedestrian streets
SHOP_W = 6.4         # one shop texture tile = shop window bay + door bay


PRIORITY_STREETS = ('Michalská', 'Ventúrska', 'Panská', 'Hlavné námestie', 'Rudnayovo námestie', 'Zámocká',
                    'Beblavého', 'Kapitulská', 'Františkánske námestie', 'Laurinská', 'Sedlárska', 'Rybárska brána',
                    'Primaciálne námestie', 'Židovská', 'Mikulášska', 'Hviezdoslavovo námestie', 'Biela', 'Zelená')
PRIO = {}
MAINR = {}      # main roads + embankment (tree detail only, not facade trims)


def _prio_index(H, misc):
    for e in misc['elements']:
        t = e.get('tags', {})
        prio = t.get('name', '').startswith(PRIORITY_STREETS)
        main = 'nábrežie' in t.get('name', '') or t.get('highway') in ('primary', 'secondary', 'trunk')
        if e['type'] == 'way' and e.get('geometry') and (prio or main):
            idx = PRIO if prio else MAINR
            pts = _ring_xy(H, e['geometry'])
            for a, b in zip(pts, pts[1:]):
                for gx in range(int(min(a[0], b[0]) // 20) - 1, int(max(a[0], b[0]) // 20) + 2):
                    for gy in range(int(min(a[1], b[1]) // 20) - 1, int(max(a[1], b[1]) // 20) + 2):
                        idx.setdefault((gx, gy), []).append((a, b))


def _prio_near(x, y, r):
    """Distance test to the walk routes / main streets (priority streets + main roads index)."""
    for gx in range(int((x - r) // 20), int((x + r) // 20) + 1):
        for gy in range(int((y - r) // 20), int((y + r) // 20) + 1):
            for p, q in PRIO.get((gx, gy), []) + MAINR.get((gx, gy), []):
                dx, dy = q[0] - p[0], q[1] - p[1]
                l2 = dx * dx + dy * dy or 1e-9
                k = max(0.0, min(1.0, ((x - p[0]) * dx + (y - p[1]) * dy) / l2))
                if math.hypot(x - p[0] - k * dx, y - p[1] - k * dy) < r:
                    return True
    return False


def _faces_priority(a, b):
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for p, q in PRIO.get((int(m[0] // 20), int(m[1] // 20)), ()):
        dx, dy = q[0] - p[0], q[1] - p[1]
        l2 = dx * dx + dy * dy
        if l2 < 1e-6:
            continue
        s_ = max(0.0, min(1.0, ((m[0] - p[0]) * dx + (m[1] - p[1]) * dy) / l2))
        if math.hypot(m[0] - p[0] - s_ * dx, m[1] - p[1] - s_ * dy) < 14.0 and \
                abs((b[0] - a[0]) * dx + (b[1] - a[1]) * dy) / (L * math.sqrt(l2)) > 0.7:
            return True
    return False


def _window_trims(H, mb, a, b, zb, z1, ground, fh, g_street=None):
    """Route-facing facade relief matching the window texture (bay 3.2 m, window 0.36-0.68 of the bay,
    0.22-0.72 of the storey): projecting sills, moulded hoods, slim jambs."""
    Vector, seg_box = H['Vector'], H['seg_box']
    A, B = Vector(a), Vector(b)
    L = (B - A).length
    nb = max(1, round(L / FLOOR_H))
    bw = L / nb
    d = (B - A) / L
    k0 = int(math.ceil((zb - ground) / fh - 0.2))
    g0_floor = ground + fh * math.ceil((g_street + 0.6 * fh - ground) / fh) if g_street is not None else -1e9
    k1 = int((z1 - ground) / fh - 0.75)
    m = (A + B) / 2
    if math.hypot(m.x - SQUARE_C[0], m.y - SQUARE_C[1]) < SQUARE_R + 25 or (470 < m.x < 510 and 170 < m.y < 300):
        for j in range(nb + 1):                    # bay rhythm: pilaster strips between the window axes
            c_ = A + d * (bw * j)
            seg_box(mb, c_ - d * 0.22, c_ + d * 0.22, -0.12, 0.02, zb, z1 - 0.5, 'plaster')
        seg_box(mb, A, B, -0.18, 0.02, ground + fh - 0.25, ground + fh, 'plaster')      # first-floor string course
    for k in range(max(0, k0), k1 + 1):
        zs, zl = ground + (k + 0.22) * fh, ground + (k + 0.74) * fh
        if zs < zb or zl > z1 or ground + k * fh < zb - 0.05 or zs < g0_floor:
            continue                              # (stretched ground floor: no trims)
        for j in range(nb):
            c0, c1 = A + d * (bw * (j + 0.29)), A + d * (bw * (j + 0.71))
            seg_box(mb, c0 - d * 0.08, c1 + d * 0.08, -0.16, 0.02, zs - 0.09, zs, 'plaster')            # sill
            seg_box(mb, c0 - d * 0.12, c1 + d * 0.12, -0.12, 0.02, zl, zl + 0.16, 'plaster')            # hood



def _facade(H, mb, pts, z0, z1, wmat, ground, shop=None, G=None, fh=FLOOR_H, trims=False, plinth=None, row=None, ghost=False):
    """Walls with explicit UVs so the window texture lines up with storeys (1 bay = 3.2 m).
    shop(a, b) -> True puts a shop-front ground storey on that edge (needs the per-point ground G)."""
    Vector = H['Vector']
    n = len(pts)
    if plinth is not None and G is not None:
        # frontages along a sloping street: split into ~6.4 m bays, each with its own (stepped) plinth level;
        # burgher-house rows (row = rng): street fronts split into 6-10 m houses, own colour + eave height
        sp = []
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            houses = row is not None and L > 11.0 and \
                _hwy_near((a[0] + b[0]) / 2 + (b[1] - a[1]) / L * 5, (a[1] + b[1]) / 2 - (b[0] - a[0]) / L * 5, 6.0)
            if houses:
                k = max(2, int(round(L / row.uniform(6.5, 9.5))))
            else:
                k = max(1, int(L / 6.4)) if abs(G(*a) - G(*b)) > 0.4 else 1
            for j in range(k):
                wm_, att = wmat, 0.0
                if houses:
                    names = list(OLD_TOWN_WEIGHTS)
                    wm_ = row.choices(names, weights=[OLD_TOWN_WEIGHTS[q] for q in names])[0].replace('v2_wall_', 'v2_narrow_')
                    att = row.choice((0.0, 0.0, 0.5, 0.9, 1.3))
                sp.append(((a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k),
                           (a[0] + (b[0] - a[0]) * (j + 1) / k, a[1] + (b[1] - a[1]) * (j + 1) / k), wm_, att))
    else:
        sp = [(pts[i], pts[(i + 1) % n], wmat, 0.0) for i in range(n)]
    wmat0 = wmat
    for a, b, wmat, att in sp:
        if att > 0:                               # this house's eaves stand higher: attic band + cornice
            mb.poly([Vector((a[0], a[1], z1)), Vector((b[0], b[1], z1)), Vector((b[0], b[1], z1 + att)), Vector((a[0], a[1], z1 + att))],
                    wmat, uv=[(0, 0.04), (1, 0.04), (1, 0.06), (0, 0.06)])
            H['seg_box'](mb, a, b, -0.3, 0.02, z1 + att - 0.3, z1 + att, 'plaster')
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 0.05:
            continue
        nb = max(1, round(L / FLOOR_H))
        u1 = float(nb)
        zb = z0
        psg = L > 2.0 and _passage_edge(a, b, ghost)            # passage span reserved: no shop / trims here
        if shop is not None and L > 3.0 and z0 < ground + 0.5 and not psg and shop(a, b):
            gs = max(G(*a), G(*b)) + 0.2 if plinth is not None else min(G(*a), G(*b))
            zs = gs + SHOP_H
            if zs < z1 - 2.0:
                us = float(max(1, round(L / SHOP_W)))
                zf = z0
                if plinth is not None and gs - 0.02 > z0:     # sloping street: stepped plinth under the shop
                    mb.poly([Vector((a[0], a[1], z0)), Vector((b[0], b[1], z0)), Vector((b[0], b[1], gs)), Vector((a[0], a[1], gs))],
                            plinth, uv=[(0, 0), (L / 2.0, 0), (L / 2.0, (gs - z0) / 2.0), (0, (gs - z0) / 2.0)])
                    zf = gs
                vs0 = (zf - gs) / SHOP_H
                q = [Vector((a[0], a[1], zf)), Vector((b[0], b[1], zf)), Vector((b[0], b[1], zs)), Vector((a[0], a[1], zs))]
                mb.poly(q, wmat.replace('v2_narrow_', 'v2_wall_').replace('v2_wall_', 'v2_shop_'), uv=[(0, vs0), (us, vs0), (us, 1.0), (0, 1.0)])
                SHOPFRONTS.append((a, b, gs, int(us)))
                zb = zs
        if plinth is not None and zb == z0 and G is not None:
            # stone plinth up to the local ground of this edge (+0.3 m): on a slope it steps with the street
            mo = ((a[0] + b[0]) / 2 + (b[1] - a[1]) / L * 0.8, (a[1] + b[1]) / 2 - (b[0] - a[0]) / L * 0.8)
            zp = max(G(*a), G(*b), G(*mo)) + 0.5       # (+ sidewalk lift / kerb)
            if zp > zb + 0.05:
                mb.poly([Vector((a[0], a[1], zb)), Vector((b[0], b[1], zb)), Vector((b[0], b[1], zp)), Vector((a[0], a[1], zp))],
                        plinth, uv=[(0, 0), (L / 2.0, 0), (L / 2.0, (zp - zb) / 2.0), (0, (zp - zb) / 2.0)])
                zb = zp
        # storeys counted down from the eaves: whole window rows under the cornice, any leftover at the base
        gadj = z1 - max(1, round((z1 - ground) / fh)) * fh if z1 - ground > fh else ground
        v0, v1 = (zb - gadj) / fh, (z1 - gadj) / fh
        # top of the ground floor: first storey line at least 0.6 storey above the street
        zs = gadj + fh * math.ceil((ground + 0.6 * fh - gadj) / fh)
        if zb < zs < z1 - 0.5 and 0.03 < abs((zs - zb) / fh - 1.0) < 0.6 and zb < ground + 0.5:
            # the leftover height goes into a taller ground floor: one whole storey stretched over zb..zs
            q = [Vector((a[0], a[1], zb)), Vector((b[0], b[1], zb)), Vector((b[0], b[1], zs)), Vector((a[0], a[1], zs))]
            mb.poly(q, wmat, uv=[(0, 0.0), (u1, 0.0), (u1, 1.0), (0, 1.0)])
            q = [Vector((a[0], a[1], zs)), Vector((b[0], b[1], zs)), Vector((b[0], b[1], z1)), Vector((a[0], a[1], z1))]
            mb.poly(q, wmat, uv=[(0, 1.0), (u1, 1.0), (u1, v1), (0, v1)])
        else:
            q = [Vector((a[0], a[1], zb)), Vector((b[0], b[1], zb)), Vector((b[0], b[1], z1)), Vector((a[0], a[1], z1))]
            mb.poly(q, wmat, uv=[(0, v0), (u1, v0), (u1, v1), (0, v1)])
        if False and plinth is not None and wmat in TINT and z1 - zb > 2.0 and L > 3.0 and \
                _hwy_near((a[0] + b[0]) / 2 + (b[1] - a[1]) / L * 4, (a[1] + b[1]) / 2 - (b[0] - a[0]) / L * 4, 4.0):
            # grime: splash band above the plinth (opaque, 1 cm proud, darker tint of the same wall)
            gname = wmat + '~grime'
            if gname not in TINT:
                base_, col_ = TINT[wmat]
                TINT[gname] = (base_, tuple(c_ * 0.8 for c_ in col_))
            o_ = Vector(((b[1] - a[1]) / L, -(b[0] - a[0]) / L)) * 0.01
            mb.poly([Vector((a[0] + o_.x, a[1] + o_.y, zb)), Vector((b[0] + o_.x, b[1] + o_.y, zb)),
                     Vector((b[0] + o_.x, b[1] + o_.y, zb + 0.45)), Vector((a[0] + o_.x, a[1] + o_.y, zb + 0.45))],
                    gname, uv=[(0.02, 0.02), (0.08, 0.02), (0.08, 0.05), (0.02, 0.05)])
        if trims and L > 3.0 and not psg and not wmat.startswith('v2_narrow') and _faces_priority(a, b):
            _window_trims(H, mb, a, b, zb, z1, gadj, fh, ground)


SHOP_CENTRE, SHOP_R = (600.0, 140.0), 480.0     # Hlavne namestie; covers Michalska / Venturska / Panska


def _shop_streets(H, misc):
    """Predicate: facade edge runs along an Old Town pedestrian street -> shop-front ground storey."""
    grid = {}
    for e in misc['elements']:
        t = e.get('tags', {})
        if e['type'] != 'way' or t.get('highway') not in ('pedestrian', 'living_street') or not e.get('geometry'):
            continue
        pts = _ring_xy(H, e['geometry'])
        for a, b in zip(pts, pts[1:]):
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if math.hypot(m[0] - SHOP_CENTRE[0], m[1] - SHOP_CENTRE[1]) > SHOP_R + 50:
                continue
            for gx in range(int(min(a[0], b[0]) // 20) - 1, int(max(a[0], b[0]) // 20) + 2):
                for gy in range(int(min(a[1], b[1]) // 20) - 1, int(max(a[1], b[1]) // 20) + 2):
                    grid.setdefault((gx, gy), []).append((a, b))

    def shop(a, b):
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if math.hypot(m[0] - SHOP_CENTRE[0], m[1] - SHOP_CENTRE[1]) > SHOP_R:
            return False
        if math.hypot(m[0], m[1]) < PODHRADIE_R and math.hypot(m[0] - SHOP_CENTRE[0], m[1] - SHOP_CENTRE[1]) > 260:
            return False                          # Podhradie is residential: windows + doors, not shopfronts
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        for p, q in grid.get((int(m[0] // 20), int(m[1] // 20)), ()):
            dx, dy = q[0] - p[0], q[1] - p[1]
            l2 = dx * dx + dy * dy
            if l2 < 1e-6:
                continue
            s_ = max(0.0, min(1.0, ((m[0] - p[0]) * dx + (m[1] - p[1]) * dy) / l2))
            if math.hypot(m[0] - p[0] - s_ * dx, m[1] - p[1] - s_ * dy) < 11.0 and \
                    abs((b[0] - a[0]) * dx + (b[1] - a[1]) * dy) / (L * math.sqrt(l2)) > 0.75:
                return True
        return False
    return shop


def _roof_dressing(H, mb, r, z, rh, rmat, wmat, rng):
    """Walk-zone pitched roofs: one row of small dormers (every other bay) on street-facing slopes -
    zinc cheeks, white-framed window - and 1-2 rendered chimneys on the ridge line, often paired."""
    Vector, seg_box = H['Vector'], H['seg_box']
    slope = 0.75                          # = _roof_field slope; eaves 0.45 m out and 0.25 m below the wall top
    z = z - 0.25 + slope * 0.45
    for a, b in zip(r, r[1:] + r[:1]):
        A, B = Vector(a), Vector(b)
        L = (B - A).length
        if L < 6.0 or not (_faces_priority(a, b) or (math.hypot(a[0], a[1]) < PODHRADIE_R and
                                                     _hwy_near((a[0] + b[0]) / 2 + (b[1] - a[1]) / L * 6, (a[1] + b[1]) / 2 - (b[0] - a[0]) / L * 6, 7.0))):
            continue
        d = (B - A) / L
        inn = Vector((-d.y, d.x))                 # CCW: interior on the left
        off = 1.2
        zb = z + slope * off - 0.3
        if zb + 1.3 > z + rh - 0.4:
            continue
        nd = int((L - 3.0) // 3.2)
        for k in range(0, nd, 2):                 # every other window axis
            c = A + d * (2.0 + (k + 0.5) * (L - 4.0) / nd) + inn * off
            w, hgt = 0.45, 1.05
            seg_box(mb, c - d * w, c + d * w, 0.0, 1.0, zb, zb + hgt, 'v2_slate')        # zinc-clad cheeks + front
            zt = zb + hgt
            f0, f1 = c - d * (w + 0.08), c + d * (w + 0.08)
            for p0_, p1_ in ((f0, c), (c, f1)):
                q = [Vector((*p0_, zt if p0_ is not c else zt + 0.5)), Vector((*p1_, zt if p1_ is not c else zt + 0.5)),
                     Vector((*(p1_ + inn * 1.1), zt if p1_ is not c else zt + 0.5)), Vector((*(p0_ + inn * 1.1), zt if p0_ is not c else zt + 0.5))]
                if (q[1] - q[0]).cross(q[3] - q[0]).z < 0:
                    q.reverse()
                mb.poly(q, rmat)
            mb.poly([Vector((*(c - d * 0.36 - inn * 0.02), zb + 0.12)), Vector((*(c + d * 0.36 - inn * 0.02), zb + 0.12)),
                     Vector((*(c + d * 0.36 - inn * 0.02), zt - 0.08)), Vector((*(c - d * 0.36 - inn * 0.02), zt - 0.08))], 'plaster')   # white frame
            mb.poly([Vector((*(c - d * 0.28 - inn * 0.03), zb + 0.2)), Vector((*(c + d * 0.28 - inn * 0.03), zb + 0.2)),
                     Vector((*(c + d * 0.28 - inn * 0.03), zt - 0.16)), Vector((*(c - d * 0.28 - inn * 0.03), zt - 0.16))], 'glass')
    # chimneys: rendered stacks on the ridge line (centroid axis), one or a pair, 0.6 m above the ridge
    cx = sum(p[0] for p in r) / len(r)
    cy = sum(p[1] for p in r) / len(r)
    pp = H['point_in_poly']
    xs, ys = [p[0] for p in r], [p[1] for p in r]
    along = (max(xs) - min(xs)) >= (max(ys) - min(ys))
    n = rng.choice((1, 2, 2))
    ridge = min(rh, slope * 0.5 * H['min_width'](r)) * 0.85    # field-roof ridge height above the eaves (conservative)
    for k in range(n):
        f = (k - (n - 1) / 2) * 0.5
        x = cx + (f * (max(xs) - min(xs)) if along else 0.0)
        y = cy + (0.0 if along else f * (max(ys) - min(ys)))
        if pp(x, y, r):
            loc = min(ridge, slope * _edge_dist(x, y, r)) - 0.15      # roof surface at the stack (field roof)
            top_ = z + loc + 0.8
            mb.box([(x - 0.45, y - 0.35), (x + 0.45, y - 0.35), (x + 0.45, y + 0.35), (x - 0.45, y + 0.35)], z, top_, 'v2_render_ochre')
            mb.box([(x - 0.53, y - 0.43), (x + 0.53, y - 0.43), (x + 0.53, y + 0.43), (x - 0.53, y + 0.43)], top_, top_ + 0.12, 'v2_stone_church')


def _seg_cross(p1, p2, p3, p4):
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return o(p1, p2, p3) * o(p1, p2, p4) < 0 and o(p3, p4, p1) * o(p3, p4, p2) < 0


def _house_doors(H, mb, r, G, shop, fh):
    """Street-facing walls without a shop front: one entrance per facade (panelled door in a stone
    surround, transom) at the plinth level, with stone steps down to the street where the plinth is high."""
    Vector, seg_box = H['Vector'], H['seg_box']
    for a, b in zip(r, r[1:] + r[:1]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 5.0:
            continue
        nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L          # outward (CCW ring)
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if not _hwy_near(mx + nx * 5, my + ny * 5, 6.0) or (shop is not None and shop(a, b)):
            continue
        A, B = Vector(a), Vector(b)
        d = (B - A) / L
        out = Vector((nx, ny))
        nb_ = max(1, round(L / FLOOR_H))
        c = A + d * (L / nb_ * max(1, nb_ // 2))                  # on a bay boundary: between two window axes
        mo = (mx + nx * 0.8, my + ny * 0.8)
        zp = max(G(*a), G(*b), G(*mo)) + 0.5                    # plinth top (= ground-floor level)
        gz = G(c.x + out.x * 0.5, c.y + out.y * 0.5)
        n0 = int((zp - gz) / 0.16)
        if zp - gz > 0.96 or (n0 > 0 and (_hwy_near(c.x + out.x * (0.3 * n0), c.y + out.y * (0.3 * n0), 1.0) or
                                          _near_flight(c.x + out.x * (0.3 * n0), c.y + out.y * (0.3 * n0), 1.5))):
            zp = gz + 0.16                                      # no room / too many risers: door at street level
        dz = c + out * 0.04
        mb.poly([Vector((*(dz - d * 0.6), zp)), Vector((*(dz + d * 0.6), zp)), Vector((*(dz + d * 0.6), zp + 2.3)),
                 Vector((*(dz - d * 0.6), zp + 2.3))], 'frame')
        mb.poly([Vector((*(dz - d * 0.6), zp + 2.4)), Vector((*(dz + d * 0.6), zp + 2.4)), Vector((*(dz + d * 0.6), zp + 2.85)),
                 Vector((*(dz - d * 0.6), zp + 2.85))], 'glass')
        for sgn in (-1, 1):                                       # stone surround
            seg_box(mb, c + d * (0.6 * sgn) - d * 0.12, c + d * (0.6 * sgn) + d * 0.12, -0.12, 0.0, zp, zp + 2.95, 'v2_stone_church')
        seg_box(mb, c - d * 0.8, c + d * 0.8, -0.14, 0.0, zp + 2.95, zp + 3.15, 'v2_stone_church')
        n = int(round((zp - gz) / 0.16))
        if 0 < n <= 6:
            for k in range(n):                                    # 16 cm risers, 30 cm treads
                seg_box(mb, c - d * 0.8, c + d * 0.8, -(0.3 * (n - k)), 0.0, gz - 0.2, zp - 0.16 * (k + 1) + 0.16, 'v2_stone_church')


def _near_flight(x, y, pad=2.0):
    for f in FLIGHTS:
        xs, ys = [q[0] for q in f], [q[1] for q in f]
        if min(xs) - pad < x < max(xs) + pad and min(ys) - pad < y < max(ys) + pad:
            if _pip(x, y, f) or _edge_dist(x, y, f) < pad:
                return True
    return False


def _concave(r):
    """Any reflex corner (CCW ring) -> the inset roof would fold; use the distance-field roof instead."""
    n = len(r)
    for i in range(n):
        a, b, c = r[i - 1], r[i], r[(i + 1) % n]
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) < -1e-6:
            return True
    return False


def _eaves(H, r, cx, cy, over=0.45):
    """Walk zone: pitched roofs overhang the walls by ~0.45 m (eaves read from the street)."""
    if not in_walk(cx, cy):
        return r
    try:
        e = [(v.x, v.y) for v in H['offset_poly'](r, over)]
    except ZeroDivisionError:
        return r
    if len(e) != len(r) or abs(_area(e)) < abs(_area(r)) or \
            any(math.hypot(e[i][0] - r[i][0], e[i][1] - r[i][1]) > 3 * over for i in range(len(r))):
        return r
    n = len(e)
    if any(_seg_cross(e[i], e[(i + 1) % n], e[j], e[(j + 1) % n]) for i in range(n) for j in range(i + 2, n)
           if not (i == 0 and j == n - 1)):
        return r                                  # concave outline: offset would fold, keep the wall line
    return e


def _roof(H, mb, r, z, h, shape, mat):
    """Hipped/gabled roofs for any outline (the shared roof_generic turns > 12-vertex outlines into
    one big pyramid): inset the eave line, retrying smaller insets until the ridge outline is simple,
    else fall back to a low mansard band around a flat top."""
    Vector = H['Vector']
    if shape in ('pyramidal', 'dome', 'onion', 'cone'):
        c = Vector((sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r), z + h))
        for a, b in zip(r, r[1:] + r[:1]):
            mb.poly([Vector((a[0], a[1], z)), Vector((b[0], b[1], z)), c], mat)
        return
    inset = min(h / 1.1, 0.45 * H['min_width'](r))
    zt = z + h
    for _ in range(4):
        try:
            inn = [(v.x, v.y) for v in H['offset_poly'](r, -inset)]
        except ZeroDivisionError:
            inn = None
        n = len(r)
        ok = inn is not None and len(inn) == n and _area(inn) > 0.5 and \
            all(math.hypot(inn[i][0] - r[i][0], inn[i][1] - r[i][1]) < 3 * inset for i in range(n))
        if ok:
            ok = not any(_seg_cross(inn[i], inn[(i + 1) % n], inn[j], inn[(j + 1) % n])
                         for i in range(n) for j in range(i + 2, n) if not (i == 0 and j == n - 1))
        if ok:
            for i in range(n):
                a, b = r[i], r[(i + 1) % n]
                c, d = inn[(i + 1) % n], inn[i]
                mb.poly([Vector((a[0], a[1], z)), Vector((b[0], b[1], z)), Vector((c[0], c[1], zt)), Vector((d[0], d[1], zt))], mat)
            _cap(H, mb, inn, zt, mat)
            return
        inset *= 0.5
        zt = z + h * (0.5 if _ < 2 else 0.3)
    _cap(H, mb, r, z + 0.3, 'v2_roof_grey')


HOLES = {}
FIELD_ROOF_R = 1000.0


def _cap_holes(H, mb, loops, z, mat):
    Vector, geometry = H['Vector'], H['geometry']
    flat = [p for lp in loops for p in lp]
    for t in geometry.tessellate_polygon([[(p[0], p[1], 0) for p in lp] for lp in loops]):
        q = [Vector((flat[i][0], flat[i][1], z)) for i in t]
        if geometry.normal(q).z < 0:
            q.reverse()
        mb.poly(q, mat)


def _roof_field(H, mb, loops, z, hmax, mat, slope=0.84):
    """Roof surface z = eave + min(slope * distance-to-eave, hmax) over the footprint (a straight-skeleton
    roof for any outline, courtyards included): ridges, hips and valleys of complex blocks come out by
    themselves instead of one inset cap. Constrained Delaunay of the densified eaves + interior grid."""
    Vector, geometry = H['Vector'], H['geometry']
    pp = H['point_in_poly']
    outer = loops[0]
    area = abs(_area(outer))
    sp = max(1.6, min(4.0, math.sqrt(area) / 8.0))
    segs = [(lp[i], lp[(i + 1) % len(lp)]) for lp in loops for i in range(len(lp))]

    def dist(x, y):
        best = 1e9
        for a, b in segs:
            dx, dy = b[0] - a[0], b[1] - a[1]
            l2 = dx * dx + dy * dy
            k = 0.0 if l2 < 1e-9 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
            dd = math.hypot(x - a[0] - k * dx, y - a[1] - k * dy)
            if dd < best:
                best = dd
        return best
    verts, faces = [], []
    for lp in loops:
        loop = []
        for i in range(len(lp)):
            a, b = lp[i], lp[(i + 1) % len(lp)]
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / sp))
            for k in range(n):
                loop.append(len(verts))
                verts.append(Vector((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)))
        faces.append(loop)
    xs, ys = [p[0] for p in outer], [p[1] for p in outer]
    y = min(ys) + sp / 2
    while y < max(ys):
        x = min(xs) + sp / 2 + (sp / 2 if int((y - min(ys)) / sp) % 2 else 0)
        while x < max(xs):
            if pp(x, y, outer) and not any(pp(x, y, hl) for hl in loops[1:]) and dist(x, y) > 0.45 * sp:
                verts.append(Vector((x, y)))
            x += sp
        y += sp
    try:
        out = geometry.delaunay_2d_cdt(verts, [], faces, 2, 1e-5)
    except Exception:
        _cap_holes(H, mb, loops, z, mat)
        return
    ov, of = out[0], out[2]
    zs = [z + min(slope * dist(v.x, v.y), hmax) for v in ov]
    for f in of:
        q = [Vector((ov[i].x, ov[i].y, zs[i])) for i in f]
        if geometry.normal(q).z < 0:
            q.reverse()
        mb.poly(q, mat)


def _cap(H, mb, pts, z, mat):
    Vector, geometry = H['Vector'], H['geometry']
    tris = geometry.tessellate_polygon([[(p[0], p[1], 0) for p in pts]])
    for t in tris:
        q = [Vector((pts[i][0], pts[i][1], z)) for i in t]
        if geometry.normal(q).z < 0:
            q.reverse()
        mb.poly(q, mat)


OLD_TOWN_HALL, PRIMATE_PALACE, CATHEDRAL = 146009, 189440, 16609274
SND, REDUTA, CARLTON = 34571529, 56305202, 56341131
FRANCISCAN, CLARISSE, BLUE_CHURCH, ST_NICHOLAS = 38539540, 39259061, 75070305, 243353518
DECOR = {}
LANDMARK_IDS = (243293986, 39391573, 123233334, 123233335, 378574918, 34571529, 56305202)   # + SND, Reduta (v2_landmarks)


VYDRICA_LEVELS = {1134986882: 6, 1134986884: 6, 1310712769: 6, 1310712776: 5}
OLD_TOWN_R = 450.0
OLD_FLOOR_H = 3.7


def _infer_levels(ix, cx, cy, area, core):
    """Untagged footprints: median storeys of tagged neighbours within 60 m (small annexes 1-2)."""
    if area < 40:
        return 1
    near = sorted(lv for gx in (-1, 0, 1) for gy in (-1, 0, 1)
                  for x, y, lv in ix.get((int(cx // 60) + gx, int(cy // 60) + gy), ())
                  if math.hypot(x - cx, y - cy) < 60)
    if len(near) >= 3:
        return near[len(near) // 2] if area > 120 else max(1, near[len(near) // 2] - 1)
    return 3 if core else 2


def _buildings(H, data, G, coll, rng, shop=None, near_ok=None):
    ChunkMB, roof_generic = H['ChunkMB'], H['roof_generic']
    walls = roofs = far_walls = VChunk(H, 'V2City_Bld|', 'V2City_BldFar|', walk_name='V2City_BldWalk|-col')
    # Podhradie ring below the castle (R_NEAR..R_MIN) replaces the V1 build_city boxes; walkable -> -col
    near = VChunk(H, 'V2City_Podhradie|-col', 'V2City_Podhradie|-col', 400.0, 400.0)
    # footprints a mapped street / footway / passage runs through (OSM offsets, building passages):
    # drawn, but without collision so the walk routes stay open
    ghost = VChunk(H, 'V2City_BldPass|', 'V2City_BldPass|', 400.0, 400.0)
    n_ghost = 0
    items = []
    for e in data['elements']:
        t = e.get('tags', {})
        if e['type'] == 'way' and e.get('geometry'):
            rings = [_ring_xy(H, e['geometry'])]
        elif e['type'] == 'relation':
            rings = _assemble(H, e.get('members', []))
        else:
            continue
        inners = []
        if e['type'] == 'relation':
            inners = [q for q in (_clean(q) for q in _assemble(H, e.get('members', []), 'inner')) if len(q) >= 3 and abs(_area(q)) > 15]
        for r in rings:
            r = _clean(r)
            if len(r) < 3 or abs(_area(r)) < 4:
                continue
            cx = sum(p[0] for p in r) / len(r)
            cy = sum(p[1] for p in r) / len(r)
            hs_ = [q for q in inners if H['point_in_poly'](q[0][0], q[0][1], r)]
            if hs_:
                HOLES[(e['id'], round(cx), round(cy))] = hs_
            items.append((e, t, r, cx, cy))
    parts = [(cx, cy, abs(_area(r))) for e, t, r, cx, cy in items if 'building:part' in t]
    outl = {}
    for e, t, r, cx, cy in items:
        if 'building:part' not in t and t.get('building'):
            for gx in range(int(min(p[0] for p in r) // 30), int(max(p[0] for p in r) // 30) + 1):
                for gy in range(int(min(p[1] for p in r) // 30), int(max(p[1] for p in r) // 30) + 1):
                    outl.setdefault((gx, gy), []).append((e['id'], r, abs(_area(r))))
    levels_ix = {}
    for e, t, r, cx, cy in items:
        lv_ = _num(t.get('building:levels'))
        if lv_ and 'building:part' not in t:
            levels_ix.setdefault((int(cx // 60), int(cy // 60)), []).append((cx, cy, lv_))
    pp = H['point_in_poly']
    count = 0
    special = {}
    for e, t, r, cx, cy in items:
        dist = math.hypot(cx, cy)
        if dist > R_BUILD or dist < R_NEAR:
            continue
        if dist < R_MIN:
            if near_ok is None or not near_ok(e['id'], cx, cy):
                continue
            H['REPLACED_IDS'].add(e['id'])
            walls = roofs = near
        else:
            walls = roofs = far_walls
        if in_walk(cx, cy) and _hwy_hits(r, pp):
            if any(any(pp(q[0], q[1], r) for q in f) or any(pp(q[0], q[1], f) for q in r) for f in FLIGHTS):
                continue                          # sits on a fortress stair flight: the stairs win
            walls = roofs = ghost
            n_ghost += 1
            GHOSTS.append(r)
        if t.get('building') in ('roof', 'carport', 'construction') or t.get('location') == 'underground':
            continue
        if dist > R_DETAIL:
            if abs(_area(r)) < 12 and e['id'] not in LANDMARK_IDS:
                continue                  # sheds, chimneys, tiny parts: invisible from the castle
            r = _simplify(r, 0.6 if dist < 1000 else 2.0)
        if 'building:part' not in t and t.get('building'):
            covered = sum(pa for px, py, pa in parts if abs(px - cx) < 120 and abs(py - cy) < 120 and pp(px, py, r))
            if covered > 0.6 * abs(_area(r)):
                continue                  # drawn by its parts (outline kept when parts cover only a tower etc.)
        if 'building:part' not in t and in_walk(cx, cy) and e['id'] not in LANDMARK_IDS and e['id'] not in DECOR_IDS:
            ar_ = abs(_area(r))
            if any(oid != e['id'] and oa > 1.3 * ar_ and pp(cx, cy, orr) for oid, orr, oa in outl.get((int(cx // 30), int(cy // 30)), ())):
                continue                          # footprint mapped inside a larger building (duplicate): drop
        if e['id'] in LANDMARK_IDS:
            special[e['id']] = (t, r, cx, cy)
            continue                      # custom landmark tops below
        if in_walk(cx, cy):                       # party walls of neighbours no longer coincide (z-fighting)
            r = [(cx + (p[0] - cx) * 0.997, cy + (p[1] - cy) * 0.997) for p in r]
        hs = [G(p[0], p[1]) for p in r]
        ground = min(hs)
        h = _num(t.get('height'))
        lv = _num(t.get('building:levels'))
        core = math.hypot(cx - SHOP_CENTRE[0], cy - SHOP_CENTRE[1]) < OLD_TOWN_R
        fh = OLD_FLOOR_H if core and (lv or 3) <= 5 else FLOOR_H     # tall historic storeys in the Old Town
        if e['id'] == PRIMATE_PALACE:
            fh = 7.0                      # ground floor + two 7 m piano nobile storeys (photo primacialny_main_facade)
        if e['id'] in VYDRICA_LEVELS:              # Vydrica riverside blocks (Earth: 6-storey terraced slabs)
            lv = VYDRICA_LEVELS[e['id']]
        if t.get('building') == 'ruins':
            h = 3.5
        if h is None and not lv and 'building:part' not in t and t.get('building') not in ('garage', 'garages', 'shed', 'kiosk'):
            lv = _infer_levels(levels_ix, cx, cy, abs(_area(r)), core)
            if dist < PODHRADIE_R and abs(_area(r)) >= 60 and t.get('building') not in FLAT_TYPES + ('shed', 'kiosk') and \
                    math.hypot(cx - SHOP_CENTRE[0], cy - SHOP_CENTRE[1]) > 260:
                lv = 3                            # untagged Podhradie houses: 3 storeys (Earth), not the block median                   # Podhradie townhouses: 3+ storeys (Earth)
        if h is None and not _num(t.get('building:levels')) and abs(_area(r)) < 60 and in_walk(cx, cy) and \
                'building:part' not in t:
            h, lv = 3.0, None                     # small untagged outbuilding: one low storey
            if 'roof:shape' not in t:
                t = dict(t, **{'roof:shape': 'flat'})
        if h is None:
            h = (lv * fh + 1.0) if lv else (9.0 if t.get('building') not in ('garage', 'garages', 'shed', 'kiosk') else 2.8)
        minh = _num(t.get('min_height'), 0.0)
        if minh == 0 and _num(t.get('building:min_level')):
            minh = _num(t.get('building:min_level')) * FLOOR_H
        if minh > 0 and in_walk(cx, cy) and abs(_area(r)) > 150:
            continue                              # large raised part over a courtyard / pavement: dropped
        if 0 < minh < 3.4 and in_walk(cx, cy):
            minh = 3.4                            # raised part over a walkway: keep head clearance
        shape = t.get('roof:shape') or ('flat' if (lv or 0) >= 6 or t.get('building') in FLAT_TYPES else 'hipped')
        ortho_col = None
        green_roof = False
        if 'roof:shape' not in t and e['id'] not in LANDMARK_IDS and dist < ORTHO_ROOF_R and \
                t.get('building') not in ('church', 'cathedral', 'chapel') and e['id'] not in DECOR_IDS:
            cls = _roof_from_ortho(H, _TT[0], r)
            if cls is not None and cls[0] == 'green':
                if abs(_area(r)) > 300 and (lv or 1) <= 3:
                    shape, green_roof = 'flat', True       # planted deck (e.g. the parking garage by the Vienna Gate)
                cls = None
            if cls is not None:
                kind_ = cls[0]
                lum = sum(cls[1]) / 3
                if kind_ == 'flat' and core and lum < 0.55 and (lv or 3) <= 6:
                    kind_ = 'slate'                # Old Town: dark grey = slate / sheet-metal mansards, not flat
                if t.get('building') in FLAT_TYPES:
                    kind_ = 'flat'                 # parking decks, sheds, malls: red is a coating / car park
                shape = 'flat' if kind_ == 'flat' else 'hipped'
                ortho_col = cls[1]
                N_ROOF[kind_] = N_ROOF.get(kind_, 0) + 1
        podh_red = in_walk(cx, cy) and dist < PODHRADIE_R and 'roof:shape' not in t and \
            t.get('building') not in FLAT_TYPES and e['id'] not in VYDRICA_LEVELS and (lv or 3) <= 5 and \
            math.hypot(cx - SHOP_CENTRE[0], cy - SHOP_CENTRE[1]) > 260 and abs(_area(r)) < 900
        if podh_red:                              # Podhradie houses: pitched red tile roofs (Earth), not flat/dark
            shape, ortho_col = 'hipped', None
        rh = _num(t.get('roof:height'))
        if rh is None:
            rl = _num(t.get('roof:levels'))
            rh = rl * 2.6 if rl else (0.0 if shape == 'flat' else (min(7.5, 0.45 * H['min_width'](r)) if dist < PODHRADIE_R and in_walk(cx, cy)
                                                                   else min(5.5, 0.32 * H['min_width'](r))))
        if shape == 'pyramidal' and abs(_area(r)) > 400:
            shape = 'hipped'                      # OSM 'pyramidal' on whole blocks (SND, Reduta): a hipped roof
        if e['id'] == SND:                        # Slovak National Theatre, historic building (neo-renaissance)
            h, shape, rh = 24.0, 'hipped', 6.0
        if t.get('building') == 'cathedral':      # St Martin: tall gothic nave under a steep roof
            h, shape, rh = 40.0, 'gabled', 18.0
        elif t.get('building') == 'church' and h < 16:
            h, rh = max(h, 22.0), max(rh, 9.0)
        elif e['id'] == OLD_TOWN_HALL:            # 2 OSM levels are tall gothic storeys; steep glazed-tile roof
            h, shape, rh = 17.0, 'hipped', 7.5
        elif e['id'] == PRIMATE_PALACE:           # tall classicist storeys, low hipped roof behind the attic
            h, shape, rh = 21.0, 'hipped', 4.5
        church_ = t.get('building') in ('church', 'cathedral', 'chapel') or e['id'] in DECOR_IDS or e['id'] in (SND, REDUTA, CARLTON)
        hill = in_walk(cx, cy) and minh == 0 and max(hs) - ground > 0.4 and t.get('building') not in ('garage', 'garages', 'shed') and \
            t.get('building') not in ('church', 'cathedral', 'chapel')
        if hill:
            # house on the slope: floors start at the uphill street level, the downhill side shows a
            # stepped stone plinth / basement storey instead of ground-floor windows cut by the slope
            ground = min(max(hs), min(hs) + 3.0)    # entrance datum, basement plinth at most one storey
        top = ground + h
        if not hill and max(hs) - ground > 2.0 and shape != 'flat':   # far hillside: count from the uphill side too
            top = max(top, max(hs) + 0.5 * h)
        wall_top = top - (rh if shape != 'flat' else 0.0)
        if _num(t.get('height')) is None and lv and shape != 'flat' and in_walk(cx, cy) and not church_:
            # building:levels count full storeys under the eaves; the roof comes on top (not out of them)
            wall_top = ground + lv * fh + 0.6
            top = wall_top + rh
        if wall_top - (ground + minh) < 0.5:
            wall_top = ground + minh + 0.5
        z0 = min(hs) - 1.0 if minh == 0 else ground + minh
        if in_walk(cx, cy) and minh == 0 and dist > R_NEAR and max(hs) - min(hs) > 0.3:
            CUTS.append((r, ground))
        if minh > 0 and in_walk(cx, cy):
            z0 = max(z0, max(hs) + 3.4)           # raised part / bridge-building: walkway head clearance everywhere
            wall_top = max(wall_top, z0 + 0.5)
        wmat = _nearest(WALL_PALETTE, _hex(t.get('building:colour') or t.get('colour')), rng, core or dist < PODHRADIE_R)
        if t.get('building') in ('church', 'cathedral', 'chapel'):
            wmat = 'v2_stone_church' if t.get('building') == 'cathedral' else 'plaster'      # no storey windows
        rmat = _nearest(ROOF_PALETTE, _hex(t.get('roof:colour')), rng)
        if e['id'] == 75070305:                   # Church of St Elizabeth, "the Blue Church"
            wmat, rmat = 'v2_wall_bluechurch', 'v2_roof_bluechurch'
        if e['id'] == PRIMATE_PALACE:
            wmat, rmat = 'v2_wall_primate', 'v2_roof_dark'
        if e['id'] == SND:
            wmat, rmat = 'v2_wall_ochre', 'v2_roof_dark'
        if e['id'] == CARLTON:
            wmat, rmat = 'v2_wall_cream', 'v2_roof_dark'
        if t.get('building') in ('garage', 'garages'):
            wmat = 'plaster'                      # plain rendered garage row, doors added below
        if t.get('building') in ('kiosk', 'shelter') or t.get('amenity') in ('shelter',) or t.get('shop') == 'kiosk':
            wmat = 'v2_shop_' + wmat.split('_')[-1]          # kiosk: glazed counters all round
            shape, rh, rmat = 'flat', 0.0, 'v2_roof_dark'
        if shape == 'flat' and ortho_col is None:
            rmat = 'v2_roof_grey'
        if podh_red and not t.get('roof:colour'):
            rmat = rng.choices(('v2_roof_red', 'v2_roof_crimson', 'v2_roof_salmon'), (3, 2, 2))[0]
        if ortho_col is not None and not t.get('roof:colour'):
            if kind_ == 'slate':
                rmat = 'v2_roof_dark'
            elif shape != 'flat':                  # tiles: the hazy ortho hue is too pale -> palette red/brown
                rmat = 'v2_roof_brown' if sum(ortho_col) / 3 < 0.33 else \
                    rng.choices(('v2_roof_red', 'v2_roof_crimson', 'v2_roof_salmon'), (3, 2, 2))[0]   # Earth: salmon..crimson mix
            else:                                  # membrane / gravel / metal: ortho grey, mostly desaturated
                lin = [_lin(v) for v in ortho_col]
                m_ = sum(lin) / 3
                col = tuple(min(1.0, (m_ * 0.7 + v * 0.3) * 1.6) for v in lin)
                rmat = '_roof_%02x%02x%02x' % tuple(int(v * 255) for v in col)
                TINT[rmat] = ('v2_flat', col)
        if e['id'] in (OLD_TOWN_HALL, PRIMATE_PALACE, FRANCISCAN, CLARISSE, BLUE_CHURCH, ST_NICHOLAS):
            DECOR[e['id']] = (r, ground, wall_top)
        church = t.get('building') in ('church', 'cathedral', 'chapel')
        public = church or e['id'] in DECOR_IDS or e['id'] in (SND, REDUTA, CARLTON) or \
            t.get('building') in ('civic', 'public', 'government', 'palace', 'theatre', 'museum', 'townhall') or \
            t.get('amenity') in ('theatre', 'townhall', 'place_of_worship', 'arts_centre') or \
            'palác' in t.get('name', '').lower() or 'radnica' in t.get('name', '').lower() or \
            t.get('building') in ('garage', 'garages', 'shed', 'roof', 'service')
        if t.get('building') in ('church', 'chapel') and in_walk(cx, cy):
            for a_, b_ in zip(r, r[1:] + r[:1]):        # tall round-headed windows on the long walls
                A_, B_ = H['Vector'](a_), H['Vector'](b_)
                L_ = (B_ - A_).length
                if L_ < 7.0:
                    continue
                d_ = (B_ - A_) / L_
                o_ = H['Vector']((d_.y, -d_.x))
                for k_ in range(int(L_ // 5.0)):
                    m_ = A_ + d_ * (L_ * (k_ + 0.5) / int(L_ // 5.0))
                    _gothic_window(H, walls, m_, d_, o_, ground + 2.5, min(wall_top - 3.0, ground + 8.0), 0.65)
        if t.get('building') == 'cathedral':      # nave/presbytery roofs, windows, buttresses in _landmarks
            DECOR[CATHEDRAL] = (r, ground, ground + 22.0)
            _facade(H, walls, r, z0, ground + 22.0, wmat, ground)
            count += 1
            continue
        modern = shape == 'flat' and not church and (lv or h / FLOOR_H) >= 4 and \
            (not core or t.get('building') in ('office', 'commercial', 'hotel', 'retail')) and \
            not (dist < PODHRADIE_R and e['id'] not in VYDRICA_LEVELS and t.get('building') not in ('office', 'commercial', 'hotel'))
        if e['id'] in VYDRICA_LEVELS:
            wmat = 'v2_wall_white'
        if t.get('building') == 'ruins':
            wmat = 'v2_stone_church'
        if modern:
            wmat = 'v2_modern_' + wmat.split('_')[-1]
        top_wall = wall_top
        pent = None
        if modern and (lv or 0) >= 5 and dist < 900 and abs(_area(r)) > 250 and not HOLES.get((e['id'], round(cx), round(cy))):
            try:
                inn = [(v.x, v.y) for v in H['offset_poly'](r, -2.5)]
                if len(inn) == len(r) and _area(inn) > 0.4 * abs(_area(r)) and \
                        all(math.hypot(inn[i][0] - r[i][0], inn[i][1] - r[i][1]) < 7.5 for i in range(len(r))):
                    pent = inn                     # recessed top storey (penthouse / terrace)
                    top_wall = wall_top - fh
            except ZeroDivisionError:
                pent = None
        plinth_mat = ('stone', 'v2_stone_church', 'concrete', 'v2_render_ochre')[e['id'] % 4]
        if in_walk(cx, cy) and not church and not modern and R_NEAR < dist < PODHRADIE_R and minh == 0 and \
                t.get('building') not in ('garage', 'garages', 'shed', 'kiosk', 'roof', 'service'):
            _house_doors(H, walls, r, G, shop if not public else None, fh)
        if in_walk(cx, cy) and minh > 2.0:            # raised part (passage / overhang): corner piers carry it
            _cap(H, walls, list(reversed(r)), z0, 'plaster')
            for p_ in r:
                if not _hwy_near(p_[0], p_[1], 1.5):
                    walls.box([(p_[0] - 0.25, p_[1] - 0.25), (p_[0] + 0.25, p_[1] - 0.25), (p_[0] + 0.25, p_[1] + 0.25), (p_[0] - 0.25, p_[1] + 0.25)],
                              G(*p_) - 0.3, z0, 'v2_stone_church')
        burgher = in_walk(cx, cy) and dist < PODHRADIE_R and not modern and not public and wmat.startswith('v2_wall_') and \
            math.hypot(cx - SHOP_CENTRE[0], cy - SHOP_CENTRE[1]) > 260
        if burgher:
            wmat = wmat.replace('v2_wall_', 'v2_narrow_')
        _facade(H, walls, r, z0, top_wall, wmat, ground, None if public else shop, G, fh,
                trims=in_walk(cx, cy) and not modern and not church, row=random.Random(e['id']) if burgher else None,
                ghost=walls is ghost,
                plinth=(plinth_mat if not modern else 'concrete') if in_walk(cx, cy) and t.get('building') != 'cathedral' else None)
        if in_walk(cx, cy) and not modern and not church and wall_top - ground > 6:
            for a_, b_ in zip(r, r[1:] + r[:1]):            # street-level read: main cornice + stone plinth
                if math.hypot(b_[0] - a_[0], b_[1] - a_[1]) > 2.0:
                    H['seg_box'](walls, a_, b_, -0.2, 0.02, top_wall - 0.45, top_wall - 0.12, 'plaster')    # 0.2 m cornice
                    if shape != 'flat' and _faces_priority(a_, b_):
                        H['seg_box'](walls, a_, b_, -0.62, -0.5, top_wall - 0.38, top_wall - 0.26, 'v2_slate')  # gutter
                    Lb = math.hypot(b_[0] - a_[0], b_[1] - a_[1])
                    kb = max(1, int(Lb / 6.4)) if abs(G(*a_) - G(*b_)) > 0.4 else 1
                    for j_ in range(kb):              # plinth steps with the street, bay by bay
                        p0_ = (a_[0] + (b_[0] - a_[0]) * j_ / kb, a_[1] + (b_[1] - a_[1]) * j_ / kb)
                        p1_ = (a_[0] + (b_[0] - a_[0]) * (j_ + 1) / kb, a_[1] + (b_[1] - a_[1]) * (j_ + 1) / kb)
                        H['seg_box'](walls, p0_, p1_, -0.06, 0.02, z0, max(G(*p0_), G(*p1_)) + 0.5, plinth_mat)
        if pent is not None:
            _facade(H, walls, pent, top_wall, wall_top, wmat, ground, None, G, fh)
            _cap(H, roofs, r, top_wall, rmat if ortho_col is not None else 'v2_roof_grey')
            for a_, b_ in zip(r, r[1:] + r[:1]):    # terrace parapet
                H['seg_box'](roofs, a_, b_, 0.0, 0.25, top_wall, top_wall + 1.0, 'concrete')
        if e['id'] in VYDRICA_LEVELS:             # Vydrica: glass loggias / balconies on the river (S/E) faces
            for a_, b_ in zip(r, r[1:] + r[:1]):
                A_, B_ = H['Vector'](a_), H['Vector'](b_)
                L_ = (B_ - A_).length
                if L_ < 6.0:
                    continue
                d_ = (B_ - A_) / L_
                o_ = H['Vector']((d_.y, -d_.x))
                if o_.y > 0.3:
                    continue
                for k_ in range(1, int((top_wall - ground) / fh)):
                    zf_ = ground + k_ * fh
                    H['seg_box'](walls, A_ + d_ * 1.0, B_ - d_ * 1.0, -1.5, 0.0, zf_ - 0.2, zf_, 'concrete')
                    q_ = [H['Vector']((*(A_ + d_ * 1.0 + o_ * 1.5), zf_)), H['Vector']((*(B_ - d_ * 1.0 + o_ * 1.5), zf_)),
                          H['Vector']((*(B_ - d_ * 1.0 + o_ * 1.5), zf_ + 1.05)), H['Vector']((*(A_ + d_ * 1.0 + o_ * 1.5), zf_ + 1.05))]
                    walls.poly(q_, 'glass')
        if e['id'] == CARLTON:                    # Carlton: dark ground-floor arcade toward Hviezdoslavovo nam.
            for a_, b_ in zip(r, r[1:] + r[:1]):
                A_, B_ = H['Vector'](a_), H['Vector'](b_)
                L_ = (B_ - A_).length
                if L_ < 8 or not _faces_priority(a_, b_):
                    continue
                d_ = (B_ - A_) / L_
                o_ = H['Vector']((d_.y, -d_.x))
                g_ = min(G(*a_), G(*b_))
                walls.poly([H['Vector']((*(A_ + o_ * 0.03), g_)), H['Vector']((*(B_ + o_ * 0.03), g_)),
                            H['Vector']((*(B_ + o_ * 0.03), g_ + 4.6)), H['Vector']((*(A_ + o_ * 0.03), g_ + 4.6))], 'v2_slate')
                nb_ = max(2, int(L_ / 3.6))
                for k_ in range(nb_ + 1):
                    c_ = A_ + d_ * (L_ * k_ / nb_)
                    H['seg_box'](walls, c_ - d_ * 0.35, c_ + d_ * 0.35, -0.7, 0.0, g_ - 0.2, g_ + 4.6, 'v2_stone_church')
                H['seg_box'](walls, A_, B_, -0.75, 0.0, g_ + 4.6, g_ + 5.3, 'v2_stone_church')
        if t.get('building') in ('garage', 'garages') and in_walk(cx, cy):     # up-and-over doors
            for a_, b_ in zip(r, r[1:] + r[:1]):
                A_, B_ = H['Vector'](a_), H['Vector'](b_)
                L_ = (B_ - A_).length
                if L_ < 2.8 or not _hwy_near((A_.x + B_.x) / 2, (A_.y + B_.y) / 2, 8.0):
                    continue
                d_ = (B_ - A_) / L_
                o_ = H['Vector']((d_.y, -d_.x)) * 0.03
                g_ = min(G(*a_), G(*b_))
                for k_ in range(int(L_ // 3.0)):
                    p0_, p1_ = A_ + d_ * (k_ * 3.0 + 0.3) + o_, A_ + d_ * (k_ * 3.0 + 2.7) + o_
                    walls.poly([H['Vector']((*p0_, g_)), H['Vector']((*p1_, g_)), H['Vector']((*p1_, g_ + 2.1)), H['Vector']((*p0_, g_ + 2.1))], 'v2_garagedoor')
        holes = HOLES.get((e['id'], round(cx), round(cy)), []) if dist < R_DETAIL else []
        cmat = wmat
        if holes and wmat in TINT:                # courtyards read as dark shafts from above (Earth)
            cmat = wmat + '~court'
            if cmat not in TINT:
                TINT[cmat] = (TINT[wmat][0], tuple(c_ * 0.5 for c_ in TINT[wmat][1]))
        for hr in holes:                          # courtyard facades (inner rings, facing the courtyard)
            _facade(H, walls, list(reversed(hr)), z0, wall_top, cmat, ground, None, G, fh)
        area_ = abs(_area(r))
        nearfl = any(_near_flight(p_[0], p_[1], 2.5) for p_ in r)
        if in_walk(cx, cy) and shape != 'flat' and rh >= 2.5 and not church and not nearfl:
            _roof_dressing(H, roofs, r, wall_top, rh, rmat, wmat, rng)
        if shape not in ('flat', 'pyramidal', 'dome', 'onion', 'cone') and rh >= 0.2 and dist < FIELD_ROOF_R and \
                (holes or len(r) > 8 or area_ > 350 or (in_walk(cx, cy) and _concave(r))):
            _roof_field(H, roofs, [r if nearfl else _eaves(H, r, cx, cy)] + holes, wall_top - 0.25 * (in_walk(cx, cy)), max(rh, 3.0), rmat, slope=0.75)
            count += 1
            continue
        if holes and (shape in ('flat',) or rh < 0.2):
            _cap_holes(H, roofs, [r] + holes, wall_top, rmat if ortho_col is not None else 'v2_roof_grey')
            count += 1
            continue
        if shape in ('flat',) or rh < 0.2:
            green_roof = green_roof or (ortho_col is None and t.get('building') == 'parking' and dist < ORTHO_ROOF_R)
            _cap(H, roofs, r, wall_top, 'grass' if green_roof else (rmat if ortho_col is not None else 'v2_roof_grey'))
        else:
            _roof(H, roofs, r if nearfl else _eaves(H, r, cx, cy), wall_top - 0.25 * (in_walk(cx, cy)), rh, shape, rmat)
        count += 1
    print('v2_city buildings', count, 'roofs from ortho', N_ROOF)
    print('v2_city walk-route buildings without collision', n_ghost)
    return far_walls.build(coll) + near.build(coll) + ghost.build(coll), special


def _gothic_window(H, mb, m, dd, out, z0, z1, hw):
    """Tall lancet: leaded glass (lattice + 2 mullions in the texture) under a pointed head, framed by a
    0.35 m deep stone splay (jambs, arch, sill) standing proud of the wall plane."""
    Vector, seg_box = H['Vector'], H['seg_box']
    zt = z1 + hw * 1.6
    g = [m - dd * hw + out * 0.05, m + dd * hw + out * 0.05]
    mb.poly([Vector((*g[0], z0)), Vector((*g[1], z0)), Vector((*g[1], z1)), Vector((*g[0], z1))], 'v2_leaded',
            uv=[(0, 0), (1, 0), (1, (z1 - z0) / (2 * hw)), (0, (z1 - z0) / (2 * hw))])
    mb.poly([Vector((*g[0], z1)), Vector((*g[1], z1)), Vector((*(m + out * 0.05), zt))], 'v2_leaded',
            uv=[(0, 0), (1, 0), (0.5, 0.8)])
    for sgn in (-1, 1):                                       # jambs
        c = m + dd * (hw + 0.18) * sgn
        mb.box([c - dd * 0.18, c + dd * 0.18, c + dd * 0.18 + out * 0.35, c - dd * 0.18 + out * 0.35], z0 - 0.3, z1, 'v2_stone_church')
    for sgn in (-1, 1):                                       # pointed arch as two sloped stone bars
        p0 = m + dd * (hw + 0.18) * sgn
        a3, b3 = Vector((*p0, z1)), Vector((*m, zt + 0.25))
        bar = [a3 + Vector((*(out * 0.0), 0)), b3, b3 + Vector((*(out * 0.35), 0)), a3 + Vector((*(out * 0.35), 0))]
        mb.poly(bar if sgn > 0 else list(reversed(bar)), 'v2_stone_church')
    seg_box(mb, m - dd * (hw + 0.36), m + dd * (hw + 0.36), -0.45, 0.0, z0 - 0.45, z0, 'v2_stone_church')      # sill
    # tracery head: a rose (ring + 3 foils) in the pointed arch, lancet heads under it
    ang = math.atan2(out.y, out.x)
    rc = Vector((*(m + out * 0.08), z1 + hw * 0.65))
    H['ellipsoid'](mb, rc, 0.06, hw * 0.55, hw * 0.55, ang, 0, 'v2_stone_church', subdiv=1)
    for k in range(3):
        a_ = math.pi / 2 + k * 2 * math.pi / 3
        H['ellipsoid'](mb, rc + Vector((*(dd * math.cos(a_) * hw * 0.22), math.sin(a_) * hw * 0.22)), 0.07, hw * 0.2, hw * 0.2, ang, 0, 'v2_leaded', subdiv=1)


def _landmarks(H, special, G, coll, data_misc):
    """Custom tops: cathedral tower crown, Michael's Gate cupola, SNP bridge pylon + UFO."""
    MB, Vector, _prism, ellipsoid, seg_box = H['MB'], H['Vector'], H['_prism'], H['ellipsoid'], H['seg_box']
    mb = VChunk(H, 'V2City_Landmarks|-col', 'V2City_Landmarks|-col', 1e5, 1e5)

    def body(r, z0, z1, mat):
        _facade(H, mb, r, z0, z1, mat, z0)
        _cap(H, mb, r, z1, 'v2_roof_grey')

    # St Martin's nave + presbytery: v2_landmarks.dom_body()
    # St Martin's west tower: v2_landmarks.dom_tower() (photo-modelled)
    # --- Michael's Gate (OSM 39391573, height 51 m): square tower, baroque copper cupola, St Michael
    if 39391573 in special:
        t, r, cx, cy = special[39391573]
        g = min(G(p[0], p[1]) for p in r)
        # plain rendered shaft; the gate passage under it stays open where Michalska crosses the outline
        streets_ = []
        for e_ in data_misc['elements']:
            if e_['type'] == 'way' and e_.get('tags', {}).get('name') == 'Michalská' and e_.get('geometry'):
                q_ = _ring_xy(H, e_['geometry'])
                streets_ += list(zip(q_, q_[1:]))
        nodes_ = [Vector(q) for sg in streets_ for q in sg]
        for p0, p1 in zip(r, r[1:] + r[:1]):
            A, B = Vector(p0), Vector(p1)
            L_ = (B - A).length
            u_ = (B - A) / max(L_, 1e-6)
            hitp = None
            for s0, s1 in streets_:
                ip = H['geometry'].intersect_line_line_2d(A, B, Vector(s0), Vector(s1))
                if ip is not None:
                    hitp = Vector(ip)
            for q in nodes_:                      # the street usually shares the outline's nodes
                tq = (q - A).dot(u_)
                if -0.01 <= tq <= L_ + 0.01 and (A + u_ * tq - q).length < 0.6:
                    hitp = q
            if hitp is None:
                mb.poly([Vector((A.x, A.y, g - 1)), Vector((B.x, B.y, g - 1)), Vector((B.x, B.y, g + 26)), Vector((A.x, A.y, g + 26))], 'plaster')
                continue
            t_ = (hitp - A).dot(u_)
            ta, tb = max(0.0, t_ - 1.9), min(L_, t_ + 1.9)
            o0, o1 = A + u_ * ta, A + u_ * tb
            gz = G(hitp.x, hitp.y)
            for a_, b_, z0_, z1_ in ((A, o0, g - 1, g + 26), (o1, B, g - 1, g + 26), (o0, o1, gz + 5.2, g + 26)):
                if (b_ - a_).length > 0.05:
                    mb.poly([Vector((a_.x, a_.y, z0_)), Vector((b_.x, b_.y, z0_)), Vector((b_.x, b_.y, z1_)), Vector((a_.x, a_.y, z1_))], 'plaster')
            print('v2_city Michael gate passage on edge', round(L_, 1), 'm')
        _cap(H, mb, r, g + 26, 'v2_roof_grey')
        # clock stage, copper roofs and St Michael: v2_landmarks.michalska()
    # Old Town Hall tower: v2_landmarks.townhall()
    # --- Maximilian (Roland) fountain, Hlavne namestie: low octagonal basin with water, a baluster pier
    # carrying a wide shell bowl, a fluted column and Roland in armour with shield and sword
    fc = Vector((612.0, 135.0))          # centre of Hlavne namestie, >= 3 m clear of the mapped square paths
    gz = G(fc.x, fc.y)
    o8 = [fc + Vector((math.cos(k * math.pi / 4 + 0.39), math.sin(k * math.pi / 4 + 0.39))) * 4.6 for k in range(8)]
    for k in range(8):
        seg_box(mb, o8[k], o8[(k + 1) % 8], -0.08, 0.45, gz - 0.2, gz + 0.7, 'v2_stone_church')
        seg_box(mb, o8[k], o8[(k + 1) % 8], -0.14, 0.5, gz + 0.7, gz + 0.82, 'v2_stone_church')   # rim moulding
    _cap(H, mb, [tuple(q) for q in o8], gz + 0.5, 'water')
    _prism(mb, Vector((fc.x, fc.y, gz)), Vector((fc.x, fc.y, gz + 0.9)), 0.9, 0.9, 'v2_stone_church', seg=8)
    _prism(mb, Vector((fc.x, fc.y, gz + 0.9)), Vector((fc.x, fc.y, gz + 1.7)), 0.45, 0.7, 'v2_stone_church', seg=8)  # baluster
    _prism(mb, Vector((fc.x, fc.y, gz + 1.7)), Vector((fc.x, fc.y, gz + 2.1)), 0.9, 2.1, 'v2_stone_church', seg=12)  # bowl
    _cap(H, mb, [tuple(fc + Vector((math.cos(k * math.pi / 6), math.sin(k * math.pi / 6))) * 2.0) for k in range(12)], gz + 2.05, 'water')
    _prism(mb, Vector((fc.x, fc.y, gz + 2.1)), Vector((fc.x, fc.y, gz + 5.0)), 0.42, 0.36, 'stone', seg=8)  # column
    _prism(mb, Vector((fc.x, fc.y, gz + 5.0)), Vector((fc.x, fc.y, gz + 5.3)), 0.45, 0.45, 'stone', seg=8)  # capital
    # Roland: legs, armoured torso, head with helmet, shield (left), raised sword (right)
    for sx in (-0.12, 0.12):
        _prism(mb, Vector((fc.x + sx, fc.y, gz + 5.3)), Vector((fc.x + sx, fc.y, gz + 6.15)), 0.13, 0.11, 'stone', seg=6)
    _prism(mb, Vector((fc.x, fc.y, gz + 6.1)), Vector((fc.x, fc.y, gz + 6.85)), 0.3, 0.34, 'stone', seg=8)
    ellipsoid(mb, Vector((fc.x, fc.y, gz + 7.02)), 0.16, 0.16, 0.2, 0, 0, 'stone', subdiv=1)
    _prism(mb, Vector((fc.x, fc.y, gz + 7.12)), Vector((fc.x, fc.y, gz + 7.3)), 0.13, 0.05, 'stone', seg=6)
    mb.box([(fc.x - 0.36, fc.y - 0.3), (fc.x - 0.3, fc.y - 0.3), (fc.x - 0.3, fc.y + 0.15), (fc.x - 0.36, fc.y + 0.15)], gz + 6.0, gz + 6.7, 'stone')
    _prism(mb, Vector((fc.x + 0.3, fc.y, gz + 6.5)), Vector((fc.x + 0.35, fc.y + 0.1, gz + 7.6)), 0.025, 0.015, 'stone', seg=4)
    # --- Ganymede fountain in front of the Slovak National Theatre (Hviezdoslavovo nam.)
    gc = Vector((717.0, 3.0))
    gz = G(gc.x, gc.y)
    o12 = [gc + Vector((math.cos(k * math.pi / 6), math.sin(k * math.pi / 6))) * 3.4 for k in range(12)]
    for k in range(12):
        seg_box(mb, o12[k], o12[(k + 1) % 12], -0.05, 0.35, gz - 0.2, gz + 0.6, 'v2_stone_church')
    _cap(H, mb, [tuple(q) for q in o12], gz + 0.4, 'water')
    _prism(mb, Vector((gc.x, gc.y, gz)), Vector((gc.x, gc.y, gz + 2.2)), 0.7, 0.45, 'v2_stone_church', seg=8)
    _prism(mb, Vector((gc.x, gc.y, gz + 2.2)), Vector((gc.x, gc.y, gz + 2.5)), 1.1, 1.1, 'v2_stone_church', seg=8)
    ellipsoid(mb, Vector((gc.x, gc.y, gz + 3.0)), 0.35, 0.3, 0.55, 0, 0, 'v2_copper', subdiv=1)     # Ganymede + eagle
    ellipsoid(mb, Vector((gc.x + 0.3, gc.y, gz + 3.5)), 0.4, 0.15, 0.2, 0, 0, 'v2_copper', subdiv=1)
    # --- church towers that break the Old Town roofline from the castle (no OSM tower parts):
    # Franciscan church (baroque-rendered shaft, Gothic stone spire), Poor Clares (slim pentagonal Gothic
    # tower with a stone spire), St Elizabeth "Blue Church" (round tower, blue cupola, 36.8 m)
    def tower(c, g, rad, z_shaft, z_top, n, wall_mat, roof_mat, gallery=True):
        o = [c + Vector((math.cos(2 * math.pi * k / n + 0.3), math.sin(2 * math.pi * k / n + 0.3))) * rad for k in range(n)]
        for k in range(n):
            a, b = o[k], o[(k + 1) % n]
            mb.poly([Vector((a.x, a.y, g - 1)), Vector((b.x, b.y, g - 1)), Vector((b.x, b.y, g + z_shaft)), Vector((a.x, a.y, g + z_shaft))], wall_mat)
            m_ = (a + b) / 2
            o_ = (m_ - c).normalized()
            sd = Vector((-o_.y, o_.x)) * min(0.45, (b - a).length * 0.25)
            mb.poly([Vector((*(m_ + o_ * 0.05 - sd), g + z_shaft - 7)), Vector((*(m_ + o_ * 0.05 + sd), g + z_shaft - 7)),
                     Vector((*(m_ + o_ * 0.05 + sd), g + z_shaft - 2.5)), Vector((*(m_ + o_ * 0.05 - sd), g + z_shaft - 2.5))], 'v2_slate')
            if gallery:
                seg_box(mb, a + (a - c) * 0.1, b + (b - c) * 0.1, 0.0, 0.15, g + z_shaft, g + z_shaft + 0.9, 'v2_stone_church')
            mb.poly([Vector((a.x, a.y, g + z_shaft)), Vector((b.x, b.y, g + z_shaft)), Vector((c.x, c.y, g + z_top))], roof_mat)
        ellipsoid(mb, Vector((c.x, c.y, g + z_top + 0.2)), 0.25, 0.25, 0.25, 0, 0, 'gold', subdiv=1)
    if FRANCISCAN in DECOR:
        r, gnd, wt = DECOR[FRANCISCAN]
        tower(Vector((636.5, 279.0)), gnd, 3.2, 27.0, 45.0, 8, 'v2_render_ochre', 'v2_stone_church')
    if CLARISSE in DECOR:
        r, gnd, wt = DECOR[CLARISSE]
        pass                                  # pentagonal tower: v2_landmarks.klarisky()
    if ST_NICHOLAS in DECOR:                   # St Nicholas (Orthodox) below the castle: west tower, green onion
        r, gnd, wt = DECOR[ST_NICHOLAS]
        w_ = min(r, key=lambda p: p[0])
        cc_ = sum((Vector(p) for p in r), Vector((0, 0))) / len(r)
        c = Vector(w_) + (cc_ - Vector(w_)).normalized() * 3.2
        tower(c, gnd, 2.6, 19.0, 19.2, 4, 'plaster', 'v2_copper', gallery=False)
        ellipsoid(mb, Vector((c.x, c.y, gnd + 21.0)), 2.3, 2.3, 2.4, 0, 0, 'v2_copper', subdiv=2)
        _prism(mb, Vector((c.x, c.y, gnd + 23.0)), Vector((c.x, c.y, gnd + 25.5)), 0.5, 0.3, 'v2_copper', seg=8)
        ellipsoid(mb, Vector((c.x, c.y, gnd + 26.0)), 0.8, 0.8, 1.0, 0, 0, 'v2_copper', subdiv=1)
        _prism(mb, Vector((c.x, c.y, gnd + 26.8)), Vector((c.x, c.y, gnd + 29.0)), 0.06, 0.04, 'gold', seg=4)
    if BLUE_CHURCH in DECOR:
        r, gnd, wt = DECOR[BLUE_CHURCH]
        c = Vector((1035.5, 488.5))
        for k in range(12):
            a = c + Vector((math.cos(k * math.pi / 6), math.sin(k * math.pi / 6))) * 3.0
            b = c + Vector((math.cos((k + 1) * math.pi / 6), math.sin((k + 1) * math.pi / 6))) * 3.0
            mb.poly([Vector((a.x, a.y, gnd - 1)), Vector((b.x, b.y, gnd - 1)), Vector((b.x, b.y, gnd + 29)), Vector((a.x, a.y, gnd + 29))], 'v2_render_blue')
        ellipsoid(mb, Vector((c.x, c.y, gnd + 29.0)), 3.3, 3.3, 4.2, 0, 0, 'v2_roof_bluechurch', subdiv=2)
        _prism(mb, Vector((c.x, c.y, gnd + 32.8)), Vector((c.x, c.y, gnd + 36.8)), 0.12, 0.04, 'gold', seg=6)
    # Primate's Palace attic, pediment, hat, portico: v2_landmarks.primate()
    return mb.build(coll)


SNP = {}


def _clip_rect(poly, x0, y0, x1, y1):
    def clip(pts, inside, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            ia, ib = inside(a), inside(b)
            if ib:
                if not ia:
                    out.append(inter(a, b))
                out.append(b)
            elif ia:
                out.append(inter(a, b))
        return out

    def ix(xc):
        return lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / ((b[0] - a[0]) or 1e-9))

    def iy(yc):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yc - a[1]) / ((b[1] - a[1]) or 1e-9), yc)
    p = poly
    for inside, inter in ((lambda q: q[0] >= x0, ix(x0)), (lambda q: q[0] <= x1, ix(x1)),
                          (lambda q: q[1] >= y0, iy(y0)), (lambda q: q[1] <= y1, iy(y1))):
        if not p:
            break
        p = clip(p, inside, inter)
    return p


def _danube(H, misc, G, coll):
    """River surface from the OSM riverbank multipolygon, clipped to the context square."""
    MB, Vector, geometry = H['MB'], H['Vector'], H['geometry']
    mb = MB('V2City_Danube')
    quay = MB('V2City_Quay-col')
    far = _load(H, 'water_far.json')
    src, lim = (far, 6000.0) if far['elements'] else (misc, 1500.0)
    for e in src['elements']:
        t = e.get('tags', {})
        if e['type'] != 'relation' or t.get('natural') != 'water' or t.get('water') != 'river':
            continue
        outers = _assemble(H, e['members'], 'outer')
        inners = _assemble(H, e['members'], 'inner')
        for ring in outers:
            ring = _clip_rect(_clean(ring), -lim, -lim, lim, lim)
            if len(ring) < 3:
                continue
            holes = []
            for hr in inners:
                hr = _clean(hr)
                if all(-lim < p[0] < lim and -lim < p[1] < lim for p in hr) and len(hr) >= 3:
                    holes.append(hr)
            loops = [[(p[0], p[1], 0) for p in ring]] + [[(p[0], p[1], 0) for p in hr] for hr in holes]
            flat = [p for lp in loops for p in lp]
            try:
                tris = geometry.tessellate_polygon(loops)
            except Exception as ex:
                print('danube tessellation failed', ex)
                continue
            z = G.water
            # stone quay walls along the bank wherever the land stands above the water
            for k in range(len(ring)):
                a, b = ring[k], ring[(k + 1) % len(ring)]
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L < 0.5 or max(abs(a[0]), abs(a[1]), abs(b[0]), abs(b[1])) > 1450.0:
                    continue
                for j in range(max(1, int(L / 12.0))):
                    t0, t1 = j / max(1, int(L / 12.0)), (j + 1) / max(1, int(L / 12.0))
                    p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
                    p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
                    # coping derived from the promenade 3 m inland (not the bank line), parapet ~1 m above it
                    dx_, dy_ = p1[0] - p0[0], p1[1] - p0[1]
                    ln_ = math.hypot(dx_, dy_) or 1.0
                    nx_, ny_ = -dy_ / ln_ * 3.0, dx_ / ln_ * 3.0
                    mx_, my_ = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
                    if H['point_in_poly'](mx_ + nx_, my_ + ny_, ring):
                        nx_, ny_ = -nx_, -ny_
                    top = min(G(p0[0] + nx_, p0[1] + ny_), G(p1[0] + nx_, p1[1] + ny_)) + 0.1
                    if top - z < 0.3 or top - z > 12:
                        continue                      # (continuous along the promenade, also where it dips)
                    wm = quay if in_walk(*p0) else mb
                    wm.poly([Vector((p0[0], p0[1], z - 1.0)), Vector((p1[0], p1[1], z - 1.0)),
                             Vector((p1[0], p1[1], top + 0.4)), Vector((p0[0], p0[1], top + 0.4))], 'stone')
                    wm.poly([Vector((p1[0], p1[1], z - 1.0)), Vector((p0[0], p0[1], z - 1.0)),
                             Vector((p0[0], p0[1], top + 0.4)), Vector((p1[0], p1[1], top + 0.4))], 'stone')
                    if wm is quay:                    # promenade railing on the river wall (and it blocks a fall)
                        a3, b3 = Vector(p0), Vector(p1)
                        H['seg_box'](quay, a3, b3, -0.04, 0.04, top + 0.95, top + 1.05, 'v2_iron')
                        H['seg_box'](quay, a3, b3, -0.25, 0.25, top + 0.3, top + 0.42, 'stone')     # coping
                        for k_ in range(max(1, int((b3 - a3).length / 2.0))):
                            c3 = a3.lerp(b3, (k_ + 0.5) / max(1, int((b3 - a3).length / 2.0)))
                            quay.box([(c3.x - 0.03, c3.y - 0.03), (c3.x + 0.03, c3.y - 0.03), (c3.x + 0.03, c3.y + 0.03), (c3.x - 0.03, c3.y + 0.03)],
                                     top + 0.42, top + 0.95, 'v2_iron')
            for tri in tris:
                q = [Vector((flat[i][0], flat[i][1], z)) for i in tri]
                if geometry.normal(q).z < 0:
                    q.reverse()
                mb.poly(q, 'river', uv_scale=40)
    return [mb.build(coll)] + ([quay.build(coll)] if quay.faces else [])


ROAD_W = {'motorway': 14, 'trunk': 12, 'primary': 11, 'secondary': 9, 'tertiary': 8, 'residential': 6,
          'unclassified': 6, 'living_street': 5, 'pedestrian': 6, 'service': 3.5}


BRIDGE_ENDS = {}


def _bridge_profile(G, pts):
    """Deck heights along a bridge way: banks at their terrain, raised over water, gentle camber. Ends shared
    with another bridge way (a viaduct split into OSM pieces) are not pulled down to the ground."""
    def end_z(p):
        k = (round(p[0]), round(p[1]))
        if BRIDGE_ENDS.get(k, 0) > 1 and in_walk(*p):
            return G(*p) + 8.2 + 1.2
        return G(*p)
    za, zb = end_z(pts[0]), end_z(pts[-1])
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])) or 1.0
    acc, out = 0.0, []
    for i, p in enumerate(pts):
        if i:
            acc += math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1])
        t = acc / total
        z = za + (zb - za) * t
        hump = max(z, G.water + 9.0 + 2.5 * math.sin(math.pi * t))
        de = max(0.0, min(acc, total - acc))      # within 60 m of a ground end the deck ramps down to it
        k = 1.0 if de > 60.0 else (de / 60.0) ** 0.7
        out.append(z + (hump - z) * k)
    # over land in the walk zone (the Staromestska / SNP approach viaduct over Rybne nam. and the promenade):
    # deck underside >= 7 m above the ground wherever the deck is already off the ground; one smooth profile
    # (moving max then moving average, ~2 m samples) so there are no humps, and the abutment ends stay put
    cum = [0.0]
    for a_, b_ in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b_[0] - a_[0], b_[1] - a_[1]))
    tot = cum[-1]
    # (away from the abutments - 25 m - the deck clears whatever runs underneath: embankment road, promenade)
    lift_ = [max(0.0, G(*p) + 8.2 - z) if in_walk(*p) and G(*p) > G.water + 1.0 and
             (z - G(*p) > 1.0 or 25.0 < c_ < tot - 25.0) else 0.0
             for p, z, c_ in zip(pts, out, cum)]
    n = len(pts)
    mx = [max(lift_[max(0, i - 8):i + 9]) for i in range(n)]
    sm = [sum(mx[max(0, i - 8):i + 9]) / len(mx[max(0, i - 8):i + 9]) for i in range(n)]
    sm = [max(a_, b_) for a_, b_ in zip(sm, lift_)]
    sa = BRIDGE_ENDS.get((round(pts[0][0]), round(pts[0][1])), 0) > 1
    sb = BRIDGE_ENDS.get((round(pts[-1][0]), round(pts[-1][1])), 0) > 1
    res = []
    for z, e, c_ in zip(out, sm, cum):   # ground ends: the clearance lift tapers out over 25 m (deck lands)
        ta = 1.0 if sa else min(1.0, c_ / 25.0)
        tb = 1.0 if sb else min(1.0, (tot - c_) / 25.0)
        res.append(z + e * max(0.0, min(ta, tb)))
    return res


def _skirts(mb, G, l0, l1, r0, r1, lk, mat, Vector, out=0.7, dz=(0.0, 0.0)):
    """Walk-zone edges: a 0.7 m ramp from the surface edge down to the terrain on both sides, so no
    lip is left where the mesh meets bare ground (player step 0.3 m)."""
    d = (l1 - l0)
    if d.length < 1e-3:
        return
    nrm = Vector((-d.y, d.x)).normalized()
    for e0, e1, sg in ((l0, l1, -1), (r0, r1, 1)):
        o = nrm * out * sg
        q = [Vector((*e0, G(*e0) + lk + dz[0])), Vector((*e1, G(*e1) + lk + dz[1])),
             Vector((*(e1 + o), G(*(e1 + o)) - 0.04)), Vector((*(e0 + o), G(*(e0 + o)) - 0.04))]
        if (q[1] - q[0]).cross(q[3] - q[0]).z < 0:
            q.reverse()
        mb.poly(q, mat)


BLD = {}


def _bld_index(footprints):
    for poly in footprints:
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        for gx in range(int(min(xs) // 20), int(max(xs) // 20) + 1):
            for gy in range(int(min(ys) // 20), int(max(ys) // 20) + 1):
                BLD.setdefault((gx, gy), []).append(poly)


def _in_bld(x, y, pad=2.0):
    from mathutils import geometry as _g
    for poly in BLD.get((int(x // 20), int(y // 20)), ()):
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        if min(xs) - pad < x < max(xs) + pad and min(ys) - pad < y < max(ys) + pad:
            if _pip(x, y, poly):
                return True
            for i in range(len(poly)):
                a, b = poly[i - 1], poly[i]
                dx, dy = b[0] - a[0], b[1] - a[1]
                l2 = dx * dx + dy * dy or 1e-9
                k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
                if math.hypot(x - a[0] - k * dx, y - a[1] - k * dy) < pad:
                    return True
    return False


def _pip(x, y, poly):
    c = False
    for i in range(len(poly)):
        a, b = poly[i], poly[i - 1]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            c = not c
    return c


def L_seg_ok(a, b):
    return (b - a).length > 0.5


def _roads(H, misc, G, coll, streets, near_ok=None):
    ChunkMB, Vector, seg_box = H['ChunkMB'], H['Vector'], H['seg_box']
    rmb = streets
    bmb = ChunkMB('V2City_Bridges', tile=1200.0)
    n_br = 0
    n_mk = [0]
    JUNC = {}
    import bpy
    from mathutils.bvhtree import BVHTree
    dg_ = bpy.context.evaluated_depsgraph_get()
    fbv = [BVHTree.FromObject(o, dg_) for o in bpy.data.objects
           if o.type == 'MESH' and o.name.startswith(('Ground_Detail', 'Ground_Base', 'Fort_Paths', 'Fort_Ramps', 'Fort_Ground'))]

    FORTBV[:] = fbv
    FORTBV_G[:] = [G]

    def fort_ground(p_):
        g_ = G(p_.x, p_.y)
        return any(b_.ray_cast(Vector((p_.x, p_.y, g_ + 2.0)), Vector((0, 0, -1)), 4.0)[0] is not None for b_ in fbv)
    BRIDGE_ENDS.clear()

    for e in misc['elements']:
        t = e.get('tags', {})
        if e['type'] == 'way' and e.get('geometry') and (t.get('highway') or t.get('railway') == 'tram') and \
                (t.get('bridge') in ('yes', 'viaduct', 'movable') or t.get('man_made') == 'bridge'):
            q_ = _ring_xy(H, e['geometry'])
            for p_ in (q_[0], q_[-1]):
                k_ = (round(p_[0]), round(p_[1]))
                BRIDGE_ENDS[k_] = BRIDGE_ENDS.get(k_, 0) + 1
    # + the mapped foot paths (street.json: footway / path ways that are not sidewalks or crossings)
    feet = [e for e in _load(H, 'street.json')['elements'] if e['type'] == 'way' and e.get('geometry') and
            e.get('tags', {}).get('highway') in ('footway', 'path') and
            e.get('tags', {}).get('footway') not in ('sidewalk', 'crossing', 'traffic_island')]
    for e in misc['elements'] + feet:
        t = e.get('tags', {})
        kind = t.get('highway') or ('tram' if t.get('railway') == 'tram' else None)
        if e['type'] != 'way' or not kind or not e.get('geometry'):
            continue
        if 'schody' in t.get('name', '').lower() or kind == 'steps':
            continue                              # stairways (Zamocke schody): built by the fortress module
        if t.get('tunnel') in ('yes', 'building_passage', 'culvert') or t.get('covered') == 'yes' or \
                (_num(t.get('layer'), 0) or 0) < 0 or t.get('location') == 'underground':
            continue                              # e.g. the tram tunnel under the castle hill (411125992/3)
        pts = _ring_xy(H, e['geometry'])
        if len(pts) < 2:
            continue
        if not (t.get('bridge') or t.get('man_made') == 'bridge') and t.get('highway') in ('footway', 'path') and \
                any(abs(p_[0] - k_[0]) < 6 and abs(p_[1] - k_[1]) < 6 for p_ in pts for k_ in BRIDGE_ENDS):
            continue                              # foot path at a footbridge end: the deck + street cover it
        if not (t.get('bridge') or t.get('man_made') == 'bridge') and \
                sum(math.hypot(b_[0] - a_[0], b_[1] - a_[1]) for a_, b_ in zip(pts, pts[1:])) < 8.0 and \
                any(BRIDGE_ENDS.get((round(p_[0]), round(p_[1])), 0) for p_ in (pts[0], pts[-1])):
            continue                              # stub between a bridge end and the street (deck covers it)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        d = math.hypot(cx, cy)
        bridge = t.get('bridge') in ('yes', 'viaduct', 'movable') or t.get('man_made') == 'bridge'
        main = kind in ('trunk', 'primary', 'secondary', 'tertiary', 'tram') or 'nábrežie' in t.get('name', '') or \
            t.get('name', '').startswith(PROP_STREETS)
        foot = kind in ('footway', 'path', 'cycleway', 'bridleway') and t.get('footway') not in ('sidewalk', 'crossing') \
            and in_walk(cx, cy)                   # mapped foot paths in the walk zone: drawn as their own ribbon
        minor_ok = foot or kind not in ('footway', 'path', 'steps', 'track', 'cycleway', 'bridleway', 'corridor')
        if d < R_MIN and kind in ('pedestrian', 'living_street', 'service') and not t.get('name') and \
                (_near_flight(cx, cy, 6.0) or d < 160):
            continue                              # castle-hill paths by the stair flights: the fortress module's ground
        if not bridge and (d > R_MAX or d < (R_ROAD_NEAR if (main or minor_ok) else R_MIN)):
            continue
        if not bridge and d < R_MIN and (near_ok is None or not near_ok(-1, cx, cy)):
            continue                              # castle precinct: V1 / fortress paths
        if bridge and d > 1600:
            continue
        w = ROAD_W.get(kind, 4.0) if kind != 'tram' else 4.0      # track bed incl. the gap to the carriageway
        if foot:
            w = {'footway': 2.2, 'path': 1.6, 'cycleway': 2.2, 'bridleway': 2.0}[kind]
        if kind != 'tram':                        # carriageway from the tags where mapped
            if _num(t.get('width')):
                w = max(2.5, min(30.0, _num(t.get('width'))))
            elif _num(t.get('lanes')) and kind not in ('pedestrian', 'living_street', 'service'):
                w = _num(t.get('lanes')) * 3.2 + 0.5
        mat = 'cobbles' if kind in ('pedestrian', 'living_street') else 'v2_asphalt'
        if foot:
            mat = 'cobbles' if math.hypot(cx - SHOP_CENTRE[0], cy - SHOP_CENTRE[1]) < OLD_TOWN_R else 'v2_slabs'
        # densify so the ribbon follows the coarse far terrain
        dense = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            k = max(1, int(L / (2.0 if in_walk(a[0], a[1]) else 8.0)))
            dense += [(a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k) for j in range(1, k + 1)]
        lanes = int(_num(t.get('lanes'), 2 if kind in ('trunk', 'primary', 'secondary', 'tertiary') else 0) or 0)
        marked = kind in ('trunk', 'primary', 'secondary', 'tertiary', 'unclassified') and lanes >= 2 and d < 1100
        lines, acc_ = [], 0.0
        if marked:
            lw = (w - 0.6) / lanes
            lines = [(-(w / 2 - 0.35), False), (w / 2 - 0.35, False)]
            for k in range(1, lanes):
                off = -(w - 0.6) / 2 + k * lw
                centre = t.get('oneway') != 'yes' and k == lanes // 2 and lanes % 2 == 0
                lines.append((off, not centre))
            n_mk[0] += 1
        if not bridge:
            for q_ in (pts[0], pts[-1]):          # junction pads so ribbons meeting at an angle leave no gaps
                JUNC.setdefault((round(q_[0], 1), round(q_[1], 1)), []).append((w, mat))
        if bridge:
            zs = _bridge_profile(G, dense)
            n_br += 1

        else:
            zs = [G(*p) + lift(p[0], p[1], 'tram' if kind == 'tram' else 'road') for p in dense]
        dlt = [0.0] * len(dense)
        slope_way = not bridge and len(dense) > 4 and in_walk(cx, cy) and math.hypot(cx, cy) < PODHRADIE_R and \
            kind in ('service', 'pedestrian', 'footway', 'path', 'living_street', 'residential')
        if not bridge and e['id'] == 27570381 and len(dense) > 6:
            # service lane on the castle_to_danube bank: ~6 m moving average of its own profile, ends kept
            gz_ = [G(*p) for p in dense]
            for i in range(2, len(dense) - 2):
                win = gz_[max(0, i - 3):i + 4]
                dlt[i] = max(-0.5, min(0.5, sum(win) / len(win) - gz_[i]))
        if False and slope_way and not t.get('name', '').startswith(GRADED_STREETS):
            # Podhradie lanes and paths on the hillside: 14 m moving-average profile, cut/fill up to 0.6 m
            # (the terrain under the ribbon is cut below it afterwards in _terrain_cuts)
            gz_ = [G(*p) for p in dense]
            for i in range(len(dense)):
                win = gz_[max(0, i - 7):i + 8]
                dlt[i] = max(-0.6, min(0.6, sum(win) / len(win) - gz_[i]))
                if dlt[i] > 0 and _in_bld(dense[i][0], dense[i][1], w / 2 + 2.0):
                    dlt[i] = 0.0
        if not bridge and t.get('name', '').startswith(GRADED_STREETS) and len(dense) > 4:
            # graded longitudinal profile: centre line = 12 m moving average of the terrain, at most
            # 0.25 m cut / fill against the ground (the corrugated lidar surface no longer shows in the road)
            gz_ = [G(*p) for p in dense]
            for i in range(len(dense)):
                if not in_walk(*dense[i]):
                    continue
                win = gz_[max(0, i - 3):i + 4]
                dlt[i] = max(-0.08, min(0.25, sum(win) / len(win) - gz_[i]))   # (cut limited: the terrain itself is not lowered)
                if dlt[i] > 0 and _in_bld(dense[i][0], dense[i][1], w / 2 + 2.0):
                    dlt[i] = 0.0                  # no fill against house fronts (cut only there)
        for i in range(len(dense) - 1):
            a, b = Vector(dense[i]), Vector(dense[i + 1])
            if (b - a).length < 0.05:
                continue
            dd = (b - a).normalized()
            nn = Vector((-dd.y, dd.x)) * (w / 2)
            za, zb = zs[i], zs[i + 1]
            if not bridge and (mat == 'cobbles' or foot) and in_walk(a.x, a.y) and _in_carriage(*((a + b) / 2), -0.3):
                continue                          # pedestrian setts stop at the carriageway edge
            if not bridge and FLIGHTS and (_near_flight(*((a + b) / 2), 2.5) or _near_flight(*(a + nn), 1.5) or _near_flight(*(a - nn), 1.5)):
                continue                          # fortress stair flights / their aprons: their ground
            if not bridge and math.hypot(a.x, a.y) < R_MIN and fort_ground((a + b) / 2):
                continue                          # fortress / castle ground already here (Vienna gate forecourt etc.)
            if not bridge and (in_precinct(*((a + b) / 2)) or in_precinct(*(a + nn)) or in_precinct(*(a - nn))):
                continue                          # the castle precinct's own ground / ramps (fortress module)
            if bridge:
                q = [Vector((*(a - nn), za)), Vector((*(b - nn), zb)), Vector((*(b + nn), zb)), Vector((*(a + nn), za))]
            else:                                 # corners follow the terrain across the slope (no lips)
                lk = lift(a.x, a.y, 'tram' if kind == 'tram' else 'road')
                ns = max(2 if (w < 6 and math.hypot(a.x, a.y) < PODHRADIE_R) else 1, int(w / 4.0)) if in_walk(a.x, a.y) else 1   # strips across
                if in_walk(a.x, a.y) and w <= 6.5 and kind in ('pedestrian', 'living_street', 'service', 'footway', 'path') and \
                        abs(G(a.x, a.y) - (G(*(a + nn)) + G(*(a - nn))) / 2) > 0.08:
                    ns = max(ns, int(math.ceil(w / 1.5)))   # convex / concave cross-section: follow it (no lane under the bank)
                # main roads / tram beds: +1.25 m each side so medians and gaps to the track bed close
                grow = (1.0 + 1.25 / max(w / 2, 0.5)) if (in_walk(a.x, a.y) and kind in ('trunk', 'primary', 'secondary', 'tertiary', 'tram')) else 1.0
                da, db = dlt[i], dlt[i + 1]
                RIBS.append((tuple(a), tuple(b), w / 2 * grow, G(*a) + lk + da, G(*b) + lk + db))
                for j_ in range(ns):
                    f0, f1 = (-1 + 2 * j_ / ns) * grow, (-1 + 2 * (j_ + 1) / ns) * grow
                    cs_ = (a + nn * f0, b + nn * f0, b + nn * f1, a + nn * f1)
                    rmb.poly([Vector((*c_, G(*c_) + lk + dd_)) for c_, dd_ in zip(cs_, (da, db, db, da))], mat)
                if in_walk(a.x, a.y):
                    _skirts(rmb, G, a + nn * -grow, b + nn * -grow, a + nn * grow, b + nn * grow, lk, mat, Vector, dz=(da, db))
                q = None
            if q is not None:
                bmb.poly(q, mat)
            if not bridge and in_walk(a.x, a.y) and kind not in ('tram',) and L_seg_ok(a, b):
                # hillside streets: retaining wall where the bank rises beside the kerb, railing where it drops
                for sgn in (-1, 1):
                    e0, e1 = a + nn * sgn, b + nn * sgn
                    m_ = (e0 + e1) / 2
                    g0 = G(m_.x, m_.y)
                    side = nn.normalized() * sgn
                    rise = G(*(m_ + side * 2.5)) - g0
                    if (rise > 1.2 or rise < -1.5) and (_in_bld(*(m_ + side * 1.5)) or _in_bld(*e0) or _in_bld(*e1)):
                        continue                  # building frontage / entrance here, no wall or railing
                    if rise > 1.2:
                        top_ = g0 + min(rise, 6.0) + 0.3
                        H['seg_box'](rmb, e0 if sgn < 0 else e1, e1 if sgn < 0 else e0, -0.45, 0.0, g0 - 0.5, top_, 'stone')
                    elif rise < -1.0 and not _hwy_near(*(m_ + side * 1.2), 0.8):
                        # drop > 1 m beside the road: railing on the kerb line, post at every ~2 m segment start,
                        # top rail and mid rail follow the road surface (sloped quads between the posts)
                        lk_ = lift(a.x, a.y, 'road')
                        z0r, z1r = G(*e0) + lk_, G(*e1) + lk_
                        H['_prism'](rmb, Vector((*e0, z0r - 0.1)), Vector((*e0, z0r + 1.05)), 0.035, 0.035, 'v2_iron', seg=4)
                        for hr_ in (1.0, 0.5):
                            rmb.poly([Vector((*e0, z0r + hr_)), Vector((*e1, z1r + hr_)), Vector((*e1, z1r + hr_ + 0.05)), Vector((*e0, z0r + hr_ + 0.05))], 'v2_iron')
                            rmb.poly([Vector((*e1, z1r + hr_)), Vector((*e0, z0r + hr_)), Vector((*e0, z0r + hr_ + 0.05)), Vector((*e1, z1r + hr_ + 0.05))], 'v2_iron')

            if marked:                            # lane markings: solid edge lines, dashed lane dividers
                tgt = bmb if bridge else rmb
                L_ = (b - a).length
                for off, dashed in lines:
                    o = nn.normalized() * off
                    seg_ = [(0.0, L_)] if not dashed else [(u0, min(u0 + 3.0, L_)) for u0 in
                                                          [k * 9.0 - (acc_ % 9.0) for k in range(int(L_ / 9.0) + 2)] if u0 < L_ and u0 + 3.0 > 0]
                    for u0, u1 in seg_:
                        u0 = max(u0, 0.0)
                        p0, p1 = a + dd * u0 + o, a + dd * u1 + o
                        if bridge:
                            z0_, z1_ = za + (zb - za) * u0 / L_ + 0.02, za + (zb - za) * u1 / L_ + 0.02
                        else:
                            z0_, z1_ = G(*p0) + lift(p0.x, p0.y, 'road') + 0.02, G(*p1) + lift(p1.x, p1.y, 'road') + 0.02
                        rw = Vector((-dd.y, dd.x)) * 0.07
                        tgt.poly([Vector((*(p0 - rw), z0_)), Vector((*(p1 - rw), z1_)), Vector((*(p1 + rw), z1_)), Vector((*(p0 + rw), z0_))], 'v2_paint')
                acc_ += L_
            if kind == 'tram':                    # rails (standard gauge) on the track bed
                for o_ in (-0.72, 0.72):
                    c0_, c1_ = a + nn.normalized() * o_, b + nn.normalized() * o_
                    rn = nn.normalized() * 0.05
                    (bmb if bridge else rmb).poly([Vector((*(c0_ - rn), za + 0.04)), Vector((*(c1_ - rn), zb + 0.04)),
                                                   Vector((*(c1_ + rn), zb + 0.04)), Vector((*(c0_ + rn), za + 0.04))], 'cobbles')   # shares the setts surface
            if bridge:
                # light concrete soffit under the deck (seen from the street below)
                bmb.poly([Vector((*(a + nn), za - 1.2)), Vector((*(b + nn), zb - 1.2)), Vector((*(b - nn), zb - 1.2)), Vector((*(a - nn), za - 1.2))], 'concrete')
                # deck edge beams + parapets
                for s in (-1, 1):
                    e0, e1 = a + nn * s, b + nn * s
                    bmb.poly([Vector((*e0, za - 1.2)), Vector((*e1, zb - 1.2)), Vector((*e1, zb)), Vector((*e0, za))], 'concrete')
                    bmb.poly([Vector((*e0, za)), Vector((*e1, zb)), Vector((*e1, zb + 1.0)), Vector((*e0, za + 1.0))], 'metal')
                # piers where the deck is high above water
                if t.get('name') == 'Most SNP':
                    SNP.setdefault('segs', []).append((a.copy(), b.copy(), za, zb))
                if i % 8 == 0 and G(*a) < G.water + 1.0 and t.get('name') != 'Most SNP':
                    c = a
                    bmb.box([c - nn * 0.9 - dd * 1.2, c + nn * 0.9 - dd * 1.2, c + nn * 0.9 + dd * 1.2, c - nn * 0.9 + dd * 1.2],
                            G.water - 3.0, za - 1.2, 'concrete')
                elif i % 6 == 0 and za - G(*a) > 2.5 and not _hwy_near(a.x, a.y, w / 2 + 2.5):   # ramp piers, clear of walk lines
                    for sg_ in (-0.55, 0.55):
                        c = a + nn * sg_
                        bmb.box([c - nn.normalized() * 0.5 - dd * 0.5, c + nn.normalized() * 0.5 - dd * 0.5,
                                 c + nn.normalized() * 0.5 + dd * 0.5, c - nn.normalized() * 0.5 + dd * 0.5],
                                G(*c) - 0.5, za - 1.2, 'concrete')
                if True:
                    for s in (-1, 1):                    # steel crash barrier inside the parapet
                        e0, e1 = a + nn * s - nn.normalized() * 0.4 * s, b + nn * s - nn.normalized() * 0.4 * s
                        bmb.poly([Vector((*e0, za + 0.45)), Vector((*e1, zb + 0.45)), Vector((*e1, zb + 0.75)), Vector((*e0, za + 0.75))], 'metal')
    for (x, y), ws in JUNC.items():
        if len(ws) < 2 or math.hypot(x, y) > R_MAX or in_precinct(x, y) or \
                (math.hypot(x, y) < R_MIN and (_near_flight(x, y, 3.0) or fort_ground(Vector((x, y))))):
            continue
        rad = max(w_ for w_, m_ in ws) / 2
        mat = 'v2_asphalt' if any(m_ == 'v2_asphalt' for w_, m_ in ws) else ws[0][1]
        lk = lift(x, y, 'road')
        ring = [(x + math.cos(k * math.pi / 4) * rad, y + math.sin(k * math.pi / 4) * rad) for k in range(8)]
        ring = [Vector((px_, py_, G(px_, py_) + lk)) for px_, py_ in ring]
        rmb.poly(ring, mat)
    print('v2_city bridge ways', n_br, 'marked roads', n_mk[0], 'junction pads', sum(1 for v in JUNC.values() if len(v) > 1))
    return rmb.build(coll) + bmb.build(coll)


def _lm(fn, *args):
    """Landmarks modelled from photos live in v2_landmarks.py (own file, own fork)."""
    import importlib
    import v2_landmarks
    importlib.reload(v2_landmarks)
    try:
        return getattr(v2_landmarks, fn)(*args) or []
    except Exception:
        import traceback
        print('V2 LANDMARK FAILED', fn)
        traceback.print_exc()
        return []


_OG = []
_TT = [None]
N_ROOF = {'pitched': 0, 'flat': 0}
FLAT_TYPES = ('ruins', 'parking', 'garage', 'garages', 'industrial', 'warehouse', 'retail', 'commercial', 'supermarket', 'hangar')
ORTHO_ROOF_R = 1500.0     # footprints classified from the orthophotos (both images cover this)
DECOR_IDS = (146009, 189440, 16609274, 38539540, 39259061, 75070305, 243353518)
_OPX = {}


def _ortho_px(H, name):
    """Orthophoto pixels (h, w, 3) float32, cached; row 0 = south edge (Blender pixel order)."""
    if name in _OPX:
        return _OPX[name]
    import bpy
    import numpy as np
    path = os.path.join(H['DATA'], name)
    if not os.path.exists(path):
        _OPX[name] = None
        return None
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    _OPX[name] = px.reshape(h, w, 4)[..., :3].copy()
    return _OPX[name]


def _roof_from_ortho(H, T, r):
    """Classify a footprint's roof from the orthophoto: ('pitched', srgb) for tiled (reddish/brown) roofs,
    ('flat', srgb) for grey / dark / white membrane roofs, None when unsure (mostly tree-covered).
    Samples a jittered grid inside the footprint shrunk 25 % toward its centroid (ortho lean, eaves)."""
    import numpy as np
    cx = sum(p[0] for p in r) / len(r)
    cy = sum(p[1] for p in r) / len(r)
    if T.x0 + 5 < cx < T.x1 - 5 and T.y0 + 5 < cy < T.y1 - 5:
        px, bb = _ortho_px(H, 'ortho4k.jpg'), (T.x0, T.y0, T.x1, T.y1)
    else:
        x0, y0 = H['to_local'](48.1288, 17.0801)
        x1, y1 = H['to_local'](48.1558, 17.1201)
        px, bb = _ortho_px(H, 'ortho_far.jpg'), (x0, y0, x1, y1)
    if px is None:
        return None
    h, w = px.shape[:2]
    inner = [(cx + (p[0] - cx) * 0.75, cy + (p[1] - cy) * 0.75) for p in r]
    xs, ys = [p[0] for p in inner], [p[1] for p in inner]
    step = max(0.8, math.sqrt(abs(_area(inner))) / 9.0)
    pp = H['point_in_poly']
    smp = []
    y = min(ys) + step / 2
    while y < max(ys):
        x = min(xs) + step / 2
        while x < max(xs):
            if pp(x, y, inner):
                i = int((x - bb[0]) / (bb[2] - bb[0]) * w)
                j = int((y - bb[1]) / (bb[3] - bb[1]) * h)
                if 0 <= i < w and 0 <= j < h:
                    smp.append(px[j, i])
            x += step
        y += step
    if len(smp) < 4:
        return None
    a = np.array(smp)
    rr, gg, bb_ = a[:, 0], a[:, 1], a[:, 2]
    veg = (gg > rr * 1.05) & (gg > bb_ * 1.05)
    if veg.mean() > 0.6:
        return 'green', None
    a, rr, gg, bb_ = a[~veg], rr[~veg], gg[~veg], bb_[~veg]
    red = (rr > gg * 1.12) & (rr > bb_ * 1.15) & (rr > 0.15)
    if red.mean() > 0.12:              # shaded slopes, chimneys, skylights and courtyards dilute the tiles
        return 'pitched', tuple(float(v) for v in np.median(a[red], 0))
    return 'flat', tuple(float(v) for v in np.median(a, 0))


def _ortho_green(H):
    """Vegetation mask from the wide orthophoto: (mask, x0, y0, x1, y1, w, h) or None."""
    if _OG:
        return _OG[0]
    import bpy
    import numpy as np
    path = os.path.join(H['DATA'], 'ortho_far.jpg')
    if not os.path.exists(path):
        return None
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[..., :3]
    r_, g_, b_ = px[..., 0], px[..., 1], px[..., 2]
    green = (g_ > r_ * 1.04) & (g_ > b_ * 1.05) & (px.mean(-1) < 0.44)
    x0, y0 = H['to_local'](48.1288, 17.0801)
    x1, y1 = H['to_local'](48.1558, 17.1201)
    _OG.append((green, x0, y0, x1, y1, w, h))
    return _OG[0]


def _edge_dist(x, y, poly):
    best = 1e9
    for i in range(len(poly)):
        a, b = poly[i - 1], poly[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
        best = min(best, math.hypot(x - a[0] - k * dx, y - a[1] - k * dy))
    return best


SQUARE_C, SQUARE_R = (612.0, 135.0), 42.0      # Hlavne namestie (fountain at the centre)


def _paving(H, G, streets, footprints, misc=None):
    """Ground cover so the orthophoto never shows at eye level: the whole walkable centre (and the Old Town
    core beyond it) gets setts (Old Town), concrete slabs (elsewhere), gravel under tree rows along paths
    and lawn on the ortho-green ground. Cells that already carry castle / fortress ground are left alone."""
    import bpy
    from mathutils.bvhtree import BVHTree
    Vector = H['Vector']
    pp = H['point_in_poly']
    mb = streets
    grid = {}
    for poly in footprints:
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        if in_walk(sum(xs) / len(xs), sum(ys) / len(ys)) and _hwy_hits(poly, pp):
            continue                              # walk-through (no-collision) footprints: pave under them
        for gx in range(int(min(xs) // 25), int(max(xs) // 25) + 1):
            for gy in range(int(min(ys) // 25), int(max(ys) // 25) + 1):
                grid.setdefault((gx, gy), []).append(poly)
    dg = bpy.context.evaluated_depsgraph_get()
    other = [(BVHTree.FromObject(o, dg), o.name.startswith('Fort_')) for o in bpy.data.objects
             if o.type == 'MESH' and not o.name.endswith('-colonly') and o.name.startswith(('Fort_', 'Ground_Detail', 'Steps', 'Paving', 'Garden', 'Courtyard', 'Terrace'))]
    river = _far_river_rings(H, misc) if misc else []
    flights = FLIGHTS
    og = _ortho_green(H)
    C, step = SHOP_CENTRE, 4.0
    w_ = WALK[0]
    bx0, by0 = min(C[0] - SHOP_R, w_[0] if w_ else 1e9), min(C[1] - SHOP_R, w_[1] if w_ else 1e9)
    bx1, by1 = max(C[0] + SHOP_R, w_[2] if w_ else -1e9), max(C[1] + SHOP_R, w_[3] if w_ else -1e9)
    nx, ny = int((bx1 - bx0) / step), int((by1 - by0) / step)
    D = Vector((0, 0, -1))
    paved = set()
    ter_ = [(BVHTree.FromObject(o, dg), o) for o in bpy.data.objects if o.name in ('Terrain-col', 'Terrain_Centre-col')]

    def slope_grass(x, y):
        for bv, ob in ter_:
            h_ = bv.ray_cast(Vector((x, y, 500.0)), D)
            if h_[0] is not None:
                ms = ob.material_slots
                return bool(ms) and 'ortho' not in ms[ob.data.polygons[h_[2]].material_index].name
        return False
    edge_cells = set()
    rgrid = {}
    for rv in river:
        xs_, ys_ = [q[0] for q in rv], [q[1] for q in rv]
        if max(xs_) < bx0 - 20 or min(xs_) > bx1 + 20 or max(ys_) < by0 - 20 or min(ys_) > by1 + 20:
            continue
        for gx in range(int(max(min(xs_), bx0 - 20) // 50), int(min(max(xs_), bx1 + 20) // 50) + 1):
            for gy in range(int(max(min(ys_), by0 - 20) // 50), int(min(max(ys_), by1 + 20) // 50) + 1):
                rgrid.setdefault((gx, gy), []).append(rv)

    def _wet(x, y):                               # inside the riverbank, or within 2.5 m of it (quay top)
        for rv in rgrid.get((int(x // 50), int(y // 50)), ()):
            if pp(x, y, rv) or _edge_dist(x, y, rv) < 2.5:
                return True
        return False

    def kind(x, y):
        walk = in_walk(x, y)
        if not walk and math.hypot(x - C[0], y - C[1]) > SHOP_R:
            return None
        d = math.hypot(x, y)
        if d < (R_NEAR if walk else R_MIN + 10) or in_precinct(x, y) or (d < R_MIN and x < 0):
            return None                           # (castle-hill west / Vienna gate: fortress ground + roads only)
        for q in grid.get((int(x // 25), int(y // 25)), ()):
            if pp(x, y, q) and _edge_dist(x, y, q) > 2.5 and \
                    not any(pp(x, y, hr) and _edge_dist(x, y, hr) > 0.5 for hl in HOLES.values() for hr in hl
                            if abs(hr[0][0] - x) < 60 and abs(hr[0][1] - y) < 60):
                return None                       # (cells reaching under a wall close the plinth gap; courtyards paved)
        g = G(x, y)
        if any(pp(x, y, f) for f in flights):
            # inside a fortress descent footprint: pave only where no fortress mesh at all lies below
            # (their walk strips there are invisible colliders on bare terrain; real flights stay open)
            for bv, fort in other:
                if fort and any(bv.ray_cast(Vector((x + ox, y + oy, g + 6.0)), D, 16.0)[0] is not None
                                for ox, oy in ((0, 0), (-2, -2), (2, -2), (2, 2), (-2, 2))):
                    return None
        if g < G.water + 1.0 or _wet(x, y):
            return None
        for bv, fort in other:                    # castle / fortress / V1 ground already here
            hit = bv.ray_cast(Vector((x, y, g + 3.0)), D, 4.0)
            if hit[0] is not None and hit[0].z > g - (0.25 if fort else 0.05):   # (sunk = hidden, ignore)
                return None
            if fort:                              # whole 4 m cell clear of fortress ground (corners too)
                for ox, oy in ((-2, -2), (2, -2), (2, 2), (-2, 2)):
                    hc = bv.ray_cast(Vector((x + ox, y + oy, g + 6.0)), D, 10.0)[0]
                    if hc is not None and hc.z > G(x + ox, y + oy) - 0.25:
                        edge_cells.add((round(x, 2), round(y, 2)))
                        return None                       # (paved later in 1 m pieces up to the fortress edge)
        green = False
        if og is not None:
            gm, x0, y0, x1, y1, w, h = og
            i, j = int((x - x0) / (x1 - x0) * w), int((y - y0) / (y1 - y0) * h)
            green = 2 <= i < w - 2 and 2 <= j < h - 2 and gm[j - 2:j + 3, i - 2:i + 3].mean() > 0.6
        if green and math.hypot(x - C[0], y - C[1]) < OLD_TOWN_R and _in_street(x, y):
            green = False                         # Old Town street: paved to the facades
        if green and CATHEDRAL in DECOR and any(math.hypot(x - q[0], y - q[1]) < 30 for q in DECOR[CATHEDRAL][0]):
            green = False                         # Rudnayovo nam. forecourt round St Martin: paved
        if green:
            if not walk:
                return None
            return 'gravel_white' if _hwy_near(x, y, 3.5) else 'grass'
        dq = math.hypot(x - SQUARE_C[0], y - SQUARE_C[1])
        if dq < SQUARE_R:                         # main square: granite bands in a grid, rings round the fountain
            # large beige/grey stone slabs with darker sett bands in a grid and a ring round the fountain
            if 7.0 < dq < 9.5:                    # sett ring round the fountain, beige stone slab field elsewhere
                return 'cobbles'
            return 'v2_squareslab'
        if math.hypot(x, y) < PODHRADIE_R and math.hypot(x - C[0], y - C[1]) > 260 and not _in_street(x, y):
            # Podhradie slopes away from the streets: dry grass / scrub, bare limestone where it is steep
            sl = abs(G(x + 2, y) - G(x - 2, y)) + abs(G(x, y + 2) - G(x, y - 2))
            near_dom = CATHEDRAL in DECOR and any(math.hypot(x - q[0], y - q[1]) < 40 for q in DECOR[CATHEDRAL][0][::2])
            if not near_dom:                      # (Rudnayovo nam. round the cathedral stays paved)
                return 'grass'                    # (bare-rock cells read as angular patches)
        if walk and not _in_street(x, y) and abs(G(x + 2, y) - G(x - 2, y)) + abs(G(x, y + 2) - G(x, y - 2)) > 1.4:
            return 'grass'                        # steep bank: no paving cell (left to the terrain)
        dc = math.hypot(x - C[0], y - C[1])
        dom_ = CATHEDRAL in DECOR and any(math.hypot(x - q[0], y - q[1]) < 30 for q in DECOR[CATHEDRAL][0])
        if dc < 260 or dom_ or (dc < OLD_TOWN_R and _in_street(x, y)):
            return 'cobbles'
        return 'v2_slabs' if _in_street(x, y) else 'grass'      # no slab fields over lawns away from streets
    n = 0
    KG = [[kind(bx0 + (ix + 0.5) * step, by0 + (jy + 0.5) * step) for ix in range(nx)] for jy in range(ny)]
    # continuous verges / promenades: grass vs paving by a 3x3 majority (no 4 m checkerboard)
    soft = ('grass', 'gravel_white')
    for _ in range(2):
        K2 = [r_[:] for r_ in KG]
        for jy in range(1, ny - 1):
            for ix in range(1, nx - 1):
                c_ = KG[jy][ix]
                if c_ is None:
                    continue
                nb_ = [KG[jy + dy][ix + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
                ng = sum(1 for v in nb_ if v in soft)
                npv = sum(1 for v in nb_ if v is not None and v not in soft)
                if c_ in soft and npv >= 6:
                    K2[jy][ix] = 'v2_slabs' if 'v2_slabs' in nb_ else 'cobbles'
                elif c_ not in soft and ng >= 6:
                    K2[jy][ix] = 'grass'
        KG = K2
    # orphan paving (single cells / 1-cell fingers with < 2 paved neighbours) in the walk zone: left as ground
    for jy in range(1, ny - 1):
        for ix in range(1, nx - 1):
            c_ = KG[jy][ix]
            if c_ in (None, 'grass', 'gravel_white'):
                continue
            xc, yc = bx0 + (ix + 0.5) * step, by0 + (jy + 0.5) * step
            if not in_walk(xc, yc):
                continue
            nb_ = sum(1 for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)) if KG[jy + dy][ix + dx] not in (None, 'grass', 'gravel_white'))
            if nb_ < 2 and not _in_street(xc, yc):
                KG[jy][ix] = None
    for jy in range(ny):
        y = by0 + (jy + 0.5) * step
        row = KG[jy]
        ix = 0
        while ix < nx:
            xc_ = bx0 + (ix + 0.5) * step
            mixed_ = row[ix] == 'grass' and in_walk(xc_, y) and math.hypot(xc_ - C[0], y - C[1]) > 260 and \
                len({_in_street(xc_ + ox_, y + oy_) for ox_, oy_ in ((-2, -2), (2, -2), (2, 2), (-2, 2))}) > 1
            if row[ix] is None or (row[ix] == 'grass' and not mixed_ and not _in_street(xc_, y) and slope_grass(xc_, y)):
                ix += 1                           # fortress grass-textured slope: leave that terrain itself
                continue
            k = ix
            walk = in_walk(bx0 + ix * step, y)
            while k < nx and row[k] == row[ix] and k - ix < (1 if walk else 6):
                k += 1
            xa, xb, ya, yb = bx0 + ix * step, bx0 + k * step, y - step / 2, y + step / 2
            lp = lift((xa + xb) / 2, y, 'pave')
            xm, ym = (xa + xb) / 2, (ya + yb) / 2
            cin = [_in_street(*c_) for c_ in ((xa, ya), (xb, ya), (xb, yb), (xa, yb))] if \
                (walk and k - ix == 1 and math.hypot(xm - C[0], ym - C[1]) > 260) else None
            if cin is not None and any(cin) and not all(cin) and row[ix] in ('v2_slabs', 'cobbles', 'grass'):
                # street-band boundary: grass base + paving clipped to the band (polygon, not the whole cell)
                if row[ix] == 'grass' or not slope_grass(xm, ym):
                    mb.poly([Vector((xa, ya, G(xa, ya) + lp - 0.02)), Vector((xb, ya, G(xb, ya) + lp - 0.02)),
                             Vector((xb, yb, G(xb, yb) + lp - 0.02)), Vector((xa, yb, G(xa, yb) + lp - 0.02))], 'grass')
                ring_ = _clip_cell_to_street((xa, ya), (xb, ya), (xb, yb), (xa, yb))
                if len(ring_) >= 3:
                    pm = 'v2_slabs' if row[ix] == 'grass' else row[ix]
                    z00, z10, z11, z01 = G(xa, ya), G(xb, ya), G(xb, yb), G(xa, yb)

                    def zb_(q):                   # bilinear from the cell corners = the same surface as full cells
                        u_, v_ = (q[0] - xa) / (xb - xa), (q[1] - ya) / (yb - ya)
                        return (z00 * (1 - u_) + z10 * u_) * (1 - v_) + (z01 * (1 - u_) + z11 * u_) * v_
                    pg_ = [Vector((q[0], q[1], zb_(q) + lp)) for q in ring_]      # one n-gon (convex-ish piece)
                    if (pg_[1] - pg_[0]).cross(pg_[2] - pg_[0]).z < 0:
                        pg_.reverse()
                    mb.poly(pg_, pm)
            else:
                mb.poly([Vector((xa, ya, G(xa, ya) + lp)), Vector((xb, ya, G(xb, ya) + lp)),
                         Vector((xb, yb, G(xb, yb) + lp)), Vector((xa, yb, G(xa, yb) + lp))], row[ix])
            for c_ in range(ix, k):
                paved.add((c_, jy))
            n += 1
            ix = k
    # cells touching fortress ground (stair flights, gate aprons): pave the 1 m pieces that are clear of it,
    # so the setts reach the flight edge instead of stopping a whole 4 m cell short (no terrain strip)
    forts = [bv for bv, fort in other if fort]
    ne = 0
    for (x, y) in edge_cells:
        oldt = math.hypot(x - C[0], y - C[1]) < OLD_TOWN_R
        if _near_flight(x, y, 4.0) or math.hypot(x, y) < R_MIN:
            continue                              # no filler pieces beside the fortress descents / castle ring
        if math.hypot(x - C[0], y - C[1]) > 260 and not _in_street(x, y):
            continue                              # off-street slope: no slab fragments against fortress edges
        mat = 'cobbles' if oldt else 'v2_slabs'
        for i in range(4):
            for j in range(4):
                x0_, y0_ = x - 2 + i, y - 2 + j
                cs = [(x0_, y0_), (x0_ + 1, y0_), (x0_ + 1, y0_ + 1), (x0_, y0_ + 1)]
                if any((lambda h_: h_ is not None and h_.z > G(cx_, cy_) - 0.25)(bv.ray_cast(Vector((cx_, cy_, G(cx_, cy_) + 6.0)), D, 10.0)[0])
                       for bv in forts for cx_, cy_ in cs + [(x0_ + 0.5, y0_ + 0.5)]):
                    continue
                if in_precinct(x0_ + 0.5, y0_ + 0.5):
                    continue
                lp = lift(x0_, y0_, 'pave')
                zs_ = [G(cx_, cy_) for cx_, cy_ in cs]
                if max(zs_) - min(zs_) > 0.45:
                    continue                      # steep bank: no tilted slab piece
                mb.poly([Vector((cx_, cy_, z_ + lp)) for (cx_, cy_), z_ in zip(cs, zs_)], mat)
                ne += 1
    print('v2_city ground cover cells', n, 'fortress-edge pieces', ne)

    # the 4 m paving quads are planar; on uneven ground the terrain mesh pokes through their middle.
    # Under fully paved cells (walk zone) the terrain vertices are dropped 0.3 m below the paving.
    nsunk = 0
    for nm in ('Terrain-col', 'Terrain_Centre-col'):
        ob = bpy.data.objects.get(nm)
        if ob is None:
            continue
        for v in ob.data.vertices:
            x, y = v.co.x, v.co.y
            if not in_walk(x, y):
                continue
            if all((int((x + ox - bx0) // step), int((y + oy - by0) // step)) in paved
                   for ox in (-1.6, 1.6) for oy in (-1.6, 1.6)):
                v.co.z -= 0.3
                nsunk += 1
        ob.data.update()
    print('v2_city terrain vertices dropped under paving', nsunk)


def _city_walls(H, G, coll):
    """Medieval city wall along Staromestska (OSM barrier=city_wall, data/v2/city/walls.json): 2.4 m thick
    rubble-stone wall standing ~2 m above the higher (Old Town) side, outer parapet, round bastions."""
    data = _load(H, 'walls.json')
    if not data['elements']:
        return []
    Vector = H['Vector']
    CMB = _cmb_class(H)
    mb = CMB('V2City_CityWalls-col')
    n = n_gap = 0
    for e in data['elements']:
        if not e.get('geometry'):
            continue
        pts = [Vector(p) for p in _ring_xy(H, e['geometry'])]
        for a, b in zip(pts, pts[1:]):
            L = (b - a).length
            if L < 0.2:
                continue
            d = (b - a) / L
            nn = Vector((-d.y, d.x))
            k = max(1, int(L / 3.0))
            for j in range(k):
                p0, p1 = a + d * (L * j / k), a + d * (L * (j + 1) / k)
                m = (p0 + p1) / 2
                if any(_hwy_near(*(p0.lerp(p1, f_)), 2.2) for f_ in (0.0, 0.25, 0.5, 0.75, 1.0)):
                    n_gap += 1
                    continue                      # street / footway passes the wall line: open gap
                hi = max(G(*(m + nn * 4)), G(*(m - nn * 4)))
                lo = min(G(*(m + nn * 4)), G(*(m - nn * 4)), G(*m))
                top = max(hi + 2.0, lo + 6.0)
                H['seg_box'](mb, p0, p1, -1.2, 1.2, lo - 1.0, top, 'v2_rubble')
                side = 1 if G(*(m + nn * 4)) < G(*(m - nn * 4)) else -1      # parapet on the low (outer) side
                H['seg_box'](mb, p0, p1, side * 1.2, side * 0.8, top, top + 1.1, 'v2_rubble')
        n += 1
    mb.cols = [(1.0, 1.0, 1.0)] * len(mb.faces)
    print('v2_city city walls', n, 'gaps', n_gap)
    return [mb.build(coll)]


def _passages(H, G, coll, misc):
    """Arched passage openings where mapped walkways run through buildings (tunnel=building_passage,
    covered=yes): dark vaulted opening with a stone surround on both facades the way crosses."""
    Vector, seg_box = H['Vector'], H['seg_box']
    CMB = _cmb_class(H)
    mb = CMB('V2City_Passages')
    n = 0
    DONE_P = []
    src = [misc, _load(H, 'street.json')]
    for d_ in src:
        for e in d_['elements']:
            t = e.get('tags', {})
            if e['type'] != 'way' or not e.get('geometry') or not t.get('highway'):
                continue
            tagged = t.get('tunnel') == 'building_passage' or t.get('covered') == 'yes'
            pts = [Vector(p) for p in _ring_xy(H, e['geometry'])]
            for s0, s1 in zip(pts, pts[1:]):
                m = (s0 + s1) / 2
                if not in_walk(m.x, m.y):
                    continue
                if tagged and not (math.hypot(m.x, m.y) < PODHRADIE_R or _prio_near(m.x, m.y, 25.0)):
                    continue
                # tagged passages through any building; untagged ways only through the walk-through (ghost) shells
                if not tagged:
                    continue                      # only real (OSM-tagged) passages get an opening
                cand = BLD.get((int(m.x // 20), int(m.y // 20)), ())
                for poly in cand:
                    for a, b in zip(poly, poly[1:] + poly[:1]):
                        ip = H['geometry'].intersect_line_line_2d(s0, s1, Vector(a), Vector(b))
                        if ip is None:
                            continue
                        ip = Vector(ip)
                        dd = (Vector(b) - Vector(a)).normalized()
                        out = Vector((dd.y, -dd.x))
                        if _area(poly) < 0:
                            out = -out
                        gz = G(ip.x, ip.y) + 0.12
                        if any((ip - Vector(q_)).length < 3.0 for q_ in DONE_P) or in_precinct(ip.x, ip.y) or \
                                any(in_precinct(ip.x + ox_, ip.y + oy_) for ox_, oy_ in ((25, 0), (-25, 0), (0, 25), (0, -25))) or \
                                H['point_in_poly'](ip.x, ip.y, H['OUTER']):
                            continue                  # castle gates / fortress passages: open, theirs
                        DONE_P.append(tuple(ip))
                        for side in (1, -1):
                            c = ip + out * 0.03 * side
                            hw, hh = 1.7, 2.9
                            # deep reveal: stone side walls + soffit projecting 0.7 m, dark void at the wall plane
                            for sg in (-1, 1):
                                cj = c + dd * (hw * sg)
                                mb.box([cj - dd * 0.12, cj + dd * 0.12, cj + dd * 0.12 + out * 0.7 * side, cj - dd * 0.12 + out * 0.7 * side],
                                       gz - 0.1, gz + hh + hw * 0.8, 'v2_stone_church')
                            mb.box([c - dd * hw, c + dd * hw, c + dd * hw + out * 0.7 * side, c - dd * hw + out * 0.7 * side],
                                   gz + hh + hw * 0.8, gz + hh + hw * 0.8 + 0.4, 'v2_stone_church')
                            q = [Vector((*(c - dd * hw), gz)), Vector((*(c + dd * hw), gz)), Vector((*(c + dd * hw), gz + hh)), Vector((*(c - dd * hw), gz + hh))]
                            if side < 0:
                                q.reverse()
                            mb.poly(q, 'v2_void')
                            arc = [c + dd * (hw * math.cos(k * math.pi / 3)) for k in range(4)]
                            zz = [gz + hh + hw * 0.8 * math.sin(k * math.pi / 3) for k in range(4)]
                            for k in range(3):
                                tri = [Vector((*c, gz + hh)), Vector((*arc[k], zz[k])), Vector((*arc[k + 1], zz[k + 1]))]
                                mb.poly(tri if side > 0 else list(reversed(tri)), 'v2_void')
                            for sg in (-1, 1):                    # stone jambs + keystone
                                cj = c + dd * (hw + 0.15) * sg
                                mb.box([cj - dd * 0.15, cj + dd * 0.15, cj + dd * 0.15 + out * 0.12 * side, cj - dd * 0.15 + out * 0.12 * side],
                                       gz - 0.1, gz + hh, 'v2_stone_church')
                        n += 1
    mb.cols = [(1.0, 1.0, 1.0)] * len(mb.faces)
    print('v2_city passage openings', n)
    return [mb.build(coll)] if mb.faces else []


def _garden_walls(H, G, coll):
    """Podhradie garden walls, retaining walls and fences from OSM (data/v2/city/barriers.json), outside
    the castle precinct; segments on a mapped walking line are left open (gates)."""
    data = _load(H, 'barriers.json')
    if not data['elements']:
        return []
    Vector, seg_box = H['Vector'], H['seg_box']
    CMB = _cmb_class(H)
    mb = CMB('V2City_GardenWalls-col')
    n = 0
    for e in data['elements']:
        t = e.get('tags', {})
        kind = t.get('barrier')
        if kind not in ('wall', 'retaining_wall', 'fence') or not e.get('geometry'):
            continue
        pts = [Vector(p) for p in _ring_xy(H, e['geometry'])]
        for a, b in zip(pts, pts[1:]):
            L = (b - a).length
            if L < 0.3:
                continue
            k = max(1, int(L / 2.0))
            for j in range(k):
                p0, p1 = a.lerp(b, j / k), a.lerp(b, (j + 1) / k)
                m = (p0 + p1) / 2
                if in_precinct(m.x, m.y) or not in_walk(m.x, m.y) or _hwy_near(m.x, m.y, 1.6) or _in_bld(m.x, m.y, 0.3) or \
                        _near_flight(m.x, m.y) or _near_flight(p0.x, p0.y) or _near_flight(p1.x, p1.y):
                    continue
                d = (p1 - p0).normalized()
                nn = Vector((-d.y, d.x))
                g1, g2 = G(*(m + nn * 1.5)), G(*(m - nn * 1.5))
                lo, hi = min(g1, g2, G(*m)), max(g1, g2, G(*m))
                if kind == 'fence':                               # iron railing on a low plinth, following the ground
                    FENCES.append(((p0.x + p1.x) / 2, (p0.y + p1.y) / 2))
                    z0f, z1f = G(*p0), G(*p1)
                    seg_box(mb, p0, p1, -0.15, 0.15, lo - 0.3, min(z0f, z1f) + 0.35, 'stone')
                    for hr_ in (1.45, 0.45):
                        q_ = [Vector((*p0, z0f + hr_)), Vector((*p1, z1f + hr_)), Vector((*p1, z1f + hr_ + 0.05)), Vector((*p0, z0f + hr_ + 0.05))]
                        mb.poly(q_, 'v2_iron')
                        mb.poly(list(reversed(q_)), 'v2_iron')
                    mb.box([(p0.x - 0.03, p0.y - 0.03), (p0.x + 0.03, p0.y - 0.03), (p0.x + 0.03, p0.y + 0.03), (p0.x - 0.03, p0.y + 0.03)],
                           z0f - 0.1, z0f + 1.5, 'v2_iron')
                elif kind == 'retaining_wall':                    # holds the upper garden, coping on top
                    top = max(hi + 0.3, lo + 1.0)
                    seg_box(mb, p0, p1, -0.3, 0.3, lo - 0.5, top, 'concrete' if m.y < -180 else 'v2_stone_church')  # precast / ashlar
                    seg_box(mb, p0, p1, -0.35, 0.35, top, top + 0.12, 'v2_stone_church')
                else:                                             # rendered garden wall with a tile coping
                    oldtown = math.hypot(m.x - SHOP_CENTRE[0], m.y - SHOP_CENTRE[1]) < 330
                    top = hi + (0.45 if oldtown else 1.2 if _near_named(m.x, m.y, 'Mudroňova', 35.0) else 1.9)
                    seg_box(mb, p0, p1, -0.22, 0.22, lo - 0.5, top, 'v2_stone_church' if oldtown else 'plaster')
                    if _near_named(m.x, m.y, 'Mudroňova', 35.0):         # villa gardens: clipped hedge on the wall
                        seg_box(mb, p0, p1, -0.35, 0.35, top, top + 1.1, 'hedge')
                    else:
                        seg_box(mb, p0, p1, -0.3, 0.3, top, top + 0.12, 'concrete')     # grey coping
                n += 1
    mb.cols = [(1.0, 1.0, 1.0)] * len(mb.faces)
    print('v2_city garden walls / fences segments', n)
    return [mb.build(coll)] if mb.faces else []


NAMED = {}


def _near_named(x, y, name, r=12.0):
    for (a, b) in NAMED.get(name, ()):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
        if math.hypot(x - a[0] - k * dx, y - a[1] - k * dy) < r:
            return True
    return False


def _street_detail(H, G, coll, near_ok):
    """Centre + embankment street detail from OSM (data/v2/city/street.json): raised sidewalks with
    kerbs, zebra crossings. Returns (objects, lamp points, bench points) for the props pass."""
    import numpy as np
    data = _load(H, 'street.json')
    lamps, benches = [], []
    if not data['elements']:
        return [], lamps, benches
    Vector, MATS = H['Vector'], H['MATS']
    CMB = _cmb_class(H)
    mb = CMB('V2City_StreetDetail-col')
    done_cr = []
    n_sw = n_cr = 0
    for e in data['elements']:
        t = e.get('tags', {})
        if e['type'] == 'node':
            x, y = H['to_local'](e['lat'], e['lon'])
            if math.hypot(x, y) > R_NEAR and near_ok(-1, x, y):
                if t.get('highway') == 'street_lamp':
                    lamps.append((x, y))
                elif t.get('amenity') == 'bench':
                    benches.append((x, y))
            continue
        if not e.get('geometry'):
            continue
        pts = [Vector(p) for p in _ring_xy(H, e['geometry'])]
        if len(pts) < 2 or not any(math.hypot(p.x, p.y) > R_NEAR and near_ok(-1, p.x, p.y) for p in pts):
            continue
        fw = t.get('footway')
        if fw in ('sidewalk', 'traffic_island'):
            w = max(1.2, min(6.0, _num(t.get('width'), 2.4 if fw == 'sidewalk' else 2.0)))
            swmat = 'v2_slabs'
            dense = [pts[0]]
            for a, b in zip(pts, pts[1:]):
                k = max(1, int((b - a).length / 3.0))
                dense += [a.lerp(b, j / k) for j in range(1, k + 1)]
            dense = [p_ for i_, p_ in enumerate(dense) if i_ == 0 or (p_ - dense[i_ - 1]).length > 0.3]
            # mitred offsets per vertex, shared by neighbouring quads (no sawtooth at the bends)
            off = []
            for i_ in range(len(dense)):
                dp = (dense[i_] - dense[i_ - 1]).normalized() if i_ > 0 else None
                dn = (dense[i_ + 1] - dense[i_]).normalized() if i_ < len(dense) - 1 else None
                ds = [v for v in (dp, dn) if v is not None]
                if not ds:
                    off.append(Vector((0, 0)))
                    continue
                n0 = Vector((-ds[0].y, ds[0].x))
                nm = sum((Vector((-v.y, v.x)) for v in ds), Vector((0, 0))).normalized() if len(ds) == 2 else n0
                cosv = max(0.5, nm.dot(n0))
                off.append(nm * (w / 2) / cosv)
            for i_ in range(len(dense) - 1):
                a, b = dense[i_], dense[i_ + 1]
                if in_precinct(*((a + b) / 2)):
                    continue
                lk = lift(a.x, a.y, 'walk')                            # 13 cm above the carriageway
                cs = [a - off[i_], b - off[i_ + 1], b + off[i_ + 1], a + off[i_]]
                mid_ = (a + b) / 2
                if math.hypot(mid_.x, mid_.y) < R_MIN and any(
                        b_.ray_cast(Vector((mid_.x, mid_.y, G(mid_.x, mid_.y) + 2.0)), Vector((0, 0, -1)), 4.0)[0] is not None for b_ in FORTBV):
                    continue                      # fortress ground here
                if in_walk(a.x, a.y) and (abs(G(*cs[0]) - G(*cs[3])) > 0.35 or not _in_carriage(*((a + b) / 2), 6.0)):
                    continue                      # no slanted / stray sidewalk pieces (steep cross-fall, off-street)
                zc = [G(*c_) + lk for c_ in cs]
                mb.poly([Vector((*c_, z_)) for c_, z_ in zip(cs, zc)], swmat)
                for sgn, (i0, i1) in ((-1, (0, 1)), (1, (3, 2))):      # granite kerbs
                    e0, e1 = cs[i0], cs[i1]
                    f = [Vector((*e0, zc[i0] - 0.3)), Vector((*e1, zc[i1] - 0.3)), Vector((*e1, zc[i1])), Vector((*e0, zc[i0]))]
                    mb.poly(f if sgn > 0 else list(reversed(f)), 'stone')
                if in_walk(a.x, a.y):                                  # ramps where the walk meets bare ground
                    _skirts(mb, G, cs[0], cs[1], cs[3], cs[2], lk - 0.02, 'v2_slabs', Vector, out=0.6)
            n_sw += 1
        elif fw == 'crossing' or t.get('highway') == 'crossing':
            total = sum((b - a).length for a, b in zip(pts, pts[1:]))
            if total < 2.0 or total > 40.0:
                continue
            mid_ = (pts[0] + pts[-1]) / 2
            if any((mid_ - c_).length < 8.0 for c_ in done_cr):
                continue                          # one crossing per place (no overlapping zebras)
            done_cr.append(mid_)
            sv = 0.6
            segs = list(zip(pts, pts[1:]))
            while sv < total - 0.6:
                acc = 0.0
                for a, b in segs:
                    L = (b - a).length
                    if acc + L >= sv:
                        d = (b - a) / max(L, 1e-6)
                        c = a + d * (sv - acc)
                        break
                    acc += L
                nn = Vector((-d.y, d.x)) * 1.5
                if in_precinct(c.x, c.y) or not _in_carriage(c.x, c.y, -0.2):
                    sv += 1.0                     # zebra stripes only across a carriageway
                    continue
                z = G(c.x, c.y) + lift(c.x, c.y, 'road') + 0.025
                q = [c - d * 0.25 - nn, c + d * 0.25 - nn, c + d * 0.25 + nn, c - d * 0.25 + nn]
                mb.poly([Vector((*p, z)) for p in q], 'v2_paint')
                sv += 1.0
            n_cr += 1
    mb.cols = [(1.0, 1.0, 1.0)] * len(mb.faces)
    print('v2_city street detail: sidewalks', n_sw, 'crossings', n_cr, 'OSM lamps', len(lamps), 'benches', len(benches))
    return [mb.build(coll)], lamps, benches


PROP_STREETS = ('Zámocká', 'Beblavého', 'Mikulášska', 'Kapitulská', 'Židovská', 'Panská', 'Ventúrska', 'Michalská')
CARS = []           # parked-car placements [x, y, z, heading] -> out/<tag>/street_cars.json (Godot instances models)
CAR_COLOURS = ['#5A5C5E', '#202224', '#6A6D70', '#3A3C3E', '#5E1A18', '#1C2A44', '#4A4840', '#2F3E32']


AWNING_COLOURS = ['#6A2424', '#E3D8C0', '#5A2E2A', '#D8CCB0']


def _shop_dressing(H, coll, G=None):
    """Shop storeys inside the walk zone: canvas awning over the shop window, a blade sign, a stone step
    at the door (positions follow the shop texture: window 0.05-0.45, door 0.58-0.77 of a 6.4 m tile);
    cafe umbrellas on Hlavne namestie in front of the square fronts."""
    Vector, seg_box, _prism = H['Vector'], H['seg_box'], H['_prism']
    CMB = _cmb_class(H)
    mb = CMB('V2City_ShopDressing')
    for hx in AWNING_COLOURS:
        _tint('_awn_' + hx, 'v2_car', hx)
    rng = random.Random(5)

    def add(fn, *a, col=(1.0, 1.0, 1.0)):
        fn(*a)
        mb.cols += [col] * (len(mb.faces) - len(mb.cols))
    n = 0
    for a, b, gs, tiles in SHOPFRONTS:
        A, B = Vector(a), Vector(b)
        if not in_walk((A.x + B.x) / 2, (A.y + B.y) / 2):
            continue
        L = (B - A).length
        d = (B - A) / L
        out = Vector((d.y, -d.x))                 # CCW ring: right normal = outside
        tw = L / max(1, tiles)
        for k in range(max(1, tiles)):
            w0, w1 = A + d * (tw * (k + 0.05)), A + d * (tw * (k + 0.45))
            if rng.random() < 0.33:                                # at most ~1 awning in 3 shops, muted canvas
                col = TINT['_awn_' + rng.choice(AWNING_COLOURS)][1]
                z0, z1 = gs + 3.0, gs + 2.55
                q = [Vector((*w0, z0)), Vector((*w1, z0)), Vector((*(w1 + out * 1.1), z1)), Vector((*(w0 + out * 1.1), z1))]
                if (q[1] - q[0]).cross(q[3] - q[0]).z < 0:
                    q.reverse()
                add(mb.poly, q, 'v2_car', col=col)
                q2 = [Vector((*(w0 + out * 1.1), z1)), Vector((*(w1 + out * 1.1), z1)), Vector((*(w1 + out * 1.1), z1 - 0.25)), Vector((*(w0 + out * 1.1), z1 - 0.25))]
                add(mb.poly, q2, 'v2_car', col=col)                # valance
            dc = A + d * (tw * (k + 0.675))                        # door steps, risers <= 0.17 m
            gout = G(*(dc + out * 0.3)) if G else gs
            nst = max(1, min(8, int(math.ceil((gs + 0.16 - gout) / 0.17))))
            for k2 in range(nst):
                add(seg_box, mb, dc - d * 0.75, dc + d * 0.75, -(0.3 * (k2 + 1)), -(0.3 * k2), gout - 0.3, gs + 0.16 - 0.17 * k2, 'v2_stone_church')
            n += 1
        dm = ((A + B) / 2 - Vector(SQUARE_C)).length
        if dm < SQUARE_R and L > 6:                                # cafe terrace umbrellas
            for k in range(int(L // 6)):
                c = A + d * (6 * k + 3) + out * 3.5
                if (c - Vector(SQUARE_C)).length < 11:
                    continue
                zc = gs
                add(_prism, mb, Vector((c.x, c.y, zc)), Vector((c.x, c.y, zc + 2.3)), 0.04, 0.04, 'v2_iron', 4)
                add(_prism, mb, Vector((c.x, c.y, zc + 2.0)), Vector((c.x, c.y, zc + 2.6)), 1.6, 0.05, 'v2_car', 8,
                    col=TINT['_awn_#E3D8C0'][1])
    # glass cafe pavilions on Hviezdoslavovo namestie (along the square axis, clear of the mapped paths)
    pv = 0
    A0, A1 = Vector((664.0, -88.0)), Vector((716.0, -22.0))
    ax = (A1 - A0).normalized()
    sd = Vector((-ax.y, ax.x))
    for k in range(4):
        for sgn in (-1, 1):
            c = A0.lerp(A1, (k + 0.5) / 4) + sd * 9.0 * sgn
            if _hwy_near(c.x, c.y, 4.0) or _in_bld(c.x, c.y, 3.0):
                continue
            zc = G(c.x, c.y) + 0.08
            pts = [c - ax * 4 - sd * 2.5, c + ax * 4 - sd * 2.5, c + ax * 4 + sd * 2.5, c - ax * 4 + sd * 2.5]
            for i in range(4):
                p0, p1 = pts[i], pts[(i + 1) % 4]
                add(mb.poly, [Vector((*p0, zc)), Vector((*p1, zc)), Vector((*p1, zc + 3.0)), Vector((*p0, zc + 3.0))], 'glass')
                add(mb.box, [(p0.x - 0.08, p0.y - 0.08), (p0.x + 0.08, p0.y - 0.08), (p0.x + 0.08, p0.y + 0.08), (p0.x - 0.08, p0.y + 0.08)],
                    zc, zc + 3.0, 'v2_iron')
            add(mb.box, [(q_.x, q_.y) for q_ in (c - ax * 4.3 - sd * 2.8, c + ax * 4.3 - sd * 2.8, c + ax * 4.3 + sd * 2.8, c - ax * 4.3 + sd * 2.8)],
                zc + 3.0, zc + 3.3, 'v2_iron')
            pv += 1
    print('v2_city shop dressing', n, 'cafe pavilions', pv)
    return [mb.build(coll)] if mb.faces else []


def _street_props(H, misc, G, footprints, coll, osm_lamps=(), osm_benches=(), near_ok=None):
    """Street life on the lanes below the castle: lanterns, benches on the pedestrian streets and parked
    cars (two boxes) on Zamocka. One object, 4 surfaces."""
    import numpy as np
    Vector, _prism = H['Vector'], H['_prism']
    for hx in CAR_COLOURS:
        _tint('_car_' + hx, 'v2_car', hx)
    TINT['_car_glass'] = ('v2_car', (0.05, 0.06, 0.07))
    CMB = _cmb_class(H)
    mb = CMB('V2City_StreetProps')
    cmb = CMB('V2City_StreetProps-colonly')     # invisible simple blockers for the walkable centre

    def blocker(c, d, L, W, z0, z1):
        if not in_walk(c.x, c.y) or _hwy_near(c.x, c.y, max(L, W) / 2 + 0.4):
            return                                # never block a mapped walking line
        nn = Vector((-d.y, d.x))
        cmb.box([c - d * L / 2 - nn * W / 2, c + d * L / 2 - nn * W / 2, c + d * L / 2 + nn * W / 2, c - d * L / 2 + nn * W / 2], z0, z1, 'metal')
    rng = random.Random(23)
    pp = H['point_in_poly']
    grid = {}
    for poly in footprints:
        grid.setdefault((int(poly[0][0] // 50), int(poly[0][1] // 50)), []).append(poly)

    def roofed(x, y):
        c = (int(x // 50), int(y // 50))
        return any(pp(x, y, q) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid.get((c[0] + dx, c[1] + dy), ()))

    def colour(n0, col):
        mb.cols += [col] * (len(mb.faces) - len(mb.cols))

    def box(c, d, L, W, z0, z1, mat):
        nn = Vector((-d.y, d.x))
        colour(0, (1.0, 1.0, 1.0))                     # faces added so far (poles) stay white
        base, col = TINT.get(mat, (mat, (1.0, 1.0, 1.0)))
        mb.box([c - d * L / 2 - nn * W / 2, c + d * L / 2 - nn * W / 2, c + d * L / 2 + nn * W / 2, c - d * L / 2 + nn * W / 2], z0, z1, base)
        colour(0, col)

    crossings = [H['to_local'](e_['lat'], e_['lon']) for e_ in _load(H, 'street.json')['elements']
                 if e_['type'] == 'node' and e_.get('tags', {}).get('highway') == 'crossing']

    def lamp_ok(q, osm=False):
        return not any(abs(q.x - c_[0]) < 4 and abs(q.y - c_[1]) < 4 for c_ in crossings) and \
            (osm or not _hwy_near(q.x, q.y, 1.2))

    PL, PB = [], []                                          # placed lamps / benches (min spacing)

    def clear_of(q, pts_, r_):
        return not any((q.x - a_) ** 2 + (q.y - b_) ** 2 < r_ * r_ for a_, b_ in pts_)

    def lantern(q, osm=False):                               # Old Town cast-iron lantern post
        if in_precinct(q.x, q.y) or not lamp_ok(q, osm) or not clear_of(q, PL, 12.0 if not osm else 4.0) or not clear_of(q, PB, 1.5) \
                or _in_carriage(q.x, q.y, 0.3):
            return
        PL.append((q.x, q.y))
        z = G(q.x, q.y) + lift(q.x, q.y, 'walk')
        blocker(q, Vector((1, 0)), 0.3, 0.3, z - 0.2, z + 4.0)
        _prism(mb, Vector((q.x, q.y, G(q.x, q.y) - 0.15)), Vector((q.x, q.y, z + 0.6)), 0.16, 0.09, 'v2_iron', seg=5)   # fluted base
        _prism(mb, Vector((q.x, q.y, z + 0.6)), Vector((q.x, q.y, z + 3.9)), 0.07, 0.045, 'v2_iron', seg=6)
        box(q, Vector((1, 0)), 0.2, 0.2, z + 3.9, z + 4.02, 'v2_iron')
        box(q, Vector((1, 0)), 0.34, 0.34, z + 4.02, z + 4.55, 'v2_lampglass')
        _prism(mb, Vector((q.x, q.y, z + 4.55)), Vector((q.x, q.y, z + 4.95)), 0.3, 0.02, 'v2_iron', seg=4)

    def mast(q, out_):                                       # modern street-light mast on the main roads
        if in_precinct(q.x, q.y) or not lamp_ok(q) or not clear_of(q, PL, 12.0) or not clear_of(q, PB, 1.5) or _in_carriage(q.x, q.y, 0.3):
            return
        PL.append((q.x, q.y))
        z = G(q.x, q.y) + lift(q.x, q.y, 'walk')
        blocker(q, Vector((1, 0)), 0.3, 0.3, z - 0.2, z + 4.0)
        _prism(mb, Vector((q.x, q.y, G(q.x, q.y) - 0.2)), Vector((q.x, q.y, z + 8.6)), 0.12, 0.07, 'v2_iron', seg=6)
        tip = q + out_ * 1.6
        _prism(mb, Vector((q.x, q.y, z + 8.5)), Vector((tip.x, tip.y, z + 8.75)), 0.05, 0.05, 'metal', seg=4)
        box(tip, out_, 0.7, 0.28, z + 8.62, z + 8.78, 'metal')

    def bench(q, d):
        if in_precinct(q.x, q.y) or not clear_of(q, PB, 4.0) or not clear_of(q, PL, 1.5) or not clear_of(q, FENCES, 1.6):
            return
        PB.append((q.x, q.y))
        z = G(q.x, q.y) + lift(q.x, q.y, 'walk')
        nn = Vector((-d.y, d.x))
        blocker(q, d, 1.8, 0.6, z - 0.1, z + 0.9)
        for k_ in range(2):                                   # seat slats
            box(q + nn * (0.11 - k_ * 0.2), d, 1.8, 0.16, z + 0.42, z + 0.46, 'v2_timber')
        box(q - nn * 0.22, d, 1.8, 0.04, z + 0.58, z + 0.8, 'v2_timber')   # back rail
        for o_ in (-0.75, 0.75):                              # cast-iron side frames
            box(q + d * o_, d, 0.05, 0.45, G(*(q + d * o_)) - 0.1, z + 0.42, 'v2_iron')
            box(q + d * o_ - nn * 0.22, d, 0.05, 0.05, z + 0.42, z + 0.85, 'v2_iron')

    def near(q, pts, r_):
        return any(abs(q.x - p[0]) < r_ and abs(q.y - p[1]) < r_ for p in pts)
    for p in osm_lamps:
        lantern(Vector(p), osm=True)
    # bench orientation: along the nearest street segment
    segs = []
    for e in misc['elements']:
        if e['type'] == 'way' and e.get('tags', {}).get('highway') and e.get('geometry'):
            pts = _ring_xy(H, e['geometry'])
            segs += [(Vector(a), Vector(b)) for a, b in zip(pts, pts[1:]) if abs(a[0] - 300) < 1200 and abs(a[1]) < 900]
    for p in osm_benches:
        q = Vector(p)
        best = min(segs, key=lambda sg: (q - (sg[0] + sg[1]) / 2).length) if segs else None
        d = (best[1] - best[0]).normalized() if best and (best[1] - best[0]).length > 1e-3 else Vector((1, 0))
        bench(q, d)
    n_l, n_b, n_c = len(osm_lamps), len(osm_benches), 0
    for e in misc['elements']:
        t = e.get('tags', {})
        nm = t.get('name', '')
        if e['type'] != 'way' or not e.get('geometry') or t.get('highway') == 'steps' or t.get('tunnel') or \
                t.get('covered') == 'yes' or (_num(t.get('layer'), 0) or 0) < 0:
            continue
        named = nm.startswith(PROP_STREETS)
        local = t.get('highway') in ('residential', 'tertiary', 'unclassified', 'living_street') and not t.get('bridge')
        main_ = t.get('highway') in ('trunk', 'primary', 'secondary') and not t.get('bridge')
        if main_ and not named:
            pts_ = _ring_xy(H, e['geometry'])
            w_ = _num(t.get('width')) or ((_num(t.get('lanes')) or 2) * 3.2 + 0.5)
            acc_ = 0.0
            for a, b in zip(pts_, pts_[1:]):
                a, b = Vector(a), Vector(b)
                L = (b - a).length
                if L < 1.0 or not in_walk(a.x, a.y):
                    acc_ += L
                    continue
                d = (b - a) / L
                nn = Vector((-d.y, d.x))
                s_ = (30.0 - acc_ % 30.0) % 30.0
                while s_ < L:
                    k_ = int((acc_ + s_) / 30.0)
                    sg = 1 if k_ % 2 else -1
                    q = a + d * s_ + nn * (w_ / 2 + 0.7) * sg
                    if not roofed(q.x, q.y) and not near(q, osm_lamps, 15.0):
                        mast(q, -nn * sg)
                        n_l += 1
                    s_ += 30.0
                acc_ += L
            continue
        if not named and not local:
            continue
        pts = _ring_xy(H, e['geometry'])
        mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        if not named and not (R_NEAR < math.hypot(mx, my) < 600 and (near_ok is None or near_ok(-1, mx, my))):
            continue
        w = ROAD_W.get(t.get('highway'), 5.0)
        if _num(t.get('width')):
            w = max(3.0, min(20.0, _num(t.get('width'))))
        sides = (1, -1) if w >= 7 else ((1,) if e['id'] % 2 else (-1,))
        ped = t.get('highway') in ('pedestrian', 'living_street', 'footway')
        acc = 0.0
        for a, b in zip(pts, pts[1:]):
            a, b = Vector(a), Vector(b)
            L = (b - a).length
            if L < 1.0:
                continue
            d = (b - a) / L
            nn = Vector((-d.y, d.x))
            s_ = 0.0
            while s_ < L:
                p = a + d * s_
                k = int((acc + s_) / 6.0)
                if k % (4 if named else 5) == 0:                 # lantern every 24 (30) m, alternating sides
                    q = p + nn * (w / 2 - 0.4) * (1 if k % 8 == 0 else -1)
                    if not roofed(q.x, q.y) and not near(q, osm_lamps, 18.0):
                        lantern(q)
                        n_l += 1
                if ped and k % 6 == 3 and nm.startswith(('Mikulášska', 'Kapitulská', 'Beblavého', 'Panská', 'Michalská')):
                    q = p - nn * (w / 2 - 1.0)
                    if not roofed(q.x, q.y) and not near(q, osm_benches, 25.0):
                        bench(q, d)
                        n_b += 1
                for sd_ in (sides if not ped and w >= 6.0 and rng.random() < 0.55 else ()):   # parked along the kerb
                    q = p + nn * (w / 2 - 1.5) * sd_          # in the kerb-side lane, 0.6 m off the kerb
                    if abs(G(q.x, q.y) - G(p.x, p.y)) < 0.4 and not in_precinct(q.x, q.y) and not roofed(q.x, q.y) and \
                            not any(_hwy_near(*(q + d * o2), 1.2) for o2 in (-2.2, 0.0, 2.2)) and \
                            not roofed((q + d * 2.2).x, (q + d * 2.2).y) and not roofed((q - d * 2.2).x, (q - d * 2.2).y) and \
                            not any(abs(q.x - c_[0]) < 5.3 and abs(q.y - c_[1]) < 5.3 for c_ in CARS[-40:]):
                        z = G(q.x, q.y) + lift(q.x, q.y, 'road')
                        CARS.append([round(q.x, 2), round(q.y, 2), round(z, 2), round(math.atan2(d.y, d.x), 4)])
                        blocker(q, d, 4.3, 1.8, z, z + 1.5)
                        n_c += 1
                s_ += 6.0
            acc += L
    print('v2_city street props: lanterns', n_l, 'benches', n_b, 'cars', n_c, 'blockers', len(cmb.faces) // 6)
    out_dir = H.get('OUT') or os.path.join(os.path.dirname(H['DATA']), 'out')
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'street_cars.json'), 'w') as f_:
        json.dump(CARS, f_)
    colour(0, (1.0, 1.0, 1.0))
    cmb.cols = [(1.0, 1.0, 1.0)] * len(cmb.faces)
    return [mb.build(coll)] + ([cmb.build(coll)] if cmb.faces else [])


def _promenade(H, misc, G, footprints, near_ok):
    """Plane-tree rows of the Danube embankment promenades (Nabrezie L. Svobodu, Razusovo, Vajanskeho,
    Fajnorovo): every 11 m, 9.5 m off the road axis on the river side, where that side meets water."""
    river = _far_river_rings(H, misc)
    pp = H['point_in_poly']
    grid = {}
    for poly in footprints:
        grid.setdefault((int(poly[0][0] // 50), int(poly[0][1] // 50)), []).append(poly)

    def wet(x, y):
        return any(pp(x, y, rv) for rv in river)

    def roofed(x, y):
        c = (int(x // 50), int(y // 50))
        return any(pp(x, y, q) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid.get((c[0] + dx, c[1] + dy), ()))
    out = []
    for e in misc['elements']:
        t = e.get('tags', {})
        if e['type'] != 'way' or 'nábrežie' not in t.get('name', '') or t.get('bridge') or not e.get('geometry'):
            continue
        pts = _ring_xy(H, e['geometry'])
        for a, b in zip(pts, pts[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 1.0 or math.hypot(a[0], a[1]) > 1500:
                continue
            dx, dy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            for k in range(int(L / 11.0) + 1):
                x, y = a[0] + dx * k * 11.0, a[1] + dy * k * 11.0
                for sgn in (-1, 1):
                    nx_, ny_ = -dy * sgn, dx * sgn
                    if not wet(x + nx_ * 45, y + ny_ * 45):
                        continue                  # not the river side
                    tx_, ty_ = x + nx_ * 9.5, y + ny_ * 9.5
                    if wet(tx_, ty_) or roofed(tx_, ty_) or G(tx_, ty_) < G.water + 1.0:
                        continue
                    if math.hypot(tx_, ty_) < R_MIN and not near_ok(-1, tx_, ty_):
                        continue
                    out.append((tx_, ty_))
    print('v2_city promenade trees', len(out))
    return out


def _trees(H, G, coll, footprints, extra=()):
    """City trees: OSM nodes and tree rows, plus canopy picked from the wide orthophoto."""
    import bpy
    import numpy as np
    ChunkMB, Vector, _prism = H['ChunkMB'], H['Vector'], H['_prism']
    leaf = H['_leaf_cluster']
    rng = random.Random(41)
    mb = VChunk(H, 'V2City_Trees|_Foliage', 'V2City_TreesFar|_Foliage')
    spots = []
    gd = _load(H, 'green.json')
    for e in gd['elements']:
        if e['type'] == 'node':
            spots.append(H['to_local'](e['lat'], e['lon']))
        elif e.get('geometry'):
            pts = _ring_xy(H, e['geometry'])
            for a, b in zip(pts, pts[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                for k in range(int(L / 8.0) + 1):
                    spots.append((a[0] + (b[0] - a[0]) * k * 8.0 / max(L, 1e-6), a[1] + (b[1] - a[1]) * k * 8.0 / max(L, 1e-6)))
    # canopy from the 3x3 km orthophoto (dark green, textured), on a jittered 9 m grid
    og = _ortho_green(H)
    if og is not None:
        green, x0, y0, x1, y1, w, h = og
        # spatial hash of footprints to reject trees on roofs
        grid = {}
        for poly in footprints:
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            grid.setdefault((int(cx // 50), int(cy // 50)), []).append(poly)
        pp = H['point_in_poly']
        for gx in range(int(-R_MAX), int(R_MAX), 9):
            for gy in range(int(-R_MAX), int(R_MAX), 9):
                x, y = gx + rng.uniform(-4, 4), gy + rng.uniform(-4, 4)
                if not (R_MIN < math.hypot(x, y) < R_MAX):
                    continue
                i = int((x - x0) / (x1 - x0) * w)
                j = int((y - y0) / (y1 - y0) * h)
                if not (3 <= i < w - 3 and 3 <= j < h - 3):
                    continue
                if green[j - 3:j + 4, i - 3:i + 4].mean() < 0.55:
                    continue
                cell = (int(x // 50), int(y // 50))
                if any(pp(x, y, q) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid.get((cell[0] + dx, cell[1] + dy), [])):
                    continue
                spots.append((x, y))
    far = VChunk(H, 'V2City_TreesFar|_Foliage', 'V2City_TreesFar|_Foliage', far_tile=900.0)
    trunks = H['MB']('V2City_TreeTrunks-colonly')
    n = n_far = 0
    n_extra = len(spots)
    spots = list(spots) + list(extra)
    for si, (x, y) in enumerate(spots):
        d = math.hypot(x, y)
        if not ((R_NEAR if si >= n_extra else R_MIN - 20) < d < R_MAX + 50):
            continue
        z = G(x, y)
        if z < G.water + 0.8:
            continue                         # river / flooded bank
        hgt = rng.uniform(8, 16)
        tone = rng.choice(('leaves', 'leaves', 'leaves_dark', 'leaves_light'))
        R = hgt * rng.uniform(0.25, 0.33)
        mature = si >= n_extra or math.hypot(x - 690, y - 55) < 70     # promenade / Hviezdoslavovo plane trees
        if mature:
            hgt = rng.uniform(15, 20)
            R = hgt * rng.uniform(0.38, 0.45)
        if d > R_TREE_NEAR and not in_walk(x, y):
            # far: one wider crossed-card crown (every other tree beyond 1 km), no trunk (hidden by the crown at 600 m+)
            if d > 800 and rng.random() < 0.76:
                continue
            leaf(far, Vector((x, y, z + hgt * 0.62)), R * 2.3, tone, rng)
            n_far += 1
            continue
        walk = in_walk(x, y)
        if walk and (_in_carriage(x, y, 1.0) or _in_bld(x, y, 0.5) or _under_deck(x, y) or
                     any((x - a_) ** 2 + (y - b_) ** 2 < 25.0 for a_, b_ in TREES_AT.get((int(x // 10), int(y // 10)), ()))):
            continue                             # not in a road, a building, under a deck, nor < 5 m from a tree
        if walk:
            TREES_AT.setdefault((int(x // 10), int(y // 10)), []).append((x, y))
            for gx_ in (-1, 0, 1):
                for gy_ in (-1, 0, 1):
                    if gx_ or gy_:
                        TREES_AT.setdefault((int(x // 10) + gx_, int(y // 10) + gy_), []).append((x, y))
        if walk and _hwy_near(x, y, 2.6):
            continue                             # never on / at the edge of a mapped footway (half-width + 0.8 m)
        if walk and not _prio_near(x, y, 22.0) and d > R_MIN:
            # walk zone away from the routes: trunk + two compact crown clusters (cheap, still grounded)
            _prism(far, Vector((x, y, z - 0.5)), Vector((x, y, z + hgt * 0.62)), 0.16 + hgt * 0.012, 0.1, 'bark', seg=4)
            leaf(far, Vector((x, y, z + hgt * 0.66)), min(3.4, R * 1.4), tone, rng)
            n_far += 1
            continue
        _prism(mb, Vector((x, y, z - 0.5)), Vector((x, y, z + hgt * 0.38)), 0.16 + hgt * 0.012, 0.12,
               'v2_planebark' if mature else 'bark', seg=5)
        if walk:
            r_ = 0.2 + hgt * 0.012
            trunks.box([(x - r_, y - r_), (x + r_, y - r_), (x + r_, y + r_), (x - r_, y + r_)], z - 0.5, z + 3.0, 'bark')
        c = Vector((x, y, z + hgt * (0.6 if mature else 0.66)))
        fork = Vector((x, y, z + hgt * 0.38))
        leaf(mb, c + Vector((0, 0, R * 0.25)), min(3.4, R * 0.9), tone, rng)              # central crown
        a = rng.uniform(0, 2 * math.pi)                                                  # lower overlapping tier
        leaf(mb, c + Vector((math.cos(a) * R * 0.35, math.sin(a) * R * 0.35, -R * 0.45)), min(3.4, R * 0.75), tone, rng)
        for k in range(7 if mature else 5):                        # 5 compact clusters (cards <= 3.4 m: no stretched sheets)
            nk = 7 if mature else 5
            a = k * 2 * math.pi / nk + rng.uniform(-0.4, 0.4)
            sp = 0.65 if mature else 0.5
            cc = c + Vector((math.cos(a) * R * sp, math.sin(a) * R * sp, rng.uniform(-0.3, 0.3) * R * (0.6 if mature else 1.0)))
            leaf(mb, cc, min(3.4, R * (0.95 if mature else 0.8)) * rng.uniform(0.8, 1.15), tone, rng)
            # limbs from the fork into every leaf cluster, so no crown floats above a cut trunk
            bk = 'v2_planebark' if mature else 'bark'
            _prism(mb, fork, cc, 0.07 + hgt * 0.006, 0.03, bk, seg=4)

        n += 1
    print('v2_city trees near', n, 'far', n_far)
    return mb.build(coll) + far.build(coll) + ([trunks.build(coll)] if trunks.faces else [])


PANEL_PALETTE = ['#EFE9DC', '#E9C98F', '#E8B48A', '#D9DCCF', '#C9D6DF', '#EADFA0', '#DCC3B8', '#F2F0EC', '#B9C4C8']
KAMZIK_FOUND = [False]
KAMZIK = 230944086          # Televizna veza na Kamziku, 194 m on the 439 m summit


def _far_river_rings(H, misc):
    """Outer rings of the Danube (and arms) water relations: water_far.json (full geometry, ~10 km),
    falling back to the clipped rings of misc.json."""
    src = _load(H, 'water_far.json')
    if not src['elements']:
        src = misc
    rings = []
    for e in src['elements']:
        t = e.get('tags', {})
        if e['type'] == 'relation' and t.get('natural') == 'water' and e.get('members'):
            for rv in _assemble(H, e['members'], 'outer'):
                rv = _clean(rv)
                if len(rv) >= 3 and max(abs(q[0]) for q in rv) < 60000:
                    rings.append(rv)
    return rings


def _skyline(H, T, G, coll, misc):
    """Far skyline beyond the OSM city square: Petrzalka panel estates + Aupark, the Nivy / Eurovea /
    Twin City high-rises, Kamzik TV tower on a hill mound. One vertex-tinted window-band material,
    flat roofs (UV parked on a plain band of the same texture), 2 km chunks named V2City_BldFar*."""
    import numpy as np
    data = _load(H, 'far.json')
    if not data['elements']:
        return []
    Vector, tx = H['Vector'], H['textures']
    if 'v2_panel' not in H['MATS']:
        n = 128
        rng_ = np.random.default_rng(5)
        y, x = np.mgrid[0:n, 0:n] / n            # row 0 = top of image (v = 1)
        rgb = np.ones((n, n, 3)) * 0.93 + rng_.normal(0, 0.015, (n, n, 1))
        band = (y > 0.40) & (y < 0.78) & (x > 0.06) & (x < 0.94)
        rgb[band] = np.stack([0.17 + 0.1 * (y - 0.4), 0.2 + 0.1 * (y - 0.4), 0.24 + 0.1 * (y - 0.4)], -1)[band]
        rgb[band & (np.abs(x - 0.5) < 0.02)] = 0.85
        rgb[(y > 0.86) & (y < 0.9)] *= 0.85      # panel joint
        _vc_material(H, 'v2_panel', tx._save(os.path.join(H['TEX'], 'v2_panel.png'), np.clip(rgb, 0, 1)), 1.0, 0.85)
    near_bb = (H['to_local'](48.1315, 17.0839), H['to_local'](48.1531, 17.1163))
    dmr = json.load(open(os.path.join(H['DATA'], 'dmr_far.json')))['bbox']
    dx0, dy0 = H['to_local'](dmr[1], dmr[0])
    dx1, dy1 = H['to_local'](dmr[3], dmr[2])
    rng = random.Random(19)
    mb = VChunk(H, 'V2City_BldFar|_Sky', 'V2City_BldFar|_Sky', 3000.0, 3000.0)
    CMB = _cmb_class(H)
    lm = CMB('V2City_Landmarks_Kamzik')
    PLAIN = (0.5, 0.06)                         # uv on the plain panel band (roofs)
    # Kamzik: mound of the Little Carpathians foothills (no DMR this far) + the TV tower
    kx, ky = None, None
    KAMZIK_FOUND[0] = False
    for e in data['elements']:
        if e['id'] == KAMZIK and e.get('geometry'):
            KAMZIK_FOUND[0] = True
            pts = _ring_xy(H, e['geometry'])
            kx, ky = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    # far ground beyond the 3x3 km DMR: flat Danube plain (Petrzalka, Ruzinov) blended into the DMR edge,
    # a Little Carpathians mound through Kamzik in the N, river channels sunk below the water level
    river = _far_river_rings(H, misc)
    top = 439.0 - T.z0                           # Kamzik summit, local metres
    base = 140.0 - T.z0
    flat = G.water + 3.5
    rd = Vector((0.6, 0.8))                      # ridge runs SW -> NE through Kamzik
    kx, ky = (kx, ky) if kx is not None else (-410.0, 4485.0)

    def plain(x, y):
        d_out = math.hypot(max(dx0 - x, 0, x - dx1), max(dy0 - y, 0, y - dy1))
        ze = G.zf(x, y) - 1.5                    # clamps to the DMR edge value
        k = min(1.0, d_out / 700.0)
        k = k * k * (3 - 2 * k)
        return ze * (1 - k) + flat * k

    def hill(x, y):
        hp = plain(x, y)
        if y <= dy1:
            return hp
        dpar = (x - kx) * rd.x + (y - ky) * rd.y
        dper = (x - kx) * rd.y - (y - ky) * rd.x  # > 0 : SE (city) side
        w = 1300.0 if dper > 0 else 3200.0
        hh = base + (top - base) * math.exp(-(dper / w) ** 2) * (1.0 - 0.25 * min(1.0, abs(dpar) / 5000))
        k = min(1.0, (y - dy1) / 900.0)
        k = k * k * (3 - 2 * k)
        return hp * (1 - k) + max(hh, hp) * k

    n_b = n_river = 0
    for e in data['elements']:
        t = e.get('tags', {})
        if e['type'] != 'way' or not e.get('geometry'):
            continue
        r = _clean(_ring_xy(H, e['geometry']))
        if len(r) < 3 or abs(_area(r)) < 60:
            continue
        cx, cy = sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r)
        if e['id'] == KAMZIK:
            continue
        if near_bb[0][0] < cx < near_bb[1][0] and near_bb[0][1] < cy < near_bb[1][1]:
            continue                            # already modelled by the detailed city square
        h = _num(t.get('height'))
        lv = _num(t.get('building:levels'))
        if h is None:
            if not lv:
                continue
            h = lv * 2.9 + 1.0
        if h < 12 or t.get('man_made') in ('works', 'chimney') and h < 30 or (h < 28 and abs(_area(r)) < 650):
            continue
        if _num(t.get('min_height'), 0.0) > 0 or _num(t.get('building:min_level'), 0.0) > 0:
            continue                            # floating parts (podium overhangs, skybridges): no base far away
        if any(H['point_in_poly'](cx, cy, rv) for rv in river):
            continue
        dist = math.hypot(cx, cy)
        r = _simplify(r, 1.5 if dist < 3000 else 3.0)
        inside_dmr = dx0 + 5 < cx < dx1 - 5 and dy0 + 5 < cy < dy1 - 5
        g = min((G(p[0], p[1]) if inside_dmr else hill(p[0], p[1])) for p in r)
        z0, z1 = min(g, G.water) - 8.0, g + h        # always reach below any far ground / horizon plane
        hx = PANEL_PALETTE[rng.randrange(len(PANEL_PALETTE))]
        _tint('_panel_' + hx, 'v2_panel', hx, 1.4)
        mat = '_panel_' + hx
        for i in range(len(r)):
            a, b = r[i], r[(i + 1) % len(r)]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            u1 = max(1.0, round(L / 3.0))
            v0, v1 = (z0 - g) / 2.9, (z1 - g) / 2.9
            mb.poly([Vector((a[0], a[1], z0)), Vector((b[0], b[1], z0)), Vector((b[0], b[1], z1)), Vector((a[0], a[1], z1))],
                    mat, uv=[(0, v0), (u1, v0), (u1, v1), (0, v1)])
        TINT.setdefault('_panel_roof', ('v2_panel', (0.55, 0.55, 0.55)))
        for tri in H['geometry'].tessellate_polygon([[(p[0], p[1], 0) for p in r]]):
            q = [Vector((r[i][0], r[i][1], z1)) for i in tri]
            if H['geometry'].normal(q).z < 0:
                q.reverse()
            mb.poly(q, '_panel_roof', uv=[PLAIN] * 3)
        n_b += 1
    out = mb.build(coll)
    if 'v2_forest' not in H['MATS']:
        _vc_material(H, 'v2_forest', None, 40.0, 1.0, src='foliage_dark')
    hmb = CMB('V2City_TerrainFar_Hills')
    nx_, ny_ = 24, 24                            # grid lines on the DMR edges -> no overlap with Terrain_Far
    sx, sy = (dx1 - dx0) / nx_, (dy1 - dy0) / ny_
    ext = 6000.0
    xs = [dx0 + i * sx for i in range(-int((ext + dx0) / sx), int((ext - dx0) / sx) + 1)]
    ys = [dy0 + j * sy for j in range(-int((ext + dy0) / sy), int((ext - dy0) / sy) + 1)]
    pp = H['point_in_poly']
    rgrid = {}
    for rv in river:
        xs_, ys_ = [q[0] for q in rv], [q[1] for q in rv]
        for gx in range(int(min(xs_) // 500), int(max(xs_) // 500) + 1):
            for gy in range(int(min(ys_) // 500), int(max(ys_) // 500) + 1):
                rgrid.setdefault((gx, gy), []).append(rv)

    def wet(x, y):
        return any(pp(x, y, rv) for rv in rgrid.get((int(x // 500), int(y // 500)), ()))
    def zat(x, y):
        return G.water - 2.5 if wet(x, y) else hill(x, y)

    def colour(zs):
        rise = (sum(zs) / len(zs) - base) / (top - base)
        k = min(1.0, max(0.0, (rise - 0.08) / 0.2))          # forested slopes vs. built-up plain
        return tuple(u * (1 - k) + f * k for u, f in zip((0.62, 0.47, 0.48), (0.11, 0.17, 0.09)))

    def cell(x0_, y0_, x1_, y1_, z4, depth):
        w4 = [z == G.water - 2.5 for z in z4]
        if depth < 2 and any(w4) and not all(w4):            # shoreline: refine 125 -> 31 m
            xm, ym = (x0_ + x1_) / 2, (y0_ + y1_) / 2
            zz = {(u, v): zat(u, v) for u in (x0_, xm, x1_) for v in (y0_, ym, y1_)}
            for (ua, va, ub, vb) in ((x0_, y0_, xm, ym), (xm, y0_, x1_, ym), (xm, ym, x1_, y1_), (x0_, ym, xm, y1_)):
                cell(ua, va, ub, vb, [zz[(ua, va)], zz[(ub, va)], zz[(ub, vb)], zz[(ua, vb)]], depth + 1)
            return
        q = [Vector((x0_, y0_, z4[0])), Vector((x1_, y0_, z4[1])), Vector((x1_, y1_, z4[2])), Vector((x0_, y1_, z4[3]))]
        nf = len(hmb.faces)
        hmb.poly(q, 'v2_forest', uv_scale=40.0)
        if len(hmb.faces) > nf:
            hmb.cols.append(colour(z4))

    Z = [[zat(x, y) for x in xs] for y in ys]
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            cx_, cy_ = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if dx0 < cx_ < dx1 and dy0 < cy_ < dy1:
                continue                         # covered by the DMR terrain
            cell(xs[i], ys[j], xs[i + 1], ys[j + 1], [Z[j][i], Z[j][i + 1], Z[j + 1][i + 1], Z[j + 1][i]], 0)
    # outer apron to the haze (flat, 1 km cells, 0.3 m under the grid where they overlap)
    X0, X1, Y0, Y1 = xs[0], xs[-1], ys[0], ys[-1]
    for i in range(-15, 15):
        for j in range(-15, 15):
            ax, ay, bx, by = i * 1000.0, j * 1000.0, (i + 1) * 1000.0, (j + 1) * 1000.0
            if ax >= X0 - 1 and bx <= X1 + 1 and ay >= Y0 - 1 and by <= Y1 + 1:
                continue
            q = [Vector((ax, ay, flat - 0.3)), Vector((bx, ay, flat - 0.3)), Vector((bx, by, flat - 0.3)), Vector((ax, by, flat - 0.3))]
            nf = len(hmb.faces)
            hmb.poly(q, 'v2_forest', uv_scale=40.0)
            if len(hmb.faces) > nf:
                hmb.cols.append((0.62, 0.47, 0.48))
    out.append(hmb.build(coll))
    if KAMZIK_FOUND[0]:
        g = hill(kx, ky)
        _prism, ellipsoid = H['_prism'], H['ellipsoid']
        for mbp, args in ((lm, (Vector((kx, ky, g - 3)), Vector((kx, ky, g + 70)), 6.5, 4.6, 'concrete', 8)),
                          (lm, (Vector((kx, ky, g + 82)), Vector((kx, ky, g + 128)), 4.4, 2.6, 'concrete', 8)),
                          (lm, (Vector((kx, ky, g + 128)), Vector((kx, ky, g + 194)), 1.3, 0.35, 'metal', 6))):
            a, b, ra, rb, m_, sg = args
            _prism(mbp, a, b, ra, rb, m_, seg=sg)
        _prism(lm, Vector((kx, ky, g + 70)), Vector((kx, ky, g + 82)), 13.0, 13.0, 'glass', seg=16)  # restaurant cabin
        ellipsoid(lm, Vector((kx, ky, g + 82.5)), 13.5, 13.5, 1.2, 0, 0, 'concrete', subdiv=2)
        ellipsoid(lm, Vector((kx, ky, g + 69.5)), 13.5, 13.5, 1.2, 0, 0, 'concrete', subdiv=2)
        lm.cols = [(1.0, 1.0, 1.0)] * len(lm.faces)
        out.append(lm.build(coll))
    print('v2_city skyline blocks', n_b)
    return out


def _sink_far_terrain(T, H=None):
    """V1 Terrain_Far parks its vertices inside the detailed-terrain box at a flat -40 m, which is above
    the real ground on the low Podhradie / embankment side (detail terrain there is ~ -65 m) and hides it.
    Drop those vertices 12 m under the detailed terrain (clear of basements), and to <= -20 m around the
    palace (cellar floor at -4.6)."""
    import bpy
    ob = bpy.data.objects.get('Terrain_Far')
    if ob is None:
        return
    palace = H['offset_poly'](H['OUTER'], 12.0) if H is not None else None
    n = 0
    for v in ob.data.vertices:
        x, y = v.co.x, v.co.y
        covered = T.covers(x, y) if hasattr(T, 'covers') else (T.x0 + 2 < x < T.x1 - 2 and T.y0 + 2 < y < T.y1 - 2)
        if not covered:
            v.co.z = _edge_blend(T, x, y, v.co.z)          # blend band only outside the surveyed area
            continue
        v.co.z = T.h(x, y) - 12.0 if abs(v.co.z + 40.0) < 1e-3 else min(v.co.z, T.h(x, y) - 12.0)
        if palace is not None and H['point_in_poly'](x, y, palace):
            v.co.z = min(v.co.z, -20.0)
        n += 1
    ob.data.update()
    print('v2_city: Terrain_Far vertices sunk under the detailed terrain', n)


def _in_carriage(x, y, pad=0.0):
    for a, b, hw in CARRIAGE.get((int(x // 10), int(y // 10)), ()):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
        if math.hypot(x - a[0] - k * dx, y - a[1] - k * dy) < hw + pad:
            return True
    return False


def _carriage_index(H, misc):
    """Motor carriageways (2D, half widths) and bridge decks, for prop / tree placement rules."""
    CARRIAGE.clear()
    DECKS.clear()
    for e in misc['elements']:
        t = e.get('tags', {})
        hw_ = t.get('highway')
        if e['type'] == 'way' and e.get('geometry') and hw_ in ROAD_W and hw_ not in ('pedestrian', 'living_street', 'service') \
                and not t.get('bridge') and not t.get('tunnel'):
            q_ = _ring_xy(H, e['geometry'])
            wq = _num(t.get('width')) or ((_num(t.get('lanes')) * 3.2 + 0.5) if _num(t.get('lanes')) else ROAD_W[hw_])
            for a_, b_ in zip(q_, q_[1:]):
                for gx in range(int(min(a_[0], b_[0]) // 10) - 1, int(max(a_[0], b_[0]) // 10) + 2):
                    for gy in range(int(min(a_[1], b_[1]) // 10) - 1, int(max(a_[1], b_[1]) // 10) + 2):
                        CARRIAGE.setdefault((gx, gy), []).append((a_, b_, wq / 2))
    for e in misc['elements']:
        t = e.get('tags', {})
        if e['type'] == 'way' and e.get('geometry') and t.get('highway') and t.get('bridge') in ('yes', 'viaduct'):
            q_ = _ring_xy(H, e['geometry'])
            hw_ = (_num(t.get('width')) or ROAD_W.get(t.get('highway'), 4.0)) / 2
            DECKS.extend((a_, b_, hw_) for a_, b_ in zip(q_, q_[1:]))


def _under_deck(x, y):
    for a, b, hw in DECKS:
        if abs(a[0] - x) > 80 and abs(b[0] - x) > 80:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
        if math.hypot(x - a[0] - k * dx, y - a[1] - k * dy) < hw + 3.0:
            return True
    return False


def _terrain_cuts(H):
    """Walk zone: (1) under every road ribbon the terrain drops 0.25 m (no grass poking through the paving);
    (2) round sloping houses a 1.5 m apron is cut down to the house datum + 0.3 m (no bank over windows),
    at most 2.5 m deep and never on a mapped walking line."""
    import bpy
    pp = H['point_in_poly']
    rg, cg = {}, {}
    for a, b, hw, za_, zb_ in RIBS:
        for gx in range(int(min(a[0], b[0]) // 10) - 1, int(max(a[0], b[0]) // 10) + 2):
            for gy in range(int(min(a[1], b[1]) // 10) - 1, int(max(a[1], b[1]) // 10) + 2):
                rg.setdefault((gx, gy), []).append((a, b, hw, za_, zb_))
    for poly, datum in CUTS:
        xs, ys = [q[0] for q in poly], [q[1] for q in poly]
        for gx in range(int(min(xs) // 10) - 1, int(max(xs) // 10) + 2):
            for gy in range(int(min(ys) // 10) - 1, int(max(ys) // 10) + 2):
                cg.setdefault((gx, gy), []).append((poly, datum))

    def segd(x, y, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
        return math.hypot(x - a[0] - k * dx, y - a[1] - k * dy)
    n1 = n2 = 0
    for nm in ('Terrain-col', 'Terrain_Centre-col'):
        ob = bpy.data.objects.get(nm)
        if ob is None:
            continue
        for v in ob.data.vertices:
            x, y = v.co.x, v.co.y
            if not in_walk(x, y):
                continue
            key = (int(x // 10), int(y // 10))
            hit_ = [(a, b, za_, zb_) for a, b, hw, za_, zb_ in rg.get(key, ()) if segd(x, y, a, b) < hw + 0.3]
            if hit_:
                a, b, za_, zb_ = hit_[0]
                dx, dy = b[0] - a[0], b[1] - a[1]
                l2 = dx * dx + dy * dy or 1e-9
                k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
                zs_ = za_ + (zb_ - za_) * k          # ribbon surface here: terrain kept >= 0.2 m below it
                v.co.z = min(v.co.z - 0.25, zs_ - 0.2)
                n1 += 1
                continue
            for poly, datum in cg.get(key, ()):
                if v.co.z > datum + 0.3 and v.co.z - datum < 2.8 and (pp(x, y, poly) or _edge_dist(x, y, poly) < 1.5) \
                        and not _hwy_near(x, y, 1.5):
                    v.co.z = datum + 0.3
                    n2 += 1
                    break
        ob.data.update()
    print('v2_city terrain: lowered under road ribbons', n1, 'cut round houses', n2)


def _sink_river_bed(H, misc, water):
    """The survey DMRs interpolate bridge decks / moored ships into the river bed: inside the river polygons
    every terrain vertex goes 1.5 m under the water surface (no 'dam walls' under bridges, no ghost hulls)."""
    import bpy
    rings = [rv for rv in _far_river_rings(H, misc) if len(rv) > 3]
    pp = H['point_in_poly']
    grid = {}
    for rv in rings:
        xs, ys = [q[0] for q in rv], [q[1] for q in rv]
        for gx in range(int(max(-3000, min(xs)) // 100), int(min(3000, max(xs)) // 100) + 1):
            for gy in range(int(max(-3000, min(ys)) // 100), int(min(3000, max(ys)) // 100) + 1):
                grid.setdefault((gx, gy), []).append(rv)
    n = 0
    for nm in ('Terrain_Centre-col', 'Terrain_Far', 'Terrain-col'):
        ob = bpy.data.objects.get(nm)
        if ob is None:
            continue
        for v in ob.data.vertices:
            if v.co.z > water - 1.5 and any(pp(v.co.x, v.co.y, rv) for rv in grid.get((int(v.co.x // 100), int(v.co.y // 100)), ())):
                v.co.z = water - 1.5
                n += 1
        ob.data.update()
    print('v2_city: terrain vertices inside the river lowered', n)


def build(H, T, feats, points, coll):
    import bpy
    bdata = _load(H, 'buildings.json')
    misc = _load(H, 'misc.json')
    if not bdata['elements']:
        print('v2_city: no data')
        return []
    _materials(H)
    G = Ground(H, T)
    _sink_river_bed(H, misc, G.water)
    G.attach_meshes(('Terrain-col', 'Terrain_Centre-col'))
    rng = random.Random(7)
    # V1 placeholders (flat Danube plane, simplified cathedral + SNP bridge) are superseded
    for nm in ('Danube', 'Landmarks'):
        ob = bpy.data.objects.get(nm)
        if ob:
            bpy.data.objects.remove(ob, do_unlink=True)
    castle = next((f['pts'] for f in feats if f.get('tags', {}).get('name') == 'Bratislavský hrad'), None)
    skip = set(H['REPLACED_IDS']) | set(H['PALACE_IDS']) | {369605106, 115596648, 115596652}
    pip = H['point_in_poly']

    if castle:
        try:
            cc_ = _clean([tuple(p[:2]) for p in castle])          # CCW, so +6 grows it
            PRECINCT[0] = [tuple(v) for v in H['offset_poly'](cc_, 6.0)]
            if abs(_area(PRECINCT[0])) < abs(_area(cc_)):
                PRECINCT[0] = cc_
        except ZeroDivisionError:
            PRECINCT[0] = castle
        PRECINCT[1] = pip

    def near_ok(i, cx, cy):
        return i not in skip and not (castle and pip(cx, cy, castle)) and not pip(cx, cy, H['OUTER'])
    _TT[0] = T
    wx0, wy0 = H['to_local'](48.1360, 17.0950)
    wx1, wy1 = H['to_local'](48.1485, 17.1150)
    WALK[0] = (wx0, wy0, wx1, wy1)
    _hwy_index(H, misc)
    PASS.clear()
    for src_ in (misc, _load(H, 'street.json')):
        for e_ in src_['elements']:
            t_ = e_.get('tags', {})
            if e_['type'] == 'way' and e_.get('geometry') and (t_.get('tunnel') == 'building_passage' or t_.get('covered') == 'yes'):
                q_ = _ring_xy(H, e_['geometry'])
                for a_, b_ in zip(q_, q_[1:]):
                    n_ = max(1, int(math.hypot(b_[0] - a_[0], b_[1] - a_[1]) / 0.7))
                    for k_ in range(n_ + 1):
                        x_, y_ = a_[0] + (b_[0] - a_[0]) * k_ / n_, a_[1] + (b_[1] - a_[1]) * k_ / n_
                        PASS.setdefault((int(x_ // 2), int(y_ // 2)), []).append((x_, y_))
    for e_ in misc['elements']:
        nm_ = e_.get('tags', {}).get('name')
        if e_['type'] == 'way' and nm_ in ('Mudroňova',) and e_.get('geometry'):
            q_ = _ring_xy(H, e_['geometry'])
            NAMED.setdefault(nm_, []).extend(zip(q_, q_[1:]))
    fp_ = os.path.join(H['DATA'], 'ref', 'fortress', 'flight_footprints.json')
    FLIGHTS[:] = [[tuple(q[:2]) for q in f] for f in json.load(open(fp_)) if len(f) >= 3] if os.path.exists(fp_) else []
    _prio_index(H, misc)
    _sink_far_terrain(T, H)
    GHOSTS.clear()
    TREES_AT.clear()
    DECKS.clear()
    SNP.clear()
    FENCES.clear()
    CUTS.clear()
    RIBS.clear()
    out, special = _buildings(H, bdata, G, coll, rng, _shop_streets(H, misc), near_ok)
    footprints = [_clean(_ring_xy(H, e['geometry'])) for e in bdata['elements']
                  if e['type'] == 'way' and e.get('geometry') and 'building' in e.get('tags', {})]
    for e in bdata['elements']:
        if e['type'] == 'relation' and 'building' in e.get('tags', {}):
            footprints += [_clean(r) for r in _assemble(H, e.get('members', []))]
    footprints = [f for f in footprints if len(f) >= 3]
    _bld_index(footprints)
    _carriage_index(H, misc)
    out += _trees(H, G, coll, footprints, _promenade(H, misc, G, footprints, near_ok))
    streets = VChunk(H, 'V2City_Streets|', 'V2City_StreetsFar|', walk_name='V2City_StreetsWalk|-col')
    _paving(H, G, streets, footprints, misc)
    out += _landmarks(H, special, G, coll, misc)
    out += _lm('snp', H, special, G, coll, misc, SNP)
    out += _lm('dom_tower', H, special, G, coll)
    out += _lm('dom_body', H, special, G, coll)
    out += _lm('michalska', H, special, G, coll)
    out += _lm('townhall', H, special, G, coll)
    out += _lm('snd', H, special, G, coll)
    out += _lm('primate', H, special, G, coll)
    out += _lm('reduta', H, special, G, coll)
    out += _lm('klarisky', H, special, G, coll)
    out += _danube(H, misc, G, coll)
    out += _roads(H, misc, G, coll, streets, near_ok)
    out += _lm('snp_deck', H, G, coll, misc, SNP)
    out += _city_walls(H, G, coll)
    out += _garden_walls(H, G, coll)
    out += _passages(H, G, coll, misc)
    out += _shop_dressing(H, coll, G)
    sd, lamps, benches = _street_detail(H, G, coll, near_ok)
    out += sd
    CARS.clear()
    out += _street_props(H, misc, G, footprints, coll, lamps, benches, near_ok)
    out += _skyline(H, T, G, coll, misc)
    _terrain_cuts(H)
    polys = sum(len(o.data.polygons) for o in out if o is not None and hasattr(o, 'data'))
    print('v2_city objects', len(out), 'polys', polys)
    return out
