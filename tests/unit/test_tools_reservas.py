"""Tools de reservas com ToolContext falso e banco SQLite temporário."""

import asyncio

import pytest

from agents.residencial_aurora.tools.reservas import (
    cancelar_reserva,
    listar_minhas_reservas,
    reservar_area,
    verificar_disponibilidade,
)
from db import repo

DATA = "2030-04-20"


# RESERVAR: ÁREA COM TAXA (Garantia 1) ############################
async def test_salao_primeira_passagem_pede_confirmacao_e_nao_grava(banco, ctx):
    c = ctx("101")
    r = await reservar_area("salao-de-festas", DATA, c)

    assert r == {"status": "aguardando_confirmacao"}
    assert len(c.pedidos) == 1
    assert c.pedidos[0]["payload"] == {"area": "salao-de-festas", "data": DATA, "taxa": 150.0}
    assert c.pedidos[0]["hint"]
    assert await repo.listar_reservas_ativas("101") == []


async def test_churrasqueira_pede_confirmacao_com_taxa_80(banco, ctx):
    c = ctx("101")
    await reservar_area("churrasqueira", DATA, c)
    assert c.pedidos[0]["payload"] == {"area": "churrasqueira", "data": DATA, "taxa": 80.0}


async def test_segunda_passagem_confirmada_grava_uma_reserva(banco, ctx):
    c = ctx("101", confirmado=True)
    r = await reservar_area("salao-de-festas", DATA, c)

    assert r["status"] == "reservada"
    assert r["codigo"].startswith("RSV-")
    assert r["taxa"] == 150.0
    assert c.pedidos == []
    gravadas = await repo.listar_reservas_ativas("101")
    assert [(g.codigo, g.area, g.data) for g in gravadas] == [(r["codigo"], "salao-de-festas", DATA)]


async def test_confirmacao_negada_nao_grava(banco, ctx):
    c = ctx("101", confirmado=False)
    r = await reservar_area("salao-de-festas", DATA, c)

    assert r["status"] == "nao_confirmada"
    assert c.pedidos == []
    assert await repo.listar_reservas_ativas("101") == []


async def test_data_ocupada_e_indisponivel_ja_na_primeira_passagem_sem_pendencia(banco, ctx):
    await repo.criar_reserva("302", "salao-de-festas", DATA)
    c = ctx("101")
    r = await reservar_area("salao-de-festas", DATA, c)

    assert r["status"] == "indisponivel"
    assert c.pedidos == []
    assert await repo.listar_reservas_ativas("101") == []


async def test_ocupada_entre_o_pedido_e_a_aprovacao_vira_indisponivel(banco, ctx):
    c1 = ctx("101")
    assert (await reservar_area("salao-de-festas", DATA, c1))["status"] == "aguardando_confirmacao"
    await repo.criar_reserva("302", "salao-de-festas", DATA)  # outro morador fecha antes

    r = await reservar_area("salao-de-festas", DATA, ctx("101", confirmado=True))

    assert r["status"] == "indisponivel"
    assert await repo.listar_reservas_ativas("101") == []


async def test_indisponivel_nao_vaza_dono_nem_codigo(banco, ctx):
    criada = await repo.criar_reserva("302", "salao-de-festas", DATA)
    r = await reservar_area("salao-de-festas", DATA, ctx("101"))
    texto = str(r)
    assert "302" not in texto and criada.codigo not in texto


# RESERVAR: QUADRA (sem taxa) ############################
async def test_quadra_reserva_direto_sem_pendencia(banco, ctx):
    c = ctx("101")
    r = await reservar_area("quadra", DATA, c)

    assert r["status"] == "reservada"
    assert r["taxa"] == 0.0
    assert c.pedidos == []
    assert len(await repo.listar_reservas_ativas("101")) == 1


async def test_apartamento_gravado_vem_do_state(banco, ctx):
    await reservar_area("quadra", DATA, ctx("205"))
    assert len(await repo.listar_reservas_ativas("205")) == 1
    assert await repo.listar_reservas_ativas("101") == []


async def test_mesma_area_outra_data_e_outra_area_mesma_data_sao_reservadas(banco, ctx):
    assert (await reservar_area("quadra", DATA, ctx("101")))["status"] == "reservada"
    assert (await reservar_area("quadra", "2030-04-21", ctx("101")))["status"] == "reservada"
    assert (await reservar_area("churrasqueira", DATA, ctx("101", True)))["status"] == "reservada"


async def test_concorrencia_cinco_na_mesma_quadra_e_data_uma_vence(banco, ctx):
    apartamentos = ["101", "102", "201", "202", "301"]
    res = await asyncio.gather(*(reservar_area("quadra", DATA, ctx(a)) for a in apartamentos))

    status = sorted(r["status"] for r in res)
    assert status == ["indisponivel"] * 4 + ["reservada"]
    donos = [a for a in apartamentos if await repo.listar_reservas_ativas(a)]
    assert len(donos) == 1


