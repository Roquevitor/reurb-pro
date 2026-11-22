"""Importação de localidades e ruas de um município.

- IBGE (API de Localidades): município, distritos e subdistritos. A API do IBGE NÃO traz nomes de ruas.
- Ruas: OpenStreetMap (Overpass API), localizadas pelo código IBGE do município (tag IBGE:GEOCODIGO).
  A cobertura depende do mapeamento colaborativo da cidade: sempre confira com a Prefeitura.
- Lista colada/CSV: para ruas informadas pela Prefeitura (ou extraídas do CNEFE/IBGE)."""
import json, re, unicodedata, urllib.request, urllib.parse

IBGE = 'https://servicodados.ibge.gov.br/api/v1/localidades'
OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
TIPOS = ['Rua', 'Avenida', 'Travessa', 'Praça', 'Alameda', 'Estrada', 'Rodovia', 'Viela', 'Beco', 'Ladeira', 'Largo', 'Via', 'Caminho', 'Vila', 'Loteamento']
UA = {'User-Agent': 'ReurbPro/1.0 (regularizacao fundiaria)'}


def _get(url, data=None, timeout=60):
    rq = urllib.request.Request(url, data=data, headers=UA)
    return urllib.request.urlopen(rq, timeout=timeout).read().decode('utf-8', 'ignore')


def norm(s):
    s = unicodedata.normalize('NFD', s or '')
    return re.sub(r'\s+', ' ', ''.join(c for c in s if unicodedata.category(c) != 'Mn')).strip().lower()


def codigo_municipio(nome, uf='BA', fetch=_get):
    """Código IBGE (7 dígitos) a partir do nome e da UF."""
    for m in json.loads(fetch(f'{IBGE}/estados/{uf}/municipios')):
        if norm(m['nome']) == norm(nome): return str(m['id'])
    return None


def divisoes(cod, fetch=_get):
    """Distritos e subdistritos (povoados/bairros que o IBGE reconhece) -> [(nome, id, tipo)]."""
    out = []
    for rec, tipo in (('distritos', 'Distrito'), ('subdistritos', 'Subdistrito')):
        try:
            for x in json.loads(fetch(f'{IBGE}/municipios/{cod}/{rec}')):
                out.append((x['nome'], str(x['id']), tipo))
        except Exception:
            pass
    return out


def ruas_osm(cod, fetch=_get):
    q = ('[out:json][timeout:90];'
         '(rel["boundary"="administrative"]["IBGE:GEOCODIGO"="%s"];rel["boundary"="administrative"]["ref:IBGE"="%s"];)->.r;'
         '.r map_to_area->.a;'
         'way(area.a)["name"]["highway"~"^(trunk|primary|secondary|tertiary|unclassified|residential|living_street|pedestrian|road)$"];'
         'out tags;') % (cod, cod)
    ultimo = None
    for ep in OVERPASS:
        try:
            dados = json.loads(fetch(ep, urllib.parse.urlencode({'data': q}).encode(), timeout=100))
            nomes = {}
            for el in dados.get('elements', []):
                n = (el.get('tags') or {}).get('name', '').strip()
                if n: nomes.setdefault(norm(n), n)
            return sorted(nomes.values(), key=norm)
        except Exception as e:
            ultimo = e
    raise RuntimeError(f'Serviço de mapas indisponível ({ultimo}).')


def separa_tipo(nome):
    """'Rua das Flores' -> ('Rua', 'das Flores'); sem tipo conhecido -> ('', nome)."""
    p = (nome or '').strip().split(' ', 1)
    for t in TIPOS:
        if norm(p[0]) == norm(t) and len(p) > 1: return t, p[1].strip()
    return '', (nome or '').strip()


def nome_completo(tipo, nome):
    tipo, nome = (tipo or '').strip(), (nome or '').strip()
    if tipo and norm(nome).startswith(norm(tipo) + ' '): return nome
    return f'{tipo} {nome}'.strip()


def parse_lista(texto):
    """Linhas 'Rua X', 'Rua X;Bairro', 'Rua X;Bairro;CEP' (separador ; ou tab) -> [(nome, bairro, cep)]."""
    out = []
    for l in (texto or '').splitlines():
        l = l.strip()
        if not l or l.startswith('#'): continue
        p = [x.strip() for x in re.split(r'[;\t]', l)] + ['', '']
        out.append((p[0], p[1], p[2]))
    return out
