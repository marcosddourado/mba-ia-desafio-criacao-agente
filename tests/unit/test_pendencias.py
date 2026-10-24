"""`_pendencias` e `_texto` do `web.py` com `Event`s reais do ADK."""

from google.adk.events import Event
from google.adk.sessions import Session
from google.genai import types

import web
from web import REQUEST_CONFIRMATION, _pendencias, _texto

PAYLOAD_SALAO = {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0}


def evento_pedido(id_confirmacao: str, payload: dict | None = PAYLOAD_SALAO, args=...) -> Event:
    """O que `request_confirmation` gera: function_call `adk_request_confirmation` do especialista."""
    if args is ...:
        args = {
            "originalFunctionCall": {
                "id": "fc-1",
                "name": "reservar_area",
                "args": {"area": payload["area"], "data": payload["data"]},
            },
            "toolConfirmation": {
                "hint": f"Reservar {payload['area']} em {payload['data']} gera cobrança.",
                "confirmed": False,
                "payload": payload,
            },
        }
    return Event(
        author="especialista_reservas",
        invocation_id="inv-1",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(id=id_confirmacao, name=REQUEST_CONFIRMATION, args=args)
                )
            ],
        ),
    )


def evento_resposta(id_confirmacao: str, confirmado: bool = True, nome: str = REQUEST_CONFIRMATION) -> Event:
    """O que a rota de confirmações envia: function_response com o id da function call."""
    return Event(
        author="user",
        invocation_id="inv-2",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=id_confirmacao, name=nome, response={"confirmed": confirmado}
                    )
                )
            ],
        ),
    )


def evento_texto(texto: str, author: str = "assistente") -> Event:
    return Event(
        author=author,
        invocation_id="inv-3",
        content=types.Content(role="model", parts=[types.Part.from_text(text=texto)]),
    )


def sessao(*eventos: Event) -> Session:
    return Session(id="s", app_name="residencial_aurora", user_id="101", events=list(eventos))


# --------------------------------------------------------------------------- #
# _pendencias                                                                  #
# --------------------------------------------------------------------------- #


def test_constante_do_nome_da_function_call():
    assert web.REQUEST_CONFIRMATION == "adk_request_confirmation"


def test_sessao_sem_eventos_nao_tem_pendencias():
    assert _pendencias(sessao()) == []


def test_pedido_sem_resposta_vira_uma_pendencia_com_id_acao_e_detalhes():
    pendencias = _pendencias(sessao(evento_pedido("adk-1")))

    assert pendencias == [{"id": "adk-1", "acao": "reservar_area", "detalhes": PAYLOAD_SALAO}]


def test_detalhes_expoem_area_data_e_taxa_do_payload():
    [pendencia] = _pendencias(sessao(evento_pedido("adk-1")))

    assert pendencia["detalhes"]["area"] == "salao-de-festas"
    assert pendencia["detalhes"]["data"] == "2030-04-20"
    assert pendencia["detalhes"]["taxa"] == 150.0


def test_pedido_aprovado_sai_da_lista():
    assert _pendencias(sessao(evento_pedido("adk-1"), evento_resposta("adk-1", confirmado=True))) == []


def test_pedido_negado_tambem_sai_da_lista():
    # Negar fecha a pendência: um novo pedido depois disso gera um id novo (item 2 → item 3 do roteiro).
    assert _pendencias(sessao(evento_pedido("adk-1"), evento_resposta("adk-1", confirmado=False))) == []


def test_dois_pedidos_um_respondido_deixa_so_o_outro():
    payload_churrasqueira = {"area": "churrasqueira", "data": "2030-05-01", "taxa": 80.0}
    eventos = (
        evento_pedido("adk-1"),
        evento_pedido("adk-2", payload=payload_churrasqueira),
        evento_resposta("adk-1"),
    )

    pendencias = _pendencias(sessao(*eventos))

    assert [p["id"] for p in pendencias] == ["adk-2"]
    assert pendencias[0]["detalhes"] == payload_churrasqueira


