# STRC BTC Scanner v3

Projeto para rodar diariamente no GitHub Actions, enviar alerta ao Telegram e publicar um dashboard executivo no GitHub Pages.

## O que faz
- baixa BTC e STRC via Yahoo Finance
- calcula sinal diário: NO TRADE / OBSERVAR / COMPRA BOA / COMPRA EXCEPCIONAL
- salva histórico em `data/history.csv`
- gera `docs/index.html` com dashboard executivo
- envia a mensagem ao Telegram

## Secrets necessários
Em `Settings > Secrets and variables > Actions` crie:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Como publicar o site
1. Suba a pasta inteira para um repositório no GitHub.
2. Vá em `Settings > Pages`.
3. Em `Source`, escolha `Deploy from a branch`.
4. Selecione `main` e a pasta `/docs`.

## Rodar manualmente
- Abra `Actions`
- Selecione `Daily STRC BTC Scanner`
- Clique em `Run workflow`

## Ajustes úteis
- Atualize as datas em `DIVIDEND_DATES`
- Altere os thresholds no workflow ou via variables/secrets
