import os
import json
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import requests
import yfinance as yf

BTC_TICKER = os.getenv('BTC_TICKER', 'BTC-USD')
STRC_TICKER = os.getenv('STRC_TICKER', 'STRC')
START_DATE = os.getenv('START_DATE', '2025-07-25')
STRC_PAR = float(os.getenv('STRC_PAR', '100'))
BTC_VOL_LOOKBACK = int(os.getenv('BTC_VOL_LOOKBACK', '20'))

BTC_DROP_OBSERVAR = float(os.getenv('BTC_DROP_OBSERVAR', '-0.015'))
BTC_DROP_COMPRA = float(os.getenv('BTC_DROP_COMPRA', '-0.02'))
BTC_VOL_RATIO_OBSERVAR = float(os.getenv('BTC_VOL_RATIO_OBSERVAR', '1.0'))
BTC_VOL_RATIO_COMPRA = float(os.getenv('BTC_VOL_RATIO_COMPRA', '1.2'))
STRC_DISC_OBSERVAR = float(os.getenv('STRC_DISC_OBSERVAR', '1.0'))
STRC_DISC_COMPRA = float(os.getenv('STRC_DISC_COMPRA', '1.5'))
STRC_DISC_EXCEPCIONAL = float(os.getenv('STRC_DISC_EXCEPCIONAL', '2.0'))

DIVIDEND_DATES = [d.strip() for d in os.getenv('DIVIDEND_DATES', '2025-08-15,2025-09-15,2025-10-15,2025-11-17,2025-12-15,2026-01-15,2026-02-17,2026-03-16').split(',') if d.strip()]

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, 'docs', 'data')
HISTORY_CSV = os.path.join(DATA_DIR, 'history.csv')
HISTORY_JSON = os.path.join(DATA_DIR, 'history.json')
LATEST_JSON = os.path.join(DATA_DIR, 'latest.json')


def download_ohlcv(ticker: str, start: str) -> pd.DataFrame:
    df = yf.download(ticker, start=start, auto_adjust=False, progress=False, threads=False)
    if df is None or df.empty:
        raise ValueError(f'Sem dados para {ticker}')
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    req = ['Open', 'High', 'Low', 'Close', 'Volume']
    df = df[req].copy()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def nearest_dividend_distance(index: pd.Index, div_dates):
    div_dates = pd.to_datetime(div_dates)
    idx = pd.Index(index)
    div_pos = []
    for d in div_dates:
        if d in idx:
            div_pos.append(idx.get_loc(d))
        else:
            pos = idx.searchsorted(d)
            if pos >= len(idx):
                pos = len(idx) - 1
            div_pos.append(pos)
    distances = []
    for current_pos, _ in enumerate(idx):
        vals = [current_pos - p for p in div_pos]
        distances.append(min(vals, key=lambda x: abs(x)))
    return pd.Series(distances, index=index)


def classify_div_window(days):
    if -5 <= days <= -1:
        return 'antes_5a1'
    if days == 0:
        return 'dia_0'
    if 1 <= days <= 3:
        return 'depois_1a3'
    if 1 <= days <= 5:
        return 'depois_1a5'
    return 'fora_janela'


def signal_label(row):
    before_div = -5 <= int(row['days_from_dividend']) <= -1
    if before_div:
        return 'NO TRADE', 10, ['Janela pré-dividendo']

    score = 0
    rationale = []
    if row['btc_ret_1d'] <= BTC_DROP_OBSERVAR:
        score += 20
        rationale.append('BTC em queda')
    if row['btc_ret_1d'] <= BTC_DROP_COMPRA:
        score += 15
        rationale.append('BTC em stress')
    if row['btc_vol_ratio'] >= BTC_VOL_RATIO_OBSERVAR:
        score += 15
        rationale.append('Volume acima da média')
    if row['btc_vol_ratio'] >= BTC_VOL_RATIO_COMPRA:
        score += 10
        rationale.append('Volume forte')
    if row['strc_discount_abs'] >= STRC_DISC_OBSERVAR:
        score += 15
        rationale.append('STRC descontado')
    if row['strc_discount_abs'] >= STRC_DISC_COMPRA:
        score += 10
        rationale.append('Desconto relevante')
    if row['strc_discount_abs'] >= STRC_DISC_EXCEPCIONAL:
        score += 15
        rationale.append('Desconto excepcional')

    score = int(min(score, 100))

    if row['btc_ret_1d'] <= BTC_DROP_COMPRA and row['btc_vol_ratio'] >= BTC_VOL_RATIO_COMPRA and row['strc_discount_abs'] >= STRC_DISC_EXCEPCIONAL:
        return 'COMPRA EXCEPCIONAL', max(score, 90), rationale
    if row['btc_ret_1d'] <= BTC_DROP_COMPRA and row['btc_vol_ratio'] >= BTC_VOL_RATIO_COMPRA and row['strc_discount_abs'] >= STRC_DISC_COMPRA:
        return 'COMPRA BOA', max(score, 75), rationale
    if row['btc_ret_1d'] <= BTC_DROP_OBSERVAR and row['btc_vol_ratio'] >= BTC_VOL_RATIO_OBSERVAR and row['strc_discount_abs'] >= STRC_DISC_OBSERVAR:
        return 'OBSERVAR', max(score, 55), rationale
    return 'NO TRADE', score, rationale or ['Setup incompleto']