def test_pedido_novo_depois_de_um_negado_fica_pendente_sozinho():
    eventos = (
        evento_pedido("adk-1"),
        evento_resposta("adk-1", confirmado=False),
        evento_texto("Nada foi reservado."),
        evento_pedido("adk-2"),
    )

    assert [p["id"] for p in _pendencias(sessao(*eventos))] == ["adk-2"]


def test_evento_sem_content_e_ignorado():
    sem_content = Event(author="user", invocation_id="inv-0")
    assert sem_content.content is None

    assert _pendencias(sessao(sem_content)) == []
    assert len(_pendencias(sessao(sem_content, evento_pedido("adk-1"), sem_content))) == 1


def test_evento_com_parts_vazio_e_ignorado():
    vazio = Event(author="assistente", invocation_id="inv-0", content=types.Content(role="model", parts=[]))

    assert _pendencias(sessao(vazio, evento_pedido("adk-1"))) == [
        {"id": "adk-1", "acao": "reservar_area", "detalhes": PAYLOAD_SALAO}
    ]


def test_evento_so_de_texto_nao_gera_pendencia():
    assert _pendencias(sessao(evento_texto("Olá! Como posso ajudar?"))) == []


def test_function_call_de_outra_tool_nao_e_pendencia():
    chamada_direta = Event(
        author="especialista_reservas",
        invocation_id="inv-1",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="fc-1", name="reservar_area", args={"area": "quadra", "data": "2030-04-20"}
                    )
                )
            ],
        ),
    )

    assert _pendencias(sessao(chamada_direta)) == []


def test_function_response_de_outra_tool_com_mesmo_id_nao_fecha_a_pendencia():
    eventos = (evento_pedido("adk-1"), evento_resposta("adk-1", nome="reservar_area"))

    assert [p["id"] for p in _pendencias(sessao(*eventos))] == ["adk-1"]


def test_function_call_sem_id_e_ignorada():
    sem_id = Event(
        author="especialista_reservas",
        invocation_id="inv-1",
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name=REQUEST_CONFIRMATION, args={}))],
        ),
    )

    assert _pendencias(sessao(sem_id)) == []


def test_pedido_sem_args_vira_pendencia_sem_acao_e_com_detalhes_vazios():
    [pendencia] = _pendencias(sessao(evento_pedido("adk-9", args=None)))

    assert pendencia == {"id": "adk-9", "acao": None, "detalhes": {}}


def test_pedido_sem_payload_tem_detalhes_vazios():
    args = {"originalFunctionCall": {"name": "reservar_area"}, "toolConfirmation": {"hint": "x", "confirmed": False}}
    [pendencia] = _pendencias(sessao(evento_pedido("adk-1", args=args)))

    assert pendencia == {"id": "adk-1", "acao": "reservar_area", "detalhes": {}}


def test_resposta_para_id_desconhecido_nao_quebra_nem_cria_pendencia():
    assert _pendencias(sessao(evento_resposta("nunca-pedido"))) == []


# --------------------------------------------------------------------------- #
# _texto                                                                       #
# --------------------------------------------------------------------------- #


def test_texto_de_evento_sem_content_e_none():
    assert _texto(Event(author="user", invocation_id="inv-0")) is None


def test_texto_de_evento_so_com_function_call_e_none():
    assert _texto(evento_pedido("adk-1")) is None


def test_texto_de_evento_so_com_function_response_e_none():
    assert _texto(evento_resposta("adk-1")) is None


def test_texto_junta_as_partes_de_texto_com_quebra_de_linha():
    evento = Event(
        author="assistente",
        invocation_id="inv-3",
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="Olá!"), types.Part.from_text(text="Como posso ajudar?")],
        ),
    )

    assert _texto(evento) == "Olá!\nComo posso ajudar?"


def test_texto_ignora_partes_vazias_e_devolve_none_se_nao_sobrar_nada():
    evento = Event(
        author="assistente",
        invocation_id="inv-3",
        content=types.Content(role="model", parts=[types.Part.from_text(text="")]),
    )

    assert _texto(evento) is None
