import re, math
from pyproj import Transformer
EPSG = {22: 31982, 23: 31983, 24: 31984, 25: 31985}  # SIRGAS 2000 UTM Sul
MC = {22: -51, 23: -45, 24: -39, 25: -33}
BA_BBOX = (-18.4, -8.4, -46.7, -37.2)  # lat_min, lat_max, lon_min, lon_max

def _limpa_rtf(t):
    if not t.lstrip().startswith('{\\rtf'): return t
    t = re.sub(r"\\'[0-9a-fA-F]{2}", ' ', t)
    t = re.sub(r'\{\\\*[^{}]*\}', ' ', t)
    t = re.sub(r'\{\\(fonttbl|colortbl|expandedcolortbl)[^{}]*(\{[^{}]*\}[^{}]*)*\}', ' ', t)
    t = re.sub(r'\\[a-zA-Z]+-?\d* ?', '\n', t)
    return re.sub(r'[{}\\]', '\n', t)

def parse_utm(texto, prefixo='V'):
    """Lê o arquivo do RTK (.txt/.csv/.rtf). Aceita 'nome E N [cota]' por linha, ou números soltos
    (um por linha, N depois E ou E depois N), vírgula ou ponto decimal."""
    texto = _limpa_rtf(texto)
    out = []
    for linha in texto.splitlines():
        l = linha.strip()
        if not l or l.startswith(('#', '//')):
            continue
        # Aceita padrão brasileiro com milhar e decimal (8.479.764,5954161).
        l = re.sub(r'(?<=\d)\.(?=\d{3}(?:[.,]|\s|$))', '', l)
        l = re.sub(r'(?<=\d),(?=\d)', '.', l)
        vals = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', l)]
        e = n = None
        for v in vals:
            if e is None and 100000 <= v <= 900000:
                e = v
            elif n is None and 5_000_000 <= v <= 10_500_000:
                n = v
        if e is None or n is None:
            continue
        m = re.match(r'^\s*([A-Za-z]+[\w\-]*|\d+)\s*[;,\t ]', l)
        nome = m.group(1) if m and float(re.sub(r'[^\d.]', '', m.group(1)) or 0) not in (e, n) else f'{prefixo}{len(out)+1}'
        if nome.isdigit():
            nome = f'{prefixo}{nome}'
        out.append((nome, e, n))
    if len(out) >= 3:
        return out
    # fallback: números em linhas separadas (E e N alternados), sem nomes
    nums = [float(x.replace(',', '.')) for x in re.findall(r'\d{5,}(?:[.,]\d+)?', texto)]
    out, pend = [], None
    for v in nums:
        if 100000 <= v <= 900000: k, pend2 = 'e', v
        elif 5_000_000 <= v <= 10_500_000: k, pend2 = 'n', v
        else: continue
        if pend and pend[0] != k:
            e, n = (pend[1], v) if k == 'n' else (v, pend[1])
            out.append((f'{prefixo}{len(out)+1}', e, n)); pend = None
        else:
            pend = (k, pend2)
    return out

def to_latlon(zona, e, n):
    t = Transformer.from_crs(EPSG[zona], 4674, always_xy=True)
    lon, lat = t.transform(e, n)
    return lat, lon

def dms(x, lat=None):
    s = abs(x); d = int(s); m = int((s-d)*60); sec = (s-d-m/60)*3600
    suf = '' if lat is None else (('N' if x >= 0 else 'S') if lat else ('E' if x >= 0 else 'W'))
    return f"{d}°{m:02d}'{sec:05.2f}\"{suf}"

def azimute(p, q):
    return math.degrees(math.atan2(q[0]-p[0], q[1]-p[1])) % 360

def dist(p, q):
    return math.hypot(q[0]-p[0], q[1]-p[1])

def area(pts):
    s = 0
    for i in range(len(pts)):
        x1, y1 = pts[i]; x2, y2 = pts[(i+1) % len(pts)]
        s += x1*y2 - x2*y1
    return abs(s)/2

def perimetro(pts):
    return sum(dist(pts[i], pts[(i+1) % len(pts)]) for i in range(len(pts)))

def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

def autointersecta(pts):
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i+1) % n]
        for j in range(i+2, n):
            if i == 0 and j == n-1:
                continue
            c, d = pts[j], pts[(j+1) % n]
            if _cross(a, b, c)*_cross(a, b, d) < 0 and _cross(c, d, a)*_cross(c, d, b) < 0:
                return True
    return False

def validar(zona, verts):
    """Retorna lista de alertas de qualidade."""
    av = []
    if len(verts) < 3:
        return ['Mínimo de 3 vértices.']
    pts = [(v['e'], v['n']) for v in verts]
    if autointersecta(pts):
        av.append('ATENÇÃO: o polígono se autointersecta (ordem dos vértices errada).')
    for i in range(len(pts)):
        d = dist(pts[i], pts[(i+1) % len(pts)])
        if d < 0.05:
            av.append(f"Vértices {verts[i]['nome']} e {verts[(i+1)%len(pts)]['nome']} praticamente coincidentes ({d:.3f} m).")
    lat, lon = to_latlon(zona, *pts[0])
    if not (BA_BBOX[0] <= lat <= BA_BBOX[1] and BA_BBOX[2] <= lon <= BA_BBOX[3]):
        av.append(f'Coordenadas fora da Bahia (lat {lat:.4f}, lon {lon:.4f}) — confira o FUSO UTM.')
    return av

