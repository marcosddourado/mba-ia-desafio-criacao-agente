"""Fase 1: esqueleto do repositório (dependências, `.gitignore`, `.env.example`, pacotes).

Nada aqui chama o Gemini nem lê o valor de `GOOGLE_API_KEY`: as checagens de
segredo usam `git grep -l` (só nomes de arquivo) e o `.env` real nunca é aberto.
"""

import importlib
import json
import re
import shutil
import subprocess
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

PADRAO_CHAVE = r"(AIza|AQ\.)[0-9A-Za-z._-]{20,}"


def _git(*args: str) -> subprocess.CompletedProcess:
    if shutil.which("git") is None or not (RAIZ / ".git").exists():
        pytest.skip("precisa do git e de um clone com .git")
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, timeout=60)


# ---- pyproject.toml, .python-version, uv.lock ------------------------------ #


def test_pyproject_fixa_google_adk_exatamente_na_2_2_0():
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))

    assert "google-adk===2.2.0" in pyproject["project"]["dependencies"]


def test_google_adk_instalado_e_a_2_2_0():
    assert version("google-adk") == "2.2.0"


def test_uv_lock_resolve_google_adk_2_2_0():
    bloco = re.search(r'name = "google-adk"\nversion = "([^"]+)"', (RAIZ / "uv.lock").read_text(encoding="utf-8"))

    assert bloco is not None
    assert bloco.group(1) == "2.2.0"


def test_pyproject_declara_as_dependencias_da_fase_1_e_o_readme():
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    nomes = {re.split(r"[=<>~! ]", d, maxsplit=1)[0] for d in pyproject["project"]["dependencies"]}

    assert {"google-adk", "fastapi", "uvicorn", "sqlalchemy", "aiosqlite", "asyncpg", "python-dotenv", "numpy"} <= nomes
    assert pyproject["project"]["readme"] == "README.md"
    assert (RAIZ / "README.md").is_file()


def test_python_version_e_3_12():
    assert (RAIZ / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


# ---- .gitignore ------------------------------------------------------------ #
# `--no-index`: sem ele o git não reporta como ignorado o que já está versionado
# (ex.: `.env.example`), e a regra de negação não seria testada de verdade.


@pytest.mark.parametrize(
    "caminho",
    [
        ".env",
        ".env.local",
        ".env.producao",
        ".adk/sessoes.db",
        ".adk/condominio.db",
        "condominio.db",
        "condominio.db-wal",
        "condominio.db-shm",
        ".adk/sessoes.db-wal",
        ".adk/sessoes.db-shm",
        ".venv/bin/python",
        "agents/__pycache__/x.pyc",
    ],
)
def test_gitignore_ignora(caminho):
    resultado = _git("check-ignore", "--no-index", "-q", caminho)

    assert resultado.returncode == 0, f"{caminho} deveria estar no .gitignore"


@pytest.mark.parametrize("caminho", [".env.example", ".vscode/settings.json", "env.py", "dados/areas.json"])
def test_gitignore_nao_ignora(caminho):
    resultado = _git("check-ignore", "--no-index", "-q", caminho)

    assert resultado.returncode == 1, f"{caminho} não pode estar no .gitignore"


def test_env_real_nao_esta_versionado():
    resultado = _git("ls-files")

    arquivos = resultado.stdout.splitlines()
    assert ".env" not in arquivos
    assert not [a for a in arquivos if re.search(r"(^|/)\.env($|\.(?!example$))", a)]
    assert ".env.example" in arquivos


# ---- .env.example ---------------------------------------------------------- #


def test_env_example_nao_tem_valor_em_google_api_key():
    linhas = (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
    chave = [linha for linha in linhas if linha.startswith("GOOGLE_API_KEY=")]

    assert len(chave) == 1
    assert chave[0] == "GOOGLE_API_KEY="


@pytest.mark.parametrize(
    "nome",
    ["GOOGLE_API_KEY", "MODELO_PRINCIPAL", "MODELO_ESPECIALISTAS", "MODELO_EMBEDDINGS", "SESSION_DB_PATH", "DATABASE_URL"],
)
def test_env_example_lista_a_variavel(nome):
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")

    # Aceita comentada (`# NOME=...`): as opcionais ficam comentadas no exemplo.
    assert re.search(rf"^#?\s*{nome}=", exemplo, re.MULTILINE)


def test_env_example_cobre_tudo_que_o_env_py_le():
    codigo = (RAIZ / "env.py").read_text(encoding="utf-8")
    lidas = set(re.findall(r"os\.environ\.get\(\s*[\"']([A-Z_]+)[\"']", codigo))
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")

    assert lidas
    for nome in lidas:
        assert re.search(rf"^#?\s*{nome}=", exemplo, re.MULTILINE), nome


def test_env_example_sem_valores_ativos_alem_dos_modelos():
    # Só `GOOGLE_API_KEY=` (vazio) e os três modelos ficam ativos; o resto vem comentado.
    ativas = {
        linha.split("=", 1)[0]
        for linha in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
        if linha.strip() and not linha.lstrip().startswith("#")
    }

    assert ativas == {"GOOGLE_API_KEY", "MODELO_PRINCIPAL", "MODELO_ESPECIALISTAS", "MODELO_EMBEDDINGS"}


# ---- segredos -------------------------------------------------------------- #


def test_nenhum_arquivo_versionado_ou_novo_tem_cara_de_chave_do_gemini():
    # `-l`: lista só nomes de arquivo, nunca a linha casada. `--untracked`: inclui o que
    # ainda não foi para o índice (a fase pode estar antes do commit). `.env` fica de fora
    # por estar no `.gitignore`.
    resultado = _git("grep", "-l", "-E", "--untracked", "-e", PADRAO_CHAVE)

    assert resultado.returncode == 1, f"padrão de chave em: {resultado.stdout.strip()}"
    assert resultado.stdout == ""


# ---- .vscode/settings.json ------------------------------------------------- #


def test_vscode_settings_aponta_para_o_venv_e_ao_pythonpath():
    cfg = json.loads((RAIZ / ".vscode" / "settings.json").read_text(encoding="utf-8"))

    assert cfg["python.defaultInterpreterPath"] == "${workspaceFolder}/.venv/bin/python"
    for plataforma in ("terminal.integrated.env.osx", "terminal.integrated.env.linux"):
        assert cfg[plataforma]["PYTHONPATH"] == "${workspaceFolder}"
        assert cfg[plataforma]["ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS"] == "1"


# ---- pacotes --------------------------------------------------------------- #


@pytest.mark.parametrize(
    "pacote",
    [
        "agents",
        "agents.residencial_aurora",
        "agents.residencial_aurora.subagents",
        "agents.residencial_aurora.tools",
        "db",
    ],
)
def test_pacote_importa(pacote):
    modulo = importlib.import_module(pacote)

    assert Path(modulo.__file__).name == "__init__.py"
    assert RAIZ in Path(modulo.__file__).resolve().parents


def test_dependencias_do_pronto_quando_importam():
    for nome in ("google.adk", "fastapi", "sqlalchemy", "aiosqlite", "numpy", "dotenv"):
        importlib.import_module(nome)
