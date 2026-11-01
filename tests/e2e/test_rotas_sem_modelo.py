"""Contrato das rotas que não passam pelo modelo (201, 404, 409, 422, listas).

Roda contra o app FastAPI em processo, via ASGITransport, com o
SqliteSessionService apontado para um banco temporário (conftest). Para os
casos que precisam de uma pendência sem chamar o Gemini, o pedido de
confirmação é gravado direto na sessão com `session_service.append_event`.
"""

import httpx
import pytest
from google.adk.events import Event
from google.genai import types

import web
from db import repo
from web import REQUEST_CONFIRMATION

PAYLOAD_SALAO = {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0}


@pytest.fixture(autouse=True)
async def _banco_temporario(banco):
    """O lifespan não roda sob ASGITransport: o `repo` usa o banco temporário do conftest."""


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


async def test_criar_sessao_grava_na_tabela_sessoes(cliente):
    session_id = await criar_sessao(cliente, "302")

    registro = await repo.obter_sessao(session_id)
    assert registro is not None and registro.apartamento == "302"


async def test_duas_sessoes_tem_ids_distintos_e_mapeiam_seus_apartamentos(cliente):
    s101 = await criar_sessao(cliente, "101")
    s302 = await criar_sessao(cliente, "302")

    assert s101 != s302
    assert (await repo.obter_sessao(s101)).apartamento == "101"
    assert (await repo.obter_sessao(s302)).apartamento == "302"


async def test_criar_sessao_com_apartamento_inexistente_devolve_404_e_nao_grava(cliente):
    resposta = await cliente.post("/sessoes", json={"apartamento": "999"})

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Apartamento não encontrado."}


@pytest.mark.parametrize("corpo", [{"apartamento": ""}, {}, {"apartamento": None}], ids=["vazio", "sem-campo", "null"])
async def test_criar_sessao_com_apartamento_invalido_devolve_422(cliente, corpo):
    resposta = await cliente.post("/sessoes", json=corpo)

    assert resposta.status_code == 422


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


async def test_sessao_na_tabela_mas_fora_do_session_service_devolve_404(cliente):
    await repo.criar_sessao("fantasma", "101")

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


async def test_confirmacao_com_id_inexistente_devolve_409_e_nao_grava_nada(cliente, banco):
    # Item 5 do roteiro F0.5.
    session_id = await criar_sessao(cliente)

    resposta = await cliente.post(
        f"/sessoes/{session_id}/confirmacoes", json={"id": "id-inexistente", "confirmado": True}
    )

    assert resposta.status_code == 409
    assert "pendente" in resposta.json()["detail"]
    assert (await cliente.get(f"/sessoes/{session_id}/eventos")).json() == []
    assert await repo.listar_reservas_ativas("101") == []


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


async def test_reenvio_de_confirmacao_ja_respondida_devolve_409_sem_executar_de_novo(cliente, banco):
    # Metade sem modelo do item 4: o id já tem function_response na sessão → 409, nenhum evento novo.
    session_id = await criar_sessao(cliente)
    await gravar_na_sessao(session_id, "101", evento_pedido("adk-1"), evento_resposta("adk-1", True))
    eventos_antes = (await cliente.get(f"/sessoes/{session_id}/eventos")).json()

    resposta = await cliente.post(f"/sessoes/{session_id}/confirmacoes", json={"id": "adk-1", "confirmado": True})

    assert resposta.status_code == 409
    assert (await cliente.get(f"/sessoes/{session_id}/eventos")).json() == eventos_antes
    assert await repo.listar_reservas_ativas("101") == []


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


async def test_reservas_sem_nenhuma_devolve_lista_vazia(cliente, banco):
    resposta = await cliente.get("/apartamentos/101/reservas")

    assert resposta.status_code == 200
    assert resposta.json() == []


async def test_reservas_filtra_pelo_apartamento_e_expoe_so_codigo_area_data(cliente, banco):
    a = await repo.criar_reserva("101", "salao-de-festas", "2030-04-20")
    b = await repo.criar_reserva("302", "churrasqueira", "2030-04-20")
    c = await repo.criar_reserva("101", "quadra", "2030-04-21")

    resposta = await cliente.get("/apartamentos/101/reservas")

    assert resposta.status_code == 200
    assert resposta.json() == [
        {"codigo": a.codigo, "area": "salao-de-festas", "data": "2030-04-20"},
        {"codigo": c.codigo, "area": "quadra", "data": "2030-04-21"},
    ]
    assert (await cliente.get("/apartamentos/302/reservas")).json() == [
        {"codigo": b.codigo, "area": "churrasqueira", "data": "2030-04-20"}
    ]
    assert (await cliente.get("/apartamentos/999/reservas")).status_code == 404


async def test_reservas_nao_lista_canceladas(cliente, banco):
    a = await repo.criar_reserva("101", "quadra", "2030-04-21")
    await repo.cancelar_reserva("101", a.codigo)

    assert (await cliente.get("/apartamentos/101/reservas")).json() == []


