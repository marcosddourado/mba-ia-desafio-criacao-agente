"""Leitura dos JSON imutáveis de `dados/` (nunca escrevemos neles)."""

import json
import re
from datetime import datetime
from typing import TypedDict

import env


class Area(TypedDict):
    nome: str
    taxa: float


DATA_RE = r"^\d{4}-\d{2}-\d{2}$"


def ler_json(arquivo: str) -> list[dict]:
    with open(f"{env.RAIZ}/dados/{arquivo}", encoding="utf-8") as f:
        return json.load(f)


APARTAMENTOS: dict[str, str] = {a["numero"]: a["morador"] for a in ler_json("apartamentos.json")}
AREAS: dict[str, Area] = {
    a["id"]: {"nome": a["nome"], "taxa": float(a["taxa"])} for a in ler_json("areas.json")
}


def apartamento_existe(numero: str) -> bool:
    return numero in APARTAMENTOS


def area_por_id(area: str) -> Area | None:
    return AREAS.get(area)


def validar_data(data: str) -> str:
    """Aceita só AAAA-MM-DD de um dia que existe; o erro vira mensagem ao morador."""
    if not re.match(DATA_RE, data or ""):
        raise ValueError(f"Data inválida: use o formato AAAA-MM-DD (recebido: {data!r}).")
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Data inválida: {data} não existe no calendário.") from None
    return data
