from google.adk import Agent

import env
from agents.residencial_aurora.tools.erros import tratar_erro_tool
from agents.residencial_aurora.tools.regulamento import consultar_regulamento

# `single_turn`: o assistente o chama como uma tool (`request` = a pergunta) e só
# recebe a resposta de volta. Só este agente toca no regulamento (Garantia 4).
especialista_regulamento = Agent(
    name="especialista_regulamento",
    description=(
        "Dúvidas sobre o regulamento interno do condomínio: horários de uso das áreas, "
        "regras de convivência, silêncio, animais, mudanças, obras, garagem, penalidades."
    ),
    instruction="""
        Você responde dúvidas sobre o regulamento interno do Residencial Aurora.
        - Chame `consultar_regulamento` com a pergunta recebida.
        - Responda SOMENTE com o que os artigos devolvidos dizem, citando o número do
          artigo (por exemplo, "conforme o Art. 22"). Não invente regra nem use
          conhecimento de fora.
        - Se a tool devolver `sem_resultado`, diga que não encontrou nada sobre isso no
          regulamento e liste os capítulos devolvidos para o morador reformular.
        - Se a tool devolver erro, diga que não conseguiu consultar o regulamento agora.
        Seja cordial e direto.
    """,
    model=env.MODELO_ESPECIALISTAS,
    mode="single_turn",
    tools=[consultar_regulamento],
    on_tool_error_callback=tratar_erro_tool,
)