def build_dataset():
    btc = download_ohlcv(BTC_TICKER, START_DATE)
    strc = download_ohlcv(STRC_TICKER, START_DATE)

    b = pd.DataFrame(index=btc.index)
    b['btc_close'] = btc['Close']
    b['btc_ret_1d'] = btc['Close'].pct_change()
    b['btc_volume'] = btc['Volume']
    b['btc_vol_ma20'] = btc['Volume'].rolling(BTC_VOL_LOOKBACK).mean()
    b['btc_vol_ratio'] = b['btc_volume'] / b['btc_vol_ma20']

    s = pd.DataFrame(index=strc.index)
    s['strc_close'] = strc['Close']
    s['strc_discount_abs'] = STRC_PAR - strc['Close']
    s['strc_discount_pct'] = (STRC_PAR / strc['Close']) - 1.0
    s['days_from_dividend'] = nearest_dividend_distance(s.index, DIVIDEND_DATES)
    s['div_window'] = s['days_from_dividend'].apply(classify_div_window)

    data = b.join(s, how='inner').dropna(subset=['btc_close', 'strc_close']).copy()
    signals, scores, rationales = [], [], []
    for _, row in data.iterrows():
        sig, score, why = signal_label(row)
        signals.append(sig)
        scores.append(score)
        rationales.append(' | '.join(why))

    data['signal'] = signals
    data['score'] = scores
    data['rationale'] = rationales
    data['distance_99_5'] = data['strc_close'] - 99.5
    data['distance_100'] = data['strc_close'] - 100.0
    data['updated_at_utc'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    return data.reset_index().rename(columns={'index': 'date'})


def persist_outputs(df: pd.DataFrame):
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(HISTORY_CSV):
        hist = pd.read_csv(HISTORY_CSV)
        hist['date'] = pd.to_datetime(hist['date'])
        df['date'] = pd.to_datetime(df['date'])
        merged = pd.concat([hist, df], ignore_index=True)
        merged = merged.sort_values('date').drop_duplicates(subset=['date'], keep='last')
    else:
        merged = df.copy()

    merged['date'] = pd.to_datetime(merged['date'])
    merged = merged.sort_values('date')

    latest = merged.iloc[-1].copy()
    score_ma7 = merged['score'].tail(7).mean() if len(merged) >= 1 else np.nan
    last7 = merged['signal'].tail(7).tolist()

    latest_payload = {
        'updated_at_utc': latest['updated_at_utc'],
        'date': latest['date'].strftime('%Y-%m-%d'),
        'signal': latest['signal'],
        'score': int(latest['score']),
        'score_ma7': round(float(score_ma7), 2) if pd.notna(score_ma7) else None,
        'btc_ret_1d': round(float(latest['btc_ret_1d']), 6),
        'btc_vol_ratio': round(float(latest['btc_vol_ratio']), 4),
        'strc_close': round(float(latest['strc_close']), 4),
        'strc_discount_abs': round(float(latest['strc_discount_abs']), 4),
        'strc_discount_pct': round(float(latest['strc_discount_pct']), 6),
        'div_window': str(latest['div_window']),
        'days_from_dividend': int(latest['days_from_dividend']),
        'distance_99_5': round(float(latest['distance_99_5']), 4),
        'distance_100': round(float(latest['distance_100']), 4),
        'rationale': str(latest['rationale']),
        'last7_signals': last7,
    }

    merged['date'] = merged['date'].dt.strftime('%Y-%m-%d')
    merged.to_csv(HISTORY_CSV, index=False)
    with open(HISTORY_JSON, 'w', encoding='utf-8') as f:
        json.dump(merged.to_dict(orient='records'), f, ensure_ascii=False, indent=2)
    with open(LATEST_JSON, 'w', encoding='utf-8') as f:
        json.dump(latest_payload, f, ensure_ascii=False, indent=2)
    return latest_payload


def send_telegram_message(payload):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print('Telegram não configurado.')
        return
    text = (
        f"<b>Scanner diário STRC/BTC</b>\n"
        f"<i>{payload['updated_at_utc']}</i>\n\n"
        f"<b>Sinal:</b> {payload['signal']}\n"
        f"<b>Data:</b> {payload['date']}\n"
        f"<b>Score:</b> {payload['score']}/100\n\n"
        f"<b>BTC</b>\n"
        f"• Retorno 1d: {payload['btc_ret_1d']:.2%}\n"
        f"• Vol/média 20d: {payload['btc_vol_ratio']:.2f}x\n\n"
        f"<b>STRC</b>\n"
        f"• Preço: ${payload['strc_close']:.2f}\n"
        f"• Desconto: ${payload['strc_discount_abs']:.2f}\n\n"
        f"<b>Dividendo</b>\n"
        f"• Janela: {payload['div_window']}\n"
        f"• Dias do próximo dividendo: {payload['days_from_dividend']}\n\n"
        f"<b>Leitura</b>\n• {payload['rationale'].replace(' | ', '\n• ')}"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }, timeout=30)
    resp.raise_for_status()


if __name__ == '__main__':
    dataset = build_dataset()
    latest = persist_outputs(dataset)
    print(json.dumps(latest, ensure_ascii=False, indent=2))
    send_telegram_message(latest)
