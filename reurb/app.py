import os, sqlite3, json, datetime, re, hmac
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, redirect, render_template, send_file, g, url_for, session, abort
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
import io, zipfile, geo, docs, crf, pecas, geoimport, workspace

app = Flask(__name__)
APP_ENV = os.environ.get('APP_ENV', 'development').lower()
SECRET_KEY = os.environ.get('SECRET_KEY')
SENHA = os.environ.get('REURB_SENHA')
if APP_ENV == 'production' and not SECRET_KEY:
    raise RuntimeError('Em produção, configure SECRET_KEY nas variáveis de ambiente.')
app.secret_key = SECRET_KEY or 'chave-local-apenas-desenvolvimento'
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=(APP_ENV == 'production'),
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=8),
    MAX_CONTENT_LENGTH=30 * 1024 * 1024,
    WTF_CSRF_TIME_LIMIT=3600,
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
csrf = CSRFProtect(app)
SENHA = SENHA or ('reurb123' if APP_ENV != 'production' else None)  # compatibilidade local; nunca usar senha padrão em produção
DB = os.environ.get('REURB_DB', 'reurb.db')
CRFCAMPOS = ['crf_numero', 'prefeitura_cnpj', 'prefeitura_end', 'prefeito_nome', 'prefeito_qualif', 'lei_municipal', 'insc_cadastral', 'rua', 'numero', 'bairro', 'cep', 'localizacao', 'insc_reduzida', 'tipo_imovel', 'nucleo', 'nucleo_origem', 'profissao_resp', 'rrt', 'construcao', 'valor_lote', 'valor_edif', 'ref_cub', 'edital', 'titulo', 'certidoes_benef', 'rrt_levant', 'rrt_imovel', 'procurador_nome', 'procurador_qualificacao', 'procurador_procuracao', 'ocupacao', 'finalidade', 'padrao', 'tipo_obra', 'area_construida', 'ambientes', 'ref_cub_edif', 'area_informada', 'perimetro_informado']
MUNCAMPOS = ['municipio', 'prefeitura_cnpj', 'prefeitura_end', 'prefeito_nome', 'prefeito_qualif', 'lei_municipal', 'tecnico', 'conselho', 'registro', 'profissao_resp', 'zona', 'modalidade', 'titulo']
BRASAO = os.environ.get('REURB_BRASAO', 'brasao.png')
UP = os.environ.get('REURB_UPLOADS', 'uploads'); CFG = os.environ.get('REURB_CONFIG', 'config')
os.makedirs(UP, exist_ok=True); os.makedirs(CFG, exist_ok=True)
def cfg(nome, padrao=None):
    p = os.path.join(CFG, nome)
    return p if os.path.exists(p) else (os.path.join(pecas.ASSETS, padrao or nome) if os.path.exists(os.path.join(pecas.ASSETS, padrao or nome)) else None)
PCAMPOS = ['sexo', 'cartorio_casamento', 'data_casamento', 'nome', 'cpf', 'inscricao', 'descricao', 'condicao', 'insc_reduzida', 'notificacao', 'certidoes', 'nascimento', 'filiacao', 'nacionalidade', 'regime', 'conjuge', 'cert_casamento', 'rg', 'estado_civil', 'profissao', 'endereco', 'telefone', 'matricula', 'cns', 'tipo_confrontante', 'v_ini', 'v_fim', 'obs', 'lat', 'lon', 'cadastro_id']
CAD = ['nome', 'cpf', 'rg', 'sexo', 'estado_civil', 'profissao', 'telefone', 'endereco', 'inscricao', 'nascimento', 'filiacao', 'nacionalidade', 'regime', 'conjuge', 'cert_casamento', 'cartorio_casamento', 'data_casamento', 'matricula', 'cns', 'descricao', 'condicao']
PROJ = ['prefeitura_id', 'cartorio_id', 'nucleo_id', 'status', 'nome', 'municipio', 'comunidade', 'quadra', 'lote', 'zona', 'modalidade', 'processo', 'requerente', 'matricula_origem', 'tecnico', 'conselho', 'registro', 'data'] + CRFCAMPOS

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
        g.db.executescript(f"""CREATE TABLE IF NOT EXISTS projetos(id INTEGER PRIMARY KEY, {', '.join(c+' TEXT' for c in PROJ)});
        CREATE TABLE IF NOT EXISTS vertices(id INTEGER PRIMARY KEY, proj_id INT, ordem INT, nome TEXT, e REAL, n REAL, distancia_manual REAL);
        CREATE TABLE IF NOT EXISTS pessoas(id INTEGER PRIMARY KEY, proj_id INT, tipo TEXT, {', '.join(c+' TEXT' for c in PCAMPOS)});
        CREATE TABLE IF NOT EXISTS prefeituras(
          id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, cnpj TEXT, ibge_codigo TEXT,
          uf TEXT DEFAULT 'BA', municipio TEXT, endereco TEXT, prefeito TEXT, telefone TEXT,
          email TEXT, lei_reurb TEXT, brasao_path TEXT, criado_em TEXT);
        CREATE TABLE IF NOT EXISTS cartorios(
          id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, cns TEXT, atribuicao TEXT,
          municipio TEXT, comarca TEXT, endereco TEXT, oficial TEXT, email TEXT, telefone TEXT,
          criado_em TEXT);
        CREATE TABLE IF NOT EXISTS bairros(
          id INTEGER PRIMARY KEY AUTOINCREMENT, prefeitura_id INT, nome TEXT NOT NULL,
          municipio TEXT, distrito TEXT, origem TEXT DEFAULT 'manual', ibge_codigo TEXT,
          ativo INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS logradouros(
          id INTEGER PRIMARY KEY AUTOINCREMENT, prefeitura_id INT, bairro_id INT,
          nome TEXT NOT NULL, tipo TEXT, cep TEXT, distrito TEXT, origem TEXT DEFAULT 'manual',
          observacao TEXT, ativo INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS cadastro_pessoas(id INTEGER PRIMARY KEY AUTOINCREMENT, {', '.join(c+' TEXT' for c in CAD)}, criado_em TEXT, atualizado_em TEXT);
        CREATE TABLE IF NOT EXISTS nucleos(id INTEGER PRIMARY KEY AUTOINCREMENT, cartorio_id INTEGER, prefeitura_id INTEGER, nome TEXT NOT NULL, matricula TEXT, data_matricula TEXT, observacao TEXT, ativo INTEGER DEFAULT 1, criado_em TEXT);
        CREATE INDEX IF NOT EXISTS idx_projetos_prefeitura ON projetos(prefeitura_id);
        CREATE INDEX IF NOT EXISTS idx_projetos_cartorio ON projetos(cartorio_id);
        CREATE INDEX IF NOT EXISTS idx_logradouros_pref ON logradouros(prefeitura_id);
        CREATE INDEX IF NOT EXISTS idx_bairros_pref ON bairros(prefeitura_id);
        CREATE TABLE IF NOT EXISTS prefeitura_cartorios(prefeitura_id INTEGER NOT NULL, cartorio_id INTEGER NOT NULL, PRIMARY KEY(prefeitura_id,cartorio_id));
        CREATE TABLE IF NOT EXISTS historico_logradouros(id INTEGER PRIMARY KEY AUTOINCREMENT, logradouro_id INTEGER NOT NULL, nome_anterior TEXT NOT NULL, tipo_anterior TEXT, motivo TEXT, fonte TEXT, data_registro TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, acao TEXT NOT NULL, entidade TEXT, entidade_id INTEGER, detalhes TEXT, data_registro TEXT NOT NULL);""")
        pc = {r[1] for r in g.db.execute('PRAGMA table_info(projetos)')}
        for c_ in PROJ:
            if c_ not in pc:
                tipo = 'INTEGER' if c_ in ('prefeitura_id','cartorio_id','nucleo_id') else 'TEXT'
                g.db.execute(f'ALTER TABLE projetos ADD COLUMN {c_} {tipo}')
        vcols = {r[1] for r in g.db.execute('PRAGMA table_info(vertices)')}
        if 'distancia_manual' not in vcols: g.db.execute('ALTER TABLE vertices ADD COLUMN distancia_manual REAL')
        cols = {r[1] for r in g.db.execute('PRAGMA table_info(pessoas)')}
        for c_ in PCAMPOS:
            if c_ not in cols: g.db.execute(f'ALTER TABLE pessoas ADD COLUMN {c_} TEXT')
        cc = {r[1] for r in g.db.execute('PRAGMA table_info(cadastro_pessoas)')}
        for c_ in CAD:
            if c_ not in cc: g.db.execute(f'ALTER TABLE cadastro_pessoas ADD COLUMN {c_} TEXT')
        # Migra os registros existentes para a organização principal sem apagar dados.
        # A autorização multiempresa só será ativada após o escopo das rotas.
        workspace.ensure_schema(g.db)
        g.db.commit()
    return g.db

