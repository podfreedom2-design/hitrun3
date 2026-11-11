import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hitrun3 import strategy as S, engine as EN
from hitrun3.config import Config


def test_lot_round():
    assert S.lot_round(40000, 33.0, 100) == 1200
    assert S.lot_round(1000, 33.0, 100) == 0
    assert S.lot_round(1000, 0, 100) == 0


def test_regime():
    assert S.regime(True, False) == "STOCKS"
    assert S.regime(False, True) == "GOLD"
    assert S.regime(False, False) == "CASH"
    assert S.regime(np.nan, False) == "HOLD"     # ไม่มีข้อมูล SET -> ถือของเดิม ไม่เดาเป็นหุ้น
    assert S.regime(None, True) == "HOLD"


def test_pick_top_positive_only():
    s = pd.Series({"A": 0.5, "B": -0.1, "C": 0.2, "D": np.nan, "E": 0.9})
    assert S.pick_top(s, 5) == ["E", "A", "C"]
    assert S.pick_top(s, 2) == ["E", "A"]


def test_above_ma():
    s = pd.Series(np.r_[np.ones(5), [2.0]])
    r = S.above_ma(s, 3)
    assert pd.isna(r.iloc[0]) and r.iloc[-1] == True  # noqa


def test_rebalance_costs_and_cash():
    cfg = Config(capital=100000, top_n=2)
    sig = {"regime": "STOCKS", "picks": ["A", "B"]}
    px = {"A": 10.0, "B": 50.0}
    tgt = EN.targets(cfg, sig, 100000, px)
    assert tgt == {"A": 4900, "B": 900}
    h, cash, tr = EN.rebalance(cfg, {}, 100000, px, tgt, "2024-01-31")
    assert cash >= 0 and len(tr) == 2
    h2, cash2, tr2 = EN.rebalance(cfg, h, cash, px, {}, "2024-02-29")
    assert h2 == {} and tr2[0]["side"] == "SELL" and tr2[0]["closed"]
    assert cash2 < 100000   # จ่ายค่าธรรมเนียมไปกลับ


def test_buy_in_rank_order():
    cfg = Config(capital=100000, top_n=2)
    sig = {"regime": "STOCKS", "picks": ["Z", "A"]}
    tgt = EN.targets(cfg, sig, 100000, {"Z": 10.0, "A": 10.0})
    assert list(tgt) == ["Z", "A"]
    _, _, tr = EN.rebalance(cfg, {}, 100000, {"Z": 10.0, "A": 10.0}, tgt, "2024-01-31")
    assert [t["sym"] for t in tr] == ["Z", "A"]


def test_hold_regime_no_targets():
    cfg = Config()
    assert EN.targets(cfg, {"regime": "HOLD", "picks": []}, 100000, {}) is None


def test_round_trip_win_rate():
    tr = [{"side": "BUY", "sym": "A", "shares": 200, "pnl": None},
          {"side": "SELL", "sym": "A", "shares": 100, "pnl": 50.0},      # ขายบางส่วน กำไร
          {"side": "SELL", "sym": "A", "shares": 100, "pnl": -80.0}]     # ปิดไม้ ขาดทุนรวม -30
    rt = EN.round_trips(tr)
    assert len(rt) == 1 and rt[0]["pnl"] == -30.0


def test_gold_valued_at_bid():
    cfg = Config(gold_source="THGOLD", gold_spread_thb=200)
    assert EN.holdings_value(cfg, {"GOLD": {"shares": 2.0}}, {"GOLD": 60000}) == 2 * 59800


def test_month_end_days():
    idx = pd.bdate_range("2024-01-01", "2024-03-15")
    me = S.month_end_days(idx)
    assert list(me.strftime("%Y-%m-%d")) == ["2024-01-31", "2024-02-29", "2024-03-15"]
    r = EN.rebalance_days(idx)          # 2024-03-15 ไม่ใช่วันทำการสุดท้ายของเดือน -> ไม่นับ
    assert pd.Timestamp("2024-03-15") not in r and pd.Timestamp("2024-02-29") in r
