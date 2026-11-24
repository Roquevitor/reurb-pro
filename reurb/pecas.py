"""Peças do técnico: memorial planimétrico, memorial do imóvel, requerimento de averbação e requerimento de REURB."""
import io, os, re
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import geo, docs, crf

F = docs._fmt
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')

def _base(papel=None):
    p = papel if papel and os.path.exists(papel) else os.path.join(ASSETS, 'papel_timbrado.docx')
    try:
        d = Document(p); body = d.element.body
        for ch in list(body):
            if ch.tag != qn('w:sectPr'): body.remove(ch)
    except Exception:
        d = Document()
    return _estilo(d)

def _plain():
    d = Document(); d.styles['Normal'].paragraph_format.space_after = Pt(4); s = d.sections[0]; s.left_margin = s.right_margin = Cm(2.5); s.top_margin = s.bottom_margin = Cm(1.8)
    return _estilo(d)

def _estilo(d):
    st = d.styles['Normal']; st.font.name = 'Times New Roman'; st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')
    st.paragraph_format.space_after = Pt(6); return d

def _p(d, text, align='j', indent=True, size=11, italic=False, after=6, bold=False):
    p = d.add_paragraph(); crf._rich(p, text, size)
    if italic or bold:
        for r in p.runs:
            if italic: r.italic = True
            if bold: r.bold = True
    p.alignment = {'j': WD_ALIGN_PARAGRAPH.JUSTIFY, 'c': WD_ALIGN_PARAGRAPH.CENTER, 'r': WD_ALIGN_PARAGRAPH.RIGHT, 'l': WD_ALIGN_PARAGRAPH.LEFT}[align]
    if indent and align == 'j': p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.space_after = Pt(after); return p

def _titulo(d, t, sub=False):
    p = d.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = p.add_run(t); r.bold = True; r.underline = True; r.font.size = Pt(12)
    p.paragraph_format.space_after = Pt(12)

def _g(proj, k):
    return (proj.get(k) or '').strip()

def _data(proj):
    return f"{proj['municipio']}, {crf.data_extenso(proj.get('data'))}"

def _assinatura(d, proj, assin):
    _p(d, _data(proj), 'r', italic=True, size=10, after=14)
    if assin and os.path.exists(assin):
        p = d.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after = Pt(0); p.add_run().add_picture(assin, width=Cm(4.2))
    else:
        _p(d, '_________________________________', 'c', after=0)
    for t, it in [(_g(proj, 'tecnico'), False), (_g(proj, 'profissao_resp') or crf.ph('profissão'), True), (f"{_g(proj, 'conselho') or 'CAU'} nº {_g(proj, 'registro')}", True)]:
        p = _p(d, t, 'c', size=10, after=0, italic=it)

# ---------- qualificação dos proprietários ----------
def _q(p):
    f = (p.get('sexo') or '').upper().startswith('F')
    a = 'a' if f else 'o'
    s = f"**{p['nome'].upper()}**, {p.get('nacionalidade') or ('brasileira' if f else 'brasileiro')}"
    if p.get('profissao'): s += f", {p['profissao']}"
    s += f", maior e capaz, portador{'a' if f else ''} do RG nº {crf.V(p.get('rg'), 'RG')}, inscrit{a} no CPF sob o nº {crf.V(p.get('cpf'), 'CPF')}"
    if p.get('nascimento'): s += f", nascid{a} em {p['nascimento']}"
    if p.get('filiacao'): s += f", fil{'ha' if f else 'ho'} de {p['filiacao']}"
    return s

