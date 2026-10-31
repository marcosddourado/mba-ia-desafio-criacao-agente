"""Consulta ao regulamento por RAG (Garantia 4, decisão D6).

Um artigo é um chunk e nenhum chunk cruza capítulo. A busca devolve só os artigos
do capítulo vencedor, então um evento nunca carrega trecho de outro assunto.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass

import numpy as np
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

import env

logger = logging.getLogger(__name__)

CAMINHO_REGULAMENTO = f"{env.RAIZ}/dados/regulamento.md"
CAMINHO_INDICE = f"{env.RAIZ}/.adk/regulamento.index.json"

DIMENSOES = 768
LOTE = 32
TOP_K = 5
# Calibrado em F4.9 (Registro #15) com 28 perguntas do regulamento e 8 fora de assunto,
# no gemini-embedding-2: acertos >= 0.707, fora de assunto <= 0.612.
LIMIAR = 0.66
# Caracteres do fim do artigo anterior, do MESMO capítulo, somados ao texto que vira
# vetor (o `texto` devolvido ao modelo continua sendo só o artigo). Medido em F4.9:
# não melhorou o ranking (250 caracteres: folga +0.064 contra +0.055 no embedding-001,
# e +0.081 contra +0.095 no embedding-2; o artigo seguinte piorou), então fica em 0.
SOBREPOSICAO = 0
TENTATIVAS = 3
CONCORRENCIA_V2 = 8  # o gemini-embedding-2 aceita 1 texto por chamada
ESPERA_COTA_S = 40  # free tier: a janela de 1 minuto precisa virar
ESPERA_5XX_S = 5

CAPITULO_RE = re.compile(r"^## Capítulo ([IVXL]+): (.+)$")
# Os nove primeiros artigos têm ordinal ("Art. 9º"); os demais, ponto ("Art. 22.").
ARTIGO_RE = re.compile(r"^\*\*Art\. (\d+)(?:º|\.)\*\*")


@dataclass
class Artigo:
    capitulo_numero: str
    capitulo_titulo: str
    artigo: str
    texto: str


@dataclass
class Resultado:
    capitulo_numero: str
    capitulo_titulo: str
    artigos: list[Artigo]
    melhor_score: float


def carregar_artigos(caminho: str = CAMINHO_REGULAMENTO) -> list[Artigo]:
    """Um `Artigo` por `**Art. N.**`, até o próximo artigo ou o próximo capítulo."""
    artigos: list[Artigo] = []
    capitulo: tuple[str, str] | None = None
    atual: tuple[str, list[str]] | None = None  # (rótulo, linhas)

    def fechar() -> None:
        nonlocal atual
        if atual and capitulo:
            rotulo, linhas = atual
            artigos.append(Artigo(capitulo[0], capitulo[1], rotulo, "\n".join(linhas).strip()))
        atual = None

    with open(caminho, encoding="utf-8") as f:
        for linha in f.read().splitlines():
            if m := CAPITULO_RE.match(linha):
                fechar()
                capitulo = (m.group(1), m.group(2).strip())
            elif m := ARTIGO_RE.match(linha):
                fechar()
                atual = (f"Art. {m.group(1)}", [linha])
            elif atual is not None:
                atual[1].append(linha)
    fechar()
    return artigos


def _modelo_v2() -> bool:
    """O gemini-embedding-2 não tem `task_type`: a tarefa vai em prefixos no texto."""
    return env.MODELO_EMBEDDINGS.endswith("-2")


def _cauda(texto: str, n: int) -> str:
    texto = " ".join(texto.split())
    return texto[-n:].split(" ", 1)[-1] if len(texto) > n else texto


def _texto_do_chunk(artigos: list[Artigo], i: int, sobreposicao: int = SOBREPOSICAO) -> str:
    """Texto que vira vetor. O título do capítulo (e, se ligada, a cauda do artigo
    anterior do mesmo capítulo) entra só aqui; o `texto` devolvido ao modelo continua
    o artigo, sem cortes."""
    artigo = artigos[i]
    corpo = artigo.texto
    if sobreposicao and i and artigos[i - 1].capitulo_numero == artigo.capitulo_numero:
        corpo = f"[...] {_cauda(artigos[i - 1].texto, sobreposicao)}\n{corpo}"
    if _modelo_v2():
        return f"title: {artigo.capitulo_titulo} | text: {corpo}"
    return f"{artigo.capitulo_titulo}\n{corpo}"


def _texto_da_pergunta(pergunta: str) -> str:
    return f"task: search result | query: {pergunta}" if _modelo_v2() else pergunta


async def _embedar_chamada(client, textos: list[str], tarefa: str):
    """Uma chamada à API, repetindo 429 e 5xx."""
    config = {"output_dimensionality": DIMENSOES}
    if not _modelo_v2():
        config["task_type"] = tarefa
    for tentativa in range(TENTATIVAS):
        try:
            return await client.aio.models.embed_content(
                model=env.MODELO_EMBEDDINGS,
                contents=textos,
                config=types.EmbedContentConfig(**config),
            )
        except genai_errors.APIError as erro:
            # 429: free tier de 100 textos/min por modelo (cada texto conta; construir
            # o índice gasta 96). 5xx: instabilidade passageira do Gemini.
            if erro.code not in (429, 500, 502, 503, 504) or tentativa == TENTATIVAS - 1:
                raise
            espera = ESPERA_COTA_S if erro.code == 429 else ESPERA_5XX_S
            logger.warning("Embeddings %s; nova tentativa em %ds.", erro.code, espera)
            await asyncio.sleep(espera)


async def _embedar(textos: list[str], tarefa: str) -> np.ndarray:
    """Vetores normalizados (a normalização é obrigatória fora de 3072 dims).

    `textos` já vêm formatados por `_texto_do_chunk`/`_texto_da_pergunta`.
    """
    client = genai.Client()  # lê GOOGLE_API_KEY
    if _modelo_v2():
        # Uma lista de textos viraria UM vetor agregado: é um texto por chamada.
        limite = asyncio.Semaphore(CONCORRENCIA_V2)

        async def um(texto: str):
            async with limite:
                resposta = await _embedar_chamada(client, [texto], tarefa)
            return resposta.embeddings[0].values

        vetores = list(await asyncio.gather(*(um(t) for t in textos)))
    else:
        vetores = []
        for i in range(0, len(textos), LOTE):
            resposta = await _embedar_chamada(client, textos[i : i + LOTE], tarefa)
            vetores.extend(e.values for e in resposta.embeddings)
    matriz = np.array(vetores, dtype=np.float32)
    return matriz / np.linalg.norm(matriz, axis=1, keepdims=True)


def _sha256(caminho: str) -> str:
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}


def _lock() -> asyncio.Lock:
    """Um lock por event loop: o `Lock` do asyncio não atravessa loops."""
    return _locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())


class IndiceRegulamento:
    """Matriz n×768 em processo, persistida em `.adk/regulamento.index.json`."""

    _instancia: "IndiceRegulamento | None" = None

    def __init__(self, artigos: list[Artigo], matriz: np.ndarray):
        self.artigos = artigos
        self.matriz = matriz

    @classmethod
    async def carregar(cls) -> "IndiceRegulamento":
        if cls._instancia is not None:
            return cls._instancia
        async with _lock():  # duas consultas simultâneas não constroem duas vezes
            if cls._instancia is None:
                cls._instancia = await cls._carregar_ou_construir()
        return cls._instancia

    @classmethod
    async def _carregar_ou_construir(cls) -> "IndiceRegulamento":
        artigos = carregar_artigos()
        sha = _sha256(CAMINHO_REGULAMENTO)
        matriz = cls._ler_cache(sha, len(artigos))
        if matriz is None:
            logger.info("Construindo o índice do regulamento (%d artigos).", len(artigos))
            matriz = await _embedar(
                [_texto_do_chunk(artigos, i) for i in range(len(artigos))], "RETRIEVAL_DOCUMENT"
            )
            cls._gravar_cache(sha, artigos, matriz)
        return cls(artigos, matriz)

    @staticmethod
    def _ler_cache(sha: str, quantidade: int) -> np.ndarray | None:
        try:
            with open(CAMINHO_INDICE, encoding="utf-8") as f:
                cache = json.load(f)
            vetores = np.array(cache["vetores"], dtype=np.float32)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        valido = (
            cache.get("sha256") == sha
            and cache.get("modelo") == env.MODELO_EMBEDDINGS
            and cache.get("dimensoes") == DIMENSOES
            and cache.get("sobreposicao") == SOBREPOSICAO
            and vetores.shape == (quantidade, DIMENSOES)
        )
        return vetores if valido else None

    @staticmethod
    def _gravar_cache(sha: str, artigos: list[Artigo], matriz: np.ndarray) -> None:
        os.makedirs(os.path.dirname(CAMINHO_INDICE), exist_ok=True)
        cache = {
            "sha256": sha,
            "modelo": env.MODELO_EMBEDDINGS,
            "dimensoes": DIMENSOES,
            "sobreposicao": SOBREPOSICAO,
            "artigos": [asdict(a) for a in artigos],
            "vetores": matriz.tolist(),
        }
        temporario = f"{CAMINHO_INDICE}.{os.getpid()}.tmp"  # um por processo
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(temporario, CAMINHO_INDICE)

    def capitulos(self) -> list[str]:
        vistos: dict[str, str] = {}
        for a in self.artigos:
            vistos.setdefault(a.capitulo_numero, f"Capítulo {a.capitulo_numero}: {a.capitulo_titulo}")
        return list(vistos.values())

    def mais_similares(self, consulta: np.ndarray, k: int = TOP_K) -> Resultado:
        """Top-k por cosseno, filtrado ao capítulo de maior soma de similaridade."""
        scores = self.matriz @ consulta
        melhores = np.argsort(scores)[::-1][:k]
        soma: dict[str, float] = {}
        for i in melhores:
            numero = self.artigos[i].capitulo_numero
            soma[numero] = soma.get(numero, 0.0) + float(scores[i])
        vencedor = max(soma, key=soma.__getitem__)
        escolhidos = sorted(i for i in melhores if self.artigos[i].capitulo_numero == vencedor)
        artigos = [self.artigos[i] for i in escolhidos]
        # O limiar vale para o melhor artigo do capítulo escolhido, não para o geral.
        melhor = max(float(scores[i]) for i in escolhidos)
        return Resultado(vencedor, artigos[0].capitulo_titulo, artigos, melhor)


async def consultar_regulamento(pergunta: str) -> dict:
    """Busca no regulamento interno os artigos que respondem a uma pergunta.

    Args:
        pergunta (str): a dúvida do morador, em linguagem natural.
    Returns:
        dict: `status` "ok" com o `capitulo` e os `artigos` ({artigo, texto}), ou
        "sem_resultado" com a lista de `capitulos` quando nada responde à pergunta.
    """
    pergunta = (pergunta or "").strip()
    if not pergunta:
        raise ValueError("Informe a pergunta sobre o regulamento.")
    indice = await IndiceRegulamento.carregar()
    consulta = (await _embedar([_texto_da_pergunta(pergunta)], "RETRIEVAL_QUERY"))[0]
    resultado = indice.mais_similares(consulta)
    if resultado.melhor_score < LIMIAR:
        return {"status": "sem_resultado", "capitulos": indice.capitulos()}
    return {
        "status": "ok",
        "capitulo": f"Capítulo {resultado.capitulo_numero}: {resultado.capitulo_titulo}",
        "artigos": [{"artigo": a.artigo, "texto": a.texto} for a in resultado.artigos],
    }
