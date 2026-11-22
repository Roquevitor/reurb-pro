"""Fundo de mapa real (satélite/ruas) reprojetado para o UTM da planta."""
import math, io, urllib.request
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from pyproj import Transformer
import geo

FONTES = {
    'satelite': ('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 'Imagem de satélite: Esri World Imagery'),
    'ruas': ('https://tile.openstreetmap.org/{z}/{x}/{y}.png', 'Mapa: © colaboradores do OpenStreetMap'),
}
_cache = {}

def _tile(url):
    if url in _cache: return _cache[url]
    try:
        rq = urllib.request.Request(url, headers={'User-Agent': 'ReurbPro/1.0 (planta REURB)'})
        im = Image.open(io.BytesIO(urllib.request.urlopen(rq, timeout=12).read())).convert('RGB')
    except Exception:
        im = None
    _cache[url] = im
    return im

def _merc(lon, lat, z):
    n = 2**z
    x = (lon+180)/360*n
    y = (1-np.log(np.tan(np.radians(lat))+1/np.cos(np.radians(lat)))/math.pi)/2*n
    return x, y

def fundo(zona, e0, e1, n0, n1, base='satelite', W=1600, H=1100, fetch=None):
    fetch = fetch or _tile
    url = FONTES[base][0]
    EE, NN = np.meshgrid(np.linspace(e0, e1, W), np.linspace(n1, n0, H))
    lon, lat = Transformer.from_crs(geo.EPSG[zona], 4326, always_xy=True).transform(EE, NN)
    res = (e1-e0)/W
    z = int(min(18 if base == 'satelite' else 19, max(3, math.ceil(math.log2(156543.03*math.cos(math.radians(lat.mean()))/res)))))
    while True:
        x, y = _merc(lon, lat, z)
        tx0, tx1, ty0, ty1 = int(x.min()), int(x.max()), int(y.min()), int(y.max())
        if (tx1-tx0+1)*(ty1-ty0+1) <= 48 or z <= 3: break
        z -= 1
    mos = np.full(((ty1-ty0+1)*256, (tx1-tx0+1)*256, 3), 215, np.uint8)
    jobs = [(tx, ty) for tx in range(tx0, tx1+1) for ty in range(ty0, ty1+1)]
    with ThreadPoolExecutor(8) as ex:
        res_t = list(ex.map(lambda j: fetch(url.format(z=z, x=j[0], y=j[1])), jobs))
    ok = 0
    for (tx, ty), im in zip(jobs, res_t):
        if im is not None:
            ok += 1
            mos[(ty-ty0)*256:(ty-ty0+1)*256, (tx-tx0)*256:(tx-tx0+1)*256] = np.asarray(im.resize((256, 256)))
    if ok == 0: return None
    px = np.clip(((x-tx0)*256).astype(int), 0, mos.shape[1]-1)
    py = np.clip(((y-ty0)*256).astype(int), 0, mos.shape[0]-1)
    return Image.fromarray(mos[py, px])
