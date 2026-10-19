"""Landmarks modelled from photo references (data/ref/landmarks/<name>/: photos, FACTS.md).

Called from v2_city.py through _lm(); every builder returns a list of built objects.
  snp(...)       Most SNP: leaning A-pylon, head block, UFO, two planes of stays (3 + back-stay per side)
  snp_deck(...)  Most SNP steel box-girder fascia with the hung walkways (after the city roads are laid)
"""
import math
import os

import numpy as np

SNP_OUTLINE = 238810163          # man_made=bridge outline of the whole structure
SNP_LEGS = (123233334, 123233335)


# ---------------------------------------------------------------- materials
def _materials(H):
    MATS, make_mat = H['MATS'], H['make_mat']
    if 'lm_steel' in MATS:
        return
    tx = H['textures']
    n = 256
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:n, 0:n] / n
    # SNP paint: off-white steel with rust runs from the top edge (photos: snp_side_view_a, snp_underside_deck)
    base = np.ones((n, n, 3)) * np.array((0.86, 0.86, 0.83))
    runs = np.zeros((n, n))
    for _ in range(40):
        x0 = rng.integers(0, n)
        w = rng.integers(1, 4)
        ln = rng.uniform(0.15, 0.6)
        runs[:, x0:x0 + w] += np.clip(1.0 - (1.0 - yy[:, x0:x0 + w]) / ln, 0, 1) * rng.uniform(0.3, 0.8)
    runs = np.clip(runs, 0, 1)
    rust = np.array((0.55, 0.38, 0.24))
    img = base * (1 - runs[..., None] * 0.45) + rust * runs[..., None] * 0.45
    img += tx.fbm(n, rng, octaves=(8, 32))[..., None] * 0.04 - 0.02
    make_mat('lm_steel', tx._save(os.path.join(H['TEX'], 'lm_steel.png'), np.clip(img, 0, 1)), uv=6.0, rough=0.6)
    rus = np.ones((n, n, 3)) * np.array((0.80, 0.70, 0.55)) + tx.fbm(n, rng, octaves=(8, 32))[..., None] * 0.06 - 0.03
    rus[(np.arange(n) % 64) < 4, :] *= 0.62                       # 0.5 m rustication courses
    make_mat('lm_rustic', tx._save(os.path.join(H['TEX'], 'lm_rustic.png'), np.clip(rus, 0, 1)), uv=2.0, rough=0.85)
    dia = np.zeros((n, n, 3))
    yy2, xx2 = np.mgrid[0:n, 0:n]
    cell = ((xx2 + yy2) // 32 + (xx2 - yy2 + n) // 32) % 3          # diagonal checker of glazed tiles
    for k, col in enumerate(((0.78, 0.76, 0.80), (0.55, 0.25, 0.45), (0.70, 0.22, 0.20))):
        dia[cell == k] = col
    make_mat('lm_glazed', tx._save(os.path.join(H['TEX'], 'lm_glazed.png'), dia), uv=1.2, rough=0.35)
    make_mat('lm_white', None, color=(0.84, 0.85, 0.84), rough=0.45)
    make_mat('lm_ufo', None, color=(0.55, 0.57, 0.58), rough=0.35, metal=0.6)
    make_mat('lm_dark', None, color=(0.04, 0.04, 0.045), rough=0.8)
    make_mat('lm_ufo_glass', None, color=(0.015, 0.02, 0.025), rough=0.25, metal=0.0)
    # walkway mesh screen: dark gap behind vertical bars
    mesh = np.ones((n, n, 3)) * 0.12
    mesh[:, (np.arange(n) % 16) < 3] = 0.75
    mesh[(np.arange(n) % 128) < 6, :] = 0.8
    make_mat('lm_screen', tx._save(os.path.join(H['TEX'], 'lm_screen.png'), mesh), uv=2.0, rough=0.7)


# ---------------------------------------------------------------- geometry helpers
def _frame(Vector, d, hint):
    d = d.normalized()
    s = d.cross(hint)
    if s.length < 1e-6:
        s = d.cross(Vector((1, 0, 0)))
    s.normalize()
    t = s.cross(d).normalized()
    return s, t


def _beam(mb, Vector, p0, p1, w0, d0, w1, d1, mat, hint):
    """Tapered rectangular member p0 -> p1: width w along `hint` x axis, depth d across."""
    s, t = _frame(Vector, p1 - p0, hint)
    def ring(p, w, d):
        return [p + s * (w / 2) * a + t * (d / 2) * b for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    A, B = ring(p0, w0, d0), ring(p1, w1, d1)
    for k in range(4):
        j = (k + 1) % 4
        q = [A[k], A[j], B[j], B[k]]
        c = sum(q, Vector((0, 0, 0))) / 4
        mid = (p0 + p1) / 2
        if H_normal(q).dot(c - mid) < 0:
            q.reverse()
        mb.poly(q, mat)
    mb.poly(list(reversed(A)), mat)
    mb.poly(B, mat)


def H_normal(q):
    from mathutils import geometry
    return geometry.normal(q)


def _lathe(mb, Vector, c, prof, mat_of, seg=40):
    """Surface of revolution about the vertical through c: prof = [(radius, z), ...] top-down or bottom-up."""
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        mat = mat_of(r0, z0, r1, z1)
        for k in range(seg):
            a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
            p = [Vector((c.x + math.cos(a0) * r0, c.y + math.sin(a0) * r0, z0)),
                 Vector((c.x + math.cos(a1) * r0, c.y + math.sin(a1) * r0, z0)),
                 Vector((c.x + math.cos(a1) * r1, c.y + math.sin(a1) * r1, z1)),
                 Vector((c.x + math.cos(a0) * r1, c.y + math.sin(a0) * r1, z1))]
            if r0 < 1e-3:
                p = [p[0], p[2], p[3]]
            elif r1 < 1e-3:
                p = [p[0], p[1], p[2]]
            out = Vector((math.cos((a0 + a1) / 2), math.sin((a0 + a1) / 2), 0))
            nrm = H_normal(p)
            # outward/upward: radial for walls, +z for flat tops, -z for undersides
            want = out * (abs(z1 - z0) + 1e-3) + Vector((0, 0, (r0 - r1)))
            if nrm.dot(want) < 0:
                p.reverse()
            mb.poly(p, mat)


def _axis(H, misc):
    """Bridge axis from the OSM outline: (centre, unit u pointing to the Old Town bank, outline pts)."""
    import v2_city as C
    Vector = H['Vector']
    for e in misc['elements']:
        if e['type'] == 'way' and e['id'] == SNP_OUTLINE and e.get('geometry'):
            P = [Vector(p) for p in C._ring_xy(H, e['geometry'])]
            c0 = sum(P, Vector((0, 0))) / len(P)
            sxx = sum((p.x - c0.x) ** 2 for p in P)
            syy = sum((p.y - c0.y) ** 2 for p in P)
            sxy = sum((p.x - c0.x) * (p.y - c0.y) for p in P)
            a = 0.5 * math.atan2(2 * sxy, sxx - syy)
            u = Vector((math.cos(a), math.sin(a)))
            if u.y < 0:                          # the Old Town is north of the river
                u = -u
            return c0, u, P
    return None


# ---------------------------------------------------------------- Most SNP
def snp(H, special, G, coll, misc, SNP):
    """Pylon (A-legs leaning back to Petrzalka), head block, UFO, stays. Fills SNP['top'/'deck'/'u']."""
    if not all(k in special for k in SNP_LEGS):
        return []
    _materials(H)
    Vector, MB = H['Vector'], H['MB']
    ax = _axis(H, misc)
    legs = [special[k] for k in SNP_LEGS]
    F = [Vector((cx, cy)) for t, r, cx, cy in legs]
    gl = min(G(f.x, f.y) for f in F)
    mid = (F[0] + F[1]) / 2
    if ax:
        c0, u, P = ax
    else:
        u = Vector((0, 1))
    v = Vector((-u.y, u.x))
    deck = G.water + 11.5
    SNP['deck'], SNP['u'], SNP['foot'] = deck, u, mid
    mb = MB('V2LM_SNP_Pylon')
    up = Vector((0, 0, 1))
    # 84.6 m pylon: legs meet ~18 m behind the footings (toward Petrzalka); head block 66-76 m,
    # UFO underside from 76 m, glazed restaurant ring, roof terrace at ~85 m above the footings (95 m above the river)
    head = Vector((*(mid - u * 18.0), gl + 70.0))
    hint = Vector((*u, 0))
    for f in F:
        sgn = 1 if (f - mid).dot(v) > 0 else -1
        foot = Vector((f.x, f.y, G(f.x, f.y) - 1.0))
        top = head + Vector((*(v * sgn * 1.6), 0))
        _beam(mb, Vector, foot, top, 5.2, 7.5, 3.0, 4.2, 'lm_white', hint)     # photo: massive tapering legs
    # crossbeam carrying the deck between the legs
    for k_, z_ in enumerate((deck - 5.0,)):
        t_ = (z_ - (gl - 1)) / (head.z - (gl - 1))
        pa = Vector((F[0].x, F[0].y, gl - 1)).lerp(head, t_)
        pb = Vector((F[1].x, F[1].y, gl - 1)).lerp(head, t_)
        _beam(mb, Vector, pa, pb, 3.0, 2.2, 3.0, 2.2, 'lm_white', up)
    # head block (lift machinery) and the short shaft under the saucer
    _beam(mb, Vector, head - Vector((0, 0, 6.0)), head + Vector((0, 0, 4.5)), 7.5, 5.0, 6.0, 4.2, 'lm_white', hint)
    c = head + Vector((0, 0, 4.5))
    # UFO saucer (FACTS: ~32 m across): shallow cone underside, dark glazed ring, sloped roof, terrace + kiosk
    prof = [(2.8, c.z), (8.0, c.z + 2.2), (15.2, c.z + 4.6), (16.2, c.z + 5.2), (16.4, c.z + 7.6),
            (15.6, c.z + 8.1), (11.0, c.z + 9.6), (0.0, c.z + 9.6)]
    def mat_of(r0, z0, r1, z1):
        if abs(r0 - 16.2) < 0.01 and abs(r1 - 16.4) < 0.01:
            return 'lm_ufo_glass'
        return 'lm_ufo'
    _lathe(mb, Vector, c, prof, mat_of)
    for k in range(64):                          # glazing mullions round the restaurant ring
        a0 = 2 * math.pi * k / 64
        p0 = Vector((c.x + math.cos(a0) * 16.42, c.y + math.sin(a0) * 16.42))
        H['_prism'](mb, Vector((*p0, c.z + 5.2)), Vector((*p0, c.z + 7.6)), 0.07, 0.07, 'lm_ufo', seg=4)
    tz = c.z + 9.6
    H['seg_box'](mb, Vector((c.x - 3.5, c.y)), Vector((c.x + 3.5, c.y)), -3.0, 3.0, tz, tz + 3.0, 'lm_white')
    for k in range(48):                          # terrace railing posts + rail ring
        a0, a1 = 2 * math.pi * k / 48, 2 * math.pi * (k + 1) / 48
        p0 = Vector((c.x + math.cos(a0) * 10.7, c.y + math.sin(a0) * 10.7))
        p1 = Vector((c.x + math.cos(a1) * 10.7, c.y + math.sin(a1) * 10.7))
        H['_prism'](mb, Vector((*p0, tz)), Vector((*p0, tz + 1.1)), 0.04, 0.04, 'metal', seg=4)
        H['seg_box'](mb, p0, p1, -0.03, 0.03, tz + 1.05, tz + 1.12, 'metal')
    H['_prism'](mb, Vector((c.x, c.y, tz + 3.0)), Vector((c.x, c.y, tz + 8.0)), 0.15, 0.06, 'metal', seg=6)
    SNP['top'] = head
    out = [mb.build(coll)]
    # stays: two cable planes at the deck edges, three into the main span + one back-stay per side
    sb = MB('V2LM_SNP_Stays')
    dmid = mid + u * 0.0
    for sgn in (-1, 1):
        for k, (dist, hz) in enumerate(((78.0, -2.0), (158.0, 0.0), (240.0, 2.0))):
            a = head + Vector((*(v * sgn * 2.4), hz))
            q = dmid + u * dist + v * sgn * 10.4
            b = Vector((q.x, q.y, deck_z(SNP, q, deck) + 0.4))
            H['_prism'](sb, a, b, 0.42, 0.42, 'lm_white', seg=6)
        a = head + Vector((*(v * sgn * 2.4), 1.0))
        q = mid - u * 48.0 + v * sgn * 9.0
        H['_prism'](sb, a, Vector((q.x, q.y, G(q.x, q.y) + 0.5)), 0.42, 0.42, 'lm_white', seg=6)
        H['seg_box'](sb, q - u * 2.0, q + u * 2.0, -1.5, 1.5, G(q.x, q.y) - 0.5, G(q.x, q.y) + 1.2, 'concrete')   # anchor block
    out.append(sb.build(coll))
    print('v2_landmarks SNP: pylon head', round(head.z - gl, 1), 'm, UFO terrace', round(tz - gl, 1),
          'm above footings, axis', tuple(round(x, 3) for x in u))
    return out


def deck_z(SNP, q, default):
    """Deck top at plan point q from the city's bridge segments (nearest), else the default level."""
    segs = SNP.get('segs')
    if not segs:
        return default
    best, bz = 1e9, default
    for a, b, za, zb in segs:
        d = b - a
        L2 = d.length_squared
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, (q - a).dot(d) / L2))
        dd = (a + d * t - q).length
        if dd < best:
            best, bz = dd, za + (zb - za) * t
    return bz


