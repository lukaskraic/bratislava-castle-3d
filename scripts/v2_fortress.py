"""V2: fortifications and castle-area buildings of Bratislava Castle.

Called from build_castle.main() before build_city:  build(H, T, feats, points, coll)
H = build_castle globals (helpers, materials).  Every OSM way rebuilt here is added to
H['REPLACED_IDS'] so the generic extrusion / wall code skips it.

Sources: OSM footprints + passages (castle_local.json), ZBGIS DMR heights, data/ref/v2/SPEC.md and
photos in data/ref/v2 (19-26) and data/ref/fortress/.
- Vienna Gate (1712): one-storey ochre gatehouse, grey stone pilasters, round carriage arch + 2 side doors,
  low pediment, urns, attached octagonal turret with a green copper bell dome.
- Leopold Gate (1674): stone portal (pilasters, entablature, imperial arms, 3 stone balls) in the 10-12 m
  rubble wall of the Leopold bastion; the vaulted passage (OSM 37409845) runs under the lawn terrace.
- Sigismund Gate: square ashlar tower, steep pyramid roof, segmental portal under a Gothic ogee gable.
- Nicholas Gate: plain brick arch through a rubble wall block (OSM steps run through it).
- Luginsland: round battered rubble bastion, cordon at 2/3 height, round gun ports, box oriel.
- S/SW bastions: angular rubble walls, red tile coping, row of small round-arched embrasures, no crenels.
"""
import json
import math
import os

NAMES = ('MB', 'ChunkMB', 'seg_box', 'wall', 'slab', 'sweep', 'oriented_poly', '_prism', 'ellipsoid',
         'lathe_up', 'window_simple', 'arch_head', 'make_mat', 'tint_mat', 'MATS', 'Vector',
         'point_in_poly', 'offset_poly', 'dist_seg', 'poly_area', 'pane', 'balustrade',
         'sph_mb_ring', 'add_light', 'lantern', 'geometry')

SIGISMUND, LEOPOLD_BASTION, VIENNA, NICHOLAS = 37409838, 37409839, 37409828, 950103752
LEOPOLD_TERRACE, HOUSE_BASTION, RIDING_SCHOOL, NORTH_WALLS = 1128350262, 37409846, 369605108, 5131386
LEOPOLD_PASSAGE = 37409845
LUGINSLAND_C, LUGINSLAND_R = None, 9.5
UP = None


def _bind(H):
    g = globals()
    for n in NAMES:
        g[n] = H[n]
    g['UP'] = H['Vector']((0, 0, 1))
    g['LUGINSLAND_C'] = H['Vector']((148.0, 133.0))


# ---------------------------------------------------------------- geometry helpers
def obb(pts):
    """Minimum-area oriented rectangle: centre, unit long axis u, perpendicular v (CCW), half sizes."""
    best = None
    P = [Vector(p[:2]) for p in pts]
    for i in range(len(P)):
        e = P[(i + 1) % len(P)] - P[i]
        if e.length < 0.3:
            continue
        u = e.normalized()
        v = Vector((-u.y, u.x))
        us = [p.dot(u) for p in P]
        vs = [p.dot(v) for p in P]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            best = (area, u, v, min(us), max(us), min(vs), max(vs))
    _, u, v, u0, u1, v0, v1 = best
    if (u1 - u0) < (v1 - v0):
        u, v, u0, u1, v0, v1 = v, -u, v0, v1, -u1, -u0
    c = u * ((u0 + u1) / 2) + v * ((v0 + v1) / 2)
    return c, u, v, (u1 - u0) / 2, (v1 - v0) / 2


def rect(c, u, v, hu, hv):
    return [c - u * hu - v * hv, c + u * hu - v * hv, c + u * hu + v * hv, c - u * hu + v * hv]


def v3(p, z):
    return Vector((p.x, p.y, z))


def quad(mb, pts, mat, want=None):
    if want is not None:
        oriented_poly(mb, pts, want, mat)
    else:
        mb.poly(pts, mat)


def ccw(pts):
    P = [Vector(p[:2]) for p in pts]
    if (P[0] - P[-1]).length < 1e-3:
        P = P[:-1]
    if poly_area([(p.x, p.y) for p in P]) < 0:
        P.reverse()
    return P


def prism8(mb, b0, b1, b2, b3, z0, t0, t1, t2, t3, z1, mat, z0b=None, z1b=None):
    """Closed prism: bottom quad (b*) at z0, top quad (t*) at z1 (battered walls).  Points 0/3 sit at the
    start of a wall piece, 1/2 at its end; z1b = top height at the end (sloped tops), or a (start, end)
    pair overriding z1; z0b likewise for the bottom."""
    def ends(z, zb):
        if zb is None:
            return z, z
        return zb if isinstance(zb, tuple) else (z, zb)
    za0, zb0 = ends(z0, z0b)
    za1, zb1 = ends(z1, z1b)
    B = [v3(b0, za0), v3(b1, zb0), v3(b2, zb0), v3(b3, za0)]
    Tt = [v3(t0, za1), v3(t1, zb1), v3(t2, zb1), v3(t3, za1)]
    c = sum(B + Tt, Vector((0, 0, 0))) / 8
    for f in [Tt, list(reversed(B))] + [[B[k], B[(k + 1) % 4], Tt[(k + 1) % 4], Tt[k]] for k in range(4)]:
        oriented_poly(mb, f, sum(f, Vector((0, 0, 0))) / 4 - c, mat)


def vault(mb, a, b, n, w, za, rise, mat, zb=None, seg=12):
    """Barrel vault over a passage a->b (springing za at a, zb at b); n = unit across, w = span."""
    zb = za if zb is None else zb
    for k in range(seg):
        t0, t1 = math.pi * k / seg, math.pi * (k + 1) / seg
        o0, o1 = -math.cos(t0) * w / 2, -math.cos(t1) * w / 2
        h0, h1 = rise * math.sin(t0), rise * math.sin(t1)
        q = [v3(a + n * o0, za + h0), v3(a + n * o1, za + h1), v3(b + n * o1, zb + h1), v3(b + n * o0, zb + h0)]
        f = sum(q, Vector((0, 0, 0))) / 4
        oriented_poly(mb, q, v3((a + b) / 2, (za + zb) / 2) - f, mat)


def floor_strip(mb, T, a, b, n, w, za, zb, mat='cobbles', step=0.8, bulge=True, lift=0.03):
    """Passage floor a->b: linear ramp za->zb raised wherever the terrain bulges above it (collision)."""
    L = (b - a).length
    k = max(2, int(L / step))
    zs = []
    for i in range(k + 1):
        p = a.lerp(b, i / k)
        zl = za + (zb - za) * i / k
        zs.append(max(zl, max(T.h(*(p + n * o)) for o in (-w / 2, 0.0, w / 2)) + lift) if bulge else zl)
    for i in range(k):
        p0, p1 = a.lerp(b, i / k), a.lerp(b, (i + 1) / k)
        oriented_poly(mb, [v3(p0 - n * w / 2, zs[i]), v3(p1 - n * w / 2, zs[i + 1]), v3(p1 + n * w / 2, zs[i + 1]),
                           v3(p0 + n * w / 2, zs[i])], UP, mat)
    return zs


