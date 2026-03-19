import json
from pathlib import Path

import pandas as pd

BASE = Path('.')
DATA_DIR = BASE / 'data'
DOCS = BASE / 'docs'
DOCS.mkdir(exist_ok=True)

HISTORY_CSV = DATA_DIR / 'history.csv'
LATEST_JSON = DATA_DIR / 'latest.json'

if HISTORY_CSV.exists():
    df = pd.read_csv(HISTORY_CSV)
else:
    df = pd.DataFrame(columns=[
        'timestamp_utc','market_date','signal','score','btc_ret_1d','btc_vol_ratio',
        'strc_price','strc_discount_abs','strc_discount_pct','days_from_dividend','div_window','rationale'
    ])

latest = {}
if LATEST_JSON.exists():
    latest = json.loads(LATEST_JSON.read_text(encoding='utf-8'))
elif not df.empty:
    latest = df.iloc[-1].to_dict()

signal_counts = df['signal'].value_counts().to_dict() if not df.empty else {}
history_json = df.tail(180).to_dict(orient='records')

html = f"""<!doctype html>
<html lang='pt-BR'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>STRC BTC Scanner Dashboard</title>
  <script src='https://cdn.jsdelivr.net/npm/chart.js'></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background:#0b1220; color:#e5e7eb; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px; }}
    .sub {{ color:#9ca3af; margin-bottom: 24px; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:16px; }}
    .card {{ background:#111827; border:1px solid #1f2937; border-radius:16px; padding:18px; box-shadow:0 6px 24px rgba(0,0,0,.25); }}
    .kpi {{ font-size:30px; font-weight:700; margin-top:8px; }}
    .good {{ color:#34d399; }} .warn {{ color:#fbbf24; }} .bad {{ color:#f87171; }} .muted{{color:#9ca3af;}}
    table {{ width:100%; border-collapse: collapse; font-size:14px; }}
    th, td {{ border-bottom:1px solid #1f2937; padding:10px; text-align:left; }}
    canvas {{ background:#111827; border:1px solid #1f2937; border-radius:16px; padding:12px; }}
    .section {{ margin-top:24px; }}
  </style>
</head>
<body>
<div class='wrap'>
  <h1>Dashboard Executivo STRC/BTC</h1>
  <div class='sub'>Histórico operacional do scanner diário com atualização automática via GitHub Actions.</div>

  <div class='grid'>
    <div class='card'><div class='muted'>Sinal atual</div><div class='kpi'>{latest.get('signal','N/A')}</div></div>
    <div class='card'><div class='muted'>Score atual</div><div class='kpi'>{latest.get('score','N/A')}</div></div>
    <div class='card'><div class='muted'>BTC 1d</div><div class='kpi'>{('{:.2%}'.format(latest.get('btc_ret_1d',0))) if latest else 'N/A'}</div></div>
    <div class='card'><div class='muted'>BTC vol / 20d</div><div class='kpi'>{('{:.2f}x'.format(latest.get('btc_vol_ratio',0))) if latest else 'N/A'}</div></div>
    <div class='card'><div class='muted'>Preço STRC</div><div class='kpi'>${('{:.2f}'.format(latest.get('strc_price',0))) if latest else 'N/A'}</div></div>
    <div class='card'><div class='muted'>Desconto STRC</div><div class='kpi'>${('{:.2f}'.format(latest.get('strc_discount_abs',0))) if latest else 'N/A'}</div></div>
  </div>

  <div class='section grid'>
    <div class='card'><canvas id='scoreChart'></canvas></div>
    <div class='card'><canvas id='priceChart'></canvas></div>
  </div>
  <div class='section grid'>
    <div class='card'><canvas id='signalChart'></canvas></div>
    <div class='card'>
      <div class='muted'>Resumo executivo</div>
      <p><b>Última data de mercado:</b> {latest.get('market_date','N/A')}</p>
      <p><b>Janela do dividendo:</b> {latest.get('div_window','N/A')} ({latest.get('days_from_dividend','N/A')} dias)</p>
      <p><b>Racional:</b> {latest.get('rationale','N/A')}</p>
      <p><b>Regra central:</b> o scanner favorece dias em que o BTC cai com volume acima da média e o STRC negocia com desconto relevante, evitando os 5 pregões anteriores ao dividendo.</p>
    </div>
  </div>

  <div class='section card'>
    <div class='muted'>Últimos registros</div>
    <table>
      <thead><tr><th>Data</th><th>Sinal</th><th>Score</th><th>BTC 1d</th><th>BTC Vol Ratio</th><th>STRC</th><th>Desconto</th><th>Janela</th></tr></thead>
      <tbody id='historyTable'></tbody>
    </table>
  </div>
</div>
<script>
const rows = {json.dumps(history_json, ensure_ascii=False)};
const signalCounts = {json.dumps(signal_counts, ensure_ascii=False)};

const labels = rows.map(r => r.market_date);
const scores = rows.map(r => Number(r.score));
const strc = rows.map(r => Number(r.strc_price));
const discount = rows.map(r => Number(r.strc_discount_abs));

new Chart(document.getElementById('scoreChart'), {{
  type:'line',
  data:{{labels, datasets:[{{label:'Score', data:scores}}, {{label:'Desconto STRC', data:discount}}]}},
  options:{{plugins:{{legend:{{labels:{{color:'#e5e7eb'}}}}}}, scales:{{x:{{ticks:{{color:'#9ca3af'}}}}, y:{{ticks:{{color:'#9ca3af'}}}}}}}}
}});
new Chart(document.getElementById('priceChart'), {{
  type:'line',
  data:{{labels, datasets:[{{label:'Preço STRC', data:strc}}]}},
  options:{{plugins:{{legend:{{labels:{{color:'#e5e7eb'}}}}}}, scales:{{x:{{ticks:{{color:'#9ca3af'}}}}, y:{{ticks:{{color:'#9ca3af'}}}}}}}}
}});
new Chart(document.getElementById('signalChart'), {{
  type:'bar',
  data:{{labels:Object.keys(signalCounts), datasets:[{{label:'Qtde', data:Object.values(signalCounts)}}]}},
  options:{{plugins:{{legend:{{labels:{{color:'#e5e7eb'}}}}}}, scales:{{x:{{ticks:{{color:'#9ca3af'}}}}, y:{{ticks:{{color:'#9ca3af'}}}}}}}}
}});

const tbody = document.getElementById('historyTable');
rows.slice().reverse().slice(0, 20).forEach(r => {{
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${{r.market_date}}</td><td>${{r.signal}}</td><td>${{r.score}}</td><td>${{(Number(r.btc_ret_1d)*100).toFixed(2)}}%</td><td>${{Number(r.btc_vol_ratio).toFixed(2)}}x</td><td>${{Number(r.strc_price).toFixed(2)}}</td><td>${{Number(r.strc_discount_abs).toFixed(2)}}</td><td>${{r.div_window}}</td>`;
  tbody.appendChild(tr);
}});
</script>
</body>
</html>
"""

(DOCS / 'index.html').write_text(html, encoding='utf-8')
print('Dashboard gerado em docs/index.html')
