"""พอร์ตจำลอง (paper) — เก็บสถานะใน data/paper_state.json
แก้ 2026-11-11: ลงยอด (ซื้อขาย/บันทึกมูลค่า) เฉพาะวันปรับพอร์ตตามกติกาเท่านั้น
  = ราคาปิดวันทำการสุดท้ายของเดือน (หรือรันตามหลังได้ โดยใช้ราคาปิดสิ้นเดือนนั้น ไม่ใช่ราคาวันนี้)
  วันอื่นแสดงสถานะอย่างเดียว ไม่เขียนไฟล์; ลงยอดซ้ำในเดือนเดียวกันไม่ได้ (idempotent)"""
from __future__ import annotations
import json, os
import pandas as pd
from .config import STATE, Config
from . import engine as EN

is_last_trading_day = EN.is_last_trading_day


def load_state(cfg: Config) -> dict:
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"created": None, "cash": float(cfg.capital), "holdings": {}, "trades": [],
            "history": [], "last_rebalance": None, "last_regime": None}


def save_state(st: dict) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE)


def equity(st: dict, prices: dict, cfg: Config | None = None) -> float:
    """มูลค่าพอร์ต (ทองคิดราคารับซื้อถ้าส่ง cfg)"""
    if cfg is None:
        return st["cash"] + sum(h["shares"] * prices.get(s, 0) for s, h in st["holdings"].items())
    return st["cash"] + EN.holdings_value(cfg, st["holdings"], prices, bid=True)


def due_index(T: pd.DataFrame) -> int | None:
    """แท่งที่ใช้ลงยอด: แท่งล่าสุดถ้าเป็นวันทำการสุดท้ายของเดือน ไม่งั้นแท่งสุดท้ายของเดือนก่อน"""
    i = len(T) - 1
    dt = T.index[i]
    if is_last_trading_day(dt):
        return i
    prev = T.index[T.index < dt.to_period("M").start_time]
    return len(prev) - 1 if len(prev) else None


def book_if_due(cfg: Config, st: dict, T, mkt, gold, set_fresh=None, eligible=None) -> tuple[dict, list, dict]:
    """ลงยอดพอร์ตจำลองถ้าถึงกำหนด คืน (state, trades, info)
    info["status"]: booked | already | not_due | hold_stale | not_started"""
    ime = due_index(T)
    if ime is None:
        return st, [], {"status": "not_due", "msg": "ยังไม่มีข้อมูลสิ้นเดือน"}
    me_dt = T.index[ime]
    me_month = me_dt.strftime("%Y-%m")
    lr = (st.get("last_rebalance") or "")[:7]
    if lr and lr >= me_month:
        return st, [], {"status": "already", "date": str(me_dt.date()),
                        "msg": f"ลงยอดรอบสิ้นเดือน {me_month} แล้ว (ครั้งล่าสุด {st.get('last_rebalance')}) — รอบถัดไปวันทำการสุดท้ายของเดือนหน้า"}
    if not st.get("created") and ime != len(T) - 1:
        return st, [], {"status": "not_started", "msg": "ยังไม่เริ่มพอร์ตจำลอง — จะเริ่มได้ที่ราคาปิดวันทำการสุดท้ายของเดือน"}
    sig = EN.signal_at(cfg, T, mkt, gold, ime, set_fresh=set_fresh, eligible=eligible)
    if sig["regime"] == "HOLD":
        return st, [], {"status": "hold_stale", "date": str(me_dt.date()), "sig": sig,
                        "msg": f"ข้อมูลดัชนี SET ณ {me_dt.date()} ขาด/เก่า — ยังไม่ลงยอด ถือของเดิมไว้ (จะลงยอดย้อนหลังด้วยราคาสิ้นเดือนเมื่อข้อมูลครบ)"}
    px = EN.prices_at(T, gold, ime)
    if not st.get("created"):
        st["created"] = str(me_dt.date())
    eq = equity(st, px, cfg)
    tgt = EN.targets(cfg, sig, eq, px)
    hold, cash, trades = EN.rebalance(cfg, st["holdings"], st["cash"], px, tgt, me_dt)
    st.update(holdings=hold, cash=round(cash, 2), last_rebalance=str(me_dt.date()), last_regime=sig["regime"])
    st["trades"] += trades
    mark(st, me_dt, px, cfg)
    return st, trades, {"status": "booked", "date": str(me_dt.date()), "sig": sig, "prices": px,
                        "msg": f"ลงยอดพอร์ตจำลองที่ราคาปิด {me_dt.date()} : {len(trades)} รายการ"}


def next_booking_date(dt) -> str:
    """วันทำการสุดท้าย (จ-ศ) ของเดือนนี้ — วันหยุดไทยอาจทำให้เลื่อนเร็วขึ้น"""
    dt = pd.Timestamp(dt)
    if is_last_trading_day(dt):
        return str(dt.date())
    return str(pd.bdate_range(dt, dt + pd.offsets.MonthEnd(0))[-1].date())


