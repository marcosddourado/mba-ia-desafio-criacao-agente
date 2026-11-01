# Decisões técnicas — Assistente do Residencial Aurora

> **Para quem é este arquivo.** Para o agente que vai escrever o plano de execução
> (`docs/plano-de-execucao.md`) e para os agentes que vão implementar e marcar o
> progresso. Ele complementa o enunciado em [`enunciado.md`](enunciado.md); nunca o
> substitui. Se este arquivo e o enunciado divergirem, o enunciado vence.
>
> **Padrão de referência.** Tudo aqui segue o projeto da disciplina em
> `/Users/macbook/Projects/mba-ia/mba-ia-dev-agents` (ADK 2.2.0, FastAPI,
> SQLAlchemy async, `App` + `Runner` + `SqliteSessionService`). A seção 1 diz o
> que copiar e de onde. Em dúvida de estilo, abra o arquivo de referência citado
> e imite.
>
> **Legenda de status.** 🔒 fixada pelo enunciado ou pelo padrão ·
> 🟡 proposta, aguardando decisão · ✅ decidida.
>
> **Estado em 2026-10-23.** Todas as decisões abertas (D1–D8) e os defaults
> menores (M1–M9) foram decididos pelo Marcos. Onde a decisão divergiu da
> recomendação (D1 e D6), o texto mantém a análise original e acrescenta um bloco
> **Decisão** com as consequências. Próximo passo: o agente de planejamento
> escreve `docs/plano-de-execucao.md` a partir deste arquivo e do `enunciado.md`,
> começando pela Fase 0 (seção 6).

---

## 0. Resumo

| # | Decisão | Status | Escolha recomendada / fixada |
|---|---|---|---|
| F1 | Linguagem e gerenciador | 🔒 | Python 3.12 + uv (`pyproject.toml` e `uv.lock` versionados) |
| F2 | Framework de agentes | 🔒 | Google ADK série 2, versão exata fixada (`google-adk===X.Y.Z`) |
| F3 | Modelos | 🔒 | Gemini via chave do Google AI Studio (`GOOGLE_API_KEY`) |
| F4 | Framework web | 🔒 (padrão) | FastAPI + uvicorn em `web.py`, porta 8000 |
| F5 | Contrato da API | 🔒 | Exatamente o do enunciado (rotas, campos, status) |
| F6 | Dados iniciais | 🔒 | `dados/` imutável; carregado para o armazenamento pelo comando de restauração |
| D1 | Versão do ADK | ✅ | **2.2.0** (a do curso, igual à referência). Recomendação original era 2.13.0; ver consequências em D1 |
| D2 | Topologia dos agentes | ✅ | **B** — principal roteia; `reservas` e `visitantes` em `chat` com as tools de confirmação; `regulamento` em `single_turn` |
| D3 | Serviço de sessão | ✅ | **SqliteSessionService** (o mesmo do `adk web`), arquivo em `.adk/` |
| D4 | Armazenamento do condomínio | ✅ | **SQLite + SQLAlchemy async** com índice único parcial; Postgres opcional por env |
| D5 | Modelos por agente | ✅ | **`gemini-3.5-flash-lite`** nos especialistas e **`gemini-3.1-flash-lite`** no principal, via `.env` (trocado em 2026-10-28; a decisão original era 3.8 e 3.5, ver D5) |
| D6 | Consulta ao regulamento | ✅ | **RAG com embeddings** (`gemini-embedding-001`, 1 artigo por chunk, índice em processo com numpy, resultado filtrado ao capítulo vencedor). Recomendação original era a tool por capítulo; ver D6 |
| D7 | Identidade da sessão | ✅ | **`user_id` = apartamento** + tabela própria `sessoes` para resolver `session_id` |
| D8 | Pendências e o 409 | ✅ | **Derivadas dos eventos** da sessão (pedido `adk_request_confirmation` sem resposta) |
| M1–M9 | Decisões menores | ✅ | Seção 5 — defaults do padrão, aceitos como estão |

---

## 1. O padrão a seguir: `mba-ia-dev-agents`

O projeto de referência não tem um "assistente de condomínio", mas tem cada peça
que este desafio precisa. A tabela diz de onde copiar o estilo.

