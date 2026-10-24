"""Variáveis de ambiente do projeto, lidas uma vez do `.env` (como `env.py` da referência)."""

import os

from dotenv import load_dotenv

load_dotenv()

RAIZ = __file__.rsplit("/", 1)[0]

# Modelos por papel (docs/decisoes-tecnicas.md, D5): principal leve, especialistas fortes.
MODELO_PRINCIPAL = os.environ.get("MODELO_PRINCIPAL", "gemini-3.5-flash-lite")
MODELO_ESPECIALISTAS = os.environ.get("MODELO_ESPECIALISTAS", "gemini-3.8-flash")
MODELO_EMBEDDINGS = os.environ.get("MODELO_EMBEDDINGS", "gemini-embedding-001")

# Onde o SqliteSessionService guarda as sessões (D3). Pasta `.adk/` fica fora do Git.
SESSION_DB_PATH = os.environ.get("SESSION_DB_PATH", f"{RAIZ}/.adk/sessoes.db")

# Banco do condomínio (D4). `None` → `db/engine.py` usa SQLite em `.adk/condominio.db`.
DATABASE_URL = os.environ.get("DATABASE_URL")