def qualificacao(pessoas):
    pr = [p for p in pessoas if p['tipo'] in ('ocupante', 'beneficiario')]
    if not pr: return crf.ph('qualificação do proprietário'), 0
    p0 = pr[0]

    # Neste documento, o cônjuge pode estar vinculado ao cadastro do titular,
    # sem existir como uma segunda linha na tabela de pessoas.
    if p0.get('conjuge'):
        sexo_titular = (p0.get('sexo') or '').strip().upper()
        sexo_conjuge = 'F' if sexo_titular.startswith('M') else ('M' if sexo_titular.startswith('F') else '')
        p1 = {
            'nome': p0.get('conjuge'),
            'sexo': sexo_conjuge,
            'nacionalidade': p0.get('conjuge_nacionalidade'),
            'profissao': p0.get('conjuge_profissao'),
            'rg': p0.get('conjuge_rg'),
            'cpf': p0.get('conjuge_cpf'),
            'nascimento': p0.get('conjuge_nascimento'),
            'filiacao': p0.get('conjuge_filiacao'),
        }
        f0 = sexo_titular.startswith('F')
        t = f"{_q(p0)}, casad{'a' if f0 else 'o'} com {_q(p1)}."
        if p0.get('regime'):
            t += f" Casados sob o regime de **{p0['regime']}**"
            if p0.get('cert_casamento'): t += f", conforme Certidão de Casamento registrada sob a Matrícula nº {p0['cert_casamento']}"
            if p0.get('cartorio_casamento'): t += f", expedida pelo {p0['cartorio_casamento']}"
            if p0.get('data_casamento'): t += f", tendo o casamento sido celebrado em {p0['data_casamento']}"
            t += '.'
        end = next((p.get('endereco') for p in pr if p.get('endereco')), None)
        t += f" Ambos são residentes e domiciliados na {end or crf.ph('endereço')}."
        return t, 2

    f0 = (p0.get('sexo') or '').upper().startswith('F')
    if len(pr) >= 2 and (p0.get('regime') or p0.get('cert_casamento')):
        p1 = pr[1]
        t = f"{_q(p0)}, casad{'a' if f0 else 'o'} com {_q(p1)}."
        if p0.get('regime'):
            t += f" Casados sob o regime de **{p0['regime']}**"
            if p0.get('cert_casamento'): t += f", conforme Certidão de Casamento registrada sob a Matrícula nº {p0['cert_casamento']}"
            if p0.get('cartorio_casamento'): t += f", expedida pelo {p0['cartorio_casamento']}"
            if p0.get('data_casamento'): t += f", tendo o casamento sido celebrado em {p0['data_casamento']}"
            t += '.'
        end = next((p.get('endereco') for p in pr if p.get('endereco')), None)
        t += f" Ambos são residentes e domiciliados na {end or crf.ph('endereço')}."
        return t, 2

    partes = []
    for p in pr:
        f = (p.get('sexo') or '').upper().startswith('F'); s = _q(p)
        if p.get('estado_civil'): s += f", {p['estado_civil']}"+(f" sob o regime de **{p['regime']}**" if p.get('regime') else '')
        partes.append(s+f", residente e domiciliad{'a' if f else 'o'} na {p.get('endereco') or crf.ph('endereço')}.")
    return ' '.join(partes), len(pr)

def _imovel_end(proj):
    s = f"{crf.V(_g(proj, 'rua'), 'Rua')}, nº{_g(proj, 'numero') or crf.ph('nº')}"
    if _g(proj, 'tipo_imovel'): s += f", {_g(proj, 'tipo_imovel')}"
    return s+f", Bairro {crf.V(_g(proj, 'bairro'), 'Bairro')}, {proj['municipio']} - BA, CEP: {crf.V(_g(proj, 'cep'), 'CEP')}"

def _tec_linha(proj, rrt):
    return f"Responsável Técnico: {_g(proj, 'tecnico').upper()} {_g(proj, 'profissao_resp').upper()} {_g(proj, 'conselho') or 'CAU'} nº {_g(proj, 'registro')}, RRT {crf.V(rrt, 'RRT')}."

def _centro(proj, vs):
    la = sum(geo.to_latlon(proj['zona'], v['e'], v['n'])[0] for v in vs)/len(vs); lo = sum(geo.to_latlon(proj['zona'], v['e'], v['n'])[1] for v in vs)/len(vs)
    f = lambda x: (lambda a: f"{int(a)}°{int((a-int(a))*60):02d}'{((a-int(a))*60-int((a-int(a))*60))*60:06.3f}\"")(abs(x))
    return f(la)+' SUL', f(lo)+' OESTE'

def _foto(d, foto, titulo='FACHADA'):
    _p(d, titulo, 'l', indent=False, italic=True, size=10)
    if foto:
        p = d.add_paragraph(); p.add_run().add_picture(io.BytesIO(foto), width=Cm(14.5))
    else:
        _p(d, crf.ph('inserir a foto da fachada (tirar foto ou importar arquivo no sistema)'), 'l', indent=False)

def _save(d):
    b = io.BytesIO(); d.save(b); return b.getvalue()