def aviso(msg, cat='ok'): session['_msg'] = [cat, msg]

@app.context_processor
def _ctx():
    return dict(
        flash_msg=session.pop('_msg', None),
        current_user=getattr(g, 'current_user', None),
        current_org_id=getattr(g, 'organization_id', None),
    )

@app.template_filter('rua')
def _rua(r): return geoimport.nome_completo(r['tipo'], r['nome'])

@app.template_filter('databr')
def _databr(v):
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', v or '')
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)}' if m else (v or '')

@app.teardown_appcontext
def close(_):
    d = g.pop('db', None)
    if d: d.close()

@app.before_request
def auth():
    if request.endpoint in ('login', 'setup', 'static'):
        return
    d = db()
    total_users = d.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if session.get('user_id'):
        member = d.execute("""SELECT u.id,u.name,u.email,m.role,m.organization_id,o.name AS organization_name
            FROM users u JOIN memberships m ON m.user_id=u.id
            JOIN organizations o ON o.id=m.organization_id
            WHERE u.id=? AND u.is_active=1 AND m.is_active=1 AND o.status='active'
            ORDER BY m.id LIMIT 1""", (session['user_id'],)).fetchone()
        if member:
            g.current_user = member
            g.organization_id = member['organization_id']
            return
        session.clear()
    # Compatibilidade temporária para a instalação antiga. Assim que o primeiro
    # proprietário individual for criado, a senha compartilhada deixa de funcionar.
    if total_users == 0 and session.get('legacy_ok'):
        g.current_user = None
        g.organization_id = d.execute("SELECT id FROM organizations WHERE slug='organizacao-principal'").fetchone()[0]
        return
    return redirect(url_for('login', next=request.full_path if request.query_string else request.path))

@app.after_request
def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if APP_ENV == 'production':
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response


@app.route('/cadastros')
def cadastros():
    d=db()
    return render_template('cadastros.html', mapa_onr=os.environ.get('REURB_MAPA_REGISTRADORES_URL',''),
      prefeituras=d.execute('SELECT f.*,(SELECT COUNT(*) FROM logradouros l WHERE l.prefeitura_id=f.id AND l.ativo=1) AS n_ruas,(SELECT COUNT(*) FROM bairros b WHERE b.prefeitura_id=f.id AND b.ativo=1) AS n_bairros FROM prefeituras f ORDER BY f.nome').fetchall(),
      cartorios=d.execute('SELECT * FROM cartorios ORDER BY nome').fetchall(),
      nucleos=d.execute('SELECT n.*,c.nome AS cartorio_nome,c.cns,p.nome AS prefeitura_nome FROM nucleos n LEFT JOIN cartorios c ON c.id=n.cartorio_id LEFT JOIN prefeituras p ON p.id=n.prefeitura_id WHERE n.ativo=1 ORDER BY c.nome,n.nome').fetchall(),
      bairros=d.execute('SELECT b.*,p.nome AS prefeitura_nome FROM bairros b LEFT JOIN prefeituras p ON p.id=b.prefeitura_id ORDER BY p.nome,b.nome').fetchall(),
      logradouros=d.execute('SELECT l.*,p.nome AS prefeitura_nome,b.nome AS bairro_nome FROM logradouros l LEFT JOIN prefeituras p ON p.id=l.prefeitura_id LEFT JOIN bairros b ON b.id=l.bairro_id WHERE l.ativo=1 ORDER BY p.nome,l.nome LIMIT 2000').fetchall(),
      historico=d.execute('SELECT h.*,l.nome AS nome_atual,p.nome AS prefeitura_nome FROM historico_logradouros h JOIN logradouros l ON l.id=h.logradouro_id LEFT JOIN prefeituras p ON p.id=l.prefeitura_id ORDER BY h.id DESC LIMIT 100').fetchall(),
      associacoes=d.execute('SELECT pc.*,p.nome AS prefeitura_nome,c.nome AS cartorio_nome,c.cns FROM prefeitura_cartorios pc JOIN prefeituras p ON p.id=pc.prefeitura_id JOIN cartorios c ON c.id=pc.cartorio_id ORDER BY p.nome,c.nome').fetchall())

@app.route('/prefeitura/salvar', methods=['POST'])
def prefeitura_salvar():
    f=request.form; d=db()
    campos=['nome','cnpj','ibge_codigo','uf','municipio','endereco','prefeito','telefone','email','lei_reurb']
    vals=[f.get(k,'').strip() for k in campos]
    if not vals[0]: return 'Informe o nome da prefeitura.',400
    if f.get('id'):
        d.execute('UPDATE prefeituras SET '+','.join(k+'=?' for k in campos)+' WHERE id=?',vals+[f['id']])
    else:
        d.execute('INSERT INTO prefeituras('+','.join(campos)+',criado_em) VALUES('+','.join('?' for _ in campos)+',?)',vals+[datetime.datetime.now().isoformat(timespec='seconds')])
    d.commit(); return redirect('/cadastros#prefeituras')

@app.route('/cartorio/salvar', methods=['POST'])
def cartorio_salvar():
    f=request.form; d=db()
    campos=['nome','cns','atribuicao','municipio','comarca','endereco','oficial','email','telefone']
    vals=[f.get(k,'').strip() for k in campos]
    if not vals[0]: return 'Informe o nome da serventia.',400
    if f.get('id'):
        d.execute('UPDATE cartorios SET '+','.join(k+'=?' for k in campos)+' WHERE id=?',vals+[f['id']])
    else:
        d.execute('INSERT INTO cartorios('+','.join(campos)+',criado_em) VALUES('+','.join('?' for _ in campos)+',?)',vals+[datetime.datetime.now().isoformat(timespec='seconds')])
    d.commit(); return redirect('/cadastros#cartorios')

@app.route('/geografia/bairro', methods=['POST'])
def bairro_salvar():
    f=request.form; d=db(); nome=f.get('nome','').strip()
    if not nome or not f.get('prefeitura_id'): return 'Selecione a prefeitura e informe o bairro.',400
    d.execute('INSERT INTO bairros(prefeitura_id,nome,municipio,distrito,origem,ibge_codigo) VALUES(?,?,?,?,?,?)',
      (f['prefeitura_id'],nome,f.get('municipio',''),f.get('distrito',''),f.get('origem','manual'),f.get('ibge_codigo','')))
    d.commit(); return redirect('/cadastros#geografia')

@app.route('/geografia/logradouro', methods=['POST'])
def logradouro_salvar():
    f=request.form; d=db(); nome=f.get('nome','').strip()
    if not nome or not f.get('prefeitura_id'): return 'Selecione a prefeitura e informe o logradouro.',400
    d.execute('INSERT INTO logradouros(prefeitura_id,bairro_id,nome,tipo,cep,distrito,origem,observacao) VALUES(?,?,?,?,?,?,?,?)',
      (f['prefeitura_id'],f.get('bairro_id') or None,nome,f.get('tipo',''),f.get('cep',''),f.get('distrito',''),f.get('origem','manual'),f.get('observacao','')))
    d.commit(); return redirect('/cadastros#geografia')

@app.route('/geografia/excluir/<tipo>/<int:item_id>', methods=['POST'])
def geografia_excluir(tipo,item_id):
    tabela='bairros' if tipo=='bairro' else 'logradouros' if tipo=='logradouro' else None
    if not tabela: return 'Tipo inválido.',400
    db().execute(f'UPDATE {tabela} SET ativo=0 WHERE id=?',(item_id,)); db().commit()
    return redirect('/cadastros#geografia')

