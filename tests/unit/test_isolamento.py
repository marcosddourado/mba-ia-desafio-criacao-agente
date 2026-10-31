"""Garante que o harness nunca usa o `.adk/` do projeto (regra do testador)."""

from pathlib import Path


def test_banco_de_sessoes_dos_testes_fica_fora_do_adk_do_projeto(arquivos_spike):
    import env
    import web

    adk_do_projeto = Path(env.RAIZ) / ".adk"
    assert Path(env.SESSION_DB_PATH).parent == arquivos_spike.dir_adk
    assert adk_do_projeto not in Path(env.SESSION_DB_PATH).parents
    assert adk_do_projeto not in Path(web.ARQUIVO_SESSOES).parents
