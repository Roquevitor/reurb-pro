import os
import io, math, re
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import geo

def _fmt(v, d=2):
    return f"{v:,.{d}f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def _dist_trecho(vs, i):
    manual = vs[i].get('distancia_manual')
    return float(manual) if manual not in (None, '') else geo.dist((vs[i]['e'],vs[i]['n']), (vs[(i+1)%len(vs)]['e'],vs[(i+1)%len(vs)]['n']))

def resumo(zona, vs):
    r=geo.resumo(zona,vs)
    r['perimetro']=sum(_dist_trecho(vs,i) for i in range(len(vs)))
    return r

def _cobertura(vs, pessoas):
    """Mapeia cada segmento k (vértice k -> k+1) ao confrontante que o cobre."""
    nomes = [v['nome'] for v in vs]; n = len(vs); seg = {}
    for p in pessoas:
        if p['tipo'] != 'confrontante' or p['v_ini'] not in nomes or p['v_fim'] not in nomes:
            continue
        a, b = nomes.index(p['v_ini']), nomes.index(p['v_fim'])
        k = a
        while k != b:
            seg[k] = p; k = (k+1) % n
    return seg

def _conf_txt(p):
    if not p: return ''
    natureza = p.get('tipo_confrontante') or ''
    if natureza == 'via' or (not natureza and re.match(r'(?i)^(rua|avenida|travessa|estrada|pra[çc]a|alameda|rodovia|beco|ladeira|via)\b', (p.get('nome') or '').strip())):
        nome = p.get('nome') or 'via pública não identificada'
        return (('a ' if re.match(r'(?i)^(rua|avenida|travessa|estrada|pra[çc]a|alameda|rodovia|beco|ladeira|via)\b', nome.strip()) else '') + nome)
    if natureza == 'matricula':
        return f"imóvel objeto da matrícula nº {p.get('matricula') or 'não informada'}, CNS nº {p.get('cns') or 'não informado'}"
    if not natureza and p.get('matricula') and not p.get('cpf') and not p.get('nome'):
        return f"imóvel objeto da matrícula nº {p['matricula']}, CNS nº {p.get('cns') or 'não informado'}"
    s = p.get('nome') or ''
    if not s and not p.get('matricula'): return ''
    if p.get('cpf'): s += f", CPF/CNPJ nº {p['cpf']}"
    if p.get('inscricao'): s += f", inscrição cadastral nº {p['inscricao']}"
    if p.get('matricula'): s += f", matrícula/transcrição nº {p['matricula']}"
    if p.get('cns'): s += f", CNS nº {p['cns']}"
    return s

def memorial_texto(proj, vs, pessoas):
    pts = [(v['e'], v['n']) for v in vs]; r = resumo(proj['zona'], vs); n = len(vs)
    seg = _cobertura(vs, pessoas)
    ocup = [p['nome'] for p in pessoas if p['tipo'] in ('ocupante', 'beneficiario')]
    lat, lon = geo.to_latlon(proj['zona'], *pts[0])
    paras = [
        f"IMÓVEL: Lote/Unidade {proj.get('lote') or 's/n'}, Quadra {proj.get('quadra') or 's/n'}, {proj.get('comunidade') or ''}, Município de {proj['municipio']}/BA.",
        f"OCUPANTE(S)/BENEFICIÁRIO(S): {', '.join(ocup) or 'não informado'}.",
        f"ÁREA: {_fmt(r['area'])} m² ({_fmt(r['ha'], 4)} ha). PERÍMETRO: {_fmt(r['perimetro'])} m.",
        f"SISTEMA GEODÉSICO: SIRGAS 2000; projeção UTM, fuso {proj['zona']}S, meridiano central {abs(r['mc'])}° W. Coordenadas obtidas por levantamento GNSS/RTK. Azimutes referidos ao norte da quadrícula UTM.",
    ]
    d = (f"DESCRIÇÃO: Inicia-se a descrição no vértice {vs[0]['nome']}, de coordenadas N {_fmt(vs[0]['n'], 5)} m e E {_fmt(vs[0]['e'], 5)} m "
         f"(lat. {geo.dms(lat, True)}, long. {geo.dms(lon, False)}); ")
    partes = []
    for k in range(n):
        q = (k+1) % n
        az = geo.azimute(pts[k], pts[q]); ds = _dist_trecho(vs, k)
        conf = _conf_txt(seg.get(k))
        trecho = f"deste, segue com azimute de {geo.dms(az)} e distância de {_fmt(ds)} m"
        if conf: trecho += f", confrontando, pelo lado {seg_lado(pts, k)}, com {conf}"
        trecho += f", até o vértice {vs[q]['nome']}, de coordenadas N {_fmt(vs[q]['n'], 5)} m e E {_fmt(vs[q]['e'], 5)} m"
        partes.append(trecho)
    d += '; '.join(partes) + f"; fechando assim o perímetro acima descrito."
    paras.append(d)
    return paras

