"""Camera list shared by Google Earth reference capture and matching Godot/Blender renders.
Each view: name -> (camera xyz local metres, look-at xyz). Prints Google Earth Web URLs."""
import json, math, os, sys
LAT0, LON0, R, Z0 = 48.142319, 17.1001165, 6371000.0, 204.53   # Z0 = courtyard elevation (m a.s.l.)
VIEWS = {
    'ge_aerial_s':   ((0, -260, 120), (0, 0, 15)),
    'ge_aerial_sw':  ((-190, -170, 110), (0, 0, 15)),
    'ge_aerial_w':   ((-260, 10, 110), (0, 0, 15)),
    'ge_aerial_nw':  ((-190, 190, 110), (10, 20, 10)),
    'ge_aerial_n':   ((20, 280, 120), (20, 40, 5)),
    'ge_aerial_ne':  ((190, 200, 110), (10, 10, 10)),
    'ge_aerial_e':   ((260, -10, 100), (0, 0, 10)),
    'ge_aerial_se':  ((190, -190, 90), (0, -10, 10)),
    'ge_top':        ((5, -5, 420), (5, 0, 0)),
    'ge_garden_top': ((40, 95, 260), (40, 96, 0)),
    'ge_garden_n':   ((45, 210, 60), (35, 60, 0)),
    'ge_honour':     ((-10, -150, 45), (-5, -40, 12)),
    'ge_court_top':  ((2, -2, 140), (2, 0, 0)),
    'ge_crown':      ((-110, -110, 50), (-43, -30, 30)),
    'ge_west_gates': ((-170, -60, 60), (-100, -20, 0)),
    'ge_south_bast': ((40, -200, 40), (10, -90, -10)),
    'ge_podhradie':  ((150, -260, 120), (60, -150, -40)),
    'ge_riding':     ((-90, 120, 50), (-40, 60, 5)),
}
# streets / centre / embankment, given as (lat, lon, height above courtyard) of the look-at point + offset of the camera
def _ll(lat, lon):
    return (math.radians(lon - LON0) * R * math.cos(math.radians(LAT0)), math.radians(lat - LAT0) * R)
for name, lat, lon, zt, off in (
        ('ge_zamocka',     48.14290, 17.10340, -25, (-90, -60, 70)),     # Zámocká / Beblavého below the castle E side
        ('ge_mikulasska',  48.14130, 17.10380, -40, (-80, 80, 70)),      # Mikulášska, Židovská, SNP bridgehead
        ('ge_dom',         48.14200, 17.10480, -45, (-120, 40, 90)),     # St Martin's cathedral + Staromestská
        ('ge_nabrezie_w',  48.13960, 17.10320, -60, (-60, 140, 80)),     # embankment below the castle, Žižkova
        ('ge_nabrezie_e',  48.14010, 17.11000, -60, (-120, 120, 90)),    # Rázusovo nábrežie, Danube promenade
        ('ge_hlavne_nam',  48.14350, 17.10790, -45, (-110, -90, 100)),   # Main square, Old Town Hall
        ('ge_michalska',   48.14520, 17.10630, -40, (-100, 60, 90)),     # Michael's gate, Michalská street
        ('ge_snp_bridge',  48.13790, 17.10470, -60, (-260, -180, 160)),  # SNP bridge + UFO from SW
        ('ge_castle_road', 48.14370, 17.09860, -10, (-120, -80, 70)),    # Palisády / Vienna gate approach W
        ('ge_stairs_s',    48.14080, 17.10130, -25, (40, -110, 50)),     # S slope, stairs from Podhradie
):
    tx, ty = _ll(lat, lon)
    VIEWS[name] = ((tx + off[0], ty + off[1], zt + off[2]), (tx, ty, zt))
