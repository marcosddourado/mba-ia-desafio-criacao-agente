"""Roteiro F0.5 (itens 1–4) de ponta a ponta, com o Gemini de verdade.

Só roda com `HARNESS_GEMINI=1 uv run pytest -q -m gemini`. O "parar e subir a
API" do item 3 é simulado trocando `web.session_service` e `web.runner` por
instâncias novas sobre o mesmo `sessoes.db`: é exatamente o que um processo
novo faz na importação de `web.py`.
"""

import os

import httpx
import pytest
from google.adk import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService

import env
import web
from agents.residencial_aurora.agent import app as adk_app

pytestmark = [
    pytest.mark.gemini,
    pytest.mark.skipif(not os.environ.get("HARNESS_GEMINI"), reason="chama o Gemini; rode com HARNESS_GEMINI=1"),
]

PEDIDO_SALAO = "Reserve o salão de festas para 2030-04-20."


@pytest.fixture
async def cliente():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web.app), base_url="http://test", timeout=120
    ) as c:
        yield c


async def criar_sessao(cliente: httpx.AsyncClient, apartamento: str = "101") -> str:
    resposta = await cliente.post("/sessoes", json={"apartamento": apartamento})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["session_id"]


async def enviar(cliente: httpx.AsyncClient, session_id: str, texto: str) -> dict:
    resposta = await cliente.post(f"/sessoes/{session_id}/mensagens", json={"texto": texto})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert set(corpo) == {"resposta", "confirmacoes_pendentes"}
    return corpo


async def reservas(cliente: httpx.AsyncClient, apartamento: str = "101") -> list[dict]:
    resposta = await cliente.get(f"/apartamentos/{apartamento}/reservas")
    assert resposta.status_code == 200
    return resposta.json()


def reiniciar_api(monkeypatch) -> None:
    """Novo SessionService e novo Runner sobre o mesmo banco, como um processo recém-subido."""
    servico = SqliteSessionService(env.SESSION_DB_PATH)
    monkeypatch.setattr(web, "session_service", servico)
    monkeypatch.setattr(web, "runner", Runner(app=adk_app, session_service=servico))


def _salao_em(reservas_: list[dict], data: str = "2030-04-20") -> list[dict]:
    return [r for r in reservas_ if r["area"] == "salao-de-festas" and r["data"] == data]


async def test_itens_1_e_2_pedido_com_taxa_gera_pendencia_e_negar_nao_grava(cliente):
    session_id = await criar_sessao(cliente)

    # item 1: pedido com taxa → 1 pendência com area e data, nada gravado
    corpo = await enviar(cliente, session_id, PEDIDO_SALAO)
    assert len(corpo["confirmacoes_pendentes"]) == 1, corpo
    pendencia = corpo["confirmacoes_pendentes"][0]
    assert pendencia["acao"] == "reservar_area"
    assert pendencia["detalhes"]["area"] == "salao-de-festas"
    assert pendencia["detalhes"]["data"] == "2030-04-20"
    assert pendencia["detalhes"]["taxa"] == 150.0
    assert _salao_em(await reservas(cliente)) == []

    # item 2: negar → nada gravado, lista vazia
    resposta = await cliente.post(
        f"/sessoes/{session_id}/confirmacoes", json={"id": pendencia["id"], "confirmado": False}
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["confirmacoes_pendentes"] == []
    assert _salao_em(await reservas(cliente)) == []


async def test_itens_3_e_4_aprovar_depois_do_reinicio_grava_uma_vez_e_reenvio_da_409(cliente, monkeypatch):
    session_id = await criar_sessao(cliente)

    # item 3: pedir, PARAR A API, SUBIR DE NOVO, aprovar → gravado exatamente uma vez
    corpo = await enviar(cliente, session_id, PEDIDO_SALAO)
    assert len(corpo["confirmacoes_pendentes"]) == 1, corpo
    id_pendencia = corpo["confirmacoes_pendentes"][0]["id"]

    reiniciar_api(monkeypatch)

    resposta = await cliente.post(
        f"/sessoes/{session_id}/confirmacoes", json={"id": id_pendencia, "confirmado": True}
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["confirmacoes_pendentes"] == []
    gravadas = _salao_em(await reservas(cliente))
    assert len(gravadas) == 1, gravadas
    assert gravadas[0]["codigo"].startswith("RSV-")

    # a tool de fato reexecutou: existe function_response de reservar_area depois da confirmação
    eventos = (await cliente.get(f"/sessoes/{session_id}/eventos")).json()
    respostas_da_tool = [
        part["function_response"]
        for evento in eventos
        for part in evento.get("content", {}).get("parts", [])
        if part.get("function_response", {}).get("name") == "reservar_area"
    ]
    assert any(r["response"].get("status") == "reservada" for r in respostas_da_tool), eventos

    # item 4: reenviar o mesmo id → 409, continua exatamente 1
    reenvio = await cliente.post(
        f"/sessoes/{session_id}/confirmacoes", json={"id": id_pendencia, "confirmado": True}
    )
    assert reenvio.status_code == 409
    assert len(_salao_em(await reservas(cliente))) == 1


async def test_quadra_reserva_direto_sem_pendencia(cliente):
    session_id = await criar_sessao(cliente)

    corpo = await enviar(cliente, session_id, "Reserve a quadra para 2030-04-22.")

    assert corpo["confirmacoes_pendentes"] == []
    gravadas = [r for r in await reservas(cliente) if r["area"] == "quadra" and r["data"] == "2030-04-22"]
    assert len(gravadas) == 1, corpo
