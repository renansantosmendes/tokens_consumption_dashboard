# Dashboard de consumo de tokens (Langfuse)

Painel estático, em HTML e JavaScript, com o consumo de tokens, o custo em reais,
a latência das operações e os usuários que mais gastaram. Os dados vêm do
Langfuse e são gerados por um coletor em Python.

A chave secreta do Langfuse fica só no coletor, que roda na sua máquina. A
página lê o arquivo `dashboard/data.js` gerado e nunca fala com o Langfuse.

## Como rodar

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe python-dotenv==1.1.1 pytest pylint   # Windows
# a partir da pasta do projeto, com src no caminho de importação:
$env:PYTHONPATH="src"; .venv/Scripts/python.exe -m dashboard.build --days 30   # gera dashboard/data.js
```

Depois, abra `dashboard/index.html` no navegador (duplo clique basta).

Opções do coletor:

- `--days N`: tamanho da janela, de 1 a 90 dias (padrão 30).
- `--usd-brl 5.45`: usa uma cotação fixa em vez de consultar o PTAX.
- `--env CAMINHO`: outro arquivo `.env` (padrão `.env` na pasta atual).

O `.env` precisa ter `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY`.

## Testes

```bash
.venv/Scripts/python.exe -m pytest
```

## O que o painel mostra e de onde vem

| Seção | Fonte no Langfuse | Observação |
|---|---|---|
| Custo, tokens, chamadas, latência mediana | `GET /api/public/v2/metrics` sobre as observações do tipo `GENERATION` | Custo em dólar convertido para reais. |
| Consumo diário | Mesma consulta, agrupada por dia | Dias sem dados aparecem zerados. |
| Custo por modelo | Agrupado por `providedModelName` | Generations sem modelo aparecem como "modelo não identificado". |
| Latência por operação | Latência p50 e p95 por nome da observação | São os passos do LangChain/LangGraph, não as rotas da API. |
| Usuários | Agrupado por `userId` | Hoje vazio: nenhum trace leva o usuário (ver abaixo). |

## Limitações conhecidas

- **Usuários não aparecem.** O agente não envia o usuário autenticado ao
  Langfuse, então todas as observações chegam sem `userId`. Para ativar a seção,
  o agente precisa passar o id do usuário nos metadados das chamadas, com a chave
  `langfuse_user_id`, na configuração do LangChain (`config["metadata"]`).
- **Rotas da API não aparecem na latência.** Os nomes registrados são os passos
  internos da cadeia. Para medir por rota (`/chat`, `/upload`...), a rota precisa
  dar um nome ao trace, por exemplo `langfuse_trace_name`.
- **Conversão para reais usa uma única cotação.** Todo o período é convertido pela
  cotação de venda mais recente do PTAX, não pela cotação de cada dia.
- **Custo depende do preço cadastrado no Langfuse.** Um modelo sem preço aparece
  com custo zero, mesmo gastando tokens.
- **Endpoints v1 do Langfuse serão desativados em 16/11/2026.** O coletor já usa
  só a API v2.
