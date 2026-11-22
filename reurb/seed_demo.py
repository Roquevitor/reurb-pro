"""Insere um conjunto demonstrativo inteiramente fictício no banco configurado.
Execute uma única vez: python seed_demo.py
"""
from app import app, db, PROJ, PCAMPOS

with app.app_context():
    d = db()
    if d.execute('SELECT COUNT(*) FROM projetos').fetchone()[0]:
        raise SystemExit('O banco já contém projetos. Seed cancelado para evitar misturar dados.')

    prefeitura_id = d.execute(
        "INSERT INTO prefeituras(nome, uf, municipio, ibge_codigo) VALUES(?,?,?,?)",
        ('Prefeitura Demonstrativa', 'BA', 'Município Fictício', '0000000')
    ).lastrowid
    cartorio_id = d.execute(
        "INSERT INTO cartorios(nome, cns, atribuicao, municipio) VALUES(?,?,?,?)",
        ('Serventia Demonstrativa de Registro de Imóveis', '000000', 'Registro de Imóveis', 'Município Fictício')
    ).lastrowid

    projeto = {k: '' for k in PROJ}
    projeto.update({
        'prefeitura_id': prefeitura_id,
        'cartorio_id': cartorio_id,
        'status': 'Em demonstração',
        'nome': 'DEMO — Núcleo Jardim das Amostras',
        'municipio': 'Município Fictício',
        'comunidade': 'Núcleo Jardim das Amostras',
        'quadra': 'A', 'lote': '01', 'zona': '24',
        'modalidade': 'REURB-S', 'processo': 'DEMO-0001/2026',
        'requerente': 'Associação Fictícia de Moradores',
        'data': '22/11/2026',
    })
    cols = list(projeto)
    pid = d.execute(
        f"INSERT INTO projetos({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
        [projeto[k] for k in cols]
    ).lastrowid

    # Polígono retangular de exemplo em UTM, fuso 24S. Coordenadas exclusivamente fictícias.
    vertices = [
        ('V1', 320000.00000, 8380000.00000),
        ('V2', 320030.00000, 8380000.00000),
        ('V3', 320030.00000, 8380020.00000),
        ('V4', 320000.00000, 8380020.00000),
    ]
    d.executemany(
        'INSERT INTO vertices(proj_id,ordem,nome,e,n) VALUES(?,?,?,?,?)',
        [(pid, i, name, east, north) for i, (name, east, north) in enumerate(vertices)]
    )

    def add_person(tipo, **values):
        row = {k: '' for k in PCAMPOS}
        row.update(values)
        cols = ['proj_id', 'tipo'] + list(row)
        vals = [pid, tipo] + [row[k] for k in row]
        d.execute(f"INSERT INTO pessoas({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", vals)

    add_person('beneficiario', nome='Maria Exemplo (DADO FICTÍCIO)', profissao='Profissão demonstrativa', estado_civil='Solteira')
    add_person('confrontante', nome='Rua de Demonstração', tipo_confrontante='via', v_ini='V1', v_fim='V2')
    add_person('confrontante', nome='Área Verde Fictícia', tipo_confrontante='pessoa', v_ini='V2', v_fim='V3')
    add_person('confrontante', matricula='0000', cns='000000', tipo_confrontante='matricula', v_ini='V3', v_fim='V4')
    add_person('confrontante', nome='Travessa de Demonstração', tipo_confrontante='via', v_ini='V4', v_fim='V1')
    d.commit()
    print(f'Projeto fictício criado: ID {pid}. Não contém dados pessoais reais.')