async def test_cancelada_libera_a_data(banco, ctx):
    r = await reservar_area("quadra", DATA, ctx("101"))
    await cancelar_reserva(r["codigo"], ctx("101"))
    assert (await reservar_area("quadra", DATA, ctx("102")))["status"] == "reservada"


# RESERVAR: ERROS ############################
@pytest.mark.parametrize("state", [None, ""], ids=["sem-chave", "vazio"])
async def test_sessao_sem_apartamento_levanta_value_error(banco, ctx, state):
    c = ctx(state if state is not None else None)
    if state == "":
        c.state["apartamento"] = ""
    for chamada in (
        reservar_area("quadra", DATA, c),
        listar_minhas_reservas(c),
        verificar_disponibilidade("quadra", DATA, c),
        cancelar_reserva("RSV-1", c),
    ):
        with pytest.raises(ValueError, match="sessão sem apartamento"):
            await chamada


async def test_area_desconhecida_levanta_value_error(banco, ctx):
    with pytest.raises(ValueError, match="Área desconhecida"):
        await reservar_area("piscina", DATA, ctx("101"))


@pytest.mark.parametrize("data", ["20/04/2030", "2030-02-30", "", "amanhã"])
async def test_data_invalida_levanta_value_error(banco, ctx, data):
    with pytest.raises(ValueError, match="Data inválida"):
        await reservar_area("quadra", data, ctx("101"))


# LISTAR ############################
async def test_listar_minhas_reservas_so_do_apartamento_e_ordenadas_por_data(banco, ctx):
    await repo.criar_reserva("101", "quadra", "2030-05-02")
    await repo.criar_reserva("101", "churrasqueira", "2030-05-01")
    await repo.criar_reserva("302", "salao-de-festas", "2030-05-03")

    r = await listar_minhas_reservas(ctx("101"))

    assert [x["data"] for x in r["reservas"]] == ["2030-05-01", "2030-05-02"]
    assert all(set(x) == {"codigo", "area", "data"} for x in r["reservas"])


async def test_listar_sem_reservas_devolve_lista_vazia(banco, ctx):
    assert await listar_minhas_reservas(ctx("101")) == {"reservas": []}


# DISPONIBILIDADE ############################
async def test_disponibilidade_livre_e_ocupada_sem_dono(banco, ctx):
    assert await verificar_disponibilidade("quadra", DATA, ctx("101")) == {
        "area": "quadra", "data": DATA, "disponivel": True,
    }
    criada = await repo.criar_reserva("302", "quadra", DATA)

    r = await verificar_disponibilidade("quadra", DATA, ctx("101"))

    assert r == {"area": "quadra", "data": DATA, "disponivel": False}
    assert "302" not in str(r) and criada.codigo not in str(r)


async def test_disponibilidade_area_desconhecida_e_data_invalida(banco, ctx):
    with pytest.raises(ValueError):
        await verificar_disponibilidade("piscina", DATA, ctx("101"))
    with pytest.raises(ValueError):
        await verificar_disponibilidade("quadra", "x", ctx("101"))


# CANCELAR ############################
async def test_cancelar_a_propria_reserva_sem_pendencia(banco, ctx):
    criada = await repo.criar_reserva("101", "quadra", DATA)
    c = ctx("101")

    r = await cancelar_reserva(criada.codigo, c)

    assert r == {"status": "cancelada", "codigo": criada.codigo}
    assert c.pedidos == []
    assert await repo.listar_reservas_ativas("101") == []


async def test_cancelar_aceita_codigo_em_minusculas_com_espacos(banco, ctx):
    criada = await repo.criar_reserva("101", "quadra", DATA)
    r = await cancelar_reserva(f"  {criada.codigo.lower()} ", ctx("101"))
    assert r["status"] == "cancelada"


async def test_cancelar_de_outro_apartamento_e_igual_a_codigo_inexistente(banco, ctx):
    alheia = await repo.criar_reserva("302", "quadra", DATA)

    de_outro = await cancelar_reserva(alheia.codigo, ctx("101"))
    inexistente = await cancelar_reserva("RSV-0000", ctx("101"))

    assert de_outro["status"] == inexistente["status"] == "nao_encontrada"
    assert set(de_outro) == set(inexistente) == {"status", "codigo"}
    assert "302" not in str(de_outro)
    assert len(await repo.listar_reservas_ativas("302")) == 1  # intacta


async def test_cancelar_duas_vezes_a_segunda_e_nao_encontrada(banco, ctx):
    criada = await repo.criar_reserva("101", "quadra", DATA)
    await cancelar_reserva(criada.codigo, ctx("101"))
    assert (await cancelar_reserva(criada.codigo, ctx("101")))["status"] == "nao_encontrada"
