"""V2 palace interior: room roles per storey and their furnishing.

Called from build_palace() right after furnish():  build(H, P, coll)
  H = build_castle globals (helpers, constants), P = build_palace locals (rooms, W, tower_sq, ...).

Roles (rooms are per wing; each storey gets its own role):
  ground  : Knights' Hall bays (south wing, open arcade) - groin-vault ribs, armour, banners
  1st     : south wing state rooms - crimson damask, star parquet, rugs, curtains, salon chairs
  2nd     : the largest west-wing room is the Music Hall (harpsichord, chairs); others exhibition
            halls with rope barriers and info panels
  3rd     : picture gallery - salon hang, benches
  all     : curtains and wall sconces in every furnished room; Crown Tower treasury extras
"""
import math
import os
import random

import numpy as np

ROLE_COLORS = {
    'state': ('#7E2426', '#A8483C'),
    'music': ('#4E6E6A', '#7E9C92'),
    'exhibit': ('#5E6B48', '#808C66'),
    'gallery': ('#4A5468', '#6E7A92'),
    'gallery2': ('#8A6A3A', '#AE8C55'),
}


def build(H, P, coll):
    V = Context(H, P)
    V.setup_materials()
    V.assign_roles()
    for zi in range(len(H['FLOOR_Z'])):
        for r in V.rooms:
            if r['special'] or r['stair']:
                continue
            V.furnish_room(r, zi)
    for r in V.rooms:
        if r['passage']:
            V.entrance_vault(r)
    V.knights_hall()
    V.treasury()
    V.stair_materials()
    V.staircase()
    V.cellar_reveals()
    V.cellar_fittings()
    V.corridors()
    V.crown_tower()
    out = [V.deco.build(coll), V.solid.build(coll)]
    print('V2 interior: roles', {k: sum(1 for v in V.roles.values() if v == k) for k in set(V.roles.values())},
          'polys deco', len(V.deco.faces), 'solid', len(V.solid.faces))
    return out


