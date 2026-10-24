"""Tool `reservar_area` com um ToolContext falso: confirmação, gravação e erros tratados."""

import inspect
import json

import pytest

from agents.residencial_aurora import agent
from agents.residencial_aurora.agent import TAXAS, reservar_area


class ConfirmacaoFalsa:
    def __init__(self, confirmed: bool):
        self.confirmed = confirmed


class ToolContextFalso:
    """Só o que a tool usa: `state`, `tool_confirmation` e `request_confirmation`."""

    def __init__(self, state=None, tool_confirmation=None):
        self.state = {} if state is None else state
        self.tool_confirmation = tool_confirmation
        self.pedidos: list[dict] = []

    def request_confirmation(self, *, hint=None, payload=None) -> None:
        self.pedidos.append({"hint": hint, "payload": payload})


def _reservas_gravadas(arquivos_spike) -> list[dict]:
    if not arquivos_spike.reservas.exists():
        return []
    return json.loads(arquivos_spike.reservas.read_text(encoding="utf-8"))


@pytest.fixture
def contexto_101():
    return ToolContextFalso(state={"apartamento": "101"})


# --------------------------------------------------------------------------- #
# Regra do plano: nenhuma tool aceita `apartamento`                            #
# --------------------------------------------------------------------------- #


def test_tool_nao_aceita_apartamento_como_parametro():
    parametros = list(inspect.signature(reservar_area).parameters)
    assert parametros == ["area", "data", "tool_context"]
    assert "apartamento" not in parametros


def test_taxas_do_spike():
    assert TAXAS == {"salao-de-festas": 150.0, "churrasqueira": 80.0, "quadra": 0.0}


# --------------------------------------------------------------------------- #
# Garantia 1: cobrança só com confirmação                                      #
# --------------------------------------------------------------------------- #


def test_area_com_taxa_sem_confirmacao_pede_confirmacao_e_nao_grava(contexto_101, arquivos_spike):
    resultado = reservar_area("salao-de-festas", "2030-04-20", contexto_101)

    assert resultado == {"status": "aguardando_confirmacao"}
    assert len(contexto_101.pedidos) == 1
    pedido = contexto_101.pedidos[0]
    assert pedido["payload"] == {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0}
    assert "150.00" in pedido["hint"]
    assert "salao-de-festas" in pedido["hint"] and "2030-04-20" in pedido["hint"]
    assert _reservas_gravadas(arquivos_spike) == []


def test_churrasqueira_pede_confirmacao_com_taxa_80(contexto_101, arquivos_spike):
    resultado = reservar_area("churrasqueira", "2030-05-01", contexto_101)

    assert resultado["status"] == "aguardando_confirmacao"
    assert contexto_101.pedidos[0]["payload"]["taxa"] == 80.0
    assert _reservas_gravadas(arquivos_spike) == []


def test_confirmacao_negada_nao_grava_e_nao_pede_de_novo(arquivos_spike):
    contexto = ToolContextFalso(state={"apartamento": "101"}, tool_confirmation=ConfirmacaoFalsa(False))

    resultado = reservar_area("salao-de-festas", "2030-04-20", contexto)

    assert resultado == {"status": "nao_confirmada", "area": "salao-de-festas", "data": "2030-04-20"}
    assert contexto.pedidos == []
    assert _reservas_gravadas(arquivos_spike) == []


def test_confirmacao_aprovada_grava_exatamente_uma_reserva_com_codigo_rsv(arquivos_spike):
    contexto = ToolContextFalso(state={"apartamento": "101"}, tool_confirmation=ConfirmacaoFalsa(True))

    resultado = reservar_area("salao-de-festas", "2030-04-20", contexto)

    assert resultado["status"] == "reservada"
    assert resultado["codigo"].startswith("RSV-")
    assert len(resultado["codigo"]) == len("RSV-") + 8
    assert resultado["area"] == "salao-de-festas"
    assert resultado["data"] == "2030-04-20"
    assert resultado["taxa"] == 150.0
    assert contexto.pedidos == []

    gravadas = _reservas_gravadas(arquivos_spike)
    assert gravadas == [
        {"codigo": resultado["codigo"], "apartamento": "101", "area": "salao-de-festas", "data": "2030-04-20"}
    ]


def test_apartamento_gravado_vem_do_state_da_sessao(arquivos_spike):
    contexto = ToolContextFalso(state={"apartamento": "302"}, tool_confirmation=ConfirmacaoFalsa(True))

    reservar_area("churrasqueira", "2030-06-10", contexto)

    assert _reservas_gravadas(arquivos_spike)[0]["apartamento"] == "302"


