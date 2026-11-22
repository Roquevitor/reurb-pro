"""CRF – Certidão de Regularização Fundiária, no modelo de 15 seções (Prefeitura de Wenceslau Guimarães)."""
import io, os, re
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import geo, docs

MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
_UN = ['zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
_DZ = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
_CT = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']

def _m999(n):
    if n == 100: return 'cem'
    c, r = divmod(n, 100); p = []
    if c: p.append(_CT[c])
    if r:
        if r < 20: p.append(_UN[r])
        else:
            d, u = divmod(r, 10); p.append(_DZ[d]+(' e '+_UN[u] if u else ''))
    return ' e '.join(p)

def _inteiro(n):
    if n == 0: return 'zero'
    mi, resto = divmod(n, 10**6); mil, un = divmod(resto, 1000); out = ''
    if mi: out = _m999(mi)+(' milhão' if mi == 1 else ' milhões')
    if mil:
        t = 'mil' if mil == 1 else _m999(mil)+' mil'
        out = (out+(' e ' if (resto < 100 or resto % 100 == 0) else ' ') if out else '')+t
    if un:
        out = (out+(' e ' if (un < 100 or un % 100 == 0) else ' ') if out else '')+_m999(un)
    return out

def reais(v):
    t = str(v).replace('R$', '').strip()
    if ',' in t: t = t.replace('.', '').replace(',', '.')
    elif re.search(r'\.\d{3}$', t): t = t.replace('.', '')
    try: v = float(t)
    except Exception: return None
    i = int(v); c = round((v-i)*100)
    ext = _inteiro(i)+(' real' if i == 1 else ' reais')
    if c: ext += ' e '+_inteiro(c)+(' centavo' if c == 1 else ' centavos')
    return f"R$ {docs._fmt(v)} ({ext})"

def data_extenso(d):
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', d or '')
    return f"{int(m.group(1))} de {MESES[int(m.group(2))-1]} de {m.group(3)}" if m else (d or '')

def ph(txt):  # campo pendente: aparece destacado em amarelo no Word
    return f"[[{txt}]]"

def V(x, label):
    return x.strip() if x and x.strip() else ph(label)

def _rich(p, text, size=11):
    for parte in re.split(r'(\*\*.*?\*\*|\[\[.*?\]\])', text):
        if not parte: continue
        if parte.startswith('**'): r = p.add_run(parte[2:-2]); r.bold = True
        elif parte.startswith('[['): r = p.add_run('['+parte[2:-2]+']'); r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        else: r = p.add_run(parte)
        r.font.size = Pt(size)

def _par(doc, text, just=True, space=4):
    p = doc.add_paragraph(); _rich(p, text)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if just else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_after = Pt(space); p.paragraph_format.first_line_indent = Cm(1.25) if just else None
    return p

def _secao(doc, titulo):
    t = doc.add_table(rows=1, cols=1); t.style = 'Table Grid'; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]; p = c.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(titulo.upper()); r.bold = True; r.font.size = Pt(11.5)
    p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(2)
    sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(0); sp.paragraph_format.space_before = Pt(0)
    for r in sp.runs: r.font.size = Pt(2)

def _eh_via(p):
    if p.get('tipo_confrontante'): return p.get('tipo_confrontante') == 'via'
    return bool(re.match(r'(?i)^(rua|avenida|travessa|estrada|pra[çc]a|alameda|rodovia|beco|ladeira|via)\b', (p.get('nome') or '').strip()))

def _artigo(nome):
    return 'a ' if re.match(r'(?i)^(rua|avenida|travessa|estrada|pra[çc]a|alameda|rodovia|beco|ladeira|via)\b', nome.strip()) else ''

def _doc(p):
    return 'CNPJ' if len(re.sub(r'\D', '', p.get('cpf') or '')) == 14 else 'CPF'

