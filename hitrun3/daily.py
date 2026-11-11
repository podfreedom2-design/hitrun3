"""คำสั่ง daily (สำหรับ GitHub Actions): fetch -> signal -> paper -> alerts -> dashboard/export
สถานะกันส่งซ้ำเก็บที่ data/alert_state.json"""
from __future__ import annotations
import json, os, traceback
from datetime import datetime, timedelta, timezone
import pandas as pd
from pandas.tseries.offsets import BDay

from . import config as C, data as D, engine as EN, strategy as S, paper as PP, telegram as TG

BKK = timezone(timedelta(hours=7))
ALERT_STATE = os.path.join(C.DATA, "alert_state.json")
TH = {"STOCKS": "ถือหุ้นไทย 📈", "GOLD": "ถือทองคำ 🟡", "CASH": "ถือเงินสด 💵", "HOLD": "ถือของเดิม (ข้อมูล SET ขาด/เก่า) ⛔"}
ACT = {"BUY": "ซื้อ", "SELL": "ขาย", "HOLD": "ถือต่อ"}


def now_bkk() -> datetime:
    return datetime.now(BKK)


def load_alert_state() -> dict:
    if os.path.exists(ALERT_STATE):
        with open(ALERT_STATE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_alert_state(a: dict) -> None:
    with open(ALERT_STATE, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=2)


def sym_name(s):
    return "ทองคำ (ออม NOW)" if s == EN.GOLD else s


# ---------- ตรวจข้อมูล ----------
def check_fetch(cfg, report: dict, today) -> list[str]:
    """คืนรายการปัญหา (ว่าง = ปกติ)"""
    probs = []
    bad = [k for k, v in report.items() if v[0] == "ERROR"]
    if cfg.market_symbol not in report or report.get(cfg.market_symbol, ("ERROR",))[0] == "ERROR":
        probs.append("ดึงดัชนี SET ไม่ได้")
    if EN.thgold(cfg) and report.get(D.THGOLD, ("ERROR",))[0] == "ERROR":
        probs.append("ดึงราคาทองสมาคมค้าทองคำไม่ได้")
    n = len(cfg.universe)
    nbad = len([b for b in bad if b in cfg.universe])
    if n and nbad > max(3, n // 5):
        probs.append(f"ดึงราคาหุ้นไม่ได้ {nbad}/{n} ตัว")
    # ข้อมูลเก่าเกิน stale_days วันทำการ (SET, ทอง และหุ้นทุกตัว)
    lim = pd.Timestamp(today) - BDay(int(getattr(cfg, "stale_days", 4)))
    gsym = D.THGOLD if EN.thgold(cfg) else cfg.gold_symbol
    for k, name in ((cfg.market_symbol, "SET"), (gsym, "ทองคำ")):
        s = D.load_close(k, cfg)
        if s is not None and len(s) and s.index[-1] < lim:
            probs.append(f"ข้อมูล {name} ล่าสุด {s.index[-1].date()} เก่าเกินไป")
    old = [s for s in cfg.universe if (lambda x: x is not None and len(x) and x.index[-1] < lim)(D.load_close(s, cfg))]
    if old:
        probs.append(f"หุ้นข้อมูลเก่าเกิน {getattr(cfg, 'stale_days', 4)} วันทำการ: {', '.join(old)}")
    # ตรวจความผิดปกติของราคา (เฉพาะที่กระทบสัญญาณตอนนี้)
    try:
        probs += [w["msg"] for w in D.validate(cfg) if w["level"] == "error"]
    except Exception as e:  # noqa
        probs.append(f"ตรวจข้อมูลไม่สำเร็จ: {type(e).__name__}: {e}")
    return list(dict.fromkeys(probs))


# ---------- ข้อความ ----------
def msg_orders(cfg, sig, st, trades, prices, eq) -> str:
    d = pd.Timestamp(sig["date"]).date()
    L = [f"🔔 HitRun V3 — รายการปรับพอร์ตประจำเดือน",
         f"คำนวณจากราคาปิด {d} (สิ้นเดือน)",
         f"สภาวะตลาด: {TH[sig['regime']]}",
         f"SET {'เหนือ' if sig['set_up'] else 'ใต้'}เส้น SMA{cfg.ma_days} | ทอง {'เหนือ' if sig['gold_up'] else 'ใต้'}เส้น SMA{cfg.ma_days}",
         "", "รายการ (ทำวันทำการแรกของเดือน):"]
    sold = {t["sym"] for t in trades if t["side"] == "SELL"}
    bought = {t["sym"] for t in trades if t["side"] == "BUY"}
    for t in sorted(trades, key=lambda t: (t["side"] != "SELL", t["sym"])):
        q = f"{t['shares']:,.4f} บาททองคำ" if t["sym"] == EN.GOLD else f"{int(t['shares']):,} หุ้น"
        full = " (ขายหมด)" if t["side"] == "SELL" and t["sym"] not in st["holdings"] else ""
        L.append(f"• {ACT[t['side']]} {sym_name(t['sym'])} {q} @ {t['price']:,.2f}{full}")
    for s, h in sorted(st["holdings"].items()):
        if s not in sold and s not in bought:
            L.append(f"• ถือต่อ {sym_name(s)} {h['shares']:,} @ {prices.get(s, 0):,.2f}")
    if not trades:
        L.append("• ไม่มีการซื้อขาย ถือเหมือนเดิม")
    if not st["holdings"]:
        L.append("• ถือเงินสดทั้งหมด")
    L += ["", f"มูลค่าพอร์ตจำลอง {eq:,.0f} บาท (เงินทุนตั้งต้น {cfg.capital:,.0f})",
          "หมายเหตุ: จำนวนหุ้นคิดจากพอร์ตจำลอง ปรับตามเงินจริงของคุณ (ถือ 5 ตัว ตัวละ ~1/5)"]
    return "\n".join(L)


def msg_summary(cfg, st, eq, month_label) -> str:
    h = pd.DataFrame(st.get("history", []))
    L = [f"📒 สรุปพอร์ตจำลอง เดือน {month_label}",
         f"มูลค่า {eq:,.0f} บาท | กำไร/ขาดทุนสะสม {eq - cfg.capital:+,.0f} บาท ({(eq / cfg.capital - 1) * 100:+.1f}%)"]
    if len(h):
        h["date"] = pd.to_datetime(h["date"])
        h = h.set_index("date")["equity"].sort_index()
        prev = h[h.index < pd.Timestamp(month_label + "-01")]
        cur = h[h.index < pd.Timestamp(month_label + "-01") + pd.offsets.MonthBegin(1)]
        if len(prev) and len(cur):
            L.append(f"เดือนนี้ {(cur.iloc[-1] / prev.iloc[-1] - 1) * 100:+.1f}%")
        L.append(f"เริ่มพอร์ตจำลอง {st.get('created')} | ปรับพอร์ตล่าสุด {st.get('last_rebalance')}")
    L.append(f"เงินสดคงเหลือ {st['cash']:,.0f} บาท")
    L.append("ถืออยู่: " + (", ".join(f"{sym_name(s)} {v['shares']:,}" for s, v in sorted(st["holdings"].items())) or "-"))
    return "\n".join(L)


def ma_warnings(cfg, mkt, gold, i) -> list[str]:
    band = float(getattr(cfg, "alert_ma_band", 0.015))
    out = []
    for name, s in (("SET", mkt), ("ทองคำ", gold)):
        ma = S.moving_average(s, cfg.ma_days, cfg.ma_type)
        c, m = s.iloc[i], ma.iloc[i]
        if pd.isna(c) or pd.isna(m):
            continue
        dist = c / m - 1
        # สถานะ ณ สิ้นเดือนก่อน (เทียบว่าตัดเส้นหรือยัง)
        idx = s.index[: i + 1]
        pm = idx[idx < idx[-1].to_period("M").start_time]
        crossed = False
        if len(pm):
            j = len(pm) - 1
            if pd.notna(ma.iloc[j]):
                crossed = (s.iloc[j] > ma.iloc[j]) != (c > m)
        if crossed:
            out.append(f"⚠️ {name} {'ตัดขึ้น' if c > m else 'ตัดลง'}เส้น SMA{cfg.ma_days} แล้วเทียบกับสิ้นเดือนก่อน "
                       f"(ปิด {c:,.2f} / เส้น {m:,.2f}, {dist * 100:+.2f}%) — ถ้าปิดสิ้นเดือนแบบนี้ สัญญาณจะเปลี่ยน")
        elif abs(dist) <= band:
            out.append(f"👀 {name} ใกล้เส้น SMA{cfg.ma_days} ห่างเพียง {dist * 100:+.2f}% "
                       f"(ปิด {c:,.2f} / เส้น {m:,.2f}) — สัญญาณสิ้นเดือนอาจเปลี่ยน")
    return out


def bdays_left_in_month(dt) -> int:
    """จำนวนวันทำการ (จ-ศ) ที่เหลือหลังวันนี้ในเดือนเดียวกัน"""
    dt = pd.Timestamp(dt).normalize()
    end = dt + pd.offsets.MonthEnd(0)
    return max(len(pd.bdate_range(dt + pd.Timedelta(days=1), end)), 0)


# ---------- งานหลัก ----------
def run(cfg, dry_run=False, preview=False, skip_fetch=False) -> int:
    """คืน exit code (0 ปกติ, 1 มีปัญหาข้อมูล)"""
    today = now_bkk().date()
    A = load_alert_state()
    sends = []  # (key, text)

    probs = []
    if not skip_fetch:
        try:
            report = D.fetch(cfg)
            probs = check_fetch(cfg, report, today)
        except Exception as e:  # noqa
            probs = [f"fetch ล้มเหลว: {type(e).__name__}: {e}"]

    T, mkt, gold = D.load_panel(cfg)
    i = len(T) - 1
    dt = T.index[i]
    # วันที่ใช้ปรับพอร์ต: ถ้าแท่งล่าสุดเป็นวันทำการสุดท้ายของเดือน ใช้แท่งนี้; ไม่งั้นใช้แท่งสุดท้ายของเดือนก่อน (กรณีพลาด/วันหยุด)
    if PP.is_last_trading_day(dt):
        ime = i
    else:
        prev = T.index[T.index < dt.to_period("M").start_time]
        ime = len(prev) - 1 if len(prev) else None

    st = PP.load_state(cfg)
    trades = []
    sf = D.LAST_HEALTH.get("set_fresh")
    if ime is not None:
        # ลงยอดเฉพาะเมื่อถึงกำหนด (วันทำการสุดท้ายของเดือน หรือรันตามหลังด้วยราคาสิ้นเดือน) — กันลงยอดซ้ำในตัว
        st, trades, info = PP.book_if_due(cfg, st, T, mkt, gold, set_fresh=sf)
        print("  " + info["msg"])
        if info["status"] == "booked" and not dry_run:
            PP.save_state(st)
        me_month = T.index[ime].strftime("%Y-%m")
        if info["status"] == "hold_stale":
            probs.append(info["msg"])
        # (a) รายการปรับพอร์ต — ส่งครั้งเดียวต่อเดือนสิ้นงวด (คืนสิ้นเดือนหลังตลาดปิด หรือวันแรกของเดือนใหม่ถ้าพลาด)
        elif (st.get("last_rebalance") or "")[:7] == me_month and (A.get("orders_sent_for") != me_month or preview):
            sig_me = EN.signal_at(cfg, T, mkt, gold, ime, set_fresh=sf)
            px_me = EN.prices_at(T, gold, ime)
            if not trades:
                trades = [t for t in st.get("trades", []) if str(t.get("date", ""))[:10] == st.get("last_rebalance")]
            eq = PP.equity(st, px_me, cfg)
            sends.append(("orders", me_month, msg_orders(cfg, sig_me, st, trades, px_me, eq)))
            # (c) สรุปพอร์ตจำลองรายเดือน
            sends.append(("summary", me_month, msg_summary(cfg, st, eq, me_month)))

    # ไม่บันทึกมูลค่ารายวันลงไฟล์ (ลงยอดเฉพาะวันปรับพอร์ต) — มูลค่าวันนี้แสดงบนแดชบอร์ดอย่างเดียว
    prices = EN.prices_at(T, gold, i)

    # (b) เตือนใกล้เส้น SMA ในช่วง N วันทำการสุดท้ายของเดือน
    nwin = int(getattr(cfg, "alert_days_before_month_end", 3))
    if bdays_left_in_month(today) < nwin or preview:
        w = ma_warnings(cfg, mkt, gold, i)
        key = str(today)
        if w and (A.get("ma_warn_date") != key or preview):
            sends.append(("ma", key, "🟠 HitRun V3 — เตือนก่อนสิ้นเดือน (ราคาปิด " + str(dt.date()) + ")\n" + "\n".join(w)
                          + f"\nเหลือวันทำการอีก {bdays_left_in_month(today)} วันในเดือนนี้"))

    # (d) แจ้งปัญหา
    if probs:
        key = str(today)
        if A.get("error_date") != key or preview:
            sends.append(("error", key, "❌ HitRun V3 — ระบบมีปัญหา\n" + "\n".join("• " + p for p in probs)
                          + "\nระบบใช้ข้อมูลเดิมในไฟล์ไปก่อน กรุณาเช็ก GitHub Actions log"))

    for kind, key, text in sends:
        ok = TG.send(text, cfg, dry_run=dry_run)
        if ok and not preview:
            A[{"orders": "orders_sent_for", "summary": "summary_sent_for", "ma": "ma_warn_date",
               "error": "error_date"}[kind]] = key
    A["last_run"] = now_bkk().strftime("%Y-%m-%d %H:%M")
    A["last_data_date"] = str(dt.date())
    if not dry_run and not preview:
        save_alert_state(A)
    if not sends:
        print("  วันนี้ไม่มีเรื่องต้องแจ้ง Telegram")
    return 1 if probs else 0


def notify_crash(cfg, exc: BaseException) -> None:
    os.makedirs(C.OUT, exist_ok=True)
    open(os.path.join(C.OUT, ".crash_notified"), "w").close()  # กัน workflow ส่งซ้ำ
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-1500:]
    TG.send("❌ HitRun V3 — รันไม่สำเร็จ (crash)\n" + tb, cfg)
