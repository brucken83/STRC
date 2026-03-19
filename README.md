# STRC BTC Scanner v4

Projeto com scanner diário STRC/BTC, envio ao Telegram, histórico em CSV/JSON e dashboard executivo estático para GitHub Pages.

## Recursos
- Classificação: NO TRADE, OBSERVAR, COMPRA BOA, COMPRA EXCEPCIONAL
- Histórico salvo em `data/history.csv` e `docs/data/latest.json`
- Dashboard executivo em `docs/index.html`
- Atualização automática via GitHub Actions
- Envio para Telegram via Bot API

## Secrets no GitHub
Crie em `Settings > Secrets and variables > Actions`:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Publicar dashboard
1. Suba a pasta inteira para um repositório no GitHub.
2. Vá em `Settings > Pages`.
3. Selecione `Deploy from a branch`.
4. Escolha a branch `main` e a pasta `/docs`.

## Rodar manualmente
- Actions > `Daily STRC BTC Scanner v4` > `Run workflow`

## Ajustes
No workflow, ajuste as datas de dividendos em `DIVIDEND_DATES` quando necessário.