def arch_ring(mb, m, n, want, zs, r0, r1, mat, seg=10, key=None):
    """Flat archivolt ring in the plane spanned by n (horizontal) and z, centred at m / springing zs."""
    for j in range(seg):
        t0, t1 = math.pi * j / seg, math.pi * (j + 1) / seg
        rr = r1 + (key if key and j == seg // 2 else 0.0)
        quad(mb, [v3(m - n * (r0 * math.cos(t0)), zs + r0 * math.sin(t0)), v3(m - n * (r0 * math.cos(t1)), zs + r0 * math.sin(t1)),
                  v3(m - n * (rr * math.cos(t1)), zs + rr * math.sin(t1)), v3(m - n * (rr * math.cos(t0)), zs + rr * math.sin(t0))],
             mat, want=want)


def arched_niche(mb, p, d, out, z, w, h, mat, seg=6):
    """Flat round-headed opening (embrasure / slit) drawn just proud of a wall face."""
    q = p + out * 0.03
    pts = [v3(q - d * (w / 2), z), v3(q + d * (w / 2), z)]
    zs = z + h - w / 2
    for k in range(seg + 1):
        t = math.pi * k / seg
        pts.append(v3(q + d * (w / 2 * math.cos(t)), zs + w / 2 * math.sin(t)))
    oriented_poly(mb, pts, v3(out, 0), mat)


def round_port(mb, p, d, out, z, r, mat, seg=8):
    q = p + out * 0.03
    pts = [v3(q + d * (r * math.cos(2 * math.pi * k / seg)), z + r * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
    oriented_poly(mb, pts, v3(out, 0), mat)


def passage_axis(roads, pts):
    """Dominant direction of OSM ways running through a footprint (gate passage) and a point on them."""
    poly = [tuple(p[:2]) for p in pts]
    acc = Vector((0, 0))
    inside = []
    for f in roads:
        for a, b in zip(f['pts'], f['pts'][1:]):
            A, B = Vector(a[:2]), Vector(b[:2])
            L = (B - A).length
            if L < 0.3:
                continue
            d = (B - A) / L
            hits = [A.lerp(B, (k + 0.5) / 8) for k in range(8) if point_in_poly(*(A.lerp(B, (k + 0.5) / 8)), poly)]
            inside += hits
            n_in = len(hits)
            if n_in:
                if acc.length > 0 and d.dot(acc) < 0:
                    d = -d
                acc += d * L * n_in
    if acc.length == 0:
        return None, None
    return acc.normalized(), sum(inside, Vector((0, 0))) / len(inside)


# ---------------------------------------------------------------- materials
def materials():
    def img_of(m):
        return next(nd.image for nd in MATS[m].node_tree.nodes if nd.type == 'TEX_IMAGE')
    for nm, src, hexc, uv in (('plaster_ochre', 'plaster', '#E2BE72', 3.0), ('plaster_lime', 'plaster', '#F2EEE4', 3.0),
                              ('coping', 'roof', '#D9876A', 1.2), ('ashlar', 'limestone', '#D8C7A6', 1.6),
                              ('rubble_light', 'rubble', '#E6DCC8', 2.0)):
        if nm not in MATS:
            make_mat(nm, img_of(src), uv=uv, rough=0.9)
            tint_mat(nm, hexc)
    if 'rail_orange' not in MATS:
        make_mat('rail_orange', None, color=(0.86, 0.36, 0.06), rough=0.5)
    if 'asphalt' not in MATS:
        make_mat('asphalt', img_of('gravel'), uv=1.5, rough=0.9)
        tint_mat('asphalt', '#8A8E94')
        mx = next(nd for nd in MATS['asphalt'].node_tree.nodes if nd.type == 'MIX')
        mx.inputs['B'].default_value = (0.36, 0.37, 0.39, 1.0)
    if 'paving_band' not in MATS:
        make_mat('paving_band', img_of('cobbles'), uv=0.7, rough=0.85)
        tint_mat('paving_band', '#F4F0E8')
    if 'paving_red' not in MATS:
        make_mat('paving_red', img_of('cobbles'), uv=1.0, rough=0.85)
        tint_mat('paving_red', '#B4503C')
    if 'pale_paving' not in MATS:
        make_mat('pale_paving', img_of('cobbles'), uv=1.0, rough=0.85)
        tint_mat('pale_paving', '#E8E2D6')
    if 'stage_dark' not in MATS:
        make_mat('stage_dark', None, color=(0.07, 0.07, 0.075), rough=0.8)
    if 'roof_dark' not in MATS:
        make_mat('roof_dark', img_of('roof'), uv=3.0, rough=0.85)
        tint_mat('roof_dark', '#8E6A62')
        mix = next(nd for nd in MATS['roof_dark'].node_tree.nodes if nd.type == 'MIX')
        mix.inputs['B'].default_value = (0.5, 0.36, 0.33, 1.0)          # darker grey-red tiles (tint_mat keeps brightness)
    if 'seat_blue' not in MATS:
        make_mat('seat_blue', None, color=(0.08, 0.2, 0.62), rough=0.6)
    if 'fort_void' not in MATS:
        make_mat('fort_void', None, color=(0.025, 0.022, 0.02), rough=1.0)


# ---------------------------------------------------------------- walls
def wall_pieces(pts, step=2.5):
    for a, b in zip(pts, pts[1:]):
        A, B = Vector(a[:2]), Vector(b[:2])
        L = (B - A).length
        if L < 0.2:
            continue
        n = max(1, int(L / step))
        d = (B - A) / L
        for k in range(n):
            yield A.lerp(B, k / n), A.lerp(B, (k + 1) / n), d, Vector((-d.y, d.x))


DESCENT_LINES = []


def on_descent(q, r, d=None):
    """Is q within r of a walk-tested descent (the swept walking corridor, Codex V4 3)?  With a wall direction d,
    only descents crossing it (not running alongside) count."""
    for pl in DESCENT_LINES:
        for a, b in zip(pl, pl[1:]):
            if dist_seg(q, a, b) < r and (d is None or (b - a).length < 1e-6 or abs(d.dot((b - a).normalized())) < 0.85):
                return True
    return False


def fort_wall(mbc, mbd, T, pts, castle, near_steps, garden_off, piece_no, near_way=None):
    """Battered rubble retaining walls / curtain walls: parapet with terracotta coping, round-arched
    embrasures (tall bastion walls) or slit loopholes (curtain), buttresses on tall walls.
    Tops follow the upper ground continuously from piece to piece (no stair-stepped coping)."""
    def side_hi(p, nn):
        return max(T.h(*(p + nn * 3.5)), T.h(*(p - nn * 3.5)))
    PCS = list(wall_pieces(pts))
    gap = []
    for p0, p1, d, nn in PCS:                            # openings where a stair, a way or a descent passes through
        pm = (p0 + p1) / 2
        gap.append(bool(near_steps(pm) or (near_way and near_way(pm, (p0, p1))) or on_descent(pm, 1.4, d)
                        or any(on_descent(q_, 1.6) for q_ in (p0, pm, p1))))   # nothing inside the >=2 m walking corridor
    for k in {0, 1, len(PCS) - 2, len(PCS) - 1}:         # wall ends next to a descent: no tall end face like a pier
        if 0 <= k < len(PCS) and on_descent((PCS[k][0] + PCS[k][1]) / 2, 3.5):
            gap[k] = True
    i = 0
    while i < len(PCS):                                  # no short isolated stub left standing like a pier beside a descent
        j = i
        while j < len(PCS) and not gap[j]:
            j += 1
        if j > i and sum((PCS[k][1] - PCS[k][0]).length for k in range(i, j)) < 4.0 and (j - i < len(PCS)):   # orphan panels
            for k in range(i, j):
                gap[k] = True
        i = j + 1
    for (p0, p1, d, nn), gp in zip(PCS, gap):
        p0, p1 = p0 - d * 0.05, p1 + d * 0.05            # pieces overlap: no cracks at the joints
        pm = (p0 + p1) / 2
        piece_no[0] += 1
        if gp:
            continue
        sa, sb = T.h(*(pm + nn * 3.5)), T.h(*(pm - nn * 3.5))
        lo, hi = min(sa, sb, T.h(p0.x, p0.y), T.h(p1.x, p1.y)), max(sa, sb)
        lf = min([lo] + [T.h(*(q_ + nn * o_)) for q_ in (p0, pm, p1) for o_ in (-2.5, -1.2, 1.2, 2.5)]) - 0.6   # footing below every adjacent vertex
        if garden_off and point_in_poly(pm.x, pm.y, garden_off):
            balustrade(mbc, p0, p1, lo, hi)
            continue
        h0, h1 = side_hi(p0, nn), side_hi(p1, nn)
        # N/W of the palace the curtain carries flat light stone caps (ref 16); S bastions red tiles (ref 26)
        # red tiles only on the S bastions (Earth ref 26); town-side retaining walls grey stone (Fable V4#2)
        cop = 'coping' if -95 < pm.x < 95 and pm.y < -60 else ('limestone' if pm.y > -50 and pm.x > -90 else 'stone')
        out = -nn if sa > sb else nn             # outward = towards the lower side
        th = 1.1 if castle else 0.75
        if hi - lo > 1.5:                        # retaining / bastion wall
            hgt = hi - lo + 1.5
            bat = min(0.12 * hgt, 1.2)           # ~1:8 batter on the outer face
            i0, i1 = p0 - out * (th / 2), p1 - out * (th / 2)
            ob0, ob1 = p0 + out * (th / 2 + bat), p1 + out * (th / 2 + bat)
            ot0, ot1 = p0 + out * (th / 2), p1 + out * (th / 2)
            prism8(mbc, i0, i1, ob1, ob0, min(lo - 1.5, lf), i0, i1, ot1, ot0, h0, 'rubble', z1b=h1)
            q0, q1 = p0 + out * (th / 2 - 0.6), p1 + out * (th / 2 - 0.6)
            prism8(mbc, q0, q1, ot1, ot0, min(h0, h1) - 0.2, q0, q1, ot1, ot0, h0 + 1.0, 'rubble', z1b=h1 + 1.0)
            c0, c1 = q0 - out * 0.06, q1 - out * 0.06
            e0, e1 = ot0 + out * 0.08, ot1 + out * 0.08
            prism8(mbd, c0, c1, e1, e0, 0.0, c0, c1, e1, e0, 0.0, cop, z0b=(h0 + 1.0, h1 + 1.0), z1b=(h0 + 1.13, h1 + 1.13))
            if (piece_no[0] * 7919) % 6 == 0 and hgt > 2.0 and not on_descent(pm, 8.0):   # ivy on some retaining faces, not by the walks
                hd = min(hgt - 0.5, 1.5 + (piece_no[0] % 3))
                for k_ in range(2):
                    s0, s1 = 0.1 + 0.45 * k_, 0.55 + 0.45 * k_
                    A0, A1 = ot0.lerp(ot1, s0) + out * 0.05, ot0.lerp(ot1, s1) + out * 0.05
                    za_, zb_ = h0 + (h1 - h0) * s0 + 0.9, h0 + (h1 - h0) * s1 + 0.9
                    db = out * (bat * hd / max(hgt, 0.1))
                    quad(mbd, [v3(A0 + db, za_ - hd), v3(A1 + db, zb_ - hd * 0.8), v3(A1, zb_), v3(A0, za_)], 'leaves_dense', want=v3(out, 0))
            if castle:
                L = (p1 - p0).length
                nn_ = max(1, int(L / 1.25))
                for j in range(nn_):
                    t = (j + 0.5) / nn_
                    pp = p0.lerp(p1, t) + out * (th / 2)
                    zh = h0 + (h1 - h0) * t
                    if hgt > 4.0:
                        arched_niche(mbd, pp, d, out, zh + 0.25, 0.32, 0.5, 'fort_void')
                    elif j % 2 == 0:
                        arched_niche(mbd, pp, d, out, zh + 0.2, 0.1, 0.55, 'fort_void', seg=2)
            if hgt > 6.0 and piece_no[0] % 4 == 0 and not (near_way and near_way(pm + out * (th / 2 + bat + 0.7))):   # buttress, never on a way
                b0, b1 = pm - d * 0.7, pm + d * 0.7
                prism8(mbc, b0 + out * (th / 2), b1 + out * (th / 2), b1 + out * (th / 2 + bat + 1.4),
                       b0 + out * (th / 2 + bat + 1.4), min(lo - 1.0, lf),
                       b0 + out * (th / 2), b1 + out * (th / 2), b1 + out * (th / 2 + 0.1), b0 + out * (th / 2 + 0.1),
                       min(h0, h1) - 0.6, 'rubble')
        else:
            dz = 2.4 if castle else 1.1
            a0, a1 = p0 - nn * (th / 2), p1 - nn * (th / 2)
            b0, b1 = p0 + nn * (th / 2), p1 + nn * (th / 2)
            prism8(mbc, a0, a1, b1, b0, min(lo - 1.2, lf), a0, a1, b1, b0, h0 + dz, 'rubble', z1b=h1 + dz)
            w = nn * 0.08
            prism8(mbd, a0 - w, a1 - w, b1 + w, b0 + w, 0.0, a0 - w, a1 - w, b1 + w, b0 + w, 0.0, cop,
                   z0b=(h0 + dz, h1 + dz), z1b=(h0 + dz + 0.13, h1 + dz + 0.13))
            if castle and piece_no[0] % 2 == 0:  # slit loopholes, both faces
                for s in (-1, 1):
                    arched_niche(mbd, pm + nn * (s * th / 2), d, nn * s, (h0 + h1) / 2 + dz - 1.3, 0.1, 0.6, 'fort_void', seg=2)


def bartizan(mbc, mbd, c, z, s=1.25, h=3.0, rot=0.0):
    """Square stone sentry box on a bastion angle: rubble walls, slits, pyramid tile roof."""
    u = Vector((math.cos(rot), math.sin(rot)))
    v = Vector((-u.y, u.x))
    R = rect(c, u, v, s, s)
    for k in range(4):
        a, b = R[k], R[(k + 1) % 4]
        L = (b - a).length
        wall(mbc, a, b, z - 0.5, z + h, 0.4, 'rubble', [(L / 2 - 0.06, L / 2 + 0.06, z + 1.2, z + 1.9)], mat_in='rubble')
    slab(mbc, [R], z + 0.05, 0.3, 'stone', 'stone', 'stone')
    oo = rect(c, u, v, s + 0.3, s + 0.3)
    ap = v3(c, z + h + 2.1)
    for k in range(4):
        m = (oo[k] + oo[(k + 1) % 4]) / 2
        quad(mbd, [v3(oo[k], z + h), v3(oo[(k + 1) % 4], z + h), ap], 'roof_tower', want=UP + v3((m - c).normalized(), 0))
    _prism(mbd, ap - Vector((0, 0, 0.05)), ap + Vector((0, 0, 0.7)), 0.025, 0.01, 'metal', seg=4)


def bastion(mbc, mbd, T, pts, top, passage=None, turret_at=None, near_steps=None, gaps=()):
    """Bastion: battered rubble walls round a lawn terrace at `top`, parapet with red tile coping and a
    row of small round-arched embrasures; optional vaulted passage (a, b, width, crown z) cut through."""
    P = ccw(pts)
    for k in range(len(P)):
        a, b = P[k], P[(k + 1) % len(P)]
        L = (b - a).length
        if L < 0.4:
            continue
        d = (b - a) / L
        nin = Vector((-d.y, d.x))
        n = max(1, int(L / 1.5))
        for j in range(n):
            p0, p1 = a.lerp(b, j / n), a.lerp(b, (j + 1) / n)
            pm = (p0 + p1) / 2
            lo = min(T.h(*(pm - nin * 3)), top)
            hgt = top - lo
            in_gap = any(dist_seg(pm, ga, gb) < gw for ga, gb, gw in gaps)
            if (hgt < 1.2 and not in_gap) or (near_steps and near_steps(pm)):
                continue                         # terrace flush with the outside ground / stair head: open
            bat = min(0.1 * hgt, 1.0)
            z0 = lo - 1.5
            if passage and dist_seg(pm, passage[0], passage[1]) < passage[2] / 2 + 0.2:
                z0 = passage[3]
            prism8(mbc, p0 - nin * bat, p1 - nin * bat, p1 + nin * 1.4, p0 + nin * 1.4, z0,
                   p0, p1, p1 + nin * 1.4, p0 + nin * 1.4, top, 'rubble')
            if in_gap:
                continue                         # no parapet where two terraces meet flush
            prism8(mbc, p0, p1, p1 + nin * 0.6, p0 + nin * 0.6, top, p0, p1, p1 + nin * 0.6, p0 + nin * 0.6, top + 1.0, 'rubble')
            prism8(mbd, p0 - nin * 0.08, p1 - nin * 0.08, p1 + nin * 0.68, p0 + nin * 0.68, top + 1.0,
                   p0 - nin * 0.08, p1 - nin * 0.08, p1 + nin * 0.68, p0 + nin * 0.68, top + 1.13, 'coping')
            if hgt > 3.0:
                arched_niche(mbd, pm, d, -nin, top + 0.25, 0.32, 0.5, 'fort_void')
            clear = not passage or dist_seg(pm, passage[0], passage[1]) > passage[2] / 2 + 2.6
            if hgt > 6.0 and clear:              # tile drip course 3.2 m below the terrace (ref 26)
                zc = top - 3.2
                bc = bat * 3.2 / hgt
                prism8(mbd, p0 - nin * (bc + 0.25), p1 - nin * (bc + 0.25), p1 - nin * (bc - 0.05), p0 - nin * (bc - 0.05), zc,
                       p0 - nin * (bc - 0.05), p1 - nin * (bc - 0.05), p1 - nin * (bc - 0.05), p0 - nin * (bc - 0.05), zc + 0.18, 'coping')
    slab(mbc, [offset_poly(P, -1.4)], top + 0.02, 0.6, 'grass', 'rubble', 'rubble')
    if turret_at is not None:
        cc = min(P, key=lambda p: (p - turret_at).length)
        inw = (sum(P, Vector((0, 0))) / len(P) - cc).normalized()
        bartizan(mbc, mbd, cc + inw * 1.0, top + 0.3, rot=math.atan2(inw.y, inw.x) + math.pi / 4)


# ---------------------------------------------------------------- gates
def vienna_gate(mbc, mbd, T, pts, axis, coll):
    axis = axis[0]
    """Vienna Gate: ochre gatehouse, grey stone pilasters, round carriage arch, 2 side doors,
    low pediment over the arch, attic with urns, attached octagonal turret with copper bell dome."""
    c, u, v, hu, hv = obb(pts)
    if axis is not None and abs(axis.dot(u)) > abs(axis.dot(v)):
        u, v, hu, hv = v, -u, hv, hu                     # passage runs along v (through the long faces)
    R = rect(c, u, v, hu, hv)
    g = min(T.h(p.x, p.y) for p in R)
    top = g + 5.6
    aw, ah = 3.2, 4.5
    inner_side = 1 if v.dot(-c) > 0 else -1             # palace side
    for k in range(4):
        a, b = R[k], R[(k + 1) % 4]
        L = (b - a).length
        d = (b - a) / L
        nin = Vector((-d.y, d.x))
        long_face = k in (0, 2)
        ops = []
        if long_face:
            ops.append((L / 2 - aw / 2, L / 2 + aw / 2, g - 0.5, g + ah))
            for s in (-1, 1):
                ops.append((L / 2 + s * 3.6 - 0.65, L / 2 + s * 3.6 + 0.65, g - 0.5, g + 2.6))
        wall(mbc, a, b, g - 1.5, top, 0.7, 'plaster_ochre', ops, mat_in='plaster_ochre')
        seg_box(mbd, a, b, -0.08, 0.02, g - 0.3, g + 0.55, 'stone')           # stone plinth
        if long_face:
            o = ops[0]
            arch_head(mbc, a + d * o[0], a + d * o[1], o[3], 0.0, 0.7, 'plaster_ochre')
            zs = o[3] - aw / 2
            arch_ring(mbd, a + d * (L / 2) - nin * 0.04, d, v3(-nin, 0), zs, aw / 2, aw / 2 + 0.38, 'stone', key=0.2)
            for s in (-1, 1):                         # arch jambs
                e = o[0] if s < 0 else o[1]
                p0 = a + d * (e - (0.4 if s < 0 else 0))
                seg_box(mbd, p0, p0 + d * 0.4, -0.1, 0.02, g, zs, 'stone')
            for o2 in ops[1:]:                        # side doors: stone frames + iron grilles
                seg_box(mbd, a + d * (o2[0] - 0.22), a + d * o2[0], -0.1, 0.02, g, o2[3] + 0.22, 'stone')
                seg_box(mbd, a + d * o2[1], a + d * (o2[1] + 0.22), -0.1, 0.02, g, o2[3] + 0.22, 'stone')
                seg_box(mbd, a + d * o2[0], a + d * o2[1], -0.1, 0.02, o2[3], o2[3] + 0.22, 'stone')
                for jj in range(7):
                    q = a + d * (o2[0] + (o2[1] - o2[0]) * (jj + 0.5) / 7)
                    seg_box(mbd, q - d * 0.012, q + d * 0.012, 0.3, 0.33, g, o2[3], 'metal')
                seg_box(mbd, a + d * o2[0], a + d * o2[1], 0.3, 0.33, g + 2.3, g + 2.36, 'metal')
                seg_box(mbd, a + d * o2[0], a + d * o2[1], 0.3, 0.33, g + 0.15, g + 0.21, 'metal')
            for off in (0.15, L / 2 - aw / 2 - 1.05, L / 2 + aw / 2 + 0.45, L - 0.75):   # pilasters
                seg_box(mbd, a + d * off, a + d * (off + 0.6), -0.16, 0.02, g, top - 0.55, 'stone')
            # low pediment over the arch bay (front + back triangle, raking cornices)
            pa, pb = a + d * (L / 2 - aw / 2 - 1.2), a + d * (L / 2 + aw / 2 + 1.2)
            pm = (pa + pb) / 2
            zb, zp = top - 0.1, top + 1.15
            quad(mbd, [v3(pa - nin * 0.2, zb), v3(pb - nin * 0.2, zb), v3(pm - nin * 0.2, zp)], 'plaster_ochre', want=v3(-nin, 0))
            quad(mbd, [v3(pa + nin * 0.5, zb), v3(pb + nin * 0.5, zb), v3(pm + nin * 0.5, zp)], 'plaster_ochre', want=v3(nin, 0))
            for e0 in (pa, pb):
                q0, q1 = v3(e0 - nin * 0.32, zb), v3(pm - nin * 0.32, zp)
                q2, q3 = v3(pm + nin * 0.55, zp), v3(e0 + nin * 0.55, zb)
                lift = Vector((0, 0, 0.2))
                quad(mbd, [q0, q1, q1 + lift, q0 + lift], 'stone', want=v3(-nin, 0))
                quad(mbd, [q0 + lift, q1 + lift, q2 + lift, q3 + lift], 'stone', want=UP)
        else:
            for off in (0.15, L - 0.75):
                seg_box(mbd, a + d * off, a + d * (off + 0.6), -0.16, 0.02, g, top - 0.55, 'stone')
        sweep(mbd, a, b, [(0.0, 0.0), (0.15, 0.05), (0.25, 0.2), (0.4, 0.3), (0.4, 0.45), (0.0, 0.45)], top - 0.55, 'stone', -nin)
    # passage: walls, vault, paving
    pa, pb = c - v * hv, c + v * hv
    for s in (-1, 1):
        wall(mbc, pa + u * (s * aw / 2), pb + u * (s * aw / 2), g - 0.5, g + ah - aw / 2 + 0.05, 0.25, 'plaster_ochre',
             off=(0.0 if s < 0 else -0.25))
    vault(mbd, pa, pb, u, aw, g + ah - aw / 2, aw / 2, 'plaster_ochre')
    GATE_PASSAGES.append((c, g + ah - 0.05, pa, pb, aw, g + 0.03, g + 0.03))
    oriented_poly(mbc, [v3(p, g + 0.03) for p in rect(c, u, v, aw / 2, hv + 0.3)], UP, 'cobbles')
    # flat roof + attic with urns
    slab(mbc, [R], top, 0.5, 'gravel', 'plaster_ochre', 'plaster_ochre')
    for k in range(4):
        a, b = R[k], R[(k + 1) % 4]
        L = (b - a).length
        d = (b - a) / L
        seg_box(mbd, a, b, 0.0, 0.4, top, top + 0.75, 'plaster_ochre')
        seg_box(mbd, a, b, -0.05, 0.45, top + 0.75, top + 0.88, 'stone')
        nu = max(2, int(L / 3.2))
        for j in range(nu + 1):
            q = a + d * (L * j / nu) + Vector((-d.y, d.x)) * 0.2
            lathe_up(mbd, q, top + 0.88, [(0.0, 0.0), (0.16, 0.0), (0.16, 0.08), (0.07, 0.16), (0.2, 0.38), (0.15, 0.55),
                                          (0.06, 0.6), (0.1, 0.66), (0.03, 0.8), (0.0, 0.82)], 'stone', seg=10)
    # attached octagonal turret on the palace side at one end
    tc = c + u * (hu - 1.3) + v * (inner_side * (hv + 1.0))
    r = 1.75
    o8 = [tc + Vector((math.cos(math.pi / 8 + k * math.pi / 4), math.sin(math.pi / 8 + k * math.pi / 4))) * r for k in range(8)]
    tt = top + 3.8
    for k in range(8):
        a, b = o8[k], o8[(k + 1) % 8]                    # CCW: wall thickness goes inward (left)
        L = (b - a).length
        d = (b - a) / L
        ops = [(L / 2 - 0.2, L / 2 + 0.2, top + 1.6, top + 2.6)] if k % 2 else []
        wall(mbc, a, b, g - 1.0, tt, 0.4, 'plaster_lime', ops, mat_in='plaster_int')     # white turret (Earth gs_vienna_gate)
        for o in ops:
            window_simple(mbd, a + d * o[0], a + d * o[1], o[2], o[3], Vector((-d.y, d.x)), 0.2)
    for k in range(8):                                   # stone corner lesenes
        p = o8[k]
        out = (p - tc).normalized()
        side = Vector((-out.y, out.x))
        seg_box(mbd, p - side * 0.18, p + side * 0.18, -0.1, 0.04, g, tt - 0.4, 'stone')
    lathe_up(mbd, tc, tt - 0.45, [(0.0, 0.0), (r + 0.05, 0.0), (r + 0.3, 0.2), (r + 0.4, 0.42), (0.0, 0.45)], 'stone', seg=16)
    lathe_up(mbd, tc, tt, [(0.0, 0.0), (r + 0.35, 0.0), (r + 0.1, 0.25), (r - 0.05, 0.55), (r - 0.2, 0.95), (r - 0.55, 1.35),
                           (0.7, 1.6), (0.35, 1.72), (0.3, 1.82), (0.0, 1.84)], 'copper', seg=16)
    lathe_up(mbd, tc, tt + 1.84, [(0.0, 0.0), (0.12, 0.0), (0.18, 0.15), (0.1, 0.3), (0.05, 0.32), (0.04, 1.2), (0.09, 1.3),
                                  (0.04, 1.4), (0.015, 2.0), (0.0, 2.05)], 'copper', seg=8)
    slab(mbc, [o8], tt, 0.3, 'plaster_int', 'plaster_int', 'plaster_int')
    for s in (-1, 1):                                    # gate lanterns on the city side
        lp = c - v * (inner_side * (hv + 0.45)) + u * (s * (aw / 2 + 0.75))
        lantern(mbd, lp, g + 3.9, g + 3.2, r=0.13)
        add_light(coll, 'L_street_gate', (lp.x, lp.y, g + 3.4), 60, color=(1.0, 0.8, 0.55))


def ogee_gable(mbd, m, d, out, zb, W, H, mat):
    """Gothic ogee (keel) arch moulding over a portal, with crockets, a fleuron and side pinnacles."""
    def hw(s):                                           # half width vs. normalised height (S-curve)
        return W / 2 * (1 - (3 * s * s - 2 * s * s * s))
    n = 12
    for side in (-1, 1):
        for k in range(n):
            s0, s1 = k / n, (k + 1) / n
            p0, p1 = m + d * (side * hw(s0)), m + d * (side * hw(s1))
            q0, q1 = m + d * (side * max(hw(s0) - 0.22, 0)), m + d * (side * max(hw(s1) - 0.22, 0))
            z0, z1 = zb + H * s0, zb + H * s1
            quad(mbd, [v3(p0 + out * 0.2, z0), v3(p1 + out * 0.2, z1), v3(q1 + out * 0.2, z1 + 0.12), v3(q0 + out * 0.2, z0 + 0.12)],
                 mat, want=v3(out, 0))
            quad(mbd, [v3(p0, z0), v3(p1, z1), v3(p1 + out * 0.2, z1), v3(p0 + out * 0.2, z0)], mat, want=v3(d * side, 0) - UP * 0.2)
            quad(mbd, [v3(q0, z0 + 0.12), v3(q1, z1 + 0.12), v3(q1 + out * 0.2, z1 + 0.12), v3(q0 + out * 0.2, z0 + 0.12)], mat,
                 want=UP - v3(d * side, 0) * 0.3)
            if k % 3 == 1:                               # crockets
                sph_mb_ring(mbd, m + d * (side * hw(s1)) + out * 0.25, z1 - 0.05, 0.09, mat, seg=6)
        pin = m + d * (side * (W / 2 + 0.35))            # pinnacle shafts
        seg_box(mbd, pin - d * 0.14, pin + d * 0.14, -0.3, 0.0, zb - 2.2, zb + H * 0.85, mat)
        _prism(mbd, v3(pin + out * 0.15, zb + H * 0.85), v3(pin + out * 0.15, zb + H * 0.85 + 0.6), 0.16, 0.02, mat, seg=4)
    _prism(mbd, v3(m + out * 0.15, zb + H), v3(m + out * 0.15, zb + H + 0.9), 0.06, 0.04, mat, seg=4)
    for k in range(4):                                   # fleuron
        a = k * math.pi / 2
        _prism(mbd, v3(m + out * 0.15, zb + H + 0.5), v3(m + out * 0.15 + Vector((math.cos(a), math.sin(a))) * 0.18, zb + H + 0.65),
               0.04, 0.02, mat, seg=4)


def sigismund_gate(mbc, mbd, T, pts, axis):
    """Square ashlar gate tower, 3 storeys, steep pyramid roof; segmental portal under an ogee gable on the
    lower (outer) face; vaulted ramp passage following the slope."""
    axis = axis[0]
    c, u, v, hu, hv = obb(pts)
    if axis is None:
        axis = u
    across = Vector((-axis.y, axis.x))
    ha = max(abs(axis.dot(u)) * hu + abs(axis.dot(v)) * hv, 3.0)
    hx = max(abs(across.dot(u)) * hu + abs(across.dot(v)) * hv, 3.0)
    R = rect(c, axis, across, ha, hx)
    za = T.h(*(c - axis * (ha + 0.6)))
    zb = T.h(*(c + axis * (ha + 0.6)))
    g = min(za, zb)
    top = g + 14.5
    aw, ah = 3.4, 4.3
    for k in range(4):
        a, b = R[k], R[(k + 1) % 4]
        L = (b - a).length
        d = (b - a) / L
        nin = Vector((-d.y, d.x))
        end_face = abs(nin.dot(axis)) > 0.7
        zf = za if nin.dot(axis) > 0 else zb
        ops = [(L / 2 - aw / 2, L / 2 + aw / 2, zf - 1.0, zf + ah)] if end_face else []
        for zz in (g + 7.6, g + 11.0):                   # small square windows
            for t in ((0.36, 0.64) if end_face else (0.5,)):
                ops.append((L * t - 0.25, L * t + 0.25, zz, zz + 0.5))
        wall(mbc, a, b, g - 3.0, top, 1.3, 'ashlar', ops, mat_in='plaster_int')
        for o in ops:
            if o[1] - o[0] > 2:
                arch_head(mbc, a + d * o[0], a + d * o[1], o[3], 0.0, 1.3, 'ashlar')
                seg_box(mbd, a + d * (o[0] - 0.3), a + d * o[0], -0.12, 0.02, zf, o[3] - 0.9, 'limestone')
                seg_box(mbd, a + d * o[1], a + d * (o[1] + 0.3), -0.12, 0.02, zf, o[3] - 0.9, 'limestone')
                if zf == min(za, zb):                    # outer face: Gothic ogee gable
                    ogee_gable(mbd, a + d * (L / 2) - nin * 0.02, d, -nin, o[3] + 0.25, aw + 1.4, 3.0, 'limestone')
            else:
                window_simple(mbd, a + d * o[0], a + d * o[1], o[2], o[3], nin, 0.5)
        for zz in (g + 7.0, g + 10.2):                   # string courses
            seg_box(mbd, a, b, -0.14, 0.02, zz, zz + 0.22, 'limestone')
        for zq in range(int(g), int(top)):               # corner quoins
            seg_box(mbd, a, a + d * (0.85 if zq % 2 else 0.5), -0.07, 0.02, zq, zq + 0.95, 'limestone')
        seg_box(mbd, a, b, -0.35, 0.02, top - 0.4, top, 'limestone')
    pa, pb = c - axis * (ha + 0.6), c + axis * (ha + 0.6)
    for s in (-1, 1):
        wall(mbc, pa + across * (s * aw / 2), pb + across * (s * aw / 2), g - 1.0, max(za, zb) + ah - 1.55, 0.35,
             'ashlar', off=(0.0 if s > 0 else -0.35))
    zs = floor_strip(mbc, T, pa, pb, across, aw, za, zb, bulge=False)
    for s in (-1, 1):                                    # low stone plinth along both walls: covers the terrain grid edges
        i0, i1 = pa + across * (s * (aw / 2 - 0.3)), pb + across * (s * (aw / 2 - 0.3))
        o0, o1 = pa + across * (s * aw / 2), pb + across * (s * aw / 2)
        prism8(mbc, i0, i1, o1, o0, min(za, zb) - 1.5, i0, i1, o1, o0, za + 0.35, 'ashlar', z1b=zb + 0.35)
    for p_out, p_in, z_in in ((c - axis * (ha + 2.2), pa, zs[0]), (c + axis * (ha + 2.2), pb, zs[-1])):   # aprons into the terrain
        floor_strip(mbc, T, p_out, p_in, across, aw, T.h(*p_out) - 0.3, z_in, step=0.5, bulge=False)
    vault(mbd, pa, pb, across, aw, za + ah - 1.6, 1.6, 'plaster_lime', zb=zb + ah - 1.6)
    GATE_PASSAGES.append((c, (za + zb) / 2 + ah - 0.05, pa, pb, aw, za, zb))
    slab(mbc, [R], max(za, zb) + ah + 1.2, 0.5, 'parquet', 'plaster_lime', 'plaster_lime')
    oo = rect(c, axis, across, ha + 0.55, hx + 0.55)
    rh = 1.25 * min(ha, hx) + 1.0
    ap = v3(c, top + rh)
    for k in range(4):
        m = (oo[k] + oo[(k + 1) % 4]) / 2
        quad(mbd, [v3(oo[k], top - 0.05), v3(oo[(k + 1) % 4], top - 0.05), ap], 'roof', want=UP + v3((m - c).normalized(), 0))
    slab(mbc, [R], top, 0.3, 'plaster_int', 'plaster_int', 'plaster_int')
    _prism(mbd, ap - Vector((0, 0, 0.1)), ap + Vector((0, 0, 1.2)), 0.03, 0.01, 'metal', seg=4)


def nicholas_gate(mbc, mbd, T, pts, axis, ramp):
    """Plain brick arch through a rubble wall block; the OSM steps provide the passage floor."""
    axis, on = axis
    c0, u, v, hu, hv = obb(pts)
    if axis is None:
        axis, on = u, c0
    across = Vector((-axis.y, axis.x))
    ha = abs(axis.dot(u)) * hu + abs(axis.dot(v)) * hv
    hx0 = abs(across.dot(u)) * hu + abs(across.dot(v)) * hv
    sh = (on - c0).dot(across)                           # passage follows the stair, off the block centre
    c = c0 + across * sh
    za, zb = T.h(*(c - axis * ha)), T.h(*(c + axis * ha))
    aw, ah = 2.8, 4.3
    # the hires DMR climbs ~3 m inside 4 m at the west mouth (the real passage is a stair): a smooth
    # walk ramp (collision only) limited to 0.45 rise per metre, eased out onto the ground on both sides
    ds, ext = 0.4, ha + 2.5
    prof = []
    for i in range(int(2 * ext / ds) + 1):
        q = c - axis * ext + axis * (i * ds)
        g_ = min(T.h(q.x + ox, q.y + oy) for ox in (-1.0, 0.0, 1.0) for oy in (-1.0, 0.0, 1.0)) - 0.02
        inside_p = abs((q - c).dot(axis)) <= ha + 0.5
        prof.append([q, max(T.h(*(q + across * o)) for o in (-aw / 2, 0.0, aw / 2)) + 0.3 if inside_p else g_])
    for _ in range(2):
        for i in range(1, len(prof)):
            prof[i][1] = max(prof[i][1], prof[i - 1][1] - 0.45 * ds)
        for i in range(len(prof) - 2, -1, -1):
            prof[i][1] = max(prof[i][1], prof[i + 1][1] - 0.45 * ds)
    # (the walk strip itself now comes from descent_ramps along the Nicholas descent; prof only lifts the arches)
    # arches / vault clear the walk ramp at both mouths
    za = max(za, min(prof, key=lambda pz: abs((pz[0] - c).dot(axis) + ha))[1])
    zb = max(zb, min(prof, key=lambda pz: abs((pz[0] - c).dot(axis) - ha))[1])
    top = max(za, zb) + 5.3
    for s in (-1, 1):                                    # the two masonry halves
        hx = hx0 - s * sh
        P = [c - axis * ha + across * (s * aw / 2), c + axis * ha + across * (s * aw / 2),
             c + axis * ha + across * (s * hx), c - axis * ha + across * (s * hx)]
        prism8(mbc, P[0], P[1], P[2], P[3], min(za, zb) - 2.0, P[0], P[1], P[2], P[3], top, 'rubble')
    P = [c - axis * ha - across * aw / 2, c + axis * ha - across * aw / 2, c + axis * ha + across * aw / 2, c - axis * ha + across * aw / 2]
    prism8(mbc, P[0], P[1], P[2], P[3], max(za, zb) + ah, P[0], P[1], P[2], P[3], top, 'rubble')
    for end, zz, sgn in ((c - axis * ha, za, -1), (c + axis * ha, zb, 1)):
        zs = zz + ah - aw / 2
        arch_ring(mbd, end + axis * (sgn * 0.03), across, v3(axis * sgn, 0), zs, aw / 2, aw / 2 + 0.45, 'brick', seg=11)
        e0, e1 = (end + across * aw / 2, end - across * aw / 2) if sgn < 0 else (end - across * aw / 2, end + across * aw / 2)
        arch_head(mbc, e0, e1, zz + ah, 0.0, 0.5, 'rubble')
        if zz < max(za, zb) - 0.05:                      # lower end: masonry up to the crown mass
            quad(mbc, [v3(end - across * aw / 2, zz + ah), v3(end + across * aw / 2, zz + ah),
                       v3(end + across * aw / 2, max(za, zb) + ah), v3(end - across * aw / 2, max(za, zb) + ah)],
                 'rubble', want=v3(axis * sgn, 0))
    vault(mbd, c - axis * ha, c + axis * ha, across, aw, za + ah - aw / 2, aw / 2, 'brick', zb=zb + ah - aw / 2)
    GATE_PASSAGES.append((c, (za + zb) / 2 + ah - 0.05, c - axis * ha, c + axis * ha, aw, za, zb))
    # floor clears the paving meshes draped on the terrain (up to ~0.25 m above T.h); 3 m aprons run into them
    zs = floor_strip(mbd, T, c - axis * (ha + 0.5), c + axis * (ha + 0.5), across, aw - 0.1, za, zb, mat='stone', lift=0.05, step=0.4)   # visual; walk = descent strip
    for p_out, p_in, z_in in ((c - axis * (ha + 3.5), c - axis * (ha + 0.5), zs[0]), (c + axis * (ha + 3.5), c + axis * (ha + 0.5), zs[-1])):
        z_out = min(T.h(p_out.x + ox, p_out.y + oy) for ox in (-1.0, 0.0, 1.0) for oy in (-1.0, 0.0, 1.0)) - 0.05   # 2 m mesh grid
        floor_strip(mbd, T, p_out, p_in, across, aw - 0.1, z_out, z_in, mat='stone', step=0.5, bulge=False)   # visual: the descent strip carries the walk
    RR = rect(c0, axis, across, ha, hx0)
    for k in range(4):
        a, b = RR[k], RR[(k + 1) % 4]
        nin = Vector((-(b - a).normalized().y, (b - a).normalized().x))
        prism8(mbd, a - nin * 0.08, b - nin * 0.08, b + nin * 0.7, a + nin * 0.7, top,
               a - nin * 0.08, b - nin * 0.08, b + nin * 0.7, a + nin * 0.7, top + 0.13, 'coping')
    slab(mbc, [RR], top + 0.01, 0.2, 'grass', 'rubble', 'rubble')


def leopold_gate(mbc, mbd, T, a, b, coll):
    """Leopold Gate: vaulted passage a->b under the bastion terrace, Baroque stone portal at a:
    rusticated pilasters, entablature with the imperial arms and three stone balls."""
    d = (b - a).normalized()
    n = Vector((-d.y, d.x))
    za, zb = T.h(*(a - d * 2.0)), T.h(*(b + d * 2.0))
    aw, ah = 3.2, 4.8
    crown = max(za, zb) + ah
    for s in (-1, 1):                                    # tunnel side walls up to the terrace
        wall(mbc, a + n * (s * aw / 2), b + n * (s * aw / 2), min(za, zb) - 1.0, crown + 1.0, 1.0, 'rubble',
             off=(0.0 if s > 0 else -1.0), mat_in='stone')
    fa, fb = a - d * 0.7, b + d * 0.7
    oriented_poly(mbc, [v3(fa - n * aw / 2, za), v3(fa + n * aw / 2, za), v3(fb + n * aw / 2, zb), v3(fb - n * aw / 2, zb)], UP, 'cobbles')
    vault(mbd, a - d * 0.6, b + d * 0.6, n, aw, za + ah - aw / 2, aw / 2, 'stone', zb=zb + ah - aw / 2)
    GATE_PASSAGES.append(((a + b) / 2, (za + zb) / 2 + ah - 0.05, a, b, aw, za, zb))
    for p, z in ((a, za), (b, zb)):                      # arch spandrels + infill up to the crown in the bastion face
        arch_head(mbc, p - n * aw / 2 + d * 0.6, p + n * aw / 2 + d * 0.6, z + ah, 0.0, 1.2, 'rubble')
        if z + ah < crown + 0.55:
            seg_box(mbc, p - d * 0.6, p + d * 0.6, -aw / 2, aw / 2, z + ah, crown + 0.6, 'rubble')
    # east exit: plain limestone arch frame (ref 26)
    zs = zb + ah - aw / 2
    arch_ring(mbd, b + d * 0.62, n, v3(d, 0), zs, aw / 2, aw / 2 + 0.35, 'limestone')
    for s in (-1, 1):
        q = b + d * 0.62 + n * (s * (aw / 2 + 0.17))
        seg_box(mbd, q - n * 0.17, q + n * 0.17, -0.05, 0.05, zb, zs, 'limestone')
    # west portal
    pf = a - d * 0.62                                    # outer face of the bastion wall
    out = -d
    pz = za
    for s in (-1, 1):                                    # paired rusticated pilasters
        for off in (aw / 2 + 0.5, aw / 2 + 1.25):
            base = pf + n * (s * off)
            for j in range(8):
                dep = 0.36 if j % 2 == 0 else 0.3
                w2 = 0.62 if j % 2 == 0 else 0.5
                p0, p1 = base - n * (w2 / 2), base + n * (w2 / 2)
                prism8(mbd, p0, p1, p1 + out * dep, p0 + out * dep, pz + j * 0.62,
                       p0, p1, p1 + out * dep, p0 + out * dep, pz + j * 0.62 + 0.58, 'limestone')
    zs = pz + ah - aw / 2
    arch_ring(mbd, pf + out * 0.06, n, v3(out, 0), zs, aw / 2, aw / 2 + 0.42, 'limestone', seg=11, key=0.25)
    ze = pz + 5.0
    ea, eb = pf - n * (aw / 2 + 1.75), pf + n * (aw / 2 + 1.75)
    sweep(mbd, ea, eb, [(0.0, 0.0), (0.4, 0.0), (0.42, 0.3), (0.48, 0.36), (0.52, 0.6), (0.66, 0.7), (0.66, 0.9), (0.0, 0.9)], ze, 'limestone', out)
    # attic panel with the imperial arms and 3 stone balls
    seg_box(mbd, pf - n * 1.3, pf + n * 1.3, 0.0, -0.3, ze + 0.9, ze + 2.1, 'limestone')
    cart = pf + out * 0.42
    yaw = math.atan2(out.y, out.x)
    ellipsoid(mbd, v3(cart, ze + 1.5), 0.1, 0.55, 0.62, yaw, 0.0, 'limestone', subdiv=2)
    ellipsoid(mbd, v3(cart + out * 0.06, ze + 1.55), 0.06, 0.3, 0.36, yaw, 0.0, 'stone', subdiv=1)
    for s in (-1, 1):
        ellipsoid(mbd, v3(cart + n * (s * 0.62), ze + 1.6), 0.08, 0.32, 0.18, yaw, 0.0, 'limestone', subdiv=1)
    lathe_up(mbd, cart - out * 0.1, ze + 2.1, [(0.0, 0.0), (0.3, 0.0), (0.32, 0.14), (0.2, 0.24), (0.09, 0.34), (0.0, 0.37)], 'limestone', seg=10)
    for off in (-(aw / 2 + 0.9), 0.0, aw / 2 + 0.9):
        q = pf + out * 0.3 + n * off
        zq = ze + 0.9 if off else ze + 2.45
        lathe_up(mbd, q, zq, [(0.0, 0.0), (0.22, 0.0), (0.22, 0.12), (0.1, 0.18)], 'limestone', seg=10)
        sph_mb_ring(mbd, q, zq + 0.18, 0.28, 'limestone', seg=10)
    for s in (-1, 1):                                    # gate leaves folded back
        hinge = a + d * 0.5 + n * (s * (aw / 2 - 0.08))
        seg_box(mbd, hinge, hinge + d * 1.9, -0.06, 0.06, za, za + ah - 0.7, 'door')
    lp = pf + out * 0.5 + n * (aw / 2 + 2.4)
    add_light(coll, 'L_street_gate', (lp.x, lp.y, za + 4.2), 50, color=(1.0, 0.8, 0.55))
    return crown + 0.6


# ---------------------------------------------------------------- buildings
STABLES = 5131387


def stables_row(mbc, mbd, T, pts):
    """Long single-storey white range split into bays, each with its own transverse gable roof (red tiles):
    the sawtooth skyline of the castle stables (Earth ph_zamocka_mid).  Bays step with the ground: no
    floating or buried façades on the slope."""
    c, u, v, hu, hv = obb(pts)
    if hv > hu:
        u, v, hu, hv = v, u, hv, hu
    hv = min(hv, 6.0)
    n = max(3, int(round(2 * hu / 7.5)))
    bays = [(-hu + 2 * hu * k / n, -hu + 2 * hu * (k + 1) / n) for k in range(n)]
    for _ in range(2):                                   # a bay over a steep fall steps down in two floor levels
        nb = []
        for s0, s1 in bays:
            spread = [T.h(*(c + u * s_ + v * t_)) for s_ in (s0, s1) for t_ in (-hv, hv)]
            if max(spread) - min(spread) > 2.0 and s1 - s0 > 3.5:
                nb += [(s0, (s0 + s1) / 2), ((s0 + s1) / 2, s1)]
            else:
                nb.append((s0, s1))
        bays = nb
    for s0, s1 in bays:
        bl = s1 - s0
        m = c + u * ((s0 + s1) / 2)
        a0, a1 = m - u * (bl / 2), m + u * (bl / 2)
        R = [a0 - v * hv, a1 - v * hv, a1 + v * hv, a0 + v * hv]
        hs = [T.h(*q) for q in R] + [T.h(*m)]
        floor = max(hs) + 0.15
        for e in range(4):                               # lowest ground along the bay walls, just outside them
            q0, q1 = R[e], R[(e + 1) % 4]
            for t in range(9):
                q = q0.lerp(q1, t / 8)
                hs.append(T.h(*(q + (q - m).normalized() * 0.8)))
        eave = floor + 3.4
        mbc.box(R, floor - 0.3, eave, 'plaster_lime')
        mbc.box([q + (q - m).normalized() * 0.06 for q in R], min(hs) - 0.6, floor + 0.45, 'rubble')   # exposed base: rubble plinth
        mbd.box([q + (q - m).normalized() * 0.1 for q in R], floor + 0.45, floor + 0.55, 'limestone')     # plinth cap
        ridge = eave + hv * 0.6                          # ~31 deg: low cross gables (Earth)
        o = 0.35
        E = [a0 - u * 0.02 - v * (hv + o), a1 + u * 0.02 - v * (hv + o), a1 + u * 0.02 + v * (hv + o), a0 - u * 0.02 + v * (hv + o)]
        for s_ in (-1, 1):                               # roof planes fall to the bay ends (ridge across the range)
            e0, e1 = (E[0], E[3]) if s_ < 0 else (E[1], E[2])
            r0, r1 = m - v * (hv + o), m + v * (hv + o)
            quad(mbd, [v3(e0, eave - 0.25), v3(e1, eave - 0.25), v3(r1, ridge), v3(r0, ridge)], 'roof', want=v3(u * s_, 0) + UP)
        for s_ in (-1, 1):                               # gable triangles on both long faces
            g0, g1, gm = m - u * (bl / 2) + v * (s_ * hv), m + u * (bl / 2) + v * (s_ * hv), m + v * (s_ * hv)
            quad(mbc, [v3(g0, eave), v3(g1, eave), v3(gm, ridge - 0.2)], 'plaster_lime', want=v3(v * s_, 0))
            out_ = v * s_                                   # one window per bay and side + a small gable light:
            for hw_w, z0w, z1w in ((0.6, floor + 0.9, floor + 2.4), (0.3, eave + 0.5, eave + 1.2)):   # flat on the wall face
                f0, f1 = gm - u * (hw_w + 0.08) + out_ * 0.02, gm + u * (hw_w + 0.08) + out_ * 0.02
                quad(mbd, [v3(f0, z0w - 0.08), v3(f1, z0w - 0.08), v3(f1, z1w + 0.08), v3(f0, z1w + 0.08)], 'frame', want=v3(out_, 0))
                g0, g1 = gm - u * hw_w + out_ * 0.03, gm + u * hw_w + out_ * 0.03
                quad(mbd, [v3(g0, z0w), v3(g1, z0w), v3(g1, z1w), v3(g0, z1w)], 'glass', want=v3(out_, 0))
                quad(mbd, [v3(gm + out_ * 0.035 - u * 0.02, z0w), v3(gm + out_ * 0.035 + u * 0.02, z0w),
                           v3(gm + out_ * 0.035 + u * 0.02, z1w), v3(gm + out_ * 0.035 - u * 0.02, z1w)], 'frame', want=v3(out_, 0))


def gabled_house(mbc, mbd, T, pts, levels, wall_mat, rubble_base=True, arched=False, dormers=False, roof_h=None,
                 hipped=False, floor_h=3.4, window_w=1.1, spacing=3.1):
    """Rectangular building (OBB of the footprint) with a proper gable or hip roof."""
    c, u, v, hu, hv = obb(pts)
    R = rect(c, u, v, hu, hv)
    gs = [T.h(p.x, p.y) for p in R]
    g, gt = min(gs), max(gs)
    eave = gt + levels * floor_h + 0.6
    for k in range(4):
        a, b = R[k], R[(k + 1) % 4]
        L = (b - a).length
        d = (b - a) / L
        nin = Vector((-d.y, d.x))
        ops = []
        nax = max(1, int(L / spacing))
        sp = L / nax
        short_end = arched and L < 1.2 * hv * 2 + 0.1        # riding school short ends (Earth): entrance + small windows
        rect_ops = []
        if short_end:
            ze = T.h(*((a + b) / 2 - nin * 1.0)) + 0.05                         # entrance at the ground outside
            ops.append((L / 2 - 1.2, L / 2 + 1.2, ze, ze + 3.6))                  # arched entrance
            for j in range(nax):
                uu = sp * (j + 0.5)
                if abs(uu - L / 2) > 2.0:
                    rect_ops.append((uu - 0.55, uu + 0.55, gt + floor_h + 1.0, gt + floor_h + 2.3))
            rect_ops.append((L / 2 - 0.55, L / 2 + 0.55, gt + floor_h + 1.6, gt + floor_h + 2.6))
        for lv in range(0 if short_end else (1 if arched else levels)):
            zz = gt + 0.9 + lv * floor_h
            hh = (floor_h * levels - 1.8) if arched else 1.7
            for j in range(nax):
                uu = sp * (j + 0.5)
                ops.append((uu - window_w / 2, uu + window_w / 2, zz, zz + hh))
        if rubble_base:
            wall(mbc, a, b, g - 2.0, gt + 0.6, 0.7, 'rubble', [], mat_in='rubble')
            wall(mbc, a, b, gt + 0.6, eave, 0.6, wall_mat, ops, mat_in='plaster_int')
        else:
            wall(mbc, a, b, g - 2.0, eave, 0.6, wall_mat, ops + rect_ops, mat_in='plaster_int')
            seg_box(mbd, a, b, -0.06, 0.02, g - 0.3, gt + 0.5, 'stone')
        for o in rect_ops:
            window_simple(mbd, a + d * o[0], a + d * o[1], o[2], o[3], nin, 0.3)
            seg_box(mbd, a + d * (o[0] - 0.12), a + d * (o[1] + 0.12), -0.08, 0.22, o[2] - 0.1, o[2], 'stone')
        for o in ops:
            if short_end and o[1] - o[0] > 2.0:          # entrance: arch + door leaves
                arch_head(mbc, a + d * o[0], a + d * o[1], o[3], 0.0, 0.6, wall_mat)
                seg_box(mbd, a + d * o[0], a + d * o[1], 0.3, 0.38, o[2], o[3] - 1.2, 'door')
                continue
            if arched:
                arch_head(mbc, a + d * o[0], a + d * o[1], o[3], 0.0, 0.6, wall_mat)
                window_simple(mbd, a + d * o[0], a + d * o[1], o[2], o[3] - (o[1] - o[0]) / 2, nin, 0.3)
            else:
                window_simple(mbd, a + d * o[0], a + d * o[1], o[2], o[3], nin, 0.3)
            seg_box(mbd, a + d * (o[0] - 0.15), a + d * (o[1] + 0.15), -0.1, 0.22, o[2] - 0.1, o[2], 'stone')
        sweep(mbd, a, b, [(0.0, 0.0), (0.12, 0.06), (0.22, 0.2), (0.35, 0.3), (0.0, 0.3)], eave - 0.3, 'frame', -nin)
    slab(mbc, [R], eave, 0.3, 'plaster_int', 'plaster_int', 'plaster_int')
    slab(mbc, [rect(c, u, v, hu - 0.3, hv - 0.3)], gt + 0.15, 0.3, 'parquet', 'stone', 'stone')   # ground floor seen through windows
    rh = roof_h if roof_h else min(hv * 0.9, 6.0)
    ov = 0.45
    A0, A1, A2, A3 = rect(c, u, v, hu + ov, hv + ov)
    inset = (hv + ov) if hipped else 0.0
    r0, r1 = c - u * (hu + ov - inset), c + u * (hu + ov - inset)
    z_e, z_r = eave - 0.15, eave + rh
    quad(mbd, [v3(A0, z_e), v3(A1, z_e), v3(r1, z_r), v3(r0, z_r)], 'roof', want=UP - v3(v, 0))
    quad(mbd, [v3(A2, z_e), v3(A3, z_e), v3(r0, z_r), v3(r1, z_r)], 'roof', want=UP + v3(v, 0))
    if hipped:
        quad(mbd, [v3(A1, z_e), v3(A2, z_e), v3(r1, z_r)], 'roof', want=UP + v3(u, 0))
        quad(mbd, [v3(A3, z_e), v3(A0, z_e), v3(r0, z_r)], 'roof', want=UP - v3(u, 0))
    else:
        for e0, e1, sgn in ((R[1], R[2], 1), (R[3], R[0], -1)):
            quad(mbc, [v3(e0, eave), v3(e1, eave), v3(c + u * (sgn * hu), z_r - 0.2)], wall_mat, want=v3(u * sgn, 0))
    _prism(mbd, v3(r0, z_r + 0.05), v3(r1, z_r + 0.05), 0.14, 0.14, 'roof', seg=6)
    if dormers:                                          # small gabled dormers proud of the roof plane (no black slashes)
        n_d = max(2, int(2 * (hu - inset * 0.6) / 3.2))
        for side in (-1, 1):
            for j in range(n_d):
                t = (j + 0.5) / n_d
                base = c + u * ((t - 0.5) * 2 * (hu - inset * 0.7)) + v * (side * (hv + ov) * 0.62)
                zb = z_e + rh * (1 - 0.62 * (hv + ov) / (hv + ov)) - 0.05
                dormer(mbd, base, u * side, v * side, zb, w=0.9, h=0.85, depth=0.8)
    return eave


def dormer(mbd, base, d, out, zf, w=1.1, h=1.3, depth=0.75):
    """Small gabled dormer: front face at `base` (facing `out`), cheeks back into the roof slope."""
    a, b = base - d * (w / 2), base + d * (w / 2)
    back = -out * depth
    zr = zf + h + 0.42
    m = base
    o0, o1, z0w, z1w = 0.2, w - 0.2, zf + 0.22, zf + h - 0.08       # real opening in the front (Earth: dark glazing)
    A_ = lambda u_: a + d * u_
    for qq in ([v3(A_(0), zf), v3(A_(o0), zf), v3(A_(o0), zf + h), v3(A_(0), zf + h)],
               [v3(A_(o1), zf), v3(A_(w), zf), v3(A_(w), zf + h), v3(A_(o1), zf + h)],
               [v3(A_(o0), zf), v3(A_(o1), zf), v3(A_(o1), z0w), v3(A_(o0), z0w)],
               [v3(A_(o0), z1w), v3(A_(o1), z1w), v3(A_(o1), zf + h), v3(A_(o0), zf + h)],
               [v3(a, zf + h), v3(b, zf + h), v3(m, zr)]):
        quad(mbd, qq, 'plaster_lime', want=v3(out, 0))
    quad(mbd, [v3(A_(o0) + back * 0.4, z0w), v3(A_(o1) + back * 0.4, z0w), v3(A_(o1) + back * 0.4, z1w), v3(A_(o0) + back * 0.4, z1w)],
         'fort_void', want=v3(out, 0))
    for e0, e1 in ((A_(o0), A_(o0) + back * 0.4), (A_(o1), A_(o1) + back * 0.4)):     # reveals
        quad(mbd, [v3(e0, z0w), v3(e1, z0w), v3(e1, z1w), v3(e0, z1w)], 'plaster_lime', want=v3(m - e0, 0))
    for e in (a, b):
        quad(mbd, [v3(e, zf), v3(e + back, zf + 0.25), v3(e + back, zf + h), v3(e, zf + h)], 'plaster_lime',
             want=v3(e - m, 0))
    for e in (a, b):
        quad(mbd, [v3(e - (m - e).normalized() * 0.08 + out * 0.12, zf + h - 0.05), v3(m + out * 0.12, zr + 0.03),
                   v3(m + back, zr + 0.03), v3(e - (m - e).normalized() * 0.08 + back, zf + h - 0.05)], 'roof',
             want=UP + v3(e - m, 0).normalized() * 0.6)
    window_simple(mbd, A_(o0), A_(o1), z0w, z1w, -out, 0.08)


def spire(mbd, c, z, r, h, mat='roof_tower', seg=12):
    if seg == 4:                                         # square tower: straight pyramid
        lathe_up(mbd, c, z, [(0.0, 0.0), (r, 0.0), (0.0, h)], mat, seg=4)
    else:
        lathe_up(mbd, c, z, [(0.0, 0.0), (r, 0.0), (r * 0.82, h * 0.12), (r * 0.35, h * 0.62), (0.08, h), (0.0, h + 0.02)], mat, seg=seg)
    _prism(mbd, v3(c, z + h - 0.1), v3(c, z + h + 1.4), 0.035, 0.012, 'metal', seg=4)
    sph_mb_ring(mbd, c, z + h + 0.5, 0.09, 'gold', seg=6)


def north_walls(mbc, mbd, T, pts, garden_c=None):
    """'Severné hradby': curved 2-storey range along the north curtain round the Baroque garden.
    Garden frontage (refs 15, 17, 27): white, regular windows on both floors, tall mansard roof with a dense
    row of dormers; outer (city) face: rubble lower storey, plaster above.  Corner turrets with red spires
    at the round west end and the small stair turret.  The round east end is the Luginsland bastion:
    battered rubble up to a parapet that hides the roof, cordon at 2/3 height, gun ports, a box oriel."""
    P = ccw(pts)
    N = len(P)
    hs = [T.h(p.x, p.y) for p in P]
    gt = max(hs)
    eave = gt + 7.4
    lug = lambda p: (p - LUGINSLAND_C).length < LUGINSLAND_R
    # (centre, capture radius, roof radius, wall top, roof height, roof segments): round NW corner tower
    # and the small square tower mid-length with a red pyramid roof (ref 27)
    turrets = [(Vector((-3.0, 210.3)), 5.5, 4.4, eave + 2.0, 6.5, 12), (Vector((70.8, 171.4)), 3.6, 3.0, eave + 2.6, 3.6, 4)]
    tur = lambda p: next((t for t in turrets if (p - t[0]).length < t[1]), None)
    en = [Vector(((P[(k + 1) % N] - P[k]).y, -(P[(k + 1) % N] - P[k]).x)).normalized() for k in range(N)]   # outward
    vn = [(en[k - 1] + en[k]).normalized() for k in range(N)]
    for k in range(N):
        a, b = P[k], P[(k + 1) % N]
        L = (b - a).length
        if L < 0.3:
            continue
        d = (b - a) / L
        nin = Vector((-d.y, d.x))
        foot = min(T.h(*(a - nin * 2.5)), T.h(*(b - nin * 2.5)), gt)
        if lug(a) and lug(b):                            # Luginsland (mitred batter: no seams between facets)
            ztop = eave + 1.3
            n = max(1, int(L / 1.6))
            bat = min(0.08 * (ztop - foot), 1.2)
            bc = bat * 0.34
            for j in range(n):
                t0, t1 = j / n, (j + 1) / n
                p0, p1 = a.lerp(b, t0), a.lerp(b, t1)
                o0 = vn[k].lerp(vn[(k + 1) % N], t0) if lug(P[k - 1]) else -nin
                o1 = vn[k].lerp(vn[(k + 1) % N], t1) if lug(P[(k + 2) % N]) else -nin
                prism8(mbc, p0 + o0 * bat, p1 + o1 * bat, p1 + nin * 1.6, p0 + nin * 1.6, foot - 2.0,
                       p0, p1, p1 + nin * 1.6, p0 + nin * 1.6, ztop, 'rubble')
                zc = foot + (ztop - foot) * 0.66
                prism8(mbd, p0 + o0 * (bc + 0.22), p1 + o1 * (bc + 0.22), p1 + nin * 0.2, p0 + nin * 0.2, zc,
                       p0 + o0 * (bc + 0.22), p1 + o1 * (bc + 0.22), p1 + nin * 0.2, p0 + nin * 0.2, zc + 0.3, 'stone')
                pm = (p0 + p1) / 2
                if j % 2 == 0:
                    round_port(mbd, pm - nin * (bat * 0.55), d, -nin, foot + (ztop - foot) * 0.45, 0.22, 'fort_void')
                else:
                    arched_niche(mbd, pm - nin * (bc * 0.5), d, -nin, zc + 1.4, 0.45, 0.8, 'fort_void')
            prism8(mbd, a - nin * 0.08, b - nin * 0.08, b + nin * 1.7, a + nin * 1.7, ztop,
                   a - nin * 0.08, b - nin * 0.08, b + nin * 1.7, a + nin * 1.7, ztop + 0.13, 'coping')
            continue
        m = (a + b) / 2
        garden = garden_c is not None and (-nin).dot(garden_c - m) > 0 and (garden_c - m).length < 140
        tt = tur(a) if tur(a) is tur(b) else None
        ztop = tt[3] if tt else eave
        ops = []
        if L > 2.8:
            nax = max(1, int(L / 3.4))
            for j in range(nax):
                uu = L / nax * (j + 0.5)
                ops.append((uu - 0.55, uu + 0.55, gt + 4.4, gt + 6.1))
                if garden or tt:
                    ops.append((uu - 0.55, uu + 0.55, gt + 1.0, gt + 2.8))
        if garden or tt:                                 # garden side: pale plaster (Earth), stone plinth
            wall(mbc, a, b, foot - 2.5, ztop, 0.8, 'plaster_lime', ops, mat_in='plaster_int')
            seg_box(mbd, a, b, -0.1, 0.02, foot - 0.3, gt + 0.6, 'stone')                        # plinth
        else:
            wall(mbc, a, b, foot - 2.5, gt + 3.6, 1.1, 'rubble', [], mat_in='rubble')
            wall(mbc, a, b, gt + 3.6, ztop, 0.7, 'plaster_lime', ops, mat_in='plaster_int')
        for o in ops:
            window_simple(mbd, a + d * o[0], a + d * o[1], o[2], o[3], nin, 0.3)
            seg_box(mbd, a + d * (o[0] - 0.12), a + d * (o[1] + 0.12), -0.08, 0.3, o[2] - 0.1, o[2], 'stone')
            if garden or tt:                             # plain light window surrounds
                for e0, e1 in ((o[0] - 0.16, o[0]), (o[1], o[1] + 0.16)):
                    seg_box(mbd, a + d * e0, a + d * e1, -0.05, 0.02, o[2], o[3] + 0.16, 'plaster_lime')
                seg_box(mbd, a + d * (o[0] - 0.16), a + d * (o[1] + 0.16), -0.05, 0.02, o[3], o[3] + 0.16, 'plaster_lime')
        seg_box(mbd, a, b, -0.18, 0.02, gt + 3.45, gt + 3.7, 'stone')
        sweep(mbd, a, b, [(0.0, 0.0), (0.12, 0.06), (0.22, 0.2), (0.35, 0.3), (0.0, 0.3)], ztop - 0.3, 'frame', -nin)
        if garden and not tt and L > 2.8:                # dense dormer row on the lower garden slope + small upper ones
            nax = max(1, int(L / 2.6))
            for j in range(nax):
                uu = L / nax * (j + 0.5)
                dormer(mbd, a + d * uu - nin * 0.25 + nin * 0.45, d, -nin, eave + 0.95, w=0.95)
                if j % 2 == 0:
                    dormer(mbd, a + d * uu + nin * 1.45, d, -nin, eave + 3.85, w=0.6, h=0.6, depth=0.9)
    for c, _, r, zt, h, sg in turrets:                  # turret roofs
        spire(mbd, c, zt - 0.1, r + 0.55, h, seg=sg)
    # box oriel on the Luginsland south side
    lp = [p for p in P if lug(p)]
    if lp:
        s_pt = min(lp, key=lambda p: p.y)
        out = (s_pt - LUGINSLAND_C).normalized()
        side = Vector((-out.y, out.x))
        zo = eave - 2.6
        f0, f1 = s_pt + side * 1.0 + out * 1.1, s_pt - side * 1.0 + out * 1.1
        b0, b1 = s_pt + side * 1.0 - out * 0.3, s_pt - side * 1.0 - out * 0.3
        prism8(mbd, b0, b1, f1, f0, zo, b0, b1, f1, f0, zo + 2.2, 'limestone')
        for k in range(3):                               # corbels
            t = 1.1 - 0.35 * (k + 1)
            prism8(mbd, b0, b1, s_pt - side + out * t, s_pt + side + out * t, zo - 0.3 * (k + 1),
                   b0, b1, s_pt - side + out * (t + 0.35), s_pt + side + out * (t + 0.35), zo - 0.3 * k, 'stone')
        quad(mbd, [v3(f0 + out * 0.2 + side * 0.15, zo + 2.2), v3(f1 + out * 0.2 - side * 0.15, zo + 2.2),
                   v3(b1 - side * 0.15, zo + 3.0), v3(b0 + side * 0.15, zo + 3.0)], 'roof_tower', want=UP + v3(out, 0))
        window_simple(mbd, f0 - side * 0.5, f1 + side * 0.5, zo + 0.6, zo + 1.7, -out, -0.02)
    # tall mansard on a simplified outline (turret loops get their own spires)
    RP = [p for p in P if not tur(p)]
    slab(mbc, [RP], eave, 0.3, 'plaster_int', 'plaster_int', 'plaster_int')
    o_out = offset_poly(RP, 0.45)
    i1 = offset_poly(RP, -1.3)
    i2 = offset_poly(RP, -3.2)
    z1, z2 = eave + 3.9, eave + 4.8
    for k in range(len(RP)):
        j = (k + 1) % len(RP)
        nout = Vector(((RP[j] - RP[k]).y, -(RP[j] - RP[k]).x)).normalized()
        quad(mbd, [v3(o_out[k], eave - 0.15), v3(o_out[j], eave - 0.15), v3(i1[j], z1), v3(i1[k], z1)], 'roof', want=UP * 0.3 + v3(nout, 0))
        quad(mbd, [v3(i1[k], z1), v3(i1[j], z1), v3(i2[j], z2), v3(i2[k], z2)], 'roof', want=UP + v3(nout, 0) * 0.4)
    slab(mbd, [i2], z2 + 0.01, 0.05, 'roof', 'roof', 'roof')
    return eave


# ---------------------------------------------------------------- south terrace + lower court (Earth views)
ARCADE_WALL = 115596635
# paved terrace south of the Honour Court up to the white arcade wall, and the lower court below it
# (amphitheatre); outlines from the orthophoto and the OSM wall 115596635
S_TERRACE = [(-25.2, -87.1), (7.8, -89.6), (8.3, -89.3), (9.4, -88.9), (11.1, -86.9), (14.3, -87.1), (26.2, -87.8),
             (26.8, -78.0), (-25.2, -78.0)]
LOWER_COURT = [(-24.0, -88.9), (7.8, -91.4), (9.4, -90.7), (11.1, -88.7), (14.3, -88.9), (25.4, -89.6), (29.5, -92.5),
               (29.5, -104.0), (14.0, -112.8), (-12.0, -112.8), (-13.0, -104.8), (-24.0, -104.8)]   # W: road up from the Leopold Gate
LOWER_Z = -9.85
SEATS = (-15.4, 7.3, -105.8, -95.4)        # amphitheatre seating block (blue rows, ortho), rising to the north
STAGE = (-13.0, 9.0, -117.0, -112.2)


GATE_RECTS = []


def gate_passage_rect(T, pts, ax, aw, shift, extra=0.5):
    """Passage footprint of a gate tower/block (same frame as sigismund_gate / nicholas_gate) and a terrain
    function carving it to just below the linear floor between the two mouths."""
    axis, on = ax
    c, u, v, hu, hv = obb(pts)
    if axis is None:
        axis, on = u, c
    across = Vector((-axis.y, axis.x))
    if shift:
        c = c + across * (on - c).dot(across)
        ha = abs(axis.dot(u)) * hu + abs(axis.dot(v)) * hv
        za, zb = T.h(*(c - axis * ha)), T.h(*(c + axis * ha))
    else:
        ha = max(abs(axis.dot(u)) * hu + abs(axis.dot(v)) * hv, 3.0)
        za, zb = T.h(*(c - axis * (ha + 0.6))), T.h(*(c + axis * (ha + 0.6)))
    hl, hx = ha + extra, aw / 2 + 1.2                     # inside the tower walls: no pit opens beside the tower
    R = [tuple(c - axis * hl - across * hx), tuple(c + axis * hl - across * hx), tuple(c + axis * hl + across * hx),
         tuple(c - axis * hl + across * hx)]
    def raw(x, y):                                       # the terrain this carve replaces (never raised)
        saved = T.patches
        T.patches = ()
        try:
            return T.h(x, y)
        finally:
            T.patches = saved

    def zf(x, y, c=c, axis=axis, hl=hl, za=za, zb=zb):
        t = max(0.0, min(1.0, ((x - c.x) * axis.x + (y - c.y) * axis.y + hl) / (2 * hl)))
        return min(za + (zb - za) * t - 0.15, raw(x, y))
    return R, zf


def terrain_patches(H, T):
    """Flat terraces held by walls that the 2.4 m DMR smears into slopes (called from Terrain.__init__)."""
    bb = lambda P: (min(p[0] for p in P) - 0.01, max(p[0] for p in P) + 0.01, min(p[1] for p in P) - 0.01, max(p[1] for p in P) + 0.01)
    court = lambda x, y: -0.03 - 0.02 * max(0.0, -40.0 - y)          # Honour Court fall continued (Terrain.h)
    base = [(S_TERRACE, court, bb(S_TERRACE)), (LOWER_COURT, lambda x, y: LOWER_Z, bb(LOWER_COURT))]
    # terrain trimmed under the rebuilt flights of the descents (no terrain wedges poking through the treads)
    T.patches = base
    try:
        routes = json.load(open(os.path.join(H['DATA'], DESCENTS_JSON)))
        feats = json.load(open(os.path.join(H['DATA'], 'castle_local.json')))['features']
    except (OSError, ValueError):
        return base
    import math as _m
    rl = [[(q[0], q[1]) for q in P] for P in routes.values()]

    def dseg(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy + 1e-12)))
        return _m.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1])
    out = []
    for f in feats:
        if f['kind'] != 'road' or f['tags'].get('highway') != 'steps':
            continue
        pl = [(q[0], q[1]) for q in f['pts']]
        if f['id'] in (25117591, 115596640):
            continue                                     # Zámocké schody: own street profile below; Nicholas passage stair
        probe = pl + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(pl, pl[1:])]
        if not any(dseg(m, a, b) < 1.5 for m in probe for L_ in rl for a, b in zip(L_, L_[1:])):
            continue
        try:
            w = float(f['tags'].get('width', '').split()[0])
        except (ValueError, IndexError):
            w = 2.4
        Ls = [0.0]
        for a, b in zip(pl, pl[1:]):
            Ls.append(Ls[-1] + _m.hypot(b[0] - a[0], b[1] - a[1]))
        if Ls[-1] < 0.6:
            continue
        za, zb = T.h(*pl[0]), T.h(*pl[-1])
        for i, (a, b) in enumerate(zip(pl, pl[1:])):
            L = Ls[i + 1] - Ls[i]
            if L < 0.2:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            hw = w / 2 + (1.2 if f['id'] == 155211869 else 0.9)   # trim beyond the treads: no grass wedges (Codex V5)
            R = [(a[0] - uy * hw, a[1] + ux * hw), (a[0] + uy * hw, a[1] - ux * hw), (b[0] + uy * hw, b[1] - ux * hw), (b[0] - uy * hw, b[1] + ux * hw)]

            def zf(x, y, a=a, ux=ux, uy=uy, s0=Ls[i], L=L, tot=Ls[-1], za=za, zb=zb):
                t = max(0.0, min(L, (x - a[0]) * ux + (y - a[1]) * uy))
                zl = za + (zb - za) * (s0 + t) / tot - 0.06
                return min(zl, T.raw(x, y) - T.z0)
            out.append((R, zf, bb(R)))
    # Zámocké schody: terrain sunk under the visual stepped street (monotone profile of the terrain along it)
    n_gen = len(out)
    zf_ = next((f for f in feats if f['id'] == 25117591), None)      # street + apron footprint (Codex V4 4)
    if zf_:
        pl = [(q[0], q[1]) for q in zf_['pts']]
        samp, acc = [], 0.0
        for a, b in zip(pl, pl[1:]):
            L = _m.hypot(b[0] - a[0], b[1] - a[1])
            k = max(1, int(L / 0.9))
            for i in range(k):
                t = i / k
                samp.append((acc + L * t, T.h(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)))
            acc += L
        samp.append((acc, T.h(*pl[-1])))
        prof = []
        for s_, z_ in samp:
            prof.append((s_, min(z_, prof[-1][1]) if prof else z_))
        acc = 0.0
        for a, b in zip(pl, pl[1:]):
            L = _m.hypot(b[0] - a[0], b[1] - a[1])
            if L < 0.2:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            hw = 6.0                                     # street + shoulders up to the house fronts (Codex V4#2 3)
            R = [(a[0] - uy * hw, a[1] + ux * hw), (a[0] + uy * hw, a[1] - ux * hw), (b[0] + uy * hw, b[1] - ux * hw), (b[0] - uy * hw, b[1] + ux * hw)]

            def zf2(x, y, a=a, ux=ux, uy=uy, s0=acc, L=L):
                t = max(0.0, min(L, (x - a[0]) * ux + (y - a[1]) * uy)) + s0
                dd = abs((x - a[0]) * -uy + (y - a[1]) * ux)
                zp = min(prof, key=lambda q: abs(q[0] - t))[1]
                return min(T.raw(x, y) - T.z0, zp - 0.25 if dd <= 4.8 else zp - 0.25 + 0.3 * (dd - 4.8))
            out.append((R, zf2, bb(R)))
            acc += L
    out = out[n_gen:] + out[:n_gen]                      # the street trench wins over the flights joining it
    # gate passages: terrain carved to the passage floor profile (no draped paving rising up the walls, Codex V4 1)
    _bind(H)
    roads = [f for f in feats if f['kind'] == 'road']
    F_ = {f['id']: f for f in feats}
    for gid, aw in ((SIGISMUND, 3.4),):
        if gid not in F_:
            continue
        R, zf3 = gate_passage_rect(T, F_[gid]['pts'], passage_axis(roads, F_[gid]['pts']), aw, gid == NICHOLAS, extra=0.8)
        out.append((R, zf3, bb(R)))
        GATE_RECTS.append(R)
    T.patches = base + out
    return base + out + wall_breaks(T, feats, bb) + path_trenches(T, feats, bb)


