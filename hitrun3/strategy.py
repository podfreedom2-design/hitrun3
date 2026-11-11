"""กติกาล้วน (pure functions) — ทดสอบได้ด้วย pytest"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd


def moving_average(s: pd.Series, n: int, kind: str = "SMA") -> pd.Series:
    if kind.upper() == "EMA":
        return s.ewm(span=n, adjust=False, min_periods=n).mean()
    return s.rolling(n).mean()


def above_ma(s: pd.Series, n: int, kind: str = "SMA") -> pd.Series:
    """True/False/NaN (NaN = ยังไม่มีข้อมูลพอ)"""
    m = moving_average(s, n, kind)
    out = (s > m).astype(object)
    out[m.isna() | s.isna()] = np.nan
    return out


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def regime(set_up, gold_up) -> str:
    """STOCKS / GOLD / CASH / HOLD
    HOLD = ไม่มีข้อมูล SET หรือข้อมูลเก่า -> ห้ามเดาเป็นหุ้น ให้ถือของเดิมไว้และแจ้งเตือน (แก้ 2026-11-11)"""
    if _nan(set_up):
        return "HOLD"
    if bool(set_up):
        return "STOCKS"
    if not _nan(gold_up) and bool(gold_up):
        return "GOLD"
    return "CASH"


def momentum(close: pd.DataFrame, i: int, lookback: int) -> pd.Series:
    if i < lookback:
        return pd.Series(np.nan, index=close.columns)
    return close.iloc[i] / close.iloc[i - lookback] - 1


def pick_top(scores: pd.Series, n: int) -> list[str]:
    s = scores.dropna()
    s = s[s > 0]
    return list(s.sort_values(ascending=False).index[:n])


def lot_round(value: float, price: float, lot: int) -> int:
    if not price or price <= 0 or not np.isfinite(price) or value <= 0:
        return 0
    return int(math.floor(value / price / lot) * lot)


def month_end_days(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period("M")).max().values)
