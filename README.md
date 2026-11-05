# Dashboard de consumo de tokens (Langfuse)

Painel estático, em HTML e JavaScript, com o consumo de tokens, o custo em reais,
a latência das operações e os usuários que mais gastaram. Os dados vêm de dois
projetos do Langfuse, somados:

- **agente**: o `.env` do projeto do agente (`.env`).
- **proxy**: o `.env` do proxy da OpenAI (`.env_proxy`), em que cada chamada já
  leva a matrícula do aluno como `user_id`.

O coletor em Python lê os dois projetos com as chaves secretas e grava
`dashboard/data.js`. A página lê esse arquivo e nunca fala com o Langfuse.

## Como rodar

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe python-dotenv==1.1.1 pytest pylint
```

No PowerShell, a partir da pasta do projeto:

```powershell
$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m dashboard.build --days 30
```

Depois, abra `dashboard/index.html` no navegador (duplo clique basta).

Opções do coletor:

- `--source ROTULO=CAMINHO`: projeto a coletar. Repita para mais de um. Padrão:
  `agente=.env` e `proxy=.env_proxy`.
- `--days N`: tamanho da janela, de 1 a 90 dias (padrão 30).
- `--usd-brl 5.45`: usa uma cotação fixa em vez de consultar o PTAX.

Cada `.env` precisa de `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY`, e de
`LANGFUSE_HOST` ou `LANGFUSE_BASE_URL` (o proxy usa este último nome).

## Testes

```bash
.venv\Scripts\python.exe -m pytest
```

## O que o painel mostra e de onde vem

| Seção | Fonte no Langfuse | Observação |
|---|---|---|
| Custo, tokens, chamadas, latência mediana | `GET /api/public/v2/metrics` sobre as observações do tipo `GENERATION` | Soma dos projetos. Custo em dólar convertido para reais. |
| Consumo diário | Mesma consulta, agrupada por dia | Dias sem dados aparecem zerados. |
| Custo por modelo | Agrupado por `providedModelName` | Generations sem modelo aparecem como "modelo não identificado". |
| Latência por operação | Latência p50 e p95 por nome da observação | Passos do LangChain/LangGraph, não as rotas da API. |
| Usuários | Agrupado por `userId` (matrícula, no proxy) | Nome lido de `pgl_proxy.students` no Neon, em modo somente leitura (`NEON_DATABASE_URL` do `.env_proxy`). Se o banco não responder, a coleta segue sem nomes. |

## Limitações conhecidas

- **Latência combinada é aproximada.** A mediana de cada operação entre os
  projetos é uma média ponderada pelas chamadas, e o p95 é o maior valor entre
  os projetos. Os números exatos exigiriam os dados brutos de cada chamada.
- **Usuários só existem no proxy.** O agente chama a OpenAI diretamente, sem
  passar pelo proxy, então o gasto do agente não tem usuário.
- **Rotas da API não aparecem na latência.** Os nomes registrados são os passos
  internos da cadeia. Para medir por rota (`/chat`, `/upload`...), a rota precisa
  dar um nome ao trace.
- **Conversão para reais usa uma única cotação.** Todo o período é convertido pela
  cotação de venda mais recente do PTAX, não pela cotação de cada dia.
- **Custo depende do preço cadastrado no Langfuse.** Um modelo sem preço aparece
  com custo zero, mesmo gastando tokens.
- **Dados pessoais.** Nomes e matrículas dos alunos aparecem no painel. Não compartilhe o `dashboard/data.js` nem o painel com quem não deve ver essas informações.
- **Segredos.** O `.env_proxy` contém a chave da OpenAI e as senhas do banco,
  além das chaves do Langfuse. Ele está no `.gitignore`, mas o coletor só precisa
  das chaves do Langfuse. Vale deixar nesse arquivo apenas `LANGFUSE_*`.
- **Endpoints v1 do Langfuse serão desativados em 16/11/2026.** O coletor usa
  só a API v2.

## Visualizador de conversas

`src/dashboard/viewer.py` sobe um servidor local, só em `127.0.0.1`, que lê as
conversas do proxy no Langfuse. Ele não grava nenhum texto em arquivo: as
perguntas e respostas são buscadas quando você abre a conversa.

```powershell
$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m dashboard.viewer
```

Depois, abra http://127.0.0.1:8765/ (a página é `conversas.html`). O filtro
por aluno usa a lista do `data.js`, então gere o painel antes.

Esse conteúdo é dado pessoal dos alunos: perguntas e respostas podem trazer
informações de terceiros, como o texto de um contrato. Use só no seu
computador e não exponha o servidor na rede.
