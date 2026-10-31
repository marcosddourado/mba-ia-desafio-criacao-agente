"""`adk web agents` carrega o agente só com a raiz no PYTHONPATH (Registro #13)."""

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

_CODIGO = (
    "from google.adk.cli.utils.agent_loader import AgentLoader;"
    "print(type(AgentLoader('agents').load_agent('residencial_aurora')).__name__)"
)


def _carregar(pythonpath: str | None) -> subprocess.CompletedProcess:
    ambiente = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if pythonpath:
        ambiente["PYTHONPATH"] = pythonpath
    # `-P`: não coloca o cwd no sys.path, como o executável `adk` (o `-c` poria).
    return subprocess.run(
        [sys.executable, "-P", "-c", _CODIGO],
        cwd=RAIZ, env=ambiente, capture_output=True, text=True, timeout=120,
    )


def test_agente_carrega_com_a_raiz_no_pythonpath():
    resultado = _carregar(str(RAIZ))
    assert resultado.returncode == 0, resultado.stderr[-400:]
    assert resultado.stdout.strip() == "App"


def test_sem_pythonpath_o_adk_web_nao_acha_o_env():
    """Documenta o porquê de o README mandar `PYTHONPATH=. uv run adk web agents`."""
    resultado = _carregar(None)
    assert resultado.returncode != 0
    assert "No module named 'env'" in resultado.stderr