@app.route('/api/prefeitura/<int:pref_id>/geografia')
def api_geografia(pref_id):
    d=db()
    bairros=[dict(r) for r in d.execute('SELECT id,nome,distrito FROM bairros WHERE prefeitura_id=? AND ativo=1 ORDER BY nome',(pref_id,))]
    ruas=[dict(r) for r in d.execute('SELECT id,bairro_id,nome,tipo,cep FROM logradouros WHERE prefeitura_id=? AND ativo=1 ORDER BY nome',(pref_id,))]
    return json.dumps({'bairros':bairros,'logradouros':ruas},ensure_ascii=False)



@app.route('/instituicao/vincular-cartorio', methods=['POST'])
def vincular_cartorio():
    f=request.form; d=db(); pref=f.get('prefeitura_id'); cart=f.get('cartorio_id')
    if not pref or not cart: return 'Selecione prefeitura e cartório.',400
    d.execute('INSERT OR IGNORE INTO prefeitura_cartorios(prefeitura_id,cartorio_id) VALUES(?,?)',(pref,cart)); d.commit()
    return redirect('/cadastros#vinculos')

@app.route('/instituicao/desvincular-cartorio', methods=['POST'])
def desvincular_cartorio():
    f=request.form; d=db(); d.execute('DELETE FROM prefeitura_cartorios WHERE prefeitura_id=? AND cartorio_id=?',(f.get('prefeitura_id'),f.get('cartorio_id'))); d.commit()
    return redirect('/cadastros#vinculos')

@app.route('/geografia/logradouro/<int:item_id>/renomear', methods=['POST'])
def logradouro_renomear(item_id):
    f=request.form; d=db(); atual=d.execute('SELECT * FROM logradouros WHERE id=? AND ativo=1',(item_id,)).fetchone(); novo=(f.get('nome') or '').strip()
    if not atual or not novo: return 'Logradouro não encontrado ou nome vazio.',400
    tipo=f.get('tipo','')
    if novo != atual['nome'] or tipo != (atual['tipo'] or ''):
        agora=datetime.datetime.now().isoformat(timespec='seconds')
        d.execute('INSERT INTO historico_logradouros(logradouro_id,nome_anterior,tipo_anterior,motivo,fonte,data_registro) VALUES(?,?,?,?,?,?)',(item_id,atual['nome'],atual['tipo'],f.get('motivo',''),f.get('fonte',''),agora))
        d.execute('UPDATE logradouros SET nome=?,tipo=?,observacao=? WHERE id=?',(novo,tipo,f.get('observacao',atual['observacao']),item_id))
        d.execute('INSERT INTO auditoria(usuario,acao,entidade,entidade_id,detalhes,data_registro) VALUES(?,?,?,?,?,?)',('admin','ALTERAÇÃO DE LOGRADOURO','logradouro',item_id,json.dumps({'nome_anterior':atual['nome'],'nome_novo':novo,'motivo':f.get('motivo','')},ensure_ascii=False),agora)); d.commit()
    return redirect('/cadastros#geografia')

@app.route('/api/logradouros')
def buscar_logradouros():
    pref=request.args.get('prefeitura_id','').strip(); termo=request.args.get('q','').strip()
    if not pref: return json.dumps({'items':[]},ensure_ascii=False)
    sql='SELECT l.id,l.nome,l.tipo,l.cep,b.nome AS bairro FROM logradouros l LEFT JOIN bairros b ON b.id=l.bairro_id WHERE l.prefeitura_id=? AND l.ativo=1'; args=[pref]
    if termo: sql+=' AND (l.nome LIKE ? OR b.nome LIKE ?)'; args += [f'%{termo}%',f'%{termo}%']
    rows=db().execute(sql+' ORDER BY l.nome LIMIT 500',args).fetchall()
    return json.dumps({'items':[dict(id=x['id'],nome=geoimport.nome_completo(x['tipo'],x['nome']),tipo=x['tipo'],cep=x['cep'],bairro=x['bairro']) for x in rows]},ensure_ascii=False)

@app.route('/api/nucleos')
def api_nucleos():
    cart=request.args.get('cartorio_id','').strip(); pref=request.args.get('prefeitura_id','').strip()
    rows=db().execute('SELECT id,nome,matricula,data_matricula FROM nucleos WHERE ativo=1 AND (?=\'\' OR cartorio_id=?) AND (?=\'\' OR prefeitura_id=? OR prefeitura_id IS NULL) ORDER BY nome',(cart,cart,pref,pref)).fetchall()
    return json.dumps([dict(x) for x in rows],ensure_ascii=False)

@app.route('/api/prefeitura/<int:pref_id>/cartorios')
def cartorios_da_prefeitura(pref_id):
    rows=db().execute("""SELECT c.id,c.nome,c.cns,c.atribuicao FROM cartorios c LEFT JOIN prefeitura_cartorios pc ON pc.cartorio_id=c.id WHERE pc.prefeitura_id=? OR c.municipio=(SELECT municipio FROM prefeituras WHERE id=?) GROUP BY c.id ORDER BY c.nome""",(pref_id,pref_id)).fetchall()
    return json.dumps([dict(x) for x in rows],ensure_ascii=False)

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    d = db()
    if d.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
        return redirect(url_for('login'))
    setup_token = os.environ.get('REURB_SETUP_TOKEN', '')
    if request.method == 'POST':
        supplied = request.form.get('token', '')
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        if not setup_token or len(setup_token) < 24 or not hmac.compare_digest(supplied, setup_token):
            aviso('Token inicial inválido ou não configurado. Configure REURB_SETUP_TOKEN com pelo menos 24 caracteres.', 'erro')
        elif not nome or '@' not in email or len(senha) < 12:
            aviso('Informe nome, e-mail válido e senha com pelo menos 12 caracteres.', 'erro')
        else:
            agora = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            try:
                cur = d.execute('INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)',
                    (nome, email, generate_password_hash(senha), agora))
                uid = cur.lastrowid
                org = d.execute("SELECT id FROM organizations WHERE slug='organizacao-principal'").fetchone()
                d.execute('INSERT INTO memberships(organization_id,user_id,role,created_at) VALUES(?,?,?,?)',
                    (org['id'], uid, 'owner', agora))
                d.execute('INSERT INTO activity_events(organization_id,user_id,event_type,details,created_at) VALUES(?,?,?,?,?)',
                    (org['id'], uid, 'owner_created', 'Primeiro proprietário da organização', agora))
                d.commit()
                session.clear(); session.permanent = True; session['user_id'] = uid
                aviso('Conta proprietária criada. A partir de agora, o acesso é individual.')
                return redirect(url_for('index'))
            except sqlite3.IntegrityError:
                d.rollback()
                aviso('Este e-mail já está cadastrado.', 'erro')
    return render_template('setup.html', token_configurado=bool(setup_token and len(setup_token) >= 24))


@app.route('/login', methods=['GET', 'POST'])
def login():
    d = db()
    total_users = d.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        user = d.execute('SELECT * FROM users WHERE email=? AND is_active=1', (email,)).fetchone() if total_users else None
        if user and check_password_hash(user['password_hash'], senha):
            member = d.execute('SELECT organization_id FROM memberships WHERE user_id=? AND is_active=1 ORDER BY id LIMIT 1', (user['id'],)).fetchone()
            if member:
                session.clear(); session.permanent = True; session['user_id'] = user['id']
                d.execute('UPDATE users SET last_login_at=? WHERE id=?',
                    (datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), user['id']))
                d.commit()
                destino = request.args.get('next', '/')
                if not destino.startswith('/') or destino.startswith('//'):
                    destino = '/'
                return redirect(destino)
        elif total_users == 0 and SENHA and hmac.compare_digest(senha, SENHA):
            session.clear(); session.permanent = True; session['legacy_ok'] = True
            return redirect(url_for('index'))
        aviso('E-mail ou senha incorretos.', 'erro')
    return render_template('login.html', primeiro_acesso=(total_users == 0))


@app.route('/sair', methods=['POST'])
def sair():
    session.clear()
    return redirect(url_for('login'))


def _is_owner():
    return bool(getattr(g, 'current_user', None) and g.current_user['role'] == 'owner')


def _require_owner():
    if not _is_owner():
        abort(403)


