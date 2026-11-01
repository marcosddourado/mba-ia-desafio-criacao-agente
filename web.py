"""API do assistente do Residencial Aurora (contrato do enunciado).

Rodar:

    uv run uvicorn web:app --port 8000

Endpoints:

    POST /sessoes                          cria a sessão de um apartamento (201; 404 se não existe)
    POST /sessoes/{id}/mensagens           um turno de conversa (409 com confirmação pendente)
    POST /sessoes/{id}/confirmacoes        responde uma confirmação pendente (409 se não pendente)
    GET  /sessoes/{id}/eventos             todos os eventos gravados, em ordem
    GET  /apartamentos/{n}/reservas        verificação, sem passar pelo modelo
    GET  /apartamentos/{n}/visitantes      verificação, sem passar pelo modelo
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from google.adk import Runner
from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, Field

import env
from agents.residencial_aurora.agent import app as adk_app
from db import dados, repo
from db.engine import close_db, init_db

# Nome da function call que o `request_confirmation` de uma tool gera no stream
# de eventos. É por ela que a pendência é detectada e a resposta é endereçada.
REQUEST_CONFIRMATION = "adk_request_confirmation"

# Tools cujo `function_response` prova que o turno mudou o banco. Transferência
# e consultas de leitura não contam: se o modelo falhou depois delas, é 503.
TOOLS_QUE_GRAVAM = {"reservar_area", "cancelar_reserva", "autorizar_visitante"}

# --------------------------------------------------------------------------- #
# Montagem: SessionService -> App -> Runner -> API                             #
# --------------------------------------------------------------------------- #

os.makedirs(f"{env.RAIZ}/.adk", exist_ok=True)
session_service = SqliteSessionService(env.SESSION_DB_PATH)
runner = Runner(app=adk_app, session_service=session_service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(title="Assistente do Residencial Aurora", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _texto(event: Event) -> str | None:
    """Texto do evento (None se ele só carrega function_call/response)."""
    if not event.content or not event.content.parts:
        return None
    partes = [part.text for part in event.content.parts if part.text and not part.thought]
    return "\n".join(partes) if partes else None


def _partes(sessao: Session):
    for event in sessao.events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                yield event, part


def _pendencias(sessao: Session) -> list[dict]:
    """Confirmações pedidas e ainda sem resposta, derivadas dos eventos (D8).

    Uma `adk_request_confirmation` cujo id já tem `function_response` na sessão
    foi respondida — tirá-la da lista é o que torna a rota de confirmações
    idempotente (o reenvio recebe 409 e nada executa de novo).
    """
    pendentes: dict[str, dict] = {}
    for _, part in _partes(sessao):
        function_call = part.function_call
        if function_call and function_call.name == REQUEST_CONFIRMATION and function_call.id:
            args = function_call.args or {}
            pendentes[function_call.id] = {
                "id": function_call.id,
                "acao": (args.get("originalFunctionCall") or {}).get("name"),
                "detalhes": (args.get("toolConfirmation") or {}).get("payload") or {},
            }
        function_response = part.function_response
        if function_response and function_response.name == REQUEST_CONFIRMATION and function_response.id:
            pendentes.pop(function_response.id, None)
    return list(pendentes.values())


def _montar_resposta(sessao_apos_run: Session | None, texto: str | None) -> dict:
    return {
        "resposta": texto or "",
        "confirmacoes_pendentes": _pendencias(sessao_apos_run) if sessao_apos_run else [],
    }


def _exigir_apartamento(numero: str) -> None:
    if not dados.apartamento_existe(numero):
        raise HTTPException(status_code=404, detail="Apartamento não encontrado.")


async def _carregar_sessao(session_id: str) -> Session:
    """Sessão do ADK a partir do `session_id` do contrato; 404 se não existe."""
    registro = await repo.obter_sessao(session_id)
    sessao = None
    if registro is not None:
        sessao = await session_service.get_session(
            app_name=runner.app_name, user_id=registro.apartamento, session_id=session_id
        )
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return sessao


async def _reler(sessao: Session) -> Session | None:
    return await session_service.get_session(
        app_name=runner.app_name, user_id=sessao.user_id, session_id=sessao.id
    )


def _turno_avancou(antes: Session, depois: Session) -> bool:
    """O turno que falhou já deixou pendência nova ou executou alguma tool?"""
    if {p["id"] for p in _pendencias(depois)} - {p["id"] for p in _pendencias(antes)}:
        return True
    novos = depois.events[len(antes.events):]
    return any(
        part.function_response and part.function_response.name in TOOLS_QUE_GRAVAM
        for event in novos
        for part in (event.content.parts if event.content and event.content.parts else [])
    )


async def _rodar(sessao: Session, conteudo: types.Content) -> dict:
    """Roda um turno e monta a resposta do contrato a partir da sessão relida.

    A releitura é necessária: os eventos da rodada, inclusive um pedido de
    confirmação, só estão gravados depois que o `run_async` termina.

    `resposta` junta os textos finais do turno: num pedido misto ("minhas
    reservas e a piscina") a raiz fala num evento e o especialista noutro.
    """
    textos: list[str] = []
    try:
        async for event in runner.run_async(
            user_id=sessao.user_id, session_id=sessao.id, new_message=conteudo
        ):
            texto = _texto(event)
            if event.author != "user" and event.is_final_response() and texto and texto != (textos[-1] if textos else None):
                textos.append(texto)
    except APIError:
        # Erro do modelo (503 "high demand", 429). Se a tool já gravou algo
        # antes da falha, o cliente precisa saber (a pendência tem o `id`).
        depois = await _reler(sessao)
        if depois and _turno_avancou(sessao, depois):
            return _montar_resposta(depois, "\n".join(textos))
        raise HTTPException(
            status_code=503, detail="O modelo está indisponível no momento; repita a mensagem."
        ) from None

    return _montar_resposta(await _reler(sessao), "\n".join(textos))


# --------------------------------------------------------------------------- #
# Rotas de conversa                                                            #
# --------------------------------------------------------------------------- #


class NovaSessaoRequest(BaseModel):
    apartamento: str = Field(min_length=1)


@app.post("/sessoes", status_code=201)
async def criar_sessao(request: NovaSessaoRequest):
    _exigir_apartamento(request.apartamento)
    # Garantia 2: o apartamento entra uma única vez, aqui, como `user_id` e no state.
    sessao = await session_service.create_session(
        app_name=runner.app_name,
        user_id=request.apartamento,
        state={"apartamento": request.apartamento},
    )
    await repo.criar_sessao(sessao.id, request.apartamento)
    return {"session_id": sessao.id}


class MensagemRequest(BaseModel):
    # Texto vazio chegaria ao modelo como turno invisível e viraria 400 → 500.
    texto: str = Field(min_length=1)


@app.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(session_id: str, request: MensagemRequest):
    sessao = await _carregar_sessao(session_id)
    pendencias = _pendencias(sessao)
    if pendencias:
        # Sem isso o especialista pode devolver a conversa à raiz antes da
        # confirmação e a retomada cairia num agente sem a tool.
        raise HTTPException(
            status_code=409,
            detail={
                "mensagem": "Responda a confirmação pendente antes de enviar outra mensagem.",
                "confirmacoes_pendentes": pendencias,
            },
        )
    conteudo = types.Content(role="user", parts=[types.Part.from_text(text=request.texto)])
    return await _rodar(sessao, conteudo)


class ConfirmacaoRequest(BaseModel):
    id: str
    confirmado: bool


def _autor_do_pedido(sessao: Session, id_confirmacao: str) -> str | None:
    for event, part in _partes(sessao):
        if part.function_call and part.function_call.id == id_confirmacao:
            return event.author
    return None


def _autor_do_ultimo_evento_do_agente(sessao: Session) -> str | None:
    for event in reversed(sessao.events):
        if event.author != "user":
            return event.author
    return None


@app.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(session_id: str, request: ConfirmacaoRequest):
    """Responde uma confirmação pendente e retoma a execução da tool.

    A resposta é um `FunctionResponse` com o id da function call
    `adk_request_confirmation`; o Runner entrega ao agente que a pediu.
    """
    sessao = await _carregar_sessao(session_id)
    if request.id not in {p["id"] for p in _pendencias(sessao)}:
        raise HTTPException(
            status_code=409,
            detail="Não existe confirmação pendente com esse id nesta sessão.",
        )
    if _autor_do_pedido(sessao, request.id) != _autor_do_ultimo_evento_do_agente(sessao):
        # A conversa saiu do especialista que pediu: retomar cairia num agente
        # sem a tool. A pendência não é consumida.
        raise HTTPException(
            status_code=409,
            detail="A conversa saiu do especialista que pediu esta confirmação; ela não pode mais ser respondida.",
        )
    conteudo = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=request.id,
                    name=REQUEST_CONFIRMATION,
                    response={"confirmed": request.confirmado},
                )
            )
        ],
    )
    return await _rodar(sessao, conteudo)


@app.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str):
    sessao = await _carregar_sessao(session_id)
    return [event.model_dump(mode="json", exclude_none=True) for event in sessao.events]


# --------------------------------------------------------------------------- #
# Rotas de verificação (leem o banco direto, sem chamar agente nenhum)         #
# --------------------------------------------------------------------------- #


@app.get("/apartamentos/{numero}/reservas")
async def listar_reservas(numero: str):
    _exigir_apartamento(numero)
    reservas = await repo.listar_reservas_ativas(numero)
    return [{"codigo": r.codigo, "area": r.area, "data": r.data} for r in reservas]


@app.get("/apartamentos/{numero}/visitantes")
async def listar_visitantes(numero: str):
    _exigir_apartamento(numero)
    visitantes = await repo.listar_visitantes(numero)
    return [{"nome": v.nome, "data": v.data} for v in visitantes]
