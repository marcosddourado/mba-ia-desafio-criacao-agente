"""Contrato das rotas que não passam pelo modelo (201, 404, 409, 422, listas).

Roda contra o app FastAPI em processo, via ASGITransport, com o
SqliteSessionService apontado para um banco temporário (conftest). Para os
casos que precisam de uma pendência sem chamar o Gemini, o pedido de
confirmação é gravado direto na sessão com `session_service.append_event`.
"""

import json

import httpx
import pytest
from google.adk.events import Event
from google.genai import types

import web
from web import REQUEST_CONFIRMATION

PAYLOAD_SALAO = {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0}


@pytest.fixture
async def cliente():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://test") as c:
        yield c


async def criar_sessao(cliente: httpx.AsyncClient, apartamento: str = "101") -> str:
    resposta = await cliente.post("/sessoes", json={"apartamento": apartamento})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["session_id"]


async def gravar_na_sessao(session_id: str, apartamento: str, *eventos: Event) -> None:
    sessao = await web.session_service.get_session(
        app_name=web.runner.app_name, user_id=apartamento, session_id=session_id
    )
    assert sessao is not None
    for evento in eventos:
        await web.session_service.append_event(sessao, evento)


def evento_pedido(id_confirmacao: str, payload: dict = PAYLOAD_SALAO) -> Event:
    return Event(
        author="especialista_reservas",
        invocation_id="inv-1",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id=id_confirmacao,
                        name=REQUEST_CONFIRMATION,
                        args={
                            "originalFunctionCall": {
                                "id": "fc-1",
                                "name": "reservar_area",
                                "args": {"area": payload["area"], "data": payload["data"]},
                            },
                            "toolConfirmation": {"hint": "cobrança", "confirmed": False, "payload": payload},
                        },
                    )
                )
            ],
        ),
    )


def evento_resposta(id_confirmacao: str, confirmado: bool) -> Event:
    return Event(
        author="user",
        invocation_id="inv-2",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=id_confirmacao, name=REQUEST_CONFIRMATION, response={"confirmed": confirmado}
                    )
                )
            ],
        ),
    )


# --------------------------------------------------------------------------- #
# POST /sessoes                                                                #
# --------------------------------------------------------------------------- #


async def test_criar_sessao_devolve_201_com_session_id_e_grava_no_session_service(cliente):
    resposta = await cliente.post("/sessoes", json={"apartamento": "101"})

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert set(corpo) == {"session_id"}
    assert isinstance(corpo["session_id"], str) and corpo["session_id"]

    sessao = await web.session_service.get_session(
        app_name=web.runner.app_name, user_id="101", session_id=corpo["session_id"]
    )
    assert sessao is not None
    assert sessao.user_id == "101"
    assert sessao.state == {"apartamento": "101"}
    assert sessao.events == []


async def test_criar_sessao_registra_apartamento_no_mapa_do_spike(cliente, arquivos_spike):
    session_id = await criar_sessao(cliente, "302")

    mapa = json.loads(arquivos_spike.sessoes.read_text(encoding="utf-8"))
    assert mapa == {session_id: "302"}


async def test_duas_sessoes_tem_ids_distintos_e_mapeiam_seus_apartamentos(cliente, arquivos_spike):
    s101 = await criar_sessao(cliente, "101")
    s302 = await criar_sessao(cliente, "302")

    assert s101 != s302
    mapa = json.loads(arquivos_spike.sessoes.read_text(encoding="utf-8"))
    assert mapa == {s101: "101", s302: "302"}


@pytest.mark.parametrize("corpo", [{"apartamento": ""}, {}, {"apartamento": None}], ids=["vazio", "sem-campo", "null"])
async def test_criar_sessao_com_apartamento_invalido_devolve_422(cliente, corpo, arquivos_spike):
    resposta = await cliente.post("/sessoes", json=corpo)

    assert resposta.status_code == 422
    assert not arquivos_spike.sessoes.exists()


# --------------------------------------------------------------------------- #
# GET /sessoes/{id}/eventos                                                    #
# --------------------------------------------------------------------------- #


async def test_eventos_de_sessao_nova_e_lista_vazia(cliente):
    session_id = await criar_sessao(cliente)

    resposta = await cliente.get(f"/sessoes/{session_id}/eventos")

    assert resposta.status_code == 200
    assert resposta.json() == []