async def test_reservas_le_o_que_a_tool_gravou(cliente, banco, ctx):
    """A tool e a rota compartilham o banco (`repo`)."""
    from agents.residencial_aurora.tools.reservas import reservar_area

    resultado = await reservar_area("quadra", "2030-04-20", ctx("101"))

    resposta = await cliente.get("/apartamentos/101/reservas")
    assert resposta.json() == [{"codigo": resultado["codigo"], "area": "quadra", "data": "2030-04-20"}]


async def test_reservas_de_apartamento_inexistente_devolve_404(cliente):
    resposta = await cliente.get("/apartamentos/999/reservas")

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Apartamento não encontrado."}


# --------------------------------------------------------------------------- #
# GET /apartamentos/{n}/visitantes                                             #
# --------------------------------------------------------------------------- #


async def test_visitantes_sem_nenhum_devolve_lista_vazia(cliente):
    resposta = await cliente.get("/apartamentos/101/visitantes")

    assert resposta.status_code == 200
    assert resposta.json() == []


async def test_visitantes_filtra_pelo_apartamento_e_expoe_nome_e_data(cliente):
    await repo.autorizar_visitante("101", "Maria", "2030-04-20")
    await repo.autorizar_visitante("302", "João", "2030-04-21")

    assert (await cliente.get("/apartamentos/101/visitantes")).json() == [{"nome": "Maria", "data": "2030-04-20"}]
    assert (await cliente.get("/apartamentos/302/visitantes")).json() == [{"nome": "João", "data": "2030-04-21"}]


async def test_visitantes_de_apartamento_inexistente_devolve_404(cliente):
    resposta = await cliente.get("/apartamentos/999/visitantes")

    assert resposta.status_code == 404


# --------------------------------------------------------------------------- #
# 404 de sessão inexistente nas três rotas                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "metodo,rota,corpo",
    [
        ("get", "/sessoes/x/eventos", None),
        ("post", "/sessoes/x/mensagens", {"texto": "oi"}),
        ("post", "/sessoes/x/confirmacoes", {"id": "a", "confirmado": True}),
    ],
)
async def test_sessao_inexistente_devolve_404_nas_tres_rotas(cliente, metodo, rota, corpo):
    resposta = await getattr(cliente, metodo)(rota, **({"json": corpo} if corpo else {}))

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Sessão não encontrada."}


# --------------------------------------------------------------------------- #
# 409: mensagem com pendência; confirmação com autor trocado                   #
# --------------------------------------------------------------------------- #


async def test_mensagem_com_pendencia_devolve_409_com_mensagem_e_pendencias(cliente):
    session_id = await criar_sessao(cliente)
    await gravar_na_sessao(session_id, "101", evento_pedido("adk-1"))

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "outra coisa"})

    assert resposta.status_code == 409
    detail = resposta.json()["detail"]
    assert set(detail) == {"mensagem", "confirmacoes_pendentes"}
    assert detail["confirmacoes_pendentes"] == [
        {"id": "adk-1", "acao": "reservar_area", "detalhes": PAYLOAD_SALAO}
    ]
    # nada entrou na sessão
    assert len((await cliente.get(f"/sessoes/{session_id}/eventos")).json()) == 1


async def test_mensagem_apos_pendencia_respondida_nao_e_409(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    await gravar_na_sessao(session_id, "101", evento_pedido("adk-1"), evento_resposta("adk-1", False))
    _fake_run(monkeypatch, [evento_texto("especialista_reservas", "Ok.")])

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "oi"})

    assert resposta.status_code == 200


async def test_confirmacao_com_autor_trocado_devolve_409_sem_consumir_pendencia(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    pedido = evento_pedido("adk-1")
    outro = Event(
        author="agente_raiz",
        invocation_id="inv-3",
        content=types.Content(role="model", parts=[types.Part(text="Voltei.")]),
    )
    await gravar_na_sessao(session_id, "101", pedido, outro)
    chamado = _fake_run(monkeypatch, [])

    resposta = await cliente.post(f"/sessoes/{session_id}/confirmacoes", json={"id": "adk-1", "confirmado": True})

    assert resposta.status_code == 409
    assert "especialista" in resposta.json()["detail"]
    assert chamado == []  # runner não foi acionado
    sessao = await web._carregar_sessao(session_id)
    assert [p["id"] for p in web._pendencias(sessao)] == ["adk-1"]


# --------------------------------------------------------------------------- #
# _montar_resposta, junção de textos e APIError (runner.run_async falso)       #
# --------------------------------------------------------------------------- #


def evento_texto(autor: str, texto: str, *, pensamento: bool = False, final: bool = True) -> Event:
    parte = types.Part(text=texto, thought=True) if pensamento else types.Part(text=texto)
    return Event(
        author=autor,
        invocation_id="inv-x",
        content=types.Content(role="model", parts=[parte]),
    )


def evento_tool(nome: str) -> Event:
    return Event(
        author="especialista_reservas",
        invocation_id="inv-x",
        content=types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(id="r1", name=nome, response={"ok": 1}))],
        ),
    )


