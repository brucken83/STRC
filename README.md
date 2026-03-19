# STRC BTC Scanner v5.1

Versão com correção de carregamento do dashboard no GitHub Pages.

## Correção principal

Os arquivos do dashboard ficam em:

- `docs/index.html`
- `docs/data/latest.json`
- `docs/data/history.json`
- `docs/data/history.csv`

O front-end usa caminhos relativos:

- `./data/latest.json`
- `./data/history.json`

Isso evita o erro `Unexpected token '<'` quando o GitHub Pages devolve HTML de 404.

## Publicação

1. Suba tudo no GitHub.
2. Ative **Settings > Pages**.
3. Escolha **Deploy from a branch**.
4. Branch `main`, pasta `/docs`.
5. Rode o workflow em **Actions**.

## Secrets

Crie em `Settings > Secrets and variables > Actions`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