# ---------- 1. memorial descritivo – levantamento planimétrico ----------
def memorial_planimetrico(proj, vs, pessoas, foto=None, papel=None, assin=None):
    pts = [(v['e'], v['n']) for v in vs]; n = len(vs); res = docs.resumo(proj['zona'], vs); seg = docs._cobertura(vs, pessoas)
    d = _base(papel); _titulo(d, 'LEVANTAMENTO PLANIMÉTRICO MEMORIAL DESCRITIVO')
    q, np_ = qualificacao(pessoas)
    _p(d, q+(f" {'Ambos proprietários solicitaram' if np_ > 1 else 'O proprietário solicitou'} que fosse executado um levantamento planimétrico para fins de Regularização Fundiária Urbana (REURB)."))
    t = (f"Inicia-se a descrição deste terreno urbano de propriedade particular, Lote: {crf.V(_g(proj, 'lote'), 'lote')}, Quadra: {crf.V(_g(proj, 'quadra'), 'quadra')}, medido a área de **{F(res['area'])} m²**, "
         f"perímetro de **{F(res['perimetro'])} metros**, localizado na {_imovel_end(proj)}, de Inscrição Reduzida: **{crf.V(_g(proj, 'insc_reduzida'), 'inscrição reduzida')}**, Zoneamento Atual: **{crf.V(_g(proj, 'insc_cadastral'), 'zoneamento')}**"
         + (f", a **{_g(proj, 'localizacao')}**" if _g(proj, 'localizacao') else '')
         + f", no vértice **{vs[0]['nome']}**, de coordenadas ***{crf._fmtc(vs[0]['n'], 4)} m Norte e {crf._fmtc(vs[0]['e'], 4)} m Leste***, Datum SIRGAS 2000 com Meridiano Central {res['mc']}")
    for k in range(n):
        j = (k+1) % n
        t += (f", deste, confrontando neste trecho {crf._trecho(seg.get(k))} com azimute **{crf._dms1(geo.azimute(pts[k], pts[j]))}** e distância **{F(docs._dist_trecho(vs, k))} metros** até o vértice **{vs[j]['nome']}**, "
              f"de coordenadas ***{crf._fmtc(vs[j]['n'], 4)} m Norte e {crf._fmtc(vs[j]['e'], 4)} m Leste***")
    t += (f", fechando a poligonal e encerrando esta descrição. Todas as coordenadas aqui descritas estão georreferenciadas ao Sistema Geodésico Brasileiro, e referenciadas ao Meridiano Central {res['mc']}° WGr, "
          "tendo como Datum SIRGAS 2000. Todos os azimutes e distâncias, área e perímetro foram calculados no plano de projeção no Sistema Universal Transverso de Mercator (UTM).")
    t = t.replace('***', '**')
    _p(d, t); _p(d, _tec_linha(proj, _g(proj, 'rrt_levant')))
    la, lo = _centro(proj, vs); _p(d, f"Coordenadas Geográficas de Latitude {la} e Longitude {lo}.")
    _assinatura(d, proj, assin); d.add_page_break(); _foto(d, foto)
    return _save(d)

# ---------- 2. memorial descritivo de imóvel urbano ----------
def _num(x):
    try: return float(str(x).replace('.', '').replace(',', '.')) if ',' in str(x) else float(x)
    except Exception: return None

def _pavimentos(txt):
    pav, cur = [], None
    for ln in (txt or '').splitlines():
        ln = ln.strip()
        if not ln: continue
        if ln.startswith('#'): cur = (ln.lstrip('# ').strip() or 'Pavimento Térreo', []); pav.append(cur); continue
        if cur is None: cur = ('Pavimento Térreo', []); pav.append(cur)
        if ':' in ln:
            nm, ar = ln.rsplit(':', 1); v = _num(ar.strip().replace('m²', '').replace('m2', '').strip())
            if v is not None: cur[1].append((nm.strip(), v))
    return pav