def wall_breaks(T, feats, bb):
    """Lower S hillside: the DMR smears the terrace breaks held by the OSM retaining walls into one grassy bowl.
    Along those walls the ground is levelled 3 m uphill (shelf) and 3 m downhill (foot), so the wall face takes
    the step (Codex V4#3 2; modest: Earth shows a construction site there)."""
    def under(x, y):
        saved = T.patches
        T.patches = ()
        try:
            return T.h(x, y)
        finally:
            T.patches = saved
    out = []
    for f in feats:
        if f['kind'] != 'wall' or f['tags'].get('barrier') != 'retaining_wall':
            continue
        P = [Vector(q[:2]) for q in f['pts']]
        for a, b in zip(P, P[1:]):
            L = (b - a).length
            m = (a + b) / 2
            if L < 1.0 or not (-190.0 < m.x < 130.0 and m.y < -112.0):
                continue
            u = (b - a) / L
            n = Vector((-u.y, u.x))
            za, zb = under(*(m + n * 3.5)), under(*(m - n * 3.5))
            if abs(za - zb) < 1.0:
                continue
            up = n if za > zb else -n
            for sg, lim in ((1, max(za, zb)), (-1, min(za, zb))):
                side = up * sg
                R = [tuple(a + side * 0.2), tuple(b + side * 0.2), tuple(b + side * 3.0), tuple(a + side * 3.0)]
                zs_ = (under(*(a + side * 3.5)), under(*(b + side * 3.5)))

                def zf(x, y, a=a, u=u, L=L, zs_=zs_, sg=sg):
                    t = max(0.0, min(1.0, (Vector((x, y)) - a).dot(u) / L))
                    zl = zs_[0] + (zs_[1] - zs_[0]) * t
                    return max(under(x, y), zl) if sg > 0 else min(under(x, y), zl)
                out.append((R, zf, bb(R)))
    return out


