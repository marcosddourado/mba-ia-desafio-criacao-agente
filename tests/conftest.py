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
from types import SimpleNamespace

import pytest

_DIR_ADK_TESTES = Path(tempfile.mkdtemp(prefix="aurora-harness-"))
atexit.register(shutil.rmtree, _DIR_ADK_TESTES, ignore_errors=True)
os.environ["SESSION_DB_PATH"] = str(_DIR_ADK_TESTES / "sessoes.db")
# `db/` só entra na Fase 2; já fica apontado para não vazar em `.adk/condominio.db`.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DIR_ADK_TESTES / 'condominio.db'}"


@pytest.fixture(autouse=True)
def arquivos_spike(tmp_path, monkeypatch):
    """Aponta os JSONs do spike (reservas e mapa de sessões) para `tmp_path`.

    `web.py` importa `ARQUIVO_RESERVAS` por nome, então o módulo do agente e o
    `web` têm vínculos separados; os dois apontam para o mesmo arquivo para que
    a tool grave onde `GET /apartamentos/{n}/reservas` lê.
    """
    import web
    from agents.residencial_aurora import agent

    reservas = tmp_path / "spike_reservas.json"
    sessoes = tmp_path / "spike_sessoes.json"
    monkeypatch.setattr(agent, "ARQUIVO_RESERVAS", str(reservas))
    monkeypatch.setattr(web, "ARQUIVO_RESERVAS", str(reservas))
    monkeypatch.setattr(web, "ARQUIVO_SESSOES", str(sessoes))
    return SimpleNamespace(reservas=reservas, sessoes=sessoes, dir_adk=_DIR_ADK_TESTES)