def memorial_docx(proj, vs, pessoas):
    doc = Document()
    st = doc.styles['Normal']; st.font.name = 'Arial'; st.font.size = Pt(11)
    for s in doc.sections: s.left_margin = s.right_margin = Cm(2.5)
    h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.add_run('MEMORIAL DESCRITIVO').bold = True
    h2 = doc.add_paragraph(); h2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h2.add_run(f"Regularização Fundiária Urbana – REURB ({(proj.get('modalidade') or 'REURB-S')})").bold = True
    for t in memorial_texto(proj, vs, pessoas):
        p = doc.add_paragraph(t); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    t = doc.add_table(rows=1, cols=5); t.style = 'Table Grid'
    for c, x in zip(t.rows[0].cells, ['Vértice', 'E (m)', 'N (m)', 'Latitude', 'Longitude']): c.text = x
    for v in vs:
        la, lo = geo.to_latlon(proj['zona'], v['e'], v['n'])
        cells = t.add_row().cells
        for c, x in zip(cells, [v['nome'], _fmt(v['e'], 5), _fmt(v['n'], 5), geo.dms(la, True), geo.dms(lo, False)]): c.text = x
    doc.add_paragraph(); conf_docx(doc, vs, pessoas); doc.add_paragraph()
    _assinatura(doc, proj)
    b = io.BytesIO(); doc.save(b); return b.getvalue()

def _assinatura(doc, proj):
    p = doc.add_paragraph(f"{proj['municipio']}/BA, {proj.get('data','')}."); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph('\n______________________________________\n'
                          f"{proj.get('tecnico','')}\n{(proj.get('conselho') or 'CREA/CAU/CFT')}: {proj.get('registro','')}\nResponsável Técnico")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

