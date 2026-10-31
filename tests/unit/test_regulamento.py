"""Fase 4: chunker, busca por capítulo, cache do índice e `_embedar` (sem Gemini real)."""

import asyncio
import json
import os
import re

import numpy as np
import pytest
from google.genai import errors as genai_errors

import env
from agents.residencial_aurora.tools import regulamento as reg
from agents.residencial_aurora.tools.regulamento import Artigo, IndiceRegulamento

_SLEEP_REAL = asyncio.sleep  # o autouse troca asyncio.sleep por um no-op que não cede o loop
ARTIGOS = reg.carregar_artigos()
CAPITULOS = list(dict.fromkeys(a.capitulo_numero for a in ARTIGOS))


# ---------------------------------------------------------------- fixtures
def _eixo(i: int, peso: float = 1.0) -> np.ndarray:
    v = np.zeros(reg.DIMENSOES, dtype=np.float32)
    v[i] = peso
    return v


def _vetor_chunk(artigo: Artigo) -> np.ndarray:
    # Um eixo por capítulo: documentos do mesmo capítulo são idênticos.
    return _eixo(CAPITULOS.index(artigo.capitulo_numero))


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    """Cache em tmp_path, singleton e locks zerados, sem espera real."""
    monkeypatch.setattr(reg, "CAMINHO_INDICE", str(tmp_path / "idx" / "regulamento.index.json"))
    monkeypatch.setattr(IndiceRegulamento, "_instancia", None)
    monkeypatch.setattr(reg, "_locks", {})

    async def sem_espera(_):
        return None

    monkeypatch.setattr(reg.asyncio, "sleep", sem_espera)


@pytest.fixture
def embedar(monkeypatch):
    """`_embedar` sintético: documento -> eixo do capítulo; consulta -> `consulta_eixo`."""
    estado = {"docs": 0, "consultas": 0, "consulta": _eixo(CAPITULOS.index("IV"))}

    async def falso(textos, tarefa):
        await _SLEEP_REAL(0)
        if tarefa == "RETRIEVAL_DOCUMENT":
            estado["docs"] += 1
            # calculado na hora: segue o modelo vigente (formatação -001 ou -2)
            mapa = {reg._texto_do_chunk(ARTIGOS, i): _vetor_chunk(a) for i, a in enumerate(ARTIGOS)}
            return np.array([mapa[t] for t in textos])
        estado["consultas"] += 1
        return np.array([estado["consulta"] for _ in textos])

    monkeypatch.setattr(reg, "_embedar", falso)
    return estado


def _indice_pequeno(spec: list[tuple[str, float]]) -> tuple[IndiceRegulamento, np.ndarray]:
    """Artigos com cosseno `s` contra a consulta (eixo 0). `spec` = [(capítulo, s)]."""
    artigos, linhas = [], []
    for n, (cap, s) in enumerate(spec, start=1):
        artigos.append(Artigo(cap, f"Titulo {cap}", f"Art. {n}", f"**Art. {n}.** x"))
        v = _eixo(0, s) + _eixo(n, float(np.sqrt(1 - s * s)))
        linhas.append(v)
    return IndiceRegulamento(artigos, np.array(linhas, dtype=np.float32)), _eixo(0)


# ---------------------------------------------------------------- chunker
def test_96_artigos_distintos_em_14_capitulos():
    rotulos = [a.artigo for a in ARTIGOS]
    assert len(ARTIGOS) == 96 and len(set(rotulos)) == 96
    assert len(CAPITULOS) == 14


def test_artigo_com_ordinal_e_com_ponto_reconhecidos():
    por = {a.artigo: a for a in ARTIGOS}
    assert por["Art. 9"].texto.startswith("**Art. 9º**")
    assert por["Art. 22"].texto.startswith("**Art. 22.**")


def test_todo_texto_comeca_com_o_artigo_e_nao_tem_capitulo():
    for a in ARTIGOS:
        assert a.texto.startswith(f"**Art. {a.artigo.split()[1]}"), a.artigo
        assert "## Capítulo" not in a.texto, a.artigo


