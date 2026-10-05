"""Extract castle-area OSM features into local metric coords (origin = palace centroid)."""
import json, math, sys
d = json.load(open(sys.argv[1]))
nodes = {e['id']: (e['lat'], e['lon']) for e in d['elements'] if e['type'] == 'node'}
ways = {}
for e in d['elements']:
    # "out skel" repeats ways without tags; keep the tagged copy
    if e['type'] == 'way' and (e['id'] not in ways or e.get('tags')):
        ways[e['id']] = e
rels = [e for e in d['elements'] if e['type'] == 'relation']

# palace centroid from building:part 244267968..81 bbox
LAT0, LON0 = 48.142319, 17.1001165
R = 6378137.0
def xy(lat, lon):
    x = math.radians(lon - LON0) * R * math.cos(math.radians(LAT0))
    y = math.radians(lat - LAT0) * R
    return round(x, 2), round(y, 2)

def way_pts(w):
    return [xy(*nodes[n]) for n in w['nodes'] if n in nodes]

out = []
for w in ways.values():
    t = w.get('tags', {})
    if not t: continue
    kind = None
    if 'building:part' in t: kind = 'part'
    elif 'building' in t: kind = 'building'
    elif t.get('barrier') in ('wall', 'retaining_wall', 'city_wall'): kind = 'wall'
    elif t.get('leisure') in ('garden', 'park'): kind = 'garden'
    elif t.get('historic') == 'castle': kind = 'castle_area'
    elif 'highway' in t: kind = 'road'
    elif t.get('landuse') or t.get('natural') or t.get('amenity') == 'parking' or t.get('area:highway'): kind = 'area'
    elif t.get('natural') == 'tree_row': kind = 'area'
    if not kind: continue
    pts = way_pts(w)
    if not pts: continue
    if max(abs(p[0]) for p in pts) > 450 or max(abs(p[1]) for p in pts) > 350: continue
    out.append({'id': w['id'], 'kind': kind, 'tags': t, 'pts': pts,
                'closed': w['nodes'][0] == w['nodes'][-1]})
for r in rels:
    t = r.get('tags', {})
    if 'building' not in t: continue
    for m in r['members']:
        if m['type'] == 'way' and m['ref'] in ways and m['role'] in ('outer', 'inner'):
            pts = way_pts(ways[m['ref']])
            if pts and max(abs(p[0]) for p in pts) < 450 and max(abs(p[1]) for p in pts) < 350:
                out.append({'id': m['ref'], 'kind': 'building' if m['role']=='outer' else 'hole', 'tags': t, 'pts': pts, 'closed': True, 'rel': r['id']})
import os
points = []
nf = os.path.join(os.path.dirname(sys.argv[1]), 'osm_nodes.json')
if os.path.exists(nf):
    for e in json.load(open(nf))['elements']:
        t = e.get('tags', {})
        kind = ('tree' if t.get('natural') == 'tree' else 'bench' if t.get('amenity') == 'bench'
                else 'lamp' if t.get('highway') == 'street_lamp' else 'flagpole' if t.get('man_made') == 'flagpole'
                else 'well' if t.get('man_made') == 'water_well' else 'statue' if t.get('historic') in ('memorial', 'monument')
                or t.get('tourism') == 'artwork' else 'fountain' if t.get('amenity') == 'fountain' else None)
        if kind:
            x, y = xy(e['lat'], e['lon'])
            if abs(x) < 330 and abs(y) < 330:
                points.append({'kind': kind, 'x': x, 'y': y, 'tags': t})
trees = [p for p in points if p['kind'] == 'tree']
json.dump({'origin': [LAT0, LON0], 'features': out, 'points': points}, open(sys.argv[2], 'w'))
from collections import Counter
print(Counter(f['kind'] for f in out), 'trees', len(trees))
