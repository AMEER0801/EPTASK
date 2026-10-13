import sys, json, time
sys.path.insert(0, '/home/z/my-project/mini-services/eptask-api')
import os
os.chdir('/home/z/my-project/mini-services/eptask-api')
from app.state import STATE
STATE.load()
import corridor as CO
osm = json.loads(open('assets/osm_cache/overpass_corridor.json').read())
places = STATE.reference['data']['places']
G, an = CO.build_corridor({'osm': osm, 'places': places}, prefer_osm=True)
STATE.swap_graph(G)
import app.routes as R
t0 = time.time()
g = R.graph()
dt = time.time() - t0
print(f"graph endpoint OK in {dt:.1f}s | source: {g['source']}")
print("edges served:", len(g['edges']), "| nodes served:", len(g['nodes']))
print("routes pts:", {k: len(v) for k, v in g['routes'].items()})
G2, _ = CO.build_corridor({'places': places}, prefer_osm=False)
STATE.swap_graph(G2)
g2 = R.graph()
print("schematic still OK:", g2['source'][:20], '| edges:', len(g2['edges']), '| routes:', {k: len(v) for k, v in g2['routes'].items()})
