"""V2: Baroque garden terraces - white retaining walls with balustrades, broad axial stairs, garden walls.

The 4.8 m DMR smears each terrace wall into a 3-5 m slope.  terrace_sharpener() (called from
Terrain.set_garden before the terrain mesh is built) finds the terrace edges and returns a function that
turns T.h into a step along each edge (plateau heights sampled 5 m away from the edge line) and into the
exact stair profile under every terrace stair, so the terrain meets the treads.
build() (called from v2_fortress.build) adds per edge one continuous wall at a shared elevation with a
balustrade, pedestals at the stair openings, broad stone flights perpendicular to the wall with sloping
balustrades on both sides (refs 11/12), a gravel walk on the upper side (hides the 2 m terrain grid smear),
and rebuilds the other OSM walls inside the garden as continuous, sloping balustrades.

Edges: OSM retaining walls across the garden axis (terrace A, y~67-74, refs 11/17, garden_ortho.png),
plus one edge through every OSM flight whose ends differ by > 0.5 m in the DMR and which is not on an edge
yet (terrace B at the 513653094 flight, y~83), parallel to its neighbour.
"""
import json
import math
import os

W = 5.0          # half width of the band in which the DMR slope is replaced by a step
CUT = -0.8       # the step sits this far on the upper side; terrain vertices are snapped onto it (build)
WALK = 1.8       # gravel walk along the top of each terrace wall (covers the paving-mesh smear at CUT)
TREAD, RISE = 0.32, 0.16
WALL_T = 0.5


def _pip(x, y, poly):
    c = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            c = not c
        j = i
    return c


def _clip(poly, p, t):
    """Parameter range of the line p + t*s inside the polygon (outermost crossings)."""
    ss = []
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i][0], poly[i][1]
        bx, by = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        ex, ey = bx - ax, by - ay
        den = t[0] * ey - t[1] * ex
        if abs(den) < 1e-9:
            continue
        s = ((ax - p[0]) * ey - (ay - p[1]) * ex) / den
        u = ((ax - p[0]) * t[1] - (ay - p[1]) * t[0]) / den
        if 0 <= u <= 1:
            ss.append(s)
    return (min(ss), max(ss)) if len(ss) >= 2 else None


