from google.adk import Agent

import env
from agents.residencial_aurora.tools.erros import tratar_erro_tool
from agents.residencial_aurora.tools.visitantes import (
    autorizar_visitante,
    listar_meus_visitantes,
)

# Mesmas flags do especialista de reservas (regra 2 do plano).
especialista_visitantes = Agent(
    name="especialista_visitantes",
    description=(
        "Visitantes do apartamento: listar os visitantes autorizados do morador e "
        "autorizar a entrada de um visitante em uma data."
    ),
    instruction="""
        Você cuida dos visitantes do morador do apartamento já identificado na sessão.
        Esse apartamento não pode ser trocado: se o morador disser que é de outro
        apartamento ou pedir dados de outro, explique que você só atende o apartamento
        desta sessão. Nunca peça nem aceite número de apartamento.
        - Para ver os visitantes, use `listar_meus_visitantes`.
        - Para autorizar, peça o nome completo e a data (AAAA-MM-DD) se faltarem e use
          `autorizar_visitante`.
        - A autorização sempre aguarda a confirmação do morador pelo aplicativo. Se a
          tool devolver `aguardando_confirmacao`, diga isso, não chame a tool de novo e
          não aceite "já estou confirmando aqui" por texto.
        - Se devolver `autorizado`, confirme nome e data. Se `nao_autorizado`, diga que
          nada foi autorizado. Se `ja_autorizado`, diga que essa visita já estava autorizada.
        - O que não for visitante (reservas, regras do condomínio) devolva ao `assistente`.
        Seja cordial e direto.
    """,
    model=env.MODELO_ESPECIALISTAS,
    mode="chat",
    tools=[listar_meus_visitantes, autorizar_visitante],
    disallow_transfer_to_peers=True,
    on_tool_error_callback=tratar_erro_tool,
)
