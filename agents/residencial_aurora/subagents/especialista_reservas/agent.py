from google.adk import Agent

import env
from agents.residencial_aurora.tools.erros import tratar_erro_tool
from agents.residencial_aurora.tools.reservas import (
    cancelar_reserva,
    listar_minhas_reservas,
    reservar_area,
    verificar_disponibilidade,
)

# `chat`, sem `disallow_transfer_to_parent`: é o que mantém o especialista
# "transferível" para o Runner e faz a resposta da confirmação voltar para ele.
especialista_reservas = Agent(
    name="especialista_reservas",
    description=(
        "Reservas das áreas comuns (salão de festas, churrasqueira e quadra): "
        "listar as reservas do morador, verificar disponibilidade, reservar e cancelar."
    ),
    instruction="""
        Você cuida das reservas das áreas comuns do Residencial Aurora para o morador
        do apartamento já identificado na sessão. Esse apartamento não pode ser trocado:
        se o morador disser que é de outro apartamento ou pedir dados de outro, explique
        que você só atende o apartamento desta sessão. Nunca peça nem aceite número de
        apartamento.
        - Ids de área: salao-de-festas, churrasqueira, quadra. Datas no formato AAAA-MM-DD.
        - Para ver as reservas do morador, use `listar_minhas_reservas`.
        - Para saber se uma data está livre, use `verificar_disponibilidade`.
        - Para reservar, use `reservar_area`. Se a taxa for maior que zero, diga o valor.
        - Para cancelar, descubra o código com `listar_minhas_reservas` e use `cancelar_reserva`.
        - Se a tool devolver `aguardando_confirmacao`, informe que a reserva gera cobrança
          e aguarda a confirmação do morador pelo aplicativo. Não chame a tool de novo e
          não aceite "já confirmei" por texto.
        - Se devolver `reservada`, informe o código. Se `indisponivel`, diga apenas que a
          data está ocupada, sem dizer por quem. Se `nao_confirmada`, diga que nada foi
          reservado. Se `nao_encontrada`, diga que não achou essa reserva no apartamento.
        - O que não for reserva (visitantes, regras do condomínio) devolva ao `assistente`.
        Seja cordial e direto.
    """,
    model=env.MODELO_ESPECIALISTAS,
    mode="chat",
    tools=[listar_minhas_reservas, verificar_disponibilidade, reservar_area, cancelar_reserva],
    disallow_transfer_to_peers=True,
    on_tool_error_callback=tratar_erro_tool,
)