def snp_deck(H, G, coll, misc, SNP):
    """Steel box girder fascia (~4.6 m deep) along the outline long sides, with the walkway screens hung
    under the roadway (photos: snp_side_view_a, snp_lower_cycle_path, snp_underside_deck)."""
    if 'u' not in SNP:
        return []
    _materials(H)
    Vector, MB = H['Vector'], H['MB']
    ax = _axis(H, misc)
    if not ax:
        return []
    c0, u, P = ax
    mb = MB('V2LM_SNP_Deck')
    n = 0
    for a, b in zip(P, P[1:] + P[:1]):
        d = b - a
        L = d.length
        if L < 0.5 or abs(d.normalized().dot(u)) < 0.9:
            continue
        o = Vector((d.y, -d.x)).normalized()
        if (((a + b) / 2) - c0).dot(o) < 0:
            o = -o
        steps = max(1, int(L / 6.0))
        for i in range(steps):
            p0, p1 = a + d * (i / steps) + o * 0.15, a + d * ((i + 1) / steps) + o * 0.15
            z0, z1 = deck_z(SNP, p0, SNP['deck']), deck_z(SNP, p1, SNP['deck'])
            # the 4.6 m girder with the hung walkway belongs to the river span; over the low land ramps it would
            # hang at chest height across the plazas (and its soffit would be walked on)
            if min(z0 - G(*p0), z1 - G(*p1)) < 9.0:
                continue
            def band(h0, h1, mat, inset=0.0):
                q = [Vector((*(p0 - o * inset), z0 - h0)), Vector((*(p1 - o * inset), z1 - h0)),
                     Vector((*(p1 - o * inset), z1 - h1)), Vector((*(p0 - o * inset), z0 - h1))]
                if H_normal(q).to_2d().dot(o) < 0:
                    q.reverse()
                mb.poly(q, mat)
            band(1.25, 2.3, 'lm_steel')              # fascia under the city's parapet / edge beam
            band(2.3, 3.6, 'lm_screen', 0.9)         # walkway level behind its mesh screen
            band(3.6, 4.6, 'lm_steel')
            sof = [Vector((*p0, z0 - 4.6)), Vector((*p1, z1 - 4.6)), Vector((*(p1 - o * 10.0), z1 - 4.6)), Vector((*(p0 - o * 10.0), z0 - 4.6))]
            if H_normal(sof).z > 0:
                sof.reverse()
            mb.poly(sof, 'lm_steel')
            fl = [Vector((*p0, z0 - 2.3)), Vector((*p1, z1 - 2.3)), Vector((*(p1 - o * 0.9), z1 - 2.3)), Vector((*(p0 - o * 0.9), z0 - 2.3))]
            if H_normal(fl).z > 0:
                fl.reverse()
            mb.poly(fl, 'lm_steel')                  # cantilever underside above the walkway
            if i % 5 == 0:                           # tall deck lamps along both parapets (snp_side_view_a)
                lp = p0 - o * 1.0
                H['_prism'](mb, Vector((*lp, z0)), Vector((*lp, z0 + 10.0)), 0.12, 0.08, 'lm_white', seg=6)
                tip = lp - o * 1.8
                H['_prism'](mb, Vector((*lp, z0 + 9.8)), Vector((*tip, z0 + 10.1)), 0.06, 0.06, 'lm_white', seg=4)
                H['seg_box'](mb, tip - o * 0.0, tip - o * 0.6, -0.15, 0.15, z0 + 9.85, z0 + 10.05, 'lamp')
            n += 1
    print('v2_landmarks SNP deck fascia segments', n)
    return [mb.build(coll)] if n else []


# ---------------------------------------------------------------- Dom sv. Martina, west tower
DOM_TOWER = 243293986


def dom_tower(H, special, G, coll):
    """85 m west tower (photos dom_tower_spire, dom_south_facade): plain rendered square shaft to ~48 m with
    lancet windows, a rose window and clocks; above it the copper roof - flared skirt, bulbous dome with gilt ribs,
    open octagonal lantern, cornice, tall needle spire and the gilded crown on its cushion at 85 m."""
    if DOM_TOWER not in special:
        return []
    import v2_city as C
    _materials(H)
    Vector, MB = H['Vector'], H['MB']
    t, r, cx, cy = special[DOM_TOWER]
    g = min(G(p[0], p[1]) for p in r)
    c = Vector((cx, cy))
    P = [Vector(p) for p in r]
    shaft = MB('V2LM_Dom_Tower-col')
    top = MB('V2LM_Dom_Spire')
    zs = g + 48.0
    # shaft walls: rendered, a light stone plinth and a cornice band
    for a_, b_ in zip(P, P[1:] + P[:1]):
        if (b_ - a_).length < 0.3:
            continue
        for z0, z1, mat in ((g - 1.5, g + 2.2, 'v2_stone_church'), (g + 2.2, zs - 1.2, 'plaster'), (zs - 1.2, zs, 'v2_stone_church')):
            q = [Vector((*a_, z0)), Vector((*b_, z0)), Vector((*b_, z1)), Vector((*a_, z1))]
            if H_normal(q).to_2d().dot((a_ + b_) / 2 - c) < 0:
                q.reverse()
            shaft.poly(q, mat)
    C._cap(H, shaft, r, zs, 'v2_copper')
    # windows on every face: rose window low, two tiers of tall lancets, clock above (dom_south_facade)
    for a_, b_ in zip(P, P[1:] + P[:1]):
        L = (b_ - a_).length
        if L < 6.0:
            continue
        dd = (b_ - a_).normalized()
        out_ = Vector((dd.y, -dd.x))
        m_ = (a_ + b_) / 2
        if out_.dot(m_ - c) < 0:
            out_ = -out_
        C._gothic_window(H, top, m_ + out_ * 0.02, dd, out_, g + 27.0, g + 33.5, 1.0)
        C._gothic_window(H, top, m_ + out_ * 0.02, dd, out_, g + 36.5, g + 41.0, 1.0)
        ang = math.atan2(out_.y, out_.x)
        H['ellipsoid'](top, Vector((*(m_ + out_ * 0.08), g + 21.5)), 0.08, 1.5, 1.5, ang, 0, 'v2_stone_church', subdiv=2)   # rose
        H['ellipsoid'](top, Vector((*(m_ + out_ * 0.14), g + 21.5)), 0.05, 1.15, 1.15, ang, 0, 'v2_leaded', subdiv=2)
        H['ellipsoid'](top, Vector((*(m_ + out_ * 0.04), g + 45.0)), 0.06, 1.38, 1.38, ang, 0, 'gold', subdiv=2)               # clock ring
        H['ellipsoid'](top, Vector((*(m_ + out_ * 0.09), g + 45.0)), 0.05, 1.22, 1.22, ang, 0, 'lm_dark', subdiv=2)            # black dial
    # copper roof: radii from the shaft half-width w (photo proportions)
    w = 0.5 * max((P[i] - P[j]).length for i in range(len(P)) for j in range(len(P))) / math.sqrt(2)
    seg = 24
    prof = [(w * 1.08, zs), (w * 0.98, zs + 1.0), (w * 0.86, zs + 2.4), (w * 0.84, zs + 3.4),      # flared skirt
            (w * 0.86, zs + 4.4), (w * 0.86, zs + 6.0), (w * 0.80, zs + 8.0), (w * 0.66, zs + 10.0),  # bulbous dome
            (w * 0.45, zs + 11.6), (w * 0.33, zs + 12.4), (w * 0.33, zs + 12.9)]
    _lathe(top, Vector, c, prof, lambda *a: 'v2_copper', seg=seg)
    for k in range(8):                                  # gilt dome ribs + a gilt band at the skirt
        a = 2 * math.pi * (k + 0.5) / 8
        pts = [Vector((c.x + math.cos(a) * (rr + 0.06), c.y + math.sin(a) * (rr + 0.06), zz)) for rr, zz in prof[3:9]]
        for p0, p1 in zip(pts, pts[1:]):
            H['_prism'](top, p0, p1, 0.09, 0.09, 'gold', seg=4)
    _lathe(top, Vector, c, [(w * 0.87, zs + 4.3), (w * 0.875, zs + 4.6)], lambda *a: 'gold', seg=seg)
    # open octagonal lantern: 8 posts, arched openings read as dark between them
    zl0, zl1 = zs + 12.9, zs + 19.5
    rl = w * 0.33
    for k in range(8):
        a0 = 2 * math.pi * k / 8
        p = Vector((c.x + math.cos(a0) * rl, c.y + math.sin(a0) * rl))
        H['_prism'](top, Vector((*p, zl0)), Vector((*p, zl1)), 0.5, 0.42, 'v2_copper', seg=4)
    _lathe(top, Vector, c, [(rl * 0.82, zl0 + 0.1), (rl * 0.82, zl1)], lambda *a: 'lm_dark', seg=8)          # dark interior
    _lathe(top, Vector, c, [(rl + 0.5, zl1), (rl + 0.6, zl1 + 0.5), (rl + 0.2, zl1 + 1.0)], lambda *a: 'v2_copper', seg=16)
    _lathe(top, Vector, c, [(rl + 0.62, zl1 + 0.45), (rl + 0.64, zl1 + 0.6)], lambda *a: 'gold', seg=16)
    # needle spire with gilt crockets, crown on its cushion at 85 m
    z_sp0, z_sp1 = zl1 + 1.0, g + 82.4
    _lathe(top, Vector, c, [(rl + 0.2, z_sp0), (rl * 0.55, z_sp0 + 3.0), (0.25, z_sp1)], lambda *a: 'v2_copper', seg=8)
    for k in range(6):
        zz = z_sp0 + 3.0 + k * (z_sp1 - z_sp0 - 3.0) / 6
        rr = rl * 0.55 + (0.25 - rl * 0.55) * (zz - z_sp0 - 3.0) / (z_sp1 - z_sp0 - 3.0)
        _lathe(top, Vector, c, [(rr + 0.08, zz), (rr + 0.08, zz + 0.18)], lambda *a: 'gold', seg=8)
    H['ellipsoid'](top, Vector((c.x, c.y, g + 82.75)), 0.65, 0.65, 0.28, 0, 0, 'gold', subdiv=1)       # cushion 1.2 m
    _lathe(top, Vector, c, [(0.5, g + 83.0), (0.58, g + 83.6), (0.5, g + 84.0), (0.0, g + 84.35)], lambda *a: 'gold', seg=12)
    H['_prism'](top, Vector((c.x, c.y, g + 84.3)), Vector((c.x, c.y, g + 84.75)), 0.05, 0.04, 'gold', seg=4)  # cross (1.64 m crown)
    H['_prism'](top, Vector((c.x - 0.18, c.y, g + 84.6)), Vector((c.x + 0.18, c.y, g + 84.6)), 0.04, 0.04, 'gold', seg=4)
    print('v2_landmarks Dom tower: shaft', round(zs - g, 1), 'm, crown top', round(84.75, 1), 'm, half-width', round(w, 1))
    return [shaft.build(coll), top.build(coll)]


