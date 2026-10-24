"""API do assistente do Residencial Aurora — versão do spike (Fase 0).

Já segue o contrato do enunciado nas rotas de sessão; o que é exclusivo do spike
(o mapa de sessões e as reservas em JSON) está marcado com "spike" e sai na
Fase 5, quando o banco (`db/`) assume.

Rodar:

    uv run uvicorn web:app --port 8000

Endpoints:

    POST /sessoes                          cria a sessão de um apartamento (201)
    POST /sessoes/{id}/mensagens           um turno de conversa
    POST /sessoes/{id}/confirmacoes        responde uma confirmação pendente (409 se não pendente)
    GET  /sessoes/{id}/eventos             todos os eventos gravados, em ordem
    GET  /apartamentos/{n}/reservas        verificação, sem passar pelo modelo
"""

import json
import os

from fastapi import FastAPI, HTTPException
from google.adk import Runner
from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types
from pydantic import BaseModel, Field

import env
from agents.residencial_aurora.agent import ARQUIVO_RESERVAS, app as adk_app

# Nome da function call que o `request_confirmation` de uma tool gera no stream
# de eventos. É por ela que a pendência é detectada e a resposta é endereçada.
REQUEST_CONFIRMATION = "adk_request_confirmation"

# spike: mapa session_id → apartamento (D7). Na Fase 2 vira a tabela `sessoes`.
ARQUIVO_SESSOES = f"{env.RAIZ}/.adk/spike_sessoes.json"

# --------------------------------------------------------------------------- #
# Montagem: SessionService -> App -> Runner -> API                             #
# --------------------------------------------------------------------------- #

os.makedirs(f"{env.RAIZ}/.adk", exist_ok=True)
session_service = SqliteSessionService(env.SESSION_DB_PATH)
runner = Runner(app=adk_app, session_service=session_service)

app = FastAPI(title="Assistente do Residencial Aurora (spike da Fase 0)")


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _ler_json(caminho: str, vazio):
    if not os.path.exists(caminho):
        return vazio
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def _gravar_json(caminho: str, conteudo) -> None:
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(conteudo, arquivo, ensure_ascii=False, indent=2)


def _texto(event: Event) -> str | None:
    """Texto do evento (None se ele só carrega function_call/response)."""
    if not event.content or not event.content.parts:
        return None
    partes = [part.text for part in event.content.parts if part.text]
    return "\n".join(partes) if partes else None


def _pendencias(sessao: Session) -> list[dict]:
    """Confirmações pedidas e ainda sem resposta, derivadas dos eventos (D8).

    Uma `adk_request_confirmation` cujo id já tem `function_response` na sessão
    foi respondida — tirá-la da lista é o que torna a rota de confirmações
    idempotente (o reenvio recebe 409 e nada executa de novo).
    """
    pendentes: dict[str, dict] = {}
    for event in sessao.events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
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


async def _carregar_sessao(session_id: str) -> Session:
    """Sessão do ADK a partir do `session_id` do contrato; 404 se não existe."""
    apartamento = _ler_json(ARQUIVO_SESSOES, {}).get(session_id)
    sessao = None
    if apartamento is not None:
        sessao = await session_service.get_session(
            app_name=runner.app_name, user_id=apartamento, session_id=session_id
        )
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return sessao


async def _rodar(sessao: Session, conteudo: types.Content) -> dict:
    """Roda um turno e monta a resposta do contrato a partir da sessão relida.

    A releitura é necessária: os eventos da rodada, inclusive um pedido de
    confirmação, só estão gravados depois que o `run_async` termina.
    """
    texto: str | None = None
    async for event in runner.run_async(
        user_id=sessao.user_id, session_id=sessao.id, new_message=conteudo
    ):
        if event.is_final_response():
            texto = _texto(event) or texto

    sessao_apos_run = await session_service.get_session(
        app_name=runner.app_name, user_id=sessao.user_id, session_id=sessao.id
    )
    return {
        "resposta": texto or "",
        "confirmacoes_pendentes": _pendencias(sessao_apos_run) if sessao_apos_run else [],
    }


# --------------------------------------------------------------------------- #
# Rotas de conversa                                                            #
# --------------------------------------------------------------------------- #


class NovaSessaoRequest(BaseModel):
    apartamento: str = Field(min_length=1)


@app.post("/sessoes", status_code=201)
async def criar_sessao(request: NovaSessaoRequest):
    # Garantia 2: o apartamento entra uma única vez, aqui, como `user_id` e no state.
    sessao = await session_service.create_session(
        app_name=runner.app_name,
        user_id=request.apartamento,
        state={"apartamento": request.apartamento},
    )
    sessoes = _ler_json(ARQUIVO_SESSOES, {})
    sessoes[sessao.id] = request.apartamento
    _gravar_json(ARQUIVO_SESSOES, sessoes)
    return {"session_id": sessao.id}


class MensagemRequest(BaseModel):
    # Texto vazio chegaria ao modelo como turno invisível e viraria 400 → 500.
    texto: str = Field(min_length=1)


@app.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(session_id: str, request: MensagemRequest):
    sessao = await _carregar_sessao(session_id)
    conteudo = types.Content(role="user", parts=[types.Part.from_text(text=request.texto)])
    return await _rodar(sessao, conteudo)


class ConfirmacaoRequest(BaseModel):
    id: str
    confirmado: bool


@app.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(session_id: str, request: ConfirmacaoRequest):
    """Responde uma confirmação pendente e retoma a execução da tool.

    A resposta é um `FunctionResponse` com o id da function call
    `adk_request_confirmation`; o Runner entrega ao agente que a pediu.
    """
    sessao = await _carregar_sessao(session_id)
    pendentes = {p["id"] for p in _pendencias(sessao)}
    if request.id not in pendentes:
        raise HTTPException(
            status_code=409,
            detail="Não existe confirmação pendente com esse id nesta sessão.",
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
# Rota de verificação (lê os dados direto, sem chamar agente nenhum)           #
# --------------------------------------------------------------------------- #


@app.get("/apartamentos/{numero}/reservas")
async def listar_reservas(numero: str):
    # spike: lê o JSON do spike; na Fase 5 lê `repo.listar_reservas_ativas`.
    reservas = _ler_json(ARQUIVO_RESERVAS, [])
    return [
        {"codigo": reserva["codigo"], "area": reserva["area"], "data": reserva["data"]}
        for reserva in reservas
        if reserva["apartamento"] == numero
    ]
