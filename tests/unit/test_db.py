"""Fase 2: camada `db/` contra SQLite em arquivo temporário (nunca `.adk/` nem `dados/`)."""

import asyncio
import re
import sqlite3

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import env
from db import dados, repo, restaurar as mod_restaurar
from db.models import Base


@pytest.fixture
async def banco(tmp_path, monkeypatch):
    caminho = tmp_path / "condominio.db"
    eng = create_async_engine(f"sqlite+aiosqlite:///{caminho}", connect_args={"timeout": 30})

    @event.listens_for(eng.sync_engine, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    sessao = async_sessionmaker(eng, expire_on_commit=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def fechar():
        await eng.dispose()

    monkeypatch.setattr(repo, "async_session", sessao)
    monkeypatch.setattr(mod_restaurar, "async_session", sessao)
    monkeypatch.setattr(mod_restaurar, "engine", eng)
    monkeypatch.setattr(mod_restaurar, "close_db", fechar)
    monkeypatch.setattr(env, "SESSION_DB_PATH", str(tmp_path / "sessoes.db"))
    yield caminho
    await eng.dispose()


# ÍNDICE PARCIAL ############################
async def test_duas_gravacoes_concorrentes_mesma_area_e_data_uma_vence(banco):
    res = await asyncio.gather(
        repo.criar_reserva("101", "churrasqueira", "2030-05-11"),
        repo.criar_reserva("102", "churrasqueira", "2030-05-11"),
        return_exceptions=True,
    )

    erros = [r for r in res if isinstance(r, IntegrityError)]
    ok = [r for r in res if not isinstance(r, BaseException)]
    assert len(ok) == 1 and len(erros) == 1
    assert ok[0].status == "ativa"


async def test_depois_de_cancelar_a_data_volta_a_poder_ser_reservada(banco):
    r1 = await repo.criar_reserva("101", "salao", "2030-05-11")
    assert await repo.cancelar_reserva("101", r1.codigo) is not None

    r2 = await repo.criar_reserva("102", "salao", "2030-05-11")

    assert r2.codigo != r1.codigo
    assert await repo.reserva_ativa_existe("salao", "2030-05-11")


async def test_canceladas_nao_colidem_entre_si(banco):
    for apto in ("101", "102", "103"):
        r = await repo.criar_reserva(apto, "salao", "2030-05-11")
        await repo.cancelar_reserva(apto, r.codigo)

    assert await repo.listar_reservas_ativas("101") == []
    assert not await repo.reserva_ativa_existe("salao", "2030-05-11")


async def test_mesma_data_em_areas_diferentes_nao_colide(banco):
    await repo.criar_reserva("101", "salao", "2030-05-11")
    await repo.criar_reserva("101", "churrasqueira", "2030-05-11")


async def test_codigo_tem_formato_rsv_e_8_hex_e_nao_repete(banco):
    codigos = [(await repo.criar_reserva("101", "salao", f"2030-06-{d:02d}")).codigo for d in range(1, 21)]

    assert all(re.fullmatch(r"RSV-[0-9A-F]{8}", c) for c in codigos)
    assert len(set(codigos)) == len(codigos)


# CANCELAR / LISTAR ############################
async def test_dono_cancela_e_ficam_dados_de_cancelamento(banco):
    r = await repo.criar_reserva("101", "salao", "2030-05-11")

    c = await repo.cancelar_reserva("101", r.codigo)

    assert c.status == "cancelada" and c.cancelado_em is not None


async def test_outro_apartamento_nao_cancela(banco):
    r = await repo.criar_reserva("101", "salao", "2030-05-11")

    assert await repo.cancelar_reserva("102", r.codigo) is None
    assert await repo.reserva_ativa_existe("salao", "2030-05-11")


async def test_cancelar_reserva_ja_cancelada_retorna_none(banco):
    r = await repo.criar_reserva("101", "salao", "2030-05-11")
    await repo.cancelar_reserva("101", r.codigo)

    assert await repo.cancelar_reserva("101", r.codigo) is None


async def test_cancelar_codigo_inexistente_retorna_none(banco):
    assert await repo.cancelar_reserva("101", "RSV-00000000") is None


async def test_listar_reservas_ativas_ordena_por_data_filtra_status_e_apartamento(banco):
    await repo.criar_reserva("101", "salao", "2030-07-01")
    await repo.criar_reserva("101", "churrasqueira", "2030-05-01")
    cancelada = await repo.criar_reserva("101", "salao", "2030-06-01")
    await repo.cancelar_reserva("101", cancelada.codigo)
    await repo.criar_reserva("102", "salao", "2030-04-01")

    lista = await repo.listar_reservas_ativas("101")

    assert [r.data for r in lista] == ["2030-05-01", "2030-07-01"]
    assert {r.apartamento for r in lista} == {"101"}


async def test_reserva_ativa_existe(banco):
    assert not await repo.reserva_ativa_existe("salao", "2030-05-11")
    await repo.criar_reserva("101", "salao", "2030-05-11")
    assert await repo.reserva_ativa_existe("salao", "2030-05-11")
    assert not await repo.reserva_ativa_existe("salao", "2030-05-12")
    assert not await repo.reserva_ativa_existe("churrasqueira", "2030-05-11")


# VISITANTES ############################
async def test_visitante_duplicado_levanta_integrity_error(banco):
    await repo.autorizar_visitante("101", "Maria", "2030-05-11")

    with pytest.raises(IntegrityError):
        await repo.autorizar_visitante("101", "Maria", "2030-05-11")


async def test_mesmo_visitante_em_outra_data_ou_apartamento_pode(banco):
    await repo.autorizar_visitante("101", "Maria", "2030-05-11")
    await repo.autorizar_visitante("101", "Maria", "2030-05-12")
    await repo.autorizar_visitante("102", "Maria", "2030-05-11")


async def test_listar_visitantes_so_do_apartamento_ordenado(banco):
    await repo.autorizar_visitante("101", "Zé", "2030-05-12")
    await repo.autorizar_visitante("101", "Ana", "2030-05-11")
    await repo.autorizar_visitante("102", "Outro", "2030-05-11")

    lista = await repo.listar_visitantes("101")

    assert [(v.nome, v.data) for v in lista] == [("Ana", "2030-05-11"), ("Zé", "2030-05-12")]


# SESSÕES ############################
async def test_criar_e_obter_sessao(banco):
    await repo.criar_sessao("abc", "101")

    s = await repo.obter_sessao("abc")

    assert s.apartamento == "101"
    assert await repo.obter_sessao("nao-existe") is None


async def test_criar_sessao_duplicada_levanta_integrity_error(banco):
    await repo.criar_sessao("abc", "101")

    with pytest.raises(IntegrityError):
        await repo.criar_sessao("abc", "102")


# ESQUEMA ############################
async def test_schema_tem_indice_unico_parcial_para_ativas(banco):
    con = sqlite3.connect(banco)
    try:
        sql = con.execute("SELECT sql FROM sqlite_master WHERE name='ux_reservas_area_data_ativa'").fetchone()[0]
    finally:
        con.close()

    assert "UNIQUE" in sql.upper()
    assert "WHERE status = 'ativa'" in sql


# DADOS ############################
@pytest.mark.parametrize("data", ["2030-05-11", "2028-02-29"])
def test_validar_data_aceita(data):
    assert dados.validar_data(data) == data


@pytest.mark.parametrize("data", ["2030/05/11", "2030-02-30", "", None, "11-05-2030", "2030-5-1"])
def test_validar_data_rejeita(data):
    with pytest.raises(ValueError):
        dados.validar_data(data)


def test_dados_6_apartamentos_e_3_areas_com_taxas():
    assert len(dados.APARTAMENTOS) == 6
    assert len(dados.AREAS) == 3
    assert sorted(a["taxa"] for a in dados.AREAS.values()) == [0.0, 80.0, 150.0]
    primeiro = next(iter(dados.APARTAMENTOS))
    assert dados.apartamento_existe(primeiro)
    assert not dados.apartamento_existe("999")
    area = next(iter(dados.AREAS))
    assert dados.area_por_id(area) == dados.AREAS[area]
    assert dados.area_por_id("piscina-olimpica") is None


# RESTAURAR ############################
async def test_restaurar_resultado_e_idempotente_e_apaga_sessoes(banco, tmp_path):
    sessoes = tmp_path / "sessoes.db"
    for suf in ("", "-wal", "-shm"):
        (tmp_path / f"sessoes.db{suf}").write_text("falso")
    await repo.criar_reserva("101", "salao", "2031-01-01")  # lixo a ser apagado

    await mod_restaurar.restaurar()
    await mod_restaurar.restaurar()

    for suf in ("", "-wal", "-shm"):
        assert not (tmp_path / f"sessoes.db{suf}").exists()
    assert not sessoes.exists()

    con = sqlite3.connect(banco)
    try:
        reservas = con.execute("SELECT codigo, status FROM reservas ORDER BY codigo").fetchall()
        visitantes = con.execute("SELECT count(*) FROM visitantes").fetchone()[0]
    finally:
        con.close()
    assert reservas == [("RSV-1377", "ativa"), ("RSV-2950", "ativa"), ("RSV-4821", "ativa")]
    assert visitantes == 2
