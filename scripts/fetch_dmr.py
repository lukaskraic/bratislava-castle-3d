"""Sample ZBGIS DMR 5.0 elevations on a regular lat/lon grid via WMS GetFeatureInfo."""
import json, sys, urllib.request, concurrent.futures as cf, time
W, S, E, N = (17.0960, 48.1395, 17.1042, 48.1450) if len(sys.argv) < 4 else tuple(map(float, sys.argv[3].split(',')))
NX = NY = int(sys.argv[1]) if len(sys.argv) > 1 else 128
URL = ("https://zbgisws.skgeodesy.sk/zbgis_dmr_wms/service.svc/get?SERVICE=WMS&VERSION=1.1.1"
       "&REQUEST=GetFeatureInfo&LAYERS=1&QUERY_LAYERS=1&STYLES=&SRS=EPSG:4326"
       f"&BBOX={W},{S},{E},{N}&WIDTH={NX}&HEIGHT={NY}&X={{x}}&Y={{y}}&INFO_FORMAT=text/plain&FORMAT=image/png")

def get(xy):
    x, y = xy
    for attempt in range(5):
        try:
            req = urllib.request.Request(URL.format(x=x, y=y), headers={'User-Agent': 'bratislava-castle-model/1.0'})
            txt = urllib.request.urlopen(req, timeout=30).read().decode()
            return xy, float(txt.split(';')[1])
        except Exception:
            time.sleep(1 + attempt)
    return xy, None

grid = [[None] * NX for _ in range(NY)]
cells = [(x, y) for y in range(NY) for x in range(NX)]
done = 0
with cf.ThreadPoolExecutor(12) as ex:
    for (x, y), v in ex.map(get, cells):
        grid[y][x] = v
        done += 1
        if done % 2000 == 0: print(done, flush=True)
missing = sum(v is None for r in grid for v in r)
json.dump({'bbox': [W, S, E, N], 'nx': NX, 'ny': NY, 'row0': 'north', 'z': grid}, open(sys.argv[2], 'w'))
print('missing', missing)