def crf_docx(proj, vs, pessoas):
    r = resumo(proj['zona'], vs)
    doc = Document()
    st = doc.styles['Normal']; st.font.name = 'Arial'; st.font.size = Pt(11)
    for s in doc.sections: s.left_margin = s.right_margin = Cm(2.5)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f"MUNICÍPIO DE {proj['municipio'].upper()} – ESTADO DA BAHIA\n").bold = True
    p.add_run('CERTIDÃO DE REGULARIZAÇÃO FUNDIÁRIA – CRF (MINUTA)').bold = True
    doc.add_paragraph(f"Processo administrativo nº {proj.get('processo') or '____'} – Modalidade {(proj.get('modalidade') or 'REURB-S')}. "
                      "Núcleo urbano informal objeto de regularização fundiária urbana, nos termos da Lei Federal nº 13.465/2017 e do Decreto Federal nº 9.310/2018.").alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_paragraph(f"1. NÚCLEO URBANO: {proj.get('comunidade') or '____'}, Município de {proj['municipio']}/BA.").runs[0].bold = True
    doc.add_paragraph(f"Requerente/legitimado: {proj.get('requerente') or '____'}.")
    doc.add_paragraph('2. UNIDADE IMOBILIÁRIA').runs[0].bold = True
    doc.add_paragraph(f"Lote {proj.get('lote') or 's/n'}, Quadra {proj.get('quadra') or 's/n'}; área de {_fmt(r['area'])} m²; perímetro de {_fmt(r['perimetro'])} m; "
                      f"matrícula-mãe/origem: {proj.get('matricula_origem') or 'não possui registro (área de domínio a ser definido)'}.")
    for t in memorial_texto(proj, vs, pessoas)[4:]:
        doc.add_paragraph(t).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_paragraph('3. BENEFICIÁRIOS').runs[0].bold = True
    tb = doc.add_table(rows=1, cols=6); tb.style = 'Table Grid'
    for c, x in zip(tb.rows[0].cells, ['Nome', 'CPF', 'RG', 'Est. civil', 'Profissão', 'Título']): c.text = x
    for p_ in pessoas:
        if p_['tipo'] in ('ocupante', 'beneficiario'):
            cells = tb.add_row().cells
            for c, x in zip(cells, [p_['nome'], p_.get('cpf') or '', p_.get('rg') or '', p_.get('estado_civil') or '', p_.get('profissao') or '', 'Legitimação Fundiária']): c.text = x
    conf_docx(doc, vs, pessoas)
    doc.add_paragraph('\n4. Declara-se aprovada a regularização fundiária, constituindo a presente certidão título hábil para registro no Cartório de Registro de Imóveis competente, '
                      'com a abertura de matrícula e o registro da legitimação fundiária/fixação em favor dos beneficiários acima, '
                      'conforme projeto de regularização fundiária (planta, memorial descritivo e cadastro) em anexo.').alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_paragraph('\nMINUTA gerada para conferência técnica e jurídica. A emissão e assinatura da CRF são de competência do Município (art. 41 da Lei 13.465/2017). '
                      'Revise a modalidade, o título e as exigências do Cartório de Registro de Imóveis antes da apresentação.').runs[0].italic = True
    doc.add_paragraph(f"\n{proj['municipio']}/BA, {proj.get('data','')}.\n\n______________________________\nPrefeito(a) Municipal / Autoridade competente")
    b = io.BytesIO(); doc.save(b); return b.getvalue()

def kml(proj, vs):
    co = ' '.join(f"{geo.to_latlon(proj['zona'], v['e'], v['n'])[1]:.8f},{geo.to_latlon(proj['zona'], v['e'], v['n'])[0]:.8f},0" for v in vs+vs[:1])
    return f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><name>{proj["nome"]}</name><Polygon><outerBoundaryIs><LinearRing><coordinates>{co}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>'.encode()

# ---------- confrontantes: lado, numeração e quadros ----------
LADOS = ['Norte', 'Nordeste', 'Leste', 'Sudeste', 'Sul', 'Sudoeste', 'Oeste', 'Noroeste']

def _sa(pts):
    return sum(pts[i][0]*pts[(i+1) % len(pts)][1]-pts[(i+1) % len(pts)][0]*pts[i][1] for i in range(len(pts)))/2

def _normal(pts, k, sa=None):
    sa = _sa(pts) if sa is None else sa
    p, q = pts[k], pts[(k+1) % len(pts)]; dx, dy = q[0]-p[0], q[1]-p[1]
    return (dy, -dx) if sa > 0 else (-dy, dx)  # normal que aponta para fora do lote

