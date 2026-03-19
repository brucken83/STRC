import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
HISTORY_CSV = DATA_DIR / "history.csv"
HISTORY_JSON = DATA_DIR / "history.json"
LATEST_JSON = DATA_DIR / "latest.json"

BTC_TICKER = os.getenv("BTC_TICKER", "BTC-USD")
STRC_TICKER = os.getenv("STRC_TICKER", "STRC")
START_DATE = os.getenv("START_DATE", "2025-07-25")
STRC_PAR = float(os.getenv("STRC_PAR", "100"))
BTC_VOL_LOOKBACK = int(os.getenv("BTC_VOL_LOOKBACK", "20"))

BTC_DROP_OBSERVAR = float(os.getenv("BTC_DROP_OBSERVAR", "-0.015"))
BTC_DROP_COMPRA = float(os.getenv("BTC_DROP_COMPRA", "-0.02"))
BTC_VOL_RATIO_OBSERVAR = float(os.getenv("BTC_VOL_RATIO_OBSERVAR", "1.0"))
BTC_VOL_RATIO_COMPRA = float(os.getenv("BTC_VOL_RATIO_COMPRA", "1.2"))
STRC_DISC_OBSERVAR = float(os.getenv("STRC_DISC_OBSERVAR", "1.0"))
STRC_DISC_COMPRA = float(os.getenv("STRC_DISC_COMPRA", "1.5"))
STRC_DISC_EXCEPCIONAL = float(os.getenv("STRC_DISC_EXCEPCIONAL", "2.0"))
DIVIDEND_DATES = [d.strip() for d in os.getenv("DIVIDEND_DATES", "2025-08-15,2025-09-15,2025-10-15,2025-11-17,2025-12-15,2026-01-15,2026-02-17,2026-03-16").split(",") if d.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def download_ohlcv(ticker: str, start: str) -> pd.DataFrame:
    df = yf.download(ticker, start=start, auto_adjust=False, progress=False, threads=False)
    if df is None or df.empty:
        raise ValueError(f"Sem dados para {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    req = ["Open", "High", "Low", "Close", "Volume"]
    df = df[req].copy()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def nearest_dividend_distance(index: pd.Index, div_dates: list[str]) -> pd.Series:
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
    values = []
    for cur in range(len(idx)):
        vals = [cur - p for p in div_pos]
        values.append(min(vals, key=lambda x: abs(x)))
    return pd.Series(values, index=index)


def div_window_label(days: int) -> str:
    if -5 <= days <= -1:
        return "Antes do dividendo (1 a 5 pregões)"
    if days == 0:
        return "Dia do dividendo"
    if 1 <= days <= 3:
        return "1 a 3 dias após dividendo"
    if 4 <= days <= 5:
        return "4 a 5 dias após dividendo"
    return "Fora da janela"


def classify_signal(btc_ret, btc_vol_ratio, strc_discount, days_from_div):
    before_dividend_block = -5 <= int(days_from_div) <= -1
    rationale = []
    score = 0

    if btc_ret <= BTC_DROP_OBSERVAR:
        score += 20
        rationale.append("BTC caiu no dia")
    if btc_ret <= BTC_DROP_COMPRA:
        score += 10
        rationale.append("Queda do BTC acima do gatilho de compra")
    if btc_vol_ratio >= BTC_VOL_RATIO_OBSERVAR:
        score += 10
        rationale.append("Volume do BTC acima da média")
    if btc_vol_ratio >= BTC_VOL_RATIO_COMPRA:
        score += 10
        rationale.append("Volume do BTC em stress")
    if strc_discount >= STRC_DISC_OBSERVAR:
        score += 15
        rationale.append("STRC com desconto relevante")
    if strc_discount >= STRC_DISC_COMPRA:
        score += 15
        rationale.append("STRC com desconto forte")
    if strc_discount >= STRC_DISC_EXCEPCIONAL:
        score += 20
        rationale.append("STRC com desconto excepcional")
    if before_dividend_block:
        score -= 25
        rationale.append("Janela pré-dividendo reduz atratividade")
    elif int(days_from_div) >= 1:
        score += 5
        rationale.append("Fora do bloqueio pré-dividendo")

    if before_dividend_block:
        signal = "NO TRADE" if score < 60 else "OBSERVAR"
    elif btc_ret <= BTC_DROP_COMPRA and btc_vol_ratio >= BTC_VOL_RATIO_COMPRA and strc_discount >= STRC_DISC_EXCEPCIONAL:
        signal = "COMPRA EXCEPCIONAL"
    elif btc_ret <= BTC_DROP_COMPRA and btc_vol_ratio >= BTC_VOL_RATIO_COMPRA and strc_discount >= STRC_DISC_COMPRA:
        signal = "COMPRA BOA"
    elif btc_ret <= BTC_DROP_OBSERVAR and btc_vol_ratio >= BTC_VOL_RATIO_OBSERVAR and strc_discount >= STRC_DISC_OBSERVAR:
        signal = "OBSERVAR"
    else:
        signal = "NO TRADE"

    return signal, max(0, min(100, score)), rationale


def upsert_history(row: dict):
    fieldnames = list(row.keys())
    rows = []
    if HISTORY_CSV.exists():
        with open(HISTORY_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    rows = [r for r in rows if r.get("market_date") != row["market_date"]]
    rows.append({k: row[k] for k in fieldnames})
    rows = sorted(rows, key=lambda x: x["market_date"])
    with open(HISTORY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()


def main():
    btc = download_ohlcv(BTC_TICKER, START_DATE)
    strc = download_ohlcv(STRC_TICKER, START_DATE)

    btc_feat = pd.DataFrame(index=btc.index)
    btc_feat["btc_close"] = btc["Close"]
    btc_feat["btc_ret_1d"] = btc["Close"].pct_change()
    btc_feat["btc_vol_ma20"] = btc["Volume"].rolling(BTC_VOL_LOOKBACK).mean()
    btc_feat["btc_vol_ratio"] = btc["Volume"] / btc_feat["btc_vol_ma20"]

    strc_feat = pd.DataFrame(index=strc.index)
    strc_feat["strc_close"] = strc["Close"]
    strc_feat["strc_discount_abs"] = STRC_PAR - strc["Close"]
    strc_feat["strc_discount_pct"] = STRC_PAR / strc["Close"] - 1.0
    strc_feat["days_from_dividend"] = nearest_dividend_distance(strc.index, DIVIDEND_DATES)
    strc_feat["div_window"] = strc_feat["days_from_dividend"].apply(div_window_label)

    data = btc_feat.join(strc_feat, how="inner").dropna()
    row = data.iloc[-1]
    market_date = data.index[-1].strftime("%Y-%m-%d")
    signal, score, rationale = classify_signal(float(row.btc_ret_1d), float(row.btc_vol_ratio), float(row.strc_discount_abs), int(row.days_from_dividend))

    record = {
        "market_date": market_date,
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "signal": signal,
        "score": score,
        "btc_close": round(float(row.btc_close), 4),
        "btc_ret_1d": round(float(row.btc_ret_1d), 6),
        "btc_vol_ratio": round(float(row.btc_vol_ratio), 4),
        "strc_close": round(float(row.strc_close), 4),
        "strc_discount_abs": round(float(row.strc_discount_abs), 4),
        "strc_discount_pct": round(float(row.strc_discount_pct), 6),
        "days_from_dividend": int(row.days_from_dividend),
        "div_window": str(row.div_window),
        "rationale": " | ".join(rationale),
    }
    upsert_history(record)
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    emoji = {
        "NO TRADE": "⚪",
        "OBSERVAR": "🟠",
        "COMPRA BOA": "🟢",
        "COMPRA EXCEPCIONAL": "🚀",
    }.get(signal, "🔵")
    text = (
        f"<b>{emoji} Scanner diário STRC/BTC</b>\n"
        f"<i>{record['updated_at_utc']}</i>\n\n"
        f"<b>Sinal:</b> {signal}\n"
        f"<b>Score:</b> {score}/100\n"
        f"<b>Data:</b> {market_date}\n\n"
        f"<b>BTC</b>\n"
        f"• Retorno 1d: {record['btc_ret_1d']:.2%}\n"
        f"• Vol/média 20d: {record['btc_vol_ratio']:.2f}x\n\n"
        f"<b>STRC</b>\n"
        f"• Preço: ${record['strc_close']:.2f}\n"
        f"• Desconto ao par: ${record['strc_discount_abs']:.2f}\n"
        f"• Desconto %: {record['strc_discount_pct']:.2%}\n\n"
        f"<b>Dividendo</b>\n"
        f"• Janela: {record['div_window']}\n"
        f"• Dias do dividendo mais próximo: {record['days_from_dividend']}\n\n"
        f"<b>Leitura</b>\n• " + "\n• ".join(rationale)
    )
    send_telegram_message(text)


if __name__ == "__main__":
    main()
