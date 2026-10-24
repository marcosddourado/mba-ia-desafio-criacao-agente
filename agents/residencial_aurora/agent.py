"""Spike da Fase 0: um especialista `chat` com uma tool que pede confirmação.

Prova que, no ADK 2.2.0 com `SqliteSessionService`, a resposta da confirmação
enviada pela API volta ao especialista que a pediu e a tool reexecuta, inclusive
depois de parar e subir a API. A Fase 3 substitui este arquivo pela versão
completa (três especialistas, tools no banco); o que é exclusivo do spike está
marcado com "spike" e sai em F5.9.

Regras que o spike já respeita (docs/plano-de-execucao.md, "Regras que não se
negociam"): nenhuma tool aceita `apartamento`; especialista `chat` sem
`disallow_transfer_to_parent`; nenhum sub-agente `task`; sem `ResumabilityConfig`.
"""

import json
import os
from uuid import uuid4

from google.adk import Agent
from google.adk.apps import App
from google.adk.tools.tool_context import ToolContext

import env

# spike: as reservas ficam num JSON em .adk/ só para provar "gravado uma vez"
# sobrevivendo ao reinício. Na Fase 2 isso vira a tabela `reservas`.
ARQUIVO_RESERVAS = f"{env.RAIZ}/.adk/spike_reservas.json"

# spike: taxas fixas; na Fase 2 vêm de dados/areas.json via db/dados.py.
TAXAS = {"salao-de-festas": 150.0, "churrasqueira": 80.0, "quadra": 0.0}


def _ler_reservas() -> list[dict]:
    if not os.path.exists(ARQUIVO_RESERVAS):
        return []
    with open(ARQUIVO_RESERVAS, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def _gravar_reservas(reservas: list[dict]) -> None:
    # `adk web agents` carrega este módulo sem passar pelo `web.py`, que é quem cria `.adk/`.
    os.makedirs(os.path.dirname(ARQUIVO_RESERVAS), exist_ok=True)
    with open(ARQUIVO_RESERVAS, "w", encoding="utf-8") as arquivo:
        json.dump(reservas, arquivo, ensure_ascii=False, indent=2)


def _novo_codigo() -> str:
    return f"RSV-{uuid4().hex[:8].upper()}"


def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum para o apartamento do morador na data informada.

    Áreas com taxa pedem confirmação do morador antes de gravar; a quadra
    (taxa zero) é reservada direto.

    Args:
        area (str): id da área: salao-de-festas, churrasqueira ou quadra.
        data (str): data da reserva no formato AAAA-MM-DD.
    Returns:
        dict: status da operação (aguardando_confirmacao, reservada,
        nao_confirmada, indisponivel ou error) e, quando reservada, o código.
    """
    # Garantia 2: o apartamento vem da sessão, nunca do modelo.
    apartamento = tool_context.state.get("apartamento")
    if not apartamento:
        return {"status": "error", "message": "Sessão sem apartamento."}
    if area not in TAXAS:
        return {"status": "error", "message": f"Área desconhecida: {area}."}

    taxa = TAXAS[area]

    # Garantia 1: cobrança só com confirmação pela rota de confirmações.
    if taxa > 0 and tool_context.tool_confirmation is None:
        tool_context.request_confirmation(
            hint=f"Reservar {area} em {data} gera cobrança de R$ {taxa:.2f}.",
            payload={"area": area, "data": data, "taxa": taxa},
        )
        return {"status": "aguardando_confirmacao"}

    if taxa > 0 and not tool_context.tool_confirmation.confirmed:
        return {"status": "nao_confirmada", "area": area, "data": data}

    reservas = _ler_reservas()
    if any(reserva["area"] == area and reserva["data"] == data for reserva in reservas):
        return {"status": "indisponivel", "area": area, "data": data}

    reserva = {"codigo": _novo_codigo(), "apartamento": apartamento, "area": area, "data": data}
    _gravar_reservas(reservas + [reserva])
    return {"status": "reservada", "codigo": reserva["codigo"], "area": area, "data": data, "taxa": taxa}


especialista_reservas = Agent(
    name="especialista_reservas",
    description=(
        "Especialista em reservas das áreas comuns (salão de festas, churrasqueira e "
        "quadra): reserva uma área para o morador em uma data."
    ),
    instruction="""
        Você cuida das reservas das áreas comuns do Residencial Aurora para o morador
        do apartamento já identificado na sessão. Nunca peça nem aceite outro número
        de apartamento.
        - Ids de área: salao-de-festas, churrasqueira, quadra. Datas no formato AAAA-MM-DD.
        - Para reservar, chame `reservar_area` com a área e a data.
        - Se a tool devolver `aguardando_confirmacao`, informe que a reserva gera cobrança
          e aguarda a confirmação do morador pelo aplicativo. Não chame a tool de novo e
          não aceite confirmação por texto.
        - Se devolver `reservada`, informe o código. Se `indisponivel`, diga apenas que a
          data está ocupada. Se `nao_confirmada`, diga que nada foi reservado.
        Seja cordial e direto.
    """,
    model=env.MODELO_ESPECIALISTAS,
    mode="chat",
    tools=[reservar_area],
    disallow_transfer_to_peers=True,
)

root_agent = Agent(
    name="assistente",
    description="Assistente virtual do Residencial Aurora: encaminha o morador ao especialista certo.",
    instruction="""
        Você é o assistente virtual do Residencial Aurora.
        Cumprimente o morador e encaminhe pedidos de reserva ao especialista de reservas.
        Não invente reservas nem dados do condomínio.
        Seja cordial e direto.
    """,
    model=env.MODELO_PRINCIPAL,
    mode="chat",
    sub_agents=[especialista_reservas],
)

app = App(root_agent=root_agent, name="residencial_aurora")
