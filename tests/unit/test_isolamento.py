"""Garante que o harness nunca usa o `.adk/` do projeto (regra do testador)."""

from pathlib import Path


def test_banco_de_sessoes_dos_testes_fica_fora_do_adk_do_projeto(dir_adk):
    import env

    adk_do_projeto = Path(env.RAIZ) / ".adk"
    assert Path(env.SESSION_DB_PATH).parent == dir_adk
    assert adk_do_projeto not in Path(env.SESSION_DB_PATH).parents
    assert env.DATABASE_URL and str(dir_adk) in env.DATABASE_URL