def memorial_imovel(proj, vs, pessoas, papel=None, assin=None):
    pts = [(v['e'], v['n']) for v in vs]; n = len(vs); res = docs.resumo(proj['zona'], vs); terreno = res['area']
    d = _base(papel); _titulo(d, 'MEMORIAL DESCRITIVO DE IMÓVEL URBANO')
    q, _ = qualificacao(pessoas); oc = (_g(proj, 'ocupacao') or 'COMERCIAL').upper()
    _p(d, f"**SOLICITANTE:** {q}")
    _p(d, f"**IDENTIFICAÇÃO E CARACTERIZAÇÃO DA REGIÃO:** Trata-se de região inserida na malha urbana de {proj['municipio']} – Bahia, infraestrutura completa, ocupação predominante **{oc}**, com padrão de ocupação normal, apresentando facilidade de acesso.")
    _p(d, 'A região é formada por construções de médio padrão construtivo e possui média intensidade de tráfego de veículos e pedestres.')
    _p(d, '**SERVIÇOS/INFRAESTRUTURA:** O imóvel é dotado de toda a infraestrutura que normalmente serve às áreas urbanas, assim como rede de água, energia elétrica, esgotos, pavimentação, dentre outras.')
    pav = _pavimentos(_g(proj, 'ambientes'))
    dim = ''
    if n == 4:
        L = [docs._dist_trecho(vs, k) for k in range(4)]
        dim = (f" já edificada com as seguintes dimensões {F(L[0])} metros de frente, {F(L[1])} metros de frente a fundo pelo lado direito de quem da rua olha para o imóvel, {F(L[2])} metros de fundo e {F(L[3])} metros de frente a fundo do lado esquerdo de quem da rua olha para o imóvel,")
    else: dim = f" já edificada, com perímetro de {F(res['perimetro'])} metros,"
    fin = (_g(proj, 'finalidade') or 'comercial').lower()
    t = (f"Trata-se de imóvel urbano {fin} na {_imovel_end(proj)}, lote {crf.V(_g(proj, 'lote'), 'lote')}, quadra {crf.V(_g(proj, 'quadra'), 'quadra')}, Inscrição Reduzida: **{crf.V(_g(proj, 'insc_reduzida'), 'inscrição reduzida')}** e Zoneamento **{crf.V(_g(proj, 'insc_cadastral'), 'zoneamento')}**,{dim} ")
    if not pav: t += crf.ph('descrever os pavimentos e ambientes no campo "Ambientes" do projeto')+'.'
    else:
        tot = 0; blocos = []; area_terreo = None
        for nome, itens in pav:
            ar = sum(v for nm, v in itens if 'aberta' not in nm.lower()); tot += ar; area_terreo = ar if area_terreo is None else area_terreo
            lst = [f"{nm} com {F(v)} m²" for nm, v in itens]
            lst = (', '.join(lst[:-1])+' e '+lst[-1]) if len(lst) > 1 else (lst[0] if lst else '')
            blocos.append(f"**{nome} ({F(ar)}m² Construídos):** {lst}")
        ac = _num(_g(proj, 'area_construida')) or tot
        to = area_terreo/terreno*100; ca = ac/terreno
        t += (f"composta com {len(pav)} pavimento{'s' if len(pav) > 1 else ''}, sendo: " + '; '.join(blocos) +
              f". Totalizando **{F(ac)}m² construídos** em um terreno com {F(terreno)}m², Taxa de Ocupação {F(to)}%, Índice de Permeabilidade {F(100-to)}% e Índice de Aproveitamento {F(ca)}.")
    _p(d, t); _p(d, _tec_linha(proj, _g(proj, 'rrt_imovel')))
    _assinatura(d, proj, assin)
    return _save(d)

# ---------- 3. requerimento de averbação de construção ----------
def _chk(sel, val):
    return '( x )' if (sel or '').lower() == val else '(   )'

def _area_construida(proj):
    ac = _num(_g(proj, 'area_construida'))
    if ac is None:
        pav = _pavimentos(_g(proj, 'ambientes')); ac = sum(v for _, it in pav for nm, v in it if 'aberta' not in nm.lower()) or None
    return ac

def _assina_req(d, proj, pessoas):
    pr = [p for p in pessoas if p['tipo'] in ('ocupante', 'beneficiario')]
    _p(d, f"{proj['municipio']} - BA, {crf.data_extenso(proj.get('data'))}.", 'l', indent=False, italic=True, after=18)
    for p in pr or [{'nome': crf.ph('proprietário')}]:
        _p(d, '__________________________________________', 'c', indent=False, after=0); _p(d, f"**{p['nome'].upper()}**", 'c', indent=False, after=10)

def _destinatario(d, proj):
    _p(d, f"**EXCELENTÍSSIMO REGISTRADOR DA SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DA COMARCA DE {proj['municipio'].upper()}/BA - REGISTRO DE IMÓVEIS**", 'j', indent=False, after=14)