async def test_eventos_de_sessao_inexistente_devolve_404(cliente):
    resposta = await cliente.get("/sessoes/nao-existe/eventos")

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Sessão não encontrada."}


async def test_sessao_no_mapa_mas_fora_do_banco_devolve_404(cliente, arquivos_spike):
    arquivos_spike.sessoes.write_text(json.dumps({"fantasma": "101"}), encoding="utf-8")

    resposta = await cliente.get("/sessoes/fantasma/eventos")

    assert resposta.status_code == 404


async def test_eventos_listam_o_pedido_de_confirmacao_gravado_na_sessao(cliente):
    session_id = await criar_sessao(cliente)
    await gravar_na_sessao(session_id, "101", evento_pedido("adk-1"))

    resposta = await cliente.get(f"/sessoes/{session_id}/eventos")

    assert resposta.status_code == 200
    eventos = resposta.json()
    assert len(eventos) == 1
    assert eventos[0]["author"] == "especialista_reservas"
    function_call = eventos[0]["content"]["parts"][0]["function_call"]
    assert function_call["id"] == "adk-1"
    assert function_call["name"] == REQUEST_CONFIRMATION
    assert function_call["args"]["toolConfirmation"]["payload"] == PAYLOAD_SALAO


async def test_eventos_preservam_a_ordem_pedido_depois_resposta(cliente):
    session_id = await criar_sessao(cliente)
    await gravar_na_sessao(session_id, "101", evento_pedido("adk-1"), evento_resposta("adk-1", False))

    eventos = (await cliente.get(f"/sessoes/{session_id}/eventos")).json()

    assert [evento["author"] for evento in eventos] == ["especialista_reservas", "user"]
    assert eventos[1]["content"]["parts"][0]["function_response"]["response"] == {"confirmed": False}


# --------------------------------------------------------------------------- #
# POST /sessoes/{id}/confirmacoes (sem pendência válida → nada executa)        #
# --------------------------------------------------------------------------- #


async def test_confirmacao_com_id_inexistente_devolve_409_e_nao_grava_nada(cliente, arquivos_spike):
    # Item 5 do roteiro F0.5.
    session_id = await criar_sessao(cliente)

    resposta = await cliente.post(
        f"/sessoes/{session_id}/confirmacoes", json={"id": "id-inexistente", "confirmado": True}
    )

    assert resposta.status_code == 409
    assert "pendente" in resposta.json()["detail"]
    assert (await cliente.get(f"/sessoes/{session_id}/eventos")).json() == []
    assert not arquivos_spike.reservas.exists()


async def test_confirmacao_em_sessao_inexistente_devolve_404(cliente):
    resposta = await cliente.post("/sessoes/nao-existe/confirmacoes", json={"id": "adk-1", "confirmado": True})

    assert resposta.status_code == 404


@pytest.mark.parametrize(
    "corpo",
    [{}, {"id": "adk-1"}, {"confirmado": True}, {"id": "adk-1", "confirmado": "talvez"}],
    ids=["vazio", "sem-confirmado", "sem-id", "confirmado-invalido"],
)
async def test_confirmacao_com_corpo_invalido_devolve_422(cliente, corpo):
    session_id = await criar_sessao(cliente)

    resposta = await cliente.post(f"/sessoes/{session_id}/confirmacoes", json=corpo)

    assert resposta.status_code == 422


async def test_reenvio_de_confirmacao_ja_respondida_devolve_409_sem_executar_de_novo(cliente, arquivos_spike):
    # Metade sem modelo do item 4: o id já tem function_response na sessão → 409, nenhum evento novo.
    session_id = await criar_sessao(cliente)
    await gravar_na_sessao(session_id, "101", evento_pedido("adk-1"), evento_resposta("adk-1", True))
    eventos_antes = (await cliente.get(f"/sessoes/{session_id}/eventos")).json()

    resposta = await cliente.post(f"/sessoes/{session_id}/confirmacoes", json={"id": "adk-1", "confirmado": True})

    assert resposta.status_code == 409
    assert (await cliente.get(f"/sessoes/{session_id}/eventos")).json() == eventos_antes
    assert not arquivos_spike.reservas.exists()