def resumo(zona, verts):
    pts = [(v['e'], v['n']) for v in verts]
    a = area(pts)
    return dict(area=a, ha=a/10000, perimetro=perimetro(pts), mc=MC[zona])


# ---------- ponto inicial e sentido do polígono ----------
# chave de ordenação: o vértice com MENOR valor é o escolhido
MODOS_INICIO = {
    'sudoeste': ('Sudoeste (canto inferior esquerdo)', lambda v: v[1]+v[2]),
    'noroeste': ('Noroeste (canto superior esquerdo)', lambda v: v[1]-v[2]),
    'nordeste': ('Nordeste (canto superior direito)', lambda v: -(v[1]+v[2])),
    'sudeste':  ('Sudeste (canto inferior direito)', lambda v: -(v[1]-v[2])),
    'norte':    ('Mais ao norte', lambda v: -v[2]),
    'sul':      ('Mais ao sul', lambda v: v[2]),
    'leste':    ('Mais a leste', lambda v: -v[1]),
    'oeste':    ('Mais a oeste', lambda v: v[1]),
}

def orientacao(verts):
    """'horario' ou 'antihorario' (vértices como (nome,E,N) ou dicts com e/n)."""
    pts = [(v['e'], v['n']) if isinstance(v, dict) else (v[1], v[2]) for v in verts]
    s = sum(pts[i][0]*pts[(i+1) % len(pts)][1]-pts[(i+1) % len(pts)][0]*pts[i][1] for i in range(len(pts)))
    return 'antihorario' if s > 0 else 'horario'

def reorganizar(verts, inicio='sudoeste', sentido='manter', prefixo='V', renumerar=True):
    """Gira a lista para começar onde o técnico escolher e, se pedido, inverte o sentido.
    Não altera coordenadas. inicio: 'primeiro' | modo de MODOS_INICIO | 'v:NOME' | 'i:INDICE'.
    sentido: 'manter' | 'horario' | 'antihorario' | 'inverter'.
    Retorna (novos [(nome,E,N)], mapa {nome_antigo: nome_novo}, inverteu)."""
    verts = [(v[0], v[1], v[2]) for v in verts]; n = len(verts)
    if n < 3: return verts, {v[0]: v[0] for v in verts}, False
    idx = 0
    if inicio in MODOS_INICIO:
        idx = min(range(n), key=lambda i: MODOS_INICIO[inicio][1](verts[i]))
    elif inicio.startswith('v:'):
        idx = next((i for i, v in enumerate(verts) if v[0] == inicio[2:]), 0)
    elif inicio.startswith('i:'):
        try: idx = int(inicio[2:]) % n
        except ValueError: idx = 0
    rot = verts[idx:] + verts[:idx]
    inv = sentido == 'inverter' or (sentido in ('horario', 'antihorario') and orientacao(verts) != sentido)
    if inv: rot = [rot[0]] + rot[:0:-1]
    novos = [((f'{prefixo}{i+1}' if renumerar else v[0]), v[1], v[2]) for i, v in enumerate(rot)]
    return novos, {rot[i][0]: novos[i][0] for i in range(n)}, inv

def reordenar_inicio(verts, modo='sudoeste', prefixo='V'):
    """Compatível com a v6: devolve só a lista reorganizada."""
    return reorganizar(verts, modo, 'manter', prefixo)[0] if modo != 'primeiro' else verts


def parse_kml(dados, prefixo='V'):
    """Lê .kml/.kmz (Google Earth). Usa o 1º polígono/linha; se não houver, os pontos marcados.
    Retorna (zona_utm, [(nome, E, N), ...])."""
    import zipfile, io as _io
    if dados[:2] == b'PK':
        z = zipfile.ZipFile(_io.BytesIO(dados)); nome = next((n for n in z.namelist() if n.lower().endswith('.kml')), None)
        if not nome: return None, []
        dados = z.read(nome)
    t = dados.decode('utf-8', 'ignore') if isinstance(dados, bytes) else dados
    def coords(bloco):
        out = []
        for tr in bloco.split():
            p = tr.split(',')
            try: out.append((float(p[0]), float(p[1])))
            except Exception: pass
        return out
    lls, nomes = [], []
    m = re.search(r'<(Polygon|LineString)\b.*?<coordinates>(.*?)</coordinates>', t, re.S)
    if m:
        lls = coords(m.group(2))
        if len(lls) > 2 and lls[0] == lls[-1]: lls = lls[:-1]
    else:
        for pm in re.findall(r'<Placemark\b.*?</Placemark>', t, re.S):
            c = re.search(r'<Point\b.*?<coordinates>(.*?)</coordinates>', pm, re.S)
            if c and coords(c.group(1)):
                lls.append(coords(c.group(1))[0]); n = re.search(r'<name>(.*?)</name>', pm, re.S); nomes.append(n.group(1).strip() if n else '')
    if not lls: return None, []
    lon_m = sum(p[0] for p in lls)/len(lls); zona = min(25, max(22, int((lon_m+180)//6)+1))
    tr = Transformer.from_crs('EPSG:4674', f'EPSG:{EPSG[zona]}', always_xy=True)
    out = []
    for i, (lo, la) in enumerate(lls):
        e, n = tr.transform(lo, la); nm = (nomes[i] if i < len(nomes) and nomes[i] else f'{prefixo}{i+1}')
        out.append((nm, round(e, 5), round(n, 5)))
    return zona, out
