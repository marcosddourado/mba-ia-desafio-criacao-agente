"""Tools de visitantes com ToolContext falso e banco SQLite temporário."""

import pytest

from agents.residencial_aurora.tools.visitantes import autorizar_visitante, listar_meus_visitantes
from db import repo

DATA = "2030-06-10"


async def test_autorizar_sempre_pede_confirmacao_e_nao_grava(banco, ctx):
    c = ctx("101")
    r = await autorizar_visitante("Carlos Souza", DATA, c)

    assert r == {"status": "aguardando_confirmacao"}
    assert c.pedidos[0]["payload"] == {"nome": "Carlos Souza", "data": DATA}
    assert c.pedidos[0]["hint"]
    assert await repo.listar_visitantes("101") == []


async def test_confirmada_grava_uma_vez(banco, ctx):
    r = await autorizar_visitante("Carlos Souza", DATA, ctx("101", confirmado=True))

    assert r == {"status": "autorizado", "nome": "Carlos Souza", "data": DATA}
    v = await repo.listar_visitantes("101")
    assert [(x.nome, x.data) for x in v] == [("Carlos Souza", DATA)]


async def test_nome_e_aparado_antes_de_pedir_e_de_gravar(banco, ctx):
    c = ctx("101")
    await autorizar_visitante("  Carlos Souza ", DATA, c)
    assert c.pedidos[0]["payload"]["nome"] == "Carlos Souza"
    await autorizar_visitante("  Carlos Souza ", DATA, ctx("101", True))
    assert (await repo.listar_visitantes("101"))[0].nome == "Carlos Souza"


async def test_negada_nao_grava(banco, ctx):
    c = ctx("101", confirmado=False)
    r = await autorizar_visitante("Carlos Souza", DATA, c)

    assert r["status"] == "nao_autorizado"
    assert c.pedidos == []
    assert await repo.listar_visitantes("101") == []


async def test_ja_autorizado_na_segunda_confirmacao(banco, ctx):
    await autorizar_visitante("Carlos Souza", DATA, ctx("101", True))
    r = await autorizar_visitante("Carlos Souza", DATA, ctx("101", True))

    assert r["status"] == "ja_autorizado"
    assert len(await repo.listar_visitantes("101")) == 1


async def test_mesmo_nome_em_outra_data_ou_outro_apartamento_e_permitido(banco, ctx):
    assert (await autorizar_visitante("Carlos Souza", DATA, ctx("101", True)))["status"] == "autorizado"
    assert (await autorizar_visitante("Carlos Souza", "2030-06-11", ctx("101", True)))["status"] == "autorizado"
    assert (await autorizar_visitante("Carlos Souza", DATA, ctx("102", True)))["status"] == "autorizado"


@pytest.mark.parametrize("nome", ["", "   ", None])
async def test_nome_vazio_levanta_value_error(banco, ctx, nome):
    with pytest.raises(ValueError, match="nome do visitante"):
        await autorizar_visitante(nome, DATA, ctx("101"))


async def test_data_invalida_levanta_value_error(banco, ctx):
    with pytest.raises(ValueError, match="Data inválida"):
        await autorizar_visitante("Carlos", "10/06/2030", ctx("101"))


async def test_sessao_sem_apartamento_levanta_value_error(banco, ctx):
    with pytest.raises(ValueError, match="sessão sem apartamento"):
        await autorizar_visitante("Carlos", DATA, ctx(None))
    with pytest.raises(ValueError, match="sessão sem apartamento"):
        await listar_meus_visitantes(ctx(None))


async def test_listar_so_do_apartamento_da_sessao(banco, ctx):
    await repo.autorizar_visitante("101", "Ana", "2030-06-02")
    await repo.autorizar_visitante("101", "Beto", "2030-06-01")
    await repo.autorizar_visitante("302", "Marina Duarte", "2030-06-01")

    r = await listar_meus_visitantes(ctx("101"))

    assert r == {"visitantes": [{"nome": "Beto", "data": "2030-06-01"}, {"nome": "Ana", "data": "2030-06-02"}]}
    assert "Marina" not in str(r)


async def test_listar_vazio(banco, ctx):
    assert await listar_meus_visitantes(ctx("101")) == {"visitantes": []}
