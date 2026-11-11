"""ทดสอบความทนทาน (robustness) — ไม่เปลี่ยนกติกาจริง แค่ดูว่าผลพึ่งค่าตั้ง/หุ้นไม่กี่ตัวแค่ไหน
เขียน out/sensitivity.csv และ out/sensitivity.md"""
from __future__ import annotations
import copy, os
import pandas as pd
from . import config as C, data as D, engine as EN


def _run(cfg, T, mkt, gold, start, end, sf, R=None, **kw):
    mode = "realistic" if R is not None else "original"
    bt = EN.backtest(cfg, T, mkt, gold, start, end, mode=mode, R=R, set_fresh=sf, **kw)
    m = EN.metrics(bt["equity"]["equity"], bt["trades"])
    e = bt["equity"]["equity"]
    sub = {}
    for a, b, k in (("2012-01-01", "2018-12-31", "cagr_2012_18"), ("2019-01-01", "2100-01-01", "cagr_2019_now")):
        x = e.loc[a:b]
        sub[k] = round(float((x.iloc[-1] / x.iloc[0]) ** (365.25 / max((x.index[-1] - x.index[0]).days, 1)) - 1), 4) if len(x) > 20 else None
    return m, bt, sub


def run(cfg, start, end):
    T, mkt, gold = D.load_panel(cfg)
    sf = D.LAST_HEALTH.get("set_fresh")
    R = D.load_unadj(cfg, T.index)
    base_m, base_bt, base_sub = _run(cfg, T, mkt, gold, start, end, sf)
    # หุ้นที่ทำกำไรรวมสูงสุด (จาก round trip + ที่ถืออยู่)
    rt = pd.DataFrame(EN.round_trips(base_bt["trades"]))
    top = list(rt[rt.sym != EN.GOLD].groupby("sym")["pnl"].sum().sort_values(ascending=False).index) if len(rt) else []
    rows = []

    def add(group, label, m, sub):
        rows.append({"group": group, "case": label, "cagr": m["cagr"], "max_dd": m["max_drawdown"],
                     "final_value": m["final_value"], "sharpe": m["sharpe"], "win_rate_rt": m.get("win_rate"),
                     **sub})
    add("base", f"V3 ปัจจุบัน top{cfg.top_n} lookback {cfg.lookback_days}d", base_m, base_sub)
    for n in (3, 5, 7, 10):
        if n == cfg.top_n:
            continue
        c = copy.deepcopy(cfg); c.top_n = n
        m, _, sub = _run(c, T, mkt, gold, start, end, sf); add("top_n", f"top{n}", m, sub)
    for lb, lab in ((126, "6 เดือน"), (189, "9 เดือน"), (252, "12 เดือน"), (315, "15 เดือน")):
        if lb == cfg.lookback_days:
            continue
        c = copy.deepcopy(cfg); c.lookback_days = lb
        m, _, sub = _run(c, T, mkt, gold, start, end, sf); add("lookback", f"lookback {lab} ({lb}d)", m, sub)
    for k in (1, 3, 5):
        ex = top[:k]
        m, _, sub = _run(cfg, T, mkt, gold, start, end, sf, exclude=ex); add("exclude_winners", f"ตัด {k} ตัวเด่น: {', '.join(ex)}", m, sub)
    for lag in (1, 2):
        m, _, sub = _run(cfg, T, mkt, gold, start, end, sf, lag=lag); add("execution", f"ซื้อขายช้ากว่าสัญญาณ {lag} วัน", m, sub)
    c = copy.deepcopy(cfg); c.ma_days = 150
    m, _, sub = _run(c, T, mkt, gold, start, end, sf); add("ma", "SMA150", m, sub)
    c = copy.deepcopy(cfg); c.ma_days = 250
    m, _, sub = _run(c, T, mkt, gold, start, end, sf); add("ma", "SMA250", m, sub)
    nog = gold * float("nan")
    m, _, sub = _run(cfg, T, mkt, nog, start, end, sf); add("gold", "ไม่ใช้ทอง (ช่วง SET ต่ำกว่าเส้น = เงินสด)", m, sub)
    if R is not None:
        m, _, sub = _run(cfg, T, mkt, gold, start, end, sf, R=R); add("realistic", "realistic (ราคาจริง/ภาษีปันผล/ดอกเบี้ยเงินสด)", m, sub)
        m, _, sub = _run(cfg, T, mkt, gold, start, end, sf, R=R, lag=1); add("realistic", "realistic + ซื้อขายวันถัดไป", m, sub)
    df = pd.DataFrame(rows)
    os.makedirs(C.OUT, exist_ok=True)
    df.to_csv(os.path.join(C.OUT, "sensitivity.csv"), index=False, encoding="utf-8-sig")
    f = lambda x: "-" if x is None or pd.isna(x) else f"{x*100:.1f}%"
    L = ["# HitRun V3 — ทดสอบความทนทาน (sensitivity)", "",
         f"ช่วง {base_m['start']} → {base_m['end']} ทุน {cfg.capital:,.0f} บาท (โหมด original เว้นแต่ระบุ)", "",
         "| กลุ่ม | กรณี | CAGR | MaxDD | มูลค่าสุดท้าย | Sharpe | ชนะ (round trip) | 2012-18 | 2019-ปัจจุบัน |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['group']} | {r['case']} | {f(r['cagr'])} | {f(r['max_dd'])} | {r['final_value']:,.0f} | {r['sharpe']:.2f} | "
                 f"{f(r['win_rate_rt'])} | {f(r['cagr_2012_18'])} | {f(r['cagr_2019_now'])} |")
    L += ["", "อ่านผล: ถ้าเปลี่ยนค่าเล็กน้อยแล้ว CAGR เปลี่ยนมาก หรือตัดหุ้นเด่นไม่กี่ตัวแล้วผลหายมาก = ผลย้อนหลังพึ่งโชค/หุ้นไม่กี่ตัว",
          "หมายเหตุ: จักรวาลหุ้นเป็นรายชื่อปัจจุบัน (survivorship bias) ทุกกรณีจึงดีเกินจริงพอ ๆ กัน"]
    with open(os.path.join(C.OUT, "sensitivity.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    for r in rows:
        print(f"  {r['group']:15s} {r['case'][:55]:55s} CAGR {r['cagr']*100:6.2f}%  MaxDD {r['max_dd']*100:6.1f}%  final {r['final_value']:>12,.0f}")
    print(f"  เขียน out/sensitivity.md / sensitivity.csv")
    return df
