import logging
from typing import Any

from google.adk.tools import BaseTool, ToolContext

logger = logging.getLogger(__name__)


def tratar_erro_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    error: Exception,
) -> dict | None:
    """`on_tool_error_callback`: o erro vira resposta da tool em vez de derrubar o turno."""
    logger.error("Erro ao executar a ferramenta %s: %s", tool.name, error)
    if isinstance(error, ValueError):
        return {"status": "error", "message": str(error)}
    return {
        "status": "error",
        "message": "Ocorreu um erro inesperado ao processar sua solicitação.",
    }