| Aspecto | Onde está na referência | Como aplicar aqui |
|---|---|---|
| Layout de projeto | raiz: `web.py`, `db/`, `agents/`, `docs/`, `api.http`, `.env.example`, `docker-compose.yml`, `.vscode/settings.json` | Mesma raiz; `api.http` não é versionado (Registro #9): o Marcos pediu um local, só para teste manual, e ele está no `.gitignore`. `agents/residencial_aurora/` com `agent.py` (`root_agent` + `app`), `subagents/`, `tools/`. `db/` com `engine.py`, `models.py`, `repo.py`, `restaurar.py`. |
| Descoberta pelo `adk web` | `docs/01-adk-run-carregamento-de-agentes.md`: pasta = app, `agent.py` expõe `root_agent` ou `app` | `uv run adk web agents` continua funcionando para depurar transferências e confirmações. |
| Montagem do runtime | `web.py` (raiz): `App(root_agent=..., name=..., plugins=[...])`, `Runner(app=..., session_service=...)`, `SqliteSessionService(f"{CURRENT_PATH}/.adk/....db")` com `os.makedirs` | Idêntico. Um `App`, um `Runner`, um `session_service` global no módulo. |
| Leitura do stream de eventos | `web.py`: `_texto(event)`, `event.is_final_response()`, `event.get_function_responses()` | Mesmos helpers. A resposta do morador = texto do evento final; dado de máquina sai do `function_response`, nunca de parse do texto. |
| Pendência derivada dos eventos | `web.py::_aprovacao_pendente` (function call `adk_request_input` sem `function_response` do mesmo id) e o `409` em `/aprovacao` | Mesma técnica com `adk_request_confirmation` (seção 7). |
| Retomada por `FunctionResponse` | `web.py::responder_aprovacao`: `types.Part(function_response=types.FunctionResponse(id=..., name=..., response={...}))` em `Content(role="user")` | Igual, com `name="adk_request_confirmation"` e `response={"confirmed": bool}`. |
| Confirmação de tool | `agents/operador_conta_session_state/agent.py::cancelar_assinatura`: `if tool_context.tool_confirmation is None: tool_context.request_confirmation(hint=..., payload=...)`; depois `.confirmed` | Mesmo esqueleto em `reservar_area` (só se taxa > 0) e `autorizar_visitante`. |
| Dado de sessão nas tools | `operador_conta_session_state`: `create_session(state={"cliente_id": ...})`; tool lê `tool_context.state.get("cliente_id")`; nenhuma tool recebe `cliente_id` como argumento | `state={"apartamento": "101"}` na criação; nenhuma tool aceita `apartamento`. É a Garantia 2. |
| Coordenador + especialistas | `operador_conta_subagent/agent.py` (chat + `disallow_transfer_to_peers=True`), `docs/02-subagents.md` (quando usar `chat`/`single_turn`/`task`/`AgentTool`) | Regra do doc: tool com confirmação fica no principal ou num especialista `chat`; nunca atrás de `AgentTool` nem em `single_turn`. |
| Instrução curta no coordenador | `docs/02-subagents.md`: "o ADK injeta as `description`s dos especialistas" | Principal sem lista de regras; roteamento pela `description` de cada especialista. |
| Banco com SQLAlchemy async | `db/engine.py` (`create_async_engine`, `DATABASE_URL` com default sqlite+aiosqlite), `db/models.py` (`DeclarativeBase`, `Mapped`), `db/repo.py` (`async with async_session.begin()`), `db/reset.py` | Mesmos arquivos. `restaurar.py` no lugar de `reset.py`: recria tabelas e carrega `dados/*.json`. |
| Tratamento de erro de tool | `ticket_receptionist/agent.py::_handle_tool_error` via `on_tool_error_callback` | Copiar: `ValueError` vira `{"status": "error", "message": ...}`; o resto vira mensagem genérica. |
| Retry de resposta vazia | `ticket_receptionist/plugins.py::ModelRetryPlugin` | Copiar o plugin inteiro e registrar no `App`. |
| Variáveis de ambiente | `.env.example` comentado por seção; `env.py` com `load_dotenv()` | Mesmo formato. Lista em M8. |
| Requisições prontas | `api_tickets.http` com variáveis de resposta (`{{sessao.response.body.$.session_id}}`) | Não entra: o enunciado não pede (Registro #9 do plano). A Fase 6 roda os 14 passos com `curl`. |
| Modelos por papel | `root_agent` em `gemini-3.1-flash-lite`, especialistas em `gemini-3.5-flash` | Mesma ideia de "principal leve, especialista forte" (D5). |

---

## 2. Decisões já fixadas pelo enunciado (sem escolha)

- Python 3.12 ou superior, projeto gerenciado por uv, `pyproject.toml` e `uv.lock` versionados (`.python-version` = `3.12`, como na referência).
- Google ADK série 2, versão igual ou superior a 2.2.0, **exata** no `pyproject.toml` (`google-adk===X.Y.Z`, mesmo operador da referência).
- Modelos Gemini com chave do Google AI Studio. Quantidade de chamadas do avaliador: "algumas dezenas".
- API em `http://localhost:8000` seguindo o contrato literal: `POST /sessoes` (201), `POST /sessoes/{id}/mensagens` (200), `POST /sessoes/{id}/confirmacoes` (200 ou 409), `GET /sessoes/{id}/eventos` (200), `GET /apartamentos/{n}/reservas`, `GET /apartamentos/{n}/visitantes`; `404` para sessão inexistente.
- Um agente principal e **no mínimo dois** especialistas; reservas e visitantes lidos e gravados por tools.
- `dados/` idêntico ao repositório base. O estado mutável mora fora de `dados/`.
- `.env` fora do Git; `.env.example` versionado só com os nomes.
- As cinco garantias implementadas em código e apontadas no README final (seções Arquitetura, Garantias, Como rodar).
- Fora de escopo: autenticação, pagamento, regras de antecedência/horário/capacidade, testes automatizados, deploy.

---

## 3. O que o código do ADK diz sobre a "armadilha" da confirmação

O enunciado avisa: a rota de confirmações aceita a resposta, nada falha e a ação
não executa. Lendo o ADK 2.2.0 instalado na referência (`.venv/lib/python3.12/site-packages/google/adk/`),
o mecanismo é este:

1. **Quem pede.** A tool chama `tool_context.request_confirmation(hint=, payload=)`
   (`agents/context.py`). O flow gera um evento com uma function call chamada
   `adk_request_confirmation` (`flows/llm_flows/functions.py::generate_request_confirmation_event`),
   cujos `args` são `{"originalFunctionCall": {...}, "toolConfirmation": {"hint", "confirmed": false, "payload"}}`.
   O **autor desse evento é o agente dono da tool**, e o id da call entra em `long_running_tool_ids`.
2. **Quem responde.** O cliente manda um `FunctionResponse` com `id` = id dessa call,
   `name = "adk_request_confirmation"` e `response = {"confirmed": true|false}`
   (formato documentado em adk.dev; `ToolConfirmation.from_response_dict` aceita o dict direto).
3. **Quem retoma.** `Runner._find_agent_to_run` (`runners.py`) escolhe o agente do turno:
   - se o app tem `ResumabilityConfig(is_resumable=True)` e a última mensagem é uma
     function response, vai para o **autor da function call correspondente**;
   - senão, varre os eventos de trás para frente e pega o **último autor não-usuário**
     se ele for "transferível" (nenhum agente no caminho até a raiz com
     `disallow_transfer_to_parent=True`); caso contrário cai na **raiz**;
   - se a raiz tem **qualquer** sub-agente em `mode="task"`, a raiz roda sempre e a
     delegação passa pelo wrapper de task.
4. **Quem executa.** O processador `flows/llm_flows/request_confirmation.py`
   (`_RequestConfirmationLlmRequestProcessor`) roda **dentro do flow do agente escolhido**:
   lê a última mensagem do usuário, acha o `originalFunctionCall` nos eventos **do
   branch atual** e reexecuta a tool com `tool_context.tool_confirmation` preenchido.

Logo, a ação não executa quando o Runner entrega a resposta a um agente diferente
do que pediu a confirmação. As três formas de errar que o próprio código mostra:

- especialista com `disallow_transfer_to_parent=True` → não é transferível → a raiz
  recebe a resposta e não acha a function call dela;
- tool com confirmação atrás de `AgentTool` ou em `single_turn` → branch isolado;
- especialista `task` → resume via wrapper, caminho diferente do `chat`.

E o que mudou depois do 2.2.0 (changelog oficial, seção 8): 2.8.0 "checked every
function response when inferring which invocation to resume"; 2.9.0 "skipped rewound
invocations when resuming an agent in `_find_agent_to_run`"; 2.10.0 "require agent
authorship before resume-dispatching a function call"; 2.12.0 "centralize resume
routing decision", "route user FunctionResponses to sub-agents when is_resumable is
False", "run a confirmed tool once per approval"; 2.13.0 "run a resumed sub-agent
again when control transfers back to it", "keep sticky routing when a sub-agent runs
in task mode". Ou seja: o problema do enunciado foi corrigido em série entre 2.8 e 2.13.

Sobre persistência: a página oficial de confirmação diz que `DatabaseSessionService`
e `VertexAiSessionService` **não são suportados** pela feature. O `SqliteSessionService`
é o que o `adk web` usa e grava cada evento inteiro como JSON
(`event.model_dump_json(exclude_none=True)` em `sessions/sqlite_session_service.py`),
então `long_running_tool_ids` e os `args` da confirmação sobrevivem ao reinício. O
enunciado confirma: "a confirmação funcionou com sessão persistida em SQLite quando a
resposta chegou ao agente certo".

---

## 4. Decisões em aberto

### D1 — Versão exata do ADK ✅

**Contexto.** O curso usa 2.2.0; os autores do desafio testaram 2.2.0 e 2.9.1 e
tropeçaram no roteamento da retomada; a mais nova no PyPI é 2.13.0 (2026-10-22).
Mudanças marcadas como *breaking* entre 2.2.0 e 2.13.0: 2.6.0 (artefatos
namespaced por app; runtime LangGraph), 2.7.0 (`pyarrow` sai do extra `gcp`),
2.13.0 (OpenTelemetry GenAI v2 por padrão). Nenhuma toca o que usamos
(`Agent`, `App`, `Runner`, `SqliteSessionService`, `request_confirmation`).

| Opção | Prós | Contras |
|---|---|---|
| **A. 2.2.0** (a do curso) | Igual à referência: a doc local (`docs/01..03`) descreve exatamente este código; zero surpresa de API. | Carrega os bugs de roteamento que o enunciado descreve; exige `ResumabilityConfig` ou cuidado extra com `disallow_transfer_*`; a feature foi "best effort". |
| **B. 2.12.0** (2026-10-13) | Traz o lote principal de correções ("centralize resume routing", "route user FunctionResponses to sub-agents when is_resumable is False", "run a confirmed tool once per approval"); 10 dias de uso público. | Não tem os ajustes de 2.13.0 para sub-agente retomado quando o controle volta a ele e para roteamento "sticky". |
| **C. 2.13.0** (2026-10-22, mais nova) | Tudo de B mais as correções de retomada de sub-agente e de roteamento após pausa; é a versão que o avaliador provavelmente instala se não fixarmos. | Lançada ontem: menos tempo de exposição; única *breaking* é o default de OTel (irrelevante aqui). |

**Recomendação original: C (2.13.0)**, porque o risco central do desafio é a
retomada da confirmação e é isso que 2.12/2.13 corrigem.

**Decisão (Marcos, 2026-10-23): A (2.2.0)**, a versão do curso. Fixar com
`google-adk===2.2.0` (mesmo operador do `pyproject.toml` da referência) e `uv lock`.
Consequências para o plano:

- a doc local da referência (`docs/01..03`) e o código lido na seção 3 descrevem
  **exatamente** a versão que vamos usar: o plano pode citá-los como fonte;
- as três formas de errar da seção 3 passam a ser **regras de implementação**:
  nenhum especialista com `disallow_transfer_to_parent=True`; nenhum sub-agente em
  `mode="task"` pendurado na raiz; tool com confirmação só nos especialistas `chat`;
- o spike da seção 6 é obrigatório **antes** de escrever o resto, e sua escada de
  alavancas (seção 6) é a ordem de tentativa; subir para 2.12.0/2.13.0 fica
  registrado como plano B, a ser proposto ao Marcos só se todas as variantes em
  2.2.0 falharem;
- `ResumabilityConfig` no 2.2.0 avisa que a retomada é *best effort* com semântica
  *at-least-once* para a tool retomada: se o spike exigir ativá-la, as tools de
  escrita precisam ser idempotentes (a reserva já é, pelo índice único; o visitante
  fica, pelo `UNIQUE(apartamento, nome, data)` de D4).

### D2 — Topologia dos agentes e onde mora a confirmação ✅

**Contexto.** Mínimo de dois especialistas; reservas e visitantes via tools; duas
ações pedem confirmação (`reservar_area` com taxa > 0, `autorizar_visitante`).
A confirmação precisa voltar ao agente que a pediu (seção 3).

| Opção | Desenho | Prós | Contras |
|---|---|---|---|
| **A. Confirmação no principal** | Principal (`chat`) tem todas as tools de reservas/visitantes; especialistas `single_turn`: `regulamento` (consulta) e `agenda` (disponibilidade e listagens). | Retomada trivial: `_find_agent_to_run` devolve a raiz em qualquer versão; sem transferências; cache de prefixo preservado. | Divisão de trabalho artificial (o principal faz quase tudo e os especialistas só leem); prompt do principal cresce; foge do padrão da aula (HITL em especialista `chat`). |
| **B. Especialistas `chat` donos das tools** | Principal roteia; `especialista_reservas` (`chat`: listar, verificar disponibilidade, reservar, cancelar), `especialista_visitantes` (`chat`: listar, autorizar), `especialista_regulamento` (`single_turn`: `consultar_regulamento`). Especialistas **sem** `disallow_transfer_to_parent`; `disallow_transfer_to_peers=True` como na referência. | É o padrão da aula (`operador_conta_subagent` + `docs/02`: "chat é o caminho recomendado para confirmação humana"); cada especialista tem prompt e tools enxutos; o README fica natural. | Depende do roteamento da retomada (por isso D1 = 2.13.0 e o spike); transferências custam chamadas extras e o aviso de cache; pedidos mistos ("reservas e visitantes") passam por dois especialistas. |
| **C. Especialistas `task`** | Igual a B, mas `mode="task"` com `disallow_transfer_*=True` e instrução "não chame `finish_task` com confirmação pendente". | Principal mantém o controle; saída estruturada. | `docs/02` classifica como "funciona com cuidado": o modelo pode encerrar a task antes da aprovação; no 2.2.0 a raiz roda sempre que há task sub-agent e a retomada passa pelo wrapper — caminho menos testado para confirmação. |

**Decisão: B** (recomendada e aceita). Como D1 ficou em 2.2.0, as condições
viram obrigações:

- especialistas `chat` **sem** `disallow_transfer_to_parent` (é o que os mantém
  "transferíveis" para `_find_agent_to_run`) e com `disallow_transfer_to_peers=True`
  (roteamento sempre via principal, como na referência);
- nenhum sub-agente `task` na raiz (no 2.2.0 a presença de um já muda o caminho da
  retomada para a raiz);
- não ativar `ResumabilityConfig` de início: com especialistas transferíveis o
  Runner já escolhe o último autor; ativar é a primeira alavanca se o spike mostrar
  a resposta chegando à raiz;
- o spike da seção 6 passa **com sessão persistida e depois de reiniciar a API**
  antes de implementar o restante;
- fallback: topologia **A** sem mudar tools, banco ou API (as tools são as mesmas;
  muda só quem as carrega).

### D3 — Serviço de sessão ✅

| Opção | Prós | Contras |
|---|---|---|
| **A. `SqliteSessionService`** (`google.adk.sessions.sqlite_session_service`) | Mesmo serviço do `adk web`/`adk run` — é onde a confirmação foi testada em aula; grava o evento inteiro em JSON; arquivo local sem serviço externo; já usado em `web.py` da referência. | Um arquivo SQLite por API (ok para o desafio); não é re-exportado da raiz do pacote. |
| **B. `DatabaseSessionService`** (`sqlite+aiosqlite` ou Postgres) | Mesma interface para Postgres; já usada no `operador_conta_session/web.py`. | A doc oficial de confirmação diz que **não é suportado**; eventos com `actions` picklados (`sessions/schemas/v0.py`) — risco na retomada após reinício. |
| **C. `InMemorySessionService`** | Zero infra. | Perde tudo no reinício: reprova a Garantia 3. Descartada. |

**Decisão: A** (recomendada e aceita). Arquivo em `.adk/sessoes.db` (pasta ignorada pelo Git, como
na referência). O comando de restauração apaga esse arquivo (M3).

### D4 — Armazenamento dos dados do condomínio e exclusividade da reserva ✅

**Contexto.** Garantia 5: duas aprovações simultâneas para a mesma área e data;
exclusividade "no instante da gravação", resposta normal (200) para quem perde.
Códigos de reserva nunca se repetem, inclusive de canceladas.

| Opção | Como garante a exclusividade | Prós | Contras |
|---|---|---|---|
| **A. SQLite + SQLAlchemy async (`aiosqlite`)** | Índice único parcial `(area, data) WHERE status = 'ativa'` (`Index(..., unique=True, sqlite_where=...)`); `IntegrityError` capturado na tool vira `{"status": "indisponivel"}`. Linhas canceladas ficam (status), então `UNIQUE(codigo)` cobre o histórico. | Mesmo `db/` da referência; sem serviço externo; SQLite 3.53 suporta índice parcial; escritas serializadas pelo próprio SQLite. | Concorrência de escrita é por lock de arquivo: configurar `timeout` no `connect_args` e `PRAGMA journal_mode=WAL` para não receber "database is locked". |
| **B. PostgreSQL (docker-compose) + `asyncpg`** | Mesmo índice único parcial (`postgresql_where`). | Concorrência real; é o que o `docker-compose.yml` da referência já sobe. | Exige Docker no ambiente do avaliador (permitido, mas é mais um comando e um ponto de falha); mais setup para o mesmo resultado. |
| **C. Arquivos JSON em `.dados/` + lock de arquivo** | `filelock`/`fcntl` em volta de ler-verificar-gravar. | Simples de explicar. | A exclusividade mora num lock, não numa restrição do armazenamento; sem transação; reescreve o arquivo inteiro a cada mudança; foge do padrão. |

**Decisão: A** (recomendada e aceita), mantendo `DATABASE_URL` no `.env` para trocar por Postgres
(B) sem mudar código, como a referência faz. Modelos: `reservas(codigo PK, apartamento,
area, data, status, criado_em, cancelado_em)`, `visitantes(id, apartamento, nome, data,
criado_em)` com `UNIQUE(apartamento, nome, data)` (torna `autorizar_visitante`
idempotente), `sessoes(session_id PK, apartamento, criado_em)` (D7). Arquivo:
`.adk/condominio.db`.

### D5 — Modelos Gemini por agente ✅

**Contexto.** A página oficial de modelos lista como estáveis `gemini-3.8-flash`
("engineered for ... autonomous agents"), `gemini-3.6-flash`, `gemini-3.5-flash-lite`
e `gemini-3.1-flash-lite`, e diz: "For any new projects, use our latest models: 3.5
Flash-Lite or 3.8 Flash". `gemini-3.5-flash` (usado na referência) não aparece mais
na tabela. Limites do free tier não são publicados: aparecem só no AI Studio do projeto.
Limites são por modelo, então usar dois modelos divide a cota.

| Opção | Prós | Contras |
|---|---|---|
| **A. `gemini-3.8-flash` em todos** | Melhor tool calling e leitura do regulamento; um só limite para acompanhar. | Mais caro por chamada; toda a cota do fluxo (dezenas de chamadas) num bucket só. |
| **B. `gemini-3.8-flash` nos especialistas + `gemini-3.5-flash-lite` no principal** | Principal só roteia (barato e rápido); especialistas, que chamam tools e interpretam datas, ficam no modelo forte; divide a cota em dois buckets; é o desenho da referência. | Dois modelos para configurar; o principal "lite" pode errar roteamento em pedidos ambíguos (mitigado por `description`s claras). |
| **C. `gemini-3.5-flash-lite` em todos** | Mais barato e com limites mais folgados. | Tool calling e extração de "20h" do capítulo com modelo leve: mais retries e erros de data. |

**Decisão: B** (recomendada e aceita), configurável no `.env`: `MODELO_PRINCIPAL=gemini-3.5-flash-lite`
e `MODELO_ESPECIALISTAS=gemini-3.8-flash`. Se o AI Studio do Marcos mostrar cota
apertada para o 3.8, trocar o especialista para `gemini-3.6-flash` sem mexer no código.

**Atualização 2026-10-28 (Marcos).** Os padrões de `env.py` e `.env.example`
passaram a `MODELO_PRINCIPAL=gemini-3.1-flash-lite` e
`MODELO_ESPECIALISTAS=gemini-3.5-flash-lite`, os que o Marcos já usava no `.env`
local. Na prática é a opção C com dois modelos "lite" (principal mais leve que o
especialista). Contexto: o `gemini-3.8-flash` deu 503 "high demand" em 6 de 9
primeiras chamadas na Fase 0 (plano, Registro #7). Riscos que ficam, os da
opção C: tool calling e datas com modelo leve → mais retries (o
`ModelRetryPlugin` cobre resposta vazia, não 503) e roteamento do principal em
pedido misto. Voltar ao 3.8 continua sendo só editar os dois valores no `.env`
(ou nos defaults). O texto acima fica como histórico da decisão original.

### D6 — Consulta ao regulamento (Garantia 4) ✅

**Contexto.** `dados/regulamento.md` tem 14 capítulos (`## Capítulo N: Título`),
~44 KB. Nenhum evento pode conter trechos de capítulos de outros assuntos; o
principal não recebe o regulamento na instrução. Passo 12 pergunta a piscina aos
domingos (Capítulo IV, Art. 22, II: "das 9h às 20h").

| Opção | Prós | Contras |
|---|---|---|
| **A. Uma tool `consultar_regulamento(assunto)` que escolhe o capítulo em código** | O código divide o arquivo pelos `## Capítulo`, pontua cada capítulo pelas palavras do `assunto` (título pesa mais que corpo) e devolve **um** capítulo; sem match claro devolve só o sumário (títulos) e aceita `capitulo=N` na chamada seguinte. Uma chamada ao modelo; o evento carrega só o capítulo do assunto. | Heurística de palavras pode empatar em perguntas vagas (por isso o fallback do sumário). |
| **B. Duas tools: `listar_capitulos()` e `ler_capitulo(numero)`** | O modelo escolhe pelo título; nenhuma heurística. | Duas rodadas de tool por pergunta (mais chamadas e latência); o sumário entra nos eventos (títulos, não trechos — aceitável, mas a mais). |
| **C. RAG com embeddings (`gemini-embedding-001`) por artigo** | Busca semântica. | Dependência e índice extras, chamadas de embedding, chunks que cruzam capítulos (risco direto na Garantia 4); overkill para 14 capítulos. |

**Recomendação original: A** (tool que escolhe o capítulo em código).

**Decisão (Marcos, 2026-10-23): C — RAG com embeddings.** Para que o RAG não
quebre a Garantia 4, o desenho é este (sub-decisões tomadas pelo padrão "menos
dependências", contestáveis):

- **Chunk = um artigo.** O regulamento tem 96 artigos (`**Art. N.**` até o próximo)
  em 14 capítulos; cada chunk carrega `capitulo` (número e título) e `artigo`.
  Um chunk nunca cruza capítulo, o que elimina o risco apontado na tabela.
- **Embeddings:** `gemini-embedding-001` (estável, só texto, aceita
  `task_type`), com `task_type="RETRIEVAL_DOCUMENT"` nos artigos e
  `"RETRIEVAL_QUERY"` na pergunta, `output_dimensionality=768` e normalização
  manual (`v / np.linalg.norm(v)`, obrigatória nesse modelo fora de 3072 dims).
  Chamada: `client.models.embed_content(model=..., contents=[...], config=types.EmbedContentConfig(...))`
  do `google-genai`, que já é dependência do ADK (2.8.0 instalado com o 2.2.0).
  Modelo configurável em `MODELO_EMBEDDINGS`; a alternativa `gemini-embedding-2`
  (recomendada pelo Google para trabalho novo, auto-normaliza) não usa `task_type`
  e sim prefixos `task: search result | query: ...` / `title: ... | text: ...`.
- **Índice em processo** com `numpy` (matriz 96×768) gravado em
  `.adk/regulamento.index.json` com os metadados e o hash do `regulamento.md`
  (invalida se o arquivo mudar). Construído **sob demanda na primeira consulta**
  (o comando de restauração continua offline e não depende da API) e reaproveitado
  depois; cerca de 96 textos embedados uma única vez, em lotes.
  Vector DBs (chromadb, sqlite-vec, `LlamaIndexRetrieval` do ADK) foram descartados:
  infra e dependências extras para 96 vetores.
- **Busca com filtro por capítulo.** `consultar_regulamento(pergunta)` embeda a
  pergunta, calcula cosseno contra os 96 artigos, pega os `k=5` melhores,
  **agrupa por capítulo e escolhe o capítulo com maior soma de similaridade**, e
  devolve só os artigos desse capítulo que estão no top-k, com o título do capítulo.
  É essa filtragem que mantém a garantia: nenhum trecho de outro capítulo entra no
  evento da tool. Se a maior similaridade ficar abaixo de um limiar (calibrar no
  spike, ~0.5), a tool devolve só o sumário (títulos) e pede para reformular.
- **Especialista** `especialista_regulamento` em `mode="single_turn"`: recebe a
  pergunta como entrada, chama a tool, responde; o principal repassa e nunca
  recebe o regulamento na instrução.
- **Dependência nova:** `numpy` no `pyproject.toml`. **Custo:** 1 chamada de
  embedding por pergunta no fluxo do avaliador, mais a construção única do índice.
- **Atualização 2026-10-31 (Marcos pediu melhorar a recuperação).** Medido com 28
  perguntas do regulamento e 8 fora de assunto: `gemini-embedding-001` acerta
  capítulo e artigo em 28/28, mas a folga entre o pior acerto e o melhor fora de
  assunto é de +0.055 (a pergunta do cachorro na piscina marcava 0.699);
  `gemini-embedding-2` também acerta 28/28 com folga +0.095 (cachorro 0.727).
  O padrão passa a `MODELO_EMBEDDINGS=gemini-embedding-2` e `LIMIAR = 0.66`.
  Sobreposição com o fim do artigo anterior, só dentro do capítulo, foi
  implementada (`SOBREPOSICAO`, caracteres) mas fica em 0: não melhorou o
  ranking de forma consistente (+0.009 de folga no 001, −0.014 no 2; incluir o
  artigo seguinte piorou). Registro #15 do plano.
- **Prova no README:** apontar o chunker por artigo, o filtro por capítulo e o
  evento da tool no passo 12 (só Capítulo IV).

### D7 — Identidade da sessão e de onde a tool tira o apartamento (Garantia 2) ✅

**Contexto.** O contrato só carrega `session_id`, mas `session_service.get_session`
exige `app_name`, `user_id` e `session_id`. O apartamento é definido na criação e
nunca vem do modelo.

| Opção | Prós | Contras |
|---|---|---|
| **A. `user_id` = apartamento + tabela `sessoes(session_id, apartamento)` no banco do condomínio; `state={"apartamento": ...}` na criação** | Semântica fiel ("o apartamento representa o morador autenticado"); `404` resolvido na tabela; permite listar sessões por apartamento; o estado `user:` fica por apartamento. | Duas leituras por requisição (tabela e sessão); uma tabela a mais. |
| **B. `user_id` constante (ex.: `"morador"`) e apartamento só no `state`** | Sem tabela extra; `get_session` direto. | `user_id` perde significado; estado `user:` seria compartilhado entre todos (não usamos, mas é uma armadilha latente). |
| **C. Apartamento embutido no `session_id` (ex.: `101-<uuid>`)** | Sem tabela e sem lookup. | Vaza estrutura no id; parse de string como fonte de verdade; qualquer um forja `302-...`. |

**Decisão: A** (recomendada e aceita). As tools leem `tool_context.state["apartamento"]` e nenhuma
aceita `apartamento` como parâmetro (passo 15 confere isso). `verificar_disponibilidade`
devolve só `{"area", "data", "disponivel": bool}`; `listar_*` filtram pelo apartamento
do estado; `cancelar_reserva` só cancela se `reserva.apartamento == estado`, e responde
"não encontrada" sem revelar o dono.

### D8 — Como listar `confirmacoes_pendentes` e decidir o 409 (Garantia 1) ✅

| Opção | Prós | Contras |
|---|---|---|
| **A. Derivar dos eventos da sessão** (function calls `adk_request_confirmation` sem `function_response` de mesmo id) | Fonte única de verdade; idempotente por construção (respondida = tem `function_response` gravado pelo Runner → some da lista → `409` no reenvio); sobrevive ao reinício; é o que `web.py` da referência faz com `adk_request_input`. | Varre os eventos a cada requisição (sessões pequenas, custo irrelevante). |
| **B. Tabela própria `confirmacoes`** gravada pela tool e marcada na rota | Consulta direta. | Duas fontes para manter em sincronia; a tool teria de conhecer o id da call de confirmação, que o ADK gera depois do retorno dela. |
| **C. Chave no `state` da sessão** | Simples de ler. | Mesmo problema de sincronia de B; `state` não é atômico entre invocações (doc oficial). |

**Decisão: A** (recomendada e aceita). `id` = id da function call `adk_request_confirmation`;
`acao` = `args["originalFunctionCall"]["name"]`; `detalhes` = `args["toolConfirmation"]["payload"]`
(a tool passa `payload={"area": ..., "data": ...}` ou `{"nome": ..., "data": ...}`).

---

## 5. Decisões menores já tomadas pelo padrão ✅ (aceitas em 2026-10-23)

| # | Decisão | Default |
|---|---|---|
| M1 | Subida da API | `uv run uvicorn web:app --port 8000` (igual à referência). Sem `--reload` no README. |
| M2 | Nomes | app `residencial_aurora`; agentes `assistente` (principal), `especialista_reservas`, `especialista_visitantes`, `especialista_regulamento`; tools `listar_minhas_reservas`, `verificar_disponibilidade(area, data)`, `reservar_area(area, data)`, `cancelar_reserva(codigo)`, `listar_meus_visitantes`, `autorizar_visitante(nome, data)`, `consultar_regulamento(assunto, capitulo=None)`. |
| M3 | Restauração | `uv run python -m db.restaurar`: recria as tabelas, carrega `dados/reservas.json` e `dados/visitantes.json` e **apaga** `.adk/sessoes.db` (sessões antigas poderiam apontar para reservas que não existem mais). Não toca no índice do regulamento (`.adk/regulamento.index.json`), que é cache reconstruível. |
| M4 | Código de reserva | `RSV-` + 8 hex maiúsculos de `uuid4` (como `TCK-` na referência). Único por construção; linhas canceladas permanecem com `status='cancelada'`. |
| M5 | Nova mensagem com confirmação pendente | `409` com `detail` e a lista de pendências. Evita pendência duplicada para a mesma ação. (Alternativa: aceitar e manter a pendência listada.) |
| M6 | Apartamento inexistente | `POST /sessoes` e rotas de verificação respondem `404` (`apartamentos.json` é a lista válida). |
| M7 | Validações nas tools | `area` precisa existir em `areas.json`; `data` no formato `AAAA-MM-DD`; erro de validação vira `{"status": "error", "message"}` pelo `on_tool_error_callback`. Datas passadas, horários e capacidade ficam fora de escopo. |
| M8 | `.env.example` | `GOOGLE_API_KEY=`, `MODELO_PRINCIPAL=`, `MODELO_ESPECIALISTAS=`, `MODELO_EMBEDDINGS=` (default `gemini-embedding-001`), `DATABASE_URL=` (comentado, default sqlite), `SESSION_DB_PATH=` (comentado, default `.adk/sessoes.db`). `.gitignore` ganha `.adk/`, `*.db`. |
| M9 | `resposta` da API | Texto do último evento com `is_final_response()`; string vazia quando o turno parou na confirmação sem texto. `GET /eventos` devolve `event.model_dump(mode="json", exclude_none=True)` de cada evento, em ordem. |

---

## 6. Validação obrigatória antes de implementar tudo (Fase 0 do plano)

Montar um spike mínimo (`web.py` + `agents/` enxutos, 1 especialista `chat` com uma
tool que pede confirmação, `SqliteSessionService`) e provar, nesta ordem:

1. mensagem → `confirmacoes_pendentes` com 1 item e nada gravado;
2. `confirmado: false` → nada gravado, lista vazia;
3. pedido de novo → **parar a API (Ctrl+C) e subir de novo** → `confirmado: true` → gravado **uma vez**;
4. reenviar o mesmo `id` → `409` e continua gravado uma vez;
5. `id` inexistente → `409`;
6. duas sessões, duas aprovações em paralelo (`curl ... & curl ... & wait`) → dois `200`, uma reserva;
7. pergunta "até que horas a piscina funciona aos domingos?" → resposta com "20h" e
   o evento da tool `consultar_regulamento` contendo só artigos do Capítulo IV.

Se o passo 3 falhar no ADK 2.2.0, tentar nesta ordem e registrar cada resultado no
plano:

1. conferir que o especialista não tem `disallow_transfer_to_parent=True` e que a
   raiz não tem sub-agente `task` (seção 3);
2. ativar `ResumabilityConfig(is_resumable=True)` no `App` (muda o roteamento para
   "autor da function call") e passar `invocation_id` do evento da confirmação em
   `runner.run_async`;
3. propor ao Marcos subir o ADK para 2.12.0 ou 2.13.0 (correções listadas na
   seção 3), mantendo tudo o mais;
4. topologia A (D2): mover as tools de confirmação para o principal.

---

## 7. Mapa API ↔ ADK (para o plano e a implementação)

```python
# detectar pendências (D8)
REQUEST_CONFIRMATION = "adk_request_confirmation"
pendentes: dict[str, dict] = {}
for event in sessao.events:
    for part in (event.content.parts if event.content and event.content.parts else []):
        fc = part.function_call
        if fc and fc.name == REQUEST_CONFIRMATION and fc.id:
            args = fc.args or {}
            pendentes[fc.id] = {
                "id": fc.id,
                "acao": (args.get("originalFunctionCall") or {}).get("name"),
                "detalhes": (args.get("toolConfirmation") or {}).get("payload") or {},
            }
        fr = part.function_response
        if fr and fr.name == REQUEST_CONFIRMATION and fr.id:
            pendentes.pop(fr.id, None)

# responder (Garantia 1) — 409 se o id não está em `pendentes`
conteudo = types.Content(
    role="user",
    parts=[types.Part(function_response=types.FunctionResponse(
        id=confirmacao_id, name=REQUEST_CONFIRMATION,
        response={"confirmed": confirmado},
    ))],
)
async for event in runner.run_async(user_id=apartamento, session_id=session_id, new_message=conteudo):
    ...
# depois do run, reler a sessão e montar {"resposta", "confirmacoes_pendentes"} de novo
```

```python
# tool com confirmação (padrão da referência)
async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    apartamento = tool_context.state["apartamento"]          # Garantia 2
    taxa = areas[area].taxa
    if taxa > 0 and tool_context.tool_confirmation is None:  # Garantia 1
        tool_context.request_confirmation(
            hint=f"Reservar {area} em {data} gera cobrança de R$ {taxa:.2f}.",
            payload={"area": area, "data": data, "taxa": taxa},
        )
        return {"status": "aguardando_confirmacao"}
    if taxa > 0 and not tool_context.tool_confirmation.confirmed:
        return {"status": "nao_confirmada"}
    try:
        reserva = await repo.criar_reserva(apartamento, area, data)   # Garantia 5: UNIQUE parcial
    except IntegrityError:
        return {"status": "indisponivel", "area": area, "data": data}
    return {"status": "reservada", "codigo": reserva.codigo}
```

```python
# consulta ao regulamento (D6) — esqueleto
async def consultar_regulamento(pergunta: str) -> dict:
    indice = await IndiceRegulamento.carregar()            # .adk/regulamento.index.json ou constrói
    consulta = await indice.embedar(pergunta, task_type="RETRIEVAL_QUERY")
    top = indice.mais_similares(consulta, k=5)             # [(artigo, capitulo, score)]
    if not top or top[0].score < LIMIAR:
        return {"status": "sem_resultado", "capitulos": indice.sumario()}
    capitulo = max(indice.capitulos(top), key=lambda c: soma_scores(top, c))
    trechos = [t for t in top if t.capitulo == capitulo]   # Garantia 4: só um capítulo
    return {"capitulo": capitulo.titulo, "artigos": [t.texto for t in trechos]}
```

---

## 8. Fontes consultadas

- Projeto de referência: `/Users/macbook/Projects/mba-ia/mba-ia-dev-agents` (`web.py`, `db/*`, `agents/operador_conta_*`, `agents/ticket_receptionist/*`, `docs/01..03`).
- Código do ADK 2.2.0 instalado na referência: `google/adk/runners.py` (`_find_agent_to_run`, `_resolve_invocation_id`), `flows/llm_flows/functions.py`, `flows/llm_flows/request_confirmation.py`, `agents/context.py`, `apps/_configs.py`, `sessions/sqlite_session_service.py`, `sessions/schemas/v0.py`.
- Context7 `/google/adk-python`: guias de sessão (`DatabaseSessionService`, `SqliteSessionService`, limitações de `state`), `ResumabilityConfig`, `request_confirmation`/`ToolConfirmation`, modos `chat`/`task`/`single_turn`, `disallow_transfer_*`.
- Documentação oficial: https://adk.dev/tools-custom/confirmation/ (formato da resposta; "DatabaseSessionService is not supported by this feature").
- Changelog oficial: https://raw.githubusercontent.com/google/adk-python/refs/heads/main/CHANGELOG.md (2.3.0 → 2.13.0).
- PyPI: https://pypi.org/project/google-adk/ (última versão 2.13.0; extras `db` = `sqlalchemy[asyncio]`).
- Modelos Gemini: https://ai.google.dev/gemini-api/docs/models e https://ai.google.dev/gemini-api/docs/rate-limits (limites do free tier só no AI Studio).
- Embeddings: https://ai.google.dev/gemini-api/docs/embeddings (`gemini-embedding-001` com `task_type`; `gemini-embedding-2` com prefixos; normalização manual fora de 3072 dims no 001).
- SQLAlchemy 2.0 (Context7 `/websites/sqlalchemy_en_20_core`): `UniqueConstraint`, `Index(unique=True, sqlite_where=..., postgresql_where=...)`, tratamento de `IntegrityError`.
- Ambiente local: uv 0.12.21, CPython 3.12.13 (uv), SQLite 3.53.1, Docker 27.4 com Compose v2.31.