def test_ultimo_artigo_de_cada_capitulo_nao_traz_o_titulo_do_seguinte():
    titulos = {}
    for a in ARTIGOS:
        titulos.setdefault(a.capitulo_numero, a.capitulo_titulo)
    ordem = list(titulos)
    for atual, proximo in zip(ordem, ordem[1:]):
        ultimo = [a for a in ARTIGOS if a.capitulo_numero == atual][-1]
        assert f"Capítulo {proximo}" not in ultimo.texto
        assert f"## {titulos[proximo]}" not in ultimo.texto


def test_artigo_nao_contem_o_inicio_do_artigo_seguinte():
    for a, b in zip(ARTIGOS, ARTIGOS[1:]):
        assert len(re.findall(r"^\*\*Art\. ", a.texto, flags=re.M)) == 1, a.artigo


def test_art_22_tem_horario_de_domingo():
    art22 = next(a for a in ARTIGOS if a.artigo == "Art. 22")
    assert "9h às 20h" in art22.texto
    assert art22.capitulo_numero == "IV" and art22.capitulo_titulo == "Piscina"


# ---------------------------------------------------------------- mais_similares
def test_filtra_ao_capitulo_vencedor_por_soma():
    # I: um artigo a 0,9; II: quatro a 0,7 (soma maior) -> vence II.
    indice, q = _indice_pequeno([("I", 0.9)] + [("II", 0.7)] * 4)
    r = indice.mais_similares(q)
    assert r.capitulo_numero == "II"
    assert {a.capitulo_numero for a in r.artigos} == {"II"}
    assert len(r.artigos) == 4


def test_nunca_mistura_capitulos_e_ordena_por_artigo():
    indice, q = _indice_pequeno([("I", 0.5), ("II", 0.9), ("I", 0.6), ("II", 0.8), ("II", 0.7), ("I", 0.4)])
    r = indice.mais_similares(q)
    assert len({a.capitulo_numero for a in r.artigos}) == 1
    nums = [int(a.artigo.split()[1]) for a in r.artigos]
    assert nums == sorted(nums)


def test_melhor_score_e_do_capitulo_vencedor():
    indice, q = _indice_pequeno([("I", 0.95)] + [("II", 0.7)] * 4)
    r = indice.mais_similares(q)
    assert r.capitulo_numero == "II"
    assert r.melhor_score == pytest.approx(0.7, abs=1e-5)  # não 0,95 do outro capítulo


def test_caso_do_reviewer_um_a_080_contra_quatro_a_064():
    """Comportamento real: a soma decide. IV (0,85) perde para III (4 x 0,70 = 2,80);
    devolve só o capítulo III com melhor_score 0,70 (>= LIMIAR, logo `ok`)."""
    indice, q = _indice_pequeno([("IV", 0.85)] + [("III", 0.70)] * 4)
    r = indice.mais_similares(q)
    assert r.capitulo_numero == "III"
    assert len(r.artigos) == 4
    assert r.melhor_score == pytest.approx(0.70, abs=1e-5)
    assert r.melhor_score >= reg.LIMIAR


def test_top_k_limita_a_cinco():
    indice, q = _indice_pequeno([("I", 0.9)] * 8)
    assert len(indice.mais_similares(q).artigos) == reg.TOP_K


# ---------------------------------------------------------------- consultar_regulamento
async def test_consultar_ok_devolve_capitulo_e_texto_identico_ao_chunk(embedar):
    r = await reg.consultar_regulamento("Qual o horário da piscina?")
    assert r["status"] == "ok"
    assert r["capitulo"] == "Capítulo IV: Piscina"
    por = {a.artigo: a.texto for a in ARTIGOS}
    assert r["artigos"] and len(r["artigos"]) <= reg.TOP_K
    for item in r["artigos"]:
        assert item["texto"] == por[item["artigo"]]


async def test_consultar_sem_resultado_lista_14_titulos_e_nenhum_artigo(embedar):
    embedar["consulta"] = _eixo(700)  # ortogonal a tudo: score 0
    r = await reg.consultar_regulamento("Qual a capital da França?")
    assert r["status"] == "sem_resultado"
    assert set(r) == {"status", "capitulos"}
    assert len(r["capitulos"]) == 14
    assert "Capítulo IV: Piscina" in r["capitulos"]
    assert not any("**Art." in c for c in r["capitulos"])