def path_profiles(T, feats):
    """Smoothed centreline profile of every kerbed ground path (ground_paths), resampled ~1 m:
    {way id: (pts, zs, width)} -- the paving is laid level across on it, the terrain trenched below."""
    area_f = next((f['pts'] for f in feats if f['tags'].get('name') == 'Bratislavský hrad'), None)
    if not area_f:
        return {}
    area = offset_poly(area_f, 30.0)
    garden = next((f['pts'] for f in feats if f['tags'].get('name') == 'Baroková záhrada'), None)
    skip = [S_TERRACE, LOWER_COURT, WC_COURT] + ([garden] if garden else [])
    ax0, ax1 = min(p[0] for p in area) - 5, max(p[0] for p in area) + 5
    ay0, ay1 = min(p[1] for p in area) - 5, max(p[1] for p in area) + 5
    skip += [f['pts'] for f in feats if (f['kind'] in ('building', 'part') or f['kind'] == 'road' and f['tags'].get('area') == 'yes')
             and any(ax0 < q[0] < ax1 and ay0 < q[1] < ay1 for q in f['pts'])]     # as ground_paths: no paving there
    skip = [(e, (min(p[0] for p in e), max(p[0] for p in e), min(p[1] for p in e), max(p[1] for p in e))) for e in skip]
    skip += steps_footprints(feats)                      # as ground_paths: no paving over the flights / landings
    F_ = {f['id']: f for f in feats}
    roads = [f for f in feats if f['kind'] == 'road']
    ex = [[tuple(p[:2]) for p in F_[VIENNA]['pts']]] if VIENNA in F_ else []
    for gid, aw in ((SIGISMUND, 3.4), (NICHOLAS, 2.8)):  # as ground_paths: gate passages carry their own floors
        if gid in F_:
            ex.append(gate_passage_rect(T, F_[gid]['pts'], passage_axis(roads, F_[gid]['pts']), aw, gid == NICHOLAS, extra=2.4)[0])
    skip += [(e, (min(p[0] for p in e), max(p[0] for p in e), min(p[1] for p in e), max(p[1] for p in e))) for e in ex]
    prof = {}
    for f in feats:
        t = f['tags']
        hw = t.get('highway')
        if f['kind'] != 'road' or hw not in PATH_W or t.get('area') == 'yes' or t.get('tunnel') or t.get('layer', '0').startswith('-'):
            continue
        if PATH_MAT.get(t.get('surface'), 'stone') is None and f['id'] not in ROAD_OVERRIDE:
            continue
        try:
            w = float(t.get('width', '').split()[0])
        except (ValueError, IndexError):
            w = PATH_W[hw]
        if f['id'] in ROAD_OVERRIDE:
            w = ROAD_OVERRIDE[f['id']][1]
        pl = [Vector(q[:2]) for q in f['pts']]
        pts = []
        for a, b in zip(pl, pl[1:]):
            k = max(1, int((b - a).length / 1.0))
            pts += [a.lerp(b, i / k) for i in range(k)]
        pts.append(pl[-1])
        if len(pts) < 2 or not any(point_in_poly(q.x, q.y, area) for q in pts):
            continue
        raw = [T.h(q.x, q.y) for q in pts]
        zs = [sum(raw[max(0, i - 2):i + 3]) / len(raw[max(0, i - 2):i + 3]) for i in range(len(raw))]   # +-2 m mean
        keep = [point_in_poly(q.x, q.y, area) and not any(e_[0] <= q.x <= e_[1] and e_[2] <= q.y <= e_[3] and point_in_poly(q.x, q.y, e)
                                                          for e, e_ in skip) for q in pts]
        prof[f['id']] = (pts, zs, w, keep)
    return prof


def path_trenches(T, feats, bb):
    """Terrain under the kerbed paths: <= paving - 0.3 under the paving, <= paving - 0.05 in a 0.5 m band
    beside it (Fable V4: terrain / ortho decal bulging through the paving beside the stairs)."""
    T.path_prof = prof = path_profiles(T, feats)
    for fid, (pts, zs, w, keep) in list(prof.items()):  # junctions: a path's end meets the paving it joins (no lip)
        for idx in (range(len(zs)) if fid not in ROAD_OVERRIDE else ()):                       # where a wider path paves it: take that path's height
            if 0 < idx < len(zs) - 1 and covered_by(T, pts[idx], fid, w) and covered_by(T, pts[idx - 1], fid, w) \
                    and covered_by(T, pts[idx + 1], fid, w):
                zo = path_z(T, pts[idx], skip=fid)
                if zo is not None and abs(zo - 0.07 - zs[idx]) < 0.25:   # (a bigger mismatch is a real level change)
                    zs[idx] = zo - 0.07
        for end in (0, -1):
            zo = path_z(T, pts[end], skip=fid)
            if zo is None:
                continue
            dz = zo - 0.07 - zs[end]
            n_ = min(5, len(zs))
            for k in range(n_):
                idx = k if end == 0 else len(zs) - 1 - k
                zs[idx] += dz * (1.0 - k / n_)
    T.shelves = []
    out = []
    for fid, (pts, zs, w, keep) in prof.items():
        for i in range(len(pts) - 1):
            if not (keep[i] and keep[i + 1]):
                continue
            a, b = pts[i], pts[i + 1]
            L = (b - a).length
            if L < 0.1:
                continue
            u = (b - a) / L
            n = Vector((-u.y, u.x))
            hw = w / 2 + 1.4                             # trench + a blend band back up to the terrain (no pits / cliffs)
            R = [tuple(a - u * 0.3 - n * hw), tuple(b + u * 0.3 - n * hw), tuple(b + u * 0.3 + n * hw), tuple(a - u * 0.3 + n * hw)]

            def zf(x, y, a=a, u=u, n=n, L=L, z0=zs[i], z1=zs[i + 1], w=w):
                saved = T.patches
                T.patches = ()                           # the terrain this trench replaces
                try:
                    under = T.h(x, y)
                finally:
                    T.patches = saved
                q = Vector((x, y)) - a
                t = max(0.0, min(1.0, q.dot(u) / L))
                zp = z0 + (z1 - z0) * t
                dd = abs(q.dot(n)) - (w / 2 + 0.15)
                return min(under, zp - 0.3 if dd <= 0 else zp - 0.05 + 0.9 * dd)
            out.append((R, zf, bb(R)))
            m_ = (a + b) / 2
            if not S_SLOPE(m_):
                continue
            for sg in (-1, 1):                           # S hillside: a level shelf below the walk, held by a retaining face
                zo = T.h(*(m_ + n * (sg * (w / 2 + 3.0))))
                if (zs[i] + zs[i + 1]) / 2 - zo < 0.9:
                    continue                             # not the downhill side / too gentle
                e0, e1 = a + n * (sg * (w / 2 + 0.5)), b + n * (sg * (w / 2 + 0.5))
                f0, f1 = a + n * (sg * (w / 2 + 2.5)), b + n * (sg * (w / 2 + 2.5))
                Rs = [tuple(e0 - u * 0.3), tuple(e1 + u * 0.3), tuple(f1 + u * 0.3), tuple(f0 - u * 0.3)]
                if any(path_z(T, q_, skip=fid, pad=1.0) is not None for q_ in (f0, f1, (e0 + f1) / 2, (e1 + f0) / 2)):
                    continue                             # another walk below (serpentines): no shelf over it

                def zfs(x, y, a=a, u=u, L=L, z0=zs[i], z1=zs[i + 1]):
                    t = max(0.0, min(1.0, (Vector((x, y)) - a).dot(u) / L))
                    return z0 + (z1 - z0) * t - 0.12
                out.append((Rs, zfs, bb(Rs)))
                T.shelves.append((f0, f1, n * sg, zs[i] - 0.12, zs[i + 1] - 0.12))
    return out


S_SLOPE = lambda q: -120.0 < q[0] < 130.0 and -230.0 < q[1] < -112.0   # lower S hillside (ge_stairs_s / ph_slope_s)


