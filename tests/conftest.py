"""Isolamento do harness: nenhum teste toca o `.adk/` do projeto nem `dados/`.

`web.py` abre o `SqliteSessionService(env.SESSION_DB_PATH)` na importação e
`env.py` lê o ambiente uma vez; por isso as variáveis são setadas aqui, no
nível do módulo, ANTES do primeiro `import web` / `import env` de qualquer
teste. `load_dotenv()` não sobrescreve o que já está em `os.environ`, então o
`.env` do projeto não consegue redirecionar o banco de volta para `.adk/`.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_DIR_ADK_TESTES = Path(tempfile.mkdtemp(prefix="aurora-harness-"))
atexit.register(shutil.rmtree, _DIR_ADK_TESTES, ignore_errors=True)
os.environ["SESSION_DB_PATH"] = str(_DIR_ADK_TESTES / "sessoes.db")
# `db/` só entra na Fase 2; já fica apontado para não vazar em `.adk/condominio.db`.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DIR_ADK_TESTES / 'condominio.db'}"


@pytest.fixture
def dir_adk():
    """Diretório temporário que hospeda o banco de sessões dos testes (nunca `.adk/`)."""
    return _DIR_ADK_TESTES


class ConfirmacaoFalsa:
    def __init__(self, confirmed: bool):
        self.confirmed = confirmed


class ToolContextFalso:
    """Só o que as tools usam: `state`, `tool_confirmation` e `request_confirmation`."""

    def __init__(self, state=None, tool_confirmation=None):
        self.state = {} if state is None else state
        self.tool_confirmation = tool_confirmation
        self.pedidos: list[dict] = []

    def request_confirmation(self, *, hint=None, payload=None) -> None:
        self.pedidos.append({"hint": hint, "payload": payload})


@pytest.fixture
def ctx():
    """Fábrica de contexto: `ctx("101")`, `ctx("101", True)` (confirmada), `ctx(None)` (sem apartamento)."""

    def fabrica(apartamento="101", confirmado=None):
        state = {} if apartamento is None else {"apartamento": apartamento}
        conf = None if confirmado is None else ConfirmacaoFalsa(confirmado)
        return ToolContextFalso(state=state, tool_confirmation=conf)

    return fabrica


@pytest.fixture
async def banco(tmp_path, monkeypatch):
    """SQLite temporário com o esquema criado, ligado ao `repo` (nunca `.adk/`)."""
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from db import repo
    from db.models import Base

    eng = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'condominio.db'}", connect_args={"timeout": 30}
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(repo, "async_session", async_sessionmaker(eng, expire_on_commit=False))
    yield tmp_path / "condominio.db"
    await eng.dispose()