@app.route('/equipe', methods=['GET', 'POST'])
def equipe():
    d = db()
    org_id = g.organization_id
    if request.method == 'POST':
        action = request.form.get('action')
        agora = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
        if action == 'membro':
            _require_owner()
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip().lower()
            senha = request.form.get('senha', '')
            papel = request.form.get('role', 'engineer')
            papeis = {'engineer','field_technician','surveyor','registral_assistant','reviewer'}
            if not nome or '@' not in email or len(senha) < 12 or papel not in papeis:
                aviso('Confira nome, e-mail, função e senha (mínimo de 12 caracteres).', 'erro')
            else:
                try:
                    cur = d.execute('INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)',
                        (nome,email,generate_password_hash(senha),agora))
                    d.execute('INSERT INTO memberships(organization_id,user_id,role,created_at) VALUES(?,?,?,?)',
                        (org_id,cur.lastrowid,papel,agora))
                    d.commit()
                    aviso('Membro cadastrado. Oriente a pessoa a trocar a senha após o primeiro acesso.')
                except sqlite3.IntegrityError:
                    d.rollback(); aviso('Este e-mail já possui cadastro.', 'erro')
        elif action == 'equipe':
            _require_owner()
            nome = request.form.get('nome', '').strip()
            if nome:
                d.execute('INSERT INTO teams(organization_id,name,description,created_at) VALUES(?,?,?,?)',
                    (org_id,nome,request.form.get('description','').strip(),agora))
                d.commit(); aviso('Equipe criada.')
        elif action == 'integrante_equipe':
            _require_owner()
            try:
                team_id = int(request.form.get('team_id',''))
                member_id = int(request.form.get('user_id',''))
            except (TypeError,ValueError):
                team_id = member_id = 0
            team = d.execute('SELECT id FROM teams WHERE id=? AND organization_id=? AND is_active=1',(team_id,org_id)).fetchone()
            member = d.execute('SELECT user_id FROM memberships WHERE user_id=? AND organization_id=? AND is_active=1',(member_id,org_id)).fetchone()
            if team and member:
                d.execute('INSERT OR IGNORE INTO team_members(team_id,user_id,role,created_at) VALUES(?,?,?,?)',
                    (team_id,member_id,request.form.get('team_role','member'),agora))
                d.commit(); aviso('Integrante vinculado à equipe.')
            else:
                aviso('Equipe ou integrante inválido.', 'erro')
        elif action == 'tarefa':
            titulo = request.form.get('title','').strip()
            try: project_id = int(request.form.get('project_id',''))
            except (TypeError,ValueError): project_id = 0
            try: assignee = int(request.form.get('assigned_user_id','')) or None
            except (TypeError,ValueError): assignee = None
            project = d.execute('SELECT id FROM projetos WHERE id=? AND organization_id=?',(project_id,org_id)).fetchone()
            valid_assignee = d.execute('SELECT user_id FROM memberships WHERE user_id=? AND organization_id=? AND is_active=1',(assignee,org_id)).fetchone() if assignee else None
            if not titulo or not project or (assignee and not valid_assignee):
                aviso('Informe uma tarefa, um projeto válido e um responsável da organização.', 'erro')
            else:
                try: team_id = int(request.form.get('team_id','')) or None
            except (TypeError,ValueError): team_id = None
            valid_team = d.execute('SELECT id FROM teams WHERE id=? AND organization_id=? AND is_active=1',(team_id,org_id)).fetchone() if team_id else None
            if team_id and not valid_team:
                aviso('A equipe selecionada não pertence à organização.', 'erro')
                return redirect(url_for('equipe'))
            d.execute("""INSERT INTO tasks(organization_id,project_id,team_id,title,description,priority,
                    assigned_user_id,created_by_user_id,due_date,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (org_id,project_id,team_id,titulo,request.form.get('description','').strip(),
                     request.form.get('priority','normal') if request.form.get('priority') in ('low','normal','high','urgent') else 'normal',
                     assignee, g.current_user['id'] if g.current_user else None,
                     request.form.get('due_date') or None,agora,agora))
                d.commit(); aviso('Tarefa criada e vinculada ao projeto.')
        return redirect(url_for('equipe'))
    membros = d.execute("""SELECT u.id,u.name,u.email,m.role,m.is_active
        FROM users u JOIN memberships m ON m.user_id=u.id
        WHERE m.organization_id=? ORDER BY u.name""",(org_id,)).fetchall()
    equipes = d.execute('SELECT * FROM teams WHERE organization_id=? AND is_active=1 ORDER BY name',(org_id,)).fetchall()
    equipe_membros = d.execute('SELECT tm.team_id,u.name,u.id FROM team_members tm JOIN users u ON u.id=tm.user_id JOIN teams t ON t.id=tm.team_id WHERE t.organization_id=? ORDER BY t.name,u.name',(org_id,)).fetchall()
    projetos = d.execute('SELECT id,nome,municipio FROM projetos WHERE organization_id=? ORDER BY nome',(org_id,)).fetchall()
    tarefas = d.execute("""SELECT t.*,p.nome AS projeto_nome,u.name AS responsavel
        FROM tasks t JOIN projetos p ON p.id=t.project_id
        LEFT JOIN users u ON u.id=t.assigned_user_id
        WHERE t.organization_id=? ORDER BY CASE t.status WHEN 'blocked' THEN 0 WHEN 'review' THEN 1 WHEN 'in_progress' THEN 2 WHEN 'todo' THEN 3 ELSE 4 END,
        COALESCE(t.due_date,'9999-12-31'),t.id DESC""",(org_id,)).fetchall()
    return render_template('equipe.html', membros=membros, equipes=equipes, equipe_membros=equipe_membros, projetos=projetos, tarefas=tarefas, pode_administrar=_is_owner())


@app.route('/equipe/tarefa/<int:task_id>/status', methods=['POST'])
def tarefa_status(task_id):
    d=db(); org_id=g.organization_id
    task=d.execute('SELECT * FROM tasks WHERE id=? AND organization_id=?',(task_id,org_id)).fetchone()
    if not task: abort(404)
    if not _is_owner() and (not g.current_user or task['assigned_user_id'] != g.current_user['id']):
        abort(403)
    status=request.form.get('status')
    if status not in ('todo','in_progress','review','done','blocked'): abort(400)
    agora=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    d.execute('UPDATE tasks SET status=?,completed_at=?,updated_at=? WHERE id=? AND organization_id=?',
        (status,agora if status=='done' else None,agora,task_id,org_id))
    d.execute('INSERT INTO activity_events(organization_id,project_id,user_id,event_type,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?,?,?)',
        (org_id,task['project_id'],g.current_user['id'] if g.current_user else None,'task_status_changed','task',task_id,status,agora))
    d.commit(); return redirect(url_for('equipe'))

@app.route('/sair', methods=['POST'])
def sair():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    d=db()
    return render_template('index.html', ps=d.execute('SELECT p.*,f.nome AS prefeitura_nome,c.nome AS cartorio_nome FROM projetos p LEFT JOIN prefeituras f ON f.id=p.prefeitura_id LEFT JOIN cartorios c ON c.id=p.cartorio_id ORDER BY p.id DESC').fetchall(),
      prefeituras=d.execute('SELECT * FROM prefeituras ORDER BY nome').fetchall(),
      cartorios=d.execute('SELECT * FROM cartorios ORDER BY nome').fetchall(),
      total_prefeituras=d.execute('SELECT COUNT(*) FROM prefeituras').fetchone()[0], total_cartorios=d.execute('SELECT COUNT(*) FROM cartorios').fetchone()[0],
      total_bairros=d.execute('SELECT COUNT(*) FROM bairros WHERE ativo=1').fetchone()[0], total_logradouros=d.execute('SELECT COUNT(*) FROM logradouros WHERE ativo=1').fetchone()[0])

def texto_nucleo(n, cart):
    if not n['matricula']: return ''
    t = f"Matrícula nº {n['matricula']}"
    if n['data_matricula']: t += f", aberta em {_databr(n['data_matricula'])}"
    if cart: t += f", da serventia {cart['nome']}" + (f" (CNS {cart['cns']})" if cart['cns'] else '')
    return t

def campos_nucleo(d, nid):
    n = d.execute('SELECT * FROM nucleos WHERE id=?', (nid,)).fetchone()
    if not n: return {}
    cart = d.execute('SELECT nome,cns FROM cartorios WHERE id=?', (n['cartorio_id'],)).fetchone() if n['cartorio_id'] else None
    out = {'nucleo_id': n['id'], 'comunidade': n['nome'], 'nucleo': n['nome']}
    t = texto_nucleo(n, cart)
    if t: out['nucleo_origem'] = t
    return out

@app.route('/novo', methods=['POST'])
def novo():
    f = request.form; d = dict(zona='24', modalidade='REURB-S', status='Em planejamento', data=datetime.date.today().strftime('%d/%m/%Y'))
    d.update({k: f.get(k, '') for k in PROJ if f.get(k) is not None and f.get(k) != ''})
    if d.get('prefeitura_id'):
        pref=db().execute('SELECT * FROM prefeituras WHERE id=?',(d['prefeitura_id'],)).fetchone()
        if pref:
            d['municipio']=pref['municipio'] or pref['nome']
            for k,v in [('prefeitura_cnpj',pref['cnpj']),('prefeitura_end',pref['endereco']),('prefeito_nome',pref['prefeito']),('lei_municipal',pref['lei_reurb'])]:
                if v and not d.get(k): d[k]=v
    if d.get('nucleo_id'): d.update(campos_nucleo(db(), d['nucleo_id']))
    c = db().execute(f"INSERT INTO projetos({','.join(d)}) VALUES({','.join('?'*len(d))})", list(d.values()))
    db().commit(); return redirect(f'/p/{c.lastrowid}')

def carregar(pid):
    d = db(); p = d.execute('SELECT * FROM projetos WHERE id=?', (pid,)).fetchone()
    vs = [dict(r) for r in d.execute('SELECT * FROM vertices WHERE proj_id=? ORDER BY ordem', (pid,))]
    ps = [dict(r) for r in d.execute('SELECT * FROM pessoas WHERE proj_id=? ORDER BY id', (pid,))]
    return dict(p), vs, ps

@app.route('/brasao', methods=['POST'])
def brasao():
    from PIL import Image
    f = request.files.get('arq')
    if f and f.filename: Image.open(f).convert('RGBA').save(BRASAO, 'PNG')
    return redirect('/')

def _cobertura_avisos(vs, ps):
    n = len(vs); nomes = [v['nome'] for v in vs]; cont = {}; av = []
    confs = [q for q in ps if q['tipo'] == 'confrontante']
    if not confs:
        return ['Nenhum confrontante cadastrado ainda.']
    for q in confs:
        a, b = q.get('v_ini'), q.get('v_fim'); rot = q.get('nome') or ('matrícula ' + (q.get('matricula') or '?'))
        if a not in nomes or b not in nomes:
            av.append(f'Confrontante “{rot}” sem trecho definido (vértice inicial/final).'); continue
        if a == b:
            av.append(f'Confrontante “{rot}”: vértice inicial e final são iguais ({a}).'); continue
        k = nomes.index(a); fim = nomes.index(b)
        while k != fim:
            cont.setdefault(k, []).append(rot); k = (k+1) % n
    sem = [f"{nomes[k]}→{nomes[(k+1) % n]}" for k in range(n) if k not in cont]
    dup = [f"{nomes[k]}→{nomes[(k+1) % n]}" for k, l in cont.items() if len(l) > 1]
    if sem: av.append('Lados sem confrontante: ' + ', '.join(sem) + '.')
    if dup: av.append('Lados cobertos por mais de um confrontante: ' + ', '.join(dup) + '.')
    return av

@app.route('/p/<int:pid>')
def projeto(pid):
    p, vs, ps = carregar(pid); extra = {}; d = db()
    if len(vs) >= 3:
        extra = docs.resumo(int(p['zona']), vs); extra['avisos'] = geo.validar(int(p['zona']), vs)
        for k, v, lb in [('area_informada', extra['area'], 'Área informada'), ('perimetro_informado', extra['perimetro'], 'Perímetro informado')]:
            inf = pecas._num(p.get(k) or '')
            if inf and abs(inf-v)/inf > .005:
                extra['avisos'].append(f"{lb} ({inf:.2f}) difere do valor calculado pelas coordenadas ({v:.2f}). Os documentos usam o valor calculado das coordenadas — confira o levantamento.")
        extra['avisos'] += _cobertura_avisos(vs, ps)
        if not any(q['tipo'] in ('ocupante', 'beneficiario') for q in ps): extra['avisos'].append('Nenhum ocupante/beneficiário cadastrado.')
        extra['orient'] = geo.orientacao(vs)
        extra['foto'] = os.path.exists(os.path.join(UP, f'fachada_{pid}.jpg'))
    pid_pref, pid_cart = p.get('prefeitura_id'), p.get('cartorio_id')
    pref = d.execute('SELECT nome FROM prefeituras WHERE id=?', (pid_pref,)).fetchone() if pid_pref else None
    cart = d.execute('SELECT nome,cns FROM cartorios WHERE id=?', (pid_cart,)).fetchone() if pid_cart else None
    ruas, bairros = [], []
    if pid_pref:
        ruas = sorted([dict(nome=geoimport.nome_completo(r['tipo'], r['nome']), bairro=r['bairro'] or '', cep=r['cep'] or '') for r in d.execute('SELECT l.tipo,l.nome,l.cep,b.nome AS bairro FROM logradouros l LEFT JOIN bairros b ON b.id=l.bairro_id WHERE l.prefeitura_id=? AND l.ativo=1', (pid_pref,))], key=lambda r: geoimport.norm(r['nome']))
        bairros = [r['nome'] for r in d.execute('SELECT nome FROM bairros WHERE prefeitura_id=? AND ativo=1 ORDER BY nome', (pid_pref,))]
    nucleos = d.execute('SELECT * FROM nucleos WHERE ativo=1 AND (id=? OR cartorio_id=? OR prefeitura_id=?) ORDER BY nome', (p.get('nucleo_id') or 0, pid_cart or 0, pid_pref or 0)).fetchall()
    return render_template('projeto.html', p=p, prefeitura=pref, cartorio=cart, vs=vs, ps=ps, x=extra, ruas=ruas, bairros=bairros, nucleos=nucleos, modos=geo.MODOS_INICIO,
      foto=os.path.exists(os.path.join(UP, f'fachada_{pid}.jpg')), drone=os.path.exists(os.path.join(UP, f'drone_{pid}.jpg')), marcado=os.path.exists(os.path.join(UP, f'drone_marcado_{pid}.jpg')), plantas={k: next((f'/p/{pid}/arquivo-planta/{k}{e}' for e in ('.pdf','.png','.jpg','.jpeg','.webp') if os.path.exists(os.path.join(UP,f'planta_{pid}_{k}{e}'))), None) for k in ('terreo','primeiro','segundo','terceiro')})

@app.route('/p/<int:pid>/salvar', methods=['POST'])
def salvar(pid):
    d = db(); upd = {k: request.form[k] for k in PROJ if k in request.form}
    if 'nucleo_id' in upd:
        atual = d.execute('SELECT nucleo_id FROM projetos WHERE id=?', (pid,)).fetchone()
        if upd['nucleo_id'] and str(atual['nucleo_id'] or '') != upd['nucleo_id']: upd.update(campos_nucleo(d, upd['nucleo_id']))
        upd['nucleo_id'] = upd['nucleo_id'] or None
    if upd: d.execute(f"UPDATE projetos SET {','.join(k+'=?' for k in upd)} WHERE id=?", list(upd.values())+[pid]); d.commit(); aviso('Dados salvos.')
    return redirect(f'/p/{pid}' + ('#' + request.form['_ancora'] if request.form.get('_ancora') else ''))

def _grava_vertices(d, pid, novos):
    antigos = {r['nome']: r['distancia_manual'] for r in d.execute('SELECT nome,distancia_manual FROM vertices WHERE proj_id=?', (pid,))}
    d.execute('DELETE FROM vertices WHERE proj_id=?', (pid,))
    d.executemany('INSERT INTO vertices(proj_id,ordem,nome,e,n,distancia_manual) VALUES(?,?,?,?,?,?)', [(pid, i, a, b, c, antigos.get(a)) for i, (a, b, c) in enumerate(novos)])

@app.route('/p/<int:pid>/coords', methods=['POST'])
def coords(pid):
    txt = request.form.get('txt', ''); pref = (request.form.get('prefixo') or 'V').strip() or 'V'; zona = None; kml = False
    f = request.files.get('arq')
    if f and f.filename:
        raw = f.read()
        if f.filename.lower().endswith(('.kml', '.kmz')) or b'<kml' in raw[:500]:
            zona, novos = geo.parse_kml(raw, pref); kml = True
        else: novos = geo.parse_utm(raw.decode('utf-8', 'ignore'), pref)
    else: novos = geo.parse_utm(txt, pref)
    if not novos:
        aviso('Nenhum vértice reconhecido no arquivo/texto. Confira o formato (nome, E, N em UTM, ou KML com polígono).', 'erro'); return redirect(f'/p/{pid}#coords')
    ini, sent = request.form.get('inicio_kml', 'sudoeste'), request.form.get('sentido_kml', 'manter')
    if kml and not (ini == 'primeiro' and sent == 'manter'):
        novos, _, _ = geo.reorganizar(novos, ini, sent, pref, not request.form.get('manter_nomes'))
    d = db()
    if zona: d.execute('UPDATE projetos SET zona=? WHERE id=?', (str(zona), pid))
    _grava_vertices(d, pid, novos); d.commit()
    aviso(f'{len(novos)} vértices importados — começam em {novos[0][0]}, sentido {geo.orientacao(novos).replace("anti", "anti-")}.')
    return redirect(f'/p/{pid}#coords')

@app.route('/p/<int:pid>/vertices/distancias', methods=['POST'])
def vertices_distancias(pid):
    d=db(); vs=d.execute('SELECT id,nome FROM vertices WHERE proj_id=? ORDER BY ordem',(pid,)).fetchall()
    for v in vs:
        raw=(request.form.get('dist_'+str(v['id'])) or '').strip().replace(',','.')
        try: val=float(raw) if raw else None
        except ValueError: val=None
        if val is not None and val<=0: val=None
        d.execute('UPDATE vertices SET distancia_manual=? WHERE id=? AND proj_id=?',(val,v['id'],pid))
    d.commit(); aviso('Distâncias manuais atualizadas. Elas substituem apenas a distância do trecho correspondente; as coordenadas e a área permanecem inalteradas.')
    return redirect(f'/p/{pid}#coords')

@app.route('/p/<int:pid>/vertices/reordenar', methods=['POST'])
def vertices_reordenar(pid):
    d = db(); vs = [dict(r) for r in d.execute('SELECT * FROM vertices WHERE proj_id=? ORDER BY ordem', (pid,))]
    if len(vs) < 3: aviso('Importe os vértices primeiro.', 'erro'); return redirect(f'/p/{pid}#coords')
    f = request.form; pref = (f.get('prefixo') or 'V').strip() or 'V'
    novos, mapa, inv = geo.reorganizar([(v['nome'], v['e'], v['n']) for v in vs], f.get('inicio', 'primeiro'), f.get('sentido', 'manter'), pref, not f.get('manter_nomes'))
    _grava_vertices(d, pid, novos)
    for q in d.execute("SELECT id,v_ini,v_fim FROM pessoas WHERE proj_id=? AND tipo='confrontante'", (pid,)).fetchall():
        a, b = mapa.get(q['v_ini'], q['v_ini']), mapa.get(q['v_fim'], q['v_fim'])
        if inv: a, b = b, a
        d.execute('UPDATE pessoas SET v_ini=?,v_fim=? WHERE id=?', (a, b, q['id']))
    d.commit(); aviso(f'Vértices reorganizados: {novos[0][0]} é o novo ponto inicial; sentido {geo.orientacao(novos).replace("anti", "anti-")}. Os trechos dos confrontantes foram ajustados.')
    return redirect(f'/p/{pid}#coords')

# ---------- pessoas do projeto + cadastro reutilizável ----------
def upsert_cadastro(d, dados, cid=None, mesclar=True):
    vals = {k: (dados.get(k) or '').strip() for k in CAD}
    if not vals['nome']: return None
    agora = datetime.datetime.now().isoformat(timespec='seconds')
    if not cid and vals['cpf']:
        dig = re.sub(r'\D', '', vals['cpf'])
        if dig:
            for r in d.execute("SELECT id,cpf FROM cadastro_pessoas WHERE cpf!=''"):
                if re.sub(r'\D', '', r['cpf']) == dig: cid = r['id']; break
    if cid:
        ks = [k for k in CAD if (vals[k] or not mesclar)]
        d.execute(f"UPDATE cadastro_pessoas SET {','.join(k+'=?' for k in ks)},atualizado_em=? WHERE id=?", [vals[k] for k in ks]+[agora, cid])
        return int(cid)
    c = d.execute(f"INSERT INTO cadastro_pessoas({','.join(CAD)},criado_em,atualizado_em) VALUES({','.join('?'*len(CAD))},?,?)", [vals[k] for k in CAD]+[agora, agora])
    return c.lastrowid

@app.route('/p/<int:pid>/pessoa', methods=['POST'])
def pessoa(pid):
    f = request.form; d = db(); tipo = f.get('tipo', '')
    volta = f'/p/{pid}#pessoas'
    if tipo not in ('ocupante', 'beneficiario', 'confrontante'): aviso('Escolha o tipo de cadastro.', 'erro'); return redirect(volta)
    dados = {k: f.get(k, '').strip() for k in PCAMPOS}
    nat = ''
    if tipo == 'confrontante':
        nat = dados['tipo_confrontante'] = dados.get('tipo_confrontante') or 'pessoa'
        if nat == 'pessoa' and not dados['nome']: aviso('Informe o nome do confrontante (pessoa física ou jurídica).', 'erro'); return redirect(volta)
        if nat == 'via':
            if not dados['nome']: aviso('Informe o nome da rua ou via pública.', 'erro'); return redirect(volta)
            for k in ('cpf', 'matricula', 'cns', 'inscricao', 'descricao'): dados[k] = ''
        if nat == 'matricula':
            if not dados['matricula'] or not dados['cns']: aviso('Para confrontante por matrícula, informe o número da matrícula e o CNS da serventia.', 'erro'); return redirect(volta)
            for k in ('nome', 'cpf', 'inscricao', 'descricao', 'rg', 'endereco'): dados[k] = ''
    else:
        dados['tipo_confrontante'] = ''
        if not dados['nome']: aviso('Informe o nome completo.', 'erro'); return redirect(volta)
    if (tipo != 'confrontante' or nat == 'pessoa') and f.get('salvar_cadastro'):
        cid = upsert_cadastro(d, dados, int(dados['cadastro_id']) if dados.get('cadastro_id', '').isdigit() else None)
        dados['cadastro_id'] = str(cid) if cid else ''
    vals = [dados.get(k, '') for k in PCAMPOS]
    if f.get('id'):
        d.execute(f"UPDATE pessoas SET tipo=?,{','.join(k+'=?' for k in PCAMPOS)} WHERE id=? AND proj_id=?", [tipo]+vals+[f['id'], pid])
    else:
        d.execute(f"INSERT INTO pessoas(proj_id,tipo,{','.join(PCAMPOS)}) VALUES(?,?,{','.join('?'*len(PCAMPOS))})", [pid, tipo]+vals)
    d.commit(); aviso(f"Cadastro salvo: {dados['nome'] or 'matrícula ' + dados['matricula']}.")
    return redirect(volta)

@app.route('/p/<int:pid>/del/<int:id>', methods=['POST'])
def delpessoa(pid, id):
    db().execute('DELETE FROM pessoas WHERE id=? AND proj_id=?', (id, pid)); db().commit(); aviso('Cadastro removido do projeto.'); return redirect(f'/p/{pid}#pessoas')

@app.route('/p/<int:pid>/pessoa/<int:id>/sincronizar', methods=['POST'])
def pessoa_sincronizar(pid, id):
    d = db(); q = d.execute('SELECT cadastro_id FROM pessoas WHERE id=? AND proj_id=?', (id, pid)).fetchone()
    c = d.execute('SELECT * FROM cadastro_pessoas WHERE id=?', (q['cadastro_id'] or 0,)).fetchone() if q else None
    if not c: aviso('Esta pessoa não está vinculada ao cadastro de pessoas.', 'erro'); return redirect(f'/p/{pid}#pessoas')
    d.execute(f"UPDATE pessoas SET {','.join(k+'=?' for k in CAD)} WHERE id=?", [c[k] or '' for k in CAD]+[id]); d.commit()
    aviso('Dados atualizados a partir do cadastro de pessoas.'); return redirect(f'/p/{pid}#pessoas')

@app.route('/p/<int:pid>/excluir', methods=['POST'])
def projeto_excluir(pid):
    d = db()
    for t in ('vertices', 'pessoas'): d.execute(f'DELETE FROM {t} WHERE proj_id=?', (pid,))
    d.execute('DELETE FROM projetos WHERE id=?', (pid,)); d.commit()
    for n in (f'fachada_{pid}.jpg', f'drone_{pid}.jpg', f'drone_marcado_{pid}.jpg'):
        q = os.path.join(UP, n)
        if os.path.exists(q): os.remove(q)
    aviso('Projeto excluído.'); return redirect('/')

@app.route('/p/<int:pid>/mapa.json')
def mapa(pid):
    p, vs, ps = carregar(pid); z = int(p['zona'])
    ll = [geo.to_latlon(z, v['e'], v['n']) for v in vs]
    return json.dumps(dict(poly=ll, nomes=[v['nome'] for v in vs],
        pessoas=[dict(nome=q['nome'], tipo=q['tipo'], lat=q['lat'], lon=q['lon']) for q in ps if q['lat'] and q['lon']]))

@app.route('/p/<int:pid>/drone', methods=['POST'])
def drone(pid):
    from PIL import Image
    f = request.files.get('arq')
    if f and f.filename:
        im = Image.open(f).convert('RGB'); im.thumbnail((3000, 3000)); im.save(os.path.join(UP, f'drone_{pid}.jpg'), 'JPEG', quality=88)
        mk = os.path.join(UP, f'drone_marcado_{pid}.jpg')
        if os.path.exists(mk): os.remove(mk)
    return redirect(f'/p/{pid}#drone')

@app.route('/p/<int:pid>/drone/marcar', methods=['POST'])
def drone_marcar(pid):
    import base64
    d = request.form.get('img', '')
    if d.startswith('data:image'):
        open(os.path.join(UP, f'drone_marcado_{pid}.jpg'), 'wb').write(base64.b64decode(d.split(',', 1)[1]))
    return redirect(f'/p/{pid}#drone')

@app.route('/p/<int:pid>/drone.jpg')
def drone_img(pid):
    mk = os.path.join(UP, f'drone_marcado_{pid}.jpg'); p = os.path.join(UP, f'drone_{pid}.jpg')
    q = p if request.args.get('orig') else (mk if os.path.exists(mk) else p)
    return send_file(q) if os.path.exists(q) else ('', 404)

@app.route('/p/<int:pid>/drone/excluir')
def drone_del(pid):
    for n in (f'drone_{pid}.jpg', f'drone_marcado_{pid}.jpg'):
        q = os.path.join(UP, n)
        if os.path.exists(q): os.remove(q)
    return redirect(f'/p/{pid}#drone')

@app.route('/p/<int:pid>/planta/<pavimento>', methods=['POST'])
def planta_upload(pid,pavimento):
    permitidos={'terreo':'Térreo','primeiro':'1º pavimento','segundo':'2º pavimento','terceiro':'3º pavimento'}
    if pavimento not in permitidos: return ('Pavimento inválido',404)
    f=request.files.get('arq')
    if not f or not f.filename: aviso('Selecione um arquivo de planta baixa.','erro'); return redirect(f'/p/{pid}#plantas')
    ext=os.path.splitext(f.filename)[1].lower()
    if ext not in ('.pdf','.png','.jpg','.jpeg','.webp'): aviso('Formato permitido: PDF, PNG, JPG ou WEBP.','erro'); return redirect(f'/p/{pid}#plantas')
    f.save(os.path.join(UP,f'planta_{pid}_{pavimento}{ext}'))
    # remove versão anterior em outra extensão
    for e in ('.pdf','.png','.jpg','.jpeg','.webp'):
        q=os.path.join(UP,f'planta_{pid}_{pavimento}{e}')
        if e!=ext and os.path.exists(q): os.remove(q)
    aviso(f'Planta do {permitidos[pavimento]} anexada.'); return redirect(f'/p/{pid}#plantas')

@app.route('/p/<int:pid>/fachada', methods=['POST'])
def fachada(pid):
    from PIL import Image, ImageOps
    f = request.files.get('arq')
    if f and f.filename:
        im = ImageOps.exif_transpose(Image.open(f)).convert('RGB'); im.thumbnail((1800, 1800))
        im.save(os.path.join(UP, f'fachada_{pid}.jpg'), 'JPEG', quality=85)
    return redirect(f'/p/{pid}#fachada')

@app.route('/p/<int:pid>/arquivo-planta/<pavimento>')
def planta_arquivo(pid,pavimento):
    if pavimento not in ('terreo','primeiro','segundo','terceiro'): return ('',404)
    for e in ('.pdf','.png','.jpg','.jpeg','.webp'):
        q=os.path.join(UP,f'planta_{pid}_{pavimento}{e}')
        if os.path.exists(q): return send_file(q,as_attachment=False)
    return ('',404)

@app.route('/p/<int:pid>/fachada.jpg')
def fachada_img(pid):
    p = os.path.join(UP, f'fachada_{pid}.jpg')
    return send_file(os.path.abspath(p)) if os.path.exists(p) else ('', 404)

@app.route('/p/<int:pid>/fachada/excluir')
def fachada_del(pid):
    p = os.path.join(UP, f'fachada_{pid}.jpg')
    if os.path.exists(p): os.remove(p)
    return redirect(f'/p/{pid}#fachada')

@app.route('/config', methods=['POST'])
def config():
    from PIL import Image
    f = request.files.get('assinatura')
    if f and f.filename: Image.open(f).convert('RGBA').save(os.path.join(CFG, 'assinatura.png'), 'PNG')
    f = request.files.get('papel')
    if f and f.filename: f.save(os.path.join(CFG, 'papel_timbrado.docx'))
    return redirect('/')

def _drone(pid):
    for n in (f'drone_marcado_{pid}.jpg', f'drone_{pid}.jpg'):
        q = os.path.join(UP, n)
        if os.path.exists(q): return q
    return None

def gerar(pid, what, base='satelite'):
    p, vs, ps = carregar(pid); p['zona'] = int(p['zona'])
    if len(vs) < 3: raise ValueError('Importe ao menos 3 vértices.')
    nome = pecas.nome_arquivo(ps, p); fp = os.path.join(UP, f'fachada_{pid}.jpg')
    foto = open(fp, 'rb').read() if os.path.exists(fp) else None; papel, assin = cfg('papel_timbrado.docx'), cfg('assinatura.png')
    if what == 'memorial_planimetrico': return pecas.memorial_planimetrico(p, vs, ps, foto, papel, assin), f'MEMORIAL_DESCRITIVO_LEVANTAMENTO_PLANIMETRICO_{nome}.docx'
    if what == 'memorial_imovel': return pecas.memorial_imovel(p, vs, ps, papel, assin), f'MEMORIAL_DE_IMOVEL_DETALHADO_{nome}.docx'
    if what == 'req_averbacao': return pecas.req_averbacao(p, vs, ps), f'REQUERIMENTO_DE_AVERBACAO_DE_CONSTRUCAO_{nome}.docx'
    if what == 'req_reurb': return pecas.req_reurb(p, vs, ps), f'REQUERIMENTO_REURB_E_VALOR_REAL_{nome}.docx'
    if what == 'crf': return crf.crf_docx(p, vs, ps, BRASAO if os.path.exists(BRASAO) else cfg('brasao.png'), foto), f'CRF_{nome}.docx'
    if what == 'planta': return docs.planta_pdf(p, vs, ps, base, _drone(pid)), f'PLANTA_{nome}.pdf'
    if what == 'kml': return docs.kml(p, vs), f'{nome}.kml'
    raise ValueError('documento desconhecido')

@app.route('/p/<int:pid>/baixar/<what>')
def baixar(pid, what):
    try:
        if what == 'tudo':
            b = io.BytesIO()
            with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
                for w in ['memorial_planimetrico', 'memorial_imovel', 'req_averbacao', 'req_reurb', 'crf', 'planta', 'kml']:
                    data, fn = gerar(pid, w); z.writestr(fn, data)
            b.seek(0); return send_file(b, as_attachment=True, download_name=f'REURB_{pid}_documentos.zip')
        data, fn = gerar(pid, what, request.args.get('base', 'satelite'))
    except ValueError as e:
        return str(e), 400
    return send_file(io.BytesIO(data), as_attachment=True, download_name=fn)

# ---------- cadastro de pessoas (reutilizável entre projetos) ----------
@app.route('/pessoas')
def pessoas_lista():
    q = request.args.get('q', '').strip(); d = db()
    sql = 'SELECT c.*,(SELECT COUNT(*) FROM pessoas p WHERE p.cadastro_id=c.id) AS usos FROM cadastro_pessoas c'; args = []
    if q: sql += ' WHERE c.nome LIKE ? OR c.cpf LIKE ? OR c.inscricao LIKE ?'; args = [f'%{q}%'] * 3
    rows = d.execute(sql + ' ORDER BY c.nome LIMIT 500', args).fetchall()
    return render_template('pessoas.html', rows=rows, q=q, total=d.execute('SELECT COUNT(*) FROM cadastro_pessoas').fetchone()[0])

@app.route('/pessoas/salvar', methods=['POST'])
def pessoas_salvar():
    f = request.form; cid = int(f['id']) if f.get('id', '').isdigit() else None
    if not f.get('nome', '').strip(): aviso('Informe o nome.', 'erro'); return redirect('/pessoas')
    upsert_cadastro(db(), f, cid, mesclar=False); db().commit(); aviso('Pessoa salva no cadastro.'); return redirect('/pessoas')

@app.route('/pessoas/<int:cid>/excluir', methods=['POST'])
def pessoas_excluir(cid):
    d = db(); d.execute('DELETE FROM cadastro_pessoas WHERE id=?', (cid,)); d.execute("UPDATE pessoas SET cadastro_id='' WHERE cadastro_id=?", (str(cid),)); d.commit()
    aviso('Pessoa removida do cadastro (os projetos já feitos mantêm os dados copiados).'); return redirect('/pessoas')

@app.route('/api/pessoas')
def api_pessoas():
    q = request.args.get('q', '').strip()
    if len(q) < 2: return json.dumps([])
    rows = db().execute('SELECT * FROM cadastro_pessoas WHERE nome LIKE ? OR cpf LIKE ? OR inscricao LIKE ? ORDER BY nome LIMIT 15', [f'%{q}%'] * 3).fetchall()
    return json.dumps([dict(r) for r in rows], ensure_ascii=False)

# ---------- núcleos da serventia ----------
@app.route('/nucleo/salvar', methods=['POST'])
def nucleo_salvar():
    f = request.form; d = db(); campos = ['cartorio_id', 'prefeitura_id', 'nome', 'matricula', 'data_matricula', 'observacao']
    vals = [(f.get(k, '').strip() or None) for k in campos]
    if not vals[2]: aviso('Informe o nome do núcleo.', 'erro'); return redirect('/cadastros#nucleos')
    if not vals[0]: aviso('Selecione a serventia do núcleo.', 'erro'); return redirect('/cadastros#nucleos')
    if f.get('id'): d.execute('UPDATE nucleos SET ' + ','.join(k+'=?' for k in campos) + ' WHERE id=?', vals+[f['id']])
    else: d.execute('INSERT INTO nucleos(' + ','.join(campos) + ',criado_em) VALUES(' + ','.join('?' for _ in campos) + ',?)', vals+[datetime.datetime.now().isoformat(timespec='seconds')])
    d.commit(); aviso('Núcleo salvo.'); return redirect('/cadastros#nucleos')

@app.route('/nucleo/<int:nid>/excluir', methods=['POST'])
def nucleo_excluir(nid):
    db().execute('UPDATE nucleos SET ativo=0 WHERE id=?', (nid,)); db().commit(); aviso('Núcleo removido da lista (projetos existentes mantêm os dados).'); return redirect('/cadastros#nucleos')

# ---------- importação de ruas e localidades do município ----------
def _bairro_id(d, pref, nome, origem='manual'):
    if not nome: return None
    for r in d.execute('SELECT id,nome FROM bairros WHERE prefeitura_id=? AND ativo=1', (pref,)):
        if geoimport.norm(r['nome']) == geoimport.norm(nome): return r['id']
    return d.execute('INSERT INTO bairros(prefeitura_id,nome,origem) VALUES(?,?,?)', (pref, nome, origem)).lastrowid

def _add_ruas(d, pref, itens, origem):
    ja = {geoimport.norm(geoimport.nome_completo(r['tipo'], r['nome'])) for r in d.execute('SELECT tipo,nome FROM logradouros WHERE prefeitura_id=? AND ativo=1', (pref,))}
    novos = 0
    for nome, bairro, cep in itens:
        if not nome or geoimport.norm(nome) in ja: continue
        tipo, resto = geoimport.separa_tipo(nome); ja.add(geoimport.norm(nome))
        d.execute('INSERT INTO logradouros(prefeitura_id,bairro_id,nome,tipo,cep,origem) VALUES(?,?,?,?,?,?)', (pref, _bairro_id(d, pref, bairro, origem), resto, tipo, cep, origem)); novos += 1
    return novos, len(itens)-novos

@app.route('/geografia/importar', methods=['POST'])
def geografia_importar():
    f = request.form; d = db(); pid = f.get('prefeitura_id'); fonte = f.get('fonte', 'osm'); volta = f.get('volta') or '/cadastros#geografia'
    pref = d.execute('SELECT * FROM prefeituras WHERE id=?', (pid,)).fetchone() if pid else None
    if not pref: aviso('Selecione a prefeitura (município do projeto).', 'erro'); return redirect(volta)
    try:
        if fonte == 'lista':
            novos, ign = _add_ruas(d, pid, geoimport.parse_lista(f.get('lista', '')), 'lista')
            aviso(f'{novos} ruas adicionadas; {ign} já existiam ou vieram vazias.')
        else:
            cod = pref['ibge_codigo'] or geoimport.codigo_municipio(pref['municipio'] or pref['nome'], pref['uf'] or 'BA')
            if not cod: raise RuntimeError('município não encontrado no IBGE — confira o nome/UF da prefeitura')
            if not pref['ibge_codigo']: d.execute('UPDATE prefeituras SET ibge_codigo=? WHERE id=?', (cod, pid))
            if fonte == 'ibge':
                n = 0
                for nome, ibge_id, tipo in geoimport.divisoes(cod):
                    if _bairro_id(d, pid, nome, 'ibge') and not d.execute('SELECT 1 FROM bairros WHERE prefeitura_id=? AND ibge_codigo=?', (pid, ibge_id)).fetchone():
                        d.execute('UPDATE bairros SET ibge_codigo=?,distrito=COALESCE(NULLIF(distrito,\'\'),?) WHERE prefeitura_id=? AND nome=? AND (ibge_codigo IS NULL OR ibge_codigo=\'\')', (ibge_id, tipo, pid, nome)); n += 1
                aviso(f'{n} localidades (distritos/subdistritos) do IBGE incluídas na base territorial.')
            else:
                nomes = geoimport.ruas_osm(cod)
                if not nomes: raise RuntimeError(f'o OpenStreetMap não retornou ruas para o código IBGE {cod}; use a opção de colar a lista da Prefeitura')
                novos, ign = _add_ruas(d, pid, [(n, '', '') for n in nomes], 'openstreetmap')
                aviso(f'{novos} ruas importadas do OpenStreetMap (município {cod}); {ign} já existiam. Confira com a Prefeitura.')
        d.commit()
    except Exception as e:
        aviso(f'Não foi possível importar: {e}', 'erro')
    return redirect(volta)

@app.route('/geografia/limpar-importadas', methods=['POST'])
def geografia_limpar():
    db().execute("UPDATE logradouros SET ativo=0 WHERE prefeitura_id=? AND origem IN ('openstreetmap','lista')", (request.form.get('prefeitura_id'),)); db().commit()
    aviso('Ruas importadas removidas da lista (ruas cadastradas manualmente foram mantidas).'); return redirect('/cadastros#geografia')

@app.route('/backup')
def backup():
    db().commit(); return send_file(os.path.abspath(DB), as_attachment=True, download_name='reurb_backup_' + datetime.date.today().isoformat() + '.db')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
