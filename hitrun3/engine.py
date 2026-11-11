"""เครื่องจำลองรายเดือน — backtest และพอร์ตจำลองใช้ฟังก์ชันเดียวกัน (rebalance)
แก้ 2026-11-11: HOLD เมื่อข้อมูล SET ขาด/เก่า, มูลค่าทองคิดที่ราคารับซื้อ (bid), ซื้อตามอันดับโมเมนตัม,
win rate แบบ round trip, benchmark SET TR (ประมาณ), โหมด realistic (ราคาจริง/ล็อตจริง/ภาษีปันผล/ดอกเบี้ยเงินสด),
ไม่ถือแท่งสุดท้ายของเดือนที่ยังไม่จบเป็นวันปรับพอร์ต"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay
from . import strategy as S
from .config import Config

GOLD = "GOLD"


def is_last_trading_day(dt) -> bool:
    dt = pd.Timestamp(dt)
    return (dt + BDay(1)).month != dt.month


def signal_at(cfg: Config, T: pd.DataFrame, mkt: pd.Series, gold: pd.Series, i: int,
              set_up=None, gold_up=None, set_fresh=None, eligible=None) -> dict:
    """สัญญาณ ณ แท่งที่ i: regime, รายชื่อที่จะถือ (เรียงตามอันดับ), ตารางอันดับ
    set_fresh: Series bool — ถ้า SET ไม่มีข้อมูลจริง ณ แท่งนี้ (ขาด/เก่า) -> regime HOLD
    eligible: Series bool ต่อหุ้น (จักรวาล ณ วันนั้น เช่น จาก membership) — None = ทุกตัว"""
    if set_up is None:
        set_up = S.above_ma(mkt.iloc[: i + 1], cfg.ma_days, cfg.ma_type).iloc[-1]
    if gold_up is None:
        gold_up = S.above_ma(gold.iloc[: i + 1], cfg.ma_days, cfg.ma_type).iloc[-1]
    stale = set_fresh is not None and not bool(set_fresh.iloc[i])
    reg = S.regime(np.nan if stale else set_up, gold_up)
    scores = S.momentum(T, i, cfg.lookback_days)
    if eligible is not None:
        scores = scores.where(eligible.reindex(scores.index).fillna(False).astype(bool))
    picks = S.pick_top(scores, cfg.top_n) if reg == "STOCKS" else []
    if reg == "GOLD":
        picks = [GOLD]
    return {"date": T.index[i], "regime": reg, "picks": picks, "scores": scores,
            "set_up": set_up, "gold_up": gold_up, "set_stale": bool(stale)}


def thgold(cfg) -> bool:
    return str(getattr(cfg, "gold_source", "GLD")).upper() == "THGOLD"


def value_px(cfg: Config, sym: str, px: float) -> float:
    """ราคาที่ใช้คิดมูลค่าพอร์ต: ทองไทย = ราคารับซื้อ (ขายออก − ส่วนต่าง) เพราะถ้าขายจะได้ราคานี้"""
    if sym == GOLD and thgold(cfg) and px:
        return max(px - cfg.gold_spread_thb, 0.0)
    return px


def holdings_value(cfg: Config, holdings: dict, prices: dict, bid: bool = True) -> float:
    tot = 0.0
    for s, h in holdings.items():
        n = h["shares"] if isinstance(h, dict) else h
        p = prices.get(s, 0) or 0
        tot += n * (value_px(cfg, s, p) if bid else p)
    return tot


def fee_of(cfg: Config, sym: str, n: float, px: float, side: str) -> float:
    """ค่าใช้จ่ายต่อรายการ: หุ้นไทย % ต่อขา; ทองไทย = ส่วนต่างรับซื้อ-ขายออก (ตอนขาย) + ค่าธนาคาร (ตอนซื้อ)"""
    if sym != GOLD:
        return n * px * cfg.cost_thai
    if thgold(cfg):
        return n * cfg.gold_spread_thb if side == "SELL" else cfg.gold_fee_thb
    return n * px * cfg.cost_foreign


def gold_qty(cfg: Config, money: float, px: float) -> float:
    if not px or not np.isfinite(px) or money <= 0:
        return 0
    if thgold(cfg):
        step = cfg.gold_unit_step
        return round(np.floor(max(money - cfg.gold_fee_thb, 0) / px / step) * step, 6)
    return S.lot_round(money / (1 + cfg.cost_foreign), px, 1)


def _lot(cfg, sym, lots):
    return cfg.lot_size * (lots.get(sym, 1.0) if lots else 1.0)


def targets(cfg: Config, sig: dict, equity: float, prices: dict, lots: dict | None = None):
    """จำนวนหุ้นเป้าหมาย เรียงตามอันดับโมเมนตัม; หุ้นไทยปัดล็อต, ทองปัดตามหน่วยซื้อ
    regime HOLD -> None (ไม่ปรับ ถือของเดิม)"""
    if sig["regime"] == "HOLD":
        return None
    tgt = {}
    if sig["regime"] == "STOCKS":
        per = equity / cfg.top_n
        for s in sig["picks"]:
            px = prices.get(s, np.nan)
            lot = _lot(cfg, s, lots)
            if not px or not np.isfinite(px) or px <= 0:
                continue
            sh = np.floor(per / (1 + cfg.cost_thai) / px / lot) * lot
            sh = int(sh) if float(sh).is_integer() else round(float(sh), 6)
            if sh > 0:
                tgt[s] = sh
    elif sig["regime"] == "GOLD":
        sh = gold_qty(cfg, equity, prices.get(GOLD, np.nan))
        if sh > 0:
            tgt[GOLD] = sh
    return tgt


def rebalance(cfg: Config, holdings: dict, cash: float, prices: dict, tgt: dict, date,
              lots: dict | None = None, rank_order: bool = True) -> tuple:
    """ขายก่อนแล้วซื้อ ที่ราคาปิด คืน (holdings, cash, trades)
    holdings: {sym: {"shares": n, "cost": float}} cost = ต้นทุนรวมค่าธรรมเนียม
    rank_order=True: ซื้อตามลำดับใน tgt (อันดับโมเมนตัม) — False = เรียงตัวอักษรแบบเดิม"""
    holdings = {k: dict(v) for k, v in holdings.items()}
    trades = []
    d = str(pd.Timestamp(date).date())
    for sym in sorted(set(holdings) | set(tgt)):
        cur = holdings.get(sym, {}).get("shares", 0)
        want = tgt.get(sym, 0)
        if want < cur:
            px = prices[sym]
            n = round(cur - want, 6)
            fee = fee_of(cfg, sym, n, px, "SELL")
            proceeds = n * px - fee
            avg = holdings[sym]["cost"] / cur
            pnl = proceeds - avg * n
            cash += proceeds
            holdings[sym]["shares"] = want
            holdings[sym]["cost"] = avg * want
            if want <= 1e-9:
                del holdings[sym]
            trades.append({"date": d, "side": "SELL", "sym": sym, "shares": n,
                           "price": round(px, 4), "fee": round(fee, 2), "value": round(n * px, 2),
                           "pnl": round(pnl, 2), "pnl_pct": round(pnl / (avg * n), 4) if avg else 0.0,
                           "closed": bool(want <= 1e-9)})
    for sym in (list(tgt) if rank_order else sorted(tgt)):
        cur = holdings.get(sym, {}).get("shares", 0)
        want = tgt[sym]
        if want > cur:
            px = prices[sym]
            n = want - cur
            if sym == GOLD:
                n = min(n, gold_qty(cfg, cash, px)) if thgold(cfg) else n
                while not thgold(cfg) and n > 0 and n * px + fee_of(cfg, sym, n, px, "BUY") > cash + 1e-6:
                    n -= 1
            else:
                lot = _lot(cfg, sym, lots)
                while n > 0 and n * px * (1 + cfg.cost_thai) > cash + 1e-6:
                    n -= lot
            n = round(n, 6)
            if n <= 0:
                continue
            fee = fee_of(cfg, sym, n, px, "BUY")
            cash -= n * px + fee
            h = holdings.setdefault(sym, {"shares": 0, "cost": 0.0})
            h["shares"] = round(h["shares"] + n, 6)
            h["cost"] += n * px + fee
            trades.append({"date": d, "side": "BUY", "sym": sym, "shares": n,
                           "price": round(px, 4), "fee": round(fee, 2), "value": round(n * px, 2),
                           "pnl": None, "pnl_pct": None})
    return holdings, cash, trades


def prices_at(T, gold, i) -> dict:
    p = {k: float(v) for k, v in T.iloc[i].items() if np.isfinite(v) and v > 0}
    g = gold.iloc[i]
    if np.isfinite(g):
        p[GOLD] = float(g)
    return p


def rebalance_days(idx: pd.DatetimeIndex, include_partial: bool = False) -> set:
    """วันปรับพอร์ต = แท่งสุดท้ายของแต่ละเดือน; แท่งสุดท้ายของข้อมูลนับเฉพาะเมื่อเป็นวันทำการสุดท้ายของเดือนจริง"""
    r = set(S.month_end_days(idx))
    if not include_partial and len(idx) and not is_last_trading_day(idx[-1]):
        r.discard(idx[-1])
    return r


def backtest(cfg: Config, T, mkt, gold, start=None, end=None, mode: str = "original", R=None,
             exclude=None, lag: int = 0, set_fresh=None, member=None) -> dict:
    """mode:
      original  = ราคาปรับปันผล (ปันผลลงทุนต่อ ไม่หักภาษี), ล็อต 100 หน่วยราคาปรับ, เงินสดไม่มีดอกเบี้ย
      realistic = ซื้อขาย/มูลค่าที่ราคาจริง (R = D.load_unadj), ล็อต 100 หุ้นจริง, ปันผลเงินสดหักภาษี dividend_tax,
                  เงินสดได้ดอกเบี้ย cash_rate (สัญญาณยังใช้ราคาปรับปันผลเหมือนเดิม)
      legacy    = โค้ดเดิมก่อนแก้ (ทองคิดราคาขายออก, ซื้อเรียงตัวอักษร, นับแท่งกลางเดือนเป็นวันปรับพอร์ต)
    exclude: รายชื่อหุ้นที่ตัดออก (ทดสอบความทนทาน); lag: ซื้อขายช้ากว่าสัญญาณ N แท่ง
    member: DataFrame bool (วัน x หุ้น) จักรวาลย้อนหลัง"""
    legacy = mode == "legacy"
    real = mode == "realistic"
    set_up_all = S.above_ma(mkt, cfg.ma_days, cfg.ma_type)
    gold_up_all = S.above_ma(gold, cfg.ma_days, cfg.ma_type)
    idx = T.index
    first_ok = idx[min(cfg.lookback_days, len(idx) - 1)]
    s0 = max(pd.Timestamp(start), first_ok) if start else first_ok
    rdays = rebalance_days(idx, include_partial=legacy)
    Px, DIV, LOTF = T, None, None
    if real:
        if R is None:
            raise ValueError("realistic mode ต้องมีข้อมูลราคาไม่ปรับปันผล (data/unadj) — รัน fetch")
        CL, DIV, LOTF = R
        Px = CL.reindex(columns=T.columns).combine_first(T)   # ไม่มีราคาจริง -> ใช้ราคาปรับ
        DIV = DIV.reindex(columns=T.columns).fillna(0.0)
        LOTF = LOTF.reindex(columns=T.columns).fillna(1.0)
    tax = float(getattr(cfg, "dividend_tax", 0.10)) if real else 0.0
    rate = float(cfg.cash_rate) if real else 0.0
    excl = set(exclude or [])
    elig_all = pd.Series(True, index=T.columns)
    if excl:
        elig_all[list(excl & set(T.columns))] = False
    cash = float(cfg.capital)
    hold: dict = {}
    eq, trades, hist, regimes = [], [], [], []
    daily_cash = (1 + rate) ** (1 / 252)
    pend = {}
    divs_net = 0.0
    Pv = Px.values
    cols = list(Px.columns)
    for i, dt in enumerate(idx):
        if dt < s0 or (end and dt > pd.Timestamp(end)):
            continue
        if cash > 0:
            cash *= daily_cash
        if DIV is not None and hold:
            for s, h in hold.items():
                if s != GOLD:
                    dv = DIV.at[dt, s]
                    if dv > 0:
                        x = h["shares"] * dv * (1 - tax)
                        cash += x
                        divs_net += x
        row = Pv[i]
        px = {c: float(v) for c, v in zip(cols, row) if np.isfinite(v) and v > 0}
        g = gold.iloc[i]
        if np.isfinite(g):
            px[GOLD] = float(g)
        if dt in rdays:
            el = elig_all
            if member is not None:
                el = el & member.loc[dt].reindex(T.columns).fillna(False)
            sig = signal_at(cfg, T, mkt, gold, i, set_up_all.iloc[i], gold_up_all.iloc[i],
                            set_fresh=set_fresh, eligible=el if (excl or member is not None) else None)
            pend[i + lag] = sig
            regimes.append({"date": str(dt.date()), "regime": sig["regime"],
                            "set_above_ma": None if pd.isna(sig["set_up"]) else bool(sig["set_up"]),
                            "gold_above_ma": None if pd.isna(sig["gold_up"]) else bool(sig["gold_up"])})
        if i in pend:
            sig = pend.pop(i)
            e_now = cash + holdings_value(cfg, hold, px, bid=not legacy)
            lots = {s: float(LOTF.iat[i, LOTF.columns.get_loc(s)]) for s in sig["picks"] if s in LOTF.columns} if real else None
            tgt = targets(cfg, sig, e_now, px, lots)
            if tgt is not None:
                hold, cash, tr = rebalance(cfg, hold, cash, px, tgt, dt, lots=lots, rank_order=not legacy)
                trades += tr
            hist.append({"date": str(dt.date()), "regime": sig["regime"],
                         "holdings": {s: h["shares"] for s, h in hold.items()}})
        e = cash + holdings_value(cfg, hold, px, bid=not legacy)
        eq.append((dt, e, cash))
    E = pd.DataFrame(eq, columns=["date", "equity", "cash"]).set_index("date")
    return {"equity": E, "trades": trades, "holdings": hist, "regimes": regimes,
            "start": E.index[0], "end": E.index[-1], "mode": mode, "dividends_net": round(divs_net, 2),
            "open_positions": {s: h["shares"] for s, h in hold.items()}}


def round_trips(trades: list) -> list[dict]:
    """รวมการขายบางส่วน (ปรับน้ำหนัก) เข้ากับไม้เดียวกัน; ไม้ปิดเมื่อขายจนหมด"""
    pos, acc, start, out = {}, {}, {}, []
    for t in trades:
        s = t["sym"]
        if t["side"] == "BUY":
            if pos.get(s, 0) <= 1e-9:
                start[s], acc[s] = t.get("date"), 0.0
            pos[s] = pos.get(s, 0) + t["shares"]
        else:
            pos[s] = pos.get(s, 0) - t["shares"]
            acc[s] = acc.get(s, 0.0) + (t["pnl"] or 0.0)
            if pos[s] <= 1e-9:
                out.append({"sym": s, "open": start.get(s), "close": t.get("date"), "pnl": round(acc[s], 2)})
                pos[s], acc[s] = 0, 0.0
    return out


def metrics(eq: pd.Series, trades: list | None = None, capital: float | None = None) -> dict:
    eq = eq.dropna()
    yrs = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    r = eq.pct_change().dropna()
    out = {"start": str(eq.index[0].date()), "end": str(eq.index[-1].date()), "years": round(yrs, 2),
           "start_value": round(float(eq.iloc[0]), 2), "final_value": round(float(eq.iloc[-1]), 2),
           "total_return": round(float(eq.iloc[-1] / eq.iloc[0] - 1), 4),
           "cagr": round(float((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1), 4),
           "max_drawdown": round(float((eq / eq.cummax() - 1).min()), 4),
           "sharpe": round(float(r.mean() / r.std() * np.sqrt(252)), 2) if r.std() > 0 else 0.0}
    if trades is not None:
        sells = [t for t in trades if t["side"] == "SELL"]
        rt = round_trips(trades)
        rs = [x for x in rt if x["sym"] != GOLD]
        rg = [x for x in rt if x["sym"] == GOLD]
        wr = lambda xs: round(float(sum(x["pnl"] > 0 for x in xs) / len(xs)), 3) if xs else None
        out["n_trades"] = len(trades)
        out["n_closed"] = len(rt)                 # ไม้ที่ปิดจริง (ขายหมด)
        out["win_rate"] = wr(rt)                  # win rate แบบ round trip
        out["n_closed_stocks"], out["win_rate_stocks"] = len(rs), wr(rs)
        out["n_closed_gold"], out["win_rate_gold"] = len(rg), wr(rg)
        out["n_sells"] = len(sells)               # รวมขายบางส่วนตอนปรับน้ำหนัก (ตัวเลขแบบเดิม)
        out["win_rate_sells"] = round(float(sum(t["pnl"] > 0 for t in sells) / len(sells)), 3) if sells else None
        out["total_fees"] = round(float(sum(t["fee"] for t in trades)), 2)
    return out


def yearly(eq: pd.Series) -> dict:
    y = eq.resample("YE").last()
    prev = pd.concat([pd.Series([eq.iloc[0]], index=[eq.index[0]]), y.iloc[:-1]])
    return {str(d.year): round(float(v / p - 1), 4) for d, v, p in zip(y.index, y.values, prev.values)}


def benchmarks(T, mkt, start, end, capital, div_yield: float = 0.032) -> dict:
    """SET = ดัชนีราคา (ไม่รวมปันผล); SET_TR_est = ราคา + ปันผลประมาณ div_yield/ปี ทบต้นรายวัน
    (ไม่มีข้อมูล SET TRI จริง — เป็นค่าประมาณ); EW_BH = ซื้อถือเท่ากันทุกตัวในจักรวาล"""
    out = {}
    m = mkt.loc[start:end].dropna()
    if len(m) > 2:
        out["SET"] = capital * m / m.iloc[0]
        days = (m.index - m.index[0]).days.values
        out["SET_TR_est"] = out["SET"] * (1 + div_yield) ** (days / 365.25)
    X = T.loc[start:end]
    a = X.iloc[0].notna()
    X = X.loc[:, a]
    out["EW_BH"] = capital * (X / X.iloc[0]).mean(axis=1)
    return out