def shelf_walls(mb, T, shelves):
    """Retaining faces + grey copings along the S-hillside walk shelves (terrace breaks of ge_stairs_s)."""
    for f0, f1, out, z0, z1 in shelves:
        g0, g1 = T.h(*(f0 + out * 0.8)), T.h(*(f1 + out * 0.8))
        if max(z0 - g0, z1 - g1) < 0.5:
            continue
        i0, i1, o0, o1 = f0 - out * 0.15, f1 - out * 0.15, f0 + out * 0.45, f1 + out * 0.45
        prism8(mb, i0, i1, o1, o0, min(g0, g1) - 0.4, i0, i1, o1, o0, z0 + 0.35, 'rubble', z1b=z1 + 0.35)
        prism8(mb, i0 - out * 0.05, i1 - out * 0.05, o1 + out * 0.05, o0 + out * 0.05, z0 + 0.35,
               i0 - out * 0.05, i1 - out * 0.05, o1 + out * 0.05, o0 + out * 0.05, z0 + 0.45, 'stone', z0b=(z0 + 0.35, z1 + 0.35), z1b=(z0 + 0.45, z1 + 0.45))


def covered_by(T, q, fid, w):
    """Does a wider (or equal, lower-id) kerbed path pave q?  Then this path leaves the junction to it:
    one surface, no overlapping strips / seams (Codex V5 junctions)."""
    for f2, (pts, zs, w2, keep) in getattr(T, 'path_prof', {}).items():
        if f2 == fid or w2 < w or (w2 == w and f2 > fid):
            continue
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if not (keep[i] and keep[i + 1]) or abs(q.x - a.x) > 6 or abs(q.y - a.y) > 6:
                continue
            L = (b - a).length or 1.0
            t = max(0.0, min(1.0, (q - a).dot(b - a) / (L * L)))
            if (a.lerp(b, t) - q).length <= w2 / 2 + 0.1:
                return True
    return False


def path_z(T, q, skip=None, pad=0.0, own=None):
    """Paving height of the kerbed path under q (None off the paths); `skip`: a way id to ignore; `own`:
    (way id, sample index) -- that way still counts, except its segments next to the index (sharp bends)."""
    best = None
    for fid, (pts, zs, w, keep) in getattr(T, 'path_prof', {}).items():
        if fid == skip:
            continue
        for i in range(len(pts) - 1):
            if own and fid == own[0] and abs(i - own[1]) <= 2:
                continue
            a, b = pts[i], pts[i + 1]
            if not (keep[i] and keep[i + 1]) or abs(q.x - a.x) > 6 or abs(q.y - a.y) > 6:
                continue
            L = (b - a).length or 1.0
            t = max(0.0, min(1.0, (q - a).dot(b - a) / (L * L)))
            if (a.lerp(b, t) - q).length <= w / 2 + pad:
                z = zs[i] + (zs[i + 1] - zs[i]) * t + 0.07
                best = z if best is None else max(best, z)
    return best


def _clip_convex(cell, poly):
    """Sutherland-Hodgman: clip a polygon (list of (x, y)) by a convex CCW polygon."""
    out = cell
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        inside = lambda p: (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) >= 0
        src, out = out, []
        for j in range(len(src)):
            p, q = src[j], src[(j + 1) % len(src)]
            ip, iq = inside(p), inside(q)
            if ip:
                out.append(p)
            if ip != iq:
                dx, dy = q[0] - p[0], q[1] - p[1]
                den = (bx - ax) * dy - (by - ay) * dx
                if abs(den) > 1e-12:
                    t = ((ax - p[0]) * (by - ay) - (ay - p[1]) * (bx - ax)) / den
                    out.append((p[0] + dx * t, p[1] + dy * t))
        if not out:
            return []
    return out


def _convex(poly):
    n = len(poly)
    sg = [(poly[(i + 1) % n][0] - poly[i][0]) * (poly[(i + 2) % n][1] - poly[i][1]) -
          (poly[(i + 1) % n][1] - poly[i][1]) * (poly[(i + 2) % n][0] - poly[i][0]) for i in range(n)]
    return all(v >= -1e-9 for v in sg) or all(v <= 1e-9 for v in sg)


def drape_poly(mb, T, poly, mat, dz, maxe=1.5):
    """Any (non-convex) polygon draped on T.h: tessellated, triangles split to <= maxe so they follow the
    ground; edges stay exactly on the outline (no cell sawtooth)."""
    from mathutils.geometry import tessellate_polygon
    P = [Vector((p[0], p[1], 0.0)) for p in poly]
    if len(P) > 3 and (P[0] - P[-1]).length < 1e-6:
        P = P[:-1]
    if len(P) < 3:
        return
    stack = [[P[i].xy, P[j].xy, P[k].xy] for i, j, k in tessellate_polygon([P])]
    while stack:
        t = stack.pop()
        L = [(t[(i + 1) % 3] - t[i]).length for i in range(3)]
        m = max(range(3), key=lambda i: L[i])
        if L[m] > maxe:
            a, b, c = t[m], t[(m + 1) % 3], t[(m + 2) % 3]
            h = (a + b) / 2
            stack += [[a, h, c], [h, b, c]]
            continue
        oriented_poly(mb, [Vector((q.x, q.y, T.h(q.x, q.y) + dz)) for q in t], UP, mat)


def drape(mb, T, poly, mat, dz, cell=1.0, skip=()):
    """Paving draped on T.h over a polygon: whole cells inside, boundary cells clipped to a convex outline
    (clean edges), cells inside `skip` polygons left out."""
    poly = [tuple(p[:2]) for p in poly]
    if poly_area(poly) < 0:
        poly = poly[::-1]
    convex = _convex(poly)
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    x = math.floor(min(xs))
    while x < max(xs):
        y = math.floor(min(ys))
        while y < max(ys):
            q = [(x, y), (x + cell, y), (x + cell, y + cell), (x, y + cell)]
            cx, cy = x + cell / 2, y + cell / 2
            ins = [point_in_poly(a, b, poly) for a, b in q]
            if all(ins):
                pass
            elif convex and any(ins) or (convex and point_in_poly(cx, cy, poly)):
                q = _clip_convex(q, poly)
            elif point_in_poly(cx, cy, poly):
                pass
            else:
                q = []
            if len(q) >= 3 and not any(point_in_poly(cx, cy, s_) for s_ in skip):
                oriented_poly(mb, [Vector((a, b, T.h(a, b) + dz)) for a, b in q], UP, mat)
            y += cell
        x += cell

def arcade_wall(mbc, mbd, T, pts, way_lines=None):
    """White ashlar retaining wall of the south terrace (Earth): vertical face, buttresses every 4.2 m
    linked by round relieving arches (the blind arcade seen from the south), parapet with stone coping."""
    P = [Vector(p[:2]) for p in pts]
    segs = []
    for a, b in zip(P, P[1:]):                           # cut 1.6 m openings where a way crosses (walkable descents)
        cuts = []
        for pl in (way_lines or []):
            for c, e in zip(pl, pl[1:]):
                if _seg_x(a, b, c, e):
                    dd = (b - a)
                    den = dd.x * (e - c).y - dd.y * (e - c).x
                    if abs(den) > 1e-9:
                        cuts.append(((c - a).x * (e - c).y - (c - a).y * (e - c).x) / den)
        L0 = (b - a).length
        pts_ = [0.0]
        for t in sorted(cuts):
            pts_ += [max(0.0, t - 1.6 / L0), min(1.0, t + 1.6 / L0)]
        pts_.append(1.0)
        for t0, t1 in zip(pts_[0::2], pts_[1::2]):
            if t1 - t0 > 0.05:
                segs.append((a.lerp(b, t0), a.lerp(b, t1)))
    for a, b in segs:
        L = (b - a).length
        if L < 0.3:
            continue
        d = (b - a) / L
        nn = Vector((-d.y, d.x))
        m = (a + b) / 2
        sa, sb = T.h(*(m + nn * 2.5)), T.h(*(m - nn * 2.5))
        out = -nn if sa > sb else nn                     # towards the lower court
        hi, lo = max(sa, sb), min(sa, sb)
        if hi - lo < 1.0:
            hi = max(hi, lo + 1.0)
        th = 0.6                                         # thin: the OSM path runs along its foot
        q = [a, b, b + out * th, a + out * th]
        mbc.box(q, lo - 1.2, hi, 'limestone')
        par = [a - out * 0.1, b - out * 0.1, b + out * 0.45, a + out * 0.45]
        mbc.box(par, hi, hi + 1.0, 'limestone')
        mbd.box([a - out * 0.18, b - out * 0.18, b + out * 0.55, a + out * 0.55], hi + 1.0, hi + 1.14, 'stone')
        if hi - lo > 4.0 and L > 5.0:                     # mostly solid pale wall: narrow buttresses, shallow arched niches
            nb = max(2, int(L / 6.0) + 1)
            fa = a + out * th
            zt = hi - 1.4
            prev = None
            for k in range(nb):
                c = fa + d * (L * k / (nb - 1))
                bw = 0.3
                c0 = c - d * bw if k > 0 else c
                c1 = c + d * bw if k < nb - 1 else c
                mbc.box([c0, c1, c1 + out * 0.35, c0 + out * 0.35], lo - 1.0, hi - 0.9, 'limestone')
                if prev is not None:                     # shallow round-headed niche between buttresses
                    pa, pb = prev + d * 0.9, c0 - d * 0.9
                    if (pb - pa).length > 1.5:
                        if Vector((-(pb - pa).y, (pb - pa).x)).dot(out) < 0:
                            pa, pb = pb, pa
                        dd = (pb - pa).normalized()
                        arched_niche(mbd, (pa + pb) / 2 - out * 0.0, dd, out, lo + 0.3, (pb - pa).length, zt - lo - 0.3, 'stone', seg=8)
                prev = c1
            mbd.box([fa - out * 0.02, fa + d * L - out * 0.02, fa + d * L + out * 0.3, fa + out * 0.3], hi - 0.9, hi - 0.7, 'limestone')


def amphitheatre(mbc, mbd):
    """Open-air amphitheatre in the lower court (Earth / ortho): concrete tiers with blue seats rising north
    from a dark stage, two aisles."""
    x0, x1, y0, y1 = SEATS
    rows = 9
    dep = (y1 - y0) / rows
    aisles = [(-9.95, -9.05), (1.95, 2.85)]
    for k in range(rows):
        ya, yb = y0 + k * dep, y0 + (k + 1) * dep
        z = LOWER_Z + (k + 1) * 0.42
        mbc.box([Vector((x0, ya)), Vector((x1, ya)), Vector((x1, y1)), Vector((x0, y1))], LOWER_Z - 0.2, z, 'limestone')   # pale stone tiers
        xs = [x0 + 0.3] + [v for a in aisles for v in a] + [x1 - 0.3]
        for xa, xb in zip(xs[0::2], xs[1::2]):
            mbd.box([Vector((xa, ya + 0.2)), Vector((xb, ya + 0.2)), Vector((xb, ya + 0.75)), Vector((xa, ya + 0.75))],
                    z, z + 0.42, 'seat_blue')
    sx0, sx1, sy0, sy1 = STAGE
    mbc.box([Vector((sx0, sy0)), Vector((sx1, sy0)), Vector((sx1, sy1)), Vector((sx0, sy1))], LOWER_Z - 0.2, LOWER_Z + 0.8, 'stage_dark')


# ---------------------------------------------------------------- west courtyard complex (OSM 5131401)
WEST_COURT = 5131401
WC_LAWN = [(-86.5, -15.1), (-65.7, -18.1), (-59.7, 22.8), (-80.1, 25.5)]          # ortho
WC_PLANTERS = [(-79.5, 11.3), (-64.6, 8.7), (-82.4, -4.0), (-67.3, -6.8)]
WC_COURT = [(-95.0, -27.1), (-63.7, -34.1), (-61.5, -21.7), (-51.6, 30.2), (-86.8, 38.3)]


def _hull(P):
    pts = sorted(set((round(p.x, 4), round(p.y, 4)) for p in P))
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


class _RoofSplit:
    """Proxy MB: roof faces over the wing along the palace get the darker grey-red tiles (Earth)."""
    def __init__(self, mb, dark):
        self.mb, self.dark = mb, dark

    def poly(self, pts, mat, **kw):
        c = sum((Vector(p) for p in pts), Vector((0, 0, 0))) / len(pts)
        self.mb.poly(pts, 'roof_dark' if self.dark(c) else mat, **kw)


def west_court(H, mbc, mbd, T, pts):
    """U-shaped two-storey range west of the palace (Earth, ortho): white walls, regular windows, round-arched
    arcades on the courtyard ground floor with a gallery behind, hip roofs per wing with dormers (darker tiles
    on the wing along the palace); the courtyard: paving, lawn panel with four round planters."""
    P = ccw(pts)
    N = len(P)
    hull = _hull(P)
    court_z = sorted(T.h(*q) for q in [Vector((-75.0, y)) for y in range(-15, 30, 5)])[4]
    f0 = court_z + 0.12                                   # ground-floor level = courtyard
    fh = 4.0
    eave = f0 + 2 * fh + 0.4
    for k in range(N):
        a, b = P[k], P[(k + 1) % N]
        L = (b - a).length
        if L < 0.4:
            continue
        d = (b - a) / L
        nin = Vector((-d.y, d.x))
        m = (a + b) / 2
        q = m - nin * 4.0
        court = point_in_poly(q.x, q.y, hull) and not point_in_poly(q.x, q.y, [(p.x, p.y) for p in P])
        foot = min(T.h(*(a - nin * 1.5)), T.h(*(b - nin * 1.5)), f0) - 1.0
        ops, arches = [], []
        if L > 2.6:
            nax = max(1, int(L / 3.6))
            for j in range(nax):
                uu = L / nax * (j + 0.5)
                ops.append((uu - 0.6, uu + 0.6, f0 + fh + 0.9, f0 + fh + 2.7))
                if court and L > 6.0 and m.x < -64.0:       # palace-side range: windows/doors, no arcade (Earth)
                    arches.append((uu - 1.35, uu + 1.35, f0, f0 + 3.3))
                elif f0 + 1.0 > foot + 1.5 or court:
                    ops.append((uu - 0.6, uu + 0.6, f0 + 1.0, f0 + 2.8))
        wall(mbc, a, b, foot, eave, 0.7, 'plaster_lime', ops + arches, mat_in='plaster_int')
        if foot < f0 - 1.2:
            seg_box(mbd, a, b, -0.12, 0.02, foot, f0 - 0.1, 'stone')                 # stone plinth on the slope
        seg_box(mbd, a, b, -0.12, 0.02, f0 + fh - 0.2, f0 + fh + 0.05, 'plaster_lime')   # string course
        sweep(mbd, a, b, [(0.0, 0.0), (0.12, 0.06), (0.22, 0.2), (0.35, 0.3), (0.0, 0.3)], eave - 0.3, 'frame', -nin)
        for o in ops:
            window_simple(mbd, a + d * o[0], a + d * o[1], o[2], o[3], nin, 0.3)
            seg_box(mbd, a + d * (o[0] - 0.12), a + d * (o[1] + 0.12), -0.08, 0.3, o[2] - 0.1, o[2], 'stone')
        if arches:                                        # arcade: round arches, gallery 3 m deep behind
            for o in arches:
                arch_head(mbc, a + d * o[0], a + d * o[1], o[3], 0.0, 0.7, 'plaster_lime')
                gq = [v3(a + d * o[0] + nin * 0.35, o[2])]          # glazed arch (Earth: dark openings), frame + bars
                zs_ = o[3] - 1.35
                gq.append(v3(a + d * o[1] + nin * 0.35, o[2]))
                for kk in range(9):
                    th_ = math.pi * kk / 8
                    gq.append(v3(a + d * ((o[0] + o[1]) / 2 + 1.35 * math.cos(th_)) + nin * 0.35, zs_ + 1.35 * math.sin(th_)))
                mbd.poly(gq, 'glass')
                for uu in (o[0] + 0.9, o[1] - 0.9):
                    seg_box(mbd, a + d * (uu - 0.04), a + d * (uu + 0.04), 0.3, 0.4, o[2], zs_ + 1.35 * math.sin(math.acos(min(1, abs(uu - (o[0] + o[1]) / 2) / 1.35))), 'frame')
                seg_box(mbd, a + d * o[0], a + d * o[1], 0.3, 0.4, zs_ - 0.04, zs_ + 0.04, 'frame')
                seg_box(mbd, a + d * (o[0] - 0.25), a + d * o[0], -0.08, 0.02, f0, o[3] - 1.35, 'limestone')
                seg_box(mbd, a + d * o[1], a + d * (o[1] + 0.25), -0.08, 0.02, f0, o[3] - 1.35, 'limestone')
            ia, ib = a + d * 0.7 + nin * 3.0, b - d * 0.7 + nin * 3.0
            Lb = (ib - ia).length
            doors = [(Lb / 2 + s_ * min(Lb / 3, 7.0) - 0.7, Lb / 2 + s_ * min(Lb / 3, 7.0) + 0.7, f0 - 0.2, f0 + 2.5) for s_ in (-1, 0, 1)]
            wall(mbc, ia, ib, f0 - 0.4, f0 + 3.8, 0.4, 'plaster_lime', doors, mat_in='plaster_int')
            for o in doors:
                seg_box(mbd, ia + d * o[0], ia + d * o[1], 0.15, 0.25, o[2], o[3], 'door')
            for e0, e1 in ((a + d * 0.7, ia), (ib, b - d * 0.7)):       # gallery end walls
                wall(mbc, e0, e1, f0 - 0.4, f0 + 3.8, 0.3, 'plaster_lime', off=-0.15)
            g4 = [a + d * 0.7 + nin * 0.7, b - d * 0.7 + nin * 0.7, ib, ia]
            oriented_poly(mbd, [v3(p_, f0 + 3.8) for p_ in g4], -UP, 'plaster_lime')        # gallery ceiling
            oriented_poly(mbc, [v3(p_, f0 + 0.03) for p_ in g4], UP, 'stone')               # gallery floor
    slab(mbc, [P], eave, 0.3, 'plaster_int', 'plaster_int', 'plaster_int')
    # hip roof per wing (Terrain-independent distance-field roof from build_castle), darker along the palace
    H['roof_distfield'](_RoofSplit(mbd, lambda c: c.x > -64.0 and c.y < 30.0), [(p.x, p.y) for p in P], eave, 6.0, 'roof',
                        pitch=48.0)
    for k in range(N):                                   # dormers on the long slopes
        a, b = P[k], P[(k + 1) % N]
        L = (b - a).length
        if L < 9.0:
            continue
        d = (b - a) / L
        nin = Vector((-d.y, d.x))
        nax = max(1, int(L / 3.6))
        for j in range(nax):                             # one prominent dormer per bay (Earth)
            uu = L / nax * (j + 0.5)
            dormer(mbd, a + d * uu + nin * 0.9, d, -nin, eave + 0.6, w=1.25, h=1.45, depth=1.1)
    # courtyard: paving, lawn panel, four round planters
    drape_poly(mbc, T, WC_COURT, 'stone', 0.07)          # exact outline (no cell sawtooth); the lawn lies on top
    drape_poly(mbc, T, WC_LAWN, 'grass', 0.13, maxe=1.0)   # same kind of mesh as the court, clear of it
    for x, y in WC_PLANTERS:
        c = Vector((x, y))
        z = T.h(x, y) + 0.05
        lathe_up(mbd, c, z, [(0.0, 0.0), (1.55, 0.0), (1.55, 0.5), (1.38, 0.55), (1.38, 0.42), (0.0, 0.42)], 'limestone', seg=24)
        lathe_up(mbd, c, z + 0.42, [(0.0, 0.0), (1.3, 0.0), (1.2, 0.18), (0.6, 0.35), (0.0, 0.4)], 'box_hedge', seg=24)
        mbc.box([c + Vector((-1.2, -1.2)), c + Vector((1.2, -1.2)), c + Vector((1.2, 1.2)), c + Vector((-1.2, 1.2))], z - 0.1, z + 0.5,
                'invisible')
    return eave


# ---------------------------------------------------------------- paths of the castle grounds
PATH_W = {'footway': 2.0, 'path': 1.2, 'pedestrian': 3.6, 'service': 3.6, 'living_street': 4.5, 'track': 2.5}   # full widths
PATH_MAT = {'sett': 'cobbles', 'cobblestone': 'cobbles', 'unhewn_cobblestone': 'cobbles', 'paving_stones': 'stone',
            'asphalt': 'asphalt', 'concrete': 'pale_paving', 'clay': 'gravel_red', 'fine_gravel': 'gravel_white',
            'gravel': 'gravel_white', 'compacted': 'gravel_white', 'ground': 'gravel', 'grass': None, 'rock': 'stone',
            'wood': 'joinery', None: 'stone'}


LAMPS_KNOWN = []
BENCHES_KNOWN = []
ROAD_OVERRIDE = {37409834: ('asphalt', 6.5), 899970892: ('asphalt', 6.5), 37409835: ('asphalt', 5.0)}


def bench(mb, c, d, face, z):
    """Park bench (Earth / eye level): dark iron frame, timber seat and back, seat facing `face`."""
    L = 0.9
    for s_ in (-1, 1):                                   # two cast-iron side frames
        q = c + d * (s_ * L)
        prism8(mb, q - d * 0.03 - face * 0.22, q + d * 0.03 - face * 0.22, q + d * 0.03 + face * 0.22, q - d * 0.03 + face * 0.22, z,
               q - d * 0.03 - face * 0.22, q + d * 0.03 - face * 0.22, q + d * 0.03 + face * 0.22, q - d * 0.03 + face * 0.22, z + 0.44, 'stage_dark')
    a, b = c - d * (L + 0.1), c + d * (L + 0.1)
    prism8(mb, a - face * 0.22, b - face * 0.22, b + face * 0.22, a + face * 0.22, z + 0.44,
           a - face * 0.22, b - face * 0.22, b + face * 0.22, a + face * 0.22, z + 0.48, 'joinery')
    bk = -face * 0.24
    prism8(mb, a + bk, b + bk, b + bk - face * 0.04, a + bk - face * 0.04, z + 0.55,
           a + bk, b + bk, b + bk - face * 0.04, a + bk - face * 0.04, z + 0.9, 'joinery')
    for s_ in (-1, 1):
        q = c + d * (s_ * L) + bk
        prism8(mb, q - d * 0.03, q + d * 0.03, q + d * 0.03 - face * 0.04, q - d * 0.03 - face * 0.04, z + 0.44,
               q - d * 0.03, q + d * 0.03, q + d * 0.03 - face * 0.04, q - d * 0.03 - face * 0.04, z + 0.92, 'stage_dark')


WALL_LINES = []             # OSM wall polylines (set in _build): no handrail within 1 m of a wall / passage side


def near_any_wall(q, r=1.0):
    if any(abs(a.x - q.x) < 30 and abs(a.y - q.y) < 30 and dist_seg(q, a, b) < r + 0.6 for L_ in WALL_LINES for a, b in zip(L_, L_[1:])):
        return True
    for _, _, pa, pb, aw, _, _ in GATE_PASSAGES:            # passage walls
        ax_ = pb - pa
        if ax_.length > 1e-6 and dist_seg(q, pa, pb) < aw / 2 + 0.6:
            return True
    return False


H_OUT = []
RAILS = []                  # (mb, mat, a top, b top, foot z at a, foot z at b, kind): every handrail segment (rails audit)


def rail_seg(mb, a, b, za, zb, fa, fb, mat, kind, r=0.022, mid=None):
    """Handrail segment a(za top) -> b(zb top), post at a down to its foot fa; drawn by finish_rails() which
    chains segments into runs, drops loose stubs (< 2 m) and adds the end posts."""
    RAILS.append((mb, mat, Vector((a.x, a.y, za)), Vector((b.x, b.y, zb)), fa, fb, kind, r, mid))


