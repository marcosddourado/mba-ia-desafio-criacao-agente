# Como testar o assistente (estado atual: Fase 0)

Guia para rodar e conferir o que já existe. Ele acompanha o plano
([`plano-de-execucao.md`](plano-de-execucao.md)): cada fase acrescenta uma seção.
Hoje o que existe é o spike da Fase 0: um especialista `chat` com a tool
`reservar_area` pedindo confirmação, a API com as rotas de sessão do contrato e
a sessão persistida em SQLite.

## 1. Preparar

Pré-requisitos: Python 3.12 e [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env          # preencha GOOGLE_API_KEY (chave do Google AI Studio)
uv sync                       # instala google-adk===2.2.0 e o resto do uv.lock
```

O `.env` fica fora do Git. Os modelos (`MODELO_PRINCIPAL`, `MODELO_ESPECIALISTAS`)
já vêm com os defaults da decisão D5; não precisa mexer.

## 2. Subir a API

```bash
uv run uvicorn web:app --port 8000
```

A documentação automática fica em <http://localhost:8000/docs>. Estado local
(sessões e, por enquanto, os JSON do spike) mora em `.adk/`, ignorado pelo Git.
Para começar do zero, apague a pasta:

```bash
rm -rf .adk
```

(A partir da Fase 2 isso vira `uv run python -m db.restaurar`.)

## 3. Roteiro manual com o `api.http`

Abra [`api.http`](../api.http) no VS Code com a extensão **REST Client**
(`humao.rest-client`) e clique em "Send Request" em cada bloco, de cima para
baixo. Os ids de sessão e de pendência passam sozinhos de um bloco para o outro.

O que conferir em cada passo está no comentário do bloco. O passo que importa é o
**3b**: pare a API com Ctrl+C, suba de novo com o mesmo comando e só então
aprove (3c). É isso que prova a Garantia 3 junto com a Garantia 1: a pendência
sobreviveu ao reinício e a tool executou uma única vez.

Se uma chamada responder **500** com `503 UNAVAILABLE ... high demand` no log do
uvicorn, é o Gemini recusando a chamada por demanda alta. Repita a mesma
requisição depois de alguns segundos; nas rodadas feitas até aqui a segunda
tentativa passou. A tarefa F5.11 do plano transforma isso em `503` na API.

## 4. Conferências que o `.http` não faz

Com a API no ar e `S1` sendo o `session_id`:

```bash
# autores dos eventos: depois da aprovação, os novos devem ser especialista_reservas, nunca assistente
curl -s localhost:8000/sessoes/$S1/eventos | jq '[.[].author]'

# a tool reexecutou uma única vez: a sequência termina em "reservada" e só aparece uma vez
curl -s localhost:8000/sessoes/$S1/eventos | jq '[.[] | .content.parts[]? | select(.function_response.name=="reservar_area") | .function_response.response.status]'

# a pendência ficou gravada no SQLite (sobrevive ao reinício)
sqlite3 .adk/sessoes.db .dump | grep -c adk_request_confirmation
```

Para ver as transferências e os pedidos de confirmação numa interface:

```bash
uv run adk web agents --port 8001
```

No `adk web` a sessão não tem `apartamento` no estado, então a tool responde
"sessão sem apartamento". Para testar com estado, crie a sessão pela API dele:

```bash
curl -s -X POST localhost:8001/apps/residencial_aurora/users/101/sessions/teste -H 'content-type: application/json' -d '{"state": {"apartamento": "101"}}'
```

## 5. Testes automatizados

```bash
uv run pytest -q                              # 67 testes sem rede (unit + e2e do contrato)
HARNESS_GEMINI=1 uv run pytest -q -m gemini   # 3 testes que chamam o Gemini (roteiro F0.5 em processo)
```

Os testes usam um diretório temporário para o banco de sessões e para os JSON do
spike; nunca tocam em `.adk/` nem em `dados/`.

## 6. Harness por fase

No Claude Code, dentro deste repositório, `/harness fase-0` roda os cinco
agentes (simplificar, revisar, testes, conformidade, live) e consolida o
resultado no Registro de execução do plano. Numa sessão nova os agentes aparecem
pelo nome; numa sessão aberta antes de eles existirem, o comando usa
`general-purpose` com a definição de cada um.

O `harness-live` sobe a API sozinho na porta 8000: deixe a porta livre antes.
