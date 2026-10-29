import os

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import env
from .models import Base

ADK_PATH = f"{env.RAIZ}/.adk"
os.makedirs(ADK_PATH, exist_ok=True)

DATABASE_URL = env.DATABASE_URL or f"sqlite+aiosqlite:///{ADK_PATH}/condominio.db"
_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"timeout": 30} if _SQLITE else {},
)

if _SQLITE:

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas_sqlite(dbapi_conn, _):
        # WAL + espera por lock: duas aprovações simultâneas (passo 14) não
        # devem dar "database is locked".
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


async def init_db() -> None:
    """Cria as tabelas se não existirem (idempotente)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Fecha o pool de conexões — chamado no shutdown."""
    await engine.dispose()
