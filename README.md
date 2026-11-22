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

## Contas individuais, equipes e tarefas — etapa em implementação

A branch `feature/multiempresa-equipes` prepara o REURB Pro para uso por profissional autônomo e empresas de engenharia.

### Entregas incluídas nesta etapa

- Organizações e vínculos de usuários com papéis.
- Configuração inicial, de uso único, para criar a primeira conta proprietária.
- Login individual por e-mail e senha armazenada com hash.
- Compatibilidade temporária com a senha antiga apenas enquanto não existir nenhum usuário individual. Depois da criação do primeiro proprietário, essa senha deixa de autenticar.
- Cadastro de integrantes, equipes e associação de integrantes às equipes.
- Criação de tarefas vinculadas a projeto, responsável e equipe, com prazo, prioridade e situação.
- Atualização de situação por responsável ou proprietário.
- Alteração da própria senha.
- Eventos básicos de atividade para mudanças de status de tarefas.
- Migração não destrutiva: os registros existentes são associados à organização principal.

### Configuração do primeiro acesso

1. Configure `SECRET_KEY` e `REURB_SETUP_TOKEN` no ambiente. O token precisa ter pelo menos 24 caracteres aleatórios. Em produção, não use a senha padrão local.
2. Faça o deploy da branch de implementação.
3. Acesse `/setup` e informe o token, nome, e-mail e uma senha com pelo menos 12 caracteres.
4. Depois de criar o proprietário, entre pelo formulário de login usando e-mail e senha.
5. Em **Equipe e tarefas**, cadastre os demais integrantes e organize as atividades.

No Render, adicione `REURB_SETUP_TOKEN` em Environment antes do deploy. Guarde esse token fora do repositório e não o compartilhe. A tela de configuração é desativada automaticamente após a criação do primeiro usuário.

### Limites de segurança — leitura obrigatória

**Esta etapa ainda não libera múltiplas empresas independentes.** As telas de equipe e tarefas trabalham dentro da organização principal. As rotas antigas de projetos, cadastros, documentos, anexos e downloads ainda precisam de escopo e testes de autorização abrangentes. Não crie uma segunda organização nem armazene dados pessoais reais em ambiente compartilhado até que essa etapa esteja concluída.

A senha compartilhada antiga é aceita somente enquanto a tabela de usuários estiver vazia, para permitir a transição sem bloquear a instalação existente. Assim que a primeira conta proprietária for criada, o acesso passa a exigir conta individual.

### Próximas entregas

1. Isolamento obrigatório por organização em todas as consultas, APIs, arquivos, anexos e downloads.
2. Permissões por projeto e controle de acesso por função.
3. Convites e recuperação segura de senha.
4. Auditoria consistente de alterações e gestão de sessões.
5. Testes automatizados de acesso cruzado, migração e restauração de backup.

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
