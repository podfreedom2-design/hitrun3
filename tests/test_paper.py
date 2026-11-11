import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hitrun3 import paper as PP
from hitrun3.config import Config


def _panel(end):
    idx = pd.bdate_range("2023-01-02", end)
    n = len(idx)
    T = pd.DataFrame({s: np.linspace(10, 10 + k * 3, n) for k, s in enumerate("ABCDEF", 1)}, index=idx)
    mkt = pd.Series(np.linspace(100, 200, n), index=idx)
    gold = pd.Series(np.linspace(30000, 40000, n), index=idx)
    return T, mkt, gold


def _st(cfg):
    return {"created": None, "cash": float(cfg.capital), "holdings": {}, "trades": [], "history": [],
            "last_rebalance": None, "last_regime": None}


def test_mid_month_does_not_trade_and_month_end_books_once():
    cfg = Config(capital=100000, top_n=2, lookback_days=60, ma_days=50)
    T, m, g = _panel("2024-03-29")              # วันทำการสุดท้ายของ มี.ค.
    st, tr, info = PP.book_if_due(cfg, _st(cfg), T, m, g)
    assert info["status"] == "booked" and tr and st["last_rebalance"] == "2024-03-29"
    st2, tr2, info2 = PP.book_if_due(cfg, st, T, m, g)          # รันซ้ำ -> ไม่ลงซ้ำ
    assert info2["status"] == "already" and not tr2
    T, m, g = _panel("2024-04-15")              # กลางเดือน เม.ย.
    st3, tr3, info3 = PP.book_if_due(cfg, st2, T, m, g)
    assert info3["status"] == "already" and not tr3 and st3["last_rebalance"] == "2024-03-29"


def test_catch_up_uses_month_end_bar():
    cfg = Config(capital=100000, top_n=2, lookback_days=60, ma_days=50)
    T, m, g = _panel("2024-03-29")
    st, _, _ = PP.book_if_due(cfg, _st(cfg), T, m, g)
    T, m, g = _panel("2024-05-02")              # พลาดสิ้น เม.ย. -> ลงยอดย้อนหลังด้วยราคา 2024-04-30
    st, tr, info = PP.book_if_due(cfg, st, T, m, g)
    assert info["status"] == "booked" and st["last_rebalance"] == "2024-04-30"


def test_stale_set_holds():
    cfg = Config(capital=100000, top_n=2, lookback_days=60, ma_days=50)
    T, m, g = _panel("2024-03-29")
    sf = pd.Series(True, index=T.index); sf.iloc[-1] = False
    st, tr, info = PP.book_if_due(cfg, _st(cfg), T, m, g, set_fresh=sf)
    assert info["status"] == "hold_stale" and not tr and st["last_rebalance"] is None