def _fake_run(monkeypatch, eventos, erro: Exception | None = None, gravar: tuple = ()):
    """Troca `runner.run_async`. `gravar`: eventos anexados à sessão antes de emitir/levantar."""
    chamadas: list[dict] = []

    async def run_async(*, user_id, session_id, new_message, **_):
        chamadas.append({"user_id": user_id, "session_id": session_id})
        if gravar:
            await gravar_na_sessao(session_id, user_id, *gravar)
        for evento in eventos:
            yield evento
        if erro:
            raise erro

    monkeypatch.setattr(web.runner, "run_async", run_async)
    return chamadas


def test_montar_resposta_nunca_devolve_null():
    assert web._montar_resposta(None, None) == {"resposta": "", "confirmacoes_pendentes": []}
    assert web._montar_resposta(None, "") == {"resposta": "", "confirmacoes_pendentes": []}


async def test_mensagem_sem_texto_final_devolve_resposta_vazia_e_nao_null(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    _fake_run(monkeypatch, [])

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "oi"})

    assert resposta.status_code == 200
    assert resposta.json() == {"resposta": "", "confirmacoes_pendentes": []}


async def test_pedido_misto_junta_os_textos_finais_do_turno(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    _fake_run(
        monkeypatch,
        [
            evento_texto("agente_raiz", "Suas reservas: nenhuma."),
            evento_texto("especialista_regulamento", "A piscina abre às 8h."),
        ],
    )

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "minhas reservas e a piscina"})

    assert resposta.json()["resposta"] == "Suas reservas: nenhuma.\nA piscina abre às 8h."


async def test_resposta_ignora_user_pensamento_e_repeticao_consecutiva(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    _fake_run(
        monkeypatch,
        [
            evento_texto("user", "eco do usuário"),
            evento_texto("agente_raiz", "pensando...", pensamento=True),
            evento_texto("agente_raiz", "Olá!"),
            evento_texto("especialista_reservas", "Olá!"),
        ],
    )

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "oi"})

    assert resposta.json()["resposta"] == "Olá!"


async def test_resposta_traz_pendencia_gravada_durante_o_turno(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    _fake_run(monkeypatch, [evento_texto("especialista_reservas", "Confirma?")], gravar=(evento_pedido("adk-9"),))

    corpo = (await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "reserve"})).json()

    assert corpo["resposta"] == "Confirma?"
    assert corpo["confirmacoes_pendentes"] == [{"id": "adk-9", "acao": "reservar_area", "detalhes": PAYLOAD_SALAO}]


def _erro_modelo():
    from google.genai.errors import ServerError

    return ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})


MSG_503 = "O modelo está indisponível no momento; repita a mensagem."


async def test_apierror_sem_nada_gravado_devolve_503(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    _fake_run(monkeypatch, [], erro=_erro_modelo())

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "oi"})

    assert resposta.status_code == 503
    assert resposta.json() == {"detail": MSG_503}


@pytest.mark.parametrize("tool", ["transfer_to_agent", "consultar_reservas", "listar_visitantes"])
async def test_apierror_apos_transferencia_ou_leitura_continua_503(cliente, monkeypatch, tool):
    session_id = await criar_sessao(cliente)
    _fake_run(monkeypatch, [], erro=_erro_modelo(), gravar=(evento_tool(tool),))

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "oi"})

    assert resposta.status_code == 503
    assert resposta.json() == {"detail": MSG_503}


@pytest.mark.parametrize("tool", sorted(web.TOOLS_QUE_GRAVAM))
async def test_apierror_apos_tool_que_grava_devolve_200_com_o_que_ja_aconteceu(cliente, monkeypatch, tool):
    session_id = await criar_sessao(cliente)
    _fake_run(
        monkeypatch,
        [evento_texto("especialista_reservas", "Feito.")],
        erro=_erro_modelo(),
        gravar=(evento_tool(tool),),
    )

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "oi"})

    assert resposta.status_code == 200
    assert resposta.json() == {"resposta": "Feito.", "confirmacoes_pendentes": []}


async def test_apierror_com_pendencia_nova_devolve_200_com_a_pendencia(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    _fake_run(monkeypatch, [], erro=_erro_modelo(), gravar=(evento_pedido("adk-7"),))

    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": "reserve"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["resposta"] == ""
    assert [p["id"] for p in corpo["confirmacoes_pendentes"]] == ["adk-7"]


async def test_apierror_em_confirmacao_sem_evento_novo_devolve_503_e_mantem_pendencia(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)
    await gravar_na_sessao(session_id, "101", evento_pedido("adk-1"))
    _fake_run(monkeypatch, [], erro=_erro_modelo())

    resposta = await cliente.post(f"/sessoes/{session_id}/confirmacoes", json={"id": "adk-1", "confirmado": True})

    assert resposta.status_code == 503
    sessao = await web._carregar_sessao(session_id)
    assert [p["id"] for p in web._pendencias(sessao)] == ["adk-1"]