class Context:
    def __init__(self, H, P):
        self.H, self.P = H, P
        self.V = H['Vector']
        self.rooms = P['rooms']
        self.W = P['W']
        self.FZ = H['FLOOR_Z']
        self.EAVE = H['EAVE_Z']
        self.SLAB = H['SLAB_T']
        self.PART = H['PART_T']
        self.deco = H['MB']('Palace_Furnishing_V2')          # no collision (name contains Furnishing)
        self.solid = H['MB']('Palace_Furniture_V2-col')       # chairs, harpsichord, armour plinths
        self.rng = random.Random(2026)
        self.roles = {}
        self.windows = self._window_points()

    # ------------------------------------------------------------ materials
    def _tex(self, name, gen):
        tx = self.H['textures']
        path = os.path.join(self.H['TEX'], name + '.png')
        img = tx._save(path, gen)
        return img

    def setup_materials(self):
        H, tx = self.H, self.H['textures']
        rng = np.random.default_rng(31)
        n = 256 if H['WEB'] else 512
        mk = H['make_mat']
        for role, (b, hi) in ROLE_COLORS.items():
            nm = 'damask_' + role
            if nm not in H['MATS']:
                mk(nm, self._tex(nm, tx.damask(n, rng, b, hi)), uv=1.2, rough=0.55, spec=0.45)
        for nm, c in (('velvet_red', '#6E1E22'), ('velvet_green', '#2E4A3A'), ('velvet_blue', '#2A3550'), ('velvet_gold', '#8A6A2E')):
            if nm not in H['MATS']:
                mk(nm, self._tex(nm, tx.velvet(n, rng, c)), uv=1.0, rough=0.8)
                H['MATS'][nm].use_backface_culling = False
        if 'rug' not in H['MATS']:
            mk('rug', self._tex('rug', tx.rug(n, rng)), uv=1.0, rough=0.95)
            mk('parquet_star', self._tex('parquet_star', tx.parquet_star(n, rng)), uv=2.0, rough=0.4, spec=0.5)
            for nm, c1, c2 in (('banner_a', '#7A1E1C', '#E8D9B0'), ('banner_b', '#1E3A6A', '#E8D9B0'), ('banner_c', '#2E5A2E', '#C9A45C')):
                mk(nm, self._tex(nm, tx.banner(256, rng, c1, c2)), uv=1.0, rough=0.85)
                m = H['MATS'][nm]
                bs = next(x for x in m.node_tree.nodes if x.type == 'BSDF_PRINCIPLED')
                tn = next(x for x in m.node_tree.nodes if x.type == 'TEX_IMAGE')
                m.node_tree.links.new(tn.outputs['Alpha'], bs.inputs['Alpha'])
                m.use_backface_culling = False
                try:
                    m.surface_render_method = 'DITHERED'
                except Exception:
                    m.blend_method = 'CLIP'
            mk('steel', None, color=(0.62, 0.63, 0.65), rough=0.25, metal=1.0)
            mk('ebony', None, color=(0.05, 0.04, 0.04), rough=0.25, spec=0.6)
            mk('ivory', None, color=(0.92, 0.89, 0.8), rough=0.35)
            mk('rope_red', None, color=(0.55, 0.06, 0.08), rough=0.8)
            mk('panel_board', None, color=(0.18, 0.2, 0.24), rough=0.5)
            mk('panel_text', None, color=(0.86, 0.84, 0.78), rough=0.6)
            mk('upholstery', None, color=(0.55, 0.12, 0.14), rough=0.85)
        for k, nm in enumerate(('paint_port', 'paint_port2')):   # varnish-dark 3/4 portraits instead of the mask-like faces
            m = H['MATS'].get(nm)
            tn = next((x for x in m.node_tree.nodes if x.type == 'TEX_IMAGE'), None) if m else None
            if tn:
                tn.image = self._tex(nm + '_v2', tx.portrait_dark(512, rng, seed=k + 3))
        if 'planks_old' not in H['MATS']:
            mk('planks_old', self._tex('planks_old', tx.planks_old(512, rng)), uv=1.5, rough=0.85)
            mk('steel_frame', None, color=(0.08, 0.085, 0.09), rough=0.5, metal=0.7)
        if 'wall_dark' not in H['MATS']:
            mk('wall_dark', None, color=(0.025, 0.03, 0.04), rough=0.9)
        for nm, colr, rough in (('carpet_navy', (0.012, 0.016, 0.045), 0.95), ('sandstone', (0.55, 0.42, 0.24), 0.85),
                                ('map_paper', (0.62, 0.55, 0.4), 0.8), ('map_land', (0.3, 0.38, 0.22), 0.8)):
            if nm not in H['MATS']:
                mk(nm, None, color=colr, rough=rough)

    # ------------------------------------------------------------ roles
    def wing_of(self, r):
        for w in self.W:
            if (r['n'] - w['n']).length < 1e-6:
                return w['name']
        return '?'

    def assign_roles(self):
        H = self.H
        hall_pts = H.get('HALL_PARTS', [])
        hall = [r for r in self.rooms if any((r['wall_a'] - hp).length < 0.6 or (r['wall_b'] - hp).length < 0.6 for hp in hall_pts)]
        self.hall_rooms = hall
        north = [r for r in self.rooms if not r['special'] and r['n'].y > 0.9]     # same pick as build_castle.exhibits()
        music = max(north, key=lambda r: r['L'] * r['D']) if north else None
        for r in self.rooms:
            wing = self.wing_of(r)
            self.roles[(id(r), 0)] = 'hall' if r in hall else 'ground'
            self.roles[(id(r), 1)] = 'state' if id(r) in H.get('STATE_ROOMS', ()) else ('music' if r is music else 'exhibit')
            self.roles[(id(r), 2)] = 'exhibit_dark' if (wing in ('S', 'N') and int(abs(r['c'].x) / 7) % 3 == 1) else 'exhibit'
            self.roles[(id(r), 3)] = 'gallery' if (wing in ('S', 'N')) else 'gallery2'
        H['ROOM_ROLES'] = self.roles
        if music is not None:
            H['NAV']['music_hall'] = list(music['c'])
        south = [r for r in self.rooms if not r['special'] and not r['stair'] and self.wing_of(r) == 'S' and r not in hall]
        if south:
            r = max(south, key=lambda r: r['L'] * r['D'])
            cam = r['c'] - r['n'] * (r['D'] * 0.38) - r['d'] * (r['L'] * 0.42)
            tgt = r['c'] + r['n'] * (r['D'] * 0.3) + r['d'] * (r['L'] * 0.45)
            H['NAV']['south_room_cam'] = [cam.x, cam.y]
            H['NAV']['south_room_tgt'] = [tgt.x, tgt.y]

    # ------------------------------------------------------------ geometry helpers
    def _window_points(self):
        """Real outer-wall window openings per storey, following build_palace's FACADES rules
        (same jitter seed, blank/skip/blind lists, gateway and door axes excluded)."""
        H, V = self.H, self.V
        FAC = H.get('FACADES')
        sill = [1.1, 1.0, 1.0, 1.0]
        pts = []
        pas = {'S': 0.5, 'N': 0.5}
        for wi, w in enumerate(self.W):
            o0, o1 = w['o']
            Lo = (o1 - o0).length
            d_o = (o1 - o0) / Lo
            n_o = V((-d_o.y, d_o.x))
            ts0, ts1 = H['TOWER_SIZE'][wi], H['TOWER_SIZE'][(wi + 1) % 4]
            if not FAC:
                continue
            fac = FAC[w['name']]
            span0, span1 = ts0 + fac['margin'], Lo - ts1 - fac['margin']
            nax = fac['n']
            sp = (span1 - span0) / nax
            jr = random.Random(wi * 31)
            ax = [span0 + sp * (k + 0.5) + (jr.uniform(-1, 1) * fac.get('jitter', 0.0)) for k in range(nax)]
            pas_axis = min(ax, key=lambda u: abs(u - pas[w['name']] * Lo)) if w['name'] in pas else None
            for k in range(len(self.FZ)):
                z0 = self.FZ[k]
                for ai, u in enumerate(ax):
                    if pas_axis is not None and abs(u - pas_axis) < 1e-6 and k in (0, 1):
                        continue
                    if k in fac.get('blank', ()) or (k, ai) in fac.get('skip', set()) or (k, ai) in fac.get('blind', set()):
                        continue
                    if w['name'] == 'S' and k == 0 and pas_axis is not None and abs(abs(u - pas_axis) - sp) < 1e-6:
                        continue
                    zs = z0 + sill[k]
                    pts.append(dict(wing=w['name'], k=k, p=o0 + d_o * u + n_o * H['OUTER_T'], d=d_o, n=n_o,
                                    w=fac['w'], z0=zs, z1=zs + fac['h'][k]))
        return pts

    def room_windows(self, r, zi):
        wing = self.wing_of(r)
        a, b = r['far_a'], r['far_b']
        ab = b - a
        L2 = ab.length_squared
        if L2 < 1e-6:
            return []
        L = math.sqrt(L2)
        res = []
        for wp in self.windows:
            if wp['wing'] != wing or wp['k'] != zi:
                continue
            t = (wp['p'] - a).dot(ab) / L2
            if 0.05 < t < 0.95 and abs((wp['p'] - a).cross(ab)) / L < 1.5:
                res.append(wp)
        return res

    def is_partition(self, pt, r):
        """wall_a/wall_b at the ends of a wing's corridor line are open corners, not partitions."""
        return sum(1 for r2 in self.rooms if (r2['n'] - r['n']).length < 1e-6 and
                   min((r2['wall_a'] - pt).length, (r2['wall_b'] - pt).length) < 0.05) >= 2

    def partitions(self, r):
        out = []
        for wa, fa, inward in ((r['wall_a'], r['far_a'], r['d']), (r['wall_b'], r['far_b'], -r['d'])):
            if self.is_partition(wa, r):
                out.append((wa, fa, inward))
        return out

    def ceil(self, zi):
        z1 = self.FZ[zi + 1] if zi + 1 < len(self.FZ) else self.EAVE
        return z1 - self.SLAB

    def room_quad(self, r, inset=0.05):
        V = self.V
        n, d = r['n'], r['d']
        half = self.PART / 2 + 0.02 + inset
        a = r['wall_a'] + n * half + d * half
        b = r['wall_b'] + n * half - d * half
        fa = r['far_a'] - n * inset + d * half
        fb = r['far_b'] - n * inset - d * half
        return [a, b, fb, fa]

    # ------------------------------------------------------------ per room
    def furnish_room(self, r, zi):
        role = self.roles.get((id(r), zi), 'ground')
        z0, ceil = self.FZ[zi], self.ceil(zi)
        if zi > 0 or role == 'hall':
            self.curtains(r, zi, role)
        self.window_niches(r, zi)
        if role == 'state':                                   # museum rooms stay white (refs 32/33); damask only in the 2 state rooms
            self.damask_panels(r, z0, ceil, 'damask_' + role)
        elif role == 'exhibit_dark':                          # darkened exhibition room
            self.damask_panels(r, z0, ceil, 'wall_dark', dark=True)
        if role != 'ground':
            self.sconces(r, z0)
        if role == 'state':
            self.floor_overlay(r, z0, 'parquet_star')
            self.rug(r, z0)
            self.salon_suite(r, z0)
        elif role == 'music':
            self.floor_overlay(r, z0, 'parquet_star')
            self.music_hall(r, z0)
        elif role == 'exhibit':
            self.rope_barriers(r, z0)
            self.info_panel(r, z0)
        elif role == 'exhibit_dark':
            self.dark_exhibition(r, z0)
            self.info_panel(r, z0)
        elif role in ('gallery', 'gallery2'):
            self.salon_hang(r, z0)
            self.gallery_bench(r, z0)

    def curtains(self, r, zi, role):
        H, V = self.H, self.V
        mat = {'state': 'velvet_red', 'music': 'velvet_green', 'gallery': 'velvet_blue', 'hall': 'velvet_red'}.get(role, 'velvet_gold')
        z0 = self.FZ[zi]
        for wp in self.room_windows(r, zi):
            p, d_o, n_o = wp['p'], wp['d'], wp['n']
            top = wp['z1'] + 0.35
            half_w = wp['w'] / 2
            face = p + n_o * 0.14
            for sgn in (-1, 1):                       # two pleated drapes framing the window
                c = face + d_o * (sgn * (half_w + 0.25))
                for k in range(6):                    # pleats: zig-zag strips
                    u0, u1 = (k - 3) * 0.085, (k - 2) * 0.085
                    o0, o1 = (0.05 if k % 2 else -0.04), (-0.04 if k % 2 else 0.05)
                    p0 = c + d_o * u0 + n_o * o0
                    p1 = c + d_o * u1 + n_o * o1
                    self.deco.poly([V((p0.x, p0.y, z0 + 0.02)), V((p1.x, p1.y, z0 + 0.02)), V((p1.x, p1.y, top)), V((p0.x, p0.y, top))],
                                   mat, uv=[(u0 * 2, 0), (u1 * 2, 0), (u1 * 2, 3), (u0 * 2, 3)])
            a, b = face - d_o * (half_w + 0.6), face + d_o * (half_w + 0.6)   # pelmet with gilded edge
            H['seg_box'](self.deco, a, b, -0.02, 0.16, top, top + 0.32, mat)
            H['seg_box'](self.deco, a, b, -0.03, 0.17, top - 0.03, top, 'gold')
            H['_prism'](self.deco, V((a.x, a.y, top - 0.1)), V((b.x, b.y, top - 0.1)), 0.015, 0.015, 'gold', seg=6)

    def damask_panels(self, r, z0, ceil, mat, dark=False):
        """Silk wall panels in gilded frames between dado and cornice, avoiding doors."""
        H, V = self.H, self.V
        half = self.PART / 2 + 0.02
        z_lo, z_hi = (z0 + 0.03, ceil - 0.32) if dark else (z0 + 1.2, ceil - 0.62)
        for a, b, inward in self.partitions(r):
            L = (b - a).length
            if L < 1.0:
                continue
            dvec = (b - a) / L
            door_u = L * 0.72                           # partition enfilade door
            spans = [(0.4, door_u - 1.05), (door_u + 1.05, L - 0.6)]
            for s0, s1 in spans:
                self._panels_along(a + inward * half, dvec, inward, s0, s1, z_lo, z_hi, mat, dark)
        a, b = r['wall_a'] + r['n'] * half, r['wall_b'] + r['n'] * half   # corridor wall (door in the middle)
        L = (b - a).length
        if L < 1.0:
            return
        dvec = (b - a) / L
        for s0, s1 in ((0.5, L / 2 - 1.0), (L / 2 + 1.0, L - 0.5)):
            self._panels_along(a, dvec, r['n'], s0, s1, z_lo, z_hi, mat, dark)

    def _panels_along(self, base, dvec, inward, s0, s1, z_lo, z_hi, mat, dark=False):
        H, V = self.H, self.V
        if s1 - s0 < 0.9:
            return
        n_p = max(1, int((s1 - s0) / 2.4))
        w = (s1 - s0) / n_p
        for k in range(n_p):
            a = base + dvec * (s0 + k * w + 0.12)
            b = base + dvec * (s0 + (k + 1) * w - 0.12)
            q = [V((a.x, a.y, z_lo)), V((b.x, b.y, z_lo)), V((b.x, b.y, z_hi)), V((a.x, a.y, z_hi))]
            off = V((inward.x, inward.y, 0)) * 0.006
            H['oriented_poly'](self.deco, [p + off for p in q], V((inward.x, inward.y, 0)), mat,
                               uv=[(0, 0), ((b - a).length / 1.2, 0), ((b - a).length / 1.2, (z_hi - z_lo) / 1.2), (0, (z_hi - z_lo) / 1.2)])
            if dark:
                continue
            for e0, e1, h0, h1 in ((a, b, z_lo - 0.05, z_lo), (a, b, z_hi, z_hi + 0.05), (a, a + dvec * 0.05, z_lo, z_hi), (b - dvec * 0.05, b, z_lo, z_hi)):
                self.deco.box([e0, e1, e1 + inward * 0.03, e0 + inward * 0.03], h0, h1, 'gold')

    def sconces(self, r, z0):
        """Gilded two-arm wall sconces on the partitions."""
        H, V = self.H, self.V
        half = self.PART / 2 + 0.02
        for wa, fa, inward in self.partitions(r):
            if (fa - wa).length < 1.0:
                continue
            if z0 < 1.0 and any(r2['passage'] and min((r2['wall_a'] - wa).length, (r2['wall_b'] - wa).length) < 0.05 for r2 in self.rooms):
                continue                                    # gate passage wall with the exposed Gothic portal
            for t in (0.2, 0.92):
                p = wa.lerp(fa, t) + inward * half
                zc = z0 + 2.3
                self.deco.box([p - (fa - wa).normalized() * 0.06, p + (fa - wa).normalized() * 0.06,
                               p + (fa - wa).normalized() * 0.06 + inward * 0.04, p - (fa - wa).normalized() * 0.06 + inward * 0.04],
                              zc - 0.15, zc + 0.15, 'gold')
                tg = (fa - wa).normalized()
                for sgn in (-1, 1):
                    tip = p + inward * 0.22 + tg * (sgn * 0.16)
                    H['_prism'](self.deco, V((p.x, p.y, zc)), V((tip.x, tip.y, zc + 0.12)), 0.01, 0.01, 'gold', seg=5)
                    H['_prism'](self.deco, V((tip.x, tip.y, zc + 0.12)), V((tip.x, tip.y, zc + 0.27)), 0.012, 0.012, 'candle', seg=6)
                    H['ellipsoid'](self.deco, V((tip.x, tip.y, zc + 0.3)), 0.01, 0.01, 0.022, 0, 0, 'lamp', subdiv=0)

    def floor_overlay(self, r, z0, mat):
        q = self.room_quad(r, 0.1)
        V = self.V
        self.deco.poly([V((p.x, p.y, z0 + 0.004)) for p in q], mat)

    def rug(self, r, z0):
        V = self.V
        c, n, d = r['c'], r['n'], r['d']
        hl, hd = r['L'] * 0.17, r['D'] * 0.17
        q = [c - d * hl - n * hd, c + d * hl - n * hd, c + d * hl + n * hd, c - d * hl + n * hd]
        self.deco.poly([V((p.x, p.y, z0 + 0.012)) for p in q], 'rug', uv=[(0, 0), (1, 0), (1, 1), (0, 1)])

    def chair(self, p, face_dir, z0, mat='upholstery'):
        """Baroque side chair: carved legs, upholstered seat and back (collidable seat box)."""
        H, V = self.H, self.V
        f = face_dir.normalized()
        s = V((-f.y, f.x))
        q = lambda c, a, b: [c - f * a - s * b, c + f * a - s * b, c + f * a + s * b, c - f * a + s * b]
        wood = 'door'
        self.solid.box(q(p, 0.22, 0.23), z0 + 0.4, z0 + 0.45, wood)                  # seat frame (collidable)
        self.deco.box(q(p + f * 0.01, 0.2, 0.21), z0 + 0.45, z0 + 0.49, mat)          # upholstered seat
        H['ellipsoid'](self.deco, V((p.x, p.y, z0 + 0.49)), 0.19, 0.2, 0.025, math.atan2(f.y, f.x), 0, mat, subdiv=1)
        bk = p - f * 0.2
        for sy in (-1, 1):                                                           # thin back stiles, slightly raked
            sp = bk + s * (sy * 0.2)
            H['_prism'](self.deco, V((sp.x, sp.y, z0 + 0.45)), V(((sp - f * 0.04).x, (sp - f * 0.04).y, z0 + 0.98)), 0.017, 0.014, wood, seg=6)
        tr = bk - f * 0.04
        H['_prism'](self.deco, V(((tr - s * 0.21).x, (tr - s * 0.21).y, z0 + 0.97)), V(((tr + s * 0.21).x, (tr + s * 0.21).y, z0 + 0.97)),
                    0.02, 0.02, wood, seg=6)                                         # top rail
        bp = bk - f * 0.025
        self.deco.box(q(bp, 0.014, 0.16), z0 + 0.6, z0 + 0.9, mat)                    # upholstered back pad
        for lx, ly in ((0.18, 0.19), (0.18, -0.19), (-0.18, 0.19), (-0.18, -0.19)):
            lp = p + f * lx + s * ly
            H['_prism'](self.deco, V((lp.x, lp.y, z0)), V((lp.x, lp.y, z0 + 0.4)), 0.02, 0.014, wood, seg=6)

    def salon_suite(self, r, z0):
        """Settee + armchairs around a round table on the rug (state rooms)."""
        H, V = self.H, self.V
        c, n, d = r['c'], r['n'], r['d']
        H['lathe_up'](self.solid, c, z0, [(0.0, 0.0), (0.25, 0.0), (0.26, 0.03), (0.05, 0.08), (0.04, 0.6), (0.08, 0.68), (0.45, 0.7),
                                          (0.45, 0.74), (0.0, 0.74)], 'door', seg=12)
        for k in range(4):
            a = k * math.pi / 2 + 0.4
            p = c + V((math.cos(a), math.sin(a))) * 1.05
            self.chair(p, c - p, z0)

    def music_hall(self, r, z0):
        """Harpsichord with open lid, music stands and rows of chairs facing it."""
        H, V = self.H, self.V
        c, n, d = r['c'], r['n'], r['d']
        hp = c - n * 0.3                                # in front of the organ dais
        f, s = -n, d                                    # keyboard faces the audience (towards the corridor)
        outline = [hp + s * -0.45 + f * 0.0, hp + s * 0.45 + f * 0.0, hp + s * 0.45 - f * 1.0,
                   hp + s * 0.2 - f * 2.1, hp + s * -0.45 - f * 2.2]
        H['slab'](self.solid, [outline], z0 + 0.95, 0.28, 'ebony', 'ebony', 'ebony')
        for lp in (outline[0], outline[1], outline[3], outline[4]):
            q = lp + (hp - f * 1.0 - lp) * 0.12
            H['_prism'](self.deco, V((q.x, q.y, z0)), V((q.x, q.y, z0 + 0.67)), 0.035, 0.028, 'gold', seg=6)
        lid = [V((p.x, p.y, z0 + 0.96)) for p in outline]
        hinge_s = s
        for i, p in enumerate(lid):                      # lid propped open ~35 degrees about the spine
            lat = (p - V((hp.x, hp.y, p.z))).dot(V((hinge_s.x, hinge_s.y, 0)))
            lid[i] = p + V((0, 0, max(0.0, 0.45 - lat) * 0.55))
        self.deco.poly(lid, 'ebony')
        self.deco.poly(list(reversed(lid)), 'ebony')
        kb0, kb1 = hp + s * -0.4 + f * 0.05, hp + s * 0.4 + f * 0.05
        H['seg_box'](self.deco, kb0, kb1, 0.0, 0.16, z0 + 0.86, z0 + 0.9, 'ivory')
        for k in range(28):
            p = kb0.lerp(kb1, (k + 0.5) / 28)
            if k % 7 in (1, 2, 4, 5, 6):
                H['seg_box'](self.deco, p - s * 0.006, p + s * 0.006, 0.07, 0.16, z0 + 0.9, z0 + 0.915, 'ebony')
        bench = hp + f * 0.55
        self.solid.box([bench - s * 0.4 - f * 0.18, bench + s * 0.4 - f * 0.18, bench + s * 0.4 + f * 0.18, bench - s * 0.4 + f * 0.18],
                       z0 + 0.45, z0 + 0.52, 'upholstery')
        for lx, ly in ((0.35, 0.14), (0.35, -0.14), (-0.35, 0.14), (-0.35, -0.14)):   # bench legs
            lp = bench + s * lx + f * ly
            H['_prism'](self.deco, V((lp.x, lp.y, z0)), V((lp.x, lp.y, z0 + 0.45)), 0.02, 0.016, 'ebony', seg=6)
        for row in range(3):
            for k in range(-3, 4):
                if abs(k) < 1:
                    continue                              # central aisle
                p = hp + f * (1.5 + row * 0.9) + s * (k * 0.7)
                self.chair(p, -f, z0)
        cz = self.ceil(1 if z0 > 1 else 0)               # deep coved cornice: the hall reads taller (organ wall left free)
        prof = [(0.0, 0.0), (0.0, -0.78)] + [(0.72 - 0.68 * math.cos(math.pi / 2 * k / 8), -0.78 + 0.68 * math.sin(math.pi / 2 * k / 8)) for k in range(9)] + [(0.72, 0.0)]
        half = self.PART / 2 + 0.02
        for p0, p1, inw in ((r['wall_a'], r['wall_b'], n), (r['wall_a'], r['far_a'], d), (r['wall_b'], r['far_b'], -d)):
            H['sweep'](self.deco, p0 + inw * half, p1 + inw * half, prof, cz, 'plaster_int', inw)
            H['sweep'](self.deco, p0 + inw * (half + 0.005), p1 + inw * (half + 0.005),
                       [(0.0, 0.0), (0.04, 0.0), (0.04, 0.03), (0.0, 0.03)], cz - 0.84, 'gold', inw)
        for k in (-1, 1):                                 # music stands
            p = hp + f * 1.4 + s * (k * 1.6)
            H['_prism'](self.deco, V((p.x, p.y, z0)), V((p.x, p.y, z0 + 1.1)), 0.012, 0.012, 'gold', seg=5)
            H['seg_box'](self.deco, p - s * 0.22, p + s * 0.22, -0.01, 0.01, z0 + 1.05, z0 + 1.35, 'door')

    def window_niches(self, r, zi):
        """Deep round-arched window niches on the room side of the outer wall (SPEC: exhibition rooms)."""
        H = self.H
        V = self.V
        for wp in self.room_windows(r, zi):      # arched stucco surround ABOVE the opening: nothing shows through the glass
            dd = wp['d']
            room = V((-dd.y, dd.x)) * 0.035
            hw = wp['w'] / 2 + 0.14
            rise = min(0.42, hw)
            pts = []
            for k in range(13):
                th = math.pi * k / 12
                q = wp['p'] - dd * (hw * math.cos(th)) + room
                pts.append(V((q.x, q.y, wp['z1'] + 0.06 + rise * math.sin(th))))
            for p0, p1 in zip(pts, pts[1:]):
                H['_prism'](self.deco, p0, p1, 0.045, 0.045, 'plaster_int', seg=6)
            for e in (pts[0], pts[-1]):              # imposts
                H['_prism'](self.deco, e - V((0, 0, 0.12)), e, 0.06, 0.06, 'plaster_int', seg=4)
            kq = pts[6]
            H['_prism'](self.deco, kq - V((0, 0, 0.1)), kq + V((0, 0, 0.08)), 0.05, 0.04, 'plaster_int', seg=4)   # keystone

    def entrance_vault(self, r):
        """Gate passage: white segmental vault on piers with clustered (Gothic profiled) shafts."""
        H, V = self.H, self.V
        q = self.room_quad(r, 0.02)
        ceil = self.ceil(0)
        a, b, fb, fa = q
        span_d = b - a
        nseg, rise = 14, 1.1
        zs = ceil - rise
        for k in range(nseg):
            t0, t1 = k / nseg, (k + 1) / nseg
            h0 = zs + rise * math.sin(math.pi * t0)
            h1 = zs + rise * math.sin(math.pi * t1)
            p0, p1 = a + span_d * t0, a + span_d * t1
            e0, e1 = fa + (fb - fa) * t0, fa + (fb - fa) * t1
            H['oriented_poly'](self.deco, [V((p0.x, p0.y, h0)), V((p1.x, p1.y, h1)), V((e1.x, e1.y, h1)), V((e0.x, e0.y, h0))],
                               V((0, 0, -1)), 'plaster_int')
        dn = (fa - a).normalized()
        Ln = (fa - a).length
        dd_ = span_d.normalized()
        for tb in (1 / 3, 2 / 3):                          # transverse arch bands on profiled wall shafts
            for sd in (-0.18, 0.18):
                for k in range(nseg):
                    t0, t1 = k / nseg, (k + 1) / nseg
                    h0 = zs + rise * math.sin(math.pi * t0) - 0.13
                    h1 = zs + rise * math.sin(math.pi * t1) - 0.13
                    p0 = a + span_d * t0 + dn * (Ln * tb + sd)
                    p1 = a + span_d * t1 + dn * (Ln * tb + sd)
                    H['oriented_poly'](self.deco, [V((p0.x, p0.y, h0)), V((p1.x, p1.y, h1)), V((p1.x, p1.y, h1 + 0.13)), V((p0.x, p0.y, h0 + 0.13))],
                                       V((dn.x, dn.y, 0)) * (1 if sd > 0 else -1), 'plaster_int')
            for k in range(nseg):
                t0, t1 = k / nseg, (k + 1) / nseg
                h0 = zs + rise * math.sin(math.pi * t0) - 0.13
                h1 = zs + rise * math.sin(math.pi * t1) - 0.13
                e = [a + span_d * t0 + dn * (Ln * tb - 0.18), a + span_d * t1 + dn * (Ln * tb - 0.18),
                     a + span_d * t1 + dn * (Ln * tb + 0.18), a + span_d * t0 + dn * (Ln * tb + 0.18)]
                H['oriented_poly'](self.deco, [V((e[0].x, e[0].y, h0)), V((e[1].x, e[1].y, h1)), V((e[2].x, e[2].y, h1)), V((e[3].x, e[3].y, h0))],
                                   V((0, 0, -1)), 'plaster_int')
            for side, inw in ((a, dd_), (b, -dd_)):
                foot = side + dn * (Ln * tb) + inw * 0.12
                for k in range(3):
                    sp = foot + dn * ((k - 1) * 0.14)
                    H['_prism'](self.deco, V((sp.x, sp.y, 0.0)), V((sp.x, sp.y, zs - 0.13)), 0.07, 0.07, 'plaster_int', seg=8)
        for side, inw in ((a, dd_), (b, -dd_)):              # impost cornice along the springing
            bq = [side, side + dn * Ln, side + dn * Ln + inw * 0.16, side + inw * 0.16]
            self.deco.box(bq if dn.cross(inw) > 0 else bq[::-1], zs - 0.28, zs - 0.13, 'plaster_int')
        for corner in q:                                   # clustered shafts at the four corners
            for k in range(5):
                ang = k * 2 * math.pi / 5
                sp = corner + V((math.cos(ang), math.sin(ang))) * 0.13
                H['_prism'](self.deco, V((sp.x, sp.y, 0.0)), V((sp.x, sp.y, zs)), 0.07, 0.07, 'plaster_int', seg=8)
            H['_prism'](self.deco, V((corner.x, corner.y, zs - 0.25)), V((corner.x, corner.y, zs)), 0.26, 0.3, 'plaster_int', seg=8)
        # exposed Gothic portal (ref 03): sandstone, stepped roll mouldings, pointed arch, on the west side wall
        n, d = r['n'], r['d']
        wa, fa_ = r['wall_b'], r['far_b']                 # east side wall (the west side opens to the Knights' Hall)
        inward = -d
        base = wa.lerp(fa_, 0.7) + inward * (self.PART / 2 + 0.01)
        tg = (fa_ - wa).normalized()
        w0, hj = 0.7, 2.4
        for k, (wk, rr) in enumerate(((w0 + 0.42, 0.11), (w0 + 0.25, 0.09), (w0 + 0.1, 0.07))):
            dep = 0.05 + 0.09 * k
            for sx in (-1, 1):
                j0 = base + tg * (sx * wk) + inward * dep
                H['_prism'](self.deco, V((j0.x, j0.y, 0.0)), V((j0.x, j0.y, hj)), rr, rr, 'sandstone', seg=6)
            for sx in (-1, 1):
                cen = base - tg * (sx * wk) + inward * dep
                pts = []
                for j in range(9):
                    th = math.acos(0.5) * j / 8
                    p2 = cen + tg * (sx * 2 * wk * math.cos(th))
                    pts.append(V((p2.x, p2.y, hj + 2 * wk * math.sin(th))))
                for p0, p1 in zip(pts, pts[1:]):
                    H['_prism'](self.deco, p0, p1, rr, rr, 'sandstone', seg=6)
        for sx in (-1, 1):
            j0 = base + tg * (sx * (w0 + 0.62))
            self.deco.box([j0 - tg * 0.12, j0 + tg * 0.12, j0 + tg * 0.12 + inward * 0.3, j0 - tg * 0.12 + inward * 0.3], 0.0, 0.5, 'sandstone')
        rec = [base - tg * (w0 + 0.1) + inward * 0.07, base + tg * (w0 + 0.1) + inward * 0.07]       # dark walled-up opening, arch-shaped
        outline = [V((rec[0].x, rec[0].y, 0.0)), V((rec[1].x, rec[1].y, 0.0))]
        span = 2 * (w0 + 0.1)
        for j in range(9):                                 # arc from the rec[1] springing up to the apex (centre rec[0])
            th = math.acos(0.5) * j / 8
            p2 = rec[0] + (rec[1] - rec[0]) * math.cos(th)
            outline.append(V((p2.x, p2.y, hj + span * math.sin(th))))
        for j in range(7, -1, -1):                         # and back down to the rec[0] springing (centre rec[1])
            th = math.acos(0.5) * j / 8
            p2 = rec[1] + (rec[0] - rec[1]) * math.cos(th)
            outline.append(V((p2.x, p2.y, hj + span * math.sin(th))))
        H['oriented_poly'](self.deco, outline, V((inward.x, inward.y, 0)), 'wall_dark')
        # info boards on the opposite wall, pendant lantern
        wb, fb_ = r['wall_a'], r['far_a']
        for t in (0.2, 0.8):
            p = wb.lerp(fb_, t) + d * (self.PART / 2 + 0.02)
            tg2 = (fb_ - wb).normalized()
            self.deco.box([p - tg2 * 0.4, p + tg2 * 0.4, p + tg2 * 0.4 + d * 0.03, p - tg2 * 0.4 + d * 0.03], 1.1, 2.2, 'panel_board')
        H['lantern'](self.deco, r['c'], ceil - 0.02, ceil - 1.4, r=0.22)
        if n.y < -0.9:                                     # review camera in the main (south) gate passage
            cam = r['c'] - d * (r['L'] / 2 - 0.7) - n * (r['D'] * 0.3)
            H['NAV']['passage_portal'] = [cam.x, cam.y, 1.65, base.x, base.y, 2.3]

    def rope_barriers(self, r, z0):
        """Brass stanchions with red ropes around the two vitrines of exhibition rooms."""
        H, V = self.H, self.V
        if r['L'] < 5 or r['D'] < 6:
            return
        c, n, d = r['c'], r['n'], r['d']
        for k in (-1, 1):
            p = c + d * (k * r['L'] * 0.22)
            ring = [p - d * 1.0 - n * 0.85, p + d * 1.0 - n * 0.85, p + d * 1.0 + n * 0.85, p - d * 1.0 + n * 0.85]
            for q in ring:
                H['lathe_up'](self.deco, q, z0, [(0.0, 0.0), (0.12, 0.0), (0.12, 0.03), (0.02, 0.06), (0.018, 0.9), (0.035, 0.94), (0.0, 0.98)], 'gold', seg=8)
            for j in range(3):                               # leave the corridor side open
                a, b = ring[j], ring[j + 1]
                pts = [a.lerp(b, t / 6) for t in range(7)]
                for t in range(6):
                    za = z0 + 0.88 - 0.12 * math.sin(math.pi * t / 6)
                    zb = z0 + 0.88 - 0.12 * math.sin(math.pi * (t + 1) / 6)
                    H['_prism'](self.deco, V((pts[t].x, pts[t].y, za)), V((pts[t + 1].x, pts[t + 1].y, zb)), 0.012, 0.012, 'rope_red', seg=5)

    def info_panel(self, r, z0):
        """Museum info stand near the corridor door with title strip and text block."""
        H, V = self.H, self.V
        n, d = r['n'], r['d']
        p = (r['wall_a'] + r['wall_b']) / 2 + n * 1.8 + d * 1.4
        H['_prism'](self.deco, V((p.x, p.y, z0)), V((p.x, p.y, z0 + 1.05)), 0.03, 0.03, 'metal', seg=6)
        a, b = p - d * 0.35, p + d * 0.35
        self.deco.box([a, b, b + n * 0.03, a + n * 0.03], z0 + 1.05, z0 + 1.6, 'panel_board')
        for k, (h0, h1, w) in enumerate(((1.5, 1.56, 0.28), (1.4, 1.43, 0.25), (1.34, 1.37, 0.25), (1.28, 1.31, 0.22), (1.22, 1.25, 0.25))):
            ta, tb = p - d * w, p + d * (w - 0.04 * k)
            self.deco.box([ta - n * 0.002, tb - n * 0.002, tb - n * 0.004, ta - n * 0.004], z0 + h0, z0 + h1, 'panel_text')

    def salon_hang(self, r, z0):
        """Picture gallery: tiers of paintings on the partitions (old-master 'salon' hang)."""
        H, V = self.H, self.V
        half = self.PART / 2 + 0.02
        paints = ('paint_land', 'paint_land2', 'paint_harbour', 'paint_still', 'paint_port', 'paint_port2')
        for wa, fa, inward in self.partitions(r):
            L = (fa - wa).length
            if L < 1.0:
                continue
            door_u = L * 0.72
            tg = (fa - wa) / L
            for u0, u1 in ((0.6, door_u - 1.1), (door_u + 1.1, L - 0.6)):
                u = u0
                while u < u1 - 0.6:
                    w2 = self.rng.uniform(0.3, 0.6)
                    if u + 2 * w2 > u1:
                        break
                    base = wa + tg * (u + w2) + inward * (half + 0.012)
                    for h0, hh in ((z0 + 1.25, self.rng.uniform(0.6, 1.0)), (z0 + 2.45, self.rng.uniform(0.5, 0.9))):
                        H['hang_painting'](self.deco, base, inward, w2, h0, h0 + hh, self.rng.choice(paints))
                    u += 2 * w2 + 0.25

    def gallery_bench(self, r, z0):
        H, V = self.H, self.V
        c, n, d = r['c'], r['n'], r['d']
        q = [c - d * 1.2 - n * 0.3, c + d * 1.2 - n * 0.3, c + d * 1.2 + n * 0.3, c - d * 1.2 + n * 0.3]
        self.solid.box(q, z0 + 0.38, z0 + 0.46, 'upholstery', bottom='door')
        for p in q:
            p2 = c + (p - c) * 0.9
            H['_prism'](self.deco, V((p2.x, p2.y, z0)), V((p2.x, p2.y, z0 + 0.38)), 0.03, 0.025, 'door', seg=5)

    # ------------------------------------------------------------ Knights' Hall
    def knights_hall(self):
        """Groin-vault ribs over each bay, suits of armour on plinths, hanging banners."""
        H, V = self.H, self.V
        z0, ceil = self.FZ[0], self.ceil(0)
        banners = ('banner_a', 'banner_b', 'banner_c')
        for bi, r in enumerate(self.hall_rooms):
            q = self.room_quad(r, 0.15)
            c = sum(q, V((0, 0))) / 4
            zs, hv = ceil - 1.9, 1.85
            gz = lambda x, y: zs + hv * max(math.sqrt(max(0.0, 1 - x * x)), math.sqrt(max(0.0, 1 - y * y)))
            qa, qb, qfb, qfa = self.room_quad(r, -(self.PART / 2 + 0.02))   # edges on the partition axes: bays share junctions
            bl = lambda s_, t_: (qa * (1 - s_) + qb * s_) * (1 - t_) + (qfa * (1 - s_) + qfb * s_) * t_
            N = 12                                        # groin vault: two intersecting barrels, arrises on the diagonals
            P3 = lambda i, j: (lambda p: V((p.x, p.y, gz(2 * i / N - 1, 2 * j / N - 1))))(bl(i / N, j / N))
            for i in range(N):
                for j in range(N):
                    H['oriented_poly'](self.deco, [P3(i, j), P3(i + 1, j), P3(i + 1, j + 1), P3(i, j + 1)], V((0, 0, -1)), 'plaster_int')
            for edge in ([(i, 0) for i in range(N + 1)], [(i, N) for i in range(N + 1)], [(0, j) for j in range(N + 1)], [(N, j) for j in range(N + 1)]):
                for (i0, j0), (i1, j1) in zip(edge, edge[1:]):
                    e0, e1 = P3(i0, j0), P3(i1, j1)
                    quad = [e0, e1, V((e1.x, e1.y, ceil)), V((e0.x, e0.y, ceil))]
                    self.deco.poly(quad, 'plaster_int')
                    self.deco.poly(quad[::-1], 'plaster_int')
            for corner in q:                              # diagonal ribs along the groins, from the corners to the crown
                pts = []
                for k in range(13):
                    t = k / 12
                    p = corner.lerp(c, t)
                    pts.append(V((p.x, p.y, zs - 0.05 + hv * math.sqrt(max(0.0, 1 - (1 - t) ** 2)))))
                for a, b in zip(pts, pts[1:]):
                    H['_prism'](self.deco, a, b, 0.09, 0.09, 'frame', seg=6)
                H['_prism'](self.deco, V((corner.x, corner.y, z0)), V((corner.x, corner.y, zs - 0.05)), 0.16, 0.14, 'frame', seg=8)
            H['ellipsoid'](self.deco, V((c.x, c.y, ceil - 0.08)), 0.22, 0.22, 0.1, 0, 0, 'gold', subdiv=1)
            n, d = r['n'], r['d']
            for k in (-1, 1):                              # suits of armour along the outer wall
                p = c + n * (r['D'] * 0.32) + d * (k * r['L'] * 0.3)
                self.armour(p, -n, z0)
                if 'armour_cam' not in H['NAV']:
                    cam = p - n * 2.2 + d * 0.9
                    H['NAV']['armour_cam'] = [cam.x, cam.y, z0 + 1.6, p.x, p.y, z0 + 1.35]
            for k in (-1, 1):                              # banners hung from the corridor wall
                p = (r['wall_a'] + r['wall_b']) / 2 + n * (self.PART / 2 + 0.06) + d * (k * r['L'] * 0.25)
                a, b = p - d * 0.45, p + d * 0.45
                top = ceil - 0.5
                H['oriented_poly'](self.deco, [V((a.x, a.y, top - 2.4)), V((b.x, b.y, top - 2.4)), V((b.x, b.y, top)), V((a.x, a.y, top))],
                                   V((n.x, n.y, 0)), banners[(bi + k) % 3], uv=[(0, 0), (1, 0), (1, 1), (0, 1)])
                H['_prism'](self.deco, V(((a - d * 0.08).x, (a - d * 0.08).y, top + 0.02)), V(((b + d * 0.08).x, (b + d * 0.08).y, top + 0.02)),
                            0.02, 0.02, 'gold', seg=6)

    def armour(self, p, face, z0):
        """Full plate armour on a moulded stone plinth: smooth subdivided plates in dark steel - sabatons,
        greaves, knee cops, cuisses, tassets, fauld, ridged breastplate, pauldrons, couters, vambraces,
        gauntlets, gorget and an armet with a pointed visor; halberd at the side."""
        H, V = self.H, self.V
        f = face.normalized()
        s = V((-f.y, f.x))
        if 'steel_dark' not in H['MATS']:
            H['make_mat']('steel_dark', None, color=(0.34, 0.35, 0.37), rough=0.42, metal=0.85)
        M = 'steel_dark'
        sq = lambda h: [p - f * h - s * h, p + f * h - s * h, p + f * h + s * h, p - f * h + s * h]
        self.solid.box(sq(0.42), z0, z0 + 0.12, 'marble')
        self.solid.box(sq(0.36), z0 + 0.12, z0 + 0.34, 'marble')
        self.deco.box(sq(0.4), z0 + 0.34, z0 + 0.4, 'marble')
        b = z0 + 0.4
        yaw = math.atan2(f.y, f.x)
        SM = H['SMOOTH']                                  # smooth-shaded mesh: plates read as polished curves
        E = lambda c, sx, sy, sz, m=M, sub=2, pitch=0.0: H['ellipsoid'](SM, c, sx, sy, sz, yaw, pitch, m, subdiv=sub)
        P3 = lambda q, z: V((q.x, q.y, z))
        T = lambda a, b_, ra, rb: H['_prism'](SM, a, b_, ra, rb, M, seg=10)
        for sg in (-1, 1):
            lp = p + s * (sg * 0.1)
            E(P3(lp + f * 0.06, b + 0.04), 0.13, 0.055, 0.04, sub=1)                  # sabaton
            T(P3(lp, b + 0.07), P3(lp, b + 0.5), 0.05, 0.066)                         # greave
            E(P3(lp + f * 0.03, b + 0.5), 0.06, 0.06, 0.055, sub=1)                   # knee cop
            T(P3(lp, b + 0.52), P3(lp + s * (sg * 0.01), b + 0.88), 0.068, 0.088)     # cuisse
            E(P3(lp + f * 0.07, b + 0.83), 0.03, 0.09, 0.1, pitch=0.15, sub=1)        # tasset
            sp_ = p + s * (sg * 0.26)
            E(P3(sp_, b + 1.4), 0.12, 0.1, 0.085)                                      # pauldron
            T(P3(sp_ + s * (sg * 0.01), b + 1.36), P3(sp_ + s * (sg * 0.02), b + 1.1), 0.055, 0.05)   # rerebrace
            E(P3(sp_ + s * (sg * 0.02) + f * 0.02, b + 1.08), 0.06, 0.05, 0.05, sub=1)   # couter
            T(P3(sp_ + s * (sg * 0.02) + f * 0.02, b + 1.07), P3(sp_ + f * 0.15, b + 0.88), 0.048, 0.04)   # vambrace
            E(P3(sp_ + f * 0.16, b + 0.84), 0.05, 0.045, 0.065, sub=1)                # gauntlet
        H['_prism'](SM, P3(p, b + 0.8), P3(p, b + 0.98), 0.2, 0.155, M, seg=12)          # flared fauld / tasset skirt
        H['_prism'](SM, P3(p, b + 0.96), P3(p, b + 1.12), 0.145, 0.165, M, seg=12)       # waist lames
        E(P3(p + f * 0.02, b + 1.27), 0.15, 0.21, 0.19)                               # breastplate (chest)
        E(P3(p, b + 1.38), 0.11, 0.2, 0.08, sub=1)                                    # shoulder yoke
        H['_prism'](SM, P3(p + f * 0.155, b + 1.0), P3(p + f * 0.15, b + 1.38), 0.012, 0.012, M, seg=4)   # medial ridge
        E(P3(p, b + 1.5), 0.1, 0.11, 0.06)                                            # gorget
        E(P3(p, b + 1.67), 0.12, 0.11, 0.14)                                          # armet skull
        E(P3(p + f * 0.07, b + 1.63), 0.09, 0.08, 0.08, pitch=-0.2)                   # pointed visor
        vis = p + f * 0.15
        H['seg_box'](self.deco, vis - s * 0.055, vis + s * 0.055, -0.004, 0.004, b + 1.665, b + 1.68, 'ebony')
        H['_prism'](self.deco, P3(p - f * 0.08, b + 1.78), P3(p + f * 0.1, b + 1.8), 0.012, 0.01, M, seg=4)   # comb
        hp = p + s * 0.38 + f * 0.12                                                  # halberd held in the right gauntlet
        H['_prism'](self.deco, P3(hp, z0 + 0.4), P3(hp, b + 2.1), 0.016, 0.016, 'door', seg=6)
        H['seg_box'](self.deco, hp, hp + f * 0.24, -0.004, 0.004, b + 1.86, b + 2.04, M)
        H['seg_box'](self.deco, hp - f * 0.12, hp, -0.004, 0.004, b + 1.92, b + 1.98, M)
        H['_prism'](self.deco, P3(hp, b + 2.1), P3(hp, b + 2.35), 0.012, 0.002, M, seg=4)

    # ------------------------------------------------------------ Crown Tower treasury
    def treasury(self):
        """Extra vitrines (sceptre, orb) and crimson walls around the crown replica."""
        H, V = self.H, self.V
        sq = self.P['tower_sq'][0][1]
        cen = sum(sq, V((0, 0))) / 4
        for k, off in enumerate((V((2.2, 1.4)), V((-1.4, 2.2)))):
            c = cen + off
            q = lambda rr: [c + V((-rr, -rr)), c + V((rr, -rr)), c + V((rr, rr)), c + V((-rr, rr))]
            self.solid.box(q(0.35), 0.0, 0.95, 'door', top='joinery')
            self.deco.box(q(0.25), 0.95, 1.0, 'rope_red')
            if k == 0:   # sceptre
                H['_prism'](self.deco, V((c.x - 0.2, c.y, 1.02)), V((c.x + 0.2, c.y, 1.02)), 0.012, 0.012, 'gold', seg=6)
                H['ellipsoid'](self.deco, V((c.x + 0.22, c.y, 1.03)), 0.035, 0.035, 0.035, 0, 0, 'gold', subdiv=1)
            else:        # orb with cross
                H['ellipsoid'](self.deco, V((c.x, c.y, 1.08)), 0.07, 0.07, 0.07, 0, 0, 'gold', subdiv=2)
                H['_prism'](self.deco, V((c.x, c.y, 1.15)), V((c.x, c.y, 1.25)), 0.008, 0.008, 'gold', seg=4)
            g = q(0.3)
            for j in range(4):
                a, b = g[j], g[(j + 1) % 4]
                self.deco.poly([V((a.x, a.y, 1.0)), V((b.x, b.y, 1.0)), V((b.x, b.y, 1.55)), V((a.x, a.y, 1.55))], 'glass')
            self.deco.poly([V((p.x, p.y, 1.55)) for p in g], 'glass')
            self.solid.box(q(0.31), 1.0, 1.55, 'invisible')

    # ------------------------------------------------------------ Theresian staircase (refs 28-30)
    def stair_materials(self):
        H, mk = self.H, self.H['make_mat']
        for nm, col, rough in (('marble_grey', (0.2, 0.19, 0.18), 0.35), ('oak_honey', (0.45, 0.2, 0.06), 0.45),
                               ('organ_white', (0.88, 0.87, 0.84), 0.5), ('dais_grey', (0.36, 0.37, 0.39), 0.6)):
            if nm not in H['MATS']:
                mk(nm, None, color=col, rough=rough, spec=0.4)

    def staircase(self):
        """Open well with square piers, round arches over every flight/landing edge, sail vaults over the
        landings and the top bays, rampant barrels under the flights with gilded ovals, and grey-marble
        pierced balustrades of interlaced ovals. Step geometry and collision stay in build_stairs."""
        H, V, P = self.H, self.V, self.P
        if not P.get('stair_hole'):
            return
        pa, pb, fb, fa = P['stair_hole']
        width, depth = (pb - pa).length, (fa - pa).length
        d, n = (pb - pa) / width, (fa - pa) / depth
        gap = H.get('STAIR_GAP', 0.5)
        fw, land = (width - gap) / 2, 2.6
        pw = 0.45 if gap > 0.9 else gap        # square piers at the well corners (one central pier for a slit)
        if gap > 0.9:
            pier_u = [(fw, fw + pw), (width - fw - pw, width - fw)]
            spans = [(0.0, fw), (fw + pw, width - fw - pw), (width - fw, width)]
        else:
            pier_u = [(mid_ - 0.25, mid_ + 0.25) for mid_ in (width / 2,)]
            spans = [(0.0, width / 2 - 0.25), (width / 2 + 0.25, width)]
        run = depth - land - 0.1
        ccw = V((-d.y, d.x)).dot(n) > 0
        FZ, ztop, mb = self.FZ, self.EAVE - self.SLAB, self.deco
        mid = width / 2
        Q = lambda u, v: pa + d * u + n * v
        Q3 = lambda u, v, z: V(((pa + d * u + n * v).x, (pa + d * u + n * v).y, z))

        def box(u0, u1, v0, v1, z0, z1, mat='plaster_int'):
            base = [Q(u0, v0), Q(u1, v0), Q(u1, v1), Q(u0, v1)]
            mb.box(base if ccw else list(reversed(base)), z0, z1, mat)

        def two_sided(pts, mat='plaster_int'):
            mb.poly(pts, mat)
            mb.poly(list(reversed(pts)), mat)

        storeys = []
        for k in range(len(FZ) - 1):
            z0, z1 = FZ[k], FZ[k + 1]
            zm = (z0 + z1) / 2
            nst = max(8, round((zm - z0) / 0.16))
            storeys.append((z0, z1, zm, (zm - z0) / nst))

        # pierced balustrades along both edges of the well, and across the open top-floor bay
        for z0, z1, zm, rise in storeys:
            for u, za, zb in ((fw, z0, zm), (width - fw, z1, zm)):
                self.balustrade(Q(u, 0.0), Q(u, run), za, zb)
        rails = [(Q(0.05, -0.14), Q(fw, -0.14), FZ[-1])]                     # open top-floor bay over flight 1
        if gap > 0.9:                                                        # well edges at every floor and landing
            rails += [(Q(fw, -0.14), Q(width - fw, -0.14), z) for z in FZ[1:]]
            rails += [(Q(fw + pw, run), Q(width - fw - pw, run), zm) for z0, z1, zm, rise in storeys]
        for a, b, z in rails:
            self.balustrade(a, b, z, z)
            H['sloped_prism'](P['ramps'], a, b, z, z, -0.09, 0.09, 0.0, 1.0, 'stone')

        # piers at both ends of the well, full height, with moulded capitals at each arch springing
        springs = []
        arches = []      # (v0, v1, z_top)
        for L in range(len(FZ)):
            arches.append((0.0, 0.3, FZ[L + 1] - self.SLAB if L + 1 < len(FZ) else ztop))
        for k, (z0, z1, zm, rise) in enumerate(storeys):
            arches.append((run, run + 0.3, storeys[k + 1][2] - 0.35 if k + 1 < len(storeys) else ztop))
        for v0, v1, zt in arches:
            for u0, u1 in spans:
                r = (u1 - u0) / 2
                zs = zt - 0.5 - r
                springs.append((v0, zs))
                a, b = Q(u0, v0), Q(u1, v0)
                off, t = (0.0, v1 - v0) if ccw else (-(v1 - v0), v1 - v0)
                H['arch_head'](mb, a, b, zs + r, off, t, 'plaster_int', seg=12)
                box(u0, u1, v0, v1, zs + r, zt)
                box(u0, u0 + 0.22, v0 - 0.02, v1 + 0.02, zs - 0.16, zs, 'plaster_int')      # imposts
                box(u1 - 0.22, u1, v0 - 0.02, v1 + 0.02, zs - 0.16, zs, 'plaster_int')
                km = (u0 + u1) / 2
                box(km - 0.09, km + 0.09, v0 - 0.03, v1 + 0.03, zs + r - 0.25, zs + r + 0.05, 'gold')   # keystone
                box(u0, u1, v0 - 0.025, v0, zt - 0.08, zt - 0.05, 'gold')                       # gilded fillet line
        for v0, v1 in ((0.0, 0.45), (run - 0.225, run + 0.225)):
            for pu0, pu1 in pier_u:
                box(pu0, pu1, v0, v1, FZ[0], ztop)
                box(pu0 - 0.07, pu1 + 0.07, v0 - 0.07, v1 + 0.07, FZ[0], FZ[0] + 0.3, 'marble_grey')
                caps = []
                for va, zs in sorted(set((round(va, 3), round(zs, 3)) for va, zs in springs)):
                    if abs(va - v0) < 0.3:
                        box(pu0 - 0.07, pu1 + 0.07, v0 - 0.07, v1 + 0.07, zs - 0.2, zs, 'plaster_int')
                        box(pu0 - 0.05, pu1 + 0.05, v0 - 0.05, v1 + 0.05, zs - 0.26, zs - 0.2, 'gold')
                        caps.append(zs - 0.26)
                lo = FZ[0] + 0.3
                for hi in sorted(caps):              # framed panel on every pier face between base/capitals
                    if hi - lo > 1.2:
                        z_a, z_b = lo + 0.25, hi - 0.25
                        for (ua, va_), (ub, vb_) in (((pu0, v0), (pu1, v0)), ((pu1, v0), (pu1, v1)), ((pu1, v1), (pu0, v1)), ((pu0, v1), (pu0, v0))):
                            e0, e1 = Q(ua, va_), Q(ub, vb_)
                            L_ = (e1 - e0).length
                            if L_ < 0.3:
                                continue
                            tq = (e1 - e0) / L_
                            out = V((tq.y, -tq.x)) if ccw else V((-tq.y, tq.x))
                            f0, f1 = e0 + tq * 0.08 + out * 0.005, e1 - tq * 0.08 + out * 0.005
                            for zz in (z_a, z_b):
                                mb.box([f0, f1, f1 + out * 0.015, f0 + out * 0.015], zz, zz + 0.025, 'gold')
                            for fp in (f0, f1):
                                mb.box([fp - tq * 0.0125, fp + tq * 0.0125, fp + tq * 0.0125 + out * 0.015, fp - tq * 0.0125 + out * 0.015], z_a, z_b + 0.025, 'gold')
                    lo = hi + 0.26

        # sail vaults: over each landing (under the next landing) and the top bays of the hall
        bays = []
        for k, (z0, z1, zm, rise) in enumerate(storeys):
            zt = storeys[k + 1][2] - 0.35 if k + 1 < len(storeys) else ztop
            bays += [(0.0, mid, run + 0.3, depth, zt), (mid, width, run + 0.3, depth, zt)]
        for u0, u1 in ((0.0, mid), (mid, width)):
            bays += [(u0, u1, 0.3, run / 2, ztop), (u0, u1, run / 2, run, ztop)]
        for u0, u1, v0, v1, zt in bays:
            self.sail_vault(Q3, u0, u1, v0, v1, zt, two_sided)

        # rampant barrels under the flights of storeys 1.. (seen from the flights below)
        for j in range(1, len(storeys)):
            z0, z1, zm, rise = storeys[j]
            for u0, u1, za, zb, slot_u in ((0.0, fw, z0, zm, fw), (width - fw, width, z1, zm, width - fw)):
                zz = lambda v: za - 0.35 - rise + (zb - za) * v / run
                hb = 0.45
                zf = lambda u, v: zz(v) - 0.03 - hb * (2 * (u - u0) / (u1 - u0) - 1) ** 2
                NU, NV = 8, 10
                vs = [0.3 + (run - 0.3) * i / NV for i in range(NV + 1)]
                us = [u0 + (u1 - u0) * i / NU for i in range(NU + 1)]
                for i in range(NV):
                    for m in range(NU):
                        quad = [Q3(us[m], vs[i], zf(us[m], vs[i])), Q3(us[m + 1], vs[i], zf(us[m + 1], vs[i])),
                                Q3(us[m + 1], vs[i + 1], zf(us[m + 1], vs[i + 1])), Q3(us[m], vs[i + 1], zf(us[m], vs[i + 1]))]
                        H['oriented_poly'](mb, quad, V((0, 0, -1)), 'plaster_int')
                for i in range(NV):        # strip on the well side up to the flight soffit
                    two_sided([Q3(slot_u, vs[i], zf(slot_u, vs[i])), Q3(slot_u, vs[i + 1], zf(slot_u, vs[i + 1])),
                               Q3(slot_u, vs[i + 1], zz(vs[i + 1])), Q3(slot_u, vs[i], zz(vs[i]))])
                for v in (vs[0], vs[-1]):
                    for m in range(NU):
                        two_sided([Q3(us[m], v, zf(us[m], v)), Q3(us[m + 1], v, zf(us[m + 1], v)),
                                   Q3(us[m + 1], v, zz(v)), Q3(us[m], v, zz(v))])
                vmid = (vs[0] + vs[-1]) / 2
                for i in range(NU):        # transverse stucco band between the two bays
                    two_sided([Q3(us[i], vmid - 0.12, zf(us[i], vmid) - 0.06), Q3(us[i + 1], vmid - 0.12, zf(us[i + 1], vmid) - 0.06),
                               Q3(us[i + 1], vmid + 0.12, zf(us[i + 1], vmid) - 0.06), Q3(us[i], vmid + 0.12, zf(us[i], vmid) - 0.06)])
                for vc in ((vs[0] + vmid) / 2, (vmid + vs[-1]) / 2):
                    uc = (u0 + u1) / 2
                    ry, rx = (vmid - vs[0]) * 0.36, (u1 - u0) * 0.3
                    ring = [(uc + rx * math.cos(2 * math.pi * s / 40), vc + ry * math.sin(2 * math.pi * s / 40)) for s in range(41)]
                    pts = [Q3(u, v, zf(u, v) - 0.015) for u, v in ring]
                    for p0, p1 in zip(pts, pts[1:]):
                        H['_prism'](mb, p0, p1, 0.016, 0.016, 'gold', seg=4)
                    for u, v in ((uc, vc + ry * 1.25), (uc, vc - ry * 1.25), (uc, vc)):
                        H['ellipsoid'](mb, Q3(u, v, zf(u, v) - 0.02), 0.06, 0.16, 0.025,
                                       math.atan2(n.y, n.x) - math.pi / 2, 0, 'gold', subdiv=1)

        # thin gold panel lines on the side walls, parallel to the flights
        for z0, z1, zm, rise in storeys:
            for u, za, zb, sgn in ((0.02, z0, zm, 1), (width - 0.02, z1, zm, -1)):
                a, b = Q(u, 0.0), Q(u, run)
                lo, hi = sorted((0.0, 0.02 * sgn * (-1 if ccw else 1)))
                for h in (1.25, 3.1):
                    H['sloped_prism'](mb, a, b, za, zb, lo, hi, h, h + 0.025, 'gold')
                for i in range(1, 6):
                    t = i / 6
                    c = a.lerp(b, t)
                    zc = za + (zb - za) * t
                    H['seg_box'](mb, c - n * 0.0125, c + n * 0.0125, lo, hi, zc + 1.25, zc + 3.125, 'gold')

    def balustrade(self, a, b, za, zb, mat='marble_grey'):
        """Grey-marble pierced balustrade (refs 28/29): plinth, chain of interlaced upright oval bands, handrail.
        a-b in plan, za/zb = tread level at each end (equal for a level rail)."""
        H, V, mb = self.H, self.V, self.deco
        H['sloped_prism'](mb, a, b, za, zb, -0.13, 0.13, -0.3, 0.14, mat)
        H['sloped_prism'](mb, a, b, za, zb, -0.15, 0.15, 0.88, 1.03, mat)
        L = (b - a).length
        ax = (b - a) / L
        nrm = V((-ax.y, ax.x))
        slope = (zb - za) / L
        rx, rz, w, ht, seg = 0.17, 0.37, 0.07, 0.045, 14
        nr = max(1, int(L / 0.24))
        for i in range(nr):
            t = (i + 0.5) / nr
            c, zc = a.lerp(b, t), za + (zb - za) * t + 0.51
            C3 = V((c.x, c.y, zc))
            def Pt(th, s, o):
                p = c + ax * ((rx - s) * math.cos(th)) + nrm * o
                return V((p.x, p.y, zc + (rz - s) * math.sin(th) + slope * (rx - s) * math.cos(th)))
            for j in range(seg):
                t0, t1 = 2 * math.pi * j / seg, 2 * math.pi * (j + 1) / seg
                rad = Pt((t0 + t1) / 2, 0, 0) - C3
                n3 = V((nrm.x, nrm.y, 0))
                for quad, hint in (([Pt(t0, 0, -ht), Pt(t1, 0, -ht), Pt(t1, 0, ht), Pt(t0, 0, ht)], rad),
                                   ([Pt(t0, w, -ht), Pt(t1, w, -ht), Pt(t1, w, ht), Pt(t0, w, ht)], -rad),
                                   ([Pt(t0, 0, ht), Pt(t1, 0, ht), Pt(t1, w, ht), Pt(t0, w, ht)], n3),
                                   ([Pt(t0, 0, -ht), Pt(t1, 0, -ht), Pt(t1, w, -ht), Pt(t0, w, -ht)], -n3)):
                    H['oriented_poly'](mb, quad, hint, mat)

    def sail_vault(self, Q3, u0, u1, v0, v1, zt, two_sided, N=8):
        H, V, mb = self.H, self.V, self.deco
        a, b = (u1 - u0) / 2, (v1 - v0) / 2
        R = math.hypot(a, b)
        zs = zt - 0.02 - R
        uc, vc = (u0 + u1) / 2, (v0 + v1) / 2
        z = lambda u, v: zs + math.sqrt(max(R * R - (u - uc) ** 2 - (v - vc) ** 2, 0.0))
        us = [u0 + (u1 - u0) * i / N for i in range(N + 1)]
        vs = [v0 + (v1 - v0) * i / N for i in range(N + 1)]
        for i in range(N):
            for m in range(N):
                quad = [Q3(us[m], vs[i], z(us[m], vs[i])), Q3(us[m + 1], vs[i], z(us[m + 1], vs[i])),
                        Q3(us[m + 1], vs[i + 1], z(us[m + 1], vs[i + 1])), Q3(us[m], vs[i + 1], z(us[m], vs[i + 1]))]
                H['oriented_poly'](mb, quad, V((0, 0, -1)), 'plaster_int')
        for edge in ([(u, v0) for u in us], [(u, v1) for u in us], [(u0, v) for v in vs], [(u1, v) for v in vs]):
            for (ua, va), (ub, vb) in zip(edge, edge[1:]):
                two_sided([Q3(ua, va, z(ua, va)), Q3(ub, vb, z(ub, vb)), Q3(ub, vb, zt), Q3(ua, va, zt)])
        def surf_line(pts2, rad, mat='gold', lift=0.015):
            pts = [Q3(u, v, z(u, v) - lift) for u, v in pts2]
            for p0, p1 in zip(pts, pts[1:]):
                H['_prism'](mb, p0, p1, rad, rad, mat, seg=4)
        rx, ry = a * 0.55, b * 0.55              # double gilded oval frame (smooth)
        for sc, rad in ((1.0, 0.02), (0.9, 0.011)):
            surf_line([(uc + rx * sc * math.cos(2 * math.pi * k / 40), vc + ry * sc * math.sin(2 * math.pi * k / 40)) for k in range(41)], rad)
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):     # rocaille: S-scrolls growing out of the oval rim
            ou, ov_ = uc + rx * sx * 0.7071, vc + ry * sy * 0.7071
            du, dv = sx * a * 0.3, sy * b * 0.3                     # outward run towards the corner
            ln = math.hypot(du, dv)
            pu, pv = -dv / ln, du / ln
            for flip in (-1, 1):
                pts2 = []
                for k in range(13):                                  # S-curve off the oval
                    t = k / 12
                    pts2.append((ou + du * t + pu * flip * 0.14 * math.sin(math.pi * t),
                                 ov_ + dv * t + pv * flip * 0.14 * math.sin(math.pi * t)))
                eu, ev = pts2[-1]
                for k in range(1, 13):                               # curling volute at its end
                    th = flip * 2 * math.pi * k / 10
                    rr = 0.1 * (1 - k / 14)
                    pts2.append((eu + pu * flip * 0.1 + rr * (math.cos(th) * -pu * flip + math.sin(th) * du / ln),
                                 ev + pv * flip * 0.1 + rr * (math.cos(th) * -pv * flip + math.sin(th) * dv / ln)))
                surf_line(pts2, 0.014)
            H['ellipsoid'](mb, Q3(ou + du * 0.5, ov_ + dv * 0.5, z(ou + du * 0.5, ov_ + dv * 0.5) - 0.02), 0.12, 0.04, 0.02,
                           math.atan2(dv, du), 0, 'gold', subdiv=1)                  # acanthus leaf on the stem
        for ring, rr_, sz_ in ((0, 0.22, (0.14, 0.05)), (1, 0.12, (0.08, 0.035))):   # rosette: two rings of petals
            for k in range(8):
                th = 2 * math.pi * (k + 0.5 * ring) / 8
                pu_, pv_ = uc + rr_ * math.cos(th), vc + rr_ * math.sin(th)
                H['ellipsoid'](mb, Q3(pu_, pv_, z(pu_, pv_) - 0.025 - 0.01 * ring), sz_[0], sz_[1], 0.025, th, 0, 'gold', subdiv=1)
        surf_line([(uc + 0.36 * math.cos(2 * math.pi * k / 24), vc + 0.36 * math.sin(2 * math.pi * k / 24)) for k in range(25)], 0.01)
        H['ellipsoid'](mb, Q3(uc, vc, z(uc, vc) - 0.04), 0.07, 0.07, 0.05, 0, 0, 'gold', subdiv=2)

    # ------------------------------------------------------------ cellar stair opening (ref 37)
    def cellar_reveals(self):
        """Re-tessellate the brick vault around the cellar stair hole finely, so the cut follows the hole,
        and line the cut with brick reveals up to the ground-floor slab."""
        H, V, mb = self.H, self.V, self.deco
        ci = H.get('CELLAR_INFO')
        if not ci:
            return
        secs, along, arc = ci['secs'], ci['along'], ci['arc']
        zone, inner = ci['zone'], H['offset_poly'](ci['hole'], 0.1)
        pip = H['point_in_poly']
        inz = lambda q: pip(q.x, q.y, zone)
        cut = lambda q: pip(q.x, q.y, inner)
        z_ceil = -self.SLAB - 0.005
        for i, ((a0, b0, p0, h0), (a1, b1, p1, h1)) in enumerate(zip(secs, secs[1:])):
            for k in range(len(p0) - 1):
                if not inz((p0[k] + p1[k + 1]) / 2):
                    continue
                C = [V((p0[k].x, p0[k].y, h0[k])), V((p0[k + 1].x, p0[k + 1].y, h0[k + 1])),
                     V((p1[k + 1].x, p1[k + 1].y, h1[k + 1])), V((p1[k].x, p1[k].y, h1[k]))]
                UV = [(along[i] / 2, arc[i][k] / 2), (along[i] / 2, arc[i][k + 1] / 2),
                      (along[i + 1] / 2, arc[i + 1][k + 1] / 2), (along[i + 1] / 2, arc[i + 1][k] / 2)]
                la, lb = (C[3] - C[0]).length, (C[1] - C[0]).length
                NA, NB = max(1, math.ceil(la / 0.15)), max(1, math.ceil(lb / 0.15))
                bl = lambda s, t, L_: (L_[0] * (1 - s) + L_[1] * s) * (1 - t) + (L_[3] * (1 - s) + L_[2] * s) * t
                blu = lambda s, t: tuple(((UV[0][x] * (1 - s) + UV[1][x] * s) * (1 - t) + (UV[3][x] * (1 - s) + UV[2][x] * s) * t) for x in (0, 1))
                for ia in range(NA):
                    for ib in range(NB):
                        ss = [(ib / NB, ia / NA), ((ib + 1) / NB, ia / NA), ((ib + 1) / NB, (ia + 1) / NA), (ib / NB, (ia + 1) / NA)]
                        pts = [bl(s, t, C) for s, t in ss]
                        m = sum(pts, V((0, 0, 0))) / 4
                        if cut(m):
                            if not pip(m.x, m.y, ci['hole']):          # brick soffit of the reveal ring
                                H['oriented_poly'](mb, [V((p.x, p.y, z_ceil)) for p in pts], V((0, 0, -1)), 'brick_old', uv_scale=2.0)
                            continue
                        mb.poly(pts, 'brick_old', uv=[blu(s, t) for s, t in ss])
                        for e in range(4):                              # reveal where the neighbour is cut away
                            q0, q1 = pts[e], pts[(e + 1) % 4]
                            em = (q0 + q1) / 2
                            nb = em * 2 - m
                            if cut(nb) and q0.z < z_ceil:
                                H['oriented_poly'](mb, [q0, q1, V((q1.x, q1.y, z_ceil)), V((q0.x, q0.y, z_ceil))],
                                                   V((nb.x - m.x, nb.y - m.y, 0)), 'brick_old', uv_scale=2.0)

    def cellar_fittings(self):
        """Transverse-arch brick piers, raised steel walkway with railing (ref 37), Gothic portal fragment (ref 35)."""
        H, V = self.H, self.V
        ci, nav = H.get('CELLAR_INFO'), H['NAV']
        if not ci or 'cellar_bottom' not in nav:
            return
        secs, zf, zs = ci['secs'], H['CELLAR_Z'], ci['zs']
        pip = H['point_in_poly']
        nl = len(secs) - 1
        import bpy
        lc = bpy.data.collections.get('Cellar_Lights')
        for ai, i in enumerate(ci.get('arches', range(2, nl - 1, 4))):
            a, b = secs[i][0], secs[i][1]
            dd = (secs[i + 1][0] - a).normalized()
            for si, (p, inw) in enumerate(((a, (b - a).normalized()), (b, (a - b).normalized()))):
                if pip(p.x, p.y, ci['zone']) or pip((p + inw).x, (p + inw).y, ci['zone']):
                    continue
                if (ai + si) % 3 == 0:                      # warm bracket lantern on the pier face, local pool of light
                    lp = p + inw * 1.0
                    H['seg_box'](self.deco, p + inw * 0.7, lp, -0.015, 0.015, zf + 2.3, zf + 2.34, 'steel_frame')
                    H['lantern'](self.deco, lp, zf + 2.34, zf + 1.85, r=0.12)
                    if lc:
                        H['add_light'](lc, 'L_cellar_wall', (lp.x, lp.y, zf + 2.05), 18, color=(1.0, 0.62, 0.32))
                q = [p - dd * 0.5, p + dd * 0.5, p + dd * 0.5 + inw * 0.72, p - dd * 0.5 + inw * 0.72]
                self.solid.box(q, zf, zs + 0.02, 'brick_old')
                q2 = [p - dd * 0.58, p + dd * 0.58, p + dd * 0.58 + inw * 0.8, p - dd * 0.58 + inw * 0.8]
                self.solid.box(q2, zf, zf + 0.55, 'ashlar_old')
                self.deco.box(q2, zs - 0.12, zs + 0.02, 'ashlar_old')                # impost block
        # raised walkway continuing the stair line along the hall
        bot, low = V(nav['cellar_bottom'][:2]), V(nav['cellar_low'][:2])
        dh = (bot - low).normalized()
        nn = V((-dh.y, dh.x))
        ends = [secs[0][0], secs[-1][0]]
        far = max(ends, key=lambda e: (e - bot).dot(dh))
        L = (far - bot).dot(dh) - 1.8
        if L > 3:
            s0, s1 = bot + dh * 0.2, bot + dh * L
            hw = 0.8
            deck = [s0 - nn * hw, s1 - nn * hw, s1 + nn * hw, s0 + nn * hw]
            if (deck[1] - deck[0]).cross(deck[3] - deck[0]) < 0:
                deck.reverse()
            self.solid.box(deck, zf, zf + 0.17, 'steel_frame', top='planks_old')
            for sgn in (-1, 1):                                                    # dark steel edge channels
                e0, e1 = s0 + nn * (sgn * hw), s1 + nn * (sgn * hw)
                H['seg_box'](self.deco, e0, e1, -0.03, 0.03, zf, zf + 0.2, 'steel_frame')
            k_ = int((s1 - s0).length / 1.5)
            for j in range(k_ + 1):                                                # cross bearers under the deck edge
                pp = s0.lerp(s1, j / max(1, k_))
                H['seg_box'](self.deco, pp - nn * (hw + 0.04), pp + nn * (hw + 0.04), -0.04, 0.04, zf, zf + 0.06, 'steel_frame')
            mid = (secs[nl // 2][0] + secs[nl // 2][1]) / 2
            side = 1 if (bot - mid).dot(nn) > 0 else -1                            # railing on the wall side
            r0, r1 = s0 + nn * (side * (hw - 0.05)), s1 + nn * (side * (hw - 0.05))
            k = int((r1 - r0).length / 1.2)
            for j in range(k + 1):
                pp = r0.lerp(r1, j / k)
                H['seg_box'](self.deco, pp - dh * 0.025, pp + dh * 0.025, -0.025, 0.025, zf + 0.17, zf + 1.17, 'steel_frame')
                if j < k:
                    for t in (0.25, 0.5, 0.75):
                        qq = r0.lerp(r1, (j + t) / k)
                        H['seg_box'](self.deco, qq - dh * 0.008, qq + dh * 0.008, -0.008, 0.008, zf + 0.25, zf + 1.1, 'steel')
            for zz in (zf + 1.12, zf + 0.6):
                H['seg_box'](self.deco, r0, r1, -0.025, 0.025, zz, zz + 0.05, 'steel_frame')
            H['seg_box'](self.P['ramps'], r0, r1, -0.05, 0.05, zf, zf + 1.2, 'stone')
        # Gothic portal fragment on the far end wall: chamfered stone jambs and a pointed arch
        a, b = (secs[0][0], secs[0][1]) if far is secs[0][0] else (secs[-1][0], secs[-1][1])
        other = secs[1][0] if far is secs[0][0] else secs[-2][0]
        c = (a + b) / 2
        inw = (other - far).normalized()
        tg = (b - a).normalized()
        w, hj = 0.75, 2.1
        for sx in (-1, 1):
            j0 = c + tg * (sx * w)
            self.deco.box([j0 - tg * 0.16, j0 + tg * 0.16, j0 + tg * 0.12 + inw * 0.22, j0 - tg * 0.12 + inw * 0.22], zf, zf + hj, 'stone')
        rr = 2 * w
        for sx in (-1, 1):                 # two arcs centred on the opposite springing points
            cen = c - tg * (sx * w)
            pts = []
            for k in range(9):
                th = math.acos(0.5) * k / 8
                p2 = cen + tg * (sx * rr * math.cos(th)) + inw * 0.1
                pts.append(V((p2.x, p2.y, zf + hj + rr * math.sin(th))))
            for p0, p1 in zip(pts, pts[1:]):
                H['_prism'](self.deco, p0, p1, 0.14, 0.14, 'stone', seg=5)
        rec = [c - tg * (w - 0.1) + inw * 0.04, c + tg * (w - 0.1) + inw * 0.04]
        H['oriented_poly'](self.deco, [V((rec[0].x, rec[0].y, zf)), V((rec[1].x, rec[1].y, zf)),
                                        V((rec[1].x, rec[1].y, zf + hj)), V((rec[0].x, rec[0].y, zf + hj))],
                           V((inw.x, inw.y, 0)), 'wall_dark')

    # ------------------------------------------------------------ dark exhibition rooms (ref 33)
    def dark_exhibition(self, r, z0):
        """Navy carpet, tall lit glass vitrines with shelves of gilt objects."""
        H, V = self.H, self.V
        c, n, d = r['c'], r['n'], r['d']
        self.floor_overlay(r, z0, 'carpet_navy')
        if 'dark_room' not in H['NAV']:
            cam = c - n * (r['D'] * 0.42) - d * (r['L'] * 0.4)
            H['NAV']['dark_room'] = [cam.x, cam.y, z0 + 1.65, c.x + d.x * r['L'] * 0.3, c.y + d.y * r['L'] * 0.3, z0 + 1.2]
        for sx in (-1, 1):
            for sy in (-1, 1):
                p = c + d * (sx * r['L'] * 0.22) + n * (sy * r['D'] * 0.14)
                q = lambda h: [p - d * h - n * h, p + d * h - n * h, p + d * h + n * h, p - d * h + n * h]
                self.solid.box(q(0.38), z0, z0 + 0.3, 'panel_board')
                g = q(0.35)
                for j in range(4):
                    a, b = g[j], g[(j + 1) % 4]
                    self.deco.poly([V((a.x, a.y, z0 + 0.3)), V((b.x, b.y, z0 + 0.3)), V((b.x, b.y, z0 + 2.0)), V((a.x, a.y, z0 + 2.0))], 'glass')
                    H['_prism'](self.deco, V((a.x, a.y, z0 + 0.3)), V((a.x, a.y, z0 + 2.0)), 0.008, 0.008, 'steel', seg=4)
                self.solid.box(q(0.38), z0 + 2.0, z0 + 2.12, 'panel_board', bottom='lamp')        # lit canopy
                self.solid.box(q(0.36), z0 + 0.3, z0 + 2.0, 'invisible')
                for zz in (0.95, 1.45):
                    self.deco.poly([V((v.x, v.y, z0 + zz)) for v in q(0.33)], 'glass')
                for zz, kind in ((0.31, 0), (0.96, 1), (1.46, 2)):
                    o = p + d * (0.1 * ((kind % 2) * 2 - 1))
                    if kind == 1:
                        H['lathe_up'](self.deco, o, z0 + zz, [(0.0, 0.0), (0.06, 0.0), (0.03, 0.05), (0.08, 0.16), (0.03, 0.26), (0.0, 0.27)], 'gold', seg=10)
                    else:
                        H['ellipsoid'](self.deco, V((o.x, o.y, z0 + zz + 0.08)), 0.09, 0.09, 0.08, 0, 0, 'gold' if kind else 'steel', subdiv=1)

    # ------------------------------------------------------------ corridors: museum life
    def corridors(self):
        """Lanterns on the vault-bay rhythm, courtyard window niches with benches, framed info panels and
        maps between the room doors, plaques over the doors."""
        H, V, P = self.H, self.V, self.P
        import bpy
        lc = bpy.data.collections.get('Interior_Lights')
        bay, rise = 4.7, 0.85
        for a, b, n, Wc in P.get('corridor_segs', []):
            dd = (b - a).normalized()
            a2, b2 = a + dd * (Wc + self.PART), b - dd * (Wc + self.PART)
            L = (b2 - a2).length
            nb = int(L / bay)
            for zi in range(len(self.FZ)):
                ceil = self.ceil(zi)
                ribs = [0.0] + [k * bay for k in range(1, nb)] + [L]   # same bays as corridor_vaults
                for k in range(len(ribs) - 1):            # lantern in the middle of every vault bay
                    p = a2 + dd * ((ribs[k] + ribs[k + 1]) / 2) + n * (Wc / 2)
                    H['lantern'](self.deco, p, ceil - 0.03, ceil - 1.05)
                    if lc and k % 2 == 0:
                        H['add_light'](lc, f'L_corr_{zi}', (p.x, p.y, ceil - 0.6), 30)
        sill = P.get('sill', [1.1, 1.0, 1.0, 1.0])
        hts = [0, 2.6, 2.5, 2.2]
        for w in self.W:
            i0, i1 = w['i']
            Li = (i1 - i0).length
            d_i = (i1 - i0) / Li
            n_i = V((d_i.y, -d_i.x))
            nax = 10 if Li > 45 else 6
            axes = [2.6 + (Li - 5.2) * (g + 0.5) / nax for g in range(nax)]
            face = self.H['COURT_T'] + 0.01
            for zi in range(1, len(self.FZ)):
                z0 = self.FZ[zi]
                for g, u in enumerate(axes):
                    if u < 4.5 or u > Li - 4.5:
                        continue                                    # corridor corners
                    a = i0 + d_i * (u - 0.68) + n_i * face
                    b = i0 + d_i * (u + 0.68) + n_i * face
                    zt = z0 + sill[zi] + hts[zi]
                    if g % 2 == 0:                                  # bench in the window niche
                        p = (a + b) / 2 + n_i * 0.24
                        q = [p - d_i * 0.7 - n_i * 0.21, p + d_i * 0.7 - n_i * 0.21, p + d_i * 0.7 + n_i * 0.21, p - d_i * 0.7 + n_i * 0.21]
                        self.solid.box(q, z0 + 0.4, z0 + 0.47, 'oak_honey')
                        for pp in q:
                            p2 = p + (pp - p) * 0.88
                            H['_prism'](self.deco, V((p2.x, p2.y, z0)), V((p2.x, p2.y, z0 + 0.4)), 0.025, 0.025, 'steel', seg=4)
        # info panels / maps between room doors, plaques over the doors (corridor side of the room walls)
        for zi in range(1, len(self.FZ)):
            z0 = self.FZ[zi]
            for j, r in enumerate(self.rooms):
                if r['stair'] or r['L'] < 4.5:
                    continue
                a, b, n = r['wall_a'], r['wall_b'], r['n']
                dvec = (b - a).normalized()
                face = -n * (self.PART / 2 + 0.03)
                mid = (a + b) / 2 + face
                self.deco.box([mid - dvec * 0.55, mid + dvec * 0.55, mid + dvec * 0.55 - n * 0.05, mid - dvec * 0.55 - n * 0.05],
                              z0 + 3.4, z0 + 3.62, 'panel_board')                     # room plaque over the door
                if (j + zi) % 2 == 0:
                    continue
                p = (a + b) / 2 + dvec * (r['L'] * 0.3) + face
                is_map = (j + zi) % 4 == 1
                hw, h0, h1 = (0.7, z0 + 1.15, z0 + 2.15) if is_map else (0.45, z0 + 1.2, z0 + 2.0)
                fr = [p - dvec * hw, p + dvec * hw, p + dvec * hw - n * 0.04, p - dvec * hw - n * 0.04]
                self.deco.box(fr, h0, h1, 'frame' if is_map else 'panel_board')
                inner = [V((x.x, x.y, 0)) for x in (p - dvec * (hw - 0.06) - n * 0.045, p + dvec * (hw - 0.06) - n * 0.045)]
                quad = [V((inner[0].x, inner[0].y, h0 + 0.06)), V((inner[1].x, inner[1].y, h0 + 0.06)),
                        V((inner[1].x, inner[1].y, h1 - 0.06)), V((inner[0].x, inner[0].y, h1 - 0.06))]
                H['oriented_poly'](self.deco, quad, V((-n.x, -n.y, 0)), 'map_paper' if is_map else 'panel_text')
                if is_map:                                          # a few land masses and the Danube line
                    for k in range(4):
                        cx = p + dvec * ((k - 1.5) * 0.3) - n * 0.05
                        H['ellipsoid'](self.deco, V((cx.x, cx.y, (h0 + h1) / 2 + 0.12 * math.sin(k * 1.7))), 0.18, 0.004, 0.14,
                                       math.atan2(dvec.y, dvec.x), 0, 'map_land', subdiv=1)
                else:
                    H['seg_box'](self.deco, p - dvec * (hw - 0.1) - n * 0.05, p + dvec * (hw - 0.1) - n * 0.05, -0.002, 0.002,
                                 h1 - 0.2, h1 - 0.12, 'panel_board')

    # ------------------------------------------------------------ Crown Tower
    def crown_tower(self):
        """Ground floor: darkened treasury with spot-lit cases (ref 34). Top: viewing room with a small exhibition."""
        H, V = self.H, self.V
        import bpy
        sq = self.P['tower_sq'][0][1]
        cen = sum(sq, V((0, 0))) / 4
        lc = bpy.data.collections.get('Interior_Lights')
        faces = []
        for k in range(4):
            a, b = sq[k], sq[(k + 1) % 4]
            L = (b - a).length
            dvec = (b - a) / L
            nl = V((-dvec.y, dvec.x))
            inw = nl if (cen - (a + b) / 2).dot(nl) > 0 else -nl
            faces.append((a + inw * 0.91, dvec, inw, L))
        ceil0 = self.FZ[1] - self.SLAB
        for a, dvec, inw, L in faces:                     # dark wall panels, leaving the central door/window bay free
            for s0, s1 in ((0.95, L / 2 - 1.0), (L / 2 + 1.0, L - 0.95)):
                pa, pb = a + dvec * s0, a + dvec * s1
                H['oriented_poly'](self.deco, [V((pa.x, pa.y, 0.03)), V((pb.x, pb.y, 0.03)), V((pb.x, pb.y, ceil0 - 0.05)), V((pa.x, pa.y, ceil0 - 0.05))],
                                   V((inw.x, inw.y, 0)), 'wall_dark')
        hs = 9.6 / 2 - 0.95
        fl = [cen + V((-hs, -hs)), cen + V((hs, -hs)), cen + V((hs, hs)), cen + V((-hs, hs))]
        self.deco.poly([V((p.x, p.y, 0.008)) for p in fl], 'carpet_navy')
        lt = bpy.data.objects.get('L_treasury')
        if lt:
            lt.data.energy *= 0.35

        def spot(name, loc, tgt, energy, deg=28):
            if not lc:
                return
            ld = bpy.data.lights.new(name, 'SPOT')
            ld.energy, ld.spot_size, ld.spot_blend, ld.color = energy, math.radians(deg), 0.4, (1.0, 0.93, 0.8)
            ob = bpy.data.objects.new(name, ld)
            ob.location = loc
            ob.rotation_euler = (V(tgt) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
            lc.objects.link(ob)
        top = ceil0 - 0.2
        spot('L_treasury_crown', (cen.x - 0.8, cen.y - 0.8, top), (cen.x, cen.y, 1.1), 120)
        for off in (V((2.2, 1.4)), V((-1.4, 2.2))):
            p = cen + off
            spot('L_treasury_case', (p.x - 0.5, p.y - 0.5, top), (p.x, p.y, 1.05), 60, 22)
        # viewing room at the top: small exhibition in the corners + wall panels
        zf = self.EAVE + 0.02
        H['NAV']['crown_top'] = [cen.x + 3.4, cen.y - 1.0, zf + 1.65, cen.x - 3.3, cen.y + 3.3, zf + 1.0]
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            p = cen + V((sx * 3.3, sy * 3.3))
            q = lambda h: [p + V((-h, -h)), p + V((h, -h)), p + V((h, h)), p + V((-h, h))]
            self.solid.box(q(0.3), zf, zf + 0.95, 'panel_board', top='joinery')
            g = q(0.27)
            for j in range(4):
                a, b = g[j], g[(j + 1) % 4]
                self.deco.poly([V((a.x, a.y, zf + 0.95)), V((b.x, b.y, zf + 0.95)), V((b.x, b.y, zf + 1.4)), V((a.x, a.y, zf + 1.4))], 'glass')
            self.deco.poly([V((v.x, v.y, zf + 1.4)) for v in g], 'glass')
            self.solid.box(q(0.28), zf + 0.95, zf + 1.4, 'invisible')
            H['ellipsoid'](self.deco, V((p.x, p.y, zf + 1.03)), 0.08, 0.05, 0.07, 0, 0, 'gold' if sx > 0 else 'steel', subdiv=1)
        for a, dvec, inw, L in faces:
            for s in (L / 2 - 2.0, L / 2 + 2.0):
                p = a + dvec * s + inw * 0.02
                self.deco.box([p - dvec * 0.4, p + dvec * 0.4, p + dvec * 0.4 + inw * 0.03, p - dvec * 0.4 + inw * 0.03],
                              zf + 1.15, zf + 1.95, 'panel_board')
                pp = p + inw * 0.035
                H['oriented_poly'](self.deco, [V(((pp - dvec * 0.34).x, (pp - dvec * 0.34).y, zf + 1.22)), V(((pp + dvec * 0.34).x, (pp + dvec * 0.34).y, zf + 1.22)),
                                               V(((pp + dvec * 0.34).x, (pp + dvec * 0.34).y, zf + 1.78)), V(((pp - dvec * 0.34).x, (pp - dvec * 0.34).y, zf + 1.78))],
                                   V((inw.x, inw.y, 0)), 'map_paper' if s < L / 2 else 'panel_text')
