"""Restaura o estado inicial: `uv run python -m db.restaurar` (offline, sem Gemini)."""

import os
from asyncio import run

import env
from db.dados import ler_json
from db.engine import async_session, close_db, engine
from db.models import Base, ReservaModel, VisitanteModel


def _apagar_sessoes() -> None:
    """Apaga as sessões do ADK, inclusive os arquivos -wal/-shm do SQLite."""
    for sufixo in ("", "-wal", "-shm"):
        try:
            os.remove(env.SESSION_DB_PATH + sufixo)
        except FileNotFoundError:
            pass


async def restaurar() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    reservas = ler_json("reservas.json")
    visitantes = ler_json("visitantes.json")
    async with async_session.begin() as session:
        session.add_all(ReservaModel(status="ativa", **r) for r in reservas)
        session.add_all(VisitanteModel(**v) for v in visitantes)
    await close_db()

    _apagar_sessoes()
    print(f"{len(reservas)} reservas, {len(visitantes)} visitantes, sessões apagadas")


if __name__ == "__main__":
    run(restaurar())
