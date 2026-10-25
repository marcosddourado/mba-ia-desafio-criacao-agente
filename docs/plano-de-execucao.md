# Plano de execução — Assistente do Residencial Aurora

> **Para quem é este arquivo.** Para os agentes implementadores. Ele é a única
> fonte de progresso do projeto: cada tarefa é um checkbox que o implementador
> marca com data e evidência. Ele foi escrito a partir do enunciado em
> [`README.md`](../README.md) e das decisões fechadas em
> [`docs/decisoes-tecnicas.md`](decisoes-tecnicas.md). Se os três divergirem, a
> ordem é: enunciado > decisões > este plano. Qualquer desvio entra no
> [Registro de execução](#registro-de-execução), no fim.
>
> **Padrão de código.** Tudo imita o projeto da disciplina em
> `/Users/macbook/Projects/mba-ia/mba-ia-dev-agents` (ADK 2.2.0, FastAPI,
> SQLAlchemy async). Antes de escrever um arquivo, abra o equivalente lá (a
> tabela da seção 1 das decisões diz qual) e copie o estilo: nomes em
> português, comentários curtos explicando o porquê, um `App` + um `Runner` +
> um `session_service` globais em `web.py`, `db/` com `engine`/`models`/`repo`.
>
> **Estado em 2026-10-23.** Fase 0 concluída: a retomada da confirmação passou
> no ADK 2.2.0 com `SqliteSessionService` e reinício da API, **sem nenhuma
> alavanca** (Registro #4). Harness de verificação criado em `.claude/agents/`
> e obrigatório no fim de toda fase (seção "Harness de verificação"); a Fase 0
> passou por ele em 2026-10-24 (Registro #7). Modelo dos especialistas mantido
> em `gemini-3.8-flash` por decisão do Marcos (Registro #8). Próxima: Fase 1.

---

## Regras que não se negociam

Quem não vai ler as decisões inteiras lê isto. Cada regra tem a origem entre
parênteses.

1. **Nenhuma tool aceita `apartamento` como parâmetro.** O apartamento vem de
   `tool_context.state["apartamento"]`, gravado uma única vez em
   `POST /sessoes`. Nenhuma tool devolve dado de outro apartamento;
   `verificar_disponibilidade` devolve só livre/ocupado. (D7, Garantia 2,
   passo 15.)
2. **Especialistas `chat` sem `disallow_transfer_to_parent`** e com
   `disallow_transfer_to_peers=True`. É o que mantém o especialista
   "transferível" para `Runner._find_agent_to_run` no ADK 2.2.0 e faz a
   resposta da confirmação voltar para ele. (Seção 3 e D2.)
3. **Nenhum sub-agente `mode="task"` na raiz.** No 2.2.0 a presença de um já
   muda o caminho da retomada para a raiz. (Seção 3.)
4. **Tool com confirmação só nos especialistas `chat`** (`reservar_area` com
   taxa > 0 em `especialista_reservas`; `autorizar_visitante` em
   `especialista_visitantes`). Nunca atrás de `AgentTool`, nunca em
   `single_turn`. (Seção 3, `docs/02-subagents.md` da referência.)
5. **O principal não recebe o regulamento.** Nem na `instruction`, nem por
   tool. Só `especialista_regulamento` (`single_turn`) chama
   `consultar_regulamento`. (Garantia 4.)
6. **Nenhum evento carrega capítulos de outros assuntos.** Chunk = um artigo,
   nunca cruza capítulo; a busca devolve só artigos do capítulo vencedor.
   (D6.)
7. **`dados/` não muda.** Estado mutável mora em `.adk/condominio.db`; o
   comando de restauração recarrega a partir de `dados/*.json`. (Enunciado,
   passo 15.)
8. **ADK fixado em `google-adk===2.2.0`** no `pyproject.toml`, com `uv lock`.
   Subir de versão é plano B e exige aval do Marcos. (D1.)
9. **Layout da seção 1 das decisões:** `web.py`, `env.py`, `api.http`, `db/`,
   `agents/residencial_aurora/{agent.py,subagents/,tools/}`, `docs/`. Tudo em
   português. (Seção 1.)
10. **Nenhuma chave versionada.** `.env` no `.gitignore`; `.env.example` só
    com nomes e defaults não sensíveis. (Enunciado.)
11. **O resultado da Fase 0 decide as alavancas.** Nenhuma alavanca da seção 6
    das decisões (`ResumabilityConfig`, versão do ADK, topologia A) entra no
    código sem estar registrada na tabela
    [Estado das alavancas](#estado-das-alavancas).
12. **Toda fase termina com o harness** (`/harness fase-N`): simplificar →
    revisar → testar → conformidade → live, nessa ordem, com o relatório no
    Registro. Fase sem relatório do harness não está pronta. (Seção
    [Harness de verificação](#harness-de-verificação-obrigatório-ao-fim-de-cada-fase).)

---

## Layout final

```
.
├── web.py                               # FastAPI + App + Runner + SqliteSessionService (Fase 5)
├── env.py                               # load_dotenv + constantes (Fase 0/1)
├── api.http                             # roteiro da Fase 0 hoje; os 14 passos do avaliador na Fase 6
├── pyproject.toml  uv.lock  .python-version
├── .env.example  .gitignore  .vscode/settings.json
├── agents/
│   ├── __init__.py
│   └── residencial_aurora/
│       ├── __init__.py
│       ├── agent.py                     # root_agent `assistente` + `app`
│       ├── plugins.py                   # ModelRetryPlugin (cópia da referência)
│       ├── subagents/
│       │   ├── __init__.py
│       │   ├── especialista_reservas/{__init__.py,agent.py}
│       │   ├── especialista_visitantes/{__init__.py,agent.py}
│       │   └── especialista_regulamento/{__init__.py,agent.py}
│       └── tools/
│           ├── __init__.py
│           ├── erros.py                 # tratar_erro_tool (on_tool_error_callback)
│           ├── reservas.py              # 4 tools de reservas
│           ├── visitantes.py            # 2 tools de visitantes
│           └── regulamento.py           # chunker + índice + consultar_regulamento
├── db/
│   ├── __init__.py
│   ├── engine.py                        # create_async_engine, DATABASE_URL, init_db, close_db
│   ├── models.py                        # reservas, visitantes, sessoes
│   ├── repo.py                          # funções async de leitura/escrita
│   ├── dados.py                         # leitura de dados/apartamentos.json e dados/areas.json
│   └── restaurar.py                     # uv run python -m db.restaurar
├── dados/                               # imutável
├── docs/
│   ├── decisoes-tecnicas.md
│   ├── plano-de-execucao.md             # este arquivo
│   ├── como-testar.md                   # guia de testes manuais, cresce a cada fase
│   └── enunciado.md                     # README original, movido na Fase 7
├── tests/                               # harness: unit/ e e2e/ (pytest, grupo dev)
├── .claude/
│   ├── agents/                          # os 5 agentes do harness
│   ├── skills/harness/SKILL.md          # /harness fase-N
│   └── launch.json                      # preview da API no app (uv run uvicorn web:app --port 8000)
└── .adk/                                # ignorado pelo Git
    ├── sessoes.db                       # SqliteSessionService
    ├── condominio.db                    # SQLAlchemy
    └── regulamento.index.json           # cache do RAG
```

Dois acréscimos ao layout da seção 1 das decisões, ambos dentro de pastas já
previstas: `db/dados.py` (leitura dos JSON imutáveis, usada por tools e por
`web.py`) e `agents/residencial_aurora/tools/erros.py` (o
`on_tool_error_callback` copiado de `ticket_receptionist/agent.py`).

---

## Como marcar progresso

- **Tarefa concluída:** troque `- [ ]` por `- [x]` e acrescente, na mesma
  linha ou logo abaixo, ` — ✅ AAAA-MM-DD — evidência: ...`. Evidência é algo
  que outra pessoa consegue reproduzir: a saída resumida de um `curl`
  (status + campos relevantes), a saída de um `uv run ...`, o caminho do
  arquivo criado, ou o hash do commit.
- **Tarefa bloqueada ou alterada:** não apague o texto original. Acrescente
  ` — ⚠️ AAAA-MM-DD — ver Registro #N` e escreva a entrada no
  [Registro de execução](#registro-de-execução).
- **Tarefa condicional não acionada** (o gatilho não ocorreu, como a escada de
  alavancas): `- [x]` com ` — ⏭️ AAAA-MM-DD — não acionada: motivo`.
- **Fase pronta:** só quando todas as tarefas estão `[x]`, o critério
  "Pronto quando" foi executado e colado como evidência no fim da fase, e o
  harness da fase rodou com relatório no Registro (seção seguinte).
- **Ordem:** Fase 0 antes de tudo. As demais seguem a numeração; dentro de
  uma fase a ordem das tarefas é a sugerida, não obrigatória.
- **Commits:** um por fase no mínimo (`feat: fase N — ...`), mais os que
  forem convenientes. Nunca commitar `.env`, `.adk/` ou `*.db`.
- **Registro de execução:** toda decisão nova, desvio do plano ou resultado de
  spike vira uma entrada numerada e datada no fim deste arquivo. O resultado
  da Fase 0 atualiza a tabela [Estado das alavancas](#estado-das-alavancas),
  e as tarefas F3.7 e F5.5 leem essa tabela antes de serem feitas.
- **Saídas grandes** (eventos completos, dumps) ficam fora do Git. Cole no
  Registro só as linhas que provam o ponto.

---

## Harness de verificação (obrigatório ao fim de cada fase)

Cinco agentes em `.claude/agents/`, rodados **nesta ordem** pelo comando
`/harness fase-N` (`.claude/skills/harness/SKILL.md`), sempre sobre os arquivos
que a fase criou ou alterou:

| # | Agente | O que faz | Mexe em código? |
|---|---|---|---|
| 1 | `harness-simplificar` | Revisa reuso, simplificação, eficiência e altitude (o trabalho do `/simplify`) e aplica só correções que preservam comportamento | Sim, nos arquivos da fase |
| 2 | `harness-revisar` | Code review à procura de bugs, lacunas e violações das regras do plano, com cenário de falha e severidade | Não (relata) |
| 3 | `harness-testes` | Escreve/atualiza e roda `tests/unit` e `tests/e2e` (pytest + httpx contra o app); o que chama o Gemini fica atrás da marca `gemini` e só roda com `HARNESS_GEMINI=1` | Só em `tests/` |
| 4 | `harness-conformidade` | Confere a implementação contra o enunciado (contrato, garantias, passos), as decisões e o "Pronto quando" da fase | Não (relata) |
| 5 | `harness-live` | Sobe a API real na porta 8000 e executa o roteiro live da fase com `curl`, inclusive reinícios; colhe evidências | Não |

Regras:

- A ordem importa: o simplificador muda código antes dos testes; o live é o
  último porque é o mais caro (Gemini real).
- Agente que devolve **FALHOU**: corrigir, rodar de novo só aquele agente, no
  máximo duas voltas; se persistir, registrar e parar antes do live. **ATENÇÃO**
  é decisão item a item, registrada.
- O relatório consolidado (agente → veredito → achados → ação) vira uma entrada
  do Registro; a fase só é marcada depois disso.
- Antes do `harness-live`, parar qualquer API já no ar na porta 8000. O 503
  "high demand" do Gemini é transitório: os agentes repetem até 3 vezes antes
  de acusar falha.
- Os agentes não tocam em `dados/`, não commitam e não imprimem a chave. Quem
  commita é a sessão principal, depois do Registro.
- A Fase 0 foi implementada antes do harness existir e passou por ele em
  seguida (Registro #7). Das fases 1 a 7, o harness faz parte do "Pronto
  quando".

---

## Fase 0 — Spike da confirmação (obrigatória, antes de tudo)

**Objetivo.** Provar, no ADK 2.2.0 com `SqliteSessionService`, que uma tool
com `request_confirmation` dentro de um especialista `chat` **reexecuta**
quando a resposta chega pela API, **inclusive depois de parar e subir a API
entre o pedido e a aprovação**. É o risco que o enunciado chama de
"armadilha silenciosa" e o único que pode mudar o desenho (seção 6 das
decisões). Nada das fases 2 a 7 começa antes desta fase estar marcada.

**Escopo.** Itens 1 a 5 da seção 6 das decisões. Os itens 6 (disputa
simultânea) e 7 (regulamento) dependem do banco e do RAG, que ainda não
existem; eles são provados nas fases 2 (F2.6) e 4 (F4.8) e repetidos de ponta
a ponta na Fase 6. Esse recorte é uma escolha deste plano, registrada no
Registro #1.

**Onde o spike mora.** Nos arquivos finais (`web.py`,
`agents/residencial_aurora/agent.py`, `env.py`), em versão mínima. As fases 3
e 5 reescrevem esses arquivos; o que for exclusivo do spike (os JSON em
`.adk/spike_*.json` e a rota de leitura deles) sai em F5.9.

**Arquivos.** `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`,
`.env` (local), `env.py`, `agents/__init__.py`,
`agents/residencial_aurora/__init__.py`, `agents/residencial_aurora/agent.py`,
`web.py`.

### Tarefas

- [x] **F0.1 Bootstrap mínimo.** Criar `pyproject.toml` (nome
  `residencial-aurora`, `requires-python = ">=3.12"`, dependências
  `google-adk===2.2.0`, `fastapi`, `uvicorn`, `sqlalchemy>=2.0`, `aiosqlite`,
  `asyncpg`, `python-dotenv`, `numpy`; a Fase 1 revisa), `.python-version`
  com `3.12`, rodar `uv lock` e `uv sync`. Acrescentar `.adk/` e `*.db` ao
  `.gitignore`. Não copiar o `.env` da referência: criar um `.env` local
  só com `GOOGLE_API_KEY`, `MODELO_PRINCIPAL=gemini-3.5-flash-lite`,
  `MODELO_ESPECIALISTAS=gemini-3.8-flash`, `MODELO_EMBEDDINGS=gemini-embedding-001`.
  Conferir:
  `uv run python -c "from importlib.metadata import version; print(version('google-adk'))"`
  imprime `2.2.0`.
  — ✅ 2026-10-23 — evidência: `google-adk 2.2.0` impresso; `uv.lock` com
  `name = "google-adk"` / `version = "2.2.0"`; `uv sync` resolveu 62 pacotes;
  `.env` local com 4 linhas, ignorado pelo Git; `pyproject.toml` já com o grupo
  `dev` (pytest, pytest-asyncio, httpx) e a config do pytest para o harness.
- [x] **F0.2 `env.py`.** Igual ao da referência: `load_dotenv()` e constantes
  `MODELO_PRINCIPAL`, `MODELO_ESPECIALISTAS`, `MODELO_EMBEDDINGS`
  (default `gemini-embedding-001`), `SESSION_DB_PATH` (default
  `<raiz>/.adk/sessoes.db`), `RAIZ = __file__.rsplit("/", 1)[0]`.
  — ✅ 2026-10-23 — evidência: `env.py` (também expõe `DATABASE_URL` opcional).
- [x] **F0.3 Agentes do spike** em `agents/residencial_aurora/agent.py`:
  - tool `reservar_area(area: str, data: str, tool_context: ToolContext) -> dict`
    com o esqueleto da seção 7 das decisões (taxas fixas de `dados/areas.json`:
    `150.0` salão, `80.0` churrasqueira, `0` quadra), gravando em
    `.adk/spike_reservas.json` (lista de `{"codigo","apartamento","area","data"}`,
    código `RSV-` + 8 hex de `uuid4`); `apartamento` lido de
    `tool_context.state["apartamento"]`;
  - `especialista_reservas = Agent(name=..., description=..., instruction=...,
    model=MODELO_ESPECIALISTAS, mode="chat", tools=[reservar_area],
    disallow_transfer_to_peers=True)` — **sem** `disallow_transfer_to_parent`;
  - `root_agent = Agent(name="assistente", model=MODELO_PRINCIPAL,
    mode="chat", sub_agents=[especialista_reservas], instruction=<curta>)`;
  - `app = App(root_agent=root_agent, name="residencial_aurora")` — **sem**
    `ResumabilityConfig`.
  — ✅ 2026-10-23 — evidência: `agents/residencial_aurora/agent.py`; a
  verificação estática imprimiu `especialista_reservas chat gemini-3.8-flash |
  to_parent: False | to_peers: True`, `resumability: None`, sem `task`.
- [x] **F0.4 `web.py` do spike.** Copiar a montagem de `web.py` da referência:
  `os.makedirs(.adk)`, `session_service = SqliteSessionService(SESSION_DB_PATH)`
  (`from google.adk.sessions.sqlite_session_service import SqliteSessionService`),
  `runner = Runner(app=app, session_service=session_service)`. Mapa
  `session_id → apartamento` em `.adk/spike_sessoes.json` (a tabela `sessoes`
  chega na Fase 2). Helpers `_texto(event)` (cópia) e `_pendencias(sessao)`
  (código da seção 7 das decisões). Rotas, já no contrato do enunciado:
  `POST /sessoes` (201, `user_id=apartamento`, `state={"apartamento": ...}`),
  `POST /sessoes/{id}/mensagens`, `POST /sessoes/{id}/confirmacoes` (409 se o
  `id` não está em `_pendencias`), `GET /sessoes/{id}/eventos`
  (`event.model_dump(mode="json", exclude_none=True)`), e
  `GET /apartamentos/{n}/reservas` lendo o JSON do spike. As rotas de
  mensagem e confirmação **releem a sessão depois do `run_async`** e montam
  `{"resposta", "confirmacoes_pendentes"}` a partir dela.
  — ✅ 2026-10-23 — evidência: `web.py`; rotas registradas: `/sessoes`,
  `/sessoes/{session_id}/mensagens`, `/sessoes/{session_id}/confirmacoes`,
  `/sessoes/{session_id}/eventos`, `/apartamentos/{numero}/reservas`.
- [x] **F0.5 Roteiro dos itens 1–5.** Subir com `uv run uvicorn web:app --port 8000`
  e executar, anotando status e corpo de cada passo:

  ```bash
  B=http://localhost:8000; J='content-type: application/json'
  S1=$(curl -s -X POST $B/sessoes -H "$J" -d '{"apartamento":"101"}' | jq -r .session_id)
  # item 1: pedido com taxa → 1 pendência, nada gravado
  curl -s -X POST $B/sessoes/$S1/mensagens -H "$J" -d '{"texto":"Reserve o salão de festas para 2030-04-20."}' | jq
  curl -s $B/apartamentos/101/reservas | jq            # sem salão em 2030-04-20
  # item 2: negar → nada gravado, lista vazia
  ID=<id da pendência>
  curl -s -X POST $B/sessoes/$S1/confirmacoes -H "$J" -d "{\"id\":\"$ID\",\"confirmado\":false}" | jq
  # item 3: pedir de novo, PARAR A API (Ctrl+C), SUBIR DE NOVO, aprovar → gravado uma vez
  curl -s -X POST $B/sessoes/$S1/mensagens -H "$J" -d '{"texto":"Reserve o salão de festas para 2030-04-20."}' | jq
  ID2=<novo id>      # Ctrl+C no uvicorn, subir de novo, então:
  curl -s -X POST $B/sessoes/$S1/confirmacoes -H "$J" -d "{\"id\":\"$ID2\",\"confirmado\":true}" | jq
  curl -s $B/apartamentos/101/reservas | jq            # exatamente 1 salão em 2030-04-20
  # item 4: reenviar o mesmo id → 409, continua 1
  curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/sessoes/$S1/confirmacoes -H "$J" -d "{\"id\":\"$ID2\",\"confirmado\":true}"
  # item 5: id inexistente → 409
  curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/sessoes/$S1/confirmacoes -H "$J" -d '{"id":"id-inexistente","confirmado":true}'
  ```

  Em **cada tentativa** do item 3 registrar: data/hora, flags dos agentes
  (`mode`, `disallow_transfer_*`), `ResumabilityConfig` ligado ou não, a
  sequência de `author` dos eventos **depois** do `function_response`
  (`curl -s $B/sessoes/$S1/eventos | jq '.[].author'`) e se existe um
  `function_response` de `reservar_area` após a confirmação
  (`jq '[.[] | .content.parts[]? | select(.function_response.name=="reservar_area")] | length'`;
  se o dump sair em camelCase, use `functionResponse`). O sinal da armadilha
  é: `200`, `author` da raiz (`assistente`) depois da resposta, nenhum
  `function_response` de `reservar_area`, nada gravado.
  — ✅ 2026-10-23 — evidência (sessão `6960d35d…`, detalhes no Registro #4):
  item 1 → `200`, `confirmacoes_pendentes` = `[{"acao": "reservar_area",
  "detalhes": {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0}}]`,
  reservas `[]`; item 2 → `200`, lista vazia, reservas `[]`; item 3 → 19
  eventos antes e depois do reinício, aprovação `200` com
  `RSV-3DE0B09B`, autores novos `["user", "especialista_reservas",
  "especialista_reservas"]`, `function_response` de `reservar_area` =
  `reservada`, reservas com 1 item; item 4 → `409`, continua 1; item 5 → `409`.
  `GET /sessoes/sessao-inexistente/eventos` → `404`.
- [x] **F0.6 Escada de alavancas** — só se o item 3 falhar. — ⏭️ 2026-10-23 —
  não acionada: o item 3 passou na primeira tentativa (Registro #4). Tentar nesta ordem,
  uma por vez, repetindo o roteiro inteiro de F0.5 a cada tentativa e
  registrando o resultado no Registro:
  - [x] ⏭️ **F0.6a** conferir que `especialista_reservas` não tem
    `disallow_transfer_to_parent=True` e que a raiz não tem sub-agente `task`
    (`runners.py::_is_transferable_across_agent_tree` e o bloco
    `has_task_subagent` em `Runner.run_async`);
  - [x] ⏭️ **F0.6b** `App(..., resumability_config=ResumabilityConfig(is_resumable=True))`
    (`from google.adk.apps import ResumabilityConfig`). Com isso o Runner
    passa a rotear pelo **autor da function call** e exige `invocation_id`
    coerente: a rota de confirmação passa a chamar
    `runner.run_async(..., new_message=conteudo, invocation_id=<invocation_id do evento que carrega a function call adk_request_confirmation>)`.
    Atenção à semântica *at-least-once* da retomada: as tools de escrita
    precisam ser idempotentes (a reserva fica pelo índice único de F2.2; o
    visitante pelo `UNIQUE(apartamento, nome, data)`);
  - [x] ⏭️ **F0.6c** **parar e propor ao Marcos** subir para `google-adk===2.12.0`
    ou `2.13.0` (correções listadas na seção 3 das decisões). Não aplicar sem
    resposta dele; registrar a proposta;
  - [x] ⏭️ **F0.6d** topologia A (D2): mover `reservar_area` e
    `autorizar_visitante` para o principal, mantendo os especialistas de
    leitura. Tools, banco e API não mudam.
- [x] **F0.7 Registrar o resultado.** Entrada no Registro com: o que passou,
  qual alavanca ficou em uso (ou nenhuma), o trecho de `jq '.[].author'` que
  prova a retomada, e a confirmação de que `.adk/sessoes.db` guardou o pedido
  (`sqlite3 .adk/sessoes.db .dump | grep -c adk_request_confirmation` ≥ 1).
  Atualizar a tabela [Estado das alavancas](#estado-das-alavancas). Se
  alguma alavanca entrou, marcar em F3.7 e F5.5 o que muda.
  — ✅ 2026-10-23 — evidência: Registro #4; tabela de alavancas com "não"
  em todas; `sqlite3 .adk/sessoes.db .dump | grep -c adk_request_confirmation`
  → `3` antes do reinício. F3.7 e F5.5 seguem o texto do plano.

**Pronto quando.** Os itens 1–5 passam com a API reiniciada entre o pedido e
a aprovação do item 3; F0.7 está no Registro; a tabela de alavancas está
preenchida; `git status` não mostra `.env`, `.adk/` nem `*.db`.
— ✅ 2026-10-23: tudo conferido (Registro #4). Harness da Fase 0: Registro #7.

---

## Fase 1 — Esqueleto do projeto

**Objetivo.** Deixar o repositório no formato que o avaliador espera no passo
1: `uv sync` limpo, versão exata do ADK, `.env.example` completo, nada
sensível versionado, mesmas conveniências da referência.

**Arquivos.** `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`,
`.gitignore`, `.vscode/settings.json`, `env.py`, `agents/__init__.py`,
`agents/residencial_aurora/__init__.py`, `agents/residencial_aurora/subagents/__init__.py`,
`agents/residencial_aurora/tools/__init__.py`, `db/__init__.py`.

### Tarefas

- [ ] **F1.1 `pyproject.toml` final.** Revisar o de F0.1: `description` em
  português, `readme = "README.md"`, dependências com versões mínimas no
  estilo da referência (`"google-adk===2.2.0"`, `"fastapi>=0.133"`,
  `"uvicorn>=0.34"`, `"sqlalchemy>=2.0"`, `"aiosqlite>=0.21"`,
  `"asyncpg>=0.31"`, `"python-dotenv>=1"`, `"numpy>=2"`). Rodar `uv lock` e
  `uv sync`. Conferir: `grep -n 'google-adk===2.2.0' pyproject.toml` e
  `grep -A1 'name = "google-adk"' uv.lock | grep 'version = "2.2.0"'`.
- [ ] **F1.2 `.python-version`** com `3.12` (igual à referência).
- [x] **F1.3 `.env.example`** comentado por seção como o da referência, sem
  nenhum valor sensível (M8): — ✅ 2026-10-25 — evidência: `.env.example`
  criado antes da Fase 1 para o Marcos testar a Fase 0 (`docs/como-testar.md`);
  conteúdo igual ao bloco abaixo.

  ```dotenv
  # Copie para `.env` na raiz do repositório: cp .env.example .env

  # ---- Obrigatório -------------------------------------------------------- #
  # Chave do Gemini (https://aistudio.google.com/apikey). Lida pelo ADK e pelo google-genai.
  GOOGLE_API_KEY=

  # ---- Modelos (docs/decisoes-tecnicas.md, D5) ----------------------------- #
  MODELO_PRINCIPAL=gemini-3.5-flash-lite
  MODELO_ESPECIALISTAS=gemini-3.8-flash
  MODELO_EMBEDDINGS=gemini-embedding-001

  # ---- Opcional ------------------------------------------------------------ #
  # Banco do condomínio. Default: SQLite em .adk/condominio.db.
  # DATABASE_URL=postgresql+asyncpg://aurora:aurora@localhost:5432/aurora
  # Arquivo das sessões do ADK. Default: .adk/sessoes.db
  # SESSION_DB_PATH=.adk/sessoes.db
  ```
- [ ] **F1.4 `.gitignore`**: `.env`, `.venv/`, `__pycache__/`, `*.pyc`,
  `.adk/`, `*.db`, `.history/`.
- [ ] **F1.5 `.vscode/settings.json`** copiado da referência (interpretador
  `.venv`, `PYTHONPATH=${workspaceFolder}`,
  `ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS=1`).
- [ ] **F1.6 Pacotes vazios** (`__init__.py` listados acima) e `env.py` final
  (acrescentar `DATABASE_URL` opcional, lido em `db/engine.py`).
- [ ] **F1.7 Verificação de segredos.** `git ls-files | grep -E '(^|/)\.env$'`
  vazio; `git grep -nE 'AIza[0-9A-Za-z_-]{20,}'` vazio; `.env.example`
  versionado.

**Pronto quando.** `rm -rf .venv && uv sync` termina sem erro;
`uv run python -c "import google.adk, fastapi, sqlalchemy, aiosqlite, numpy, dotenv; print('ok')"`
imprime `ok`; F1.1 e F1.7 conferidos; commit `feat: fase 1 — esqueleto do projeto`; `/harness fase-1` com relatório no Registro.

---

## Fase 2 — Banco do condomínio (`db/`)

**Objetivo.** Armazenamento com SQLAlchemy async em `.adk/condominio.db`, com
a exclusividade da reserva **no instante da gravação** (índice único parcial)
e o comando de restauração offline.

**Referência.** `db/engine.py`, `db/models.py`, `db/repo.py`, `db/reset.py`
da referência. Mesmo estilo: `DeclarativeBase`, `Mapped`, `mapped_column`,
`async with async_session.begin() as session`.

**Arquivos.** `db/engine.py`, `db/models.py`, `db/repo.py`, `db/dados.py`,
`db/restaurar.py`.

### Tarefas

- [ ] **F2.1 `db/engine.py`.** `DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///<raiz>/.adk/condominio.db")`;
  `os.makedirs(<raiz>/.adk, exist_ok=True)`;
  `engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"timeout": 30} se sqlite)`;
  listener `@event.listens_for(engine.sync_engine, "connect")` que executa
  `PRAGMA journal_mode=WAL` e `PRAGMA busy_timeout=5000` quando a URL é
  SQLite (evita "database is locked" na disputa do passo 14);
  `async_session`, `init_db()`, `close_db()` iguais à referência.
- [ ] **F2.2 `db/models.py`.**
  - `ReservaModel` (`reservas`): `codigo` PK `String(16)` com default
    `_novo_codigo()` = `f"RSV-{uuid4().hex[:8].upper()}"` (M4);
    `apartamento String(8)` indexado; `area String(32)`; `data String(10)`
    (AAAA-MM-DD); `status String(16)` default `"ativa"`; `criado_em`,
    `cancelado_em` nullable. **Índice único parcial:**
    `Index("ux_reservas_area_data_ativa", "area", "data", unique=True, sqlite_where=text("status = 'ativa'"), postgresql_where=text("status = 'ativa'"))`
    em `__table_args__`. Canceladas ficam na tabela com `status='cancelada'`,
    então `codigo` PK cobre a regra 5 (código nunca repete, nem de cancelada).
  - `VisitanteModel` (`visitantes`): `id` autoincrement, `apartamento`,
    `nome String(120)`, `data String(10)`, `criado_em`,
    `UniqueConstraint("apartamento", "nome", "data")`.
  - `SessaoModel` (`sessoes`): `session_id` PK `String(64)`, `apartamento`,
    `criado_em`.
- [ ] **F2.3 `db/dados.py`.** Carrega uma vez `dados/apartamentos.json` e
  `dados/areas.json` (imutáveis): `APARTAMENTOS: dict[str, str]`
  (`numero → morador`), `AREAS: dict[str, Area]` (`id → {nome, taxa}`),
  `apartamento_existe(numero) -> bool`, `area_por_id(area) -> Area | None`,
  `DATA_RE = r"^\d{4}-\d{2}-\d{2}$"` e `validar_data(data)` que levanta
  `ValueError` (M7).
- [ ] **F2.4 `db/repo.py`.** Todas `async`, uma transação por função:
  `listar_reservas_ativas(apartamento) -> list[ReservaModel]` (ordem por
  `data`); `reserva_ativa_existe(area, data) -> bool`;
  `criar_reserva(apartamento, area, data) -> ReservaModel` (**deixa
  `IntegrityError` subir**: quem trata é a tool);
  `cancelar_reserva(apartamento, codigo) -> ReservaModel | None` (um
  `UPDATE ... WHERE codigo=? AND apartamento=? AND status='ativa'`; devolve
  `None` quando não é do apartamento ou não está ativa — a tool responde
  "não encontrada" sem revelar o dono); `listar_visitantes(apartamento)`;
  `autorizar_visitante(apartamento, nome, data) -> VisitanteModel` (deixa
  `IntegrityError` subir); `criar_sessao(session_id, apartamento)`;
  `obter_sessao(session_id) -> SessaoModel | None`.
- [ ] **F2.5 `db/restaurar.py`.** No molde de `db/reset.py`: `drop_all`,
  `create_all`, inserir `dados/reservas.json` com `status="ativa"` e
  `dados/visitantes.json`, apagar `.adk/sessoes.db` **e** os arquivos
  `sessoes.db-wal` / `sessoes.db-shm` se existirem (M3), imprimir um resumo
  (`3 reservas, 2 visitantes, sessões apagadas`). Não toca em
  `.adk/regulamento.index.json`. Não chama a API do Gemini. Entrada:
  `uv run python -m db.restaurar`.
- [ ] **F2.6 Verificação da exclusividade.** Rodar um script temporário (fora
  do Git) com duas gravações simultâneas na mesma área e data:

  ```python
  import asyncio
  from sqlalchemy.exc import IntegrityError
  from db import repo
  from db.engine import close_db, init_db

  async def tentar(apt):
      try:
          r = await repo.criar_reserva(apt, "salao-de-festas", "2030-05-11")
          return f"{apt}: reservada {r.codigo}"
      except IntegrityError:
          return f"{apt}: indisponivel"

  async def main():
      await init_db()
      print(await asyncio.gather(tentar("101"), tentar("201")))
      await close_db()

  asyncio.run(main())
  ```

  Esperado: uma linha `reservada`, uma `indisponivel`, sem exceção solta.
  Repetir 3 vezes (rodando `uv run python -m db.restaurar` entre elas).

**Pronto quando.** `uv run python -m db.restaurar` imprime o resumo;
`sqlite3 .adk/condominio.db "select codigo, apartamento, area, data, status from reservas"`
lista `RSV-1377`, `RSV-4821`, `RSV-2950` ativas;
`sqlite3 .adk/condominio.db ".schema reservas"` mostra o índice com
`WHERE status = 'ativa'`; `ls .adk/sessoes.db` falha depois da restauração;
F2.6 passou 3 vezes; commit `feat: fase 2 — banco do condomínio`; `/harness fase-2` com relatório no Registro.

---

## Fase 3 — Tools e agentes (`agents/residencial_aurora/`)

**Objetivo.** O principal `assistente` roteando para `especialista_reservas`
e `especialista_visitantes` (`chat`, donos das tools), com as garantias 1 e
2 dentro das tools. O `especialista_regulamento` entra na Fase 4.

**Referência.** `operador_conta_session_state/agent.py` (tool com
`request_confirmation` e estado da sessão), `operador_conta_subagent/agent.py`
(coordenador + `chat` com `disallow_transfer_to_peers=True`),
`ticket_receptionist/agent.py` (`_handle_tool_error`, `App` com plugin) e
`ticket_receptionist/plugins.py`.

**Antes de começar:** ler a tabela [Estado das alavancas](#estado-das-alavancas).

**Arquivos.** `agents/residencial_aurora/tools/erros.py`, `tools/reservas.py`,
`tools/visitantes.py`, `subagents/especialista_reservas/agent.py`,
`subagents/especialista_visitantes/agent.py`, `plugins.py`, `agent.py`.

### Tarefas

- [ ] **F3.1 `tools/erros.py`.** `tratar_erro_tool(tool, args, tool_context, error)`
  copiado de `_handle_tool_error`: `ValueError` → `{"status": "error",
  "message": str(error)}`; qualquer outro → mensagem genérica, com `logger.error`.
- [ ] **F3.2 `tools/reservas.py`.** Quatro tools `async`, nenhuma com
  parâmetro `apartamento`, todas lendo `tool_context.state["apartamento"]`
  (se faltar, `ValueError("sessão sem apartamento")`), validando `area`
  (`dados.area_por_id`) e `data` (`dados.validar_data`) com `ValueError`:
  - `listar_minhas_reservas(tool_context) -> {"reservas": [{"codigo","area","data"}]}`;
  - `verificar_disponibilidade(area, data, tool_context) -> {"area","data","disponivel": bool}`
    — nunca devolve de quem é a reserva;
  - `reservar_area(area, data, tool_context)`: (1) se
    `repo.reserva_ativa_existe(area, data)` → `{"status": "indisponivel", "area", "data"}`
    **antes** de pedir confirmação (poupa uma rodada e evita pendência
    inútil no passo 10); (2) se `taxa > 0` e `tool_context.tool_confirmation is None`
    → `request_confirmation(hint=..., payload={"area", "data", "taxa"})` e
    `{"status": "aguardando_confirmacao"}`; (3) se `taxa > 0` e
    `not tool_confirmation.confirmed` → `{"status": "nao_confirmada"}`;
    (4) `repo.criar_reserva` dentro de `try/except IntegrityError` →
    `{"status": "indisponivel"}` (Garantia 5); sucesso →
    `{"status": "reservada", "codigo", "area", "data", "taxa"}`;
  - `cancelar_reserva(codigo, tool_context)`: `repo.cancelar_reserva(apartamento, codigo)`;
    `None` → `{"status": "nao_encontrada", "codigo"}`; sucesso →
    `{"status": "cancelada", "codigo"}`. Sem confirmação (regra 4).
- [ ] **F3.3 `tools/visitantes.py`.**
  - `listar_meus_visitantes(tool_context) -> {"visitantes": [{"nome","data"}]}`;
  - `autorizar_visitante(nome, data, tool_context)`: **sempre** pede
    confirmação na primeira passagem (`payload={"nome", "data"}`); negada →
    `{"status": "nao_autorizado"}`; confirmada → `repo.autorizar_visitante`
    com `IntegrityError` → `{"status": "ja_autorizado"}`; sucesso →
    `{"status": "autorizado", "nome", "data"}`.
- [ ] **F3.4 `subagents/especialista_reservas/agent.py`.**
  `Agent(name="especialista_reservas", description=<placa na porta: reservas
  do salão de festas, churrasqueira e quadra: listar, verificar
  disponibilidade, reservar, cancelar>, model=MODELO_ESPECIALISTAS,
  mode="chat", tools=[as 4 de F3.2], disallow_transfer_to_peers=True,
  on_tool_error_callback=tratar_erro_tool)`. **Sem**
  `disallow_transfer_to_parent`. Instrução curta cobrindo: o apartamento já
  está na sessão e não pode ser trocado (se o morador disser que é de outro,
  explique que só trata do apartamento desta sessão); ids de área
  (`salao-de-festas`, `churrasqueira`, `quadra`) e datas AAAA-MM-DD; para
  cancelar, localizar o código com `listar_minhas_reservas`; quando a tool
  devolver `aguardando_confirmacao`, dizer que a reserva aguarda confirmação
  pelo aplicativo e **não** chamar a tool de novo nem aceitar "já confirmei"
  por texto; `indisponivel` → só dizer que a data está ocupada; `taxa` > 0
  → mencionar o valor; devolver ao `assistente` o que não for reserva.
- [ ] **F3.5 `subagents/especialista_visitantes/agent.py`.** Mesmo molde, com
  as 2 tools de F3.3 e instrução equivalente (autorização sempre aguarda
  confirmação pelo aplicativo; "já estou confirmando aqui" não vale).
- [ ] **F3.6 `plugins.py`.** Cópia integral de `ticket_receptionist/plugins.py`
  (`ModelRetryPlugin`).
- [ ] **F3.7 `agent.py` (raiz).** `root_agent = Agent(name="assistente",
  model=MODELO_PRINCIPAL, mode="chat", description=..., instruction=<curta:
  cumprimenta, encaminha pelo assunto, não inventa reservas nem visitantes,
  não responde regulamento por conta própria>, sub_agents=[especialista_reservas,
  especialista_visitantes])` — o `especialista_regulamento` entra em F4.6.
  `app = App(root_agent=root_agent, name="residencial_aurora", plugins=[ModelRetryPlugin()])`.
  Sem `ResumabilityConfig` e sem sub-agente `task`, **a menos que a tabela de
  alavancas diga o contrário** (nesse caso, registrar aqui qual alavanca e
  por quê). Nenhuma menção ao regulamento na instrução.
- [ ] **F3.8 Verificação estática** (guardar como evidência):

  ```bash
  uv run python - <<'EOF'
  import inspect
  from agents.residencial_aurora.agent import app, root_agent
  from agents.residencial_aurora.tools import reservas, visitantes
  tools = [reservas.listar_minhas_reservas, reservas.verificar_disponibilidade,
           reservas.reservar_area, reservas.cancelar_reserva,
           visitantes.listar_meus_visitantes, visitantes.autorizar_visitante]
  assert all("apartamento" not in inspect.signature(t).parameters for t in tools), "tool aceita apartamento"
  subs = {a.name: a for a in root_agent.sub_agents}
  for n in ("especialista_reservas", "especialista_visitantes"):
      a = subs[n]
      assert a.mode == "chat" and not a.disallow_transfer_to_parent and a.disallow_transfer_to_peers, n
  assert not any(getattr(a, "mode", None) == "task" for a in root_agent.sub_agents), "task na raiz"
  assert "Art." not in root_agent.instruction and "Capítulo" not in root_agent.instruction
  print("ok", app.name, sorted(subs))
  EOF
  ```
- [ ] **F3.9 Smoke pela API do spike.** Com o `web.py` de F0.4 (que importa
  `app`), rodar `uv run python -m db.restaurar`, subir a API e passar pelos
  passos 3, 4, 5, 6 e 11 do avaliador em uma sessão do 101. Conferir:
  passo 3 não traz `RSV-4821` nem `Marina Duarte`
  (`curl -s $B/sessoes/$S1/eventos | grep -c -E 'RSV-4821|Marina Duarte'` → 0);
  passo 5 cancela `RSV-1377` sem pendência e passo 6 reserva a quadra sem
  pendência — conferir **no banco**, com
  `sqlite3 .adk/condominio.db "select codigo, area, data, status from reservas where apartamento='101'"`,
  porque a rota de verificação do spike ainda lê o JSON; passo 11 gera
  pendência com `nome` e `data` em `detalhes`.
  Opcional para ver transferências: `uv run adk web agents --port 8001`
  (criar a sessão com estado via
  `POST http://localhost:8001/apps/residencial_aurora/users/101/sessions/<id>`
  com corpo `{"state": {"apartamento": "101"}}`; sem o estado as tools
  devolvem o erro tratado "sessão sem apartamento").

**Pronto quando.** F3.8 imprime `ok`; F3.9 conferido e colado como evidência;
`grep -rn "apartamento:" agents/residencial_aurora/tools/` não mostra
parâmetro de função; commit `feat: fase 3 — tools e agentes`; `/harness fase-3` com relatório no Registro.

---

## Fase 4 — Regulamento por RAG (Garantia 4)

**Objetivo.** `consultar_regulamento(pergunta)` com embeddings
`gemini-embedding-001`, um artigo por chunk, índice em processo com numpy em
`.adk/regulamento.index.json`, busca top-5 **filtrada ao capítulo vencedor**,
servida por `especialista_regulamento` em `single_turn`. O principal nunca vê
o regulamento.

**Arquivos.** `agents/residencial_aurora/tools/regulamento.py`,
`agents/residencial_aurora/subagents/especialista_regulamento/agent.py`,
`agents/residencial_aurora/agent.py` (acrescenta o especialista).

### Tarefas

- [ ] **F4.1 Chunker.** `carregar_artigos(caminho=dados/regulamento.md) -> list[Artigo]`
  com `Artigo(capitulo_numero: str, capitulo_titulo: str, artigo: str, texto: str)`.
  Capítulos pelo regex `^## Capítulo ([IVXL]+): (.+)$`; artigos por
  `^\*\*Art\. (\d+)\.\*\*`; o texto de um artigo vai até o próximo artigo
  **ou o próximo capítulo**, o que vier primeiro (um chunk nunca cruza
  capítulo). `texto` é o artigo inteiro como está no arquivo, com o prefixo
  `**Art. N.**` e seus incisos e parágrafos, sem cortes. Conferir: `len(artigos) == 96`, 14 capítulos distintos, nenhum
  `texto` contém `## Capítulo`.
- [ ] **F4.2 Embeddings.** `google.genai.Client()` (lê `GOOGLE_API_KEY`),
  `await client.aio.models.embed_content(model=MODELO_EMBEDDINGS, contents=lote, config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=768))`
  em lotes de até 32 textos; `task_type="RETRIEVAL_QUERY"` para a pergunta;
  normalização `v / np.linalg.norm(v)` (obrigatória fora de 3072 dims).
- [ ] **F4.3 Índice persistido.** Classe `IndiceRegulamento` com
  `carregar()` (lê `.adk/regulamento.index.json` se o `sha256` do
  `regulamento.md` e o `modelo` baterem; senão constrói e grava), matriz
  `numpy` 96×768, metadados dos artigos, `asyncio.Lock` para não construir
  duas vezes em chamadas concorrentes. Construção **sob demanda na primeira
  consulta**; `db.restaurar` não toca nele.
- [ ] **F4.4 Busca com filtro por capítulo.** `mais_similares(q, k=5)` por
  cosseno (`M @ q`); agrupar por capítulo, vencedor = maior soma de
  similaridade; devolver só os artigos do vencedor que estão no top-k, em
  ordem de artigo. Se o melhor score < `LIMIAR` (constante no módulo,
  inicial `0.5`, calibrada em F4.7) → `{"status": "sem_resultado",
  "capitulos": [títulos]}`.
- [ ] **F4.5 Tool.** `async def consultar_regulamento(pergunta: str) -> dict`
  → `{"status": "ok", "capitulo": "Capítulo IV: Piscina", "artigos": [{"artigo": "Art. 22", "texto": "..."}]}`
  (`texto` igual ao do chunk, sem cortes, para que F4.8 consiga reconhecê-lo).
  Sem parâmetro de apartamento (não precisa de `tool_context`). A
  assinatura `consultar_regulamento(assunto, capitulo=None)` de M2 foi
  substituída por D6; registrar no Registro.
- [ ] **F4.6 `subagents/especialista_regulamento/agent.py`.**
  `Agent(name="especialista_regulamento", description=<dúvidas sobre o
  regulamento interno: horários, regras de uso, penalidades...>,
  model=MODELO_ESPECIALISTAS, mode="single_turn", tools=[consultar_regulamento],
  on_tool_error_callback=tratar_erro_tool)`. Instrução: chamar a tool com a
  pergunta recebida; responder **só** com os artigos devolvidos, citando o
  número; em `sem_resultado`, dizer que não encontrou e listar os capítulos;
  não inventar regra. No 2.2.0 o `single_turn` sem `input_schema` recebe a
  pergunta no argumento `request` (`_SingleTurnAgentTool`). Acrescentar em
  `sub_agents` do `root_agent` (F3.7) e repetir F3.8 com a asserção
  `subs["especialista_regulamento"].mode == "single_turn"`.
- [ ] **F4.7 Calibração do limiar.** Script temporário chamando a tool
  direto com: "Até que horas a piscina funciona aos domingos?" (esperado
  Capítulo IV, Art. 22), "Posso levar meu cachorro na piscina?" (IV ou
  VIII), "Qual o horário de silêncio?" (III), "Como faço uma mudança?" (IX),
  "Posso fazer obra no sábado?" (X), "Quantos convidados na churrasqueira?"
  (VI) e duas fora de assunto ("Qual é a capital da França?", "Receita de
  bolo"). Anotar top score e capítulo vencedor de cada uma no Registro;
  fixar `LIMIAR` abaixo do menor score correto e acima dos fora de assunto.
- [ ] **F4.8 Verificação da Garantia 4 nos eventos.** Pela API: restaurar,
  criar sessão, enviar o passo 12, salvar `GET /eventos` em um arquivo
  temporário (`curl -s $B/sessoes/$S1/eventos > /tmp/eventos-s1.json`) e
  rodar, passando o caminho como argumento:

  ```bash
  uv run python - /tmp/eventos-s1.json <<'EOF'
  import json, sys
  from agents.residencial_aurora.tools.regulamento import carregar_artigos

  def textos(x):
      if isinstance(x, str):
          yield x
      elif isinstance(x, dict):
          for v in x.values():
              yield from textos(v)
      elif isinstance(x, list):
          for v in x:
              yield from textos(v)

  norm = lambda t: " ".join(t.split())
  eventos = json.load(open(sys.argv[1], encoding="utf-8"))
  corpo = norm(" ".join(textos(eventos)))
  presentes = {a.capitulo_numero for a in carregar_artigos() if norm(a.texto)[:100] in corpo}
  print("capítulos com trecho nos eventos:", sorted(presentes) or "nenhum")
  assert presentes <= {"IV"}, "trecho de outro capítulo vazou para os eventos"
  assert "20h" in corpo, "resposta sem o horário de fechamento"
  print("ok")
  EOF
  ```

  Esperado: `['IV']` e `ok`. O mesmo script roda em F6.4 sobre os eventos
  completos de S1.

**Pronto quando.** F4.1 confere 96 artigos e 14 capítulos; `.adk/regulamento.index.json`
existe depois da primeira consulta e a segunda consulta não chama
`embed_content` para documentos (log); F4.7 anotado; F4.8 passa; F3.8
repetido com os três especialistas; commit `feat: fase 4 — regulamento por RAG`; `/harness fase-4` com relatório no Registro.

---

## Fase 5 — API (`web.py`) no contrato do enunciado

**Objetivo.** Substituir o `web.py` do spike pela versão final: contrato
literal, `404`/`409` nos lugares certos, pendências derivadas dos eventos,
rotas de verificação lendo o banco direto.

**Referência.** `web.py` da raiz da referência (montagem, `_texto`,
`_aprovacao_pendente`, `responder_aprovacao`, releitura da sessão depois do
`run_async`).

**Antes de começar:** ler a tabela [Estado das alavancas](#estado-das-alavancas)
(afeta F5.5).

**Arquivos.** `web.py`.

### Tarefas

- [ ] **F5.1 Montagem.** `import env` primeiro; `os.makedirs(.adk)`;
  `session_service = SqliteSessionService(env.SESSION_DB_PATH)`;
  `runner = Runner(app=app, session_service=session_service)`; `lifespan`
  com `init_db()`/`close_db()`; `FastAPI(title="Assistente do Residencial Aurora", lifespan=lifespan)`.
  Constante `REQUEST_CONFIRMATION = "adk_request_confirmation"`.
- [ ] **F5.2 Helpers.** `_texto(event)` (cópia); `_pendencias(sessao) -> list[dict]`
  exatamente como a seção 7 das decisões (`id` = id da function call,
  `acao` = `originalFunctionCall.name`, `detalhes` = `toolConfirmation.payload`,
  removendo as que já têm `function_response` de mesmo id);
  `_montar_resposta(sessao_apos_run, texto) -> {"resposta": texto or "", "confirmacoes_pendentes": _pendencias(...)}`;
  `_carregar_sessao(session_id) -> tuple[SessaoModel, Session]` que consulta
  `repo.obter_sessao` e `session_service.get_session(app_name=runner.app_name, user_id=registro.apartamento, session_id=...)`,
  levantando `HTTPException(404)` se qualquer um faltar;
  `_rodar(sessao, conteudo, invocation_id=None) -> dict` que itera
  `runner.run_async`, guarda o texto do último `event.is_final_response()`,
  relê a sessão e chama `_montar_resposta`.
- [ ] **F5.3 `POST /sessoes`** (`status_code=201`). Body `{"apartamento": str}`
  (`BaseModel`, `Field(min_length=1)`: vazio → `422`). `404` se
  `not dados.apartamento_existe(apartamento)` (M6).
  `session_service.create_session(app_name=runner.app_name, user_id=apartamento, state={"apartamento": apartamento})`,
  depois `repo.criar_sessao(sessao.id, apartamento)`. Resposta
  `{"session_id": sessao.id}`.
- [ ] **F5.4 `POST /sessoes/{session_id}/mensagens`.** Body `{"texto": str}`
  com `Field(min_length=1)` (vazio → `422`; texto vazio chegaria ao modelo como
  turno invisível e viraria 500, Registro #7). `_carregar_sessao` (404). Se
  `_pendencias(sessao)` não está vazia →
  `HTTPException(409, detail={"mensagem": "Responda a confirmação pendente antes de enviar outra mensagem.", "confirmacoes_pendentes": [...]})`
  (M5). **Obrigatório, não opcional:** sem isso o especialista pode devolver a
  conversa à raiz antes da confirmação e a retomada cai num agente sem a tool
  (`ValueError: Tool 'reservar_area' not found` → 500, aprovação consumida e
  perdida; Registro #7, achado 1). Senão
  `_rodar(sessao, Content(role="user", parts=[Part.from_text(texto)]))`.
- [ ] **F5.5 `POST /sessoes/{session_id}/confirmacoes`.** Body
  `{"id": str, "confirmado": bool}`. `_carregar_sessao` (404). Se `id` não
  está em `_pendencias(sessao)` → `HTTPException(409, detail="Não existe confirmação pendente com esse id nesta sessão.")`
  — cobre id já respondido e id inexistente. Defesa extra (Registro #7,
  achado 1): se o autor do último evento não-usuário for diferente do autor do
  evento que carrega a `adk_request_confirmation` com esse `id`, responder
  `409` com `detail` dizendo que a conversa saiu do especialista, **sem**
  consumir a pendência. Senão
  `Content(role="user", parts=[Part(function_response=FunctionResponse(id=id, name=REQUEST_CONFIRMATION, response={"confirmed": confirmado}))])`
  e `_rodar`. **Se a alavanca F0.6b estiver em uso**, passar
  `invocation_id` do evento que carrega a function call com esse `id`.
- [ ] **F5.6 `GET /sessoes/{session_id}/eventos`.** `_carregar_sessao` (404);
  devolve `[e.model_dump(mode="json", exclude_none=True) for e in sessao.events]`
  em ordem (M9).
- [ ] **F5.7 `GET /apartamentos/{numero}/reservas`.** `404` se o apartamento
  não existe (M6). `[{"codigo", "area", "data"}]` das reservas ativas, lido
  direto do banco (`repo.listar_reservas_ativas`), sem passar pelo modelo.
- [ ] **F5.8 `GET /apartamentos/{numero}/visitantes`.** Idem, `[{"nome", "data"}]`.
- [ ] **F5.9 Limpeza do spike.** Remover o mapa `.adk/spike_sessoes.json`, a
  gravação em `.adk/spike_reservas.json` e qualquer rota ou helper exclusivo
  do spike; apagar os arquivos em `.adk/`.
- [ ] **F5.10 Verificação do contrato por `curl`** (colar como evidência):

  ```bash
  B=http://localhost:8000; J='content-type: application/json'
  uv run python -m db.restaurar
  curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/sessoes -H "$J" -d '{"apartamento":"101"}'        # 201
  curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/sessoes -H "$J" -d '{"apartamento":"999"}'        # 404
  curl -s -o /dev/null -w '%{http_code}\n' $B/sessoes/sessao-inexistente/eventos                        # 404
  curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/sessoes/sessao-inexistente/mensagens -H "$J" -d '{"texto":"oi"}'  # 404
  curl -s $B/apartamentos/101/reservas | jq -c          # [{"codigo":"RSV-1377","area":"quadra","data":"2030-03-09"}]
  curl -s $B/apartamentos/302/visitantes | jq -c        # [{"nome":"Marina Duarte","data":"2030-03-16"}]
  S1=$(curl -s -X POST $B/sessoes -H "$J" -d '{"apartamento":"101"}' | jq -r .session_id)
  curl -s -X POST $B/sessoes/$S1/mensagens -H "$J" -d '{"texto":"Olá"}' | jq -c 'keys'  # ["confirmacoes_pendentes","resposta"]
  curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/sessoes/$S1/confirmacoes -H "$J" -d '{"id":"id-inexistente","confirmado":true}'  # 409
  ```

- [ ] **F5.11 Erro do modelo não vira 500.** Em `_rodar`, capturar
  `google.genai.errors.APIError` (inclui o `ServerError` 503 "high demand" visto
  na Fase 0, Registro #5) e responder `HTTPException(503, detail="O modelo está
  indisponível no momento; repita a mensagem.")`. Não grava nada no banco; o
  turno parcial que o ADK deixou na sessão é inofensivo (o próximo turno segue).
  Conferir forçando um modelo inexistente em `MODELO_PRINCIPAL` e enviando uma
  mensagem → `503` com o `detail` acima, e `GET /eventos` continua `200`.
  **Na rota de confirmações** a ordem dos processadores do ADK faz a tool
  reexecutar e gravar **antes** da chamada ao modelo: ao capturar o erro,
  reler a sessão; se já existe `function_response` da tool original depois do
  evento do usuário, a ação executou → responder `200` com `resposta: ""` e as
  pendências; só devolver `503` quando a tool não chegou a rodar (Registro #7,
  achado 2). Vale o mesmo na rota de mensagens: o live da Fase 0 viu um 503
  chegar **depois** de a `adk_request_confirmation` ter sido gravada, e o
  cliente recebeu 500 sem o `id` de uma pendência que já existia. Regra única
  para as duas rotas: capturou erro do modelo → reler a sessão → se o turno
  deixou pendência nova ou `function_response` da tool, `200` com
  `resposta: ""` e as pendências; senão `503`.

**Pronto quando.** F5.10 devolve os códigos indicados; os itens 1–5 da Fase 0
repassam com este `web.py` **duas vezes**: com `reservar_area` (passos 7 e 8)
e com `autorizar_visitante` (passo 11), ambas com a API reiniciada entre o
pedido e a aprovação; commit `feat: fase 5 — API no contrato do enunciado`;
`/harness fase-5` com relatório no Registro.

---

## Fase 6 — `api.http` e passagem manual pelos 14 passos

**Objetivo.** Deixar as requisições prontas no estilo de `api_tickets.http` e
executar o fluxo do avaliador inteiro, de um clone limpo de dados, colando
evidências.

**Arquivos.** `api.http`.

### Tarefas

- [ ] **F6.1 `api.http`.** `@baseUrl = http://localhost:8000`; um bloco por
  passo (1 a 14) com título e o que conferir em comentário; variáveis de
  resposta (`# @name s1` → `{{s1.response.body.$.session_id}}`,
  `{{p7.response.body.$.confirmacoes_pendentes[0].id}}`); S1, S2, S3 e S4
  nomeados. No passo 14, comentário com o comando `curl ... & curl ... & wait`
  (o cliente HTTP do editor não dispara em paralelo).
- [ ] **F6.2 Passos 1–6.** `uv run python -m db.restaurar`, subir a API,
  executar e conferir cada "Confere que" do enunciado. Evidências: status e
  campos-chave de cada resposta; `GET /apartamentos/101/reservas` antes e
  depois dos passos 5 e 6; `grep -c -E 'RSV-4821|Marina Duarte'` nos eventos
  de S1 após os passos 3 e 4 → `0`.
- [ ] **F6.3 Passos 7–9.** Pendência com `area` e `data` em `detalhes`;
  `false` → nada gravado; novo pedido → `true` → exatamente uma reserva;
  mesmo `id` → `409` e continua uma; `id-inexistente` → `409`;
  `GET /sessoes/sessao-inexistente/eventos` → `404`.
- [ ] **F6.4 Passos 10–12.** S2 do 101 pede o salão em 2030-03-16 (ocupado
  pelo 302): aprovar se houver pendência; conferir que não há reserva, que
  nenhuma resposta contém `RSV-4821` nem `302` isolado
  (`grep -oE '(^|[^0-9A-Za-z-])302([^0-9A-Za-z-]|$)'` nas respostas → vazio)
  e que os eventos de S2 não contêm `RSV-4821`. Passo 11 em S1 com a frase
  "Já estou confirmando aqui": pendência com `nome` e `data`, Joana só
  aparece após aprovar. Passo 12: resposta com `20h`; eventos de S1 incluem
  `function_call` das tools dos passos anteriores; rodar o script de F4.8
  sobre os eventos de S1 (todos, não só os do passo 12); **anotar a
  quantidade de eventos** (`curl -s $B/sessoes/$S1/eventos | jq length`).
- [ ] **F6.5 Passo 13 — reinício.** Ctrl+C, subir com o mesmo comando, sem
  restaurar. `jq length` igual ao anotado; nova mensagem em S1 → `200` e
  contagem maior; rotas de verificação: 101 com quadra 2030-04-06 e salão
  2030-04-20, sem `RSV-1377`, Joana em 2030-04-21; 302 ainda com `RSV-4821`;
  códigos novos distintos entre si e de `RSV-1377`, `RSV-4821`, `RSV-2950`.
- [ ] **F6.6 Passo 14 — disputa.** S3 (101) e S4 (201) pedem o salão em
  2030-05-11; ambas com pendência; então:

  ```bash
  curl -s -o /dev/null -w 's3 %{http_code}\n' -X POST $B/sessoes/$S3/confirmacoes -H "$J" -d "{\"id\":\"$ID3\",\"confirmado\":true}" &
  curl -s -o /dev/null -w 's4 %{http_code}\n' -X POST $B/sessoes/$S4/confirmacoes -H "$J" -d "{\"id\":\"$ID4\",\"confirmado\":true}" &
  wait
  curl -s $B/apartamentos/101/reservas | jq -c '[.[] | select(.area=="salao-de-festas" and .data=="2030-05-11")] | length'
  curl -s $B/apartamentos/201/reservas | jq -c '[.[] | select(.area=="salao-de-festas" and .data=="2030-05-11")] | length'
  ```

  Dois `200`; a soma das duas contagens é `1`. Repetir a disputa 3 vezes
  (restaurar entre elas) e anotar qual apartamento venceu em cada uma.
- [ ] **F6.7 Evidências e Registro.** Entrada no Registro com a tabela
  passo → resultado → evidência resumida, e qualquer ajuste de instrução ou
  `description` que tenha sido necessário para o roteamento acertar.

**Pronto quando.** Os 14 passos conferidos e registrados; F6.6 passou 3
vezes; `api.http` versionado; commit `feat: fase 6 — api.http e passagem pelo fluxo do avaliador`; `/harness fase-6` com relatório no Registro.

---

## Fase 7 — README final

**Objetivo.** Substituir o enunciado pelo README da entrega com as três
seções exigidas, apontando arquivos e trechos que existem.

**Arquivos.** `README.md`, `docs/enunciado.md`.

### Tarefas

- [ ] **F7.1 Preservar o enunciado.** `git mv README.md docs/enunciado.md` e
  ajustar o link no cabeçalho de `docs/decisoes-tecnicas.md` e deste plano
  (`../README.md` → `enunciado.md`).
- [ ] **F7.2 Seção Arquitetura.** Tabela com cada agente (`assistente`,
  `especialista_reservas`, `especialista_visitantes`,
  `especialista_regulamento`): responsabilidade, `mode`, modelo (variável do
  `.env`), tools, como é acionado (`transfer_to_agent` para os `chat`;
  chamada como tool para o `single_turn`) e **por quê** (chat para quem pede
  confirmação; single_turn para consulta autônoma; por que o principal não
  tem tools). Um diagrama de sequência curto (mermaid) do passo 7/8. Um
  parágrafo sobre `App` + `Runner` + `SqliteSessionService` e sobre o banco.
- [ ] **F7.3 Seção Garantias.** Para cada uma: arquivo, função ou trecho
  (com link `arquivo#Lnn`) e por que não depende do modelo:
  - G1: `agents/residencial_aurora/tools/reservas.py::reservar_area` e
    `tools/visitantes.py::autorizar_visitante` (`request_confirmation`),
    `web.py::_pendencias` e o `409` em `POST /sessoes/{id}/confirmacoes`;
  - G2: `web.py` (`create_session(..., state={"apartamento"})`), as tools
    lendo `tool_context.state["apartamento"]`, nenhuma com o parâmetro,
    `db/repo.py::cancelar_reserva` filtrando por apartamento,
    `verificar_disponibilidade` sem dono;
  - G3: `SqliteSessionService` em `.adk/sessoes.db`, `db/engine.py`
    (SQLite em `.adk/condominio.db`), `db/restaurar.py` como único apagador;
  - G4: `tools/regulamento.py` (chunk por artigo, filtro pelo capítulo
    vencedor), `especialista_regulamento` em `single_turn`, instrução do
    `assistente` sem regulamento; citar o evento do passo 12;
  - G5: `db/models.py` (índice único parcial), `reservar_area` tratando
    `IntegrityError`, resultado do passo 14.
- [ ] **F7.4 Seção Como rodar.** Pré-requisitos (Python 3.12, uv), `cp .env.example .env`
  e as variáveis, `uv sync`, `uv run python -m db.restaurar`,
  `uv run uvicorn web:app --port 8000`, `api.http`, opcional
  `uv run adk web agents --port 8001`, opcional Postgres via `DATABASE_URL`
  (sem docker-compose neste repositório). Dizer que a restauração apaga as
  sessões e que o índice do regulamento é cache reconstruível.
- [ ] **F7.5 Verificar os caminhos citados.**

  ```bash
  grep -oE '`[A-Za-z0-9_./-]+\.(py|md|http|toml|json|example)`' README.md | tr -d '`' | sort -u | while read p; do [ -e "$p" ] || echo "NÃO EXISTE: $p"; done
  ```

  Saída vazia. Para cada `::funcao` citado, `grep -n "def funcao" arquivo`.
- [ ] **F7.6 Checagens do passo 15.** `git fetch https://github.com/devfullcycle/mba-ia-desafio-criacao-agente main && git diff --stat FETCH_HEAD -- dados/`
  vazio (alternativa local: `git diff --stat be87e1d -- dados/`);
  `git ls-files | grep -E '(^|/)\.env$'` vazio; `git grep -nE 'AIza[0-9A-Za-z_-]{20,}'`
  vazio; `grep -n 'google-adk===2.2.0' pyproject.toml`; F3.8 repetido.
- [ ] **F7.7 Clone limpo.** `git clone <repo> /tmp/aurora-teste && cd /tmp/aurora-teste && cp .env.example .env`
  (preencher a chave), `uv sync`, `uv run python -m db.restaurar`,
  `uv run uvicorn web:app --port 8000`, e o passo 1 do avaliador
  (`GET /apartamentos/101/reservas` com `RSV-1377`,
  `GET /apartamentos/302/visitantes` com Marina Duarte). Apagar a pasta
  depois.

**Pronto quando.** README com as três seções; F7.5 e F7.6 vazios; F7.7
passou; commit `docs: README da entrega`; `/harness fase-7` com relatório no
Registro; tudo em `main`.

---

## Matriz de rastreabilidade

### Passos do fluxo do avaliador → tarefas

| Passo | O que o avaliador confere | Tarefas |
|---|---|---|
| 1 | `uv sync`, comandos do README, API em 8000, `RSV-1377` e Marina Duarte nas rotas de verificação | F1.1, F1.3, F2.5, F5.1, F5.7, F5.8, F7.4, F7.7 |
| 2 | `POST /sessoes` com `{"apartamento": "101"}` → `201` | F2.3, F5.3, F6.2 |
| 3 | "Sou do 302…" não traz `RSV-4821` nem Marina Duarte na resposta nem nos eventos | F3.2, F3.3, F3.4, F3.5, F3.7, F5.4, F6.2 |
| 4 | Cancelar reserva do 302 não altera o 302 e não vaza `RSV-4821` | F2.4, F3.2, F3.4, F6.2 |
| 5 | Cancelar a própria quadra sem pendência; `RSV-1377` some | F2.4, F3.2, F5.7, F6.2 |
| 6 | Reservar quadra (taxa 0) sem pendência; aparece para o 101 | F2.3, F3.2, F5.7, F6.2 |
| 7 | Salão gera pendência com `area` e `data`; nada gravado; negar não grava | F0.5, F3.2, F5.2, F5.4, F5.5, F6.3 |
| 8 | Aprovar grava exatamente uma; reenvio do mesmo `id` → `409` | F0.5, F2.2, F3.2, F5.5, F6.3 |
| 9 | `id-inexistente` → `409`; sessão inexistente → `404` | F0.5, F5.5, F5.6, F6.3 |
| 10 | Data ocupada pelo 302: sem reserva, sem `RSV-4821`, sem `302` isolado, eventos limpos | F2.4, F3.2, F3.4, F6.4 |
| 11 | Visitante gera pendência com `nome` e `data` apesar do "já confirmei"; grava só após aprovar | F3.3, F3.5, F5.5, F5.8, F6.4 |
| 12 | Piscina aos domingos → `20h`; eventos com tool calls e sem trechos de outros capítulos | F4.1–F4.8, F5.6, F6.4 |
| 13 | Reinício mantém eventos e dados; nova mensagem funciona; códigos distintos | F0.5, F2.1, F2.2, F5.1, F6.5 |
| 14 | Duas aprovações simultâneas → dois `200`, uma reserva | F2.1, F2.2, F2.6, F3.2, F5.5, F6.6 |
| 15 | Versão fixada, `dados/` idêntico, sem chave, 1 principal + ≥2 especialistas, tools, apartamento da sessão, principal sem regulamento, exclusividade na gravação, README aponta trechos reais | F1.1, F1.7, F2.2, F3.2, F3.3, F3.7, F3.8, F4.6, F7.3, F7.5, F7.6 |

### Critérios de aceite → tarefas

| Critério (README) | Tarefas |
|---|---|
| `uv sync` sem erro, ADK exato ≥ 2.2.0 na série 2 | F0.1, F1.1 |
| Restauração e subida deixam a API em 8000 com os dados iniciais | F2.5, F5.1, F7.4 |
| `dados/` idêntico ao base | regra 7; F7.6 |
| Sem chave versionada; `.env` fora; `.env.example` completo | F1.3, F1.4, F1.7, F7.6 |
| Principal + ≥2 especialistas | F3.4, F3.5, F3.7, F4.6, F3.8 |
| Reservas e visitantes por tools; mudanças aparecem nas rotas de verificação | F3.2, F3.3, F5.7, F5.8, F6.2 |
| G1: reservar com taxa → pendência com `area`/`data`, nada antes da resposta | F3.2, F5.2, F6.3 |
| G1: negar não grava | F3.2, F5.5, F6.3 |
| G1: aprovar grava exatamente uma | F2.2, F3.2, F5.5, F6.3 |
| G1: reenvio → `409`, sem reexecutar | F5.2, F5.5, F6.3 |
| G1: id não pendente → `409`, nada muda | F5.5, F6.3 |
| G1: área sem taxa não pede confirmação | F3.2, F6.2 |
| G1: visitante pede confirmação mesmo com "já confirmei"; grava só depois | F3.3, F3.5, F6.4 |
| G2: dados do 302 numa sessão do 101 não aparecem | F3.2, F3.3, F3.4, F3.5, F6.2 |
| G2: cancelar reserva do 302 não altera nem vaza | F2.4, F3.2, F6.2 |
| G2: cancelar a própria sem pendência | F3.2, F6.2 |
| G2: data ocupada pelo 302 não cria, não vaza `RSV-4821` nem `302` | F3.2, F6.4 |
| G2: apartamento vem da sessão; nenhuma tool o aceita | F3.2, F3.3, F3.8, F5.3 |
| G3: eventos iguais após reinício; aceita novas mensagens | F5.1, F6.5 |
| G3: dados anteriores continuam; códigos não repetem | F2.1, F2.2, F6.5 |
| G4: resposta da piscina traz o horário | F4.4, F4.5, F4.6, F4.7, F6.4 |
| G4: eventos com tool calls e sem trechos de outros capítulos | F4.1, F4.4, F4.8, F6.4 |
| G4: principal sem regulamento | F3.7, F3.8, F4.6 |
| G5: duas aprovações → dois `200` | F2.1, F3.2, F6.6 |
| G5: soma exatamente uma reserva | F2.2, F2.6, F6.6 |
| G5: exclusividade na gravação | F2.2, F3.2, F7.3 |
| Contrato: caminhos, campos, formatos, status | F5.3–F5.8, F5.10 |
| README com Arquitetura, Garantias e Como rodar apontando trechos reais | F7.2, F7.3, F7.4, F7.5 |

### Contrato da API → tarefas

| Rota | Entrada | Saída e status | Tarefas |
|---|---|---|---|
| `POST /sessoes` | `{"apartamento"}` | `201 {"session_id"}`; `404` apartamento inexistente (M6) | F5.3, F2.3 |
| `POST /sessoes/{id}/mensagens` | `{"texto"}` | `200 {"resposta", "confirmacoes_pendentes": [{"id","acao","detalhes"}]}`; `resposta` pode ser `""`; `404` sessão; `409` com pendência aberta (M5) | F5.2, F5.4 |
| `POST /sessoes/{id}/confirmacoes` | `{"id", "confirmado"}` | `200` mesmo formato; `409` id não pendente (inclui já respondido); `404` sessão | F5.2, F5.5 |
| `GET /sessoes/{id}/eventos` | — | `200` lista completa em ordem; `404` | F5.6 |
| `GET /apartamentos/{n}/reservas` | — | `200 [{"codigo","area","data"}]`; `404` (M6) | F5.7, F2.4 |
| `GET /apartamentos/{n}/visitantes` | — | `200 [{"nome","data"}]`; `404` (M6) | F5.8, F2.4 |
| Datas AAAA-MM-DD | — | validação nas tools (M7) | F2.3, F3.2, F3.3 |

---

## Riscos e verificações por fase

| Fase | Risco | Sinal | Verificação | Mitigação |
|---|---|---|---|---|
| 0 | Resposta da confirmação roteada à raiz (a "armadilha") | `200`, `author` = `assistente` após o `function_response`, nenhum `function_response` de `reservar_area`, nada gravado | `jq '.[].author'` e o `jq` de F0.5 | Escada F0.6, na ordem; registrar cada tentativa |
| 0 | `ValueError: Function call event not found for function response id` | 500 na rota de confirmação | log do uvicorn | O `409` de `_pendencias` deve barrar antes; conferir que o `id` enviado é o da function call `adk_request_confirmation` |
| 0 | Sessão não persistiu o pedido (`long_running_tool_ids`/`args`) | pendência some após reinício | `sqlite3 .adk/sessoes.db .dump \| grep -c adk_request_confirmation` | Confirmar `SqliteSessionService` (não `InMemory`), caminho absoluto em `.adk/` |
| 0 | Alavanca 2 (`ResumabilityConfig`) reexecuta a tool mais de uma vez (*at-least-once*) | duas reservas / dois visitantes | rotas de verificação | Índice único parcial e `UNIQUE(apartamento,nome,data)` já tornam as escritas idempotentes |
| 1 | `uv sync` falha no avaliador por dependência pesada | erro de build | `rm -rf .venv && uv sync` | Manter a lista mínima; `asyncpg` só porque D4 pede troca por env |
| 1 | Chave vazando em commit | `git grep` acha `AIza` | F1.7, F7.6 | `.env` no `.gitignore` antes do primeiro commit com `.env` local |
| 2 | "database is locked" na disputa | 500 em uma das aprovações | F2.6 ×3, F6.6 ×3 | WAL + `busy_timeout` + `connect_args={"timeout": 30}` (F2.1) |
| 2 | Índice parcial não criado (sintaxe `sqlite_where`) ou ignorado no Postgres | duas reservas ativas | `.schema reservas` mostra `WHERE status = 'ativa'`; F2.6 | `Index(..., unique=True, sqlite_where=text(...), postgresql_where=text(...))` |
| 2 | Restauração deixa `sessoes.db-wal`/`-shm` e a sessão "ressuscita" | eventos antigos após restaurar | `ls .adk/` após restaurar | F2.5 apaga os três arquivos |
| 2 | Restauração dependendo da API do Gemini | falha sem rede/chave | rodar com `GOOGLE_API_KEY` vazia | Índice do regulamento só sob demanda (F4.3) |
| 3 | Tool com parâmetro `apartamento` ou especialista com `disallow_transfer_to_parent=True` | F3.8 falha | F3.8 | Regras 1 e 2 |
| 3 | `cancelar_reserva`/`verificar_disponibilidade` revelando dono | código ou apartamento alheio na resposta | passos 3, 4 e 10; `grep RSV-4821` | Retornos de F3.2 não carregam dono; `repo.cancelar_reserva` filtra por apartamento |
| 3 | Principal "lite" roteia errado ou faz ping-pong em pedido misto (passo 3: reservas **e** visitantes) | transferências em loop, resposta parcial | `jq '.[].author'` no passo 3 | Ajustar `description` (placa na porta), não a instrução do principal; `disallow_transfer_to_peers=True` força a volta pelo principal |
| 3 | Modelo aceita "já confirmei" e chama a tool de novo | duas pendências para a mesma ação | `confirmacoes_pendentes` com 2 itens | Instrução de F3.4/F3.5; o `409` de M5 bloqueia nova mensagem com pendência |
| 3 | Sessão sem `apartamento` no `adk web` | `KeyError` | log | `ValueError` tratado ("sessão sem apartamento"); criar sessão com `state` na API do `adk web` |
| 4 | Chunk cruzando capítulo ou evento com dois capítulos | F4.8 falha | F4.1 e F4.8 | Cortar no próximo `## Capítulo`; filtrar ao capítulo vencedor |
| 4 | Limiar mal calibrado (sem resultado para a piscina, ou capítulo errado) | `sem_resultado` ou capítulo ≠ IV | F4.7 | Ajustar `LIMIAR`; conferir `task_type` e normalização |
| 4 | Primeira consulta lenta (construção do índice) ou cota de embeddings | timeout no passo 12 | tempo da primeira resposta | Lotes de 32; índice em cache; opcionalmente fazer uma consulta antes da avaliação |
| 4 | Regulamento entrando na instrução de algum agente | `grep -rn "Art\." agents/` acha instrução | F3.8 | Regra 5; só a tool lê o arquivo |
| 5 | O spike só provou a retomada em `especialista_reservas`; `autorizar_visitante` vive em outro especialista `chat` (passo 11) | aprovação do visitante responde `200` e não grava | repetir os itens 1–5 de F0.5 com o passo 11, com reinício ("Pronto quando" da Fase 5) | Mesmas flags de F3.4 em F3.5; se falhar só ali, comparar `jq '.[].author'` dos dois casos antes de mexer em alavanca |
| 5 | 503 "high demand" do Gemini vira 500 na API e deixa um turno parcial na sessão (visto na Fase 0) | `500` na rota de mensagens, log com `ServerError: 503 UNAVAILABLE` | F5.11; o live repete até 3 vezes | F5.11 responde `503` com `detail`; cliente repete; `ModelRetryPlugin` não cobre esse caso (é erro de transporte, não resposta vazia) |
| 5 | `resposta` nula em vez de `""` ao pausar | contrato quebrado | F5.10 | `_montar_resposta` com `texto or ""` |
| 5 | Pendência derivada errada (id da call original em vez da `adk_request_confirmation`) | `409` em id válido | item 4 de F0.5 | Usar `fc.id` da call `adk_request_confirmation`, `response={"confirmed": bool}` |
| 5 | `user_id` errado no `get_session` | `404` em sessão existente | F5.10 | `user_id` = apartamento da tabela `sessoes` |
| 6 | Passo 13: `_find_agent_to_run` após reinício cai na raiz e a conversa "esquece" o especialista | nova mensagem ignora contexto | `jq '.[].author'` após o passo 13 | Especialistas transferíveis (regra 2); se persistir, só afeta tom, não as garantias |
| 6 | Passo 14: um `500` por lock ou duas reservas | status ≠ 200 ou soma ≠ 1 | F6.6 ×3 | F2.1 e F2.2; tool trata `IntegrityError` |
| 6 | Passo 10: resposta menciona `302` por conta própria | `grep` acha `302` isolado | F6.4 | A tool nunca devolve dono; instrução não cita outros apartamentos |
| 6 | Cota do free tier estourada no meio do fluxo | 429 / resposta vazia | log | `ModelRetryPlugin`; trocar `MODELO_ESPECIALISTAS` para `gemini-3.6-flash` pelo `.env` (D5) |
| 7 | README citando arquivo ou função que não existe | F7.5 acha caminho | F7.5 | Escrever a seção Garantias com o código aberto ao lado |
| 7 | `dados/` alterado sem querer (formatação, ordem) | `git diff` não vazio | F7.6 | Nunca abrir `dados/` para escrita; `restaurar.py` só lê |

---

## Registro de execução

Entradas numeradas, mais nova por último. Formato:
`#N · AAAA-MM-DD · tipo (spike | desvio | decisão | evidência) · fase/tarefa` e
o texto.

### Estado das alavancas

Preenchido por F0.7. Enquanto todas estiverem "não", F3.7 e F5.5 seguem o
texto do plano.

| Alavanca (seção 6 das decisões) | Em uso? | Decidido em | Evidência |
|---|---|---|---|
| 1. Conferir flags (`disallow_transfer_to_parent`, sub-agente `task`) | conferida (ok) | 2026-10-23 | F0.3: `to_parent: False`, `to_peers: True`, sem `task` |
| 2. `ResumabilityConfig(is_resumable=True)` + `invocation_id` na retomada | **não** | 2026-10-23 | Registro #4: retomada passou sem ela |
| 3. Subir o ADK para 2.12.0/2.13.0 (só com aval do Marcos) | **não** | 2026-10-23 | Registro #4: 2.2.0 mantido |
| 4. Topologia A (tools de confirmação no principal) | **não** | 2026-10-23 | Registro #4: topologia B mantida |

### Entradas

- **#1 · 2026-10-23 · decisão · Fase 0.** O spike cobre os itens 1–5 da
  seção 6 das decisões. Os itens 6 (disputa simultânea) e 7 (regulamento)
  ficam para F2.6 e F4.8, onde a infraestrutura deles nasce, e são repetidos
  de ponta a ponta na Fase 6. Motivo: os dois dependem do banco e do RAG; o
  risco que decide as alavancas é só a retomada da confirmação. O spike é
  escrito nos arquivos finais em versão mínima, e o que for exclusivo dele
  sai em F5.9.
- **#2 · 2026-10-23 · decisão · F4.5.** A assinatura
  `consultar_regulamento(assunto, capitulo=None)` listada em M2 das decisões
  foi substituída por `consultar_regulamento(pergunta)` quando D6 passou de
  "tool por capítulo" para RAG. O plano segue D6 e a seção 7 das decisões.
- **#3 · 2026-10-23 · decisão · layout.** Dois arquivos a mais dentro de
  pastas já previstas: `db/dados.py` (leitura dos JSON imutáveis, usada por
  tools e por `web.py`) e `agents/residencial_aurora/tools/erros.py`
  (`on_tool_error_callback`). `asyncpg` entra nas dependências para que
  `DATABASE_URL` com Postgres funcione sem mudar código (D4); não há
  `docker-compose.yml` neste repositório.
- **#4 · 2026-10-23 · spike · Fase 0 (F0.5/F0.7).** Itens 1–5 da seção 6 das
  decisões **passaram na primeira tentativa**, em `google-adk===2.2.0`, com
  `SqliteSessionService` em `.adk/sessoes.db`, topologia B (`assistente` chat →
  `especialista_reservas` chat, `disallow_transfer_to_peers=True`, sem
  `disallow_transfer_to_parent`, sem `task`, sem `ResumabilityConfig`), modelos
  `gemini-3.5-flash-lite` (principal) e `gemini-3.8-flash` (especialista).
  Sessão `6960d35d-ac03-47d5-b757-ebdefd341500`, apartamento 101:
  - item 1: `POST /mensagens` "Reserve o salão de festas para 2030-04-20." →
    `200`, `resposta` do especialista dizendo que aguarda confirmação pelo
    aplicativo, `confirmacoes_pendentes` = 1 item (`id` `adk-e772b75f…`,
    `acao` `reservar_area`, `detalhes` `{area, data, taxa: 150.0}`);
    `GET /apartamentos/101/reservas` = `[]`;
  - item 2: `confirmado: false` → `200`, "nada foi reservado", lista vazia,
    reservas `[]`; `function_response` de `reservar_area` = `nao_confirmada`;
  - item 3: novo pedido → pendência `adk-764c291f…`; **API parada e subida de
    novo** (19 eventos antes, 19 depois; `sqlite3 .adk/sessoes.db .dump | grep -c
    adk_request_confirmation` = 3); `confirmado: true` → `200`, "reservado com
    sucesso… RSV-3DE0B09B"; autores dos eventos novos = `["user",
    "especialista_reservas", "especialista_reservas"]`; sequência de
    `function_response` de `reservar_area` = `[aguardando_confirmacao,
    nao_confirmada, aguardando_confirmacao, reservada]`; reservas = 1 item;
  - item 4: mesmo `id` → `409`, reservas continuam 1;
  - item 5: `id-inexistente` → `409`; `GET /sessoes/sessao-inexistente/eventos`
    → `404`. Total: 22 eventos.
  Conclusão: no 2.2.0, sem resumability, `Runner._find_agent_to_run` escolheu o
  último autor transferível (o especialista) e o processador de confirmação
  reexecutou a tool uma vez. **Nenhuma alavanca entra em uso**; F3.7 e F5.5
  seguem o texto do plano.
- **#5 · 2026-10-23 · desvio · Fase 0.** Duas vezes a **primeira** chamada ao
  especialista (`gemini-3.8-flash`) recebeu `503 UNAVAILABLE` ("This model is
  currently experiencing high demand") do Gemini; o cliente `google-genai` já
  repete internamente e ainda assim falhou; a API respondeu `500` e o turno
  parcial (user + transferência do `assistente`) ficou gravado na sessão. A
  repetição da mesma chamada 5 s depois funcionou e a sessão seguiu normal.
  Ações: tarefa nova **F5.11** (erro do modelo → `503` com `detail`), risco
  novo na Fase 5, e o `harness-live` repete chamadas 5xx até 3 vezes. Não é
  motivo para trocar de modelo; se virar frequente, D5 prevê
  `gemini-3.6-flash` pelo `.env`.
- **#6 · 2026-10-23 · decisão · harness.** Criados os cinco agentes do harness
  em `.claude/agents/` (`harness-simplificar`, `harness-revisar`,
  `harness-testes`, `harness-conformidade`, `harness-live`), o comando
  `/harness fase-N` em `.claude/skills/harness/SKILL.md` e `.claude/launch.json`
  para subir a API pelo app. A regra 12 e a seção "Harness de verificação"
  tornam o harness obrigatório no "Pronto quando" das fases 1 a 7. O
  `pyproject.toml` ganhou o grupo `dev` (pytest, pytest-asyncio, httpx) e a
  config do pytest (marca `gemini` para testes que chamam o modelo).
- **#7 · 2026-10-24 · harness · Fase 0.** Primeira rodada do harness, feita
  depois da implementação (os agentes ainda não apareciam como
  `subagent_type` nesta sessão; rodaram como `general-purpose` com a
  definição de `.claude/agents/<nome>.md` no prompt, como prevê o SKILL.md).

  | Agente | Veredito | Achados | Ação |
  |---|---|---|---|
  | harness-simplificar | PASSOU | 4 mudanças cosméticas (import unificado em `web.py`, `r`→`reserva` em dois lugares, comentário do `makedirs` em `agent.py`); duplicação proposital dos helpers JSON do spike deixada (sai em F2/F5.9) | aplicadas |
  | harness-revisar | ATENÇÃO | 0 alta / 2 média / 3 baixa. (1) média: com pendência aberta, se o especialista devolver a conversa à raiz e depois chegar a aprovação, `_find_agent_to_run` entrega à raiz, que não tem a tool → `ValueError` → 500 e pendência consumida; (2) média: na aprovação a tool reexecuta e grava **antes** da chamada ao modelo, então um 503 depois disso vira 500 com a ação feita; (3) baixa: `texto` vazio → 500; (4) baixa: `apartamento` vazio cria sessão que dá 404; (5) baixa: leitura-modificação-escrita do JSON de sessões do spike sem lock | (1) M5 obrigatório em F5.4 + defesa do autor em F5.5; (2) incorporado a F5.11; (3) e (4) corrigidos agora com `Field(min_length=1)` → 422; (5) esperado no spike, sai em F5.9 |
  | harness-testes | ATENÇÃO | `tests/` criado: 40 unit + 30 e2e, **67 passed / 0 failed / 3 skipped** (os 3 `gemini`, só com `HARNESS_GEMINI=1`); nenhum bug de produto; ATENÇÃO só porque os itens 1–4 de F0.5 dependem do modelo e ficaram nos testes pulados (cobertos pelo live) | mantido |
  | harness-conformidade | PASSOU | 29 atende / 0 parcial / 0 falta (6 "não se aplica ainda": regra 6, `especialista_regulamento`, `.env.example`, M5, M6, rota de visitantes); contrato das rotas do spike literal; evidências de F0.1–F0.7 reproduzidas no `.adk/` real; 2 notas cosméticas no texto de F0.1/F0.3 | notas corrigidas no plano |
  | harness-live | ATENÇÃO | 9 passos ok / 0 falhos, sessão `b2472a3e…`: retomada após reinício provada de novo (23 eventos antes e depois do reinício; aprovação `200` com `RSV-DCE9681F`; autores novos `["user", "especialista_reservas", "especialista_reservas"]`; `function_response` de `reservar_area` = `reservada`; reenvio `409`; `id-inexistente` `409`; sessão inexistente `404`; `apartamento` vazio `422`). **4 repetições por 503** "high demand" do `gemini-3.8-flash` (item 1: 1; item 3a: 3 de 3, e a 2ª tentativa gravou a `adk_request_confirmation` antes do 503, então a pendência existia nos eventos mas o cliente recebeu 500) | F5.11 ampliado (ver acima); decisão sobre o modelo levada ao Marcos |

  Linhas dos agentes: "harness-simplificar · fase-0 · PASSOU · 4 mudanças" ·
  "harness-revisar · fase-0 · ATENÇÃO · 0 alta / 2 média / 3 baixa" ·
  "harness-testes · fase-0 · ATENÇÃO · 67 passed / 0 failed / 3 skipped" ·
  "harness-conformidade · fase-0 · PASSOU · 29 atende / 0 parcial / 0 falta" ·
  "harness-live · fase-0 · ATENÇÃO · 9 passos ok / 0 falhos".

  Conclusão: a Fase 0 fica fechada; nenhum achado muda o desenho (topologia B,
  2.2.0, sem alavanca). Os dois achados médios do revisor são de robustez da
  API e já têm tarefa na Fase 5. **Ponto para decisão do Marcos (D5):** nas
  duas rodadas live desta noite, 6 de 9 primeiras chamadas ao
  `gemini-3.8-flash` deram 503; o fluxo do avaliador faz dezenas de chamadas.
  Opções: manter o 3.8 contando com F5.11 e a repetição pelo cliente, ou
  trocar `MODELO_ESPECIALISTAS` para `gemini-3.6-flash` no `.env`/`.env.example`
  (sem mudar código). Até a decisão, o plano segue com o 3.8.
- **#8 · 2026-10-25 · decisão · D5.** Marcos decidiu **manter
  `gemini-3.8-flash`** em `MODELO_ESPECIALISTAS` apesar dos 503 "high demand"
  vistos nas rodadas live da Fase 0 (Registro #5 e #7). A tolerância fica no
  código e no cliente: F5.11 (erro do modelo → `503` com `detail`, ou `200`
  quando o turno já deixou pendência ou gravou a tool) e a repetição da chamada
  pelo cliente (o `harness-live` e o `api.http` repetem 5xx até 3 vezes). A
  troca para `gemini-3.6-flash` continua disponível só pelo `.env`, sem mudar
  código, se o avaliador relatar instabilidade.
