---
name: harness
description: Roda o harness de verificação de uma fase do plano do Residencial Aurora (simplificar → revisar → testar → conformidade → live) e consolida o relatório no Registro de execução. Use ao fechar qualquer fase, com /harness fase-N; o plano exige o harness no "Pronto quando" de toda fase.
---

# /harness fase-N

Executa, nesta ordem, os cinco agentes de `.claude/agents/` sobre os arquivos que a fase criou ou alterou, e fecha com uma entrada no Registro de execução de `docs/plano-de-execucao.md`.

## Passos

1. **Delimite a fase.** `fase-N` vem dos argumentos (default: a fase em andamento no plano). Liste os arquivos dela: a seção "Arquivos" da fase no plano mais `git status --short` e `git diff --name-only <último commit antes da fase>`. Ignore `dados/`, `uv.lock`, `.env*`.
2. **Pare qualquer API no ar** na porta 8000 que seja sua (preview ou uvicorn em segundo plano) antes de começar; o `harness-live` sobe a dele.
3. **Rode os agentes em sequência**, cada um com a tool `Agent` (`subagent_type` = nome abaixo) e um prompt curto: a fase, a lista de arquivos, e o que mudou desde a última rodada. **Nunca em paralelo**: o simplificador edita código, os testes precisam do código final, o live é o mais caro.
   1. `harness-simplificar`
   2. `harness-revisar`
   3. `harness-testes`
   4. `harness-conformidade`
   5. `harness-live`
   Se os agentes não aparecerem na lista de `subagent_type` desta sessão (foram criados há pouco), use `general-purpose` com o conteúdo do arquivo `.claude/agents/<nome>.md` como prompt, precedido da fase e dos arquivos.
4. **Trate os vereditos.** `FALHOU` em qualquer etapa: corrija o que foi apontado (ou decida e registre por que não), rode de novo **só aquele agente**, no máximo duas voltas; se persistir, registre e pare antes do live. `ATENÇÃO`: decida item a item e registre a decisão. Achados do revisor que viram correção de código exigem repetir `harness-testes`.
5. **Consolide no Registro.** Acrescente uma entrada numerada em "Registro de execução" com a tabela `agente → veredito → achados → ação tomada`, as linhas "Linha para o Registro" de cada agente e a evidência-chave do live. Só então marque o "Pronto quando" da fase e commite (`feat: fase N — ...` ou `test:`/`chore:` para o que o harness mudou).

## Lembretes

- `HARNESS_GEMINI=1` só quando a fase exigir testes e2e com o modelo; o live já usa o Gemini real.
- O 503 "high demand" do Gemini é transitório; os agentes repetem até 3 vezes. Se persistir por minutos, registre e tente mais tarde em vez de trocar o modelo sem decisão.
- Nenhum agente commita, toca em `dados/` ou imprime `.env`. Quem commita é a sessão principal, depois do Registro.