def _pessoa(p):
    s = p['nome']+(f", {_doc(p)}: {p['cpf']}" if p.get('cpf') else '')
    ex = []
    if p.get('matricula'): ex.append(f"Matrícula: {p['matricula']}")
    if p.get('insc_reduzida'): ex.append(f"Inscrição Reduzida: {p['insc_reduzida']}")
    if p.get('inscricao'): ex.append(f"Zoneamento: {p['inscricao']}")
    return s+(', de '+', '.join(ex) if ex else '')

def _trecho(p):
    """Texto do confrontante no memorial (seção 2 da CRF e memorial planimétrico)."""
    if not p: return 'confrontante '+ph('não informado')
    natureza = p.get('tipo_confrontante') or ''
    if _eh_via(p): return f"com {_artigo(p.get('nome') or 'via pública')}{p.get('nome') or 'via pública'}"
    if natureza == 'matricula' or (p.get('matricula') and not p.get('cpf') and not p.get('nome')):
        return f"com o imóvel objeto da matrícula nº {p.get('matricula')}, do Serviço de Registro de Imóveis, CNS nº {p.get('cns') or 'não informado'}"
    cond = p.get('condicao') or 'em posse de'
    if p.get('descricao'): return f"{p['descricao'].strip().rstrip(',')}, {cond} {_pessoa(p)}"
    return f"com {_pessoa(p)}"

def _fmtc(x, d=3):
    return docs._fmt(x, 5 if d == 3 else d)

def _dms1(a):
    d = int(a); m = int((a-d)*60); s = (a-d-m/60)*3600
    return f"{d}°{m}'{s:.1f}\""

def mapa_png(proj, vs):
    try:
        import mapa
        from PIL import ImageDraw
        pts = [(v['e'], v['n']) for v in vs]
        es, ns = [p[0] for p in pts], [p[1] for p in pts]
        span = max(max(es)-min(es), max(ns)-min(ns), 10)*3.4; W, H = 1400, 875
        cx, cy = (max(es)+min(es))/2, (max(ns)+min(ns))/2; hw = span/2; hh = hw*H/W
        e0, e1, n0, n1 = cx-hw, cx+hw, cy-hh, cy+hh
        img = mapa.fundo(proj['zona'], e0, e1, n0, n1, 'satelite', W, H)
        if img is None: return None
        d = ImageDraw.Draw(img, 'RGBA')
        px = [((p[0]-e0)/(e1-e0)*(W-1), (n1-p[1])/(n1-n0)*(H-1)) for p in pts]
        d.polygon(px, fill=(255, 215, 0, 60)); d.line(px+[px[0]], fill=(255, 215, 0, 255), width=4)
        for (x, y), v in zip(px, vs):
            d.ellipse([x-5, y-5, x+5, y+5], fill=(220, 0, 0, 255)); d.text((x+8, y-12), v['nome'], fill=(255, 255, 255, 255))
        b = io.BytesIO(); img.save(b, 'PNG'); return b.getvalue()
    except Exception:
        return None

def _campo_pagina(par):
    r = par.add_run(); f1 = OxmlElement('w:fldChar'); f1.set(qn('w:fldCharType'), 'begin')
    it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve'); it.text = 'PAGE'
    f2 = OxmlElement('w:fldChar'); f2.set(qn('w:fldCharType'), 'end'); r._r.append(f1); r._r.append(it); r._r.append(f2)

