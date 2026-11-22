# REURB Pro

Sistema web de apoio à organização de projetos de Regularização Fundiária Urbana (REURB). A aplicação reúne cadastro de projetos, beneficiários, imóveis, importação de coordenadas/KML, confrontantes, plantas e geração de documentos técnicos.

> **Estado do projeto:** versão de demonstração/colaboração. Não utilizar para instruir procedimentos reais sem validação técnica, jurídica, de segurança e de conformidade pela instituição responsável.

## Demonstração hospedada

O endereço público será informado após a criação do serviço no Render. O código-fonte é público; a aplicação online exige senha. Após o primeiro deploy, se quiser apresentar um projeto demonstrativo, execute `python seed_demo.py` no Shell do serviço apenas uma vez e confirme que o banco está vazio.

## Funcionalidades presentes

- Cadastro de prefeituras, serventias, núcleos e projetos.
- Cadastro reutilizável de pessoas e beneficiários.
- Importação de coordenadas UTM e arquivos KML/KMZ.
- Organização de vértices, indicação de ponto inicial e ajuste de distância por trecho.
- Cadastro de confrontantes por pessoa, via pública ou matrícula.
- Visualização cartográfica e geração de planta, memorial, CRF e arquivos KML.
- Anexação de plantas baixas por pavimento.
- Fluxo de projeto dividido em etapas, com navegação livre.

## Requisitos

- Python 3.11 ou superior (recomendado 3.12).
- Dependências listadas em `reurb/requirements.txt`.

## Execução local no Windows

No PowerShell, a partir da pasta do repositório:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r .\reurb\requirements.txt
Copy-Item .env.example .env
python .\reurb\app.py
```

Acesse `http://127.0.0.1:5000`. O `.env` é carregado por `python-dotenv`; altere `REURB_SENHA` e `SECRET_KEY` no arquivo local. O arquivo `.env` não deve ser enviado ao GitHub. Para criar um projeto de exemplo com dados inteiramente fictícios em um banco vazio, execute `cd reurb` e `python seed_demo.py`. O script se recusa a rodar se já houver projetos no banco.

## Publicação no GitHub

1. Crie um repositório vazio chamado `reurb-pro`.
2. Defina-o como **Public** se a intenção for disponibilizar o código-fonte.
3. Envie os arquivos desta pasta para a raiz do repositório.
4. Confirme que `.env`, bancos SQLite, `uploads/`, `config/` e documentos reais não aparecem no commit.

```bash
git init
git add .
git status
git commit -m "Publica estrutura inicial do REURB Pro"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/reurb-pro.git
git push -u origin main
```

## Hospedagem no Render

O arquivo `render.yaml` descreve o serviço web e um disco persistente. Depois de enviar o repositório ao GitHub:

1. Entre no Render e escolha **New > Blueprint**.
2. Conecte o repositório `reurb-pro`.
3. Confirme a criação do serviço definido em `render.yaml`.
4. Quando solicitado, informe um valor forte e exclusivo para `REURB_SENHA`.
5. `SECRET_KEY` é gerada pelo Render. Não a substitua por uma senha simples.
6. Aguarde o deploy e abra a URL gerada. O login estará ativo.

O disco persistente mantém banco, anexos e configurações entre deploys. O plano e o custo do Render podem mudar; confira os valores antes de ativar. A configuração usa um único worker para evitar concorrência de inicialização do SQLite.

## Colaboração multiempresa — fundação em implementação

A branch `feature/multiempresa-equipes` inicia a estrutura de dados para transformar o REURB Pro em uma plataforma que atenda tanto o profissional autônomo quanto empresas de engenharia.

### Estrutura preparada nesta etapa

- Organizações (workspaces) independentes.
- Usuários individuais e vínculos de usuário por organização, com papéis previstos para proprietário, engenheiro, técnico de campo, topógrafo, assistente registral e revisor.
- Equipes e integrantes.
- Associação de colaboradores a projetos.
- Tarefas por projeto, equipe e responsável, com prioridade, prazo e situação.
- Eventos de atividade para futura trilha de auditoria.
- Migração não destrutiva: os registros preexistentes são associados à organização principal; nenhum projeto, pessoa ou vértice é apagado.

A migração é inicializada junto com o banco existente. Os campos de organização e a organização principal são criados de forma idempotente. Durante a transição, novos registros criados pelas rotas antigas recebem a organização principal automaticamente.

### Limitação importante desta etapa

**Isto ainda não habilita o uso multiempresa em produção.** O login atual continua usando senha compartilhada e as consultas antigas ainda não aplicam autorização por organização. A estrutura de usuários/equipes/tarefas está preparada no banco, mas as telas, convites, autenticação individual, permissões por projeto e isolamento de consultas precisam ser implementados e testados antes de cadastrar uma segunda organização ou inserir dados pessoais reais.

Não considere a existência da coluna `organization_id` como isolamento de dados. Até a conclusão da autorização em todas as rotas e arquivos, mantenha uma única organização operacional e use dados fictícios em testes.

### Próximas entregas

1. Cadastro inicial seguro do proprietário e login individual com hash de senha.
2. Gestão de organização, convites, membros, papéis e equipes.
3. Gestão de tarefas com responsável, prazo, prioridade, status e histórico.
4. Escopo obrigatório por organização em todas as rotas, consultas, APIs, anexos e downloads.
5. Testes automatizados de acesso cruzado entre organizações e plano de backup/restauração.

## Dados e privacidade

- Comece somente com dados fictícios.
- Não envie ao repositório dados de beneficiários, CPF, RG, certidões, endereços, matrículas, plantas de imóveis reais ou documentos internos.
- Não utilize a demonstração para armazenar dados pessoais ou documentos reais.
- O `.gitignore` exclui arquivos de runtime, mas revise `git status` antes de cada commit: `.gitignore` não remove arquivos que já tenham sido versionados.
- Se algum segredo ou dado pessoal for enviado ao Git, removê-lo do último commit não basta em todos os casos; será necessário revogar/rotacionar segredos e limpar o histórico.

## Segurança incluída nesta preparação

- A aplicação falha ao iniciar em `APP_ENV=production` se `SECRET_KEY` ou `REURB_SENHA` não estiverem configuradas.
- Proteção CSRF em formulários POST.
- Cookies de sessão `HttpOnly`, `SameSite=Lax` e `Secure` em produção.
- Sessões com duração limitada e cabeçalhos básicos de segurança.
- Limite de tamanho de requisição de 30 MB.

Isso não equivale a uma auditoria de segurança. A aplicação ainda precisa de revisão independente, testes de autorização e proteção contra abuso antes de qualquer uso com dados reais.

## Estrutura

```text
reurb-pro/
├── reurb/                 # aplicação Flask, templates, módulos e assets
├── render.yaml            # configuração de deploy no Render
├── .gitignore
├── .env.example
└── README.md
```

## Licença

A licença ainda não foi definida. Antes de tornar o repositório público, escolha uma licença compatível com a titularidade do código e dos componentes incluídos. Publicar no GitHub sem licença explícita não concede automaticamente permissão ampla para reutilização do código.