async def test_confirmacao_negada_tambem_fecha_a_pendencia_para_a_rota(cliente):
    session_id = await criar_sessao(cliente)
    await gravar_na_sessao(session_id, "101", evento_pedido("adk-1"), evento_resposta("adk-1", False))

    resposta = await cliente.post(f"/sessoes/{session_id}/confirmacoes", json={"id": "adk-1", "confirmado": True})

    assert resposta.status_code == 409


async def test_confirmacao_com_id_pendente_de_outra_sessao_devolve_409(cliente):
    sessao_101 = await criar_sessao(cliente, "101")
    sessao_302 = await criar_sessao(cliente, "302")
    await gravar_na_sessao(sessao_101, "101", evento_pedido("adk-1"))

    resposta = await cliente.post(f"/sessoes/{sessao_302}/confirmacoes", json={"id": "adk-1", "confirmado": True})

    assert resposta.status_code == 409
    assert (await cliente.get(f"/sessoes/{sessao_302}/eventos")).json() == []


# --------------------------------------------------------------------------- #
# POST /sessoes/{id}/mensagens (só o que não chega ao modelo)                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("corpo", [{"texto": ""}, {}, {"texto": None}], ids=["vazio", "sem-campo", "null"])
async def test_mensagem_invalida_devolve_422_antes_de_chamar_o_modelo(cliente, corpo):
    session_id = await criar_sessao(cliente)

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json=corpo)

    assert resposta.status_code == 422
    assert (await cliente.get(f"/sessoes/{session_id}/eventos")).json() == []


async def test_mensagem_para_sessao_inexistente_devolve_404(cliente):
    resposta = await cliente.post("/sessoes/nao-existe/mensagens", json={"texto": "Olá"})

    assert resposta.status_code == 404


# --------------------------------------------------------------------------- #
# GET /apartamentos/{n}/reservas                                               #
# --------------------------------------------------------------------------- #


async def test_reservas_sem_arquivo_devolve_lista_vazia(cliente, arquivos_spike):
    assert not arquivos_spike.reservas.exists()

    resposta = await cliente.get("/apartamentos/101/reservas")

    assert resposta.status_code == 200
    assert resposta.json() == []


async def test_reservas_filtra_pelo_apartamento_e_expoe_so_codigo_area_data(cliente, arquivos_spike):
    arquivos_spike.reservas.write_text(
        json.dumps(
            [
                {"codigo": "RSV-00000101", "apartamento": "101", "area": "salao-de-festas", "data": "2030-04-20"},
                {"codigo": "RSV-00000302", "apartamento": "302", "area": "churrasqueira", "data": "2030-04-20"},
                {"codigo": "RSV-00000102", "apartamento": "101", "area": "quadra", "data": "2030-04-21"},
            ]
        ),
        encoding="utf-8",
    )

    resposta = await cliente.get("/apartamentos/101/reservas")

    assert resposta.status_code == 200
    assert resposta.json() == [
        {"codigo": "RSV-00000101", "area": "salao-de-festas", "data": "2030-04-20"},
        {"codigo": "RSV-00000102", "area": "quadra", "data": "2030-04-21"},
    ]
    assert (await cliente.get("/apartamentos/302/reservas")).json() == [
        {"codigo": "RSV-00000302", "area": "churrasqueira", "data": "2030-04-20"}
    ]
    assert (await cliente.get("/apartamentos/999/reservas")).json() == []


async def test_reservas_le_o_que_a_tool_gravou(cliente, arquivos_spike):
    """A tool grava em `agent.ARQUIVO_RESERVAS`; a rota lê `web.ARQUIVO_RESERVAS`. Os dois precisam coincidir."""
    from agents.residencial_aurora.agent import reservar_area

    class Contexto:
        state = {"apartamento": "101"}
        tool_confirmation = None

        def request_confirmation(self, *, hint=None, payload=None):
            raise AssertionError("quadra não pede confirmação")

    resultado = reservar_area("quadra", "2030-04-20", Contexto())

    resposta = await cliente.get("/apartamentos/101/reservas")
    assert resposta.json() == [{"codigo": resultado["codigo"], "area": "quadra", "data": "2030-04-20"}]
