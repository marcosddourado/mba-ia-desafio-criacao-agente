"""Fase 1: `env.py` trata variável em branco como ausente e respeita valor definido.

O `env.py` lê o ambiente na importação (e chama `load_dotenv()`), então cada
cenário roda num subprocesso com `os.environ` totalmente controlado. O arquivo é
copiado para uma pasta temporária: assim o `.env` real do projeto nunca é
encontrado (`find_dotenv` parte da pasta do próprio `env.py`) e não mascara o
teste. Nenhum teste lê ou imprime `GOOGLE_API_KEY`.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

NOMES = ("MODELO_PRINCIPAL", "MODELO_ESPECIALISTAS", "MODELO_EMBEDDINGS", "SESSION_DB_PATH", "DATABASE_URL")

DEFAULTS = {
    "MODELO_PRINCIPAL": "gemini-3.1-flash-lite",
    "MODELO_ESPECIALISTAS": "gemini-3.5-flash-lite",
    "MODELO_EMBEDDINGS": "gemini-embedding-001",
}

_CODIGO = """
import json, sys
sys.path.insert(0, sys.argv[1])
import env
print(json.dumps({n: getattr(env, n) for n in sys.argv[2:]}))
"""


def _importar_env(pasta: Path, ambiente: dict[str, str], dotenv: str | None = None) -> dict:
    """Importa uma cópia de `env.py` em `pasta` com só `ambiente` no `os.environ`."""
    pasta.mkdir(exist_ok=True)
    shutil.copy(RAIZ / "env.py", pasta / "env.py")
    if dotenv is not None:
        (pasta / ".env").write_text(dotenv, encoding="utf-8")
    base = {"PATH": os.environ.get("PATH", ""), "HOME": str(pasta)}
    resultado = subprocess.run(
        [sys.executable, "-c", _CODIGO, str(pasta), "RAIZ", *NOMES],
        cwd=pasta,
        env={**base, **ambiente},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr[-500:]
    return json.loads(resultado.stdout.strip().splitlines()[-1])


def test_sem_variaveis_usa_os_defaults(tmp_path):
    env = _importar_env(tmp_path / "p", {})

    assert {n: env[n] for n in DEFAULTS} == DEFAULTS
    assert env["SESSION_DB_PATH"] == f"{env['RAIZ']}/.adk/sessoes.db"
    assert env["DATABASE_URL"] is None


def test_variaveis_em_branco_caem_no_default(tmp_path):
    em_branco = {n: "" for n in NOMES}

    env = _importar_env(tmp_path / "p", em_branco)

    assert {n: env[n] for n in DEFAULTS} == DEFAULTS
    assert env["SESSION_DB_PATH"] == f"{env['RAIZ']}/.adk/sessoes.db"
    assert env["DATABASE_URL"] is None


def test_valores_definidos_vencem_os_defaults(tmp_path):
    definidos = {
        "MODELO_PRINCIPAL": "modelo-a",
        "MODELO_ESPECIALISTAS": "modelo-b",
        "MODELO_EMBEDDINGS": "modelo-c",
        "SESSION_DB_PATH": "/tmp/aurora-teste/sessoes.db",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/aurora",
    }

    env = _importar_env(tmp_path / "p", definidos)

    assert {n: env[n] for n in NOMES} == definidos


def test_variavel_em_branco_no_ambiente_vence_o_dotenv(tmp_path):
    # `load_dotenv()` não sobrescreve o ambiente: "" no ambiente + valor no `.env` → default.
    dotenv = "MODELO_PRINCIPAL=do-dotenv\nDATABASE_URL=sqlite+aiosqlite:///do-dotenv.db\n"

    env = _importar_env(
        tmp_path / "p",
        {"MODELO_PRINCIPAL": "", "DATABASE_URL": ""},
        dotenv=dotenv,
    )

    assert env["MODELO_PRINCIPAL"] == DEFAULTS["MODELO_PRINCIPAL"]
    assert env["DATABASE_URL"] is None


def test_dotenv_e_lido_quando_a_variavel_nao_esta_no_ambiente(tmp_path):
    env = _importar_env(tmp_path / "p", {}, dotenv="MODELO_ESPECIALISTAS=do-dotenv\n")

    assert env["MODELO_ESPECIALISTAS"] == "do-dotenv"


def test_linha_em_branco_no_dotenv_cai_no_default(tmp_path):
    # O caso real do bug: `MODELO_PRINCIPAL=` no `.env` chega como "" e virava `Agent(model="")`.
    env = _importar_env(
        tmp_path / "p",
        {},
        dotenv="MODELO_PRINCIPAL=\nMODELO_ESPECIALISTAS=\nMODELO_EMBEDDINGS=\nSESSION_DB_PATH=\nDATABASE_URL=\n",
    )

    assert {n: env[n] for n in DEFAULTS} == DEFAULTS
    assert env["SESSION_DB_PATH"] == f"{env['RAIZ']}/.adk/sessoes.db"
    assert env["DATABASE_URL"] is None


def test_env_real_do_projeto_com_ambiente_em_branco_cai_nos_defaults(tmp_path):
    # Mesmo `env.py` do repositório (e `.env` real ao alcance): o ambiente em branco tem precedência.
    pasta = tmp_path / "p"
    pasta.mkdir()
    base = {"PATH": os.environ.get("PATH", ""), "HOME": str(pasta)}
    resultado = subprocess.run(
        [sys.executable, "-c", _CODIGO, str(RAIZ), "RAIZ", *NOMES],
        cwd=pasta,
        env={**base, **{n: "" for n in NOMES}},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr[-500:]
    env = json.loads(resultado.stdout.strip().splitlines()[-1])

    assert env["RAIZ"] == str(RAIZ)
    assert {n: env[n] for n in DEFAULTS} == DEFAULTS
    assert env["SESSION_DB_PATH"] == f"{RAIZ}/.adk/sessoes.db"
    assert env["DATABASE_URL"] is None


def test_env_py_nao_usa_default_do_get_para_nenhuma_variavel():
    # Regressão do bug: `os.environ.get(k, default)` deixa passar "" em branco.
    codigo = (RAIZ / "env.py").read_text(encoding="utf-8")

    assert not re.search(r"os\.environ\.get\(\s*[\"'][A-Z_]+[\"']\s*,", codigo)
    nomes_lidos = set(re.findall(r"os\.environ\.get\(\s*[\"']([A-Z_]+)[\"']", codigo))
    assert nomes_lidos == set(NOMES)


@pytest.mark.parametrize("nome", ["MODELO_PRINCIPAL", "MODELO_ESPECIALISTAS", "MODELO_EMBEDDINGS"])
def test_default_do_env_py_igual_ao_valor_do_env_example(nome):
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    valor = re.search(rf"^{nome}=(\S*)\s*$", exemplo, re.MULTILINE)

    assert valor is not None
    assert valor.group(1) == DEFAULTS[nome]
