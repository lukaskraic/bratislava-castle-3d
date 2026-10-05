"""Procedural tileable textures (numpy -> PNG) so the glTF export carries real images."""
import numpy as np
import os


def _noise(n, scale, rng):
    """Smooth value noise, tileable, n x n."""
    g = rng.random((scale, scale))
    x = np.linspace(0, scale, n, endpoint=False)
    i0 = np.floor(x).astype(int) % scale
    i1 = (i0 + 1) % scale
    f = x - np.floor(x)
    f = f * f * (3 - 2 * f)
    a = g[i0][:, i0] * (1 - f)[None, :] + g[i0][:, i1] * f[None, :]
    b = g[i1][:, i0] * (1 - f)[None, :] + g[i1][:, i1] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def fbm(n, rng, octaves=(4, 8, 16, 32, 64), weights=None):
    weights = weights or [0.5 ** k for k in range(len(octaves))]
    out = sum(w * _noise(n, o, rng) for o, w in zip(octaves, weights))
    return (out - out.min()) / (np.ptp(out) + 1e-9)


def normal_from(rgb, strength):
    """Tangent-space normal map from luminance height (tileable gradients)."""
    h = rgb.mean(axis=2)
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.stack([-dx, dy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def _save(path, rgb, colorspace=None):
    import bpy
    h, w, c = rgb.shape
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=(c == 4))
    rgba = np.clip(rgb, 0, 1) if c == 4 else np.concatenate([np.clip(rgb, 0, 1), np.ones((h, w, 1))], axis=2)
    img.pixels.foreach_set(rgba[::-1].astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    if colorspace:
        img.colorspace_settings.name = colorspace
    return img


def col(hexstr):
    hexstr = hexstr.lstrip('#')
    return np.array([int(hexstr[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def plaster(n, rng, base='#ECE8DF', var=0.05):
    nz = fbm(n, rng)[..., None]
    fine = rng.random((n, n, 1))
    return col(base) * (1 - var + var * 2 * nz) * (0.97 + 0.03 * fine)


def roof_tiles(n, rng):
    """Beaver-tail tiles: rows of rounded tiles, staggered."""
    rows, cols = 16, 12
    y, x = np.mgrid[0:n, 0:n] / n
    ry = y * rows
    row = np.floor(ry).astype(int)
    fy = ry - row
    cx = x * cols + (row % 2) * 0.5
    c = np.floor(cx).astype(int)
    fx = cx - c
    edge = np.sqrt(((fx - 0.5) * 2) ** 2 + np.clip(fy * 1.2 - 0.2, 0, 1) ** 2)
    shade = 1 - 0.55 * np.clip(edge - 0.75, 0, 1) * 4
    shade *= 0.85 + 0.15 * fy
    tid = (row * 31 + c * 17) % 97 / 97.0
    tint = 0.85 + 0.25 * tid
    nz = fbm(n, rng)
    base = col('#D8653A')
    rgb = base[None, None, :] * (shade * tint * (0.85 + 0.3 * nz))[..., None]
    rgb[..., 1] *= 0.95 + 0.1 * nz
    return rgb


def stone_blocks(n, rng, base='#BDB5A6', rows=6, cols=3, mortar='#8F887C'):
    y, x = np.mgrid[0:n, 0:n] / n
    ry = y * rows
    row = np.floor(ry).astype(int)
    cx = x * cols + (row % 2) * 0.5
    c = np.floor(cx).astype(int)
    fx, fy = cx - c, ry - row
    joint = (np.minimum(fx, 1 - fx) < 0.02) | (np.minimum(fy, 1 - fy) < 0.04)
    tid = ((row * 13 + c * 7) % 23) / 23.0
    nz = fbm(n, rng)
    rgb = col(base)[None, None, :] * (0.88 + 0.12 * tid + 0.12 * (nz - 0.5))[..., None]
    rgb[joint] = col(mortar)
    return rgb


def rubble(n, rng, cells=18):
    """Irregular rubble masonry (castle bastions): Voronoi stones with mortar gaps, tileable."""
    pts = (np.stack(np.meshgrid(np.arange(cells), np.arange(cells)), -1).reshape(-1, 2)
           + rng.random((cells * cells, 2)) * 0.8 + 0.1) / cells
    pts = np.concatenate([pts + np.array([dx, dy]) for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    tone = np.tile(rng.random(cells * cells), 9)
    warm = np.tile(rng.random(cells * cells), 9)
    y, x = np.mgrid[0:n, 0:n] / n
    xy = np.stack([x.ravel(), y.ravel()], 1)
    d1 = np.full(len(xy), 9.0)
    d2 = np.full(len(xy), 9.0)
    idx = np.zeros(len(xy), dtype=int)
    for i, p in enumerate(pts):
        d = np.hypot(xy[:, 0] - p[0], (xy[:, 1] - p[1]) * 2.2)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        idx = np.where(closer, i, idx)
        d1 = np.where(closer, d, d1)
    gap = ((d2 - d1) < (0.008 + 0.012 * rng.random())).reshape(n, n)
    t = tone[idx].reshape(n, n)
    w = warm[idx].reshape(n, n)
    nz = fbm(n, rng)
    base = col('#A79E8E')[None, None] * (0.78 + 0.32 * t + 0.15 * (nz - 0.5))[..., None]
    brick = (w > 0.95)[..., None]
    base = np.where(brick, col('#9C7A64')[None, None] * (0.8 + 0.25 * t[..., None]), base)
    base[gap] = col('#7E776B')
    return base


HEIGHTS = {}


def _voronoi(n, rng, cells, aspect=1.0, warp=0.0):
    """Tileable Voronoi: returns (d1, d2, cell index) for an n x n tile."""
    pts = (np.stack(np.meshgrid(np.arange(cells), np.arange(cells)), -1).reshape(-1, 2)
           + rng.random((cells * cells, 2)) * 0.8 + 0.1) / cells
    allp = np.concatenate([pts + np.array([dx, dy]) for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    ids = np.tile(np.arange(cells * cells), 9)
    y, xg = np.mgrid[0:n, 0:n] / n
    if warp:
        xg = xg + warp * (fbm(n, rng, octaves=(4, 8)) - 0.5)
        y = y + warp * (fbm(n, rng, octaves=(4, 8)) - 0.5)
    xy = np.stack([xg.ravel(), y.ravel()], 1)
    d1 = np.full(len(xy), 9.0, dtype=np.float32)
    d2 = np.full(len(xy), 9.0, dtype=np.float32)
    idx = np.zeros(len(xy), dtype=np.int32)
    # only test seeds near each pixel: iterate seeds but restrict with a bounding test
    for i, p in enumerate(allp):
        if not (-1.5 / cells < p[0] < 1 + 1.5 / cells and -1.5 / cells < p[1] < 1 + 1.5 / cells):
            continue
        d = np.hypot(xy[:, 0] - p[0], (xy[:, 1] - p[1]) * aspect)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        idx = np.where(closer, ids[i], idx)
        d1 = np.where(closer, d, d1)
    return d1.reshape(n, n), d2.reshape(n, n), idx.reshape(n, n)


def cobbles(n, rng):
    """Granite setts laid in courses: ~100 mm rows, 90-130 mm stones, jittered edges, sandy joints.
    1.5 m tile -> 15 rows. Height: flat crowns, 2-4 mm bevel, recessed joints."""
    rows = 15
    y, xg = np.mgrid[0:n, 0:n] / n
    warp_x = (fbm(n, rng, octaves=(8, 16)) - 0.5) * 0.012
    warp_y = (fbm(n, rng, octaves=(8, 16)) - 0.5) * 0.012
    yy = (y + warp_y) % 1.0
    xx = (xg + warp_x) % 1.0
    ry = yy * rows
    row = np.floor(ry).astype(int) % rows
    fy = ry - np.floor(ry)
    # per-row random stone widths (in tile units), cumulative edges, tile-periodic
    edges = []
    for r in range(rows):
        ws = []
        tot = 0.0
        while tot < 1.0:
            w = rng.uniform(0.06, 0.087)          # 90-130 mm at 1.5 m per tile
            ws.append(w)
            tot += w
        ws = np.array(ws) / tot
        e = np.concatenate([[0], np.cumsum(ws)]) + rng.uniform(0, 1)
        edges.append(e)
    fx = np.zeros_like(xx)
    sid = np.zeros_like(row)
    for r in range(rows):
        m = row == r
        e = edges[r]
        xs = (xx[m] - e[0]) % 1.0 + e[0]
        k = np.searchsorted(e, xs) - 1
        k = np.clip(k, 0, len(e) - 2)
        fx[m] = (xs - e[k]) / (e[k + 1] - e[k])
        sid[m] = r * 31 + k
    jw = 0.07 + 0.04 * fbm(n, rng, octaves=(16, 32))      # joint width varies 5-10 mm
    dx = np.minimum(fx, 1 - fx) / jw
    dy = np.minimum(fy, 1 - fy) / (jw * 0.7)
    dist = np.minimum(dx, dy)
    joint = dist < 1.0
    tone = (sid * 0.618) % 1.0
    speck = rng.random((n, n))
    nz = fbm(n, rng)
    base = np.stack([0.56 + 0.12 * tone, 0.54 + 0.11 * tone, 0.51 + 0.1 * tone], -1)
    base *= (0.88 + 0.18 * nz[..., None]) * (0.92 + 0.12 * speck[..., None])
    warm = ((sid * 0.37) % 1.0) > 0.82
    base[warm] *= np.array([1.07, 1.0, 0.9])
    rgb = np.where(joint[..., None], col('#77705F')[None, None] * (0.85 + 0.25 * nz[..., None]), base)
    HEIGHTS['cobbles'] = np.clip((dist - 1.0) / 1.6, 0, 1) ** 0.5 * 0.85 + 0.15 * nz * (dist > 1)
    return rgb


def parquet(n, rng):
    """Herringbone-ish oak parquet."""
    y, x = np.mgrid[0:n, 0:n] / n
    k = 8
    u, v = x * k, y * k
    cell = (np.floor(u) + np.floor(v)).astype(int) % 2
    along = np.where(cell == 0, u, v)
    across = np.where(cell == 0, v, u)
    plank = np.floor(across * 4).astype(int)
    # directional grain running along each board, plus per-board tone
    wob = fbm(n, rng, octaves=(4, 16))
    grain = 0.5 + 0.5 * np.sin((across * 4 % 1) * 2 * np.pi * 9 + wob * 6 + along * 0.7)
    grain = 0.7 * grain + 0.3 * fbm(n, rng, octaves=(64, 128))
    tid = ((plank * 7 + np.floor(along).astype(int) * 3 + cell * 11) % 13) / 13.0
    seam = (np.abs((across * 4) % 1 - 0.5) > 0.47) | (np.abs(along % 1 - 0.5) > 0.49)
    shade = (0.78 + 0.3 * tid) * (0.82 + 0.22 * grain)
    shade[seam] *= 0.6
    return col('#9A6A3C')[None, None, :] * shade[..., None]


def marble(n, rng):
    """Light limestone/marble floor tiles: domain-warped branching veins with soft cores,
    per-tile tone shift, thin recessed grout (height kept separate from veins)."""
    y, xg = np.mgrid[0:n, 0:n] / n
    w1 = fbm(n, rng, octaves=(2, 4, 8))
    w2 = fbm(n, rng, octaves=(4, 8, 16))
    u = xg * 3 + w1 * 2.2
    v_ = y * 3 + w2 * 2.2
    f = fbm(n, rng, octaves=(4, 8, 16, 32, 64))
    ridge = 1 - np.abs(np.sin((u + v_ * 0.6 + f * 3.0) * np.pi))       # branching ridges
    vein = np.clip((ridge - 0.8) / 0.2, 0, 1) ** 2
    fine = np.clip((1 - np.abs(np.sin((u * 2.3 - v_ + f * 5) * np.pi)) - 0.93) / 0.07, 0, 1)
    tile = (np.floor(xg * 2) + np.floor(y * 2) * 2).astype(int)
    tone = np.choose(tile % 4, [1.0, 0.97, 1.02, 0.985])
    base = col('#E4DED2')[None, None] * tone[..., None] * (0.96 + 0.06 * f[..., None])
    rgb = base * (1 - 0.11 * vein[..., None] - 0.04 * fine[..., None])
    rgb[..., 0] *= 1 - 0.03 * vein
    grout = ((np.abs((xg * 2) % 1 - 0.5) > 0.496) | (np.abs((y * 2) % 1 - 0.5) > 0.496))
    rgb[grout] = col('#BFB6A6')
    HEIGHTS['marble'] = np.where(grout, 0.0, 1.0)
    return rgb


def gravel(n, rng):
    nz = fbm(n, rng, octaves=(16, 64, 128, 256), weights=[0.2, 0.3, 0.3, 0.2])
    return col('#CFC6B3')[None, None, :] * (0.8 + 0.35 * nz)[..., None]


def gravel_red(n, rng):
    """Crushed-brick gravel of the broderie beds."""
    nz = fbm(n, rng, octaves=(16, 64, 128, 256), weights=[0.2, 0.3, 0.3, 0.2])
    return col('#B5643F')[None, None, :] * (0.8 + 0.35 * nz)[..., None]


def gravel_white(n, rng):
    nz = fbm(n, rng, octaves=(32, 128, 256), weights=[0.3, 0.4, 0.3])
    return col('#ADA38F')[None, None, :] * (0.82 + 0.26 * nz)[..., None]


def hedge(n, rng):
    nz = fbm(n, rng, octaves=(8, 32, 64, 128), weights=[0.2, 0.3, 0.3, 0.2])
    return col('#3E5E2A')[None, None, :] * (0.6 + 0.7 * nz)[..., None]


def bark(n, rng):
    nz = fbm(n, rng, octaves=(2, 32, 64))
    stripes = 0.8 + 0.2 * np.sin(np.linspace(0, 40, n))[None, :]
    return col('#5A4636')[None, None, :] * (stripes * (0.7 + 0.5 * nz))[..., None]


def foliage(n, rng):
    nz = fbm(n, rng, octaves=(8, 16, 64, 128), weights=[0.3, 0.3, 0.2, 0.2])
    return col('#6B8C45')[None, None, :] * (0.7 + 0.6 * nz)[..., None]


def painting2(n, rng, kind):
    """Old-master canvases with brush texture and craquelure: landscape, portrait, still life, harbour."""
    y, xg = np.mgrid[0:n, 0:n] / n
    y = 1 - y
    nz = fbm(n, rng, octaves=(2, 4, 8, 16))
    brush = fbm(n, rng, octaves=(32, 64, 128)) - 0.5
    if kind == 'landscape':
        sky = col('#D8C690') * (1 - y[..., None]) * 0.6 + col('#7C8C96') * y[..., None] + 0.05
        hor = 0.4 + 0.06 * np.sin(xg * 5 + nz * 2.5) + 0.04 * nz
        land = col('#4A4B2C') * (0.5 + 0.7 * nz[..., None])
        img = np.where((y < hor)[..., None], land, sky)
        for cx_, w_ in ((0.22, 0.11), (0.7, 0.07)):
            tr = (np.abs(xg - cx_) < w_ * (1.2 - (y - hor) / 0.35)) & (y > hor - 0.03) & (y < hor + 0.33)
            img[tr] = col('#2C3420') * (0.7 + 0.5 * nz[tr][..., None])
        river = (y < hor - 0.05) & (y > hor - 0.12 - 0.05 * xg) & (np.abs(xg - 0.55 + (hor - y)) < 0.25)
        img[river] = col('#9AA6A2') * (0.85 + 0.2 * nz[river][..., None])
    elif kind == 'portrait':
        img = np.ones((n, n, 1)) * col('#2A2018')[None, None] * (0.6 + 0.6 * nz[..., None])
        fx, fy = (xg - 0.5) / 0.14, (y - 0.63) / 0.19
        face = fx ** 2 + fy ** 2 < 1
        body = (((xg - 0.5) / 0.4) ** 2 + ((y - 0.02) / 0.42) ** 2 < 1) & (y < 0.45)
        hair = ((((xg - 0.5) / 0.17) ** 2 + ((y - 0.69) / 0.21) ** 2) < 1) & ~face | (face & (fy > 0.55))
        collar = body & (np.abs(xg - 0.5) < 0.16) & (y > 0.33)
        img[body] = col('#5C1E18') * (0.6 + 0.6 * nz[body][..., None])
        img[collar] = col('#E4DCCB')
        img[hair] = col('#3A2A1C') * (0.7 + 0.5 * nz[hair][..., None])
        light = np.clip(0.75 - fx * 0.25, 0.4, 1.0)
        img[face] = (col('#D2A584') * light[face][..., None])
        for ex in (-0.35, 0.35):
            eye = ((fx - ex) / 0.16) ** 2 + ((fy - 0.12) / 0.07) ** 2 < 1
            img[eye] = col('#3A2A20')
        mouth = (np.abs(fx) < 0.28) & (np.abs(fy + 0.45) < 0.04)
        img[mouth] = col('#8A4A3C')
        nose = (np.abs(fx - 0.05) < 0.07) & (fy > -0.25) & (fy < 0.1)
        img[nose] *= 0.85
    elif kind == 'still':
        img = np.ones((n, n, 1)) * col('#1E1812')[None, None] * (0.7 + 0.5 * nz[..., None])
        table = y < 0.3
        img[table] = col('#4A3220') * (0.7 + 0.4 * nz[table][..., None])
        for cx_, cy_, r_, c_ in ((0.35, 0.42, 0.12, '#A8382A'), (0.55, 0.38, 0.09, '#C8A040'), (0.68, 0.45, 0.11, '#5A7A30'), (0.45, 0.6, 0.15, '#B8B0A0')):
            fr = ((xg - cx_) ** 2 + (y - cy_) ** 2) < r_ ** 2
            sh = np.clip(1.1 - ((xg - cx_ + 0.04) ** 2 + (y - cy_ - 0.04) ** 2) / r_ ** 2, 0.4, 1.2)
            img[fr] = col(c_) * sh[fr][..., None]
    else:   # harbour
        sky = col('#C9B98E') * (1 - y[..., None]) + col('#5F7488') * y[..., None]
        sea = y < 0.35
        img = sky * (0.85 + 0.3 * nz[..., None])
        img[sea] = col('#3E5560') * (0.7 + 0.5 * nz[sea][..., None])
        hull = (np.abs(xg - 0.5) < 0.18) & (y > 0.3) & (y < 0.38)
        img[hull] = col('#3A2618')
        for mx in (0.42, 0.56):
            mast = (np.abs(xg - mx) < 0.006) & (y > 0.38) & (y < 0.75)
            img[mast] = col('#2A1C12')
            sail = (xg > mx + 0.01) & (xg < mx + 0.1 - (y - 0.42) * 0.15) & (y > 0.42) & (y < 0.7)
            img[sail] = col('#D8CCB0') * (0.8 + 0.3 * nz[sail][..., None])
    for _ in range(4):        # soften shapes into painterly transitions
        img = (img + np.roll(img, 1, 0) + np.roll(img, -1, 0) + np.roll(img, 1, 1) + np.roll(img, -1, 1)) / 5
    img = img + brush[..., None] * 0.08
    crack = (np.abs(fbm(n, rng, octaves=(16, 32, 64)) - 0.5) < 0.003)
    img[crack] *= 0.9
    varnish = col('#C8A060') * 0.08
    vign = 1 - 0.5 * (((xg - 0.5) ** 2 + (y - 0.5) ** 2) * 2.0)
    return np.clip((img * 0.85 + varnish) * vign[..., None], 0, 1)


def flag_sk(w=384, h=256):
    """Slovak flag: white/blue/red with the state coat of arms toward the hoist."""
    y, x = np.mgrid[0:h, 0:w]
    yy = y / h                                   # 0 = top
    img = np.where((yy < 1 / 3)[..., None], col('#FFFFFF'), np.where((yy < 2 / 3)[..., None], col('#0B4EA2'), col('#EE1C25')))
    img = img * np.ones((h, w, 1))
    cx, top, bot, sw = w * 0.31, h * 0.17, h * 0.85, w * 0.135     # shield box
    u = (x - cx) / sw
    v = (y - top) / (bot - top)
    inside = (np.abs(u) <= 1) & (v >= 0) & (v <= 1) & ((v < 0.62) | (u ** 2 + ((v - 0.62) / 0.38) ** 2 <= 1))
    border = inside & ~((np.abs(u) <= 0.92) & (v >= 0.03) & (v <= 0.97) & ((v < 0.62) | (u ** 2 + ((v - 0.62) / 0.36) ** 2 <= 0.85)))
    img[inside] = col('#EE1C25')
    img[border] = col('#FFFFFF')
    hills = inside & (v > 0.72) & ((((u + 0.55) / 0.42) ** 2 + ((v - 0.86) / 0.16) ** 2 <= 1) |
                                   (((u - 0.55) / 0.42) ** 2 + ((v - 0.86) / 0.16) ** 2 <= 1) |
                                   ((u / 0.48) ** 2 + ((v - 0.80) / 0.2) ** 2 <= 1) | (v > 0.86))
    img[hills & ~border] = col('#0B4EA2')
    cross = inside & ~hills & ((np.abs(u) < 0.09) & (v > 0.12) & (v < 0.80) |
                               (np.abs(u) < 0.42) & (np.abs(v - 0.30) < 0.045) |
                               (np.abs(u) < 0.55) & (np.abs(v - 0.50) < 0.05))
    img[cross & ~border] = col('#FFFFFF')
    return img


def brick(n, rng):
    """Old hand-made brick (cellar vaults): staggered courses, varied firing, worn mortar."""
    rows, cols = 28, 8                 # 2 m tile -> 250 x 71 mm bricks
    y, xg = np.mgrid[0:n, 0:n] / n
    y = y + (fbm(n, rng, octaves=(8, 16)) - 0.5) * 0.004     # courses wander +-4 mm
    xg = xg + (fbm(n, rng, octaves=(8, 16)) - 0.5) * 0.004
    ry = y * rows
    row = np.floor(ry).astype(int)
    cx = xg * cols + (row % 2) * 0.5
    c = np.floor(cx).astype(int)
    fx, fy = cx - c, ry - row
    jv = 1 + 0.5 * (fbm(n, rng, octaves=(16, 32)) - 0.5)
    joint = (np.minimum(fx, 1 - fx) < 0.025 * jv) | (np.minimum(fy, 1 - fy) < 0.08 * jv)
    tid = ((row * 13 + c * 7) % 29) / 29.0
    nz = fbm(n, rng)
    base = col('#9A5636')[None, None] * (0.7 + 0.45 * tid[..., None] + 0.15 * (nz[..., None] - 0.5))
    chip = (fbm(n, rng, octaves=(32, 64, 128)) > 0.78) & ~joint
    base[chip] *= 0.75
    base[joint] = col('#B8AE9C') * (0.8 + 0.2 * nz[joint][..., None])
    smear = fbm(n, rng, octaves=(2, 4, 8)) > 0.68            # lime wash remnants
    base[smear] = base[smear] * 0.6 + col('#CFC6B4') * 0.4
    damp = fbm(n, rng, octaves=(1, 2, 4))
    base *= (1 - 0.25 * np.clip(damp - 0.55, 0, 1) * 2)[..., None]
    jd = np.minimum(np.minimum(fx, 1 - fx) / 0.025, np.minimum(fy, 1 - fy) / 0.08)
    HEIGHTS['brick'] = np.clip(jd, 0, 1) * (1 - 0.4 * chip)
    return base


def leaves(n, rng, base='#4F7A32', count=520, spread=0.46):
    """RGBA leaf-cluster card: many small lanceolate leaves on twigs, alpha-cut background."""
    img = np.zeros((n, n, 4))
    y, x = np.mgrid[0:n, 0:n] / n
    bc = col(base)
    # twigs
    for _ in range(9):
        a = rng.uniform(0, 2 * np.pi)
        L = rng.uniform(0.25, 0.45)
        t = np.linspace(0, 1, 200)
        px_ = 0.5 + np.cos(a) * L * t
        py_ = 0.5 + np.sin(a) * L * t
        for qx, qy in zip((px_ * n).astype(int), (py_ * n).astype(int)):
            if 0 <= qx < n and 0 <= qy < n:
                img[max(0, qy - 1):qy + 1, max(0, qx - 1):qx + 1] = [0.25, 0.2, 0.14, 1]
    for _ in range(count):
        r = spread * np.sqrt(rng.random())
        a = rng.uniform(0, 2 * np.pi)
        cx, cy = 0.5 + r * np.cos(a), 0.5 + r * np.sin(a)
        L, W = rng.uniform(0.035, 0.06), rng.uniform(0.014, 0.024)
        th = rng.uniform(0, np.pi)
        i0, i1 = int((cx - L) * n), int((cx + L) * n) + 1
        j0, j1 = int((cy - L) * n), int((cy + L) * n) + 1
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1, n), min(j1, n)
        if i1 <= i0 or j1 <= j0:
            continue
        xx, yy = x[j0:j1, i0:i1] - cx, y[j0:j1, i0:i1] - cy
        u = xx * np.cos(th) + yy * np.sin(th)
        v = -xx * np.sin(th) + yy * np.cos(th)
        m = (u / L) ** 2 + (v / W) ** 2 < 1
        shade = rng.uniform(0.65, 1.25) * (0.9 + 0.2 * (u / L))
        tint = bc[None, None, :] * shade[..., None] * np.array([rng.uniform(0.85, 1.1), 1, rng.uniform(0.8, 1.05)])
        vein = np.abs(v) < W * 0.12
        rgbm = np.where(vein[..., None], tint * 0.75, tint)
        reg = img[j0:j1, i0:i1]
        reg[m, :3] = rgbm[m]
        reg[m, 3] = 1.0
    return img


def grass(n, rng):
    nz = fbm(n, rng, octaves=(4, 16, 64, 128), weights=[0.3, 0.3, 0.25, 0.15])
    blades = rng.random((n, n))
    return col('#5E7F3A')[None, None, :] * (0.7 + 0.35 * nz + 0.12 * blades)[..., None]


HI_RES = {'plaster', 'plaster_int', 'roof', 'cobbles', 'parquet', 'stone', 'rustica', 'brick', 'gravel_white', 'grass', 'gravel_red', 'marble'}


def oak(n, rng):
    """Quarter-sawn oak: long grain lines along U with medullary flecks, 4 boards per tile."""
    y, xg = np.mgrid[0:n, 0:n] / n
    board = np.floor(y * 4).astype(int)
    wob = fbm(n, rng, octaves=(2, 4, 8))
    lines = 0.5 + 0.5 * np.sin((y * 4 % 1) * 2 * np.pi * 14 + wob * 5 + board * 1.7)
    fleck = (fbm(n, rng, octaves=(64, 128)) > 0.72) * 0.12
    tone = ((board * 0.618) % 1.0)
    shade = (0.72 + 0.22 * tone[..., None]) * (0.82 + 0.2 * lines[..., None]) + fleck[..., None]
    seam = (np.abs((y * 4) % 1 - 0.5) > 0.493)[..., None]
    rgb = col('#6E4A2C')[None, None] * shade
    return np.where(seam, rgb * 0.55, rgb)


def fresco(n, rng):
    """Baroque ceiling fresco: luminous sky with billowing clouds, warm vignette toward the frame."""
    y, xg = np.mgrid[0:n, 0:n] / n
    r = np.hypot(xg - 0.5, (y - 0.5) * 1.3)
    sky = col('#9DB4CE')[None, None] * (1 - r[..., None] * 0.6) + col('#F2D9A8')[None, None] * np.clip(0.55 - r, 0, 1)[..., None]
    c = fbm(n, rng, octaves=(3, 6, 12, 24))
    cloud = np.clip((c - 0.48) / 0.2, 0, 1) * np.clip(r * 1.6, 0, 1)
    shade = fbm(n, rng, octaves=(6, 12, 24))
    ccol = col('#F4EEE2')[None, None] * (0.8 + 0.3 * shade[..., None]) + col('#C89A80')[None, None] * 0.15 * (1 - shade[..., None])
    img = sky * (1 - cloud[..., None]) + ccol * cloud[..., None]
    for k in range(5):        # distant putti / figures suggested as soft warm blobs on the clouds
        fx, fy = rng.uniform(0.2, 0.8), rng.uniform(0.2, 0.8)
        blob = np.exp(-(((xg - fx) / 0.03) ** 2 + ((y - fy) / 0.045) ** 2))
        img = img * (1 - blob[..., None] * 0.6) + col('#D9A27E')[None, None] * blob[..., None] * 0.6
    vign = np.clip(1.15 - r * 0.7, 0, 1)
    return np.clip(img * vign[..., None], 0, 1)


def streaks(n, rng):
    """RGBA rain streaks below a cornice: vertical, dark at the top, fading downward."""
    y, xg = np.mgrid[0:n, 0:n] / n
    cols = fbm(n, rng, octaves=(16, 32, 64))[0:1, :] * np.ones((n, 1))
    cols = np.clip((cols - 0.45) * 3, 0, 1)
    fade = y ** 1.4                                   # row 0 = bottom after flip -> strong at top
    a = cols * fade * 0.28 + fade ** 3 * 0.12
    rgb = np.ones((n, n, 3)) * col('#6A645A')[None, None]
    return np.concatenate([rgb, np.clip(a, 0, 1)[..., None]], -1)


def grime(n, rng):
    """RGBA splash/rising-damp band: dark at the bottom, fading up with noisy edge."""
    y, xg = np.mgrid[0:n, 0:n] / n          # row 0 = bottom after flip
    y = 1 - y
    nz = fbm(n, rng, octaves=(4, 8, 32, 64))
    streak = fbm(n, rng, octaves=(32, 64)) ** 2
    a = np.clip(1.0 - y * 1.25 + (nz - 0.5) * 0.5, 0, 1) ** 1.6 * 0.42 + streak * 0.08 * (1 - y)
    rgb = np.ones((n, n, 3)) * col('#5B564C')[None, None] * (0.8 + 0.4 * nz[..., None])
    return np.concatenate([rgb, np.clip(a, 0, 1)[..., None]], -1)


def grass_tuft(n, rng):
    """RGBA card of grass blades (bottom = roots), for lawn tufts."""
    img = np.zeros((n, n, 4))
    for _ in range(110):
        x0 = rng.uniform(0.08, 0.92)
        h = rng.uniform(0.45, 0.98)
        lean = rng.uniform(-0.18, 0.18)
        w0 = rng.uniform(0.008, 0.016)
        c = col('#5E8A36') * rng.uniform(0.7, 1.25)
        for k in range(int(h * n)):
            t = k / n / h
            xc = x0 + lean * t * t
            ww = w0 * (1 - t) + 0.001
            i0, i1 = int((xc - ww) * n), int((xc + ww) * n) + 1
            row = n - 1 - k
            if 0 <= row < n:
                img[row, max(0, i0):min(n, i1), :3] = c * (0.55 + 0.6 * t)
                img[row, max(0, i0):min(n, i1), 3] = 1
    return img


def build_all(outdir, n=512):
    os.makedirs(outdir, exist_ok=True)
    rng = np.random.default_rng(7)
    n_lo = n
    n_hi = n * 2
    gens = {
        'plaster': lambda: plaster(n, rng),
        'plaster_int': lambda: plaster(n, rng, base='#E0D8C8', var=0.03),
        'roof': lambda: roof_tiles(n, rng),
        'stone': lambda: stone_blocks(n, rng),
        'rustica': lambda: stone_blocks(n, rng, base='#E2DCCF', rows=4, cols=2, mortar='#B8B0A0'),
        'cobbles': lambda: cobbles(n, rng),
        'rubble': lambda: rubble(n, rng),
        'parquet': lambda: parquet(n, rng),
        'marble': lambda: marble(n, rng),
        'gravel': lambda: gravel(n, rng),
        'hedge': lambda: hedge(n, rng),
        'bark': lambda: bark(n, rng),
        'foliage': lambda: foliage(n, rng),
        'grass': lambda: grass(n, rng),
        'grass_tuft': lambda: grass_tuft(256, rng),
        'grime': lambda: grime(256, rng),
        'streaks': lambda: streaks(256, rng),
        'fresco': lambda: fresco(1024, rng),
        'oak': lambda: oak(512, rng),
        'brick': lambda: brick(n, rng),
        'leaves': lambda: leaves(512, rng),
        'leaves_dark': lambda: leaves(512, rng, base='#3B5F2A'),
        'leaves_light': lambda: leaves(512, rng, base='#6E9440'),
        'leaves_dense': lambda: leaves(512, rng, base='#557F36', count=900, spread=0.5),
        'gravel_red': lambda: gravel_red(n, rng),
        'gravel_white': lambda: gravel_white(n, rng),
        'flag_sk': lambda: flag_sk(),
        'paint_land': lambda: painting2(512, rng, 'landscape'),
        'paint_port': lambda: painting2(512, rng, 'portrait'),
        'paint_land2': lambda: painting2(512, rng, 'landscape'),
        'paint_port2': lambda: painting2(512, rng, 'portrait'),
        'paint_still': lambda: painting2(512, rng, 'still'),
        'paint_harbour': lambda: painting2(512, rng, 'harbour'),
    }
    nh = n_hi
    gens_hi = {
        'plaster': lambda: plaster(nh, rng), 'plaster_int': lambda: plaster(nh, rng, base='#E0D8C8', var=0.03),
        'roof': lambda: roof_tiles(nh, rng), 'cobbles': lambda: cobbles(nh, rng), 'parquet': lambda: parquet(nh, rng),
        'stone': lambda: stone_blocks(nh, rng), 'rustica': lambda: stone_blocks(nh, rng, base='#E2DCCF', rows=4, cols=2, mortar='#B8B0A0'),
        'brick': lambda: brick(nh, rng), 'gravel_white': lambda: gravel_white(nh, rng), 'grass': lambda: grass(nh, rng),
        'gravel_red': lambda: gravel_red(nh, rng), 'marble': lambda: marble(nh, rng),
    }
    strength = {'roof': 3, 'rubble': 8, 'cobbles': 9, 'marble': 2, 'stone': 5, 'rustica': 5, 'parquet': 1,
                'plaster': 3, 'plaster_int': 1.5, 'bark': 6, 'hedge': 4, 'grass': 3, 'oak': 1.5, 'brick': 6, 'gravel_red': 4, 'gravel_white': 3, 'gravel': 4}
    out = {}
    for name, g in gens.items():
        p = os.path.join(outdir, name + '.png')
        rgb = g() if name not in HI_RES else gens_hi[name]()
        out[name] = _save(p, rgb)
        if name in strength:
            hsrc = HEIGHTS.get(name)
            src = np.repeat(hsrc[..., None], 3, -1) if hsrc is not None else rgb
            out[name + '_n'] = _save(os.path.join(outdir, name + '_n.png'), normal_from(src, strength[name]), 'Non-Color')
    return out