async def test_consultar_limiar_na_fronteira(embedar):
    # cosseno exatamente abaixo do limiar -> sem_resultado; acima -> ok.
    eixo = CAPITULOS.index("IV")
    for s, esperado in ((reg.LIMIAR - 0.01, "sem_resultado"), (reg.LIMIAR + 0.01, "ok")):
        IndiceRegulamento._instancia = None
        embedar["consulta"] = _eixo(eixo, s) + _eixo(701, float(np.sqrt(1 - s * s)))
        assert (await reg.consultar_regulamento("x"))["status"] == esperado


@pytest.mark.parametrize(
    "delta,esperado", [(-0.005, "sem_resultado"), (-0.0005, "sem_resultado"), (0.0005, "ok"), (0.005, "ok")]
)
async def test_consultar_borda_fina_do_limiar_066(embedar, delta, esperado):
    s = 0.66 + delta
    embedar["consulta"] = _eixo(CAPITULOS.index("IV"), s) + _eixo(701, float(np.sqrt(1 - s * s)))
    assert (await reg.consultar_regulamento("x"))["status"] == esperado


@pytest.mark.parametrize("pergunta", ["", "   ", None])
async def test_pergunta_vazia_levanta_value_error(embedar, pergunta):
    with pytest.raises(ValueError):
        await reg.consultar_regulamento(pergunta)
    assert embedar["docs"] == 0 and embedar["consultas"] == 0


# ---------------------------------------------------------------- cache
def _ler_cache():
    with open(reg.CAMINHO_INDICE, encoding="utf-8") as f:
        return json.load(f)


async def _novo_processo():
    IndiceRegulamento._instancia = None
    return await IndiceRegulamento.carregar()


async def test_primeira_carga_embeda_documentos_e_grava_cache(embedar):
    indice = await IndiceRegulamento.carregar()
    assert embedar["docs"] == 1 and len(indice.artigos) == 96
    cache = _ler_cache()
    assert cache["sha256"] == reg._sha256(reg.CAMINHO_REGULAMENTO)
    assert cache["modelo"] == env.MODELO_EMBEDDINGS
    assert cache["dimensoes"] == reg.DIMENSOES
    assert len(cache["vetores"]) == 96 and len(cache["vetores"][0]) == reg.DIMENSOES


async def test_segunda_carga_em_novo_processo_le_o_cache_sem_embedar(embedar):
    await IndiceRegulamento.carregar()
    antes = embedar["docs"]
    indice = await _novo_processo()
    assert embedar["docs"] == antes
    assert indice.matriz.shape == (96, reg.DIMENSOES)


async def test_instancia_em_memoria_e_reaproveitada(embedar):
    a = await IndiceRegulamento.carregar()
    b = await IndiceRegulamento.carregar()
    assert a is b and embedar["docs"] == 1


async def test_muda_sha256_reconstroi(embedar, monkeypatch):
    await IndiceRegulamento.carregar()
    monkeypatch.setattr(reg, "_sha256", lambda _: "outro")
    await _novo_processo()
    assert embedar["docs"] == 2
    assert _ler_cache()["sha256"] == "outro"


async def test_muda_modelo_reconstroi(embedar, monkeypatch):
    await IndiceRegulamento.carregar()
    monkeypatch.setattr(env, "MODELO_EMBEDDINGS", "outro-modelo")
    await _novo_processo()
    assert embedar["docs"] == 2 and _ler_cache()["modelo"] == "outro-modelo"


async def test_cache_grava_a_sobreposicao(embedar):
    await IndiceRegulamento.carregar()
    assert _ler_cache()["sobreposicao"] == reg.SOBREPOSICAO


async def test_muda_sobreposicao_no_codigo_reconstroi(embedar, monkeypatch):
    await IndiceRegulamento.carregar()
    monkeypatch.setattr(reg, "SOBREPOSICAO", 250)
    await _novo_processo()
    assert embedar["docs"] == 2 and _ler_cache()["sobreposicao"] == 250