def finish_rails():
    """Draw the railing runs: no loose stubs, a post at every segment start and at each run end."""
    nxt = {}
    for i, r_ in enumerate(RAILS):
        for j, q_ in enumerate(RAILS):
            if i != j and q_[1] == r_[1] and (q_[2].xy - r_[3].xy).length < 0.08:
                nxt[i] = j
                break
    prev = {j: i for i, j in nxt.items()}
    keep, seen = [], set()
    for i in range(len(RAILS)):
        if i in prev or i in seen:
            continue
        run, k = [], i
        while k is not None and k not in seen:
            seen.add(k)
            run.append(k)
            k = nxt.get(k)
        if sum((RAILS[k][3].xy - RAILS[k][2].xy).length for k in run) >= 2.0:
            keep.append(run)
    for i in range(len(RAILS)):                          # closed loops / leftovers
        if i not in seen:
            keep.append([i])
    out = []
    for run in keep:
        for n_, k in enumerate(run):
            mb, mat, a, b, fa, fb, kind, r, mid = RAILS[k]
            _prism(mb, a, b, r, r, mat, seg=4)
            _prism(mb, Vector((a.x, a.y, fa - 0.05)), a, 0.018, 0.018, mat, seg=4)
            if mid is not None:
                _prism(mb, Vector((a.x, a.y, fa + mid)), Vector((b.x, b.y, fb + mid)), 0.018, 0.018, mat, seg=4)
            if n_ == len(run) - 1:
                _prism(mb, Vector((b.x, b.y, fb - 0.05)), b, 0.018, 0.018, mat, seg=4)
            out.append([kind, list(a), list(b), fa, fb])
    try:
        json.dump(out, open(os.path.join(H_OUT[0], 'rails.json'), 'w'))   # per build tag: parallel builds don't mix
    except (OSError, IndexError):
        pass


BEB_ZONE = lambda q: 160.0 < q[0] < 240.0 and -110.0 < q[1] < 0.0     # Beblavého rampart walks (orange railings)
SE_ZONE = lambda q: 90.0 < q[0] < 230.0 and q[1] < -110.0               # SE slope under the Sigismund gate (white walls)


def steps_footprints(feats):
    """(polygon, bbox) of every OSM flight incl. its landings (+0.6 m; the Zámocké street with its 2.6 m shoulders):
    ground_paths lays no paving or kerbs there (Codex V4#4 1)."""
    out = []
    for f in feats:
        if f['kind'] != 'road' or f['tags'].get('highway') != 'steps':
            continue
        try:
            w = float(f['tags'].get('width', '').split()[0])
        except (ValueError, IndexError):
            w = 2.4
        hw = 2.0 + 2.6 if f['id'] == 25117591 else w / 2 + 0.6
        pl = [Vector(q[:2]) for q in f['pts']]
        for i, (a, b) in enumerate(zip(pl, pl[1:])):
            if (b - a).length < 1e-6:
                continue
            d = (b - a).normalized()
            nn = Vector((-d.y, d.x))
            a_ = a - d * (0.8 if i == 0 else 0.0)
            b_ = b + d * (0.8 if i == len(pl) - 2 else 0.0)
            P = [a_ - nn * hw, b_ - nn * hw, b_ + nn * hw, a_ + nn * hw]
            out.append(([tuple(p) for p in P], (min(p.x for p in P), max(p.x for p in P), min(p.y for p in P), max(p.y for p in P))))
    return out


SFP = []


def ground_paths(mbc, mbd, T, feats, area, excl):
    """Clean paved paths along the OSM ways of the castle grounds (Earth: kerbed sett / paving / clay walks,
    the serpentines on the S and SE slopes): a draped strip at its OSM surface plus stone kerbs.
    Skipped inside areas modelled otherwise (courts, terraces, garden, buildings, gate passages)."""
    n_seg = 0
    SFP[:] = steps_footprints(feats)
    WL = [[Vector(q[:2]) for q in f['pts']] for f in feats if f['kind'] == 'wall']

    def near_wall(q):                                    # Fable V4#4: no rail where a wall / parapet stands within 1 m
        return any(abs(a.x - q.x) < 40 and abs(a.y - q.y) < 40 and dist_seg(q, a, b) < 1.0 + 0.6 for L_ in WL for a, b in zip(L_, L_[1:]))
    LAMPS_KNOWN[:] = [(p_['x'], p_['y']) for p_ in POINTS if p_['kind'] in ('lamp', 'street_lamp')]
    BENCHES_KNOWN[:] = [(p_['x'], p_['y']) for p_ in POINTS if p_['kind'] == 'bench']
    for f in feats:
        t = f['tags']
        hw = t.get('highway')
        if f['kind'] != 'road' or hw not in PATH_W or t.get('area') == 'yes' or t.get('tunnel') or t.get('layer', '0').startswith('-'):
            continue
        mat = PATH_MAT.get(t.get('surface'), 'stone')
        if mat is None:
            continue
        try:
            w = float(t.get('width', '').split()[0])
        except (ValueError, IndexError):
            w = PATH_W[hw]
        if f['id'] in ROAD_OVERRIDE:                     # Vienna gate approach: continuous asphalt carriageway (Earth)
            mat, w = ROAD_OVERRIDE[f['id']]
        pl = [Vector(q[:2]) for q in f['pts']]
        pts = []                                         # resample ~1 m
        for a, b in zip(pl, pl[1:]):
            L = (b - a).length
            k = max(1, int(L / 1.0))
            pts += [a.lerp(b, i / k) for i in range(k)]
        pts.append(pl[-1])
        if len(pts) < 2:
            continue
        nrm = []
        for i in range(len(pts)):
            d0 = pts[i] - pts[max(0, i - 1)]
            d1 = pts[min(len(pts) - 1, i + 1)] - pts[i]
            d = (d0.normalized() if d0.length > 1e-6 else d1.normalized()) + (d1.normalized() if d1.length > 1e-6 else d0.normalized())
            d = d.normalized() if d.length > 1e-6 else Vector((1, 0))
            nrm.append(Vector((-d.y, d.x)))
        on_fl = lambda q: any(e_[0] <= q.x <= e_[1] and e_[2] <= q.y <= e_[3] and point_in_poly(q.x, q.y, e) for e, e_ in SFP)
        ok = [point_in_poly(q.x, q.y, area) and not any(point_in_poly(q.x, q.y, e) for e in excl) and not on_fl(q) for q in pts]
        pp = getattr(T, 'path_prof', {}).get(f['id'])
        zpv = pp[1] if pp and len(pp[1]) == len(pts) else None
        for i in range(len(pts) - 1):
            if not (ok[i] and ok[i + 1]):
                continue
            a, b, na, nb = pts[i], pts[i + 1], nrm[i], nrm[i + 1]
            L0, R0, L1, R1 = a + na * (w / 2), a - na * (w / 2), b + nb * (w / 2), b - nb * (w / 2)
            if zpv:                                      # level across on the smoothed profile (terrain trenched below)
                za_, zb_ = zpv[i], zpv[i + 1]
                z = lambda q, a=a, b=b, za_=za_, zb_=zb_: za_ + (zb_ - za_) * max(0.0, min(1.0, (q - a).dot(b - a) / max((b - a).length_squared, 1e-9)))
            else:
                z = lambda q: T.h(q.x, q.y)
            if zpv and f['id'] not in ROAD_OVERRIDE and covered_by(T, (a + b) / 2, f['id'], w) and covered_by(T, a, f['id'], w) and covered_by(T, b, f['id'], w):
                continue                                 # junction: the wider path's paving and kerbs carry it
            oriented_poly(mbc, [v3(R0, z(R0) + 0.07), v3(R1, z(R1) + 0.07), v3(L1, z(L1) + 0.07), v3(L0, z(L0) + 0.07)], UP, mat)
            for s_, P0, P1, n0, n1 in ((1, L0, L1, na, nb), (-1, R0, R1, na, nb)):     # kerbs / low walls
                if any(path_z(T, X_ + n0 * (s_ * 0.12), skip=f['id'], pad=0.15) is not None for X_ in (P0, (P0 + P1) / 2, P1)) or \
                        (zpv and path_z(T, (P0 + P1) / 2 + n0 * (s_ * 0.12), own=(f['id'], i)) is not None) or \
                        on_fl((P0 + P1) / 2) or on_fl(P0) or on_fl(P1):   # no kerb onto a rebuilt flight / landing
                    continue                             # junction: no kerb across the other path's paving
                drop = z(P0) - T.h(*(P0 + n0 * (s_ * 1.4)))
                low_wall = drop > 0.35                   # downhill edge on a slope: low stone wall (Earth E park)
                beb, se = BEB_ZONE(P0), SE_ZONE(P0)
                rail = 'rail_orange' if beb else 'stage_dark'
                drop1 = z(P1) - T.h(*(P1 + n1 * (s_ * 1.4)))
                if min(drop, drop1) > 0.8 and not near_wall(P0) and not near_wall(P1):   # steep, no parapet next to it: railing
                    Q0, Q1 = P0 + n0 * (s_ * 0.15), P1 + n1 * (s_ * 0.15)   # on the low wall (top +0.5); orange: mid rail
                    rail_seg(mbd, Q0, Q1, z(P0) + 1.05, z(P1) + 1.05, z(P0) + 0.5, z(P1) + 0.5, rail, 'path',
                             r=0.03 if beb else 0.022, mid=0.05 if beb else None)
                    low_wall = True
                wface = 'plaster_lime' if se and low_wall else ('rubble' if beb and low_wall else 'stone')   # SE slope: white walls
                kw, kh = (0.3, 0.5) if low_wall else (0.15, 0.16)
                K0, K1 = P0 + n0 * (s_ * kw), P1 + n1 * (s_ * kw)
                q = [P0, P1, K1, K0]
                zt = [z(P0) + kh, z(P1) + kh, z(P1) + kh, z(P0) + kh]
                _blk = [v3(q_, zz) for q_, zz in zip(q, zt)]
                oriented_poly(mbd, _blk, UP, 'stone')
                oriented_poly(mbd, [v3(K0, min(z(K0), T.h(*K0)) - 0.3), v3(K1, min(z(K1), T.h(*K1)) - 0.3), v3(K1, zt[2]), v3(K0, zt[3])], v3(n0 * s_, 0), wface)
                oriented_poly(mbd, [v3(P0, z(P0) + 0.05), v3(P1, z(P1) + 0.05), v3(P1, zt[1]), v3(P0, zt[0])], -v3(n0 * s_, 0), 'stone')
                dseg_ = (P1 - P0).normalized() if (P1 - P0).length > 1e-6 else Vector((1, 0))
                for E_, F_, zz_, sg_ in ((P0, K0, zt[0], -1), (P1, K1, zt[1], 1)):   # end caps: no hollow kerb / wall ends
                    oriented_poly(mbd, [v3(E_, min(z(E_), T.h(*E_)) - 0.3), v3(F_, min(z(F_), T.h(*F_)) - 0.3), v3(F_, zz_), v3(E_, zz_)],
                                  v3(dseg_ * sg_, 0), wface)
            n_seg += 1
        # dark modern lamp masts along the castle walks (every ~28 m, none next to an OSM lamp), a bin at every 3rd
        acc = 14.0
        for i in range(len(pts) - 1):
            if not (ok[i] and ok[i + 1]):
                continue
            acc += (pts[i + 1] - pts[i]).length
            if acc < (16.0 if SE_ZONE(pts[i]) else 28.0):   # SE zig-zag walks: closer lamp posts (Earth)
                continue
            acc = 0.0
            q = pts[i] + nrm[i] * (w / 2 + 0.55)
            if any((q - Vector(l_)).length < 12.0 for l_ in LAMPS_KNOWN):
                continue
            LAMPS_KNOWN.append((q.x, q.y))
            z0 = T.h(q.x, q.y)
            _prism(mbd, v3(q, z0 - 0.2), v3(q, z0 + 4.4), 0.07, 0.05, 'stage_dark', seg=6)
            hd = q - nrm[i] * 0.45
            mbd.box([hd - Vector((0.22, 0.1)), hd + Vector((0.22, -0.1)), hd + Vector((0.22, 0.1)), hd + Vector((-0.22, 0.1))],
                    z0 + 4.3, z0 + 4.42, 'stage_dark')
            mbd.box([hd - Vector((0.18, 0.07)), hd + Vector((0.18, -0.07)), hd + Vector((0.18, 0.07)), hd + Vector((-0.18, 0.07))],
                    z0 + 4.27, z0 + 4.3, 'lamp')
            _prism(mbd, v3(q, z0 + 4.36), v3(hd, z0 + 4.36), 0.03, 0.03, 'stage_dark', seg=4)   # arm from the mast to the head
            if hw in ('footway', 'pedestrian') and len(LAMPS_KNOWN) % 2 == 0:      # bench facing the walk
                bq = pts[i] - nrm[i] * (w / 2 + 0.75)
                if abs(T.h(*bq) - T.h(*pts[i])) < 0.25 and not any((bq - Vector(b_)).length < 15.0 for b_ in BENCHES_KNOWN):
                    BENCHES_KNOWN.append((bq.x, bq.y))
                    bench(mbd, bq, (pts[i + 1] - pts[i]).normalized(), nrm[i], T.h(*bq))
            if len(LAMPS_KNOWN) % 3 == 0:
                b_ = q + (pts[i + 1] - pts[i]).normalized() * 0.9
                lathe_up(mbd, b_, T.h(b_.x, b_.y), [(0.0, 0.0), (0.22, 0.0), (0.24, 0.75), (0.26, 0.82), (0.0, 0.84)], 'stage_dark', seg=10)
    return n_seg


# ---------------------------------------------------------------- rotunda foundations by the palace SW corner
RUINS_SW = 1288660862


def low_ruin(mb, T, pts, h=0.18):
    """Excavated foundations (OSM building=ruins, height 0.4) shown as a low pale stone kerb ring round the
    oval lawn (Earth): draped top, short sides."""
    P = ccw(pts)
    tris = geometry.tessellate_polygon([[(p.x, p.y, 0.0) for p in P]])
    for tri in tris:
        q = [P[i] for i in tri]
        oriented_poly(mb, [v3(p, T.h(p.x, p.y) + h) for p in q], UP, 'limestone')
    for k in range(len(P)):
        a, b = P[k], P[(k + 1) % len(P)]
        nout = Vector(((b - a).y, -(b - a).x)).normalized()
        oriented_poly(mb, [v3(a, T.h(a.x, a.y) - 0.15), v3(b, T.h(b.x, b.y) - 0.15), v3(b, T.h(b.x, b.y) + h), v3(a, T.h(a.x, a.y) + h)],
                      v3(nout, 0), 'limestone')


def ruin_outline(mb, T, pts, w=0.7, h=0.4):
    """Excavated foundations in the lawn (Earth E park): low grey rubble outlines, no coping, top draped."""
    P = ccw(pts)
    for k in range(len(P)):
        a, b = P[k], P[(k + 1) % len(P)]
        L = (b - a).length
        if L < 0.2:
            continue
        d = (b - a) / L
        nin = Vector((-d.y, d.x))
        n = max(1, int(L / 1.5))
        for j in range(n):
            p0, p1 = a.lerp(b, j / n) - d * (w / 2 if j == 0 else 0), a.lerp(b, (j + 1) / n) + d * (w / 2 if j == n - 1 else 0)
            q = [p0 - nin * (w / 2), p1 - nin * (w / 2), p1 + nin * (w / 2), p0 + nin * (w / 2)]
            zt = [T.h(c.x, c.y) + h for c in q]
            prism8(mb, q[0], q[1], q[2], q[3], min(zt) - h - 0.4, q[0], q[1], q[2], q[3], 0.0, 'rubble',
                   z1b=(zt[0], zt[1]))


# ---------------------------------------------------------------- Honour Court paving pattern
COURT_AXIS_X = -6.8          # midway between the two OSM flagpoles, through Svätopluk
COURT_DRAINS = (-52.0, -64.0, -76.0)


def court_paving(mb, T, regions, cell=0.25):
    """Honour Court + south terrace: continuous pale granite paving with subtle joint lines on a 6 m grid,
    a pale axis band and narrow cast-iron drains (Earth)."""
    for r in regions:
        drape(mb, T, r, 'pale_paving', 0.075)
        R = [Vector(p[:2]) for p in r]                   # skirt down to the ground: no exposed edges / dark slits
        for a, b in zip(R, R[1:] + R[:1]):
            L = (b - a).length
            for k in range(max(1, int(L / 1.0))):
                p0, p1 = a.lerp(b, k / max(1, int(L / 1.0))), a.lerp(b, (k + 1) / max(1, int(L / 1.0)))
                mb.poly([Vector((p0.x, p0.y, T.h(*p0) - 0.08)), Vector((p1.x, p1.y, T.h(*p1) - 0.08)),
                         Vector((p1.x, p1.y, T.h(*p1) + 0.075)), Vector((p0.x, p0.y, T.h(*p0) + 0.075))], 'pale_paving')
    xs = [p[0] for r in regions for p in r]
    ys = [p[1] for r in regions for p in r]
    x = math.floor(min(xs))
    while x < max(xs):
        y = math.floor(min(ys))
        while y < max(ys):
            cx, cy = x + cell / 2, y + cell / 2
            mat = None
            if any(abs(cy - yd) < 0.13 for yd in COURT_DRAINS) and abs(cx - COURT_AXIS_X) > 1.6:
                mat = 'granite'
            elif abs(abs(cx - COURT_AXIS_X) - 1.6) < 0.13 or (cx - COURT_AXIS_X) % 12.0 < cell or (cy + 40.0) % 12.0 < cell:
                mat = 'paving_band'
            if mat and any(point_in_poly(cx, cy, r) for r in regions):
                q = [(x, y), (x + cell, y), (x + cell, y + cell), (x, y + cell)]
                oriented_poly(mb, [Vector((a, b_, T.h(a, b_) + (0.09 if mat == 'granite' else 0.095))) for a, b_ in q], UP, mat)
            y += cell
        x += cell


# ---------------------------------------------------------------- walkable descents castle -> Old Town
DESCENTS_JSON = 'ref/fortress/descents.json'      # routed over the OSM ways (Zámocké schody, Beblavého, Vienna, Nicholas)


def _seg_x(a, b, c, d):
    """2D segments a-b and c-d intersect."""
    cr = lambda o, p, q: (p.x - o.x) * (q.y - o.y) - (p.y - o.y) * (q.x - o.x)
    d1, d2, d3, d4 = cr(c, d, a), cr(c, d, b), cr(a, b, c), cr(a, b, d)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


WALK_SAMPLES = []           # (xy, z) of the descent walk strips: visible flights are cut to this profile


def descent_ramps(mb, T, feats, routes, width=1.4, step=0.5, grade=0.5, vis=None):
    """Invisible walk strip (-colonly) along each descent: rides 8 cm over the terrain and over the OSM flights
    (linear tread profile), raised wherever needed so it never climbs faster than `grade` -> eye-level walk
    without snags at kerbs, stair heads/feet or terrace-edge steps."""
    flights = []
    for f in feats:
        if f['kind'] == 'road' and f['tags'].get('highway') == 'steps':
            pl = [Vector(q[:2]) for q in f['pts']]
            Ls = [0.0]
            for a, b in zip(pl, pl[1:]):
                Ls.append(Ls[-1] + (b - a).length)
            if Ls[-1] > 0.5:
                flights.append((pl, Ls, T.h(*pl[0]), T.h(*pl[-1])))

    def stair_z(q):
        best = None                                       # nearest leg only: switchback legs lie ~2 m apart
        for pl, Ls, za, zb in flights:
            for i, (a, b) in enumerate(zip(pl, pl[1:])):
                dd = dist_seg(q, a, b)
                if dd < 1.4 and (best is None or dd < best[0]):
                    L = (b - a).length or 1.0
                    t = max(0.0, min(1.0, (q - a).dot(b - a) / (L * L)))
                    best = (dd, za + (zb - za) * (Ls[i] + t * L) / Ls[-1])
        return best and best[1]
    def passage_floor(q):                                 # visible gate floors (floor_strip): walk rides on them
        for _, _, pa, pb, aw, za_, zb_ in GATE_PASSAGES:
            ax_ = pb - pa
            L = ax_.length or 1.0
            ax_ /= L
            t = (q - pa).dot(ax_)
            if -0.5 <= t <= L + 0.5 and abs((q - pa).dot(Vector((-ax_.y, ax_.x)))) <= aw / 2:
                cr = Vector((-ax_.y, ax_.x))
                tt = max(0.0, min(1.0, t / L))
                return max(za_ + (zb_ - za_) * tt, max(T.h(*(q + cr * o)) for o in (-aw / 2, 0.0, aw / 2)) + 0.05)
        return None
    n_r = 0
    zl_ = [Vector(q[:2]) for q in routes.get('zamocke', [])]
    ZAM_LINE = [(c_, e_) for c_, e_ in zip(zl_, zl_[1:]) if max(c_.x, e_.x) > 195.0]
    ZAM_ALL = list(zip(zl_, zl_[1:]))
    WLd = [[Vector(q[:2]) for q in f['pts']] for f in feats if f['kind'] == 'wall']
    WALK_SAMPLES.clear()
    ground = _Ground(T)
    for nm, P in routes.items():
        P = [Vector(q) for q in P]
        pts = []
        for a, b in zip(P, P[1:]):
            k = max(1, int((b - a).length / step))
            pts += [a.lerp(b, i / k) for i in range(k)]
        pts.append(P[-1])
        nrm = []
        for i in range(len(pts)):
            d = pts[min(len(pts) - 1, i + 1)] - pts[max(0, i - 1)]
            d = d.normalized() if d.length > 1e-6 else Vector((1, 0))
            nrm.append(Vector((-d.y, d.x)))
        zs = []
        for q, nn in zip(pts, nrm):
            sz = stair_z(q)
            z = max(ground(*q), min(T.h(*q), sz + 1.0)) if sz is not None else \
                max(max(T.h(*(q + nn * o)) for o in (-width / 2, 0.0, width / 2)),
                    min(max(T.h(*(q + nn * o)) for o in (-1.4, 1.4)), T.h(*q) + 0.25), ground(*q))   # cross-fall: the outer band only lifts a little
            pz_ = path_z(T, q)
            if pz_ is not None:                           # on the kerbed paving: ride 2 cm over it
                z = max(z, pz_ - 0.06)
            pf = passage_floor(q)
            if pf is not None:
                z = max(z, pf - 0.05)
            zs.append(max(z + 0.3 * 0, sz if sz is not None else z) + 0.08)
        gr = [(1.0 if q.x > 266.0 else 0.8) if (nm in ('zamocke', 'beblaveho') and q.x > 228.0) else grade for q in pts]   # Zámocké foot is steep
        for _ in range(3):                               # raise to the grade limit, both directions
            for i in range(1, len(zs)):
                zs[i] = max(zs[i], zs[i - 1] - gr[i] * (pts[i] - pts[i - 1]).length)
            for i in range(len(zs) - 2, -1, -1):
                zs[i] = max(zs[i], zs[i + 1] - gr[i] * (pts[i] - pts[i + 1]).length)
        hw = [width / 2 for q in pts]
        WALK_SAMPLES.extend(zip(pts, zs))

        for i in range(len(pts) - 1):
            q = [pts[i] - nrm[i] * hw[i], pts[i + 1] - nrm[i + 1] * hw[i + 1],
                 pts[i + 1] + nrm[i + 1] * hw[i + 1], pts[i] + nrm[i] * hw[i]]
            oriented_poly(mb, [v3(q[0], zs[i]), v3(q[1], zs[i + 1]), v3(q[2], zs[i + 1]), v3(q[3], zs[i])], UP, 'invisible')
            g0, g1 = T.h(*pts[i]), T.h(*pts[i + 1])
            lower = (nm in ('zamocke', 'beblaveho') and 200.0 < pts[i].x < 229.0 and pts[i].y < -78.0 or   # open hillside / grass path
                     nm == 'nicholas' and pts[i].x > 205.0 and pts[i].y > 60.0) and \
                not any(e_[0] <= pts[i].x <= e_[1] and e_[2] <= pts[i].y <= e_[3] and point_in_poly(pts[i].x, pts[i].y, e)
                        for e, e_ in SFP) and \
                not (nm == 'beblaveho' and any(dist_seg(pts[i], c_, e_) < 1.5 for c_, e_ in ZAM_LINE))   # one ribbon where they share the way
            if vis is not None and (lower or max(zs[i] - g0, zs[i + 1] - g1) > 0.12) and stair_z(pts[i]) is None and passage_floor(pts[i]) is None:     # floating: show a ramped stone walk
                lz = 0.03 if lower else -0.01                 # ribbon over the city's draped grass, not fighting it
                oriented_poly(vis, [v3(q[0], zs[i] + lz), v3(q[1], zs[i + 1] + lz), v3(q[2], zs[i + 1] + lz), v3(q[3], zs[i] + lz)],
                              UP, 'cobbles')
                for a_, b_, nn_ in ((q[0], q[1], -nrm[i]), (q[3], q[2], nrm[i])):
                    oriented_poly(vis, [v3(a_, T.h(*a_) - 0.1), v3(b_, T.h(*b_) - 0.1), v3(b_, zs[i + 1] - 0.01), v3(a_, zs[i] - 0.01)],
                                  v3(nn_, 0), 'rubble')
                    if lower:                            # sett ramp: kerb stones + a gutter along the edge (Fable V4#2)
                        k0, k1 = a_ + nn_ * 0.15, b_ + nn_ * 0.15
                        prism8(vis, a_, b_, k1, k0, zs[i] - 0.25, a_, b_, k1, k0, zs[i] + 0.1, 'stone', z0b=(zs[i] - 0.25, zs[i + 1] - 0.25),
                               z1b=(zs[i] + 0.1, zs[i + 1] + 0.1))
                        g0, g1 = a_ - nn_ * 0.3, b_ - nn_ * 0.3
                        oriented_poly(vis, [v3(g0, zs[i] - 0.005), v3(g1, zs[i + 1] - 0.005), v3(b_, zs[i + 1] - 0.005), v3(a_, zs[i] - 0.005)],
                                      UP, 'stone')
                    if zs[i] - T.h(*(a_ + nn_ * 1.0)) > 0.8 and i % 2 == 0 and i + 2 < len(pts) and \
                            not any(dist_seg(a_, c_, e_) < 1.6 for L_ in WLd for c_, e_ in zip(L_, L_[1:])
                                    if abs(c_.x - a_.x) < 40 and abs(c_.y - a_.y) < 40):   # drop, no parapet: railing
                        if near_any_wall(a_, 0.6) or (nm == 'beblaveho' and any(dist_seg(a_, c_, e_) < 2.0 for c_, e_ in ZAM_ALL)) \
                                or path_z(T, a_ + nn_ * 0.1, pad=0.4) is not None:   # on a kerbed path: its own edge carries it
                            continue                     # passage mouths / the shared Zámocké way: one railing only
                        rl = 'rail_orange' if BEB_ZONE(a_) else 'stage_dark'
                        b2 = pts[i + 2] + nn_ * hw[i]
                        a2_, b3_ = a_ + nn_ * 0.1, b2 + nn_ * 0.1        # just outside the walk, posts down to the ground
                        fa_, fb_ = T.h(*a2_) + 0.1, T.h(*b3_) + 0.1      # draped ground sits up to ~0.3 over T.h
                        rail_seg(vis, a2_, b3_, max(zs[i], fa_) + 1.0, max(zs[i + 2], fb_) + 1.0, fa_, fb_, rl, 'descent', r=0.025, mid=0.5)
        n_r += 1
    return n_r


