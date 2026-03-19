# STRC BTC Scanner v5

Projeto com scanner diário STRC/BTC, envio para Telegram e dashboard executivo em GitHub Pages.

## O que tem nesta versão

- scanner diário em Python
- score de 0 a 100
- semáforo executivo
- histórico em CSV e JSON
- dashboard premium em `docs/index.html`
- GitHub Actions para atualizar dados e publicar histórico

## Secrets necessários

No GitHub, crie em `Settings > Secrets and variables > Actions`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## GitHub Pages

Ative em `Settings > Pages` e selecione:

- Branch: `main`
- Folder: `/docs`

## Rodar manualmente

Em `Actions`, execute `Daily STRC BTC Scanner V5`.