# ---------------------------------------------------------------- Michalska brana (top + shaft dressing)
MICHAEL = 39391573


def michalska(H, special, G, coll):
    """51 m gate tower (photos michalska_tower_full_height, _portrait): the city keeps the rendered shaft with
    its open passage up to the 26 m gallery; here: stone quoins, the small window per storey, arms panel over the
    arch, wrought-iron gallery, octagonal clock stage, copper bell roof, lantern, small onion, spire, St Michael."""
    if MICHAEL not in special:
        return []
    _materials(H)
    Vector, MB = H['Vector'], H['MB']
    t, r, cx, cy = special[MICHAEL]
    g = min(G(p[0], p[1]) for p in r)
    c = Vector((cx, cy))
    P = [Vector(p) for p in r]
    mb = MB('V2LM_Michael')
    # the gate tower is a ~11 m square: half-width from the outline area, faces along its longest edge
    import v2_city as C
    w = 0.5 * math.sqrt(abs(C._area([tuple(p) for p in P])))
    e0 = max(zip(P, P[1:] + P[:1]), key=lambda e: (e[1] - e[0]).length)
    d0 = (e0[1] - e0[0]).normalized()
    n0 = Vector((d0.y, -d0.x))
    edges = []
    ext = {}
    for nn in (n0, -n0, d0, -d0):                          # face planes at the outline's extreme extent
        ext[tuple(nn)] = max((p - c).dot(nn) for p in P)
    for nn in (n0, -n0, d0, -d0):
        side = Vector((-nn.y, nn.x))
        ws = ext[tuple(side)] if tuple(side) in ext else w
        wo = ext[tuple(-side)] if tuple(-side) in ext else w
        m = c + nn * ext[tuple(nn)]
        edges.append((m - side * wo, m + side * ws))
    for a_, b_ in edges:
        dd = (b_ - a_).normalized()
        out_ = Vector((dd.y, -dd.x))
        m_ = (a_ + b_) / 2
        if out_.dot(m_ - c) < 0:
            out_ = -out_
        L = (b_ - a_).length
        lft = Vector((-dd.y, dd.x))
        for q_, sg in ((a_, 1), (b_, -1)):                   # rusticated corner quoins
            o0, o1 = (0.0, 0.08) if lft.dot(out_) * sg > 0 else (-0.08, 0.0)
            for k in range(14):
                z0 = g + 1.0 + k * 1.8
                ln = 0.9 if k % 2 else 0.55
                H['seg_box'](mb, q_, q_ + dd * sg * ln, o0, o1, z0, z0 + 0.85, 'v2_stone_church')
        for k, z0 in enumerate((9.5, 13.5, 17.0, 20.5, 23.5)):  # one small framed window per storey
            if L < 5.0:
                continue
            p0, p1 = m_ - dd * 0.55 + out_ * 0.06, m_ + dd * 0.55 + out_ * 0.06
            mb.poly([Vector((*p0, g + z0)), Vector((*p1, g + z0)), Vector((*p1, g + z0 + 1.3)), Vector((*p0, g + z0 + 1.3))], 'v2_leaded')
            for (s0, s1, z_a, z_b) in ((-0.75, -0.55, z0 - 0.15, z0 + 1.45), (0.55, 0.75, z0 - 0.15, z0 + 1.45),
                                       (-0.75, 0.75, z0 - 0.25, z0), (-0.75, 0.75, z0 + 1.3, z0 + 1.5)):
                a2, b2 = m_ + dd * s0 + out_ * 0.02, m_ + dd * s1 + out_ * 0.02
                q = [Vector((*a2, g + z_a)), Vector((*b2, g + z_a)), Vector((*b2, g + z_b)), Vector((*a2, g + z_b))]
                if H_normal(q).to_2d().dot(out_) < 0:
                    q.reverse()
                mb.poly(q, 'v2_stone_church')
        # arms panel (stone) above the passage on the long street faces
        p0, p1 = m_ - dd * 0.9 + out_ * 0.07, m_ + dd * 0.9 + out_ * 0.07
        q = [Vector((*p0, g + 6.6)), Vector((*p1, g + 6.6)), Vector((*p1, g + 8.6)), Vector((*p0, g + 8.6))]
        if H_normal(q).to_2d().dot(out_) < 0:
            q.reverse()
        mb.poly(q, 'v2_stone_church')
    # 26 m: cornice with small copper pent roofs, wrought-iron gallery around the set-back octagonal stage
    z = g + 26.0
    _lathe(mb, Vector, c, [(w * 1.13, z - 0.25), (w * 1.15, z), (w * 1.0, z + 0.3)], lambda *a: 'plaster', seg=16)     # gallery slab / cornice
    ro = w * 0.87      # photo: the clock stage is ~0.8 of the shaft width
    for k in range(32):
        a0, a1 = 2 * math.pi * k / 32, 2 * math.pi * (k + 1) / 32
        p0 = Vector((c.x + math.cos(a0) * w * 1.12, c.y + math.sin(a0) * w * 1.12))
        p1 = Vector((c.x + math.cos(a1) * w * 1.12, c.y + math.sin(a1) * w * 1.12))
        H['seg_box'](mb, p0, p1, -0.03, 0.03, z + 1.5, z + 1.58, 'v2_iron')          # wrought-iron rail
        H['seg_box'](mb, p0, p1, -0.02, 0.02, z + 0.55, z + 0.6, 'v2_iron')
        H['_prism'](mb, Vector((*p0, z + 0.3)), Vector((*p0, z + 1.58)), 0.025, 0.025, 'v2_iron', seg=4)
    oc = [c + Vector((math.cos(math.pi / 8 + k * math.pi / 4), math.sin(math.pi / 8 + k * math.pi / 4))) * ro for k in range(8)]
    for k in range(8):
        a, b = oc[k], oc[(k + 1) % 8]
        q = [Vector((*a, z + 0.5)), Vector((*b, z + 0.5)), Vector((*b, z + 7.0)), Vector((*a, z + 7.0))]
        if H_normal(q).to_2d().dot((a + b) / 2 - c) < 0:
            q.reverse()
        mb.poly(q, 'plaster')
        m_ = (a + b) / 2
        o_ = (m_ - c).normalized()
        if k % 2 == 0:                                       # clock on four faces
            ang = math.atan2(o_.y, o_.x)
            H['ellipsoid'](mb, Vector((*(m_ + o_ * 0.08), z + 4.3)), 0.05, 1.05, 1.05, ang, 0, 'plaque', subdiv=2)
            H['ellipsoid'](mb, Vector((*(m_ + o_ * 0.11), z + 4.3)), 0.03, 0.18, 0.18, ang, 0, 'lm_dark', subdiv=1)
    C_ = __import__('v2_city')
    C_._cap(H, mb, [tuple(p) for p in oc], z + 0.5, 'v2_stone_church')
    # eave, bell-shaped copper roof, lantern with arched openings, small onion, spire, St Michael with the dragon
    z = z + 7.0
    rr = ro
    # tall bulbous onion (Earth gs_michalska, photo: ~0.85 of the stage wide, about as tall as the stage is wide)
    prof = [(rr * 1.02, z), (rr * 1.06, z + 0.4), (rr * 0.72, z + 1.1),                # eave
            (rr * 0.84, z + 2.4), (rr * 0.92, z + 3.6), (rr * 0.85, z + 4.8), (rr * 0.6, z + 6.0),   # onion
            (rr * 0.32, z + 6.8), (rr * 0.3, z + 7.0)]
    _lathe(mb, Vector, c, prof, lambda *a: 'v2_copper', seg=16)
    zl = z + 7.0
    rl = rr * 0.4
    for k in range(8):
        a0 = 2 * math.pi * (k + 0.5) / 8
        p = Vector((c.x + math.cos(a0) * rl, c.y + math.sin(a0) * rl))
        H['_prism'](mb, Vector((*p, zl)), Vector((*p, zl + 3.2)), 0.22, 0.22, 'v2_copper', seg=4)
    _lathe(mb, Vector, c, [(rl * 0.8, zl), (rl * 0.8, zl + 3.2)], lambda *a: 'lm_dark', seg=8)
    z = zl + 3.2
    _lathe(mb, Vector, c, [(rl * 1.25, z), (rl * 1.25, z + 0.35), (rl * 0.9, z + 0.6), (rl * 1.05, z + 1.4),
                           (rl * 0.7, z + 2.2), (rl * 0.2, z + 2.8), (0.12, z + 3.0)], lambda *a: 'v2_copper', seg=8)
    z += 3.0
    H['_prism'](mb, Vector((c.x, c.y, z)), Vector((c.x, c.y, g + 49.4)), 0.12, 0.05, 'v2_copper', seg=6)
    H['ellipsoid'](mb, Vector((c.x, c.y, g + 49.6)), 0.25, 0.25, 0.25, 0, 0, 'v2_copper', subdiv=1)     # orb
    H['ellipsoid'](mb, Vector((c.x, c.y, g + 50.3)), 0.22, 0.18, 0.55, 0, 0, 'v2_copper', subdiv=1)     # St Michael
    H['_prism'](mb, Vector((c.x, c.y, g + 50.6)), Vector((c.x + 0.25, c.y, g + 51.2)), 0.03, 0.02, 'v2_copper', seg=4)  # sword
    H['ellipsoid'](mb, Vector((c.x + 0.2, c.y, g + 50.85)), 0.06, 0.45, 0.25, 0, 0, 'v2_copper', subdiv=1)       # wings
    print('v2_landmarks Michalska: half-width', round(w, 1), 'top', round(51.2, 1))
    return [mb.build(coll)]


