"""Pedestrian walk-test routes from the castle into the Old Town, routed on the OSM way network
(castle-area footways/steps from castle_local.json + town streets from data/v2/city/misc.json/street.json).
Writes out/<tag>/city_routes.json: {route: [[x, y, z_ground], ...]} with a point every ~5 m."""
import heapq
import json
import math
import os

WALKABLE = {'footway', 'steps', 'path', 'pedestrian', 'living_street', 'residential', 'service', 'tertiary',
            'secondary', 'primary', 'unclassified', 'cycleway', 'corridor', 'track'}
# route: list of (lat, lon) stops; the router finds the network path between consecutive stops
ROUTES = {
    # the castle -> town descents are tested by v2_fortress (data/ref/fortress/descents_waypoints.json); start at the cathedral
    'town_main': [(48.14185, 17.10475), (48.14290, 17.10690), (48.14365, 17.10875),
                  (48.14455, 17.10735), (48.14523, 17.10655)],
    'town_river': [(48.14185, 17.10475), (48.14115, 17.10650), (48.13990, 17.10900)],
    # from the foot of the castle stairs (end of the Zámocké schody descent) down to the Danube promenade
    'castle_to_danube': [(48.141707, 17.104030), (48.13960, 17.10330), (48.13900, 17.10600)],
}


def build(H, T, out_dir):
    to_local, DATA = H['to_local'], H['DATA']
    nodes, adj = {}, {}

    def key(x, y):
        return (round(x / 1.5), round(y / 1.5))      # 1.5 m snapping joins the two data sources

    # building footprints: ways that cut through a building without being a mapped passage are heavily penalised
    # (OSM footways slightly misaligned with footprints would walk the tester through walls)
    bgrid = {}
    bfp = os.path.join(DATA, 'v2', 'city', 'buildings.json')
    if os.path.exists(bfp):
        for e in json.load(open(bfp))['elements']:
            if e.get('type') != 'way' or not e.get('geometry') or 'building' not in e.get('tags', {}):
                continue
            ring = [to_local(g['lat'], g['lon']) for g in e['geometry']]
            xs_, ys_ = [q[0] for q in ring], [q[1] for q in ring]
            bb = (min(xs_), max(xs_), min(ys_), max(ys_))
            for gx in range(int(bb[0] // 20), int(bb[1] // 20) + 1):
                for gy in range(int(bb[2] // 20), int(bb[3] // 20) + 1):
                    bgrid.setdefault((gx, gy), []).append((ring, bb))

    def inside_building(x, y):
        for ring, bb in bgrid.get((int(x // 20), int(y // 20)), ()):
            if bb[0] < x < bb[1] and bb[2] < y < bb[3]:
                c, n = False, len(ring)
                for i in range(n):
                    (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % n]
                    if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
                        c = not c
                if c:
                    return True
        return False
    passage = [False]

    def add_line(pts, cost_mul=1.0):
        prev = None
        for x, y in pts:
            k = key(x, y)
            nodes.setdefault(k, (x, y))
            if prev is not None and prev != k:
                d = math.dist(nodes[prev], nodes[k]) * cost_mul
                mx, my = (nodes[prev][0] + nodes[k][0]) / 2, (nodes[prev][1] + nodes[k][1]) / 2
                if not passage[0] and inside_building(mx, my):
                    d *= 50.0
                adj.setdefault(prev, []).append((k, d))
                adj.setdefault(k, []).append((prev, d))
            prev = k
    feats = json.load(open(os.path.join(DATA, 'castle_local.json')))['features']
    for f in feats:
        t = f['tags']
        if f['kind'] == 'road' and t.get('highway') in WALKABLE and t.get('tunnel') != 'yes':
            add_line([tuple(p[:2]) for p in f['pts']], 1.0 if t.get('highway') in ('footway', 'steps', 'pedestrian', 'path') else 1.3)
    for fn in ('misc.json', 'street.json'):
        fp = os.path.join(DATA, 'v2', 'city', fn)
        if not os.path.exists(fp):
            continue
        for e in json.load(open(fp))['elements']:
            t = e.get('tags', {})
            if e.get('type') != 'way' or t.get('highway') not in WALKABLE or not e.get('geometry'):
                continue
            if t.get('tunnel') == 'yes' or t.get('layer', '0').lstrip('-').isdigit() and int(t.get('layer', '0')) < 0:
                continue
            # pedestrians use sidewalks/footways, not the trunk carriageways between retaining walls
            if t.get('highway') in ('primary', 'secondary', 'trunk', 'motorway') and t.get('sidewalk', 'no') in ('no', 'none', 'separate'):
                continue
            pts = [to_local(g['lat'], g['lon']) for g in e['geometry']]
            passage[0] = t.get('tunnel') == 'building_passage' or t.get('covered') == 'yes'
            add_line(pts, 1.0 if t.get('highway') in ('footway', 'steps', 'pedestrian', 'path', 'living_street') else 1.3)
    # densify links between close-but-unjoined nodes (castle-local vs town data, sidewalks vs roads)
    grid = {}
    for k, (x, y) in nodes.items():
        grid.setdefault((int(x // 6), int(y // 6)), []).append(k)
    for (gx, gy), ks in grid.items():
        near = [k2 for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k2 in grid.get((gx + dx, gy + dy), [])]
        for k in ks:
            for k2 in near:
                if k2 != k and math.dist(nodes[k], nodes[k2]) < 6.0:
                    d = math.dist(nodes[k], nodes[k2]) * 2.0
                    adj.setdefault(k, []).append((k2, d))
    # snap stops only onto the main connected network (isolated sidewalk snippets would strand the route)
    comp, cid = {}, 0
    for k0 in nodes:
        if k0 in comp:
            continue
        stack = [k0]
        comp[k0] = cid
        while stack:
            u = stack.pop()
            for v, _ in adj.get(u, ()):
                if v not in comp:
                    comp[v] = cid
                    stack.append(v)
        cid += 1
    sizes = {}
    for c in comp.values():
        sizes[c] = sizes.get(c, 0) + 1
    main_c = max(sizes, key=sizes.get)
    allk = [k for k in nodes if comp[k] == main_c]

    def nearest(x, y):
        return min(allk, key=lambda k: (nodes[k][0] - x) ** 2 + (nodes[k][1] - y) ** 2)

    def dijkstra(a, b):
        dist, prev, pq = {a: 0.0}, {}, [(0.0, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == b:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, w in adj.get(u, ()):
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(pq, (nd, v))
        if b not in dist:
            return None
        path = [b]
        while path[-1] != a:
            path.append(prev[path[-1]])
        return [nodes[k] for k in reversed(path)]
    out = {}
    for name, stops in ROUTES.items():
        pts = []
        for (la0, lo0), (la1, lo1) in zip(stops, stops[1:]):
            seg = dijkstra(nearest(*to_local(la0, lo0)), nearest(*to_local(la1, lo1)))
            if seg is None:
                print('walk route', name, 'no path between', (la0, lo0), (la1, lo1))
                pts = None
                break
            pts += seg if not pts else seg[1:]
        if not pts:
            continue
        dense = [pts[0]]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.dist((x0, y0), (x1, y1))
            n = max(1, int(L / 5.0))
            for i in range(1, n + 1):
                dense.append((x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n))
        out[name] = [[round(x, 2), round(y, 2), round(T.h(x, y), 2)] for x, y in dense]
        print('walk route', name, len(dense), 'pts, length', round(sum(math.dist(a, b) for a, b in zip(dense, dense[1:]))), 'm')
    json.dump(out, open(os.path.join(out_dir, 'city_routes.json'), 'w'))
    return out