async def test_muda_sobreposicao_no_cache_reconstroi(embedar):
    await IndiceRegulamento.carregar()
    cache = _ler_cache()
    cache["sobreposicao"] = 250
    with open(reg.CAMINHO_INDICE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    await _novo_processo()
    assert embedar["docs"] == 2 and _ler_cache()["sobreposicao"] == reg.SOBREPOSICAO


async def test_cache_sem_campo_sobreposicao_reconstroi(embedar):
    await IndiceRegulamento.carregar()
    cache = _ler_cache()
    del cache["sobreposicao"]
    with open(reg.CAMINHO_INDICE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    await _novo_processo()
    assert embedar["docs"] == 2


async def test_muda_dimensoes_reconstroi(embedar, monkeypatch):
    await IndiceRegulamento.carregar()
    cache = _ler_cache()
    cache["dimensoes"] = 3072
    with open(reg.CAMINHO_INDICE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    await _novo_processo()
    assert embedar["docs"] == 2 and _ler_cache()["dimensoes"] == reg.DIMENSOES


async def test_muda_quantidade_reconstroi(embedar):
    await IndiceRegulamento.carregar()
    cache = _ler_cache()
    cache["vetores"] = cache["vetores"][:95]
    with open(reg.CAMINHO_INDICE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    indice = await _novo_processo()
    assert embedar["docs"] == 2 and indice.matriz.shape[0] == 96


@pytest.mark.parametrize(
    "conteudo",
    [
        "{corrompido",
        "[]",
        "{}",
        "null",
        json.dumps({"sha256": "x", "vetores": [[1.0, 2.0], [1.0]]}),  # vetores irregulares
        json.dumps({"vetores": "texto"}),
    ],
)
async def test_cache_invalido_reconstroi_sem_erro(embedar, conteudo):
    os.makedirs(os.path.dirname(reg.CAMINHO_INDICE))
    with open(reg.CAMINHO_INDICE, "w", encoding="utf-8") as f:
        f.write(conteudo)
    indice = await IndiceRegulamento.carregar()
    assert embedar["docs"] == 1 and len(indice.artigos) == 96
    assert len(_ler_cache()["vetores"]) == 96  # cache sobrescrito com o válido


async def test_escrita_atomica_sem_tmp_sobrando(embedar):
    await IndiceRegulamento.carregar()
    sobras = [n for n in os.listdir(os.path.dirname(reg.CAMINHO_INDICE)) if n.endswith(".tmp")]
    assert sobras == []
    assert os.listdir(os.path.dirname(reg.CAMINHO_INDICE)) == ["regulamento.index.json"]


async def test_nao_toca_o_indice_real(embedar):
    assert ".adk" not in reg.CAMINHO_INDICE
    await IndiceRegulamento.carregar()


# ---------------------------------------------------------------- concorrência
async def test_cinco_cargas_simultaneas_constroem_uma_vez(embedar):
    indices = await asyncio.gather(*(IndiceRegulamento.carregar() for _ in range(5)))
    assert embedar["docs"] == 1
    assert all(i is indices[0] for i in indices)


# ---------------------------------------------------------------- formatação e sobreposição
def _primeiros_de_capitulo() -> set[int]:
    return {i for i, a in enumerate(ARTIGOS) if i == 0 or ARTIGOS[i - 1].capitulo_numero != a.capitulo_numero}


def test_sobreposicao_padrao_e_zero_e_limiar_066():
    assert reg.SOBREPOSICAO == 0 and reg.LIMIAR == 0.66


def test_formato_do_documento_modelo_2(modelo_2):
    a = ARTIGOS[21]
    assert reg._texto_do_chunk(ARTIGOS, 21) == f"title: {a.capitulo_titulo} | text: {a.texto}"


def test_formato_do_documento_modelo_001(modelo_001):
    a = ARTIGOS[21]
    assert reg._texto_do_chunk(ARTIGOS, 21) == f"{a.capitulo_titulo}\n{a.texto}"


def test_formato_da_pergunta_dos_dois_modelos(monkeypatch):
    monkeypatch.setattr(env, "MODELO_EMBEDDINGS", "gemini-embedding-2")
    assert reg._texto_da_pergunta("Posso fazer festa?") == "task: search result | query: Posso fazer festa?"
    monkeypatch.setattr(env, "MODELO_EMBEDDINGS", "gemini-embedding-001")
    assert reg._texto_da_pergunta("Posso fazer festa?") == "Posso fazer festa?"


@pytest.mark.parametrize(
    "modelo,esperado", [("gemini-embedding-2", True), ("gemini-embedding-001", False), ("outro", False)]
)
def test_modelo_v2(monkeypatch, modelo, esperado):
    monkeypatch.setattr(env, "MODELO_EMBEDDINGS", modelo)
    assert reg._modelo_v2() is esperado


def test_chunk_sobreposicao_zero_nao_tem_cauda(modelo_2):
    for i, a in enumerate(ARTIGOS):
        t = reg._texto_do_chunk(ARTIGOS, i, sobreposicao=0)
        assert "[...]" not in t and t.endswith(a.texto)
        assert t == f"title: {a.capitulo_titulo} | text: {a.texto}"


def test_chunk_sobreposicao_usa_o_padrao_do_modulo(modelo_2, monkeypatch):
    monkeypatch.setattr(reg, "SOBREPOSICAO", 0)
    assert reg._texto_do_chunk(ARTIGOS, 5) == reg._texto_do_chunk(ARTIGOS, 5, sobreposicao=0)


@pytest.mark.parametrize("modelo", ["gemini-embedding-2", "gemini-embedding-001"])
def test_chunk_sobreposicao_250_cauda_do_anterior_do_mesmo_capitulo(monkeypatch, modelo):
    monkeypatch.setattr(env, "MODELO_EMBEDDINGS", modelo)
    primeiros = _primeiros_de_capitulo()
    assert len(primeiros) == 14
    for i, a in enumerate(ARTIGOS):
        t = reg._texto_do_chunk(ARTIGOS, i, sobreposicao=250)
        assert t.endswith(a.texto)
        if i in primeiros:
            assert "[...]" not in t, a.artigo  # nunca no primeiro artigo do capítulo
            assert t == reg._texto_do_chunk(ARTIGOS, i, sobreposicao=0)
        else:
            cauda = reg._cauda(ARTIGOS[i - 1].texto, 250)
            assert f"[...] {cauda}\n{a.texto}" in t, a.artigo
            assert len(cauda) <= 250


def test_chunk_sobreposicao_nunca_traz_texto_de_outro_capitulo(modelo_2):
    for i in _primeiros_de_capitulo():
        if i == 0:
            continue
        anterior = " ".join(ARTIGOS[i - 1].texto.split())
        t = reg._texto_do_chunk(ARTIGOS, i, sobreposicao=10_000)
        assert "[...]" not in t
        assert anterior[-40:] not in t
    for i in range(1, len(ARTIGOS)):
        if i in _primeiros_de_capitulo():
            continue
        t = reg._texto_do_chunk(ARTIGOS, i, sobreposicao=250)
        assert "Art. " not in t.split("\n", 1)[0].split("[...]")[0]
        assert ARTIGOS[i - 1].capitulo_numero == ARTIGOS[i].capitulo_numero


def test_chunk_sobreposicao_nao_altera_o_texto_do_artigo(modelo_2):
    antes = [a.texto for a in ARTIGOS]
    for i in range(len(ARTIGOS)):
        reg._texto_do_chunk(ARTIGOS, i, sobreposicao=250)
    assert [a.texto for a in ARTIGOS] == antes


def test_cauda_corta_em_palavra():
    texto = " ".join(f"palavra{i}" for i in range(60))
    c = reg._cauda(texto, 50)
    assert len(c) <= 50 and texto.endswith(c)
    assert texto[-len(c) - 1] == " "  # começa em início de palavra
    assert all(p.startswith("palavra") for p in c.split())


def test_cauda_texto_curto_volta_inteiro():
    assert reg._cauda("texto curto", 250) == "texto curto"
    assert reg._cauda("x" * 250, 250) == "x" * 250


def test_cauda_normaliza_espacos_e_quebras():
    assert reg._cauda("a  b\n\n c\td", 250) == "a b c d"


# ---------------------------------------------------------------- _embedar
class _Emb:
    def __init__(self, values):
        self.values = values


class _Modelos:
    def __init__(self, roteiro):
        self.roteiro = list(roteiro)  # itens: exceção ou None (sucesso)
        self.chamadas: list[list[str]] = []
        self.configs: list = []
        self.simultaneas = 0
        self.pico = 0
        self.por_texto = False  # True: vetor depende do texto "t{i}" e há atrasos variados

    async def embed_content(self, *, model, contents, config):
        self.chamadas.append(list(contents))
        self.configs.append(config)
        self.simultaneas += 1
        self.pico = max(self.pico, self.simultaneas)
        try:
            if self.por_texto:
                for _ in range(hash(contents[0]) % 5 + 1):
                    await _SLEEP_REAL(0)
            item = self.roteiro.pop(0) if self.roteiro else None
            if item is not None:
                raise item
            if self.por_texto:
                return type("R", (), {"embeddings": [_Emb([float(int(t[1:]) + 1), 1.0, 0.0, 0.0]) for t in contents]})()
            return type("R", (), {"embeddings": [_Emb([3.0, 4.0] + [0.0] * 2) for _ in contents]})()
        finally:
            self.simultaneas -= 1


@pytest.fixture
def cliente(monkeypatch):
    def montar(roteiro=()):
        modelos = _Modelos(roteiro)
        fake = type("C", (), {"aio": type("A", (), {"models": modelos})()})()
        monkeypatch.setattr(reg.genai, "Client", lambda: fake)
        return modelos

    return montar


@pytest.fixture
def esperas(monkeypatch):
    registradas: list[float] = []

    async def registra(s):
        registradas.append(s)

    monkeypatch.setattr(reg.asyncio, "sleep", registra)
    return registradas


def _erro(codigo):
    return genai_errors.APIError(codigo, {"error": {"message": "x", "status": "S"}})


@pytest.fixture(params=["gemini-embedding-001", "gemini-embedding-2"])
def modelo_qualquer(request, monkeypatch):
    monkeypatch.setattr(env, "MODELO_EMBEDDINGS", request.param)
    return request.param


@pytest.fixture
def modelo_001(monkeypatch):
    monkeypatch.setattr(env, "MODELO_EMBEDDINGS", "gemini-embedding-001")


@pytest.fixture
def modelo_2(monkeypatch):
    monkeypatch.setattr(env, "MODELO_EMBEDDINGS", "gemini-embedding-2")


async def test_embedar_001_96_textos_em_3_lotes_de_32(cliente, modelo_001):
    modelos = cliente()
    m = await reg._embedar([f"t{i}" for i in range(96)], "RETRIEVAL_DOCUMENT")
    assert [len(c) for c in modelos.chamadas] == [32, 32, 32]
    assert m.shape[0] == 96
    assert all(c.task_type == "RETRIEVAL_DOCUMENT" for c in modelos.configs)
    assert all(c.output_dimensionality == reg.DIMENSOES for c in modelos.configs)


async def test_embedar_001_consulta_usa_task_type_de_query(cliente, modelo_001):
    modelos = cliente()
    await reg._embedar(["a"], "RETRIEVAL_QUERY")
    assert modelos.configs[0].task_type == "RETRIEVAL_QUERY"


async def test_embedar_2_96_chamadas_de_1_texto_sem_task_type(cliente, modelo_2):
    modelos = cliente()
    m = await reg._embedar([f"t{i}" for i in range(96)], "RETRIEVAL_DOCUMENT")
    assert len(modelos.chamadas) == 96 and all(len(c) == 1 for c in modelos.chamadas)
    assert all(c.task_type is None for c in modelos.configs)
    assert all(c.output_dimensionality == reg.DIMENSOES for c in modelos.configs)
    assert m.shape == (96, 4)


async def test_embedar_2_consulta_tambem_sem_task_type(cliente, modelo_2):
    modelos = cliente()
    await reg._embedar(["a"], "RETRIEVAL_QUERY")
    assert modelos.configs[0].task_type is None and len(modelos.chamadas) == 1


async def test_embedar_2_nunca_mais_de_8_simultaneas(cliente, modelo_2):
    modelos = cliente()
    modelos.por_texto = True
    await reg._embedar([f"t{i}" for i in range(96)], "RETRIEVAL_DOCUMENT")
    assert reg.CONCORRENCIA_V2 == 8
    assert 1 < modelos.pico <= reg.CONCORRENCIA_V2


async def test_embedar_2_preserva_a_ordem_dos_vetores(cliente, modelo_2):
    modelos = cliente()
    modelos.por_texto = True
    m = await reg._embedar([f"t{i}" for i in range(96)], "RETRIEVAL_DOCUMENT")
    esperado = np.array([[i + 1.0, 1.0, 0.0, 0.0] for i in range(96)], dtype=np.float32)
    esperado /= np.linalg.norm(esperado, axis=1, keepdims=True)
    assert np.allclose(m, esperado)


async def test_embedar_2_429_repete_so_a_chamada_que_falhou(cliente, esperas, modelo_2):
    modelos = cliente([_erro(429)])
    m = await reg._embedar(["a", "b", "c"], "RETRIEVAL_DOCUMENT")
    assert esperas == [reg.ESPERA_COTA_S] and len(modelos.chamadas) == 4 and m.shape[0] == 3


async def test_embedar_2_503_repete(cliente, esperas, modelo_2):
    modelos = cliente([_erro(503), _erro(503)])
    await reg._embedar(["a"], "RETRIEVAL_QUERY")
    assert esperas == [reg.ESPERA_5XX_S] * 2 and len(modelos.chamadas) == 3


async def test_embedar_2_esgotadas_as_tentativas_levanta(cliente, esperas, modelo_2):
    modelos = cliente([_erro(503)] * 5)
    with pytest.raises(genai_errors.APIError):
        await reg._embedar(["a"], "RETRIEVAL_QUERY")
    assert len(modelos.chamadas) == reg.TENTATIVAS


async def test_embedar_normaliza_os_vetores(cliente):
    cliente()
    m = await reg._embedar(["a", "b"], "RETRIEVAL_QUERY")
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0)
    assert m[0, 0] == pytest.approx(0.6)


async def test_embedar_429_espera_40s_e_repete(cliente, esperas, modelo_qualquer):
    modelos = cliente([_erro(429)])
    m = await reg._embedar(["a"], "RETRIEVAL_QUERY")
    assert esperas == [reg.ESPERA_COTA_S] and len(modelos.chamadas) == 2 and m.shape[0] == 1


async def test_embedar_503_espera_5s_e_repete(cliente, esperas, modelo_qualquer):
    modelos = cliente([_erro(503)])
    await reg._embedar(["a"], "RETRIEVAL_QUERY")
    assert esperas == [reg.ESPERA_5XX_S] and len(modelos.chamadas) == 2


async def test_embedar_400_nao_repete(cliente, esperas, modelo_qualquer):
    modelos = cliente([_erro(400)])
    with pytest.raises(genai_errors.APIError):
        await reg._embedar(["a"], "RETRIEVAL_QUERY")
    assert len(modelos.chamadas) == 1 and esperas == []


async def test_embedar_esgotadas_as_tentativas_levanta(cliente, esperas):
    modelos = cliente([_erro(503)] * 5)
    with pytest.raises(genai_errors.APIError):
        await reg._embedar(["a"], "RETRIEVAL_QUERY")
    assert len(modelos.chamadas) == reg.TENTATIVAS
    assert len(esperas) == reg.TENTATIVAS - 1


# ---------------------------------------------------------------- restaurar
def test_restaurar_nao_menciona_regulamento_nem_gemini_no_codigo():
    import ast
    import pathlib

    fonte = (pathlib.Path(env.RAIZ) / "db" / "restaurar.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    # Ignora a docstring ("offline, sem Gemini"): confere imports e identificadores.
    nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}
    modulos = {
        (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(arvore)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    tudo = " ".join(nomes | modulos).lower()
    assert "regulamento" not in tudo and "genai" not in tudo and "embed" not in tudo
    assert "regulamento" not in fonte.lower().replace("sem gemini", "")