def snapshot(cfg, st, prices) -> dict:
    """มูลค่า ณ ราคาล่าสุด (คำนวณในหน่วยความจำ ไม่บันทึก)"""
    rows = []
    for s, h in sorted(st["holdings"].items()):
        p = prices.get(s)
        v = h["shares"] * EN.value_px(cfg, s, p) if p else None
        rows.append({"sym": s, "shares": h["shares"], "avg_cost": round(h["cost"] / h["shares"], 4) if h["shares"] else 0,
                     "price": p, "value": round(v, 2) if v is not None else None,
                     "pnl": round(v - h["cost"], 2) if v is not None else None,
                     "pnl_pct": round(v / h["cost"] - 1, 4) if v is not None and h["cost"] else None})
    eq = equity(st, prices, cfg)
    hist = st.get("history") or []
    last_booked = hist[-1]["equity"] if hist else float(cfg.capital)
    return {"rows": rows, "equity": round(eq, 2), "cash": st["cash"],
            "pnl_total": round(eq - cfg.capital, 2), "pnl_total_pct": round(eq / cfg.capital - 1, 4),
            "since_booked": round(eq - last_booked, 2), "last_booked_equity": last_booked}


def status(cfg, st, sig, prices) -> dict:
    """คำนวณ action list + การแจ้งเตือน (ไม่ซื้อขาย ไม่เขียนไฟล์)"""
    dt = pd.Timestamp(sig["date"])
    eq = equity(st, prices, cfg) if st["created"] else float(cfg.capital)
    tgt = EN.targets(cfg, sig, eq, prices)
    cur = {s: h["shares"] for s, h in st["holdings"].items()}
    hold_mode = tgt is None
    if hold_mode:
        tgt = dict(cur)
    actions = []
    order = list(tgt) + [s for s in sorted(cur) if s not in tgt]
    for s in order:
        a, b = cur.get(s, 0), tgt.get(s, 0)
        px = prices.get(s)
        kind = "BUY" if b > a else "SELL" if b < a else "HOLD"
        actions.append({"sym": s, "action": kind, "current": a, "target": b, "delta": round(b - a, 6),
                        "price": round(px, 2) if px else None,
                        "value": round(abs(b - a) * px, 0) if px else None})
    if not tgt and not cur:
        actions.append({"sym": "CASH", "action": "HOLD", "current": 0, "target": 0, "delta": 0,
                        "price": None, "value": round(eq, 0)})
    month = dt.strftime("%Y-%m")
    done = bool(st.get("last_rebalance")) and st["last_rebalance"][:7] >= month
    last_day = is_last_trading_day(dt)
    alerts = []
    if sig.get("set_stale") or sig["regime"] == "HOLD":
        alerts.append({"level": "error", "msg": "ข้อมูลดัชนี SET ขาดหรือเก่า — ระบบไม่เดาสัญญาณ: ถือของเดิมไว้ ห้ามปรับพอร์ตจนกว่าข้อมูลจะครบ (รัน FETCH ใหม่)"})
    if not st["created"]:
        alerts.append({"level": "info", "msg": "ยังไม่ได้เริ่มพอร์ตจำลอง — จะเริ่มเองเมื่อรัน PAPER.bat ในวันทำการสุดท้ายของเดือน"})
    if not done and last_day:
        alerts.append({"level": "due", "msg": f"ถึงวันปรับพอร์ตแล้ว ({dt.date()} เป็นวันทำการสุดท้ายของเดือน) — ทำตามรายการซื้อขายด้านล่าง แล้วรัน PAPER.bat เพื่อลงยอดพอร์ตจำลอง"})
    elif st.get("last_rebalance"):
        lr = pd.Timestamp(st["last_rebalance"])
        if (dt.to_period("M") - lr.to_period("M")).n >= 2:
            alerts.append({"level": "due", "msg": f"พลาดรอบปรับพอร์ตสิ้นเดือน (ลงยอดล่าสุด {lr.date()}) — รัน PAPER.bat เพื่อลงยอดด้วยราคาปิดสิ้นเดือน"})
    if st.get("last_regime") and sig["regime"] not in ("HOLD", st["last_regime"]):
        alerts.append({"level": "regime", "msg": f"สภาวะตลาดวันนี้ต่างจากรอบที่ลงยอด: {st['last_regime']} → {sig['regime']} "
                       f"(ยังไม่มีผล — ตัดสินที่ราคาปิดวันทำการสุดท้ายของเดือน {next_booking_date(dt)})"})
    elif any(a["action"] != "HOLD" for a in actions if a["sym"] != "CASH") and not last_day and not any(x["level"] == "due" for x in alerts):
        alerts.append({"level": "info", "msg": f"สัญญาณวันนี้ต่างจากพอร์ต แต่ยังไม่ถึงวันปรับพอร์ต ({next_booking_date(dt)}) — ดูไว้ก่อน ยังไม่ต้องซื้อขาย"})
    return {"date": str(dt.date()), "equity": round(eq, 2), "actions": actions, "alerts": alerts,
            "rebalance_done_this_month": bool(done), "is_last_trading_day": last_day, "targets": tgt,
            "next_booking": next_booking_date(dt), "hold": hold_mode}


def mark(st, dt, prices, cfg=None):
    """บันทึกมูลค่าลง history — เรียกเฉพาะตอนลงยอด (book_if_due)"""
    d = str(pd.Timestamp(dt).date())
    e = round(equity(st, prices, cfg), 2)
    st["history"] = [h for h in st["history"] if h["date"] != d] + [{"date": d, "equity": e}]