# --------------------------------------------------------------------------- #
# Exclusividade: área + data só uma vez                                        #
# --------------------------------------------------------------------------- #


def test_data_ocupada_devolve_indisponivel_e_nao_grava_segunda(arquivos_spike):
    primeiro = ToolContextFalso(state={"apartamento": "302"}, tool_confirmation=ConfirmacaoFalsa(True))
    segundo = ToolContextFalso(state={"apartamento": "101"}, tool_confirmation=ConfirmacaoFalsa(True))

    reservar_area("salao-de-festas", "2030-04-20", primeiro)
    resultado = reservar_area("salao-de-festas", "2030-04-20", segundo)

    assert resultado == {"status": "indisponivel", "area": "salao-de-festas", "data": "2030-04-20"}
    gravadas = _reservas_gravadas(arquivos_spike)
    assert len(gravadas) == 1
    assert gravadas[0]["apartamento"] == "302"


def test_mesma_area_em_outra_data_e_outra_area_na_mesma_data_sao_reservadas(arquivos_spike):
    def contexto():
        return ToolContextFalso(state={"apartamento": "101"}, tool_confirmation=ConfirmacaoFalsa(True))

    assert reservar_area("salao-de-festas", "2030-04-20", contexto())["status"] == "reservada"
    assert reservar_area("salao-de-festas", "2030-04-21", contexto())["status"] == "reservada"
    assert reservar_area("churrasqueira", "2030-04-20", contexto())["status"] == "reservada"
    assert len(_reservas_gravadas(arquivos_spike)) == 3


def test_reservas_distintas_recebem_codigos_distintos(arquivos_spike):
    contexto = ToolContextFalso(state={"apartamento": "101"})

    codigos = {
        reservar_area("quadra", "2030-04-20", contexto)["codigo"],
        reservar_area("quadra", "2030-04-21", contexto)["codigo"],
        reservar_area("quadra", "2030-04-22", contexto)["codigo"],
    }

    assert len(codigos) == 3
    assert {reserva["codigo"] for reserva in _reservas_gravadas(arquivos_spike)} == codigos


# --------------------------------------------------------------------------- #
# Quadra (taxa zero): reserva direto                                           #
# --------------------------------------------------------------------------- #


def test_quadra_reserva_direto_sem_pedir_confirmacao(contexto_101, arquivos_spike):
    resultado = reservar_area("quadra", "2030-04-20", contexto_101)

    assert resultado["status"] == "reservada"
    assert resultado["taxa"] == 0.0
    assert resultado["codigo"].startswith("RSV-")
    assert contexto_101.pedidos == []
    gravadas = _reservas_gravadas(arquivos_spike)
    assert len(gravadas) == 1
    assert gravadas[0]["area"] == "quadra"


def test_quadra_em_data_ocupada_tambem_devolve_indisponivel(arquivos_spike):
    reservar_area("quadra", "2030-04-20", ToolContextFalso(state={"apartamento": "302"}))

    resultado = reservar_area("quadra", "2030-04-20", ToolContextFalso(state={"apartamento": "101"}))

    assert resultado["status"] == "indisponivel"
    assert len(_reservas_gravadas(arquivos_spike)) == 1


# --------------------------------------------------------------------------- #
# Erros tratados (sem exceção, sem gravação, sem pedido de confirmação)        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", [{}, {"apartamento": ""}, {"apartamento": None}], ids=["sem-chave", "vazio", "None"])
def test_sessao_sem_apartamento_devolve_erro_tratado(state, arquivos_spike):
    contexto = ToolContextFalso(state=state)

    resultado = reservar_area("quadra", "2030-04-20", contexto)

    assert resultado["status"] == "error"
    assert "apartamento" in resultado["message"].lower()
    assert contexto.pedidos == []
    assert _reservas_gravadas(arquivos_spike) == []


def test_area_desconhecida_devolve_erro_tratado(contexto_101, arquivos_spike):
    resultado = reservar_area("piscina", "2030-04-20", contexto_101)

    assert resultado["status"] == "error"
    assert "piscina" in resultado["message"]
    assert contexto_101.pedidos == []
    assert _reservas_gravadas(arquivos_spike) == []


def test_area_desconhecida_nao_consulta_o_arquivo_de_reservas(contexto_101, arquivos_spike, monkeypatch):
    def nao_deveria_ler():
        raise AssertionError("não deveria ler as reservas para uma área desconhecida")

    monkeypatch.setattr(agent, "_ler_reservas", nao_deveria_ler)

    assert reservar_area("piscina", "2030-04-20", contexto_101)["status"] == "error"