def _lado(nx, ny):
    return LADOS[int(((math.degrees(math.atan2(nx, ny)) % 360)+22.5)//45) % 8]

def seg_lado(pts, k):
    return _lado(*_normal(pts, k))

def conf_info(vs, pessoas):
    pts = [(v['e'], v['n']) for v in vs]; sa = _sa(pts); seg = _cobertura(vs, pessoas); out = []
    for p in [q for q in pessoas if q['tipo'] == 'confrontante' and (q.get('nome') or q.get('matricula') or q.get('cpf') or q.get('inscricao'))]:
        ks = sorted(k for k, q in seg.items() if q is p); nx = ny = comp = 0
        for k in ks:
            ex, ey = _normal(pts, k, sa); nx += ex; ny += ey
            comp += _dist_trecho(vs, k)
        out.append(dict(num=len(out)+1, p=p, ks=ks, comp=comp, lado=_lado(nx, ny) if ks else '—'))
    return out

def _tabela_docx(doc, titulo, cab, linhas):
    doc.add_paragraph(titulo).runs[0].bold = True
    t = doc.add_table(rows=1, cols=len(cab)); t.style = 'Table Grid'
    for c, x in zip(t.rows[0].cells, cab): c.text = x
    for l in linhas:
        for c, x in zip(t.add_row().cells, l): c.text = str(x)

def conf_docx(doc, vs, pessoas):
    L = []
    for i in conf_info(vs, pessoas):
        p = i['p']; natureza = p.get('tipo_confrontante') or ('via' if re.match(r'(?i)^(rua|avenida|travessa|estrada|pra[çc]a|alameda|rodovia|beco|ladeira|via)\b', (p.get('nome') or '').strip()) else ('matricula' if p.get('matricula') and not p.get('nome') else 'pessoa'))
        ident = _conf_txt(p)
        L.append((f"C{i['num']}", natureza.capitalize(), ident, p.get('cns') or '', i['lado'],
                  f"{p.get('v_ini') or '?'} → {p.get('v_fim') or '?'}", _fmt(i['comp'])))
    _tabela_docx(doc, 'QUADRO DE CONFRONTANTES', ['Nº', 'Natureza', 'Identificação', 'CNS', 'Lado', 'Vértices', 'Extensão (m)'], L)

def _tabela_pdf(c, x, y, cols, rows, W, titulo=None, rowh=5*mm):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    def cab(y):
        c.setFont('Helvetica-Bold', 7); c.setFillColorRGB(.85, .9, .87); c.rect(x, y-1.2*mm, sum(w for _, w in cols)*mm, rowh, fill=1, stroke=0); c.setFillColorRGB(0, 0, 0)
        xx = x+1*mm
        for t, w in cols: c.drawString(xx, y, t); xx += w*mm
        return y-rowh
    if titulo:
        c.setFont('Helvetica-Bold', 9); c.drawString(x, y, titulo); y -= 6*mm
    y = cab(y); c.setFont('Helvetica', 7)
    for r in rows:
        if y < 18*mm:
            c.showPage(); c.rect(8*mm, 8*mm, W-16*mm, 194*mm); y = 198*mm; y = cab(y); c.setFont('Helvetica', 7)
        xx = x+1*mm
        for (t, w), v in zip(cols, r):
            v = str(v)
            while stringWidth(v, 'Helvetica', 7) > w*mm-2*mm and len(v) > 3: v = v[:-2]
            c.drawString(xx, y, v); xx += w*mm
        c.line(x, y-1.5*mm, x+sum(w for _, w in cols)*mm, y-1.5*mm); y -= rowh
    return y-4*mm

def planta_pdf(proj, vs, pessoas, base='satelite', drone=None):
    import mapa
    from reportlab.lib.pagesizes import A3
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
    pts = [(v['e'], v['n']) for v in vs]; r = resumo(proj['zona'], vs); n = len(vs)
    cinfo = conf_info(vs, pessoas); segnum = {k: i['num'] for i in cinfo for k in i['ks']}; sa = _sa(pts)
    W, H = landscape(A3); b = io.BytesIO(); c = canvas.Canvas(b, pagesize=(W, H)); c.setTitle('Planta REURB')
    c.rect(8*mm, 8*mm, W-16*mm, H-16*mm)
    dx0, dy0, dw, dh = 14*mm, 62*mm, 270*mm, 214*mm
    mnE, mxE = min(p[0] for p in pts), max(p[0] for p in pts); mnN, mxN = min(p[1] for p in pts), max(p[1] for p in pts)
    w, h = max(mxE-mnE, 1), max(mxN-mnN, 1)
    # Amplia o croqui: o maior lado do lote ocupa aproximadamente 82% do quadro,
    # preservando margem para rótulos e vértices. Escalas intermediárias evitam
    # saltos excessivos (por exemplo, de 1:250 diretamente para 1:500).
    ocupacao = .82
    esc_min = max(w*1000/(dw*ocupacao/mm), h*1000/(dh*ocupacao/mm))
    esc = next(s for s in [50, 75, 100, 125, 150, 175, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 900, 1000, 1250, 1500, 1750, 2000, 2500, 3000, 4000, 5000, 7500, 10000, 15000, 25000] if s >= esc_min)
    k = (1000/esc)*mm; Wm, Hm = dw/k, dh/k; cxm, cym = (mnE+mxE)/2, (mnN+mxN)/2
    e0, n0 = cxm-Wm/2, cym-Hm/2
    P = lambda p: (dx0+(p[0]-e0)*k, dy0+(p[1]-n0)*k)
    try: img = None if base == 'branco' else mapa.fundo(proj['zona'], e0, e0+Wm, n0, n0+Hm, base, 2000, int(2000*dh/dw))
    except Exception: img = None
    if img: c.drawImage(ImageReader(img), dx0, dy0, dw, dh)
    else:
        c.setFillColorRGB(1, 1, 1); c.rect(dx0, dy0, dw, dh, fill=1, stroke=0); c.setFillColorRGB(0, 0, 0)
        if base != 'branco':
            c.setFont('Helvetica-Oblique', 9); c.drawString(dx0+3*mm, dy0+dh-6*mm, 'Fundo cartográfico indisponível — planta apresentada em fundo branco.')
    c.rect(dx0, dy0, dw, dh)

    def tag(x, y, t, size=7.5, bold=False):
        f = 'Helvetica-Bold' if bold else 'Helvetica'; tw = stringWidth(t, f, size)
        c.saveState(); c.setFillColorRGB(1, 1, 1); c.setFillAlpha(.82); c.rect(x-tw/2-1*mm, y-1*mm, tw+2*mm, size*.35*mm+1.6*mm, fill=1, stroke=0); c.restoreState()
        c.setFont(f, size); c.drawCentredString(x, y, t)
    st = next(s for s in [5, 10, 20, 25, 50, 100, 200, 250, 500, 1000] if Wm/s <= 7)
    c.setFont('Helvetica', 6.5)
    e = math.ceil(e0/st)*st
    while e < e0+Wm: x = dx0+(e-e0)*k; c.line(x, dy0, x, dy0+2*mm); c.drawCentredString(x, dy0-3.2*mm, f"E {_fmt(e, 0)}"); e += st
    nn = math.ceil(n0/st)*st
    while nn < n0+Hm:
        y = dy0+(nn-n0)*k; c.line(dx0, y, dx0+2*mm, y); c.saveState(); c.translate(dx0-1*mm, y); c.rotate(90); c.drawCentredString(0, 0, f"N {_fmt(nn, 0)}"); c.restoreState(); nn += st
    c.saveState(); c.setFillColorRGB(1, .85, 0); c.setFillAlpha(.22); c.setStrokeColorRGB(1, .85, 0); c.setLineWidth(2.4)
    path = c.beginPath(); path.moveTo(*P(pts[0]))
    for p in pts[1:]: path.lineTo(*P(p))
    path.close(); c.drawPath(path, fill=1, stroke=1); c.restoreState()
    c.setStrokeColorRGB(.1, .1, .1); c.setLineWidth(.6); c.drawPath(path, fill=0, stroke=1)
    cx0, cy0 = P((sum(p[0] for p in pts)/n, sum(p[1] for p in pts)/n))
    paleta_conf = [(0.12,.36,.72),(.78,.25,.18),(.12,.53,.36),(.55,.30,.68),(.85,.48,.10),(.10,.55,.62),(.68,.28,.43),(.42,.48,.16),(.28,.35,.52),(.65,.38,.18)]
    for i, p in enumerate(pts):
        x, y = P(p); q = pts[(i+1) % n]; xq, yq = P(q)
        c.setFillColorRGB(.85, 0, 0); c.circle(x, y, 1.4*mm, fill=1); c.setFillColorRGB(0, 0, 0)
        vx, vy = x-cx0, y-cy0; m = math.hypot(vx, vy) or 1; tag(x+vx/m*5*mm, y+vy/m*5*mm-1.5, vs[i]['nome'], bold=True, size=8)
        xm, ym = (x+xq)/2, (y+yq)/2; ang = math.degrees(math.atan2(yq-y, xq-x)); ang = ang+180 if ang > 90 or ang < -90 else ang
        c.saveState(); c.translate(xm, ym); c.rotate(ang); tag(0, -1, f"{_fmt(_dist_trecho(vs, i))} m", size=7); c.restoreState()
        if i in segnum:
            ex, ey = _normal(pts, i, sa); m2 = math.hypot(ex, ey) or 1; bx, by = xm+ex/m2*8*mm, ym+ey/m2*8*mm
            c.setFillColorRGB(*paleta_conf[(segnum[i]-1)%len(paleta_conf)]); c.circle(bx, by, 3.2*mm, fill=1); c.setFillColorRGB(1, 1, 1); c.setFont('Helvetica-Bold', 7.5)
            c.drawCentredString(bx, by-2.4, f"C{segnum[i]}"); c.setFillColorRGB(0, 0, 0)
    tag(cx0, cy0+1*mm, f"LOTE {proj.get('lote') or ''}", bold=True, size=10); tag(cx0, cy0-4.5*mm, f"{_fmt(r['area'])} m²", size=9)
    # Referência de localização ligada ao V1.
    if proj.get('rua_esquina') and proj.get('distancia_esquina'):
        vx, vy = P(pts[0])
        ref_txt = f"V1 a {_fmt(float(str(proj.get('distancia_esquina')).replace(',', '.')))} metros pelo lado direito de quem olha de frente para o imóvel até a esquina da {proj.get('rua_esquina')}"
        ref_lines = wrap(ref_txt, 66*mm, 'Helvetica', 7.2)
        box_w = 70*mm; line_h = 3.5*mm; box_h = len(ref_lines)*line_h+4*mm
        bx = dx0+4*mm if vx > dx0+dw/2 else dx0+dw-box_w-4*mm
        by = dy0+dh-box_h-5*mm if vy < dy0+dh/2 else dy0+5*mm
        bx = max(dx0+2*mm, min(bx, dx0+dw-box_w-2*mm))
        by = max(dy0+2*mm, min(by, dy0+dh-box_h-2*mm))
        ex = bx+box_w if vx < bx else bx
        ey = max(by, min(vy, by+box_h))
        c.setStrokeColorRGB(.15,.15,.15); c.setLineWidth(.55); c.line(vx,vy,ex,ey)
        c.setFillColorRGB(1,1,1); c.setFillAlpha(.92); c.roundRect(bx,by,box_w,box_h,1.5*mm,fill=1,stroke=1); c.setFillAlpha(1)
        c.setFillColorRGB(0,0,0); c.setFont('Helvetica',7.2)
        for li,line in enumerate(ref_lines): c.drawString(bx+2*mm,by+box_h-3.2*mm-li*line_h,line)

    nx_, ny_ = dx0+dw-10*mm, dy0+dh-26*mm; c.setFillColorRGB(1, 1, 1); c.rect(nx_-6*mm, ny_-3*mm, 12*mm, 26*mm, fill=1, stroke=0); c.setFillColorRGB(0, 0, 0)
    c.line(nx_, ny_, nx_, ny_+15*mm); c.line(nx_, ny_+15*mm, nx_-2*mm, ny_+11*mm); c.line(nx_, ny_+15*mm, nx_+2*mm, ny_+11*mm); c.setFont('Helvetica-Bold', 10); c.drawCentredString(nx_, ny_+17*mm, 'N')
    bar = next(m for m in [1, 2, 5, 10, 20, 50, 100, 200, 500] if m*k > 20*mm)
    c.setFillColorRGB(1, 1, 1); c.rect(dx0+2*mm, dy0+3*mm, bar*k+46*mm, 10*mm, fill=1, stroke=0); c.setFillColorRGB(0, 0, 0)
    c.rect(dx0+4*mm, dy0+5*mm, bar*k, 1.6*mm); c.setFont('Helvetica', 8); c.drawString(dx0+4*mm, dy0+8.5*mm, f"0   {bar} m     Escala numérica 1:{esc} (A3)")

    # ---- painel lateral: confrontantes + quadro de coordenadas (tudo na mesma folha)
    qx = dx0+dw+4*mm; qw = W-10*mm-qx; ytop = dy0+dh
    rh = min(3.7*mm, 98*mm/(n+2)); tab_h = (n+2)*rh
    ybot = dy0+tab_h+8*mm
    def wrap(t, wd, f, sz):
        o, l = [], ''
        for pal in t.split():
            if stringWidth((l+' '+pal).strip(), f, sz) > wd: o.append(l); l = pal
            else: l = (l+' '+pal).strip()
        return o+[l]
    if drone and os.path.exists(drone):  # imagem do drone na mesma folha, acima do quadro de coordenadas
        from PIL import Image as _I
        iw, ih = _I.open(drone).size; maxh = (ytop-ybot)*(.55 if cinfo else .9)-8*mm
        dw_ = qw; dh_ = dw_*ih/iw
        if dh_ > maxh: dh_ = maxh; dw_ = dh_*iw/ih
        dyb = ybot+2*mm; dxb = qx+(qw-dw_)/2
        c.setFont('Helvetica-Bold', 8.5); c.drawString(qx, dyb+dh_+2*mm, 'IMAGEM AÉREA (DRONE)')
        c.drawImage(ImageReader(drone), dxb, dyb, dw_, dh_); c.rect(dxb, dyb, dw_, dh_)
        ybot = dyb+dh_+8*mm
    blocos = []
    for i in cinfo:
        p = i['p']; blocos.append((i, wrap(_conf_txt(p).upper(), qw-8*mm, 'Helvetica-Bold', 7.5)))
    need = sum(len(l)*3.4*mm+2*3.1*mm+2.6*mm for _, l in blocos)
    avail = ytop-6*mm-ybot; sc = max(.62, min(1, avail/need)) if need else 1
    c.setFont('Helvetica-Bold', 9.5); c.drawString(qx, ytop-4*mm, 'CONFRONTANTES'); y = ytop-10*mm
    paleta = [(0.12,.36,.72),(.78,.25,.18),(.12,.53,.36),(.55,.30,.68),(.85,.48,.10),(.10,.55,.62),(.68,.28,.43),(.42,.48,.16),(.28,.35,.52),(.65,.38,.18)]
    for i, lines in blocos:
        p = i['p']; cor=paleta[(i['num']-1)%len(paleta)]
        if y < ybot: c.setFont('Helvetica-Oblique', 7); c.drawString(qx, ybot, '… (demais confrontantes no memorial descritivo)'); break
        c.setFillColorRGB(*cor); c.circle(qx+2.6*mm, y+1.2*mm, 2.6*mm, fill=1); c.setFillColorRGB(1, 1, 1); c.setFont('Helvetica-Bold', 6.5); c.drawCentredString(qx+2.6*mm, y, f"C{i['num']}"); c.setFillColorRGB(0, 0, 0)
        for ln in lines:
            c.setFont('Helvetica-Bold', 7.5*sc); c.drawString(qx+7*mm, y, ln); y -= 3.4*mm*sc
        c.setFont('Helvetica', 7*sc)
        natureza = p.get('tipo_confrontante') or ('via' if re.match(r'(?i)^(rua|avenida|travessa|estrada|pra[çc]a|alameda|rodovia|beco|ladeira|via)\\b', (p.get('nome') or '').strip()) else ('matricula' if p.get('matricula') and not p.get('nome') else 'pessoa'))
        # CPF e inscrição imobiliária só são pertinentes a confrontante pessoa.
        if natureza == 'pessoa':
            detalhes = []
            if p.get('cpf'): detalhes.append(f"CPF/CNPJ: {p['cpf']}")
            if p.get('inscricao'): detalhes.append(f"Cad. imobiliário: {p['inscricao']}")
            if detalhes:
                c.drawString(qx+7*mm, y, '   '.join(detalhes)); y -= 3.1*mm*sc
        c.drawString(qx+7*mm, y, f"Lado {i['lado']} · {p.get('v_ini') or '?'}→{p.get('v_fim') or '?'} · {_fmt(i['comp'])} m")
        y -= 3.1*mm*sc
        y -= 2.6*mm*sc
    yt = dy0+tab_h; c.line(qx, yt+4*mm, qx+qw, yt+4*mm)
    c.setFont('Helvetica-Bold', 8.5); c.drawString(qx, yt, 'QUADRO DE COORDENADAS – SIRGAS 2000, UTM '+str(proj['zona'])+'S'); y = yt-rh-1*mm
    cols = [0, 13*mm, 42*mm, 74*mm, 98*mm]; fs = min(7.2, rh/mm*1.85)
    c.setFont('Helvetica-Bold', fs)
    for x_, t in zip(cols, ['Vért.', 'E (m)', 'N (m)', 'Azimute', 'Dist. (m)']): c.drawString(qx+x_, y, t)
    c.setFont('Helvetica', fs)
    for i, v in enumerate(vs):
        y -= rh; q = pts[(i+1) % n]
        for x_, t in zip(cols, [v['nome'], _fmt(v['e'], 5), _fmt(v['n'], 5), geo.dms(geo.azimute(pts[i], q)), _fmt(_dist_trecho(vs, i))]): c.drawString(qx+x_, y, t)
    # ---- selo
    c.rect(14*mm, 12*mm, W-28*mm, 44*mm); c.setFont('Helvetica-Bold', 11)
    c.drawString(18*mm, 49*mm, f"PLANTA DE LOTE – REURB ({proj.get('modalidade') or 'REURB-S'})")
    c.setFont('Helvetica', 8.2); ocup = ', '.join(p['nome'] for p in pessoas if p['tipo'] in ('ocupante', 'beneficiario'))[:125]
    L = [f"Município: {proj['municipio']}/BA   Núcleo: {proj.get('comunidade') or ''}   Quadra: {proj.get('quadra') or ''}   Lote: {proj.get('lote') or ''}", f"Ocupante(s)/beneficiário(s): {ocup}",
         f"Área: {_fmt(r['area'])} m² ({_fmt(r['ha'], 4)} ha)   Perímetro: {_fmt(r['perimetro'])} m   SIRGAS 2000 – UTM {proj['zona']}S   Data: {proj.get('data','')}",
         f"Responsável técnico: {proj.get('tecnico') or ''}   {proj.get('conselho') or 'CREA/CAU/CFT'}: {proj.get('registro') or ''}"]
    for i, line in enumerate(L): c.drawString(18*mm, 43*mm-i*5.2*mm, line)
    beneficiarios = [p for p in pessoas if p.get('tipo') == 'beneficiario']
    ben = beneficiarios[0] if beneficiarios else next((p for p in pessoas if p.get('tipo') == 'ocupante'), {})
    nome_ben = (ben.get('nome') or 'Beneficiário(a)')[:42]
    nome_conj = (ben.get('conjuge') or 'Cônjuge')[:42]
    c.setFont('Helvetica', 7.5)
    c.drawString(18*mm, 19*mm, f"Beneficiário(a): {nome_ben}")
    c.line(18*mm, 16.5*mm, W/2-8*mm, 16.5*mm)
    c.drawString(W/2+2*mm, 19*mm, f"Cônjuge: {nome_conj}")
    c.line(W/2+2*mm, 16.5*mm, W-18*mm, 16.5*mm)
    c.setFont('Helvetica', 7)
    fonte = (mapa.FONTES[base][1]+' – fundo ilustrativo (localização/entorno).') if img and base in mapa.FONTES else ('Planta técnica vetorial – fundo branco, sem base cartográfica.' if base == 'branco' else 'Fundo cartográfico indisponível; geometria representada em fundo branco.')
    c.drawString(18*mm, 13*mm, fonte)
    c.setFont('Helvetica', 7.5); c.drawRightString(W-18*mm, 13*mm, 'Assinatura do responsável técnico')
    c.showPage()
    c.save(); return b.getvalue()
