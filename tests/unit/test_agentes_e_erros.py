"""F3.8 (verificação estática) e `tratar_erro_tool`."""

import inspect
import logging

from google.adk.apps import App

from agents.residencial_aurora.agent import app, root_agent
from agents.residencial_aurora.plugins import ModelRetryPlugin
from agents.residencial_aurora.tools import reservas, visitantes
from agents.residencial_aurora.tools.erros import tratar_erro_tool

TOOLS = [
    reservas.listar_minhas_reservas,
    reservas.verificar_disponibilidade,
    reservas.reservar_area,
    reservas.cancelar_reserva,
    visitantes.listar_meus_visitantes,
    visitantes.autorizar_visitante,
]
SUBS = {a.name: a for a in root_agent.sub_agents}


def test_nenhuma_tool_aceita_apartamento():
    for t in TOOLS:
        assert "apartamento" not in inspect.signature(t).parameters, t.__name__


def test_tools_sao_async():
    assert all(inspect.iscoroutinefunction(t) for t in TOOLS)


def test_assinaturas_exatas_das_tools():
    assert list(inspect.signature(reservas.reservar_area).parameters) == ["area", "data", "tool_context"]
    assert list(inspect.signature(visitantes.autorizar_visitante).parameters) == ["nome", "data", "tool_context"]


def test_dois_especialistas_com_as_flags_certas():
    assert {"especialista_reservas", "especialista_visitantes"} <= set(SUBS)
    for n in ("especialista_reservas", "especialista_visitantes"):
        a = SUBS[n]
        assert a.mode == "chat", n
        assert not a.disallow_transfer_to_parent, n
        assert a.disallow_transfer_to_peers, n
        assert a.on_tool_error_callback is tratar_erro_tool, n


def test_tools_ligadas_aos_especialistas_certos():
    nomes = lambda a: {t.__name__ for t in a.tools}
    assert nomes(SUBS["especialista_reservas"]) == {t.__name__ for t in TOOLS[:4]}
    assert nomes(SUBS["especialista_visitantes"]) == {t.__name__ for t in TOOLS[4:]}


def test_sem_task_na_raiz():
    assert not any(getattr(a, "mode", None) == "task" for a in root_agent.sub_agents)


def test_instrucao_do_principal_sem_regulamento():
    assert "Art." not in root_agent.instruction and "Capítulo" not in root_agent.instruction
    assert not root_agent.tools


def test_app_com_model_retry_plugin_e_sem_resumability():
    assert isinstance(app, App)
    assert app.name == "residencial_aurora"
    assert any(isinstance(p, ModelRetryPlugin) for p in app.plugins)
    assert app.resumability_config is None


# tratar_erro_tool ############################
class _Tool:
    name = "tool_falsa"


def test_value_error_vira_a_mensagem_do_erro():
    r = tratar_erro_tool(_Tool(), {}, None, ValueError("Data inválida: x"))
    assert r == {"status": "error", "message": "Data inválida: x"}


def test_outro_erro_vira_mensagem_generica_sem_vazar_o_texto(caplog):
    with caplog.at_level(logging.ERROR):
        r = tratar_erro_tool(_Tool(), {}, None, RuntimeError("senha=segredo sqlite3 locked"))

    assert r["status"] == "error"
    assert "segredo" not in r["message"] and "sqlite" not in r["message"]
    assert "inesperado" in r["message"]
    assert "tool_falsa" in caplog.text  # o detalhe vai para o log, não para o morador
