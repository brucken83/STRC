import os
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import yfinance as yf

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
DIVIDEND_DATES_RAW = os.getenv(
    "DIVIDEND_DATES",
    "2025-08-15,2025-09-15,2025-10-15,2025-11-17,2025-12-15,2026-01-15,2026-02-17,2026-03-16"
)
DIVIDEND_DATES = [d.strip() for d in DIVIDEND_DATES_RAW.split(",") if d.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DOCS_DATA_DIR = ROOT / "docs" / "data"
HISTORY_CSV = DATA_DIR / "history.csv"
LATEST_JSON = DOCS_DATA_DIR / "latest.json"
HISTORY_JSON = DOCS_DATA_DIR / "history.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_ohlcv(ticker: str, start: str) -> pd.DataFrame:
    df = yf.download(ticker, start=start, auto_adjust=False, progress=False, threads=False)
    if df is None or df.empty:
        raise ValueError(f"Sem dados para {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    required = ["Open", "High", "Low", "Close", "Volume"]
    df = df[required].copy()
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
    distances = []
    for current_pos, _ in enumerate(idx):
        vals = [current_pos - p for p in div_pos]
        distances.append(min(vals, key=lambda x: abs(x)))
    return pd.Series(distances, index=index)


def classify_div_window(days_from_dividend: int) -> str:
    if -5 <= days_from_dividend <= -1:
        return "antes_5a1"
    if days_from_dividend == 0:
        return "dia_0"
    if 1 <= days_from_dividend <= 3:
        return "depois_1a3"
    if 1 <= days_from_dividend <= 5:
        return "depois_1a5"
    return "fora_janela"


def compute_score(btc_ret, btc_vol_ratio, strc_discount, before_dividend_block):
    score = 0
    if btc_ret <= -0.015:
        score += 15
    if btc_ret <= -0.02:
        score += 20
    if btc_ret <= -0.03:
        score += 15
    if btc_vol_ratio >= 1.0:
        score += 10
    if btc_vol_ratio >= 1.2:
        score += 15
    if btc_vol_ratio >= 1.5:
        score += 10
    if strc_discount >= 1.0:
        score += 10
    if strc_discount >= 1.5:
        score += 15
    if strc_discount >= 2.0:
        score += 20
    if before_dividend_block:
        score -= 30
    return max(0, min(100, score))


def classify_signal(btc_ret, btc_vol_ratio, strc_discount, before_dividend_block):
    if before_dividend_block:
        if btc_ret <= BTC_DROP_COMPRA and btc_vol_ratio >= BTC_VOL_RATIO_COMPRA and strc_discount >= STRC_DISC_COMPRA:
            return "OBSERVAR"
        return "NO TRADE"
    if btc_ret <= BTC_DROP_COMPRA and btc_vol_ratio >= BTC_VOL_RATIO_COMPRA and strc_discount >= STRC_DISC_EXCEPCIONAL:
        return "COMPRA EXCEPCIONAL"
    if btc_ret <= BTC_DROP_COMPRA and btc_vol_ratio >= BTC_VOL_RATIO_COMPRA and strc_discount >= STRC_DISC_COMPRA:
        return "COMPRA BOA"
    if btc_ret <= BTC_DROP_OBSERVAR and btc_vol_ratio >= BTC_VOL_RATIO_OBSERVAR and strc_discount >= STRC_DISC_OBSERVAR:
        return "OBSERVAR"
    return "NO TRADE"


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id:
        print(text)
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()


def load_history() -> pd.DataFrame:
    if HISTORY_CSV.exists():
        try:
            return pd.read_csv(HISTORY_CSV)
        except Exception:
            pass
    return pd.DataFrame()


def save_outputs(record: dict):
    hist = load_history()
    new_row = pd.DataFrame([record])
    hist = pd.concat([hist, new_row], ignore_index=True)
    hist = hist.drop_duplicates(subset=["market_date"], keep="last")
    hist = hist.sort_values("market_date")
    hist.to_csv(HISTORY_CSV, index=False)

    latest_payload = record.copy()
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(latest_payload, f, ensure_ascii=False, indent=2)

    hist_tail = hist.tail(365).copy()
    hist_records = hist_tail.to_dict(orient="records")
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(hist_records, f, ensure_ascii=False, indent=2)


def main():
    btc = download_ohlcv(BTC_TICKER, START_DATE)
    strc = download_ohlcv(STRC_TICKER, START_DATE)

    btc_feat = pd.DataFrame(index=btc.index)
    btc_feat["btc_close"] = btc["Close"]
    btc_feat["btc_ret_1d"] = btc["Close"].pct_change()
    btc_feat["btc_volume"] = btc["Volume"]
    btc_feat["btc_vol_ma20"] = btc["Volume"].rolling(BTC_VOL_LOOKBACK).mean()
    btc_feat["btc_vol_ratio"] = btc_feat["btc_volume"] / btc_feat["btc_vol_ma20"]

    strc_feat = pd.DataFrame(index=strc.index)
    strc_feat["strc_close"] = strc["Close"]
    strc_feat["strc_discount_abs"] = STRC_PAR - strc["Close"]
    strc_feat["strc_discount_pct"] = (STRC_PAR / strc["Close"]) - 1.0
    strc_feat["days_from_dividend"] = nearest_dividend_distance(strc_feat.index, DIVIDEND_DATES)
    strc_feat["div_window"] = strc_feat["days_from_dividend"].apply(classify_div_window)

    data = btc_feat.join(strc_feat, how="inner").dropna(subset=["btc_close", "strc_close"])
    if data.empty:
        raise ValueError("Base casada vazia entre BTC e STRC")

    row = data.iloc[-1]
    btc_ret = float(row["btc_ret_1d"]) if pd.notna(row["btc_ret_1d"]) else float("nan")
    btc_vol_ratio = float(row["btc_vol_ratio"]) if pd.notna(row["btc_vol_ratio"]) else float("nan")
    strc_price = float(row["strc_close"])
    strc_discount = float(row["strc_discount_abs"])
    strc_discount_pct = float(row["strc_discount_pct"])
    div_window = str(row["div_window"])
    days_from_div = int(row["days_from_dividend"])
    before_dividend_block = -5 <= days_from_div <= -1

    signal = classify_signal(btc_ret, btc_vol_ratio, strc_discount, before_dividend_block)
    score = compute_score(btc_ret, btc_vol_ratio, strc_discount, before_dividend_block)

    market_date = data.index[-1].strftime("%Y-%m-%d")
    run_time_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    record = {
        "run_time_utc": run_time_utc,
        "market_date": market_date,
        "signal": signal,
        "score": score,
        "btc_close": round(float(row["btc_close"]), 4),
        "btc_ret_1d": round(btc_ret, 6),
        "btc_vol_ratio": round(btc_vol_ratio, 4),
        "strc_close": round(strc_price, 4),
        "strc_discount_abs": round(strc_discount, 4),
        "strc_discount_pct": round(strc_discount_pct, 6),
        "div_window": div_window,
        "days_from_dividend": days_from_div,
    }
    save_outputs(record)

    signal_emoji = {
        "NO TRADE": "⚪",
        "OBSERVAR": "🟡",
        "COMPRA BOA": "🟢",
        "COMPRA EXCEPCIONAL": "🚀",
    }.get(signal, "⚪")

    text = (
        f"<b>Scanner diário STRC/BTC</b>\n"
        f"<i>{run_time_utc}</i>\n\n"
        f"<b>Data de mercado:</b> {market_date}\n"
        f"<b>Sinal:</b> {signal_emoji} {signal}\n"
        f"<b>Score:</b> {score}/100\n\n"
        f"<b>BTC</b>\n"
        f"• Fechamento: ${row['btc_close']:.2f}\n"
        f"• Retorno 1d: {btc_ret:.2%}\n"
        f"• Volume / média 20d: {btc_vol_ratio:.2f}x\n\n"
        f"<b>STRC</b>\n"
        f"• Preço: ${strc_price:.2f}\n"
        f"• Desconto ao par: ${strc_discount:.2f}\n"
        f"• Desconto %: {strc_discount_pct:.2%}\n\n"
        f"<b>Dividendo</b>\n"
        f"• Janela: {div_window}\n"
        f"• Dias do dividendo mais próximo: {days_from_div}\n"
    )
    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, text)
    print(text)

if __name__ == "__main__":
    main()