def req_averbacao(proj, vs, pessoas):
    d = _plain(); _destinatario(d, proj)
    q, _ = qualificacao(pessoas); ac = _area_construida(proj); fin = (_g(proj, 'finalidade') or 'comercial').lower(); pad = (_g(proj, 'padrao') or 'médio').lower(); ob = (_g(proj, 'tipo_obra') or 'construída').lower()
    q = q.replace(' Ambos são residentes', ' Ambos são residentes')
    _p(d, f"Eu, {q.rstrip('.')}, vem, respeitosamente, requerer seja averbada na matrícula de nº **{_g(proj, 'matricula_origem') or '_________'}**, livro 02, desta Serventia, que sobre o respectivo terreno localizado no **endereço:** **{_imovel_end(proj)}, Inscrição Reduzida: {crf.V(_g(proj, 'insc_reduzida'), 'inscrição reduzida')}**, foi,")
    _p(d, f"{_chk(ob, 'construída')} construída        {_chk(ob, 'ampliada')} ampliada        {_chk(ob, 'demolida')} demolida", 'l', indent=False)
    _p(d, f"uma edificação de **{F(ac) if ac else crf.ph('área')}** m², de finalidade:", 'l', indent=False)
    _p(d, f"{_chk(fin, 'comercial')} comercial     {_chk(fin, 'industrial')} industrial     {_chk(fin, 'residencial')} residencial, de padrão {_chk(pad, 'popular')} popular/econômico", 'l', indent=False, after=0)
    _p(d, f"{_chk(pad, 'médio')} médio {_chk(pad, 'fino')} fino", 'l', indent=False)
    _p(d, 'Atribui à edificação o valor de:', 'l', indent=False, after=0)
    v = crf.reais(_g(proj, 'valor_edif')) if _g(proj, 'valor_edif') else None
    _p(d, f"**CONSTRUÇÃO {v or crf.ph('valor da edificação')}.{(' '+_g(proj, 'ref_cub_edif')) if _g(proj, 'ref_cub_edif') else ''}**", 'l', indent=False)
    _p(d, 'Segue, anexa, certidão/habite-se da Prefeitura Municipal comprobatória da conclusão da obra em tela, a respectiva data, a metragem e o endereço *(original ou fotocópia autenticada).*'.replace('*', ''))
    _p(d, 'Também acompanha este requerimento a Certidão Detalhada da Edificação emitida pela Prefeitura Municipal (original ou fotocópia autenticada).')
    _p(d, 'OU', 'l', indent=False)
    pop = fin == 'residencial' and pad == 'popular' and (ac or 999) <= 70
    _p(d, f"{'( x )' if pop else '(   )'} afirma o ora requerente, na condição de proprietário, sob as penas da lei, que a edificação em questão tem destinação residencial unifamiliar própria, não tem ele outra residência, não ultrapassa 70 m² (setenta metros quadrados), "
          "tem padrão do tipo econômico/popular e foi executada sem a utilização de mão de obra assalariada, razão pela qual está dispensado da apresentação da CND da Previdência Social (conforme Decreto 3.048 de 06/05/1999).")
    _p(d, 'Requer, por fim, atualização do número do cadastro do imóvel junto à Prefeitura Municipal local, conforme documento anexo, caso tenha havido alteração.')
    _p(d, 'Termos em que,', 'l', indent=False, after=0); _p(d, 'Pede deferimento.', 'l', indent=False)
    _assina_req(d, proj, pessoas); return _save(d)

# ---------- 4. requerimento de registro da regularização fundiária + valor de mercado ----------
def req_reurb(proj, vs, pessoas):
    d = _plain(); _destinatario(d, proj); _p(d, '**REQUERIMENTO DE REGISTRO DA REGULARIZAÇÃO FUNDIÁRIA**', 'c', indent=False, after=12)
    q, _ = qualificacao(pessoas); vt = crf.reais(_g(proj, 'valor_lote')) if _g(proj, 'valor_lote') else None
    _p(d, f"Eu, {q.rstrip('.')}, **REQUEIRO** que, após a análise dos documentos apresentados e o cumprimento das exigências legais, seja promovida a regularização fundiária do imóvel situado na **{_imovel_end(proj)}, Inscrição Reduzida: {crf.V(_g(proj, 'insc_reduzida'), 'inscrição reduzida')}** "
          "e o correspondente registro da regularização junto a esta serventia, bem como a prática dos seguintes atos:")
    for t in ['Abertura de matrícula;', 'Todos os atos necessários para viabilizar o(s) registro(s) e/ou averbações pretendidos e;', 'Emissão de certidão de inteiro teor da matrícula.']:
        _p(d, '- '+t, 'l', indent=False, after=2)
    _p(d, f"**Declaro(amos)** que o(s) imóvel(is) objeto dos atos indicados possui(em) o seguinte valor de mercado: **TERRENO {vt or crf.ph('valor do terreno')}.{(' '+_g(proj, 'ref_cub')) if _g(proj, 'ref_cub') else ''}**")
    _p(d, 'Para fins dos arts. 137 a 181 do Provimento n.º 149/CNJ/2023, declaro(amos) que **NÃO** sou(somos) pessoa exposta politicamente – PEP.')
    _assina_req(d, proj, pessoas); return _save(d)

def nome_arquivo(pessoas, proj):
    pr = [p for p in pessoas if p['tipo'] in ('ocupante', 'beneficiario')]
    base = (pr[0]['nome'].split()[0] if pr else (proj.get('nome') or 'IMOVEL')).upper()
    return re.sub(r'[^A-Z0-9_]', '', base.replace(' ', '_')) or 'IMOVEL'
