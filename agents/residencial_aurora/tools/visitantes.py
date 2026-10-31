"""Tools de visitantes. Nenhuma recebe `apartamento`: ele vem da sessão (Garantia 2)."""

from google.adk.tools.tool_context import ToolContext
from sqlalchemy.exc import IntegrityError

from agents.residencial_aurora.tools.reservas import apartamento_da_sessao
from db import dados, repo


async def listar_meus_visitantes(tool_context: ToolContext) -> dict:
    """Lista os visitantes autorizados do apartamento do morador.

    Returns:
        dict: `visitantes`, lista de {nome, data}.
    """
    apartamento = apartamento_da_sessao(tool_context)
    visitantes = await repo.listar_visitantes(apartamento)
    return {"visitantes": [{"nome": v.nome, "data": v.data} for v in visitantes]}


async def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante do apartamento do morador em uma data.

    Sempre pede confirmação do morador antes de gravar.

    Args:
        nome (str): nome completo do visitante.
        data (str): data da visita no formato AAAA-MM-DD.
    Returns:
        dict: status (aguardando_confirmacao, autorizado, nao_autorizado,
        ja_autorizado ou error).
    """
    apartamento = apartamento_da_sessao(tool_context)
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do visitante.")
    dados.validar_data(data)

    # Garantia 1: nenhuma autorização é gravada sem confirmação pela API.
    if tool_context.tool_confirmation is None:
        tool_context.request_confirmation(
            hint=f"Autorizar a entrada de {nome} em {data}.",
            payload={"nome": nome, "data": data},
        )
        return {"status": "aguardando_confirmacao"}

    if not tool_context.tool_confirmation.confirmed:
        return {"status": "nao_autorizado", "nome": nome, "data": data}

    try:
        await repo.autorizar_visitante(apartamento, nome, data)
    except IntegrityError:
        return {"status": "ja_autorizado", "nome": nome, "data": data}
    return {"status": "autorizado", "nome": nome, "data": data}
