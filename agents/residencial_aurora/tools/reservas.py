"""Tools de reservas. Nenhuma recebe `apartamento`: ele vem da sessão (Garantia 2)."""

from google.adk.tools.tool_context import ToolContext
from sqlalchemy.exc import IntegrityError

from db import dados, repo


def apartamento_da_sessao(tool_context: ToolContext) -> str:
    """Gravado uma única vez em `POST /sessoes`; o modelo nunca o informa."""
    apartamento = tool_context.state.get("apartamento")
    if not apartamento:
        raise ValueError("sessão sem apartamento")
    return apartamento


def _validar(area: str, data: str) -> dados.Area:
    info = dados.area_por_id(area)
    if info is None:
        raise ValueError(
            f"Área desconhecida: {area}. Use salao-de-festas, churrasqueira ou quadra."
        )
    dados.validar_data(data)
    return info


async def listar_minhas_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento do morador.

    Returns:
        dict: `reservas`, lista de {codigo, area, data}, ordenada por data.
    """
    apartamento = apartamento_da_sessao(tool_context)
    reservas = await repo.listar_reservas_ativas(apartamento)
    return {"reservas": [{"codigo": r.codigo, "area": r.area, "data": r.data} for r in reservas]}


async def verificar_disponibilidade(area: str, data: str, tool_context: ToolContext) -> dict:
    """Diz se uma área comum está livre em uma data. Não informa quem a reservou.

    Args:
        area (str): id da área: salao-de-festas, churrasqueira ou quadra.
        data (str): data no formato AAAA-MM-DD.
    Returns:
        dict: {area, data, disponivel}.
    """
    apartamento_da_sessao(tool_context)
    _validar(area, data)
    ocupada = await repo.reserva_ativa_existe(area, data)
    return {"area": area, "data": data, "disponivel": not ocupada}


async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum para o apartamento do morador na data informada.

    Áreas com taxa pedem confirmação do morador antes de gravar; a quadra
    (taxa zero) é reservada direto.

    Args:
        area (str): id da área: salao-de-festas, churrasqueira ou quadra.
        data (str): data da reserva no formato AAAA-MM-DD.
    Returns:
        dict: status (aguardando_confirmacao, reservada, nao_confirmada,
        indisponivel ou error) e, quando reservada, o código e a taxa.
    """
    apartamento = apartamento_da_sessao(tool_context)
    taxa = _validar(area, data)["taxa"]

    # Evita uma pendência inútil: data ocupada não precisa de confirmação.
    if await repo.reserva_ativa_existe(area, data):
        return {"status": "indisponivel", "area": area, "data": data}

    # Garantia 1: cobrança só com confirmação pela rota de confirmações.
    if taxa > 0 and tool_context.tool_confirmation is None:
        tool_context.request_confirmation(
            hint=f"Reservar {area} em {data} gera cobrança de R$ {taxa:.2f}.",
            payload={"area": area, "data": data, "taxa": taxa},
        )
        return {"status": "aguardando_confirmacao"}

    if taxa > 0 and not tool_context.tool_confirmation.confirmed:
        return {"status": "nao_confirmada", "area": area, "data": data}

    # Garantia 5: quem decide a disputa é o índice único, não a checagem acima.
    try:
        reserva = await repo.criar_reserva(apartamento, area, data)
    except IntegrityError:
        return {"status": "indisponivel", "area": area, "data": data}
    return {"status": "reservada", "codigo": reserva.codigo, "area": area, "data": data, "taxa": taxa}


async def cancelar_reserva(codigo: str, tool_context: ToolContext) -> dict:
    """Cancela uma reserva ativa do apartamento do morador, pelo código.

    Args:
        codigo (str): código da reserva, como RSV-1377 (veja `listar_minhas_reservas`).
    Returns:
        dict: status `cancelada` ou `nao_encontrada`, com o código.
    """
    apartamento = apartamento_da_sessao(tool_context)
    reserva = await repo.cancelar_reserva(apartamento, codigo.strip().upper())
    if reserva is None:
        return {"status": "nao_encontrada", "codigo": codigo}
    return {"status": "cancelada", "codigo": reserva.codigo}