class _Ground:
    """Height of the built terrain mesh (what the walker stands on), via a BVH of Terrain-col."""
    def __init__(self, T):
        import bpy
        from mathutils.bvhtree import BVHTree
        self.T = T
        ob = bpy.data.objects.get('Terrain-col')
        self.tree = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get()) if ob else None

    def __call__(self, x, y):
        if self.tree:
            hit = self.tree.ray_cast(Vector((x, y, 400.0)), Vector((0, 0, -1)))
            if hit[0] is not None:
                return hit[0].z
        return self.T.h(x, y)


def stepped_flight(mbc, mbd, ground, pl, w, rise=0.16, ds=0.2, rails=True, street=False):
    """A flight that is ON the terrain: tread levels = a monotone envelope of the terrain mesh across the
    flight width (never below the ground -> no terrain poking through, never a riser > `rise`), quantised to
    risers of `rise`; treads collide (walk = what you see).  Kerbs, handrail (rails) or cobble aprons (street)."""
    Ls = [0.0]
    for a, b in zip(pl, pl[1:]):
        Ls.append(Ls[-1] + (b - a).length)
    total = Ls[-1]
    if total < 0.6:
        return
    def at(s_):
        for i in range(len(pl) - 1):
            if s_ <= Ls[i + 1] or i == len(pl) - 2:
                L = max(Ls[i + 1] - Ls[i], 1e-6)
                d = (pl[i + 1] - pl[i]) / L
                return pl[i] + d * (s_ - Ls[i]), d
    n = max(2, int(total / ds))
    S = [total * k / n for k in range(n + 1)]
    Z = []
    for s_ in S:
        q, d = at(s_)
        nn = Vector((-d.y, d.x))
        Z.append(max(ground(*(q + nn * o)) for o in (-0.6, 0.0, 0.6)))     # walking line (banks beside are trimmed)
    down = Z[0] >= Z[-1]                                  # walk the samples from the high end
    idx = list(range(len(S))) if down else list(range(len(S)))[::-1]
    env = [0.0] * len(S)
    m = -1e9
    for i in reversed(idx):                               # suffix max towards the low end: monotone, >= ground
        m = max(m, Z[i])
        env[i] = m
    g = rise / 0.36                                       # treads >= 0.36 m: limit the fall per metre by raising
    for k in range(1, len(idx)):                          # forward along the descent: i is above j
        i, j = idx[k - 1], idx[k]
        env[j] = max(env[j], env[i] - g * abs(S[i] - S[j]))
    zl = env[idx[-1]]
    lev = [zl + math.ceil((e - zl) / rise - 1e-6) * rise for e in env]
    # treads: runs of equal level
    k = 0
    while k < len(S) - 1:
        j = k
        while j + 1 < len(S) - 1 and abs(lev[j + 1] - lev[k]) < 1e-6:
            j += 1
        s0, s1 = S[k], S[j + 1]
        z = lev[k]
        q0, d = at(s0)
        q1, _ = at(s1)
        nn = Vector((-d.y, d.x))
        gmin = min(ground(*q0), ground(*q1))
        mbc.box([q0 - nn * (w / 2), q1 - nn * (w / 2), q1 + nn * (w / 2), q0 + nn * (w / 2)], min(gmin, z) - 0.35, z + 0.02,
                'cobbles' if street else 'stone', top='cobbles' if street else 'stone')
        nose = q0 if down else q1                         # nosing at the step edge
        mbd.box([nose - nn * (w / 2), nose + d * (0.12 if down else -0.12) - nn * (w / 2),
                 nose + d * (0.12 if down else -0.12) + nn * (w / 2), nose + nn * (w / 2)], z - 0.15, z + 0.025, 'limestone')
        k = j + 1
    zf = lambda s_: env[min(range(len(S)), key=lambda i: abs(S[i] - s_))]
    for sg in (-1, 1):                                    # kerbs / aprons / rails along the envelope
        for k in range(0, len(S) - 1, 4):
            k1 = min(k + 4, len(S) - 1)
            q0, d = at(S[k])
            q1, _ = at(S[k1])
            nn = Vector((-d.y, d.x))
            e0, e1 = q0 + nn * (sg * (w / 2 + 0.08)), q1 + nn * (sg * (w / 2 + 0.08))
            z0, z1 = env[k], env[k1]
            if street:
                o0, o1 = q0 + nn * (sg * (w / 2 + 2.6)), q1 + nn * (sg * (w / 2 + 2.6))
                quad(mbd, [v3(e0, ground(*e0) + 0.05), v3(e1, ground(*e1) + 0.05), v3(o1, ground(*o1) + 0.05),
                           v3(o0, ground(*o0) + 0.05)], 'cobbles', want=UP)
                continue
            prism8(mbd, e0 - nn * 0.08, e1 - nn * 0.08, e1 + nn * 0.08, e0 + nn * 0.08, min(z0, z1) - 0.4,
                   e0 - nn * 0.08, e1 - nn * 0.08, e1 + nn * 0.08, e0 + nn * 0.08, z0 + 0.2, 'stone', z1b=z1 + 0.2)
            if rails and 1.0 < S[k] and S[k1] < total - 1.0:
                _prism(mbd, v3(e0, z0 + 0.95), v3(e1, z1 + 0.95), 0.025, 0.025, 'metal', seg=6)
                _prism(mbd, v3(e0, z0 + 0.15), v3(e0, z0 + 0.95), 0.02, 0.02, 'metal', seg=4)
    for a, b in zip(pl, pl[1:]):
        d = (b - a).normalized()
        nn = Vector((-d.y, d.x))
        FLIGHT_FOOTPRINTS.append([tuple(a - nn * (w / 2 + 0.3)), tuple(b - nn * (w / 2 + 0.3)), tuple(b + nn * (w / 2 + 0.3)),
                                  tuple(a + nn * (w / 2 + 0.3))])


def _ray_seg(o, d, a, b):
    """Distance along the 2D ray o + t*d (|d| = 1) to segment a-b, or None."""
    e = b - a
    den = d.x * e.y - d.y * e.x
    if abs(den) < 1e-9:
        return None
    w_ = a - o
    t = (w_.x * e.y - w_.y * e.x) / den
    s_ = (w_.x * d.y - w_.y * d.x) / den
    return t if t > 0 and 0.0 <= s_ <= 1.0 else None


def street_walls(mbc, mbd, T, walls, rise=0.16):
    """The two walls flanking the Zámocké schody (OSM 1309942428/-30): rubble, grey stone coping, a continuous
    sloped top ~1 m over the treads beside them (and 0.3 m over the bank behind), footing below both."""
    for pl in walls:
        pcs = []
        for a, b in zip(pl, pl[1:]):
            L = (b - a).length
            if L < 0.2:
                continue
            n = max(1, int(L / 0.8))
            pcs += [(a.lerp(b, k / n), a.lerp(b, (k + 1) / n)) for k in range(n)]
        tops, bots = [], []
        for p0, p1 in pcs:
            pm = (p0 + p1) / 2
            d = (p1 - p0).normalized()
            nn = Vector((-d.y, d.x))
            near = [t for t in WALK_SAMPLES if (t[0] - pm).length_squared < 49.0]
            zt = min(near, key=lambda t: (t[0] - pm).length_squared)[1] if near else T.h(*pm)
            hs = (T.h(*(pm + nn * 0.8)), T.h(*(pm - nn * 0.8)))
            tops.append(max(zt + 1.0, max(hs) + 0.3))
            bots.append(min(min(hs), zt) - 0.5)
        sm = [sum(tops[max(0, k - 2):k + 3]) / len(tops[max(0, k - 2):k + 3]) for k in range(len(tops))]   # no crenellation
        for k, (p0, p1) in enumerate(pcs):
            d = (p1 - p0).normalized()
            nn = Vector((-d.y, d.x))
            t0 = (sm[k - 1] + sm[k]) / 2 if k > 0 else sm[k]
            t1 = (sm[k] + sm[k + 1]) / 2 if k + 1 < len(sm) else sm[k]
            A0, A1, B1, B0 = p0 - nn * 0.22, p1 - nn * 0.22, p1 + nn * 0.22, p0 + nn * 0.22
            prism8(mbc, A0, A1, B1, B0, bots[k], A0, A1, B1, B0, t0, 'rubble', z1b=t1)
            prism8(mbd, A0 - nn * 0.05, A1 - nn * 0.05, B1 + nn * 0.05, B0 + nn * 0.05, t0,
                   A0 - nn * 0.05, A1 - nn * 0.05, B1 + nn * 0.05, B0 + nn * 0.05, t0 + 0.1, 'stone', z0b=(t0, t1), z1b=(t0 + 0.1, t1 + 0.1))


def strip_flight(mbd, ground, pl, w, rise=0.16, ds=0.2, street=False, others=(), fp_lim=None, fid=None, side_walls=()):
    """Visible flight cut to the walk strip the walker uses (descent_ramps): tread tops = the strip profile rounded
    to `rise` (|walk - tread| <= rise/2), kerbs on the strip line, handrails 0.95 m above it, footing to the ground.
    Returns False when the strip does not follow this flight (then the generic flight stays)."""
    Ls = [0.0]
    for a, b in zip(pl, pl[1:]):
        Ls.append(Ls[-1] + (b - a).length)
    total = Ls[-1]
    if total < 0.6 or not WALK_SAMPLES:
        return False
    def at(s_):
        for i in range(len(pl) - 1):
            if s_ <= Ls[i + 1] or i == len(pl) - 2:
                L = max(Ls[i + 1] - Ls[i], 1e-6)
                d = (pl[i + 1] - pl[i]) / L
                return pl[i] + d * (s_ - Ls[i]), d
    n = max(2, int(total / ds))
    S = [total * k / n for k in range(n + 1)]
    Z, on = [], 0
    for s_ in S:
        q, _ = at(s_)
        best = min(WALK_SAMPLES, key=lambda t: (t[0] - q).length_squared)
        dd = (best[0] - q).length
        on += dd < 0.8
        Z.append(best[1] if dd < 1.5 else None)
    if on < 0.6 * len(S):
        return False
    for i in range(len(Z)):                               # fill the ends from the nearest known value
        if Z[i] is None:
            j = min((k for k in range(len(Z)) if Z[k] is not None), key=lambda k: abs(k - i))
            Z[i] = Z[j]
    if street:                                            # foot: the treads follow the ground down to the street, never above the walk
        for i in range(len(Z)):
            if total - S[i] < 3.5:
                Z[i] = min(Z[i], ground(*at(S[i])[0]) + 0.05)
    if not street:
        flight_bed(mbd, ground, pl, w)
    lev = [round(z / rise) * rise for z in Z]
    k = 0
    while k < len(S) - 1:
        j = k
        while j + 1 < len(S) - 1 and abs(lev[j + 1] - lev[k]) < 1e-6:
            j += 1
        q0, d = at(S[k])
        q1, _ = at(S[j + 1])
        nn = Vector((-d.y, d.x))
        z = lev[k]
        if street and j + 1 >= len(S) - 1:              # foot: the last tread lies flush with the street below
            z = ground(*q1) + 0.03
        gmin = min(ground(*q0), ground(*q1))
        mid_ = (q0 + q1) / 2
        if any(point_in_poly(q0.x, q0.y, fp) and point_in_poly(q1.x, q1.y, fp) for fp in FLIGHT_FOOTPRINTS[:fp_lim]) or \
                (not street and any(i_ != fid and point_in_poly(mid_.x, mid_.y, fp) for i_, fp, st, _ in ROUTE_FP if st)):
            k = j + 1                                     # shared landing with an earlier flight: one surface only
            continue
        hl_ = hr_ = w / 2 + (2.6 if street else 0.0)     # street: treads run out to the side walls / house fronts
        for sw in side_walls:                            # ...and stop at the street's own side walls (one flight between two walls)
            for sg in (-1, 1):
                for c_, e_ in zip(sw, sw[1:]):
                    hit = _ray_seg(mid_, nn * sg, c_, e_)
                    if hit is not None and hit < 6.0:
                        if sg < 0:
                            hl_ = min(hl_, max(w / 2 - 0.6, hit - 0.25))
                        else:
                            hr_ = min(hr_, max(w / 2 - 0.6, hit - 0.25))
        x0_, x1_ = (q0 - d * 0.35, q1 + d * 0.1) if street else (q0 - d * 0.05, q1 + d * 0.05)   # runs overlap: no see-through slots
        mbd.box([x0_ - nn * hl_, x1_ - nn * hl_, x1_ + nn * hr_, x0_ + nn * hr_], min(gmin, z) - 0.3, z,
                'cobbles' if street else 'stone')
        down = lev[j + 1] < z if j + 1 < len(S) else True
        nose = q1 if down else q0
        mbd.box([nose - nn * hl_, nose - d * 0.12 - nn * hl_, nose - d * 0.12 + nn * hr_, nose + nn * hr_]
                if down else [nose - nn * hl_, nose + d * 0.12 - nn * hl_, nose + d * 0.12 + nn * hr_, nose + nn * hr_],
                z - 0.15, z + 0.015, 'limestone')
        k = j + 1
    for sg in (-1, 1):                                    # kerbs + handrails along the strip line, open ends
        for k in range(0, len(S) - 1, 4):
            k1 = min(k + 4, len(S) - 1)
            q0, d = at(S[k])
            q1, _ = at(S[k1])
            nn = Vector((-d.y, d.x))
            e0, e1 = q0 + nn * (sg * (w / 2 + 0.08)), q1 + nn * (sg * (w / 2 + 0.08))
            z0, z1 = Z[k], Z[k1]
            em = (e0 + e1) / 2
            if any(min((e0 - o).length, (e1 - o).length) < 2.2 for o in others) or \
                    any((i_ != fid or abs(dn_.dot(d)) < 0.9) and point_in_poly(em.x, em.y, fp) for i_, fp, st, dn_ in ROUTE_FP):
                continue                                  # no kerb / rail across a landing, another flight or another leg
            if street:                                    # side walls carry the edges (street_walls)
                continue
            qm = (q0 + q1) / 2
            between = any(i_ == fid and abs(dn_.dot(d)) > 0.9 and point_in_poly(em.x, em.y, fp) and not point_in_poly(qm.x, qm.y, fp)
                          for i_, fp, st, dn_ in ROUTE_FP)   # switchback: the parallel leg next door
            bk0, bk1 = ground(*(e0 + nn * (sg * 0.8))), ground(*(e1 + nn * (sg * 0.8)))
            kt0, kt1 = min(max(z0 + 0.2, bk0 + 0.1), z0 + 1.6), min(max(z1 + 0.2, bk1 + 0.1), z1 + 1.6)   # cut bank: retaining wall
            prism8(mbd, e0 - nn * 0.08, e1 - nn * 0.08, e1 + nn * 0.08, e0 + nn * 0.08, min(ground(*e0), ground(*e1), z0, z1) - 0.3,
                   e0 - nn * 0.08, e1 - nn * 0.08, e1 + nn * 0.08, e0 + nn * 0.08, kt0, 'stone' if max(kt0 - z0, kt1 - z1) < 0.45 else 'rubble',
                   z1b=kt1)
            qm = (q0 + q1) / 2
            between = any(i_ == fid and abs(dn_.dot(d)) > 0.9 and point_in_poly(em.x, em.y, fp) and not point_in_poly(qm.x, qm.y, fp)
                          for i_, fp, st, dn_ in ROUTE_FP)   # switchback: the parallel leg next door, no rail over its treads
            if 2.0 < S[k] and S[k1] < total - 2.0 and not between and not near_any_wall(em) and max(kt0 - z0, kt1 - z1) < 0.45:
                rail_seg(mbd, e0, e1, z0 + 0.95, z1 + 0.95, z0 + 0.2, z1 + 0.2, 'metal', 'flight', r=0.025)   # posts on the kerb
    for a, b in zip(pl, pl[1:]):
        d = (b - a).normalized()
        nn = Vector((-d.y, d.x))
        mg = 2.6 if street else 0.3                       # the street's aprons too: no draped grass over them
        FLIGHT_FOOTPRINTS.append([tuple(a - nn * (w / 2 + mg)), tuple(b - nn * (w / 2 + mg)), tuple(b + nn * (w / 2 + mg)),
                                  tuple(a + nn * (w / 2 + mg))])
    return True


def flight_bed(mb, ground, pl, w, mg=0.35):
    """Stone bed strips along both sides of a flight (the ground layer leaves flight footprints empty):
    no bare terrain / lawn edge right against the treads."""
    for a, b in zip(pl, pl[1:]):
        L = (b - a).length
        if L < 1e-3:
            continue
        d = (b - a) / L
        nn = Vector((-d.y, d.x))
        n = max(1, int(L / 1.0))
        for k in range(n):
            q0, q1 = a + d * (L * k / n), a + d * (L * (k + 1) / n)
            for sg in (-1, 1):
                i0, i1 = q0 + nn * (sg * (w / 2 - 0.05)), q1 + nn * (sg * (w / 2 - 0.05))
                o0, o1 = q0 + nn * (sg * (w / 2 + mg)), q1 + nn * (sg * (w / 2 + mg))
                oriented_poly(mb, [v3(i0, ground(*i0) + 0.04), v3(i1, ground(*i1) + 0.04), v3(o1, ground(*o1) + 0.04),
                                   v3(o0, ground(*o0) + 0.04)], UP, 'stone')


def plain_flight(mbd, ground, pl, w, rise=0.16, mbt=None):
    """Flight next to (not on) a descent: visual treads between its terrain end heights, no cheek walls
    (the generic flight's cheek walls blocked the passing walk)."""
    Ls = [0.0]
    for a, b in zip(pl, pl[1:]):
        Ls.append(Ls[-1] + (b - a).length)
    total = Ls[-1]
    if total < 0.6:
        return
    za, zb = ground(*pl[0]), ground(*pl[-1])
    flight_bed(mbd, ground, pl, w)
    n = max(2, int(math.ceil(abs(zb - za) / rise)))
    for i, (a, b) in enumerate(zip(pl, pl[1:])):
        L = (b - a).length
        if L < 1e-3:
            continue
        d = (b - a) / L
        nn = Vector((-d.y, d.x))
        for k in range(int(Ls[i] / total * n), max(int(Ls[i + 1] / total * n), int(Ls[i] / total * n) + 1)):
            t0, t1 = max(0.0, k / n * total - Ls[i]), min(L, (k + 1) / n * total - Ls[i])
            if t1 - t0 < 0.05:
                continue
            zt = za + (zb - za) * ((k + 1) / n if zb > za else k / n)
            q0, q1 = a + d * t0, a + d * t1
            zt = max(zt, max(ground(*(q_ + nn * o_)) for q_ in (q0, q1) for o_ in (-w / 2, 0.0, w / 2)) + 0.03)   # never under the turf
            (mbt or mbd).box([q0 - nn * (w / 2), q1 - nn * (w / 2), q1 + nn * (w / 2), q0 + nn * (w / 2)],
                             min(zt - 0.5, ground(*q0) - 0.2, ground(*q1) - 0.2), zt + 0.02, 'stone')   # treads collide: walk = view


STREET_WALLS = (1309942428, 1309942430)   # walls flanking the Zámocké schody (rebuilt by street_walls)
ROUTE_FP = []               # (way id, footprint quad, is the Zámocké street, leg direction) of all flights on the descents
FLIGHT_FOOTPRINTS = []      # rebuilt flights (city paving should not cover them): v2_fortress.FLIGHT_FOOTPRINTS