def crf_docx(proj, vs, pessoas, brasao=None, foto=None):
    g = lambda k: (proj.get(k) or '').strip()
    pts = [(v['e'], v['n']) for v in vs]; res = docs.resumo(proj['zona'], vs); n = len(vs)
    seg = docs._cobertura(vs, pessoas)
    mun = g('municipio'); MUN = mun.upper(); mod = (g('modalidade') or 'REURB-S').replace('-', ' ')
    doc = Document(); st = doc.styles['Normal']; st.font.name = 'Arial'; st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')
    sec = doc.sections[0]; sec.left_margin = sec.right_margin = Cm(2); sec.top_margin = Cm(1.5); sec.bottom_margin = Cm(1.8)
    # cabeçalho institucional
    t = doc.add_table(rows=1, cols=2); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.columns[0].width = Cm(3); t.columns[1].width = Cm(14)
    c0, c1 = t.rows[0].cells; c0.width = Cm(3); c1.width = Cm(14)
    if brasao and os.path.exists(brasao):
        try: c0.paragraphs[0].add_run().add_picture(brasao, width=Cm(2.4))
        except Exception: pass
    p = c1.paragraphs[0]; r = p.add_run(f"PREFEITURA MUNICIPAL DE {MUN}"); r.bold = True; r.font.size = Pt(13)
    p2 = c1.add_paragraph(); _rich(p2, f"CNPJ nº {V(g('prefeitura_cnpj'), 'CNPJ da Prefeitura')},", 10)
    p3 = c1.add_paragraph(); _rich(p3, f"{V(g('prefeitura_end'), 'Endereço da Prefeitura')}, {mun}/BA", 10)
    doc.add_paragraph()
    tp = doc.add_paragraph(); tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = tp.add_run(f"CERTIDÃO DE REGULARIZAÇÃO FUNDIÁRIA Nº {V(g('crf_numero'), 'nº/ano')}"); r.bold = True; r.font.size = Pt(13)
    fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT; _campo_pagina(fp)

    end_imovel = f"{V(g('rua'), 'Rua')}, {V(g('numero'), 'nº')}, Bairro {V(g('bairro'), 'Bairro')}, {mun}/BA, CEP {V(g('cep'), 'CEP')}"
    # 1
    _secao(doc, '1 - Disposições iniciais e classificação de modalidade de REURB')
    loc = f", localizado a {g('localizacao')}" if g('localizacao') else ''
    _par(doc, f"Certifico que o **MUNICÍPIO DE {MUN}/BA**, Estado da Bahia, pessoa jurídica de direito público interno, CNPJ {V(g('prefeitura_cnpj'), 'CNPJ')}, "
              f"estabelecido na {V(g('prefeitura_end'), 'endereço da Prefeitura')}, representado por seu prefeito, Sr. {V(g('prefeito_nome'), 'nome do prefeito')}, {V(g('prefeito_qualif'), 'nacionalidade, estado civil, RG, CPF')}, "
              f"com fundamento na Lei Federal nº 13.465/2017, na Lei Municipal nº {V(g('lei_municipal'), 'nº/ano da lei municipal')} e, ainda, com fulcro no processo administrativo nº {V(g('processo'), 'nº do processo')}, "
              f"processou o pedido de regularização fundiária, a requerimento de interessado, classificando-o na modalidade **\"{mod}\"**, de área situada em núcleo urbano informal consolidado, com a seguinte descrição: "
              f"**LOTE URBANO**, inscrito no cadastro imobiliário municipal sob o nº **{V(g('insc_cadastral'), 'inscrição cadastral')}**, quadra {V(g('quadra'), 'quadra')}, lote {V(g('lote'), 'lote')}, "
              f"localizado na {end_imovel}{loc}, com as seguintes medidas e confrontações (conforme planta e memorial descritivo anexo):")
    if g('procurador_nome'):
        _par(doc, f"Representação por procurador: **{g('procurador_nome')}**, {g('procurador_qualificacao') or 'qualificação não informada'}, conforme procuração {g('procurador_procuracao') or 'a ser identificada nos autos do processo administrativo'}.")
    # 2
    _secao(doc, '2 - Descrição do perímetro')
    ini = (f"Inicia-se a descrição deste terreno urbano de propriedade particular, Lote: {V(g('lote'), 'lote')}, Quadra: {V(g('quadra'), 'quadra')}, medindo a área de **{docs._fmt(res['area'])} m²**, "
           f"perímetro de {docs._fmt(res['perimetro'])} metros, localizado na {end_imovel}")
    if g('tipo_imovel'): ini += f", {g('tipo_imovel')}"
    ini += (f", de Inscrição Reduzida: {V(g('insc_reduzida'), 'inscrição reduzida')}, Zoneamento Atual: {V(g('insc_cadastral'), 'zoneamento')}"
            + (f", {g('localizacao')}" if g('localizacao') else '') + f", no vértice {vs[0]['nome']}, de coordenadas {_fmtc(vs[0]['n'])} m Norte e {_fmtc(vs[0]['e'])} m Leste, "
            f"Datum SIRGAS 2000 com Meridiano Central {res['mc']}")
    partes = []
    for k in range(n):
        q = (k+1) % n
        partes.append(f"deste, confrontando neste trecho {_trecho(seg.get(k))}, com azimute {_dms1(geo.azimute(pts[k], pts[q]))} e distância {docs._fmt(docs._dist_trecho(vs, k))} metros até o vértice {vs[q]['nome']}, "
                      f"de coordenadas {_fmtc(vs[q]['n'])} m Norte e {_fmtc(vs[q]['e'])} m Leste")
    ini += ', '+', '.join(partes)+(", fechando a poligonal e encerrando esta descrição. Todas as coordenadas aqui descritas estão georreferenciadas ao Sistema Geodésico Brasileiro, "
        f"e referenciadas ao Meridiano Central {res['mc']}° WGr, tendo como Datum SIRGAS 2000. Todos os azimutes e distâncias, área e perímetro foram calculados no plano de projeção no Sistema Universal Transverso de Mercator (UTM).")
    _par(doc, ini)
    # 3
    _par(doc, f"Área (m²): {docs._fmt(res['area'])}", just=False, space=0); _par(doc, f"Perímetro (m): {docs._fmt(res['perimetro'])}", just=False)
    _secao(doc, '3 - Sistema de informação geográfica do registro de imóveis - SIG RI')
    _par(doc, "Imóvel que consta no mapa do registro de imóveis do Brasil, disponível no site https://www.registrodeimoveis.org.br/mapa. "+ph('conferir no mapa do ONR/SIG RI e, se desejar, substituir a imagem abaixo pela captura do mapa'))
    if foto:
        pi = doc.add_paragraph(); pi.alignment = WD_ALIGN_PARAGRAPH.CENTER; pi.add_run().add_picture(io.BytesIO(foto), width=Cm(14.5))
        pc = doc.add_paragraph(); pc.alignment = WD_ALIGN_PARAGRAPH.CENTER; _rich(pc, 'Fachada do imóvel.', 8)
    else:
        _par(doc, ph('inserir a foto da fachada (tirar foto ou importar no sistema)'), just=False)
    # 4
    _secao(doc, '4. Responsável técnico')
    _par(doc, f"Responsável Técnico: {V(g('tecnico'), 'nome')}, {V(g('profissao_resp'), 'profissão (ex.: Arquiteto e Urbanista)')}. Registro/{g('conselho') or 'CAU/CREA/CFT'} nº {V(g('registro'), 'nº do registro')}, "
              f"{'RRT/ART'} nº {V(g('rrt'), 'nº RRT/ART')}.", just=False)
    # 5
    _secao(doc, '5 - Da construção')
    _par(doc, g('construcao') or ph('Descrever a edificação existente: tipo, dimensões (frente, lados e fundo), pavimentos, áreas construídas, taxa de ocupação, índice de aproveitamento e responsável técnico — ou informar que o lote não possui edificação'))
    # 6
    _secao(doc, '6 - Identificação e notificação dos imóveis confrontantes')
    _par(doc, 'Os confrontantes se apresentam da seguinte forma:')
    nomes = [v['nome'] for v in vs]
    cf = sorted([p for p in pessoas if p['tipo'] == 'confrontante'], key=lambda p: nomes.index(p['v_ini']) if p.get('v_ini') in nomes else 99)
    for i, p in enumerate(cf):
        l = chr(97+i); tr = f"Do vértice {p.get('v_ini') or '?'} ao vértice {p.get('v_fim') or '?'}: "
        natureza = p.get('tipo_confrontante') or ('via' if _eh_via(p) else ('matricula' if p.get('matricula') and not p.get('cpf') and not p.get('nome') else 'pessoa'))
        if natureza == 'via':
            tx = f"confrontando-se com {_artigo(p.get('nome') or 'via pública')}{p.get('nome') or 'via pública'}, {mun}/BA;"
        elif natureza == 'matricula':
            tx = f"confrontando-se com o imóvel objeto da matrícula nº {p.get('matricula')}, do Serviço de Registro de Imóveis, CNS nº {p.get('cns')};"
        else:
            tx = 'confrontando-se com '
            tx += (p['descricao'].strip().rstrip(',') if p.get('descricao') else p.get('nome') or 'pessoa confrontante não identificada')
            if p.get('inscricao'): tx += f", inscrição {p['inscricao']}"
            if p.get('matricula'): tx += f", Matrícula {p['matricula']}"
            if p.get('cns'): tx += f", CNS nº {p['cns']}"
            if p.get('descricao') and p.get('nome'): tx += f", {(p.get('condicao') or 'de posse de').replace('em posse de', 'de posse de').replace('em propriedade de', 'de propriedade de')} {p['nome']}"
            if p.get('cpf'): tx += f", {_doc(p)}: {p['cpf']}"
            tx += '.'
            if p.get('notificacao'): tx += f" Notificação pessoal realizada em {p['notificacao']}."
            elif p.get('nome'): tx += ' '+ph('data da notificação')
            if p.get('certidoes'): tx += f" {p['certidoes'].strip()}"
            tx += ';' if i < len(cf)-1 else '.'
        _par(doc, f"{l}) {tr}{tx}")
    # 7
    _secao(doc, '7 - Valor atribuído ao imóvel')
    vl = reais(g('valor_lote')) if g('valor_lote') else None; ve = reais(g('valor_edif')) if g('valor_edif') else None
    _par(doc, f"Avaliação: Lote avaliado em {vl or ph('valor do lote')}{', conforme '+g('ref_cub') if g('ref_cub') else ''}.", space=0)
    if ve or g('construcao'): _par(doc, f"Avaliação da Edificação: {ve or ph('valor da edificação')}.")
    # 8
    _secao(doc, '8 - Incidência de imposto de transmissão de bens imóveis')
    _par(doc, 'ITBI: não há incidência de ITBI por se tratar de aquisição originária, conforme art. 11, VIII e 23 da Lei 13.465/17.')
    # 9
    _secao(doc, '9 - Situação e origem registral do núcleo urbano')
    _par(doc, f"O imóvel objeto da regularização se situa em núcleo urbano informal consolidado denominado {V(g('nucleo') or g('comunidade'), 'nome do núcleo')}, comprovadamente existente anteriormente a 22 de dezembro de 2016. "
              f"Imóvel com origem registral na Matrícula/Transcrição: {V(g('nucleo_origem'), 'matrícula/transcrição e CRI de origem')}.")
    # 10-12
    _secao(doc, '10 - Aprovações urbanísticas e ambientais do projeto de regularização fundiária')
    _par(doc, 'Projeto de regularização fundiária nos termos do §2º do art. 30 do Decreto 9.310/18, por se tratar de área já consolidada com sistema viário instalado, infraestrutura essencial e equipamentos públicos e comunitários existentes, '
              'sem necessidade de medidas de mitigação e compensação urbanística e ambiental ou de estudos técnicos, sem necessidade de intervenções a serem executadas, dispensadas as exigências relativas ao percentual mínimo e as dimensões de áreas '
              'destinadas ao uso público ou ao tamanho dos lotes regularizados, assim como a outros parâmetros urbanísticos e edilícios, dispensados os estudos técnicos referidos no art. 11 da Lei 13.465, por não se tratar de hipótese de áreas de preservação permanente, nas unidades de conservação.')
    _secao(doc, '11 - Responsabilidades das obras e serviços constantes do cronograma')
    _par(doc, 'Não há necessidade de realização de obras e serviços visto que dispensado o projeto de regularização fundiária por se tratar de núcleo urbano informal consolidado que já possui todos os parâmetros urbanísticos como sistema viário, '
              'infraestrutura essencial, equipamentos públicos e comunitários já existentes.')
    _secao(doc, '12 - Publicação em diário oficial do município')
    _par(doc, 'Depois de superadas todas as fases e cumpridas todas as formalidades legais, notificados e/ou dispensadas as notificações de todos os titulares de domínios, direitos reais ou confinantes ou terceiros eventualmente interessados, '
              f"com decurso do prazo sem impugnação, consoante Edital, publicado no Diário Oficial do Município em {V(g('edital'), 'data, ano e edição do Diário Oficial')}.")
    # 13
    _secao(doc, '13 - Do deferimento e titulação da REURB')
    _par(doc, f"Foi deferido o requerimento, mediante emprego, no âmbito da REURB \"{mod[-1]}\", do instituto jurídico da \"{g('titulo') or 'legitimação fundiária'}\", outorgando-lhe o respectivo direito real.")
    # 14
    _secao(doc, '14 - Ocupante/beneficiário')
    bs = [p for p in pessoas if p['tipo'] in ('ocupante', 'beneficiario')]
    def qual(p):
        s = p['nome'].upper()
        if p.get('nascimento'): s += f", nascido(a) em {p['nascimento']}"
        if p.get('filiacao'): s += f", filho(a) de {p['filiacao']}"
        s += f", {p.get('nacionalidade') or 'brasileiro(a)'}, maior, capaz"
        if p.get('profissao'): s += f", {p['profissao']}"
        if p.get('rg'): s += f", RG {p['rg']}"
        if p.get('cpf'): s += f", CPF {p['cpf']}"
        if p.get('estado_civil'): s += f", {p['estado_civil']}"+(f" sob o regime {p['regime']}" if p.get('regime') else '')
        if p.get('cert_casamento'): s += f" (conforme faz prova de certidão de casamento matrícula: {p['cert_casamento']})"
        if p.get('conjuge'): s += f" com {p['conjuge'].strip().rstrip(',')}"
        return s
    quals = [qual(p) for p in bs] or [ph('nome e qualificação do beneficiário')]
    end_b = next((p['endereco'] for p in bs if p.get('endereco')), None)
    _par(doc, f"Certifico, igualmente, o integral atendimento ao art. 41 da Lei nº 13.465/2017, e indico como beneficiário/ocupante: {'; '.join(quals)}, "
              f"{'são residentes e domiciliados' if len(bs) > 1 or any(p.get('conjuge') for p in bs) else 'residente e domiciliado(a)'} na {end_b or ph('endereço do beneficiário')}, outorgando-lhe direito real de propriedade por aquisição originária.")
    if g('certidoes_benef'): _par(doc, g('certidoes_benef'))
    # 15
    _secao(doc, '15 - Observações finais')
    _par(doc, 'Ficam ressalvados eventuais erros, omissões e direitos de terceiros. Requer-se e autoriza-se ao Oficial de Registro de Imóveis competente que pratique todos os atos necessários à efetivação do registro do presente título.')
    _par(doc, f"{mun}/BA, {data_extenso(g('data'))}.", just=False, space=18)
    for ln, bold in [(f"MUNICÍPIO DE {MUN}/BA", True), (V(g('prefeito_nome'), 'nome do prefeito'), False), ('Prefeito', False)]:
        pp = doc.add_paragraph(); pp.alignment = WD_ALIGN_PARAGRAPH.CENTER; pp.paragraph_format.space_after = Pt(0); _rich(pp, ('**'+ln+'**') if bold else ln)
    b = io.BytesIO(); doc.save(b); return b.getvalue()