def _median(v):
    v = sorted(v)
    return v[len(v) // 2]


def terrace_sharpener(H, T, poly):
    Vector = H['Vector']
    raw = lambda q: T.raw(q.x, q.y) - T.z0

    def eased(q):                                        # Terrain.h's terrace-level easing, without the edges
        zr = raw(q)
        lv_ = T.levels
        if not lv_:
            return zr
        k = min(range(len(lv_)), key=lambda i: abs(lv_[i] - zr))
        lv = lv_[k]
        gaps = [abs(lv - lv_[j]) for j in (k - 1, k + 1) if 0 <= j < len(lv_)]
        r = min([0.7] + [g / 2 for g in gaps])
        dz = abs(lv - zr)
        if dz < r:
            t = max(0.0, (dz - r / 2) / (r / 2))
            zr = lv + (zr - lv) * t * t * (3 - 2 * t)
        return zr
    feats = json.load(open(os.path.join(H['DATA'], 'castle_local.json')))['features']
    P = [Vector(p[:2]) for p in poly]
    c = sum(P, Vector((0, 0))) / len(P)
    sxx = sum((p.x - c.x) ** 2 for p in P)
    syy = sum((p.y - c.y) ** 2 for p in P)
    sxy = sum((p.x - c.x) * (p.y - c.y) for p in P)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    axis = Vector((math.cos(ang), math.sin(ang)))        # garden long axis
    inside = lambda f: sum(_pip(p[0], p[1], poly) for p in f['pts']) >= 2
    walls = [f for f in feats if f['kind'] == 'wall' and inside(f)]
    # --- edges from OSM walls across the axis
    pts = []
    for f in walls:
        for a, b in zip(f['pts'], f['pts'][1:]):
            A, B = Vector(a[:2]), Vector(b[:2])
            if (B - A).length > 1.5 and abs((B - A).normalized().dot(axis)) < 0.4:
                pts += [A, B]
    clusters = []
    for q in sorted(pts, key=lambda q: (q - c).dot(axis)):
        if clusters and (q - c).dot(axis) - (clusters[-1][-1] - c).dot(axis) < 4.0:
            clusters[-1].append(q)
        else:
            clusters.append([q])
    lines = []
    for cl in clusters:
        if len(cl) < 4:
            continue
        m = sum(cl, Vector((0, 0))) / len(cl)
        sxx = sum((p.x - m.x) ** 2 for p in cl)
        syy = sum((p.y - m.y) ** 2 for p in cl)
        sxy = sum((p.x - m.x) * (p.y - m.y) for p in cl)
        a2 = 0.5 * math.atan2(2 * sxy, sxx - syy)
        lines.append((m, Vector((math.cos(a2), math.sin(a2))), True))
    # --- edges through flights of steps that bridge a DMR drop
    steps = [f for f in feats if f['kind'] == 'road' and f['tags'].get('highway') == 'steps' and inside(f)]
    for f in steps:
        A, B = Vector(f['pts'][0][:2]), Vector(f['pts'][-1][:2])
        m = (A + B) / 2
        if abs(raw(A) - raw(B)) < 0.5:
            continue
        lt = min(lines, key=lambda l: abs((m - l[0]).dot(axis)))[1] if lines else Vector((-axis.y, axis.x))
        lines.append((m, lt, False))
    axial = lambda q: abs((q - c).dot(Vector((-axis.y, axis.x)))) < 6.0

    def sharpness(m, t):                                 # mean DMR drop across the line, over the garden width
        n = Vector((-t.y, t.x))
        rng = _clip(poly, m, t) or (0.0, 0.0)
        ds = [abs(raw(m + t * s - n * 2.0) - raw(m + t * s + n * 2.0)) for s in
              [rng[0] + 1.5 + 3.0 * k for k in range(max(1, int((rng[1] - rng[0] - 3.0) / 3.0)))]]
        return sum(ds) / len(ds)
    # lines closer than 6 m: keep the OSM one, else the one through the axial flight (the walk), else the sharper;
    # a flight-derived line must be a real terrace step over the garden width (mean DMR drop >= 0.5 m), not a
    # local stair (e.g. the flight from the palace N gate, which only the --hires DMR resolves)
    def inside_frac(m, t):                               # both plateaus must lie in the garden along the line
        n = Vector((-t.y, t.x))
        rng = _clip(poly, m, t) or (0.0, 0.0)
        ss = [rng[0] + 1.5 + 3.0 * k for k in range(max(1, int((rng[1] - rng[0] - 3.0) / 3.0)))]
        ok = sum(_pip(*(m + t * s_ - n * (W + 1.0)), poly) and _pip(*(m + t * s_ + n * (W + 1.0)), poly) for s_ in ss)
        return ok / len(ss)
    keep = []
    for ln in sorted(lines, key=lambda l: (not l[2], not axial(l[0]), -sharpness(l[0], l[1]))):
        sh = sharpness(ln[0], ln[1])
        if not ln[2] and inside_frac(ln[0], ln[1]) < 0.8:
            print('garden terrace line dropped (upper side leaves the garden)', round(ln[0].x, 1), round(ln[0].y, 1))
            continue
        if not ln[2] and sh < 0.5:
            print('garden terrace line dropped (soft)', round(ln[0].x, 1), round(ln[0].y, 1), round(sh, 2))
            continue
        if all(abs((ln[0] - k[0]).dot(Vector((-k[1].y, k[1].x)))) > 6.0 for k in keep):
            keep.append(ln)
    edges = []                                           # local: survives module reloads by call_v2
    stair_ids = set()
    for m, t, osm in keep:
        n = Vector((-t.y, t.x))
        if raw(m + n * W) > raw(m - n * W):
            n = -n                                       # n points to the lower terrace
        if raw(m - n * W) - raw(m + n * W) < 0.5:
            continue
        rng = _clip(poly, m, t)
        if not rng:
            continue
        ss = [rng[0] + 1.0 + 1.5 * k for k in range(int((rng[1] - rng[0] - 2.0) / 1.5) + 1)]
        zh_e = _median([eased(m + t * s - n * (W + 0.1)) for s in ss])
        zl_e = _median([eased(m + t * s + n * (W + 0.1)) for s in ss])
        sts = []
        for f in steps:
            A, B = Vector(f['pts'][0][:2]), Vector(f['pts'][-1][:2])
            da, db = (A - m).dot(n), (B - m).dot(n)
            if not (min(da, db) < 1.5 and max(da, db) > -1.5):
                continue                                 # flight does not reach this wall
            u = (0 - da) / (db - da) if abs(db - da) > 1e-6 else 0.5
            cr = A + (B - A) * max(0.0, min(1.0, u))
            s_c = (cr - m).dot(t)
            if not rng[0] + 1.0 < s_c < rng[1] - 1.0:
                continue
            base = m + t * s_c
            zh, zl = eased(base - n * (W + 0.1)), eased(base + n * (W + 0.1))
            k = max(1, int(math.ceil((zh - zl) / RISE)))
            on_axis = axial(base)
            sts.append(dict(s=s_c, w=5.0 if on_axis else 3.0, zh=zh, zl=zl, k=k, rise=(zh - zl) / k, run=k * TREAD,
                            base=base, id=f['id']))
            stair_ids.add(f['id'])
        edges.append(dict(p=m, t=t, n=n, s0=rng[0], s1=rng[1], stairs=sts, osm=osm, zh=zh_e, zl=zl_e))
    T.terrace_edges = edges
    globals()['LAST_EDGES'] = edges
    T.garden_wall_ids = {f['id'] for f in walls}
    T.garden_stair_ids = stair_ids
    # flights on one plateau (e.g. 513653100): the sharpened ground is level there, a generic flight would be
    # two loose stone blocks with cheek walls - the walk stays open instead
    T.garden_flat_steps = {f['id'] for f in steps if f['id'] not in stair_ids and abs(raw(Vector(f['pts'][0][:2])) - raw(Vector(f['pts'][-1][:2]))) < 0.5}
    print('garden terrace edges', [(round(e['p'].x, 1), round(e['p'].y, 1), round(e['zh'], 2), round(e['zl'], 2),
                                    [(round(s['s'], 1), s['k']) for s in e['stairs']]) for e in edges])

    def sharpen(x, y, zr):
        q = Vector((x, y))
        for e in edges:
            r = q - e['p']
            d = r.dot(e['n'])
            if d <= -W or d >= W:
                continue
            s = r.dot(e['t'])
            if s < e['s0'] - 1.0 or s > e['s1'] + 1.0:
                continue
            for st in e['stairs']:
                if abs(s - st['s']) < st['w'] / 2 + 0.6 and d < st['run'] + 2.0:
                    if d <= 0:
                        return st['zh']
                    return max(st['zl'], st['zh'] - st['rise'] * (d / TREAD + 1.0))   # lower envelope of the treads
            base = e['p'] + e['t'] * s
            return eased(base + e['n'] * (-W if d < CUT else W))
        return zr
    return sharpen


# ---------------------------------------------------------------- geometry
def _bal(H, mb, a, b, za, zb, top=True):
    """Balustrade on a (possibly sloping) base line a(za) -> b(zb): balusters, handrail, collision sheet."""
    Vector, oriented_poly = H['Vector'], H['oriented_poly']
    L = (b - a).length
    if L < 0.05:
        return
    d = (b - a) / L
    nn = Vector((-d.y, d.x))
    up = Vector((0, 0, 1))
    for k in range(max(1, int(L / 0.3))):
        t = (k + 0.5) / max(1, int(L / 0.3))
        m = a.lerp(b, t)
        z = za + (zb - za) * t
        H['lathe_up'](mb, m, z + 0.1, [(0.0, 0.0), (0.06, 0.0), (0.045, 0.1), (0.085, 0.3), (0.045, 0.52), (0.0, 0.6)], 'marble', seg=6)
    for z0, z1, hw in ((0.0, 0.1, 0.17), (0.7, 0.86, 0.2)):     # bottom rail + handrail, sloping
        A0, A1 = Vector((a.x, a.y, za)), Vector((b.x, b.y, zb))
        q = lambda P, o, z: Vector((P.x + nn.x * o, P.y + nn.y * o, P.z + z))
        quads = [([q(A0, -hw, z1), q(A1, -hw, z1), q(A1, hw, z1), q(A0, hw, z1)], up),
                 ([q(A0, -hw, z0), q(A1, -hw, z0), q(A1, -hw, z1), q(A0, -hw, z1)], Vector((-nn.x, -nn.y, 0))),
                 ([q(A0, hw, z0), q(A1, hw, z0), q(A1, hw, z1), q(A0, hw, z1)], Vector((nn.x, nn.y, 0)))]
        for pts, want in quads:
            oriented_poly(mb, pts, want, 'marble')
    sheet = [Vector((a.x, a.y, za)), Vector((b.x, b.y, zb)), Vector((b.x, b.y, zb + 0.86)), Vector((a.x, a.y, za + 0.86))]
    mb.poly(sheet, 'invisible')
    mb.poly(list(reversed(sheet)), 'invisible')


def _slab_wall(H, mb, a, b, za_top, zb_top, z_foot, n_off0, n_off1, mat='plaster'):
    """Solid wall between offsets n_off0..n_off1 (left normal) of a->b, sloping top za_top -> zb_top."""
    Vector, oriented_poly = H['Vector'], H['oriented_poly']
    d = (b - a).normalized()
    nn = Vector((-d.y, d.x))
    B = [a + nn * n_off0, b + nn * n_off0, b + nn * n_off1, a + nn * n_off1]
    zt = [za_top, zb_top, zb_top, za_top]
    bot = [Vector((p.x, p.y, z_foot)) for p in B]
    top = [Vector((p.x, p.y, z)) for p, z in zip(B, zt)]
    cen = sum(bot + top, Vector((0, 0, 0))) / 8
    for f in [top, list(reversed(bot))] + [[bot[k], bot[(k + 1) % 4], top[(k + 1) % 4], top[k]] for k in range(4)]:
        oriented_poly(mb, f, sum(f, Vector((0, 0, 0))) / len(f) - cen, mat)


def _block(H, mb, B, zt, z_foot, mat):
    """Closed block over the 2D quad B with per-corner top heights zt and a flat foot."""
    Vector, oriented_poly = H['Vector'], H['oriented_poly']
    bot = [Vector((q.x, q.y, z_foot)) for q in B]
    top = [Vector((q.x, q.y, z)) for q, z in zip(B, zt)]
    cen = sum(bot + top, Vector((0, 0, 0))) / 8
    for f in [top, list(reversed(bot))] + [[bot[k], bot[(k + 1) % 4], top[(k + 1) % 4], top[k]] for k in range(4)]:
        oriented_poly(mb, f, sum(f, Vector((0, 0, 0))) / len(f) - cen, mat)


def _pedestal(H, mb, c, z_foot, z_top):
    Vector = H['Vector']
    q = [c + Vector((-0.3, -0.3)), c + Vector((0.3, -0.3)), c + Vector((0.3, 0.3)), c + Vector((-0.3, 0.3))]
    mb.box(q, z_foot, z_top, 'plaster')
    q2 = [c + Vector((-0.36, -0.36)), c + Vector((0.36, -0.36)), c + Vector((0.36, 0.36)), c + Vector((-0.36, 0.36))]
    mb.box(q2, z_top, z_top + 0.12, 'marble')
    H['lathe_up'](mb, c, z_top + 0.12, [(0.0, 0.0), (0.16, 0.0), (0.16, 0.06), (0.07, 0.12), (0.2, 0.32), (0.14, 0.48),
                                        (0.04, 0.54), (0.08, 0.6), (0.0, 0.72)], 'marble', seg=10)


def _snap_terrain(T, edges, Vector):
    """The 2 m terrain grid cannot hold a vertical step: move the grid vertices within 1.2 m of each step line
    (CUT) onto it, so the terrain drops crisply there (hidden under the gravel walk) instead of a 2-3 m smear."""
    import bpy
    ob = bpy.data.objects.get('Terrain-col')
    if not ob:
        return
    moved = 0
    for v in ob.data.vertices:
        q = Vector((v.co.x, v.co.y))
        for e in edges:
            r = q - e['p']
            d = r.dot(e['n'])
            if abs(d - CUT) > 1.2:
                continue
            s_ = r.dot(e['t'])
            if not e['s0'] - 0.5 < s_ < e['s1'] + 0.5 or any(abs(s_ - st['s']) < st['w'] / 2 + 1.0 for st in e['stairs']):
                continue
            dz0 = v.co.z - T.h(q.x, q.y)                 # keep build_terrain's sink offset
            q2 = q + e['n'] * ((CUT - 0.03 if d < CUT else CUT + 0.03) - d)
            v.co.x, v.co.y, v.co.z = q2.x, q2.y, T.h(q2.x, q2.y) + dz0
            moved += 1
            break
    ob.data.update()
    print('garden terrain vertices snapped to terrace steps', moved)


def build(H, T, coll, feats=None, rep=None):
    edges = getattr(T, 'terrace_edges', None)
    if not edges:
        return []
    MB, Vector = H['MB'], H['Vector']
    mb = MB('Garden_Terraces-col')
    _snap_terrain(T, edges, Vector)
    stairs_all = []
    for e in edges:
        p, t, n = e['p'], e['t'], e['n']
        zh, zl = e['zh'], e['zl']
        foot = zl - 0.8
        s0, s1 = e['s0'] + 0.4, e['s1'] - 0.4
        opens = sorted((st['s'] - st['w'] / 2 - 0.55, st['s'] + st['w'] / 2 + 0.55) for st in e['stairs'])
        runs, cur = [], s0
        for o0, o1 in opens:
            if o0 > cur:
                runs.append((cur, o0))
            cur = max(cur, o1)
        if cur < s1:
            runs.append((cur, s1))
        # upper-terrace elevation along the wall, smoothed so walls, rails and the walk slope continuously
        zfun = lambda s_: sum(T.h(*(p + t * (s_ + o) - n * (W + 0.1))) for o in (-1.5, 0.0, 1.5)) / 3.0
        for r0, r1 in runs:                              # wall + coping + balustrade + gravel walk
            kk = max(1, int(round((r1 - r0) / 1.5)))
            ss = [r0 + (r1 - r0) * i / kk for i in range(kk + 1)]
            zs = [zfun(s_) for s_ in ss]
            for i in range(kk):
                a, b = p + t * ss[i], p + t * ss[i + 1]
                za, zb = zs[i], zs[i + 1]
                _block(H, mb, [a, b, b - n * WALL_T, a - n * WALL_T], [za, zb, zb, za], foot, 'plaster')
                _block(H, mb, [a + n * 0.06, b + n * 0.06, b - n * (WALL_T + 0.06), a - n * (WALL_T + 0.06)],
                       [za + 0.12, zb + 0.12, zb + 0.12, za + 0.12], min(za, zb) - 0.02, 'marble')
                _block(H, mb, [a - n * WALL_T, b - n * WALL_T, b - n * WALK, a - n * WALK], [za + 0.03, zb + 0.03, zb + 0.03, za + 0.03],
                       min(za, zb) - 0.45, 'gravel_white')
                la, lb = T.h(*(a + n * 0.9)) + 0.28, T.h(*(b + n * 0.9)) + 0.28       # continuous stone footing (Codex 5)
                _block(H, mb, [a, b, b + n * 0.55, a + n * 0.55], [la, lb, lb, la], foot, 'stone')
            npd = max(1, int(round((r1 - r0) / 6.0)))     # pedestals every ~6 m, balustrade between them
            for k in range(npd + 1):
                s_ = r0 + (r1 - r0) * k / npd
                _pedestal(H, mb, p + t * s_ - n * (WALL_T / 2), foot, zfun(s_) + 0.98)
                if k < npd:
                    s2 = r0 + (r1 - r0) * (k + 1) / npd
                    m_ = max(2, int((s2 - s_) / 1.5))
                    for j in range(m_):
                        sa, sb = s_ + (s2 - s_) * j / m_, s_ + (s2 - s_) * (j + 1) / m_
                        pa, pb = p + t * sa - n * (WALL_T / 2), p + t * sb - n * (WALL_T / 2)
                        if j == 0:
                            pa = pa + t * 0.36
                        if j == m_ - 1:
                            pb = pb - t * 0.36
                        _bal(H, mb, pa, pb, zfun(sa) + 0.12, zfun(sb) + 0.12)
        for st in e['stairs']:                           # broad flight, perpendicular to the wall, sloping balustrades
            c = p + t * st['s']
            w, k, rise = st['w'], st['k'], st['rise']
            for i in range(k):
                a0 = c + n * (i * TREAD)
                zt = st['zh'] - (i + 1) * rise
                mb.box([a0 - t * (w / 2), a0 + t * (w / 2), a0 + t * (w / 2) + n * TREAD, a0 - t * (w / 2) + n * TREAD],
                       st['zl'] - 0.6, zt, 'limestone')
            mb.box([c - t * (w / 2 + 0.55) - n * 1.6, c + t * (w / 2 + 0.55) - n * 1.6, c + t * (w / 2 + 0.55), c - t * (w / 2 + 0.55)],
                   st['zh'] - 0.4, st['zh'] + 0.02, 'limestone')                                   # top landing
            e_ = c + n * st['run']
            mb.box([e_ - t * (w / 2), e_ + t * (w / 2), e_ + t * (w / 2) + n * 1.2, e_ - t * (w / 2) + n * 1.2],
                   st['zl'] - 0.4, st['zl'] + 0.02, 'limestone')                                   # bottom landing
            for sg in (-1, 1):
                side = c + t * (sg * (w / 2 + 0.25))
                top_p, bot_p = side, side + n * st['run']
                d0 = (bot_p - top_p).normalized()
                lft = Vector((-d0.y, d0.x))
                ztop0, ztop1 = st['zh'] + 0.12, st['zl'] + 0.12
                # sloping cheek wall
                _slab_wall(H, mb, top_p, bot_p, ztop0, ztop1, st['zl'] - 0.6, -0.25, 0.25, 'plaster')
                _bal(H, mb, top_p + d0 * 0.36, bot_p - d0 * 0.36, ztop0, ztop1)
                _pedestal(H, mb, top_p, foot, st['zh'] + 0.98)
                _pedestal(H, mb, bot_p, st['zl'] - 0.6, st['zl'] + 0.98)
            stairs_all.append((c, n, t, st))
            if rep is not None:
                rep.add(st['id'])
    if rep is not None:
        rep.update(getattr(T, 'garden_flat_steps', ()))
    # other OSM walls inside the garden (axial corridor, boundary): continuous sloping balustrades
    if feats is not None:
        wid = getattr(T, 'garden_wall_ids', set())

        def in_stair(q):
            for c, n, t, st in stairs_all:
                r = q - c
                if -2.0 < r.dot(n) < st['run'] + 1.4 and abs(r.dot(t)) < st['w'] / 2 + 0.9:
                    return True
            return False

        def near_edge(q):
            return any(abs((q - e['p']).dot(e['n'])) < 1.0 and e['s0'] - 1 < (q - e['p']).dot(e['t']) < e['s1'] + 1 for e in edges)
        for f in feats:
            if f['id'] not in wid:
                continue
            pl = [Vector(q[:2]) for q in f['pts']]
            seg = []
            for a, b in zip(pl, pl[1:]):
                L = (b - a).length
                for i in range(max(1, int(L / 1.2))):
                    seg.append((a.lerp(b, i / max(1, int(L / 1.2))), a.lerp(b, (i + 1) / max(1, int(L / 1.2)))))
            if not seg:
                continue

            def tops(q, d):                              # rail on the garden side, foot on the far lower slope
                nn = Vector((-d.y, d.x))
                return (max(T.h(*(q + nn * 1.2)), T.h(*(q - nn * 1.2))), min(T.h(*(q + nn * 4.0)), T.h(*(q - nn * 4.0))))
            nodes = [seg[0][0]] + [b for a, b in seg]
            zs = []
            for i, q in enumerate(nodes):
                a_, b_ = nodes[max(0, i - 1)], nodes[min(len(nodes) - 1, i + 1)]
                d = (b_ - a_).normalized() if (b_ - a_).length > 1e-6 else Vector((1, 0))
                zs.append(tops(q, d))
            hi = [z[0] for z in zs]
            lo = [z[1] for z in zs]
            hs = [sum(hi[max(0, i - 2):i + 3]) / len(hi[max(0, i - 2):i + 3]) for i in range(len(hi))]   # smoothed rail
            for i, (a, b) in enumerate(seg):
                m = (a + b) / 2
                if in_stair(m) or near_edge(m):
                    continue
                foot_ = min(lo[i], lo[i + 1]) - 0.6
                tall = min(hs[i], hs[i + 1]) - foot_ > 2.0      # W edge: continuous stone retaining face (Earth)
                _slab_wall(H, mb, a, b, hs[i], hs[i + 1], foot_, -0.3 if tall else -0.25, 0.3 if tall else 0.25,
                           'stone' if tall else 'plaster')
                _bal(H, mb, a, b, hs[i], hs[i + 1])
            if rep is not None:
                rep.add(f['id'])
    return [mb.build(coll)]


# ---------------------------------------------------------------- parterre (called from build_garden)
def smooth_mask(m, k=2, passes=2):
    """Blur a bool grid with a (2k+1)^2 box `passes` times and re-threshold: clean, rounded outlines."""
    import numpy as np
    f = m.astype(np.float32)
    for _ in range(passes):
        acc = np.zeros_like(f)
        for dy in range(-k, k + 1):
            for dx in range(-k, k + 1):
                acc += np.roll(np.roll(f, dy, 0), dx, 1)
        f = acc / float((2 * k + 1) ** 2)
    return f > 0.5


def _thin(m):
    """Zhang-Suen thinning of a bool grid -> 1 px wide 8-connected skeleton."""
    import numpy as np
    img = np.pad(m.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            P2, P3, P4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            P5, P6, P7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            P8, P9 = img[1:-1, :-2], img[:-2, :-2]
            nb = [P2, P3, P4, P5, P6, P7, P8, P9]
            B = sum(x.astype(np.int16) for x in nb)
            A = sum(((nb[i] == 0) & (nb[(i + 1) % 8] == 1)).astype(np.int16) for i in range(8))
            c = img[1:-1, 1:-1] == 1
            if step == 0:
                cond = c & (B >= 2) & (B <= 6) & (A == 1) & ((P2 * P4 * P6) == 0) & ((P4 * P6 * P8) == 0)
            else:
                cond = c & (B >= 2) & (B <= 6) & (A == 1) & ((P2 * P4 * P8) == 0) & ((P2 * P6 * P8) == 0)
            if cond.any():
                img[1:-1, 1:-1][cond] = 0
                changed = True
        if not changed:
            break
    return img[1:-1, 1:-1].astype(bool)


def _trace(sk):
    """Skeleton pixels -> polylines of (j, i) split at end points and junctions."""
    import numpy as np
    pix = set(zip(*[a.tolist() for a in np.nonzero(sk)]))
    nbrs = lambda p: [(p[0] + dj, p[1] + di) for dj in (-1, 0, 1) for di in (-1, 0, 1) if (dj or di) and (p[0] + dj, p[1] + di) in pix]
    deg = {p: len(nbrs(p)) for p in pix}
    used = set()                                         # undirected pixel-pair edges already walked
    lines = []

    def walk(a, b):
        line = [a, b]
        used.add((a, b))
        used.add((b, a))
        prev, cur = a, b
        while deg[cur] == 2:
            nxt = [q for q in nbrs(cur) if q != prev and (cur, q) not in used]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            used.add((prev, cur))
            used.add((cur, prev))
            line.append(cur)
        return line
    for p in pix:
        if deg[p] != 2:
            for q in nbrs(p):
                if (p, q) not in used:
                    lines.append(walk(p, q))
    for p in pix:                                        # closed loops (all degree 2)
        for q in nbrs(p):
            if (p, q) not in used:
                lines.append(walk(p, q))
    return lines


def _simplify(P, eps):
    if len(P) < 3:
        return P
    a, b = P[0], P[-1]
    ab = (b[0] - a[0], b[1] - a[1])
    L = math.hypot(*ab) + 1e-12
    dmax, k = -1.0, 0
    for i in range(1, len(P) - 1):
        d = abs((P[i][0] - a[0]) * ab[1] - (P[i][1] - a[1]) * ab[0]) / L
        if d > dmax:
            dmax, k = d, i
    if dmax > eps:
        return _simplify(P[:k + 1], eps)[:-1] + _simplify(P[k:], eps)
    return [a, b]


def _chaikin(P, it=2):
    for _ in range(it):
        if len(P) < 3:
            return P
        Q = [P[0]]
        for a, b in zip(P, P[1:]):
            Q += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        Q.append(P[-1])
        P = Q
    return P


def _sweep(H, mb, V, w, hh, zv, closed, mat='box_hedge'):
    """Flat-topped clipped hedge strip along polyline V (2D Vectors): top, both sides, end caps; mitred joints."""
    Vector, oriented_poly = H['Vector'], H['oriented_poly']
    up = Vector((0, 0, 1))
    V = [v for k, v in enumerate(V) if k == 0 or (v - V[k - 1]).length > 0.02]
    if closed and (V[0] - V[-1]).length < 0.02:
        V = V[:-1]
    if len(V) < 2:
        return
    if not closed:                                       # ends reach half a width further (overlap at junctions)
        V[0] = V[0] + (V[0] - V[1]).normalized() * (w / 2)
        V[-1] = V[-1] + (V[-1] - V[-2]).normalized() * (w / 2)
    n = len(V)
    N = []
    for k in range(n):
        if closed:
            d0, d1 = V[k] - V[k - 1], V[(k + 1) % n] - V[k]
        else:
            d0 = (V[k] - V[k - 1]) if k > 0 else (V[1] - V[0])
            d1 = (V[k + 1] - V[k]) if k < n - 1 else (V[k] - V[k - 1])
        d = d0.normalized() + d1.normalized()
        d = d.normalized() if d.length > 1e-6 else d1.normalized()
        n_ = Vector((-d.y, d.x))
        N.append(n_ / max(0.5, n_.dot(Vector((-d1.normalized().y, d1.normalized().x)))))
    Lp = [v + q * (w / 2) for v, q in zip(V, N)]
    Rp = [v - q * (w / 2) for v, q in zip(V, N)]
    zL = [zv(p.x, p.y) for p in Lp]
    zR = [zv(p.x, p.y) for p in Rp]
    top = lambda p, z: Vector((p.x, p.y, z + hh))
    bot = lambda p, z: Vector((p.x, p.y, z - 0.03))
    for k in range(n if closed else n - 1):
        j = (k + 1) % n
        oriented_poly(mb, [top(Lp[k], zL[k]), top(Rp[k], zR[k]), top(Rp[j], zR[j]), top(Lp[j], zL[j])], up, mat, uv_scale=0.8)
        nn = Vector((N[k].x + N[j].x, N[k].y + N[j].y, 0)).normalized()
        oriented_poly(mb, [bot(Lp[k], zL[k]), bot(Lp[j], zL[j]), top(Lp[j], zL[j]), top(Lp[k], zL[k])], nn, mat, uv_scale=0.8)
        oriented_poly(mb, [bot(Rp[k], zR[k]), bot(Rp[j], zR[j]), top(Rp[j], zR[j]), top(Rp[k], zR[k])], -nn, mat, uv_scale=0.8)
    if not closed:
        for k, k2 in ((0, 1), (n - 1, n - 2)):
            out = Vector((V[k].x - V[k2].x, V[k].y - V[k2].y, 0)).normalized()
            oriented_poly(mb, [bot(Lp[k], zL[k]), bot(Rp[k], zR[k]), top(Rp[k], zR[k]), top(Lp[k], zL[k])], out, mat, uv_scale=0.8)


def hedges(H, mb, hedge, low, gx0, gy0, cell, zv, HH=0.48, feats=(), gp=None):
    """Continuous clipped box hedges (refs 17/27):
    - every OSM lawn panel (landuse=grass) and broderie bed (landuse=flowerbed) gets a clean box border swept
      along its outline;
    - the broderie scrolls and remaining hedge rows come from the traced orthophoto mask: gaps < 0.6 m closed,
      thinned to a skeleton, split into polylines, simplified + smoothed and swept as 0.42 m strips (dwarf box
      0.32 m wide / 0.26 m high inside flowerbeds).  Scraps shorter than 0.8 m (2 m outside the beds) are dropped."""
    import numpy as np
    Vector = H['Vector']
    offset_poly, poly_area, pip_mask = H['offset_poly'], H['poly_area'], H['_pip_mask']
    ny, nx = hedge.shape
    XX, YY = np.meshgrid(gx0 + (np.arange(nx) + 0.5) * cell, gy0 + (np.arange(ny) + 0.5) * cell)
    near_outline = np.zeros(hedge.shape, dtype=bool)
    fence_mb = H['MB']('Garden_Fences')                  # visual only: the walks may brush the lawn corners
    n_out = 0
    for f in feats:
        lu = f['tags'].get('landuse')
        if f['kind'] != 'area' or lu not in ('grass', 'flowerbed') or not gp or not _pip(*f['pts'][0][:2], offset_poly(gp, 3.0)):
            continue
        pq = [tuple(p[:2]) for p in f['pts']]
        if (Vector(pq[0]) - Vector(pq[-1])).length < 1e-3:
            pq = pq[:-1]
        if poly_area(pq) < 0:
            pq.reverse()
        if abs(poly_area(pq)) < 1.5:
            continue
        try:
            ring = offset_poly(pq, -0.22)
            o_in, o_out = offset_poly(pq, -0.75), offset_poly(pq, 0.5)
        except ZeroDivisionError:
            continue
        if poly_area([tuple(p) for p in ring]) <= 0.3:
            continue
        w, hh = (0.36, 0.5) if lu == 'flowerbed' else (0.4, 0.42)
        _sweep(H, mb, [Vector(p) for p in ring], w, hh, zv, True)
        if lu == 'grass':                                # low iron hoop fence round the lawn panels (Earth / eye level)
            try:
                fr = [Vector(p[:2]) for p in offset_poly(pq, 0.28)]
            except ZeroDivisionError:
                fr = []
            for k_ in range(len(fr)):
                a_, b_ = fr[k_], fr[(k_ + 1) % len(fr)]
                L_ = (b_ - a_).length
                for j_ in range(max(1, int(L_ / 1.4))):
                    q_ = a_.lerp(b_, j_ / max(1, int(L_ / 1.4)))
                    z_ = zv(q_.x, q_.y)
                    H['_prism'](fence_mb, Vector((q_.x, q_.y, z_)), Vector((q_.x, q_.y, z_ + 0.42)), 0.012, 0.012, 'stage_dark', seg=4)
                za_, zb_ = zv(a_.x, a_.y), zv(b_.x, b_.y)
                H['_prism'](fence_mb, Vector((a_.x, a_.y, za_ + 0.4)), Vector((b_.x, b_.y, zb_ + 0.4)), 0.014, 0.014, 'stage_dark', seg=4)
        band = pip_mask(XX, YY, [tuple(p) for p in o_out])
        if poly_area([tuple(p) for p in o_in]) > 0.3:
            band &= ~pip_mask(XX, YY, [tuple(p) for p in o_in])
        near_outline |= band
        n_out += 1
    m = hedge & ~near_outline
    # the two big broderie parterres: explicit mirrored scroll paths replace the traced fragments
    bids = broderie_ids(feats, gp) if gp else set()
    if bids:
        Pg = [Vector(p[:2]) for p in gp]
        cg = sum(Pg, Vector((0, 0))) / len(Pg)
        sxx = sum((p.x - cg.x) ** 2 for p in Pg)
        syy = sum((p.y - cg.y) ** 2 for p in Pg)
        sxy = sum((p.x - cg.x) * (p.y - cg.y) for p in Pg)
        ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
        ug = Vector((math.cos(ang), math.sin(ang)))
        vg = Vector((-ug.y, ug.x))
        for f in feats:
            if f['id'] not in bids:
                continue
            pq = [Vector(p[:2]) for p in f['pts']]
            us, vs = [p.dot(ug) for p in pq], [p.dot(vg) for p in pq]
            bc = ug * ((min(us) + max(us)) / 2) + vg * ((min(vs) + max(vs)) / 2)
            hu, hv = (max(us) - min(us)) / 2 - 1.1, (max(vs) - min(vs)) / 2 - 1.1
            vo = vg if (bc - cg).dot(vg) > 0 else -vg            # outward: mirror image about the garden axis
            m &= ~pip_mask(XX, YY, [tuple(p) for p in pq])
            pin = [tuple(p) for p in offset_poly([tuple(p) for p in (pq if _area([tuple(p) for p in pq]) > 0 else pq[::-1])], -0.7)]
            paths_ = broderie_paths(hu, hv)
            for path in list(paths_[:3]) + list(paths_[3:7]):     # central S + side scrolls: paired lines (denser)
                paths_.append(_offset_path(path, 0.62))
            for path in paths_:
                W3 = [bc + ug * x + vo * y for x, y in path]
                if all(_pip(q.x, q.y, pin) for q in W3):     # chamfered bed corners: drop curls that leave the bed
                    _sweep(H, mb, W3, 0.24, 0.45, zv, False)
                    _sweep(H, mb, W3, 0.95, 0.15, zv, False, mat='grass')   # planted band along the scroll (Earth)
    for e in globals().get('LAST_EDGES', []):            # no hedges on the terrace walks, walls and stairs
        dd = (XX - e['p'].x) * e['n'].x + (YY - e['p'].y) * e['n'].y
        sv = (XX - e['p'].x) * e['t'].x + (YY - e['p'].y) * e['t'].y
        zone = (dd > -WALK - 0.3) & (dd < 0.4) & (sv > e['s0'] - 1.0) & (sv < e['s1'] + 1.0)
        for st in e['stairs']:
            zone |= (np.abs(sv - st['s']) < st['w'] / 2 + 0.8) & (dd > -2.0) & (dd < st['run'] + 1.6)
        m &= ~zone
    def disc(mm, k):
        out = mm.copy()
        for dy in range(-k, k + 1):
            for dx in range(-k, k + 1):
                if dx * dx + dy * dy <= k * k:
                    out |= np.roll(np.roll(mm, dy, 0), dx, 1)
        return out
    md = disc(m, 3) | (disc(m, 6) & low)                # close gaps < 0.6 m (broderie scrolls < 1.2 m) before thinning
    sk = _thin(md & ~near_outline)
    n_strips = 0
    ends = []                                            # free polyline ends -> bridged to the nearest other end
    traced = _trace(sk)
    for li, ln in enumerate(traced):
        if len(ln) >= 3 and not (abs(ln[0][0] - ln[-1][0]) <= 1 and abs(ln[0][1] - ln[-1][1]) <= 1):
            for (j0, i0), (j1, i1) in ((ln[0], ln[min(2, len(ln) - 1)]), (ln[-1], ln[max(-3, -len(ln))])):
                ends.append((li, Vector((gx0 + (i0 + 0.5) * cell, gy0 + (j0 + 0.5) * cell)),
                             Vector(((i0 - i1) * cell, (j0 - j1) * cell)).normalized(), bool(low[j0, i0])))
    used = set()
    for a_i, (la, pa, da, lowa) in enumerate(ends):
        if a_i in used:
            continue
        best = None
        for b_i, (lb, pb, db, lowb) in enumerate(ends):
            if b_i == a_i or b_i in used or lb == la:
                continue
            g = pb - pa
            L = g.length
            if 0.05 < L < (1.3 if lowa else 0.9) and da.dot(g / L) > 0.3 and db.dot(-g / L) > 0.3 and (best is None or L < best[0]):
                best = (L, b_i, pb)
        if best:
            used |= {a_i, best[1]}
            w, hh = (0.24, 0.2) if lowa else (0.42, HH)
            _sweep(H, mb, [pa, best[2]], w, hh, zv, False)
    for ln in traced:
        P = [(gx0 + (i + 0.5) * cell, gy0 + (j + 0.5) * cell) for j, i in ln]
        L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(P, P[1:]))
        jm, im = ln[len(ln) // 2]
        is_low = bool(low[min(ny - 1, jm), min(nx - 1, im)])
        if L < (1.2 if is_low else 2.0):            # short links kept (closed star outlines), scraps dropped
            continue
        closed = len(ln) > 3 and abs(ln[0][0] - ln[-1][0]) <= 1 and abs(ln[0][1] - ln[-1][1]) <= 1
        P = _chaikin(_simplify(P, 0.06 if is_low else 0.15), 2 if is_low else 3)
        w, hh = (0.24, 0.2) if is_low else (0.42, HH)      # inner broderie scrolls: lower and thinner than borders
        _sweep(H, mb, [Vector(p) for p in P], w, hh, zv, closed)
        n_strips += 1
    knots(H, mb, zv, globals().get('LAST_EDGES', []), gp)
    import bpy
    fence_mb.build(bpy.data.collections.get('BratislavaCastle'))
    print('garden hedge strips', n_strips, 'bed/lawn borders', n_out, 'skeleton px', int(sk.sum()))


def fill_tree_grid(H, trees, extra, dark, gx0, gy0, cell, gp, feats):
    """Photo 17: the clipped lindens stand on a dense regular grid.  Grow the grid from the known crowns
    (OSM + ortho blobs): a neighbour one grid step along / across the garden axis is planted where the
    orthophoto is dark (crown shade) there, the spot is free and not on a path, stair or terrace walk."""
    import numpy as np
    Vector, offset_poly, dist_seg = H['Vector'], H['offset_poly'], H['dist_seg']
    pts = list(trees) + list(extra)
    if len(pts) < 8:
        return []
    P = [Vector(p[:2]) for p in gp]
    c = sum(P, Vector((0, 0))) / len(P)
    sxx = sum((p.x - c.x) ** 2 for p in P)
    syy = sum((p.y - c.y) ** 2 for p in P)
    sxy = sum((p.x - c.x) * (p.y - c.y) for p in P)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    u = Vector((math.cos(ang), math.sin(ang)))
    v = Vector((-u.y, u.x))
    nn = sorted(min((q - p).length for q in pts if q is not p) for p in pts)
    sp = nn[len(nn) // 2]
    if not 2.5 < sp < 8.0:
        return []
    inner = offset_poly(gp, -1.5)
    paths = [[Vector(q[:2]) for q in f['pts']] for f in feats if f['kind'] == 'road' and f['tags'].get('highway') in ('footway', 'steps', 'path', 'pedestrian')]
    ny, nx = dark.shape
    r = int(1.1 / cell)

    def shade(q):
        i, j = int((q.x - gx0) / cell), int((q.y - gy0) / cell)
        if not (r <= i < nx - r and r <= j < ny - r):
            return 0.0
        return float(dark[j - r:j + r + 1, i - r:i + r + 1].mean())

    def blocked(q):
        for e in globals().get('LAST_EDGES', []):
            d = (q - e['p']).dot(e['n'])
            if -WALK - 1.0 < d < 1.0:
                return True
        return any(dist_seg(q, a, b) < 1.6 for pl in paths for a, b in zip(pl, pl[1:]))
    new = []
    frontier = pts[:]
    for _ in range(3):
        nxt = []
        for t in frontier:
            for dv in (u * sp, -u * sp, v * sp, -v * sp):
                q = t + dv
                if not _pip(q.x, q.y, inner) or any((q - o).length < 0.6 * sp for o in pts + new):
                    continue
                if shade(q) < 0.45 or blocked(q):
                    continue
                new.append(q)
                nxt.append(q)
        frontier = nxt
    print('garden linden grid: spacing %.2f m, added %d' % (sp, len(new)))
    return new


def _area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def broderie_ids(feats, gp):
    """The two large broderie parterres by the palace (OSM flowerbeds > 200 m2 inside the garden)."""
    return {f['id'] for f in feats if f['kind'] == 'area' and f['tags'].get('landuse') == 'flowerbed'
            and _pip(f['pts'][0][0], f['pts'][0][1], gp) and abs(_area([p[:2] for p in f['pts']])) > 200}


def _bezier(p0, p1, p2, p3, n=16):
    out = []
    for k in range(n + 1):
        t = k / n
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def _spiral(cx, cy, r0, r1, a0, turns, sgn, n=None):
    n = n or int(28 * turns)
    out = []
    for k in range(n + 1):
        t = k / n
        a = a0 + sgn * 2 * math.pi * turns * t
        r = r0 + (r1 - r0) * t
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def _offset_path(path, off):
    out = []
    for i in range(len(path)):
        a = path[max(0, i - 1)]
        b = path[min(len(path) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        out.append((path[i][0] - dy / L * off, path[i][1] + dx / L * off))
    return out


def knots(H, mb, zv, edges, gp):
    """Earth: just below the broderie terrace two green panels with continuous pale looping paths (knots),
    mirrored about the garden axis: lawn panel + an outer oval walk and a figure-of-eight loop."""
    Vector = H['Vector']
    if len(edges) < 2:
        return
    A, B = sorted(edges, key=lambda e: e['p'].y)[:2]
    t, n = A['t'], A['n']
    gap = (B['p'] - A['p']).dot(n)
    if gap < 8.0:
        return
    P = [Vector(p[:2]) for p in gp]
    cg = sum(P, Vector((0, 0))) / len(P)
    mid = A['p'] + t * ((cg - A['p']).dot(t)) + n * (gap / 2)      # on the garden axis, midway between the walls
    hn = gap / 2 - WALK - 1.2
    hl = 6.5
    for side in (-1, 1):
        c = mid + t * (side * 12.5)
        if not _pip(c.x, c.y, gp):
            continue
        k = 0.5
        for i in range(int(2 * hl / k)):
            for j in range(int(2 * hn / k)):
                q = [c + t * (-hl + i * k) + n * (-hn + j * k), c + t * (-hl + (i + 1) * k) + n * (-hn + j * k),
                     c + t * (-hl + (i + 1) * k) + n * (-hn + (j + 1) * k), c + t * (-hl + i * k) + n * (-hn + (j + 1) * k)]
                H['oriented_poly'](mb, [Vector((p_.x, p_.y, zv(p_.x, p_.y) + 0.14)) for p_ in q], Vector((0, 0, 1)), 'grass')
        oval = [c + t * ((hl - 0.8) * math.cos(2 * math.pi * k_ / 48)) + n * ((hn - 0.6) * math.sin(2 * math.pi * k_ / 48)) for k_ in range(48)]
        eight = [c + t * ((hl - 1.8) * math.sin(2 * math.pi * k_ / 64)) + n * ((hn - 1.1) * math.sin(4 * math.pi * k_ / 64) * side)
                 for k_ in range(64)]
        _sweep(H, mb, oval, 0.7, 0.17, zv, True, mat='gravel_white')
        _sweep(H, mb, eight, 0.6, 0.17, zv, True, mat='gravel_white')


def broderie_paths(hu, hv):
    """Paired scroll pattern in a bed frame (u along the garden axis, v outward from it), metres from the
    bed centre: a central S of two volutes (point-symmetric, ref 17), two long C-scrolls along the sides
    with curled ends, and small leaf curls at the four corners."""
    R0 = min(0.5 * hv, 0.3 * hu)
    L = (-0.42 * hu, 0.0)
    paths = []
    left = _spiral(L[0], L[1], R0, 0.45, 0.0, 2.0, 1)
    right = [(-x, -y) for x, y in left]
    paths += [left, right]
    k = 0.75 * hv
    a, b = left[0], right[0]
    paths.append(_bezier(a, (a[0], a[1] - k), (b[0], b[1] + k), b, 24))
    for sv in (-1, 1):                                   # side C-scrolls with inward curls
        y = sv * 0.8 * hv
        x0, x1 = -0.62 * hu, 0.62 * hu
        mid = _bezier((x0, y), (-0.25 * hu, y - sv * 0.35 * hv), (0.25 * hu, y - sv * 0.35 * hv), (x1, y), 24)
        r = 0.16 * hv
        curl0 = _spiral(x0 - r * 0.0, y - sv * r, r, 0.2, sv * math.pi / 2, 1.1, -sv)
        curl1 = _spiral(x1, y - sv * r, r, 0.2, sv * math.pi / 2, 1.1, sv)
        paths += [list(reversed(curl0)) + mid[1:], curl1]
        for su in (-1, 1):                               # corner leaf curls
            cxy = (su * 0.86 * hu, sv * 0.55 * hv)
            paths.append(_spiral(cxy[0], cxy[1], 0.12 * hv, 0.15, 0.0 if su > 0 else math.pi, 1.3, su * sv))
    # interlocking inner spirals of the central pair (double volute)
    inner = _spiral(L[0], L[1], R0 * 0.72, 0.35, math.pi, 1.6, 1)
    paths += [inner, [(-x, -y) for x, y in inner]]
    for su in (-1, 1):                                   # quadrant volutes, mirrored
        for sv in (-1, 1):
            c_ = (su * 0.74 * hu, sv * 0.42 * hv)
            paths.append(_spiral(c_[0], c_[1], 0.2 * hv, 0.25, math.pi / 2 * (1 - sv), 1.5, su * sv))
    return paths


def planters(H, mb, busy, gx0, gy0, cell, zv, gp, feats, trees):
    """Ref 27: white Versailles planters with small clipped ball trees in rows beside the axial walks.
    Candidates every 4.5 m at 2.6 m either side of the garden axis; kept only on free gravel (no bed, lawn
    or hedge within 0.8 m, no tree within 1.6 m, off terrace walls / stairs / walks, clear of every OSM path)."""
    import numpy as np
    Vector, dist_seg, offset_poly, icos = H['Vector'], H['dist_seg'], H['offset_poly'], H['icosphere']
    P = [Vector(p[:2]) for p in gp]
    c = sum(P, Vector((0, 0))) / len(P)
    sxx = sum((p.x - c.x) ** 2 for p in P)
    syy = sum((p.y - c.y) ** 2 for p in P)
    sxy = sum((p.x - c.x) * (p.y - c.y) for p in P)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    u = Vector((math.cos(ang), math.sin(ang)))
    v = Vector((-u.y, u.x))
    paths = [([Vector(q[:2]) for q in f['pts']], f['tags'].get('highway')) for f in feats
             if f['kind'] == 'road' and f['tags'].get('highway') in ('footway', 'steps', 'path', 'pedestrian')]
    axis_paths = [pl for pl, hw in paths if any(_pip(q.x, q.y, gp) for q in pl)]
    inner = offset_poly(gp, -2.0)
    ny, nx = busy.shape
    r = int(0.8 / cell)
    us = [(p - c).dot(u) for p in P]
    placed = 0
    for side in (-1, 1):
        s = min(us) + 3.0
        while s < max(us) - 3.0:
            q = c + u * s + v * (side * 2.6)
            s += 4.5
            if not _pip(q.x, q.y, inner):
                continue
            i, j = int((q.x - gx0) / cell), int((q.y - gy0) / cell)
            if not (r <= i < nx - r and r <= j < ny - r) or busy[j - r:j + r + 1, i - r:i + r + 1].any():
                continue
            if any((q - t).length < 1.6 for t in trees):
                continue
            if any(-WALK - 1.0 < (q - e['p']).dot(e['n']) < 1.0 for e in globals().get('LAST_EDGES', [])):
                continue
            if any(dist_seg(q, a, b) < 1.4 for pl in axis_paths for a, b in zip(pl, pl[1:])):
                continue
            z = zv(q.x, q.y)
            sq = lambda h: [q + Vector((-h, -h)), q + Vector((h, -h)), q + Vector((h, h)), q + Vector((-h, h))]
            mb.box(sq(0.45), z - 0.05, z + 0.8, 'plaster_lime')          # white box
            for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):            # corner posts + ball finials
                cp = q + Vector((dx * 0.45, dy * 0.45))
                mb.box([cp + Vector((-0.06, -0.06)), cp + Vector((0.06, -0.06)), cp + Vector((0.06, 0.06)), cp + Vector((-0.06, 0.06))],
                       z - 0.05, z + 0.92, 'plaster_lime')
                icos(mb, Vector((cp.x, cp.y, z + 0.98)), 0.06, 'plaster_lime', smooth=True, subdiv=1)
            mb.box(sq(0.4), z + 0.8, z + 0.84, 'gravel')                   # soil
            mb.box(sq(0.035), z + 0.84, z + 1.5, 'frame')                  # stem
            icos(mb, Vector((q.x, q.y, z + 1.95)), 0.5, 'box_hedge', smooth=True, subdiv=2)    # clipped ball
            placed += 1
    print('garden planters', placed)