def route_flights(mbc, mbd, T, feats, routes, rep):
    """OSM flights on the descents rebuilt ON the terrain mesh (stepped_flight): collidable treads, open ends
    (kerbs and handrails stop short), Zámocké schody as a broad stepped street with cobble aprons."""
    lines = [[Vector(q) for q in P] for P in routes.values()]
    ground = _Ground(T)
    n_f = 0
    FLIGHT_FOOTPRINTS.clear()
    ROUTE_FP.clear()                                     # every rebuilt flight's footprint, known before any is built
    for f in feats:
        if f['kind'] == 'road' and f['tags'].get('highway') == 'steps':
            pl = [Vector(q[:2]) for q in f['pts']]
            probe = pl + [(a + b) / 2 for a, b in zip(pl, pl[1:])]
            if any(dist_seg(m, a, b) < 1.5 for m in probe for L_ in lines for a, b in zip(L_, L_[1:])):
                st = f['id'] == 25117591
                try:
                    w_ = float(f['tags'].get('width', '').split()[0])
                except (ValueError, IndexError):
                    w_ = 2.4
                hw = (4.0 if st else w_) / 2 + (2.6 if st else 0.05)
                for a, b in zip(pl, pl[1:]):
                    if (b - a).length > 1e-6:
                        dn = (b - a).normalized()
                        nn = Vector((-dn.y, dn.x))
                        ROUTE_FP.append((f['id'], [tuple(a - nn * hw), tuple(b - nn * hw), tuple(b + nn * hw), tuple(a + nn * hw)], st, dn))
    ends = [(f['id'], Vector(f['pts'][0][:2])) for f in feats if f['kind'] == 'road' and f['tags'].get('highway') == 'steps'] + \
           [(f['id'], Vector(f['pts'][-1][:2])) for f in feats if f['kind'] == 'road' and f['tags'].get('highway') == 'steps']
    for f in feats:
        if f['kind'] != 'road' or f['tags'].get('highway') != 'steps':
            continue
        pl = [Vector(q[:2]) for q in f['pts']]
        probe = pl + [(a + b) / 2 for a, b in zip(pl, pl[1:])]
        if not any(dist_seg(m, a, b) < 1.5 for m in probe for L_ in lines for a, b in zip(L_, L_[1:])):
            continue
        if f['id'] == 25117591:                          # Zámocké schody: broad stepped street cut to the walk strip
            sw = [[Vector(q[:2]) for q in g['pts']] for g in feats if g['id'] in STREET_WALLS]
            dz_ = (pl[-1] - pl[-2]).normalized()
            pl = pl + [pl[-1] + dz_ * 1.0]               # run out onto the street below: last tread flush with it
            strip_flight(mbd, ground, pl, 4.0, street=True, others=[e for i_, e in ends if i_ != f['id']], fid=f['id'], side_walls=sw)
            street_walls(mbc, mbd, T, sw)
            rep.update(STREET_WALLS)
        else:
            try:
                w = float(f['tags'].get('width', '').split()[0])
            except (ValueError, IndexError):
                w = 2.4
            oth = [e for i_, e in ends if i_ != f['id']]
            legs = list(zip(pl, pl[1:])) if len(pl) > 2 and any(                     # switchbacks: one leg at a time
                abs((b1 - a1).normalized().dot((b2 - a2).normalized())) < 0.5 for (a1, b1), (a2, b2) in zip(zip(pl, pl[1:]), zip(pl[1:], pl[2:]))) else [None]
            okf = False
            n_fp = len(FLIGHT_FOOTPRINTS)
            for lg in legs:
                wl = w
                if lg:                                   # switchback: a leg never overlaps the parallel leg next to it
                    m_ = (lg[0] + lg[1]) / 2
                    dl = (lg[1] - lg[0]).normalized()
                    for a2, b2 in zip(pl, pl[1:]):
                        if (a2, b2) != tuple(lg) and (b2 - a2).length > 1e-6 and abs((b2 - a2).normalized().dot(dl)) > 0.9:
                            wl = min(wl, dist_seg(m_, a2, b2) - 0.25)
                    wl = max(wl, 1.2)
                okf = strip_flight(mbd, ground, list(lg) if lg else pl, wl, others=oth, fp_lim=n_fp, fid=f['id']) or okf
            if not okf:                                  # route only passes by: open visual flight on the terrain
                plain_flight(mbd, ground, pl, w, mbt=mbc)
        rep.add(f['id'])
        n_f += 1
    try:
        json.dump([[list(map(float, q)) for q in fp] for fp in FLIGHT_FOOTPRINTS],
                  open(os.path.join(H_DATA[0], 'ref/fortress/flight_footprints.json'), 'w'))
    except (OSError, IndexError):
        pass
    return n_f


# ---------------------------------------------------------------- Námestie A. Dubčeka (bus area W of the castle)
DUBCEK_SQUARE = 96701720


def dubcek_square(mb, T, pts):
    """Paved square by the parliament where the castle buses turn (Earth ge_west_gates / ge_top): pale paving
    with a field of red stone discs, bollards along the edge."""
    P = [tuple(p[:2]) for p in pts]
    drape(mb, T, P, 'pale_paving', 0.3)               # above the city ground meshes draped there
    xs, ys = [p[0] for p in P], [p[1] for p in P]
    inner = offset_poly(P if poly_area(P) > 0 else P[::-1], -2.0)
    x = min(xs) + 2.0
    n = 0
    while x < max(xs):
        y = min(ys) + 2.0
        while y < max(ys):
            if point_in_poly(x, y, inner):
                ring = [(x + 0.9 * math.cos(2 * math.pi * k / 20), y + 0.9 * math.sin(2 * math.pi * k / 20)) for k in range(20)]
                oriented_poly(mb, [Vector((a, b_, T.h(a, b_) + 0.31)) for a, b_ in ring], UP, 'paving_red')
                n += 1
            y += 3.4
        x += 3.4
    return n


# ---------------------------------------------------------------- Honour Court furniture (refs 04/05/06/08, Earth)
VICTORY_GATES = [((34.1, -60.5), (1.0, 0.0)), ((-39.3, -50.9), (-1.0, -0.08))]   # where the walks cross the court edges
INFO_BOARDS = [((-110.0, -37.4), (0.7, -0.7)), ((128.5, -121.0), (1.0, 0.0)), ((-20.0, -73.0), (0.0, -1.0))]


def victory_gate(mbc, mbd, H, T, c, d):
    """Victory (Winning) Gate of the Honour Court (ref 08): white rusticated piers, flat-headed opening with an
    eared surround, cornice, segmental pediment and trophies of arms on the piers."""
    c, d = Vector(c), Vector(d).normalized()
    n = Vector((-d.y, d.x))
    z = T.h(c.x, c.y)
    ow, oh = 3.4, 4.0
    for s_ in (-1, 1):
        q = c + n * (s_ * (ow / 2 + 0.55))
        prism8(mbc, q - n * 0.55 - d * 0.55, q + n * 0.55 - d * 0.55, q + n * 0.55 + d * 0.55, q - n * 0.55 + d * 0.55, z - 0.5,
               q - n * 0.55 - d * 0.55, q + n * 0.55 - d * 0.55, q + n * 0.55 + d * 0.55, q - n * 0.55 + d * 0.55, z + oh + 0.9,
               'plaster_lime')
        for k in range(int(oh / 0.55)):                  # rustication bands: white (ref 08), stone plinth course
            zz = z + 0.3 + k * 0.55
            prism8(mbd, q - n * 0.6 - d * 0.6, q + n * 0.6 - d * 0.6, q + n * 0.6 + d * 0.6, q - n * 0.6 + d * 0.6, zz,
                   q - n * 0.6 - d * 0.6, q + n * 0.6 - d * 0.6, q + n * 0.6 + d * 0.6, q - n * 0.6 + d * 0.6, zz + 0.42,
                   'limestone' if k == 0 else 'plaster_lime')
        H['trophy'](mbd, q, z + oh + 1.35, d, ped=0.45)
    L0, L1 = c - n * (ow / 2 + 1.1), c + n * (ow / 2 + 1.1)
    prism8(mbc, L0 - d * 0.5, L1 - d * 0.5, L1 + d * 0.5, L0 + d * 0.5, z + oh, L0 - d * 0.5, L1 - d * 0.5, L1 + d * 0.5, L0 + d * 0.5,
           z + oh + 0.9, 'plaster_lime')
    for s_ in (-1, 1):
        sweep(mbd, L0, L1, [(0.0, 0.0), (0.12, 0.05), (0.2, 0.18), (0.32, 0.3), (0.32, 0.42), (0.0, 0.42)], z + oh + 0.9, 'limestone', d * s_)
    for j in range(12):                                  # segmental pediment
        t0, t1 = math.pi * j / 12, math.pi * (j + 1) / 12
        r = ow / 2 + 1.1
        p0, p1 = c - n * (r * math.cos(t0)), c - n * (r * math.cos(t1))
        z0_, z1_ = z + oh + 1.32 + 0.6 * math.sin(t0), z + oh + 1.32 + 0.6 * math.sin(t1)
        prism8(mbd, p0 - d * 0.4, p1 - d * 0.4, p1 + d * 0.4, p0 + d * 0.4, z + oh + 1.3, p0 - d * 0.4, p1 - d * 0.4, p1 + d * 0.4,
               p0 + d * 0.4, z0_, 'plaster_lime', z1b=z1_)


def info_board(mb, T, c, face):
    """Visitor information board at a castle entrance: two dark posts, a framed panel."""
    c, face = Vector(c), Vector(face).normalized()
    sd = Vector((-face.y, face.x))
    z = T.h(c.x, c.y)
    for s_ in (-1, 1):
        q = c + sd * (s_ * 0.6)
        _prism(mb, v3(q, z - 0.1), v3(q, z + 2.0), 0.04, 0.04, 'stage_dark', seg=6)
    a, b = c - sd * 0.62, c + sd * 0.62
    prism8(mb, a, b, b - face * 0.06, a - face * 0.06, z + 1.0, a, b, b - face * 0.06, a - face * 0.06, z + 1.95, 'stage_dark')
    quad(mb, [v3(a + face * 0.01 + sd * 0.05, z + 1.07), v3(b + face * 0.01 - sd * 0.05, z + 1.07),
              v3(b + face * 0.01 - sd * 0.05, z + 1.88), v3(a + face * 0.01 + sd * 0.05, z + 1.88)], 'plaque', want=v3(face, 0))


def bollards(mb, T, pts, step=2.2):
    P = [Vector(p[:2]) for p in pts]
    for a, b in zip(P, P[1:]):
        L = (b - a).length
        for k in range(int(L / step)):
            q = a.lerp(b, (k + 0.5) / max(1, int(L / step)))
            z = T.h(q.x, q.y) + 0.3
            lathe_up(mb, q, z - 0.2, [(0.0, 0.0), (0.1, 0.0), (0.1, 0.72), (0.06, 0.82), (0.0, 0.84)], 'stage_dark', seg=8)


def gate_passage_details(mbd, coll, items):
    """Lanterns hanging in the gate passages and worn limestone thresholds at the mouths."""
    for c, zc, a, b, w, za, zb in items:
        lantern(mbd, c, zc, zc - 0.9, r=0.16)
        add_light(coll, 'L_gate_passage', (c.x, c.y, zc - 0.8), 45, color=(1.0, 0.78, 0.5))
        d = (b - a).normalized()
        n = Vector((-d.y, d.x))
        for p_, z_ in ((a, za), (b, zb)):
            prism8(mbd, p_ - n * (w / 2) - d * 0.35, p_ + n * (w / 2) - d * 0.35, p_ + n * (w / 2) + d * 0.35, p_ - n * (w / 2) + d * 0.35,
                   z_ - 0.1, p_ - n * (w / 2) - d * 0.35, p_ + n * (w / 2) - d * 0.35, p_ + n * (w / 2) + d * 0.35,
                   p_ - n * (w / 2) + d * 0.35, z_ + 0.06, 'limestone')


# ---------------------------------------------------------------- entry
POINTS = []
H_DATA = []
GATE_PASSAGES = []          # (lantern xy, ceiling z, mouth a, mouth b, width, z at a, z at b) collected by the gate builders


FORT_UV = {'rubble': 0.8, 'rubble_light': 0.5, 'ashlar': 0.6, 'stone': 1.0, 'limestone': 0.6, 'rustica': 1.2}   # Fable V4 10: stones 3x smaller


def build(H, T, feats, points, coll):
    _bind(H)
    materials()
    MU = H['MAT_UV']
    saved = dict(MU)
    try:
        MU.update(FORT_UV)                               # UVs are baked per polygon: only the fortress geometry
        return _build(H, T, feats, points, coll)
    finally:
        MU.clear()
        MU.update(saved)


def _build(H, T, feats, points, coll):
    _bind(H)
    RAILS.clear()
    WALL_LINES[:] = [[Vector(q[:2]) for q in f['pts']] for f in feats if f['kind'] == 'wall']
    POINTS[:] = points
    H_DATA[:] = [H['DATA']]
    H_OUT[:] = [H['OUT']]
    try:
        DESCENT_LINES[:] = [[Vector(q) for q in P] for P in json.load(open(os.path.join(H['DATA'], DESCENTS_JSON))).values()]
    except (OSError, ValueError):
        DESCENT_LINES[:] = []
    GATE_PASSAGES.clear()
    materials()
    rep = H['REPLACED_IDS']
    before = set(rep)
    F = {f['id']: f for f in feats}
    mbc = ChunkMB('Fort_Walls-col', tile=80.0)
    mbd = ChunkMB('Fort_Detail', tile=80.0)
    gc = MB('Fort_Gates-col')
    ramps = MB('Fort_Ramps-colonly')
    gd = MB('Fort_Gates_Detail')
    # south terrace paving up to the arcade wall, lower court paving (lawns kept), amphitheatre
    lawns = [f['pts'] for f in feats if f['kind'] == 'area' and f['tags'].get('landuse') == 'grass']
    drape(gc, T, S_TERRACE, 'cobbles', 0.06)
    drape(gc, T, LOWER_COURT, 'pale_paving', 0.06)      # textured paving; the lawns lie on top with clean edges
    for lw in lawns:
        if any(point_in_poly(q[0], q[1], LOWER_COURT) for q in lw):
            drape_poly(gc, T, lw, 'grass', 0.12, maxe=1.0)
    amphitheatre(gc, gd)
    court_paving(gc, T, [H['HONOUR_COURT'], S_TERRACE])     # collidable: the court floor is what you walk on
    bc = MB('Fort_Buildings-col')
    bd = MB('Fort_Buildings_Detail')
    garden_poly = next((f['pts'] for f in feats if f['tags'].get('name') == 'Baroková záhrada'), None)
    castle_area = next((f['pts'] for f in feats if f['tags'].get('name') == 'Bratislavský hrad'), None)
    area = offset_poly(castle_area, 30.0) if castle_area else None
    roads = [f for f in feats if f['kind'] == 'road']
    step_lines = []
    for f in roads:
        if f['tags'].get('highway') != 'steps':
            continue
        try:
            wdt = float(f['tags'].get('width', '2.5').split()[0])
        except ValueError:
            wdt = 2.5
        step_lines.append(([Vector(p) for p in f['pts']], wdt))

    way_lines = [[Vector(p[:2]) for p in f['pts']] for f in roads if (f['tags'].get('highway') in PATH_W or f['tags'].get('highway') == 'steps')
                 and f['tags'].get('area') != 'yes']

    def near_way(q, piece=None):
        if piece is not None:                            # does a way cross this wall piece?
            return any(dist_seg(q, a, b) < 4.0 and _seg_x(piece[0], piece[1], a, b) for pl in way_lines for a, b in zip(pl, pl[1:]))
        return any(dist_seg(q, a, b) < 2.4 for pl in way_lines for a, b in zip(pl, pl[1:]))

    def near_steps(q):
        return any(min(dist_seg(q, a, b) for a, b in zip(pl, pl[1:])) < w / 2 + 0.4 for pl, w in step_lines)
    # ---- walls inside / around the castle grounds
    garden_off = offset_poly(garden_poly, 2.0) if garden_poly else None
    n_w = 0
    piece_no = [0]
    for f in feats:
        if f['kind'] != 'wall' or f['id'] in getattr(T, 'garden_wall_ids', ()) or f['id'] in STREET_WALLS:
            continue                                     # garden walls: v2_garden (continuous balustrades)
        if f['id'] == ARCADE_WALL:
            # only the terrace wall proper: the short return along the Zámocké descent (E of (26.8,-78)) is left out,
            # its body crowded the walk there (Godot capsule stuck at (26.7,-78))
            pw = [q for q in f['pts']]
            cut_i = min(range(len(pw)), key=lambda i: (pw[i][0] - 26.8) ** 2 + (pw[i][1] + 78.0) ** 2)
            pw = [Vector(q[:2]) for q in pw[:cut_i + 1]]
            pw[-1] = pw[-1] + (pw[-2] - pw[-1]).normalized() * 2.2     # wall stops 2.2 m short: open passage
            arcade_wall(gc, gd, T, pw, way_lines)
            rep.add(f['id'])
            continue
        cxy = Vector(f['pts'][len(f['pts']) // 2][:2])
        if area and not point_in_poly(cxy.x, cxy.y, area):
            continue
        castle = f['tags'].get('wall') == 'castle_wall' or f['tags'].get('barrier') == 'retaining_wall'
        fort_wall(mbc, mbd, T, [Vector(p[:2]) for p in f['pts']], castle, near_steps, garden_off, piece_no, near_way)
        rep.add(f['id'])
        n_w += 1
    # ---- gates and bastions
    if VIENNA in F:
        vienna_gate(gc, gd, T, F[VIENNA]['pts'], passage_axis(roads, F[VIENNA]['pts']), coll)
        rep.add(VIENNA)
    if SIGISMUND in F:
        sigismund_gate(gc, gd, T, F[SIGISMUND]['pts'], passage_axis(roads, F[SIGISMUND]['pts']))
        rep.add(SIGISMUND)
    if NICHOLAS in F:
        nicholas_gate(gc, gd, T, F[NICHOLAS]['pts'], passage_axis(roads, F[NICHOLAS]['pts']), ramps)
        rep.add(NICHOLAS)
    # The Leopold bastion lawn and the terrace block 1128350262 north of it share an edge; the lawn is set
    # flush with the terrace (DMR at its centre) so the Honour Court - terrace - lawn walk is level.
    shared = (Vector((-46.4, -92.8)), Vector((-27.6, -89.5)), 1.0)
    t_top = None
    if LEOPOLD_TERRACE in F:
        P = ccw(F[LEOPOLD_TERRACE]['pts'])
        cx = sum(P, Vector((0, 0))) / len(P)
        t_top = T.raw(cx.x, cx.y) - T.z0 + 0.05
        bastion(gc, gd, T, F[LEOPOLD_TERRACE]['pts'], t_top, near_steps=near_steps, gaps=[shared])
        rep.add(LEOPOLD_TERRACE)
    if LEOPOLD_BASTION in F:
        top = t_top if t_top is not None else -1.5      # lawn terrace (ref 26), ~8 m above the passage
        pas = None
        if LEOPOLD_PASSAGE in F:
            pp = F[LEOPOLD_PASSAGE]['pts']
            a, b = Vector(pp[0][:2]), Vector(pp[-1][:2])
            if a.x > b.x:
                a, b = b, a                              # portal on the west (outer) end
            crown = leopold_gate(gc, gd, T, a, b, coll)
            pas = (a, b, 3.2, crown)
        bastion(gc, gd, T, F[LEOPOLD_BASTION]['pts'], top, passage=pas, turret_at=Vector((-51.0, -126.2)),
                near_steps=near_steps, gaps=[shared])
        rep.add(LEOPOLD_BASTION)
    # ---- castle-area buildings
    if HOUSE_BASTION in F:
        gabled_house(bc, bd, T, F[HOUSE_BASTION]['pts'], 2, 'rubble_light', roof_h=4.2)    # stone elevations (Earth)
        rep.add(HOUSE_BASTION)
    if STABLES in F:           # N stables row (Earth ph_zamocka_mid): white single storey, a row of cross gables
        stables_row(bc, bd, T, F[STABLES]['pts'])
        rep.add(STABLES)
    if RIDING_SCHOOL in F:     # Winter Riding School: one tall storey, round-arched windows, big ~43 deg hipped roof
        # (a 34 deg roof vanished behind the eave when seen from the garden at eye height, ref 11/12)
        gabled_house(bc, bd, T, F[RIDING_SCHOOL]['pts'], 2, 'plaster_lime', rubble_base=False, arched=True,
                     dormers=True, roof_h=9.0, hipped=True, floor_h=3.7, window_w=1.4, spacing=4.2)   # Earth N/NE/E
        rep.add(RIDING_SCHOOL)
    # kerbed paths over the grounds (outside the courts, terraces, garden and buildings)
    excl = [S_TERRACE, LOWER_COURT, WC_COURT] + ([garden_poly] if garden_poly else [])
    for gid, aw in ((SIGISMUND, 3.4), (NICHOLAS, 2.8)):       # gate passages carry their own floors
        if gid in F:
            excl.append(gate_passage_rect(T, F[gid]['pts'], passage_axis(roads, F[gid]['pts']), aw, gid == NICHOLAS, extra=2.4)[0])
    if VIENNA in F:
        excl.append([tuple(p[:2]) for p in F[VIENNA]['pts']])
    if area:
        ax0, ax1 = min(p[0] for p in area) - 5, max(p[0] for p in area) + 5
        ay0, ay1 = min(p[1] for p in area) - 5, max(p[1] for p in area) + 5
        near_a = lambda f: any(ax0 < q[0] < ax1 and ay0 < q[1] < ay1 for q in f['pts'])
        excl += [f['pts'] for f in feats if f['kind'] in ('building', 'part') and near_a(f)]
        excl += [f['pts'] for f in feats if f['kind'] == 'road' and f['tags'].get('area') == 'yes' and near_a(f)]
    pmb, pmd = ChunkMB('Fort_Paths-col', tile=80.0), ChunkMB('Fort_Kerbs', tile=80.0)
    n_p = ground_paths(pmb, pmd, T, feats, area, excl) if area else 0
    shelf_walls(pmb, T, getattr(T, 'shelves', []))       # (edge a, edge b, outward normal, z a, z b) from path_trenches
    print('v2_fortress: path segments', n_p)
    for f in feats:                                      # excavated foundations in the lawns of the grounds
        if f['id'] != RUINS_SW and f['tags'].get('building') == 'ruins' and area and point_in_poly(*f['pts'][0][:2], area):
            ruin_outline(bd, T, f['pts'])
            rep.add(f['id'])
    if DUBCEK_SQUARE in F:
        print('v2_fortress: Dubcek square discs', dubcek_square(gd, T, F[DUBCEK_SQUARE]['pts']))
        bollards(gd, T, F[DUBCEK_SQUARE]['pts'])
    for c_, d_ in VICTORY_GATES:
        victory_gate(gc, gd, H, T, c_, d_)
    for c_, f_ in INFO_BOARDS:
        info_board(gd, T, c_, f_)
    gate_passage_details(gd, coll, GATE_PASSAGES)
    if RUINS_SW in F:
        low_ruin(bd, T, F[RUINS_SW]['pts'])
        rep.add(RUINS_SW)
    dpath = os.path.join(H['DATA'], DESCENTS_JSON)
    if os.path.exists(dpath):
        routes = json.load(open(dpath))
        n_d = descent_ramps(ramps, T, feats, routes, vis=gd)    # first: the flights take their treads from the strip
        n_f = route_flights(gc, gd, T, feats, routes, rep)
        print('v2_fortress: descent walk strips', n_d, 'flights rebuilt', n_f)
    if WEST_COURT in F:
        west_court(H, bc, bd, T, F[WEST_COURT]['pts'])
        rep.add(WEST_COURT)
    if NORTH_WALLS in F:
        gcen = None
        if garden_poly:
            gp = ccw(garden_poly)
            gcen = sum(gp, Vector((0, 0))) / len(gp)
        north_walls(bc, bd, T, F[NORTH_WALLS]['pts'], gcen)
        rep.add(NORTH_WALLS)
    import v2_garden                                     # garden terrace walls (edges found in Terrain.set_garden)
    finish_rails()
    obs = mbc.build(coll) + mbd.build(coll) + pmb.build(coll) + pmd.build(coll) + [m.build(coll) for m in (gc, gd, bc, bd, ramps)] + v2_garden.build(H, T, coll, feats, rep)
    print('v2_fortress: walls', n_w, 'replaced', sorted(rep - before), 'polys', sum(len(o.data.polygons) for o in obs))
    return obs
