from google.adk import Agent
from google.adk.apps import App

import env
from agents.residencial_aurora.plugins import ModelRetryPlugin
from agents.residencial_aurora.subagents.especialista_regulamento.agent import especialista_regulamento
from agents.residencial_aurora.subagents.especialista_reservas.agent import especialista_reservas
from agents.residencial_aurora.subagents.especialista_visitantes.agent import especialista_visitantes

# Sem sub-agente `task` e sem `ResumabilityConfig` (Registro #4 do plano): a
# retomada da confirmação funciona pelo último autor transferível.
root_agent = Agent(
    name="assistente",
    description="Assistente virtual do Residencial Aurora: encaminha o morador ao especialista certo.",
    instruction="""
        Você é o assistente virtual do Residencial Aurora.
        Cumprimente o morador e encaminhe o pedido ao especialista pelo assunto: reservas
        de áreas comuns ao especialista de reservas e visitantes ao especialista de
        visitantes e dúvidas sobre as regras do condomínio (horários, silêncio, animais,
        mudanças, obras, penalidades...) ao especialista de regulamento. Se o pedido
        misturar assuntos, atenda um de cada vez.
        Não invente reservas, visitantes nem dados do condomínio, e não responda regras
        do condomínio por conta própria: repasse a pergunta ao especialista de
        regulamento e responda com o que ele devolver.
        Seja cordial e direto.
    """,
    model=env.MODELO_PRINCIPAL,
    mode="chat",
    sub_agents=[especialista_reservas, especialista_visitantes, especialista_regulamento],
)

app = App(root_agent=root_agent, name="residencial_aurora", plugins=[ModelRetryPlugin()])