# low street-level obliques (~25 m above the street) along the pedestrian walk routes
for name, lat, lon, zt, off in (
        ('gs_zamocke_schody', 48.14255, 17.10360, -45, (-30, 25, 28)),
        ('gs_beblaveho',      48.14205, 17.10330, -40, (40, 30, 28)),
        ('gs_dom_square',     48.14190, 17.10530, -58, (45, -25, 28)),
        ('gs_panska',         48.14270, 17.10660, -62, (-40, -30, 28)),
        ('gs_hlavne_nam',     48.14370, 17.10880, -64, (-45, -35, 28)),
        ('gs_michalska',      48.14480, 17.10690, -60, (25, -45, 28)),
        ('gs_hviezdoslav',    48.14155, 17.10850, -63, (-55, 10, 28)),
        ('gs_razusovo',       48.13990, 17.10750, -66, (-50, 30, 28)),
        ('gs_zizkova',        48.13985, 17.10300, -64, (-40, 40, 28)),
        ('gs_vienna_gate',    48.14215, 17.09850, -6, (-35, -30, 26)),
        # V4: Podhradie (S/E foot of the castle hill) — houses and the slope roads
        ('ph_zizkova_w',      48.14045, 17.09990, -55, (-35, -25, 26)),
        ('ph_zizkova_e',      48.14010, 17.10220, -60, (40, -30, 26)),
        ('ph_slope_s',        48.14090, 17.10080, -40, (0, -60, 35)),
        ('ph_beblaveho_low',  48.14200, 17.10290, -40, (35, -25, 24)),
        ('ph_mudronova',      48.14260, 17.09720, -15, (-40, 20, 26)),
        ('ph_vydrica',        48.14000, 17.10450, -62, (30, -35, 26)),
        ('ph_zamocka_mid',    48.14320, 17.10150, -30, (-30, 30, 26)),
        ('ph_kapitulska',     48.14240, 17.10560, -55, (30, 25, 24)),
        ('ph_snp_foot',       48.14080, 17.10380, -58, (35, -35, 26)),
        ('ph_luginsland',     48.14105, 17.10230, -30, (25, -45, 30)),
):
    tx, ty = _ll(lat, lon)
    VIEWS[name] = ((tx + off[0], ty + off[1], zt + off[2]), (tx, ty, zt))


def url(cam, tgt):
    dx, dy, dz = tgt[0] - cam[0], tgt[1] - cam[1], tgt[2] - cam[2]
    heading = math.degrees(math.atan2(dx, dy)) % 360
    tilt = math.degrees(math.atan2(math.hypot(dx, dy), -dz))      # 0 = straight down, 90 = horizon
    lat = LAT0 + math.degrees(cam[1] / R)
    lon = LON0 + math.degrees(cam[0] / (R * math.cos(math.radians(LAT0))))
    return f"https://earth.google.com/web/@{lat:.6f},{lon:.6f},{Z0 + cam[2]:.1f}a,0d,45y,{heading:.1f}h,{tilt:.1f}t,0r"


# Camera altitude Earth Web actually used (status bar "Camera: N m" of each capture in data/ref/earth). Where a
# requested low camera would sit inside Earth's 3D mesh, Earth lifts it ~40 m and keeps lat/lon, heading and tilt,
# so the Godot camera must be lifted the same way or the pair shows rooftops instead of the street.
EARTH_CAM_ALT = {'gs_michalska': 202, 'gs_panska': 210, 'gs_razusovo': 206, 'gs_zamocke_schody': 228,
                 'ph_beblaveho_low': 229, 'ph_kapitulska': 213, 'ph_vydrica': 208, 'ph_zamocka_mid': 240,
                 'ph_zizkova_w': 215}


def as_captured(name, cam, tgt):
    """Camera/target of the capture as Earth rendered it (the URL keeps the requested camera)."""
    if name not in EARTH_CAM_ALT:
        return cam, tgt
    dz = EARTH_CAM_ALT[name] - Z0 - cam[2]
    return (cam[0], cam[1], cam[2] + dz), (tgt[0], tgt[1], tgt[2] + dz)


if __name__ == '__main__':
    out = {}
    for k, v in VIEWS.items():
        cam, tgt = as_captured(k, *v)
        out[k] = dict(cam=cam, tgt=tgt, url=url(*v))
    json.dump(out, open(os.path.join(os.path.dirname(__file__), '..', 'data', 'ref', 'earth', 'views.json'), 'w'), indent=1)
    for k, v in out.items():
        print(k, v['url'])