# ---------------------------------------------------------------- Dom sv. Martina, nave + presbytery
def dom_body(H, special, G, coll):
    """Hall nave + narrower presbytery under steep tiled roofs, lancets between stepped buttresses, north portal,
    south porch (moved from v2_city._landmarks); photo details added in _dom_details()."""
    import v2_city as C
    _materials(H)
    Vector, MB, seg_box = H['Vector'], H['MB'], H['seg_box']
    mb = C.VChunk(H, 'V2LM_Dom|-col', 'V2LM_Dom|-col', 1e5, 1e5)     # vertex-tinted roof materials
    # --- St Martin's Cathedral: hall nave + narrower presbytery under steep gabled roofs (ridge along the
    # principal axis of the OSM outline), tall Gothic windows between buttresses, polygonal apse roof
    if C.CATHEDRAL in C.DECOR:
        r, gnd, wt = C.DECOR[C.CATHEDRAL]
        P = [Vector(p) for p in r]
        c0 = sum(P, Vector((0, 0))) / len(P)
        sxx = sum((p.x - c0.x) ** 2 for p in P)
        syy = sum((p.y - c0.y) ** 2 for p in P)
        sxy = sum((p.x - c0.x) * (p.y - c0.y) for p in P)
        ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
        u = Vector((math.cos(ang), math.sin(ang)))
        v = Vector((-u.y, u.x))
        if 243293986 in special and (Vector(special[243293986][2:4]) - c0).dot(u) > 0:
            u, v = -u, -v                        # u points from the west tower to the apse
        ss = [(p - c0).dot(u) for p in P]
        s0, s1 = min(ss), max(ss)

        def span(sv):
            ts = []
            for a_, b_ in zip(P, P[1:] + P[:1]):
                sa, sb = (a_ - c0).dot(u), (b_ - c0).dot(u)
                if (sa - sv) * (sb - sv) < 0:
                    k = (sv - sa) / (sb - sa)
                    ts.append(((a_ + (b_ - a_) * k) - c0).dot(v))
            return (min(ts), max(ts)) if len(ts) >= 2 else None
        prof = [(sv, span(sv)) for sv in [s0 + 1.5 + i * 2.0 for i in range(int((s1 - s0 - 3) / 2.0) + 1)]]
        prof = [(sv, sp) for sv, sp in prof if sp]
        wmax = max(sp[1] - sp[0] for _, sp in prof)
        split = next((sv for sv, sp in prof if sv > s0 + 0.35 * (s1 - s0) and sp[1] - sp[0] < 0.8 * wmax), s1)

        def section(sa, sb):
            sp = [p for sv, p in prof if sa <= sv <= sb]
            sp.sort(key=lambda q: q[1] - q[0])
            q = sp[len(sp) // 3]                 # ignore buttress bumps
            return q[0], q[1]
        apse = 9.0

        def gable(sa, sb, ta, tb, ridge_z, hip_end, west_gable=None):
            tm = (ta + tb) / 2
            o = 0.5
            A = lambda s_, t_, z_: Vector((*(c0 + u * s_ + v * t_), z_))
            e0, e1 = A(sa, ta - o, wt), A(sb, ta - o, wt)
            f0, f1 = A(sa, tb + o, wt), A(sb, tb + o, wt)
            r0, r1 = A(sa, tm, ridge_z), A(sb - (apse * 0.7 if hip_end else 0), tm, ridge_z)
            mb.poly([e0, e1, r1, r0], 'v2_roof_red')
            mb.poly([f1, f0, r0, r1], 'v2_roof_red')
            if west_gable is None:
                mb.poly([f0, e0, r0], 'v2_stone_church')         # stone gable
            else:
                wa = lambda q_: q_ + Vector((*(u * (west_gable - sa)), 0))
                mb.poly([wa(f0), wa(e0), wa(r0)], 'v2_stone_church')
            if hip_end:
                tip = A(sb + 0.5, tm, wt)
                mb.poly([e1, tip, r1], 'v2_roof_red')
                mb.poly([tip, f1, r1], 'v2_roof_red')
            else:
                mb.poly([e1, f1, r1], 'v2_stone_church')
        ta, tb = section(s0, split)
        # the nave roof runs to the west front and the tower rises through it (photo dom_south_facade);
        # no west gable then, it would stand in front of the tower's lower shaft
        wg = None
        if DOM_TOWER in special:          # gable set just behind the tower's west face: hidden in the middle,
            wg = max(s0, min((Vector(q) - c0).dot(u) for q in special[DOM_TOWER][1])) + 0.4     # closes the roof ends beside it
        gable(s0 if wg is None else wg - 0.4, split + 0.5, ta, tb, wt + 0.85 * (tb - ta), False, west_gable=wg)
        if split < s1 - 4:
            pa, pb = section(split, s1 - apse)
            gable(split, s1 - 0.5, pa, pb, wt + 0.85 * (pb - pa) * 0.95, True)
        # windows + buttresses on the long faces
        for a_, b_ in zip(P, P[1:] + P[:1]):
            d_ = b_ - a_
            L = d_.length
            if L < 3.5 or abs(d_.normalized().dot(u)) < 0.85:
                continue
            out_ = Vector((d_.y, -d_.x)).normalized()           # CCW ring: right normal = outside
            m_ = (a_ + b_) / 2 + out_ * 0.08
            hw = min(1.3, L * 0.25)
            dd = d_.normalized()
            C._gothic_window(H, mb, m_, dd, out_, gnd + 5.0, wt - 5.5, hw)
            for q_ in (a_, b_):                          # buttresses stepping back in three set-offs
                for k_, (dep, zt_) in enumerate(((1.8, gnd + 7.0), (1.3, gnd + 14.0), (0.8, wt - 2.0))):
                    z0_ = gnd - 1.5                       # every set-off stands on the (sloping) ground
                    seg_box(mb, q_ - dd * 0.6, q_ + dd * 0.6, -dep, 0.0, z0_, zt_, 'v2_stone_church')
                    seg_box(mb, q_ - dd * 0.65, q_ + dd * 0.65, -dep - 0.1, 0.0, zt_ - 0.25, zt_, 'v2_stone_church')
        # main portal on the north side (Rudnayovo nam.), west half of the nave: stepped Gothic jambs, doors
        nedges = [(a_, b_) for a_, b_ in zip(P, P[1:] + P[:1]) if (b_ - a_).length > 4.0 and
                  Vector(((b_ - a_).y, -(b_ - a_).x)).normalized().y > 0.6]
        if nedges:
            a_, b_ = min(nedges, key=lambda e_: ((e_[0] + e_[1]) / 2 - c0).dot(u))
            dd = (b_ - a_).normalized()
            out_ = Vector((dd.y, -dd.x))
            m_ = (a_ + b_) / 2
            gz = G(m_.x, m_.y)
            for k_, (hw_, dep) in enumerate(((2.6, 0.9), (2.2, 0.6), (1.8, 0.3))):     # stepped orders
                for sgn in (-1, 1):
                    c_ = m_ + dd * hw_ * sgn
                    mb.box([c_ - dd * 0.2, c_ + dd * 0.2, c_ + dd * 0.2 + out_ * dep, c_ - dd * 0.2 + out_ * dep], gz - 0.2, gz + 5.5 + k_ * 0.5, 'v2_stone_church')
                tip = m_ + out_ * dep
                mb.poly([Vector((*(m_ - dd * hw_ + out_ * dep), gz + 5.5 + k_ * 0.5)), Vector((*(m_ + dd * hw_ + out_ * dep), gz + 5.5 + k_ * 0.5)),
                         Vector((*tip, gz + 8.2 + k_ * 0.6))], 'v2_stone_church')
            mb.poly([Vector((*(m_ - dd * 1.5 + out_ * 0.12), gz)), Vector((*(m_ + dd * 1.5 + out_ * 0.12), gz)),
                     Vector((*(m_ + dd * 1.5 + out_ * 0.12), gz + 4.6)), Vector((*(m_ - dd * 1.5 + out_ * 0.12), gz + 4.6))], 'frame')    # oak doors
            mb.poly([Vector((*(m_ - dd * 1.5 + out_ * 0.12), gz + 4.6)), Vector((*(m_ + dd * 1.5 + out_ * 0.12), gz + 4.6)),
                     Vector((*(m_ + out_ * 0.12), gz + 6.8))], 'v2_leaded')                                                        # tympanum glazing
        # south porch with steps (toward the lawn terrace)
        sedges = [(a_, b_) for a_, b_ in zip(P, P[1:] + P[:1]) if (b_ - a_).length > 4.0 and
                  Vector(((b_ - a_).y, -(b_ - a_).x)).normalized().y < -0.6]
        if sedges:
            a_, b_ = max(sedges, key=lambda e_: (e_[1] - e_[0]).length)
            dd = (b_ - a_).normalized()
            out_ = Vector((dd.y, -dd.x))
            m_ = (a_ + b_) / 2
            gz = G(m_.x, m_.y)
            pc = [m_ - dd * 3.0, m_ + dd * 3.0, m_ + dd * 3.0 + out_ * 4.0, m_ - dd * 3.0 + out_ * 4.0]
            for sgn in (-1, 1):                                    # side walls with an arched opening look
                c_ = m_ + dd * 2.8 * sgn
                mb.box([c_ - dd * 0.2, c_ + dd * 0.2, c_ + dd * 0.2 + out_ * 4.0, c_ - dd * 0.2 + out_ * 4.0], gz - 0.3, gz + 5.5, 'v2_stone_church')
            seg_box(mb, pc[3], pc[2], 0.0, 0.5, gz + 4.2, gz + 5.5, 'v2_stone_church')               # front lintel
            r0, r1 = m_ + out_ * 0.0, m_ + out_ * 4.2
            for sgn in (-1, 1):
                q = [Vector((*(m_ + dd * 3.2 * sgn - out_ * 0.1), gz + 5.5)), Vector((*(m_ + dd * 3.2 * sgn + out_ * 4.3), gz + 5.5)),
                     Vector((*r1, gz + 7.8)), Vector((*r0, gz + 7.8))]
                if (q[1] - q[0]).cross(q[3] - q[0]).z < 0:
                    q.reverse()
                mb.poly(q, 'v2_roof_red')
            mb.poly([Vector((*(m_ - dd * 3.2 + out_ * 4.3), gz + 5.5)), Vector((*(m_ + dd * 3.2 + out_ * 4.3), gz + 5.5)), Vector((*r1, gz + 7.8))], 'v2_stone_church')
            mb.poly([Vector((*(m_ - dd * 1.3 + out_ * 0.1), gz)), Vector((*(m_ + dd * 1.3 + out_ * 0.1), gz)),
                     Vector((*(m_ + dd * 1.3 + out_ * 0.1), gz + 3.8)), Vector((*(m_ - dd * 1.3 + out_ * 0.1), gz + 3.8))], 'frame')
            for k_ in range(3):                                    # steps out of the porch (0.15 m risers)
                c_ = m_ + out_ * (4.0 + 0.35 * k_)
                seg_box(mb, c_ - dd * 2.6, c_ + dd * 2.6, -0.35, 0.0, gz - 0.4, gz + 0.45 - 0.15 * k_, 'v2_stone_church')
        C._cap(H, mb, r, wt - 0.05, 'v2_roof_grey')
        # --- photo details (dom_south_facade, dom_north_facade, dom_east_choir)
        A = lambda s_, t_, z_: Vector((*(c0 + u * s_ + v * t_), z_))
        # the nave is rendered white, the presbytery stays bare ashlar: plaster over the nave walls
        for a_, b_ in zip(P, P[1:] + P[:1]):
            d_ = b_ - a_
            if d_.length < 1.0 or (((a_ + b_) / 2) - c0).dot(u) > split:
                continue
            out_ = Vector((d_.y, -d_.x)).normalized()
            q = [Vector((*(a_ + out_ * 0.03), gnd + 1.2)), Vector((*(b_ + out_ * 0.03), gnd + 1.2)),
                 Vector((*(b_ + out_ * 0.03), wt - 0.5)), Vector((*(a_ + out_ * 0.03), wt - 0.5))]
            if H_normal(q).to_2d().dot(out_) < 0:
                q.reverse()
            mb.poly(q, 'plaster')
        # small lidded roof vents in rows on both nave slopes
        nr = wt + 0.85 * (tb - ta)
        for k in range(5):
            sv = s0 + 6.0 + k * (split - s0 - 8.0) / 4
            for side, (t_e, frac) in ((-1, (ta, 0.45)), (1, (tb, 0.45))):
                tm = (ta + tb) / 2
                tt = tm + (t_e - tm) * frac
                zz = nr + (wt - nr) * frac
                seg_box(mb, A(sv - 0.45, tt, 0)[:2], A(sv + 0.45, tt, 0)[:2], -0.35, 0.35, zz - 0.2, zz + 0.75, 'lm_dark')
                mb.poly([A(sv - 0.55, tt - 0.45 * side, zz + 0.75), A(sv + 0.55, tt - 0.45 * side, zz + 0.75),
                         A(sv + 0.55, tt + 0.45 * side, zz + 0.55), A(sv - 0.55, tt + 0.45 * side, zz + 0.55)], 'v2_roof_red')
        # ridge turret (sanctus bell) on the presbytery roof toward the apse: dark octagonal lantern + needle
        if split < s1 - 4:
            pr = wt + 0.85 * (pb - pa) * 0.95
            q = A(s1 - apse - 4.0, (pa + pb) / 2, pr - 0.5)
            _lathe(mb, Vector, q, [(1.1, q.z), (1.1, q.z + 2.6), (1.35, q.z + 2.9), (0.9, q.z + 3.4),
                                   (0.12, q.z + 7.5)], lambda *a_: 'v2_slate', seg=8)
            H['_prism'](mb, Vector((q.x, q.y, q.z + 7.4)), Vector((q.x, q.y, q.z + 8.6)), 0.04, 0.03, 'gold', seg=4)
        # chapel of St John the Almsgiver on the north side (Earth ph_kapitulska): green copper dome + lantern
        cc = Vector((355.8, -21.3))
        _lathe(mb, Vector, cc, [(3.9, wt - 0.3), (3.9, wt + 1.4), (4.2, wt + 1.6)], lambda *a_: 'plaster', seg=8)
        _lathe(mb, Vector, cc, [(4.2, wt + 1.6), (4.0, wt + 2.6), (3.4, wt + 4.0), (2.3, wt + 5.2), (1.0, wt + 5.8)],
               lambda *a_: 'v2_copper', seg=16)
        _lathe(mb, Vector, cc, [(0.9, wt + 5.8), (0.9, wt + 7.0), (1.15, wt + 7.2), (1.1, wt + 7.7), (0.4, wt + 8.5),
                                (0.1, wt + 8.8)], lambda *a_: 'v2_copper', seg=8)
        H['_prism'](mb, Vector((cc.x, cc.y, wt + 8.7)), Vector((cc.x, cc.y, wt + 9.8)), 0.04, 0.03, 'gold', seg=4)
    return mb.build(coll) if mb.parts else []


# ---------------------------------------------------------------- Stara radnica (Old Town Hall) tower
def townhall(H, special, G, coll):
    """~45 m tower (photos radnica_main_square_facade, radnica_tower): pale yellow shaft with white corner
    pilasters, Gothic window and oculus, gateway; balustraded gallery at ~23.5 m; upper storey with white clock
    dials and arched belfry openings; Baroque copper helmet (bell, lantern, onion, spire); Gothic oriel."""
    import v2_city as C
    if C.OLD_TOWN_HALL not in C.DECOR:
        return []
    _materials(H)
    Vector, seg_box, ellipsoid, _prism = H['Vector'], H['seg_box'], H['ellipsoid'], H['_prism']
    mb = C.VChunk(H, 'V2LM_Townhall|-col', 'V2LM_Townhall|-col', 1e5, 1e5)
    r, gnd, wt = C.DECOR[C.OLD_TOWN_HALL]
    wd = Vector(H['to_local'](48.143611, 17.108889))
    best = None
    for p0, p1 in zip(r, r[1:] + r[:1]):
        p0, p1 = Vector(p0), Vector(p1)
        if (p1 - p0).length > 6.0:
            dd = ((p0 + p1) / 2 - wd).length
            if best is None or dd < best[0]:
                best = (dd, p0, p1)
    _, p0, p1 = best
    u = (p1 - p0).normalized()
    nin = Vector((-u.y, u.x))                       # CCW ring: interior on the left
    hw = 4.3
    m0 = (p0 + p1) / 2 - nin * 0.35
    sq = [m0 - u * hw, m0 + u * hw, m0 + u * hw + nin * 2 * hw, m0 - u * hw + nin * 2 * hw]
    tc = m0 + nin * hw
    g = min(G(q.x, q.y) for q in sq)
    zg, zu = g + 23.5, g + 32.8                     # gallery, top of the clock storey

    def walls(pts, z0, z1, mat):
        for k in range(len(pts)):
            a, b = pts[k], pts[(k + 1) % len(pts)]
            q = [Vector((*a, z0)), Vector((*b, z0)), Vector((*b, z1)), Vector((*a, z1))]
            if H_normal(q).to_2d().dot((a + b) / 2 - tc) < 0:
                q.reverse()
            mb.poly(q, mat)
    walls(sq, g - 1, zg, 'v2_render_ochre')
    for k in range(4):
        a, b = sq[k], sq[(k + 1) % 4]
        m_ = (a + b) / 2
        out_ = (m_ - tc).normalized()
        side = Vector((-out_.y, out_.x))
        for z in (g + 4.8, g + 12.0, zg - 0.6):       # white string courses / cornice
            seg_box(mb, a, b, -0.3, 0.05, z, z + 0.5, 'plaster')
        ang = math.atan2(out_.y, out_.x)
        ellipsoid(mb, Vector((*(m_ + out_ * 0.06), g + 16.5)), 0.05, 0.75, 0.75, ang, 0, 'plaster', subdiv=2)   # oculus
        ellipsoid(mb, Vector((*(m_ + out_ * 0.1), g + 16.5)), 0.04, 0.55, 0.55, ang, 0, 'lm_dark', subdiv=2)
        H['pane'](mb, m_ - side * 0.5 + out_ * 0.05, m_ + side * 0.5 + out_ * 0.05, g + 19.5, g + 21.8)     # small arched window
    # white pilasters at the four corners of the shaft and the upper storey
    for k in range(4):
        q_ = sq[k]
        d1 = (sq[(k + 1) % 4] - q_).normalized()
        d2 = (sq[k - 1] - q_).normalized()
        base = [q_ - (d1 + d2) * 0.12, q_ + d1 * 0.75 - d2 * 0.12, q_ + d1 * 0.75 + d2 * 0.75, q_ - d1 * 0.12 + d2 * 0.75]
        mb.box([tuple(p) for p in base], g, zg - 0.6, 'plaster')
    # gateway into the courtyard, Gothic oriel beside the tower (as before)
    gate_c = m0 - nin * 0.06
    mb.poly([Vector((*(gate_c - u * 1.7), g)), Vector((*(gate_c + u * 1.7), g)),
             Vector((*(gate_c + u * 1.7), g + 4.6)), Vector((*(gate_c - u * 1.7), g + 4.6))], 'v2_slate')
    mb.poly([Vector((*(gate_c - u * 1.7), g + 4.6)), Vector((*(gate_c + u * 1.7), g + 4.6)), Vector((*gate_c, g + 6.0))], 'v2_slate')
    for sgn in (-1, 1):
        c_ = gate_c + u * 1.95 * sgn
        mb.box([c_ - u * 0.25, c_ + u * 0.25, c_ + u * 0.25 - nin * 0.3, c_ - u * 0.25 - nin * 0.3], g - 0.2, g + 4.8, 'v2_stone_church')
    C._gothic_window(H, mb, m0 - nin * 0.02, u, -nin, g + 8.0, g + 11.0, 0.7)      # Gothic window over the gate
    oc = m0 + u * (hw + 5.0)
    ob_ = [oc - u * 1.3, oc + u * 1.3, oc + u * 1.3 - nin * 1.0, oc - u * 1.3 - nin * 1.0]
    mb.box([tuple(q) for q in ob_], g + 4.5, g + 8.5, 'v2_stone_church')
    for k in range(3):
        H['pane'](mb, oc - u * 1.0 + u * k * 0.95 - nin * 1.02, oc - u * 0.6 + u * k * 0.95 - nin * 1.02, g + 5.4, g + 7.6)
    tipo = oc - nin * 0.5
    for k in range(4):
        a, b = ob_[k], ob_[(k + 1) % 4]
        mb.poly([Vector((*a, g + 8.5)), Vector((*b, g + 8.5)), Vector((*tipo, g + 10.3))], 'v2_roof_dark')
    _prism(mb, Vector((*(oc - nin * 0.5), g + 3.5)), Vector((*(oc - nin * 0.5), g + 4.5)), 0.2, 0.9, 'v2_stone_church', seg=6)
    # gallery: projecting slab + white balustrade with corner urns (statues)
    gal = [tc + (q - tc) * 1.2 for q in sq]
    C._cap(H, mb, [tuple(q) for q in gal], zg, 'stone')
    for k in range(4):
        a, b = gal[k], gal[(k + 1) % 4]
        L = (b - a).length
        d_ = (b - a) / L
        seg_box(mb, a, b, 0.0, 0.18, zg, zg + 0.15, 'plaster')
        seg_box(mb, a, b, 0.0, 0.22, zg + 1.0, zg + 1.15, 'plaster')
        for j in range(int(L / 0.32)):               # balusters
            p_ = a + d_ * (0.16 + j * 0.32)
            _prism(mb, Vector((*p_, zg + 0.15)), Vector((*p_, zg + 1.0)), 0.06, 0.06, 'plaster', seg=4)
        _prism(mb, Vector((*a, zg + 1.15)), Vector((*a, zg + 1.9)), 0.16, 0.1, 'v2_stone_church', seg=6)   # urns / statues
    # upper storey, slightly set back: clocks and arched belfry openings
    up = [tc + (q - tc) * 0.92 for q in sq]
    walls(up, zg, zu, 'v2_render_ochre')
    for k in range(4):
        a, b = up[k], up[(k + 1) % 4]
        m_ = (a + b) / 2
        out_ = (m_ - tc).normalized()
        side = Vector((-out_.y, out_.x))
        ang = math.atan2(out_.y, out_.x)
        ellipsoid(mb, Vector((*(m_ + out_ * 0.05), zg + 3.6)), 0.05, 1.0, 1.0, ang, 0, 'v2_iron', subdiv=2)     # dial ring
        ellipsoid(mb, Vector((*(m_ + out_ * 0.08), zg + 3.6)), 0.04, 0.92, 0.92, ang, 0, 'plaque', subdiv=2)   # white dial
        cc = m_ + out_ * 0.13
        mb.box([cc - side * 0.04, cc + side * 0.04, cc + side * 0.04 + out_ * 0.02, cc - side * 0.04 + out_ * 0.02], zg + 3.6, zg + 4.3, 'v2_iron')
        mb.box([cc, cc + side * 0.55, cc + side * 0.55 + out_ * 0.02, cc + out_ * 0.02], zg + 3.55, zg + 3.65, 'v2_iron')
        H['pane'](mb, m_ - side * 0.55 + out_ * 0.05, m_ + side * 0.55 + out_ * 0.05, zg + 5.6, zg + 7.8)  # belfry opening
        ellipsoid(mb, Vector((*(m_ + out_ * 0.05), zg + 7.8)), 0.04, 0.55, 0.55, ang, 0, 'lm_dark', subdiv=1)
        seg_box(mb, a, b, -0.35, 0.05, zu - 0.5, zu, 'plaster')                       # cornice
    for k in range(4):
        q_ = up[k]
        d1 = (up[(k + 1) % 4] - q_).normalized()
        d2 = (up[k - 1] - q_).normalized()
        base = [q_ - (d1 + d2) * 0.1, q_ + d1 * 0.6 - d2 * 0.1, q_ + d1 * 0.6 + d2 * 0.6, q_ - d1 * 0.1 + d2 * 0.6]
        mb.box([tuple(p) for p in base], zg, zu - 0.5, 'plaster')
    # Baroque helmet: concave-convex copper bell, lantern, small onion, spire with orb
    rr = hw * 0.92
    prof = [(rr * 1.1, zu), (rr * 1.02, zu + 0.5), (rr * 0.86, zu + 1.4), (rr * 0.8, zu + 2.2),        # flared skirt
            (rr * 0.86, zu + 3.2), (rr * 0.78, zu + 4.4), (rr * 0.48, zu + 5.3), (rr * 0.32, zu + 5.6)]  # bell (photo: ~0.85 of the storey)
    _lathe(mb, Vector, tc, prof, lambda *a: 'v2_copper', seg=8)
    zl = zu + 5.6
    for k in range(8):
        a0 = 2 * math.pi * (k + 0.5) / 8
        p_ = tc + Vector((math.cos(a0), math.sin(a0))) * rr * 0.28
        _prism(mb, Vector((*p_, zl)), Vector((*p_, zl + 2.0)), 0.12, 0.12, 'plaster', seg=4)
    _lathe(mb, Vector, tc, [(rr * 0.22, zl), (rr * 0.22, zl + 2.0)], lambda *a: 'lm_dark', seg=8)
    z = zl + 2.0
    _lathe(mb, Vector, tc, [(rr * 0.36, z), (rr * 0.34, z + 0.3), (rr * 0.24, z + 0.6), (rr * 0.3, z + 1.3),
                            (rr * 0.16, z + 2.0), (0.1, z + 2.4)], lambda *a: 'v2_copper', seg=8)
    _prism(mb, Vector((tc.x, tc.y, z + 2.4)), Vector((tc.x, tc.y, g + 45.0)), 0.1, 0.04, 'v2_copper', seg=6)
    ellipsoid(mb, Vector((tc.x, tc.y, z + 3.2)), 0.25, 0.25, 0.25, 0, 0, 'gold', subdiv=1)
    print('v2_landmarks Old Town Hall tower: gallery', round(zg - g, 1), 'clock storey to', round(zu - g, 1),
          'top', round(45.0, 1))
    return mb.build(coll)


# ---------------------------------------------------------------- SND historical building
SND_ID = 34571529


def snd(H, special, G, coll):
    """Fellner & Helmer theatre (photos snd_main_facade_01, snd_attic_sculptures): cream walls over a rusticated
    sandstone ground floor, zinc mansard, west front with a columned porch carrying a terrace, first-floor loggia,
    oval niches with five busts, the inscription band, Thalia group and the grey zinc dome over the centre;
    the stage house rises behind."""
    if SND_ID not in special:
        return []
    import v2_city as C
    _materials(H)
    Vector, seg_box, ellipsoid, _prism = H['Vector'], H['seg_box'], H['ellipsoid'], H['_prism']
    mb = C.VChunk(H, 'V2LM_SND|-col', 'V2LM_SND|-col', 1e5, 1e5)
    t, r, cx, cy = special[SND_ID]
    c = Vector((cx, cy))
    g = min(G(p[0], p[1]) for p in r)
    f = (Vector((700.0, -12.0)) - c).normalized()       # the front faces Hviezdoslavovo nam. (west)
    sd = Vector((-f.y, f.x))
    P = [Vector(p) for p in r]
    zc = g + 18.0                                       # main cornice
    C._facade(H, mb, r, g - 1.0, zc, 'v2_wall_cream', g)
    for a_, b_ in zip(P, P[1:] + P[:1]):                # rusticated sandstone ground floor + string course
        d_ = b_ - a_
        if d_.length < 0.3:
            continue
        o_ = Vector((d_.y, -d_.x)).normalized()
        if C._area(r) < 0:
            o_ = -o_
        for z0, z1, mat, off in ((g - 0.5, g + 5.2, 'lm_rustic', 0.05), (g + 5.2, g + 5.6, 'plaster', 0.12), (zc - 0.9, zc, 'plaster', 0.18)):
            q = [Vector((*(a_ + o_ * off), z0)), Vector((*(b_ + o_ * off), z0)), Vector((*(b_ + o_ * off), z1)), Vector((*(a_ + o_ * off), z1))]
            if H_normal(q).to_2d().dot(o_) < 0:
                q.reverse()
            mb.poly(q, mat)
    C._roof_field(H, mb, [r], zc, 4.5, 'v2_roof_grey', slope=1.6)        # steep zinc mansard
    # front centre
    dmax = max((p - c).dot(f) for p in P)
    m = c + f * dmax
    gz = G(m.x, m.y)
    # porch: four columns carrying the terrace in front of the three arched entrances
    for s in (-6.0, -2.0, 2.0, 6.0):
        q = m + sd * s + f * 3.6
        _prism(mb, Vector((*q, gz - 0.2)), Vector((*q, gz + 5.3)), 0.42, 0.38, 'v2_stone_church', seg=10)
    for s in (-7.2, 7.2):                               # porch side piers
        q = m + sd * s + f * 1.8
        mb.box([tuple(q + sd * -0.6 + f * -1.8), tuple(q + sd * 0.6 + f * -1.8), tuple(q + sd * 0.6 + f * 1.8), tuple(q + sd * -0.6 + f * 1.8)],
               gz - 0.2, gz + 5.3, 'lm_rustic')
    deck = [m + sd * -7.8 - f * 0.2, m + sd * 7.8 - f * 0.2, m + sd * 7.8 + f * 4.2, m + sd * -7.8 + f * 4.2]
    mb.box([tuple(p) for p in deck], gz + 5.3, gz + 6.0, 'plaster')
    for a_, b_ in ((deck[1], deck[2]), (deck[2], deck[3]), (deck[3], deck[0])):     # terrace balustrade
        d_ = b_ - a_
        L = d_.length
        for j in range(int(L / 0.35)):
            p_ = a_ + d_ * ((j + 0.5) / int(L / 0.35))
            _prism(mb, Vector((*p_, gz + 6.0)), Vector((*p_, gz + 6.85)), 0.07, 0.07, 'plaster', seg=4)
        seg_box(mb, a_, b_, -0.15, 0.15, gz + 6.85, gz + 7.05, 'plaster')
    for k in range(3):                                  # dark arched entrance doors behind the porch
        q = m + sd * (-4.0 + k * 4.0) + f * 0.08
        mb.poly([Vector((*(q - sd * 1.2), gz)), Vector((*(q + sd * 1.2), gz)), Vector((*(q + sd * 1.2), gz + 3.6)), Vector((*(q - sd * 1.2), gz + 3.6))], 'lm_dark')
    # first-floor loggia: paired giant columns, recessed dark loggia, entablature
    lg = [m + sd * -6.5 + f * 0.06, m + sd * 6.5 + f * 0.06]
    mb.poly([Vector((*lg[0], gz + 6.0)), Vector((*lg[1], gz + 6.0)), Vector((*lg[1], gz + 12.6)), Vector((*lg[0], gz + 12.6))], 'lm_dark')
    for s in (-6.4, -5.6, -2.4, -1.6, 1.6, 2.4, 5.6, 6.4):
        q = m + sd * s + f * 1.0
        _prism(mb, Vector((*q, gz + 6.0)), Vector((*q, gz + 12.8)), 0.3, 0.26, 'plaster', seg=10)
    eb = [m + sd * -7.2 - f * 0.2, m + sd * 7.2 - f * 0.2, m + sd * 7.2 + f * 1.5, m + sd * -7.2 + f * 1.5]
    mb.box([tuple(p) for p in eb], gz + 12.8, gz + 14.0, 'plaster')
    # oval niches with the five busts, inscription band
    for k, s in enumerate((-5.6, -2.8, 0.0, 2.8, 5.6)):
        q = m + sd * s + f * 0.1
        ang = math.atan2(f.y, f.x)
        ellipsoid(mb, Vector((*q, gz + 15.6)), 0.12, 0.7, 0.9, ang, 0, 'plaster', subdiv=2)
        ellipsoid(mb, Vector((*(q + f * 0.08), gz + 15.6)), 0.1, 0.56, 0.76, ang, 0, 'v2_stone_church', subdiv=2)
        ellipsoid(mb, Vector((*(q + f * 0.3), gz + 15.7)), 0.3, 0.32, 0.45, ang, 0, 'v2_stone_church', subdiv=1)   # bust
    band = [m + sd * -6.0 + f * 0.2, m + sd * 6.0 + f * 0.2]
    mb.poly([Vector((*band[0], gz + 16.9)), Vector((*band[1], gz + 16.9)), Vector((*band[1], gz + 17.6)), Vector((*band[0], gz + 17.6))], 'v2_stone_church')
    # Thalia group on the gable over the centre
    for k, (s, h, w) in enumerate(((0.0, 2.6, 0.9), (-1.6, 1.6, 0.6), (1.6, 1.6, 0.6))):
        q = m + sd * s + f * 0.6
        ellipsoid(mb, Vector((*q, zc + 0.6 + h / 2)), w * 0.6, w, h / 2, math.atan2(f.y, f.x), 0, 'v2_iron', subdiv=1)
    # zinc dome over the front centre with oculus dormers and finial
    dc = m - f * 7.5
    _lathe(mb, Vector, dc, [(8.2, zc), (8.4, zc + 0.6), (7.9, zc + 3.0), (6.8, zc + 5.6), (4.8, zc + 7.8),
                            (2.0, zc + 9.2), (0.6, zc + 9.6), (0.0, zc + 9.7)], lambda *a: 'zinc', seg=24)
    for k in range(6):
        a0 = math.atan2(f.y, f.x) + (k - 2.5) * 0.5
        q = dc + Vector((math.cos(a0), math.sin(a0))) * 7.6
        ellipsoid(mb, Vector((*q, zc + 2.6)), 0.25, 0.75, 0.75, a0, 0, 'plaster', subdiv=1)
        ellipsoid(mb, Vector((*(q + Vector((math.cos(a0), math.sin(a0))) * 0.15), zc + 2.6)), 0.15, 0.5, 0.5, a0, 0, 'lm_dark', subdiv=1)
    _prism(mb, Vector((dc.x, dc.y, zc + 9.6)), Vector((dc.x, dc.y, zc + 12.0)), 0.15, 0.03, 'zinc', seg=6)
    # stage house behind the auditorium
    dmin = min((p - c).dot(f) for p in P)
    sh = c + f * (dmin + 9.0)
    base = [sh + sd * -11 - f * 7, sh + sd * 11 - f * 7, sh + sd * 11 + f * 7, sh + sd * -11 + f * 7]
    mb.box([tuple(p) for p in base], zc - 1.0, g + 25.0, 'v2_wall_cream')
    ridge0, ridge1 = sh - f * 7, sh + f * 7
    for sg in (-1, 1):
        q = [Vector((*(base[0 if sg < 0 else 1]), g + 25.0)), Vector((*(base[3 if sg < 0 else 2]), g + 25.0)),
             Vector((*ridge1, g + 29.0)), Vector((*ridge0, g + 29.0))]
        if H_normal(q).z < 0:
            q.reverse()
        mb.poly(q, 'v2_roof_grey')
    for e_ in ((base[0], base[1], ridge0), (base[3], base[2], ridge1)):
        q = [Vector((*e_[0], g + 25.0)), Vector((*e_[1], g + 25.0)), Vector((*e_[2], g + 29.0))]
        mb.poly(q, 'v2_wall_cream')
    print('v2_landmarks SND: front at', tuple(round(x, 1) for x in m), 'depth', round(dmax - dmin, 1))
    return mb.build(coll)


# ---------------------------------------------------------------- Primacialny palac
def primate(H, special, G, coll):
    """Attic balustrade with statues and vases, pediment with the black cast-iron cardinal's hat (moved from
    v2_city), plus the portico of four ochre columns carrying the balcony (photo primacialny_main_facade)."""
    import v2_city as C
    _materials(H)
    Vector, seg_box, ellipsoid, _prism = H['Vector'], H['seg_box'], H['ellipsoid'], H['_prism']
    mb = C.VChunk(H, 'V2LM_Primate|-col', 'V2LM_Primate|-col', 1e5, 1e5)
    # --- Primate's Palace: statues and vases on the attic of the main (north) front, pediment with the
    # cardinal's hat over the central risalit
    if C.PRIMATE_PALACE in C.DECOR:
        r, gnd, wt = C.DECOR[C.PRIMATE_PALACE]
        cc_ = sum((Vector(p) for p in r), Vector((0, 0))) / len(r)
        front = []
        for p0, p1 in zip(r, r[1:] + r[:1]):
            p0, p1 = Vector(p0), Vector(p1)
            L = (p1 - p0).length
            nrm = Vector(((p1 - p0).y, -(p1 - p0).x)) / max(L, 1e-6)        # outward for a CCW ring
            if L > 2.0 and nrm.y > 0.6:
                front.append((p0, p1, nrm, L))
        for p0, p1, nrm, L in front:
            seg_box(mb, p0, p1, -0.5, 0.2, wt - 0.2, wt + 1.1, 'plaster')            # attic balustrade
            for k in range(int(L // 4.5)):
                q = p0.lerp(p1, (k + 0.5) / int(L // 4.5)) - nrm * 0.15
                _prism(mb, Vector((q.x, q.y, wt + 1.1)), Vector((q.x, q.y, wt + 1.6)), 0.3, 0.3, 'v2_stone_church', seg=4)
                ellipsoid(mb, Vector((q.x, q.y, wt + 2.35)), 0.28, 0.28, 0.75, 0, 0, 'v2_stone_church', subdiv=1)
        if front:
            p0, p1, nrm, L = max(front, key=lambda f: f[3])
            m_ = (p0 + p1) / 2 - nrm * 0.1
            u = (p1 - p0).normalized()
            for off in (0.0, -0.6):
                c0 = m_ + nrm * off
                tri = [Vector((*(c0 - u * 8.5), wt + 1.1)), Vector((*(c0 + u * 8.5), wt + 1.1)), Vector((*c0, wt + 5.0))]
                mb.poly(tri if off == 0 else list(reversed(tri)), 'plaster')
            ellipsoid(mb, Vector((m_.x, m_.y, wt + 5.25)), 1.3, 1.3, 0.22, 0, 0, 'lm_dark', subdiv=2)   # cardinal's hat (150 kg)
            ellipsoid(mb, Vector((m_.x, m_.y, wt + 5.55)), 0.6, 0.6, 0.4, 0, 0, 'lm_dark', subdiv=1)
            # portico: four ochre columns on the square carrying the balcony of the central risalit
            gz = G(m_.x, m_.y)
            for s_ in (-4.2, -1.6, 1.6, 4.2):
                q = m_ + u * s_ + nrm * 3.0
                _prism(mb, Vector((*q, gz - 0.2)), Vector((*q, gz + 6.4)), 0.48, 0.42, 'v2_render_ochre', seg=10)
                mb.box([tuple(q + u * -0.6 + nrm * -0.6), tuple(q + u * 0.6 + nrm * -0.6), tuple(q + u * 0.6 + nrm * 0.6),
                        tuple(q + u * -0.6 + nrm * 0.6)], gz - 0.2, gz + 0.6, 'v2_render_ochre')
            bal = [m_ + u * -5.2 + nrm * 0.1, m_ + u * 5.2 + nrm * 0.1, m_ + u * 5.2 + nrm * 3.8, m_ + u * -5.2 + nrm * 3.8]
            mb.box([tuple(q) for q in bal], gz + 6.4, gz + 7.2, 'v2_render_ochre')
            for a_, b_ in ((bal[1], bal[2]), (bal[2], bal[3]), (bal[3], bal[0])):
                d_ = b_ - a_
                for j in range(int(d_.length / 0.35)):
                    p_ = a_ + d_ * ((j + 0.5) / int(d_.length / 0.35))
                    _prism(mb, Vector((*p_, gz + 7.2)), Vector((*p_, gz + 8.0)), 0.07, 0.07, 'v2_render_ochre', seg=4)
                seg_box(mb, a_, b_, -0.15, 0.15, gz + 8.0, gz + 8.2, 'v2_render_ochre')
            mb.poly([Vector((*(m_ - u * 1.6 + nrm * 0.15), gz)), Vector((*(m_ + u * 1.6 + nrm * 0.15), gz)),
                     Vector((*(m_ + u * 1.6 + nrm * 0.15), gz + 4.6)), Vector((*(m_ - u * 1.6 + nrm * 0.15), gz + 4.6))], 'lm_dark')   # gateway
    return mb.build(coll) if mb.parts else []


# ---------------------------------------------------------------- Reduta
REDUTA_ID = 56305202


def reduta(H, special, G, coll):
    """Neo-baroque concert hall (photos reduta_from_stura_square, reduta_facade_01): cream walls with three tall
    storeys and round-arched ground-floor windows, dark slate mansard with oval dormers, the ribbed dark cupola over
    the rounded corner toward Namestie L. Stura, green-roofed corner turrets and urns on the gables."""
    if REDUTA_ID not in special:
        return []
    import v2_city as C
    _materials(H)
    Vector, ellipsoid, _prism = H['Vector'], H['ellipsoid'], H['_prism']
    mb = C.VChunk(H, 'V2LM_Reduta|-col', 'V2LM_Reduta|-col', 1e5, 1e5)
    t, r, cx, cy = special[REDUTA_ID]
    c = Vector((cx, cy))
    P = [Vector(p) for p in r]
    g = min(G(p.x, p.y) for p in P)
    zc = g + 19.0
    C._facade(H, mb, r, g - 1.0, zc, 'v2_wall_cream', g, fh=6.2)
    ccw = C._area(r) > 0
    for a_, b_ in zip(P, P[1:] + P[:1]):
        d_ = b_ - a_
        L = d_.length
        if L < 0.3:
            continue
        o_ = Vector((d_.y, -d_.x)).normalized() * (1 if ccw else -1)
        for z0, z1, off in ((zc - 1.0, zc, 0.25), (g + 6.0, g + 6.4, 0.12)):          # cornice, string course
            q = [Vector((*(a_ + o_ * off), z0)), Vector((*(b_ + o_ * off), z0)), Vector((*(b_ + o_ * off), z1)), Vector((*(a_ + o_ * off), z1))]
            if H_normal(q).to_2d().dot(o_) < 0:
                q.reverse()
            mb.poly(q, 'plaster')
    C._roof_field(H, mb, [r], zc, 6.5, 'v2_roof_dark', slope=1.7)                    # steep slate mansard
    # oval dormers round the mansard
    for a_, b_ in zip(P, P[1:] + P[:1]):
        d_ = b_ - a_
        L = d_.length
        if L < 8.0:
            continue
        o_ = Vector((d_.y, -d_.x)).normalized() * (1 if ccw else -1)
        for k in range(int(L / 6.0)):
            q = a_ + d_ * ((k + 0.5) / int(L / 6.0)) - o_ * 0.9
            ang = math.atan2(o_.y, o_.x)
            ellipsoid(mb, Vector((*q, zc + 1.6)), 0.5, 0.7, 0.6, ang, 0, 'plaster', subdiv=1)
            ellipsoid(mb, Vector((*(q + o_ * 0.3), zc + 1.6)), 0.25, 0.45, 0.38, ang, 0, 'lm_dark', subdiv=1)
    # the rounded corner toward Namestie L. Stura: drum + ribbed dark cupola with lantern
    sq = Vector((690.0, -215.0))
    k0 = min(range(len(P)), key=lambda i: (P[i] - sq).length)
    cc = c + (P[k0] - c) * 0.82
    _lathe(mb, Vector, cc, [(5.2, zc + 2.0), (5.2, zc + 5.0)], lambda *a: 'plaster', seg=16)          # drum
    _lathe(mb, Vector, cc, [(5.6, zc + 5.0), (5.2, zc + 6.6), (4.2, zc + 8.4), (2.4, zc + 9.8), (1.2, zc + 10.3)],
           lambda *a: 'v2_slate', seg=16)
    for k in range(8):
        a0 = 2 * math.pi * k / 8
        q = cc + Vector((math.cos(a0), math.sin(a0))) * 5.25
        ellipsoid(mb, Vector((*q, zc + 3.5)), 0.12, 0.55, 0.8, a0, 0, 'lm_dark', subdiv=1)              # drum windows
    _lathe(mb, Vector, cc, [(1.2, zc + 10.3), (1.2, zc + 11.6), (1.5, zc + 11.8), (0.0, zc + 12.8)], lambda *a: 'v2_slate', seg=8)
    _prism(mb, Vector((cc.x, cc.y, zc + 12.8)), Vector((cc.x, cc.y, zc + 15.0)), 0.08, 0.03, 'v2_iron', seg=4)
    # green corner turrets on the two corners farthest along the long sides, urns on the gables
    far = sorted(range(len(P)), key=lambda i: -(P[i] - c).length)
    used = []
    for i in far:
        if len(used) >= 2:
            break
        if any((P[i] - P[j]).length < 25 for j in used + [k0]):
            continue
        used.append(i)
        q = c + (P[i] - c) * 0.9
        _lathe(mb, Vector, q, [(2.2, zc + 1.0), (2.2, zc + 3.5), (2.4, zc + 3.7), (1.6, zc + 5.6), (0.3, zc + 7.2)],
               lambda *a: 'v2_copper', seg=8)
        _prism(mb, Vector((q.x, q.y, zc + 7.2)), Vector((q.x, q.y, zc + 8.2)), 0.06, 0.03, 'v2_iron', seg=4)
    print('v2_landmarks Reduta: cupola corner', tuple(round(x, 1) for x in cc), 'turrets', len(used))
    return mb.build(coll)


# ---------------------------------------------------------------- Kostol klarisiek: pentagonal tower
def klarisky(H, special, G, coll):
    """c. 1400 pentagonal sandstone tower (photo klarisky_tower_full) that does not reach the ground: it springs
    from a massive buttress on the side wall through a stepped corbel, has a lancet stage, a pinnacled belfry with
    gables and gargoyles, and a crocketed stone spire with a finial."""
    import v2_city as C
    if C.CLARISSE not in C.DECOR:
        return []
    _materials(H)
    Vector, _prism = H['Vector'], H['_prism']
    mb = H['MB']('V2LM_Klarisky')
    r, gnd, wt = C.DECOR[C.CLARISSE]
    c = Vector((390.0, 162.5))
    g = G(c.x, c.y)
    rad = 2.6
    mat = 'v2_stone_church'
    def ring(rr, rot=0.3):
        return [c + Vector((math.cos(2 * math.pi * k / 5 + rot), math.sin(2 * math.pi * k / 5 + rot))) * rr for k in range(5)]
    def prism5(rr0, rr1, z0, z1):
        A, B = ring(rr0), ring(rr1)
        for k in range(5):
            j = (k + 1) % 5
            q = [Vector((*A[k], z0)), Vector((*A[j], z0)), Vector((*B[j], z1)), Vector((*B[k], z1))]
            if H_normal(q).to_2d().dot((A[k] + A[j]) / 2 - c) < 0:
                q.reverse()
            mb.poly(q, mat)
    zb = g + 13.0                                     # buttress top / corbel
    _prism(mb, Vector((c.x, c.y, g - 0.5)), Vector((c.x, c.y, zb - 1.5)), rad * 0.8, rad * 0.75, mat, seg=5)   # buttress (narrower: the tower is corbelled out)
    prism5(rad * 1.15, rad * 1.25, zb - 1.5, zb - 0.8)                                                       # stepped corbel
    prism5(rad * 1.25, rad * 1.05, zb - 0.8, zb)
    prism5(rad, rad, zb, g + 26.0)                                                                           # lancet stage
    for k, (z0, z1) in enumerate(((zb + 3.0, zb + 6.5), (g + 22.0, g + 25.0))):
        for a_, b_ in zip(ring(rad), ring(rad)[1:] + ring(rad)[:1]):
            m_ = (a_ + b_) / 2
            out_ = (m_ - c).normalized()
            dd = (b_ - a_).normalized()
            C._gothic_window(H, mb, m_ + out_ * 0.02, dd, out_, z0, z1, 0.45)
    prism5(rad * 1.12, rad * 1.12, g + 26.0, g + 26.5)                                                       # tracery band
    zt = g + 30.0
    for a_, b_ in zip(ring(rad), ring(rad)[1:] + ring(rad)[:1]):                                              # gables over the belfry
        m_ = (a_ + b_) / 2
        out_ = (m_ - c).normalized()
        tri = [Vector((*(a_ + out_ * 0.1), zt)), Vector((*(b_ + out_ * 0.1), zt)), Vector((*(m_ + out_ * 0.1), zt + 2.6))]
        if H_normal(tri).to_2d().dot(out_) < 0:
            tri.reverse()
        mb.poly(tri, mat)
    prism5(rad, rad * 0.95, g + 26.5, zt)                                                                    # belfry
    for q_ in ring(rad * 1.05):                                                                              # corner pinnacles + gargoyles
        _prism(mb, Vector((*q_, g + 26.0)), Vector((*q_, zt + 1.2)), 0.3, 0.26, mat, seg=4)
        _prism(mb, Vector((*q_, zt + 1.2)), Vector((*q_, zt + 3.4)), 0.3, 0.02, mat, seg=4)
        o_ = (q_ - c).normalized()
        _prism(mb, Vector((*q_, g + 26.3)), Vector((*(q_ + o_ * 1.0), g + 26.6)), 0.14, 0.1, mat, seg=4)
    zs1 = g + 41.0                                                                                           # crocketed spire
    prism5(rad * 0.95, 0.12, zt, zs1)
    for k in range(7):
        zz = zt + 1.0 + k * (zs1 - zt - 2.0) / 7
        rr = rad * 0.95 * (1 - (zz - zt) / (zs1 - zt))
        for q_ in ring(rr + 0.12):
            _prism(mb, Vector((*q_, zz)), Vector((*q_, zz + 0.35)), 0.11, 0.04, mat, seg=4)
    _prism(mb, Vector((c.x, c.y, zs1 - 0.2)), Vector((c.x, c.y, zs1 + 1.2)), 0.35, 0.05, mat, seg=5)         # finial
    print('v2_landmarks Klarisky tower: corbel', round(zb - g, 1), 'spire', round(zs1 - g, 1))
    return [mb.build(coll)]
