"""
XAUUSD (altin) icin RSI + hacim + ATR tabanli basit sinyal uretici.

ONEMLI: Bu bir yatirim tavsiyesi degildir. Egitim / arastirma amaclidir.
Veri kaynagi olarak yfinance ile GC=F (altin futures) kullanilir; XAUUSD spot
fiyatiyla neredeyse birebir hareket eder ama birebir ayni degildir. Forex/CFD
piyasalarinda "gercek" hacim yoktur; burada kullanilan hacim futures islem
hacmidir.

Strateji (kasitli olarak basit ve seffaf tutuldu):
  - RSI(14) asiri satim/alim bolgelerinden donusleri arar (30 / 70 esikleri)
  - EMA(50) trend filtresi olarak kullanilir (yon RSI sinyaliyle ayni olmali)
  - Hacim, 20 periyotluk ortalamanin uzerindeyse "teyitli" sayilir
  - SL/TP, ATR(14) bazli hesaplanir (volatiliteye gore otomatik olcekli)

Cikti: konsola yazdirir + signals_log.csv dosyasina ekler.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

TICKER = "GC=F"          # Altin futures (XAUUSD proxy)
INTERVAL = "1h"           # Mum periyodu
LOOKBACK_PERIOD = "60d"   # Indikatorler icin yeterli gecmis veri
RSI_LEN = 14
EMA_LEN = 50
VOL_MA_LEN = 20
ATR_LEN = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
VOLUME_CONFIRM_MULT = 1.2   # hacim, ortalamanin en az bu katinda olmali
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.0            # R:R yaklasik 1:2
LOG_FILE = "signals_log.csv"
LATEST_JSON_FILE = "docs/data/latest.json"


def fetch_data() -> pd.DataFrame:
    df = yf.download(
        TICKER,
        period=LOOKBACK_PERIOD,
        interval=INTERVAL,
        auto_adjust=True,
        progress=False,
    )
    if df.empty:
        raise RuntimeError(f"{TICKER} icin veri cekilemedi (yfinance bos donus).")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns=str.lower)
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Beklenen kolonlar eksik: {missing}")

    return df.dropna(subset=["open", "high", "low", "close"])


def rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def atr(df: pd.DataFrame, length: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = rsi(df["close"], RSI_LEN)
    df["ema_trend"] = df["close"].ewm(span=EMA_LEN, adjust=False).mean()
    df["vol_ma"] = df["volume"].rolling(VOL_MA_LEN).mean()
    df["atr"] = atr(df, ATR_LEN)
    return df


def generate_signal(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(last["close"])
    rsi_now, rsi_prev = float(last["rsi"]), float(prev["rsi"])
    ema_trend = float(last["ema_trend"])
    vol_now = float(last["volume"])
    vol_ma = float(last["vol_ma"]) if not np.isnan(last["vol_ma"]) else None
    atr_now = float(last["atr"]) if not np.isnan(last["atr"]) else None

    volume_confirmed = vol_ma is not None and vol_ma > 0 and vol_now >= vol_ma * VOLUME_CONFIRM_MULT

    crossed_up = rsi_prev < RSI_OVERSOLD <= rsi_now
    crossed_down = rsi_prev > RSI_OVERBOUGHT >= rsi_now

    action = "HOLD"
    reason_parts = []
    sl = tp = None

    if crossed_up and price > ema_trend and volume_confirmed:
        action = "BUY"
        reason_parts.append(f"RSI {RSI_OVERSOLD} ustune donus ({rsi_prev:.1f}->{rsi_now:.1f})")
        reason_parts.append("fiyat EMA50 uzerinde (yukselis trendi)")
        reason_parts.append(f"hacim teyidi ({vol_now:.0f} >= {vol_ma * VOLUME_CONFIRM_MULT:.0f})")
    elif crossed_down and price < ema_trend and volume_confirmed:
        action = "SELL"
        reason_parts.append(f"RSI {RSI_OVERBOUGHT} altina donus ({rsi_prev:.1f}->{rsi_now:.1f})")
        reason_parts.append("fiyat EMA50 altinda (dusus trendi)")
        reason_parts.append(f"hacim teyidi ({vol_now:.0f} >= {vol_ma * VOLUME_CONFIRM_MULT:.0f})")
    else:
        reason_parts.append("kosullar saglanmadi (RSI kesisimi / trend / hacim teyidi bir arada yok)")

    if action != "HOLD" and atr_now:
        if action == "BUY":
            sl = price - atr_now * ATR_SL_MULT
            tp = price + atr_now * ATR_TP_MULT
        else:
            sl = price + atr_now * ATR_SL_MULT
            tp = price - atr_now * ATR_TP_MULT

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candle_time": str(last.name),
        "price": round(price, 2),
        "rsi": round(rsi_now, 2),
        "volume": round(vol_now, 2),
        "volume_ma": round(vol_ma, 2) if vol_ma is not None else None,
        "atr": round(atr_now, 3) if atr_now is not None else None,
        "action": action,
        "sl": round(sl, 2) if sl is not None else None,
        "tp": round(tp, 2) if tp is not None else None,
        "reason": "; ".join(reason_parts),
    }


def append_log(signal: dict) -> None:
    row = pd.DataFrame([signal])
    try:
        existing = pd.read_csv(LOG_FILE)
        combined = pd.concat([existing, row], ignore_index=True)
    except FileNotFoundError:
        combined = row
    combined.to_csv(LOG_FILE, index=False)


def write_latest_json(signal: dict) -> None:
    import json
    import os

    os.makedirs(os.path.dirname(LATEST_JSON_FILE), exist_ok=True)
    with open(LATEST_JSON_FILE, "w", encoding="utf-8") as fh:
        json.dump(signal, fh, ensure_ascii=False, indent=2)


def main() -> int:
    try:
        raw = fetch_data()
    except Exception as exc:  # ag/veri hatasi durumunda Actions'i kirmizi yapip erken cik
        print(f"HATA: veri cekilemedi: {exc}", file=sys.stderr)
        return 1

    df = build_indicators(raw)
    if len(df) < max(EMA_LEN, VOL_MA_LEN, ATR_LEN) + 2:
        print("HATA: guvenilir sinyal icin yeterli mum yok.", file=sys.stderr)
        return 1

    signal = generate_signal(df)

    print("=== XAUUSD Sinyal ===")
    for key, value in signal.items():
        print(f"{key}: {value}")

    append_log(signal)
    write_latest_json(signal)

    summary_path = __import__("os").environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"### XAUUSD Sinyal ({signal['candle_time']})\n\n")
            fh.write(f"- **Aksiyon:** {signal['action']}\n")
            fh.write(f"- **Fiyat:** {signal['price']}\n")
            fh.write(f"- **RSI:** {signal['rsi']}\n")
            fh.write(f"- **SL / TP:** {signal['sl']} / {signal['tp']}\n")
            fh.write(f"- **Gerekce:** {signal['reason']}\n\n")
            fh.write("> Yatirim tavsiyesi degildir.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
