"""HitRun TH V3 — ประตูเดียว
  python run.py fetch        ดึงราคาล่าสุด (yfinance, ต้องต่อเน็ต) รวมกับไฟล์เดิม
  python run.py import-csv ^SET.BK file.csv   นำเข้าประวัติจาก CSV
  python run.py signal       ดูสัญญาณ + รายการซื้อขายเดือนนี้ + แจ้งเตือน
  python run.py backtest     ทดสอบย้อนหลังเต็มช่วง (+ ส่งออกรายงาน AI + แดชบอร์ด)
  python run.py paper        ดูสถานะพอร์ตจำลอง (อ่านอย่างเดียว ไม่เขียนไฟล์)
  python run.py paper --book  ลงยอดพอร์ตจำลอง เฉพาะเมื่อถึงวันปรับพอร์ต (สิ้นเดือน) — วันอื่นแค่แสดงสถานะ
  python run.py check        ตรวจความผิดปกติของข้อมูลราคา
  python run.py sensitivity  ทดสอบความทนทาน (top-N, lookback, ตัดหุ้นเด่น, เลื่อนวันซื้อขาย)
  python run.py dashboard    สร้าง out/dashboard.html แล้วเปิด
  python run.py daily        (GitHub Actions) fetch+signal+paper+แจ้ง Telegram+dashboard+export
  python run.py telegram-test  ส่งข้อความทดสอบ Telegram
  python run.py export       เขียน out/ai_report.json / .md / CSV
"""
from __future__ import annotations
import argparse, json, os, sys, warnings, webbrowser
warnings.simplefilter('ignore')
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from hitrun3 import config as C, data as D, engine as EN, strategy as S, paper as PP, report as RP, dashboard as DB, notify

TH = {"STOCKS": "ถือหุ้นไทย", "GOLD": "ถือทองคำ", "CASH": "ถือเงินสด", "HOLD": "ถือของเดิม (ข้อมูล SET ขาด/เก่า)"}


def _bt_key(cfg, start, end):
    import hashlib
    h = hashlib.sha1(json.dumps([cfg.to_dict(), start, end], sort_keys=True, default=str).encode())
    files = [os.path.join(C.PRICES, fn) for fn in sorted(os.listdir(C.PRICES))]
    files += [C.path_of(cfg.corrections_file), D.UNADJ, C.path_of(cfg.membership_file)]
    for p in files:
        if os.path.exists(p):
            with open(p, "rb") as fh:  # ใช้เนื้อหาไฟล์ (fetch เขียนทับทุกครั้ง)
                h.update(os.path.basename(p).encode() + hashlib.sha1(fh.read()).digest())
    return h.hexdigest()


def run_backtest(cfg, T, mkt, gold, start, end, force=False):
    """ใช้ผล backtest เดิม (out/.bt_cache.pkl) ถ้าข้อมูล/ค่าตั้งไม่เปลี่ยน — คำสั่ง backtest บังคับคำนวณใหม่
    คืน (bt, met, bench, bench_met, years, extra) extra = {"realistic": {...}} """
    import pickle
    path = os.path.join(C.OUT, ".bt_cache.pkl")
    key = _bt_key(cfg, start, end) + "|v2"
    if not force and os.path.exists(path):
        try:
            with open(path, "rb") as fh:
                c = pickle.load(fh)
            if c["key"] == key and len(c["res"]) == 6:
                return c["res"]
        except Exception:  # noqa
            pass
    print("  ... กำลังคำนวณ backtest ใหม่ (ข้อมูลหรือค่าตั้งเปลี่ยน)")
    sf = D.LAST_HEALTH.get("set_fresh")
    member = _member(cfg, T)
    bt = EN.backtest(cfg, T, mkt, gold, start, end, set_fresh=sf, member=member)
    eq = bt["equity"]["equity"]
    met = EN.metrics(eq, bt["trades"])
    bench = EN.benchmarks(T, mkt, bt["start"], bt["end"], cfg.capital, cfg.set_div_yield)
    bench_met = {k: EN.metrics(v) for k, v in bench.items()}
    extra = {}
    R = D.load_unadj(cfg, T.index)
    if R is not None:
        rb = EN.backtest(cfg, T, mkt, gold, start, end, mode="realistic", R=R, set_fresh=sf, member=member)
        rm = EN.metrics(rb["equity"]["equity"], rb["trades"])
        rm["dividends_net"] = rb["dividends_net"]
        extra["realistic"] = {"metrics": rm, "years": EN.yearly(rb["equity"]["equity"]), "equity": rb["equity"]["equity"]}
    else:
        extra["realistic"] = None
    res = (bt, met, bench, bench_met, EN.yearly(eq), extra)
    os.makedirs(C.OUT, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump({"key": key, "res": res}, fh)
    return res


def _member(cfg, T):
    if not getattr(cfg, "use_membership", False):
        return None
    m = D.load_membership(cfg)
    if m is None:
        print("  WARN use_membership=true แต่ data/membership.csv ยังไม่มีข้อมูล — ใช้จักรวาลปัจจุบัน")
        return None
    return D.member_mask(m, T.index, T.columns)


def context(cfg, args=None, need_bt=True, force_bt=False):
    T, mkt, gold = D.load_panel(cfg)
    sf = D.LAST_HEALTH.get("set_fresh")
    start = getattr(args, "start", None) or cfg.backtest_start
    end = getattr(args, "end", None) or cfg.backtest_end
    if need_bt:
        bt, met, bench, bench_met, years, extra = run_backtest(cfg, T, mkt, gold, start, end, force_bt)
    else:
        bt = met = bench = bench_met = years = extra = None
    i = len(T) - 1
    member = _member(cfg, T)
    sig = EN.signal_at(cfg, T, mkt, gold, i, set_fresh=sf, eligible=None if member is None else member.iloc[i])
    prices = EN.prices_at(T, gold, i)
    st = PP.load_state(cfg)          # อ่านอย่างเดียว — ไม่ mark/ไม่บันทึก
    stat = PP.status(cfg, st, sig, prices)
    snap = PP.snapshot(cfg, st, prices) if st["created"] else None
    stat["paper"] = snap
    checks = D.validate(cfg, panel_last=T.index[-1])
    for w in checks:
        if w["level"] in ("error", "warn") and w["kind"] in ("stale", "jump", "missing", "suspended", "nonpositive"):
            if w["level"] == "error" or w["kind"] in ("stale", "suspended"):
                stat["alerts"].append({"level": "error" if w["level"] == "error" else "info", "msg": "ข้อมูล: " + w["msg"]})
    sc = sig["scores"].dropna().sort_values(ascending=False)
    ranking = [{"rank": n + 1, "sym": s, "ret12m": round(float(v), 4), "close": round(float(T[s].iloc[i]), 2)}
               for n, (s, v) in enumerate(sc.head(15).items())]
    sma = S.moving_average(mkt, cfg.ma_days, cfg.ma_type)
    gma = S.moving_average(gold, cfg.ma_days, cfg.ma_type)
    f = lambda x: float(x) if pd.notna(x) else float("nan")
    ctx = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "set_close": f(mkt.iloc[i]), "set_ma": f(sma.iloc[i]),
           "gold_close": f(gold.iloc[i]), "gold_ma": f(gma.iloc[i]),
           "set_up": None if pd.isna(sig["set_up"]) or sig.get("set_stale") else bool(sig["set_up"]),
           "gold_up": None if pd.isna(sig["gold_up"]) else bool(sig["gold_up"]), "caveats": RP.CAVEATS,
           "gold_source": cfg.gold_source.upper(), "checks": checks, "extra": extra,
           "gold_label": "ทองคำแท่ง 96.5% (บาท/บาททองคำ)" if cfg.gold_source.upper() == "THGOLD" else "ทอง GLD (บาท)"}
    return dict(T=T, mkt=mkt, gold=gold, bt=bt, met=met, years=years, bench=bench, bench_met=bench_met,
                sig=sig, prices=prices, st=st, stat=stat, ranking=ranking, ctx=ctx, extra=extra)


def _rel(p):
    try:
        return os.path.relpath(p, C.ROOT)
    except ValueError:
        return p


def write_alerts(cfg, X):
    os.makedirs(C.OUT, exist_ok=True)
    a = {"date": X["stat"]["date"], "regime": X["sig"]["regime"], "alerts": X["stat"]["alerts"],
         "actions": X["stat"]["actions"]}
    with open(os.path.join(C.OUT, "alerts.json"), "w", encoding="utf-8") as fh:
        json.dump(a, fh, ensure_ascii=False, indent=2)
    notify.send(cfg, X["stat"]["alerts"])


def print_signal(X):
    s, st = X["sig"], X["stat"]
    print(f"\n=== สัญญาณ ณ {st['date']} : {TH[s['regime']]} ===")
    for a in st["alerts"]:
        print(f"  [{a['level'].upper()}] {a['msg']}")
    print(f"  มูลค่าพอร์ตที่ใช้คำนวณ {st['equity']:,.0f} บาท  (วันปรับพอร์ตถัดไป {st.get('next_booking')})")
    for a in st["actions"]:
        print(f"  {a['action']:4s} {a['sym']:8s} ถือ {a['current']:>9,} -> เป้า {a['target']:>9,}  ({a['delta']:+,})  @ {a['price']}")


def _mline(lab, m):
    wr = m.get("win_rate")
    w = f"  ปิดไม้จริง {m['n_closed']} ชนะ {wr*100:.0f}%" if wr is not None else ""
    return f"  {lab:28s}: {m['final_value']:>12,.0f} บาท  CAGR {m['cagr']*100:5.2f}%  MaxDD {m['max_drawdown']*100:5.1f}%  Sharpe {m['sharpe']:.2f}{w}"


def print_metrics(X):
    m = X["met"]
    print(f"\n=== Backtest {m['start']} -> {m['end']} ({m['years']} ปี) ทุน {m['start_value']:,.0f} ===")
    print(_mline("ระบบ (original)", m))
    r = (X.get("extra") or {}).get("realistic")
    if r:
        print(_mline("ระบบ (realistic)", r["metrics"]))
        print(f"      realistic = ราคาจริง/ล็อต 100 หุ้นจริง, ปันผลเงินสดหักภาษี {X['cfg'].dividend_tax*100:.0f}% "
              f"(รับสุทธิ {r['metrics'].get('dividends_net', 0):,.0f} บาท), ดอกเบี้ยเงินสด {X['cfg'].cash_rate*100:.1f}%/ปี")
    else:
        print("  (ยังไม่มี data/unadj_panel.csv สำหรับโหมด realistic — รัน FETCH.bat)")
    lab = {"SET": "SET ราคา (ไม่รวมปันผล)", "SET_TR_est": f"SET TR ประมาณ (+ปันผล {X['cfg'].set_div_yield*100:.1f}%/ปี)",
           "EW_BH": "ซื้อถือเท่ากันทุกตัว (EW_BH)"}
    for k, b in X["bench_met"].items():
        print(_mline(lab.get(k, k), b))
    print(f"  win rate แบบเดิม (นับทุกการขาย รวมขายบางส่วน) {m.get('win_rate_sells', 0)*100:.0f}% จาก {m.get('n_sells')} รายการ"
          f" | หุ้น {m.get('n_closed_stocks')} ไม้ ชนะ {(m.get('win_rate_stocks') or 0)*100:.0f}% | ทอง {m.get('n_closed_gold')} ไม้ ชนะ {(m.get('win_rate_gold') or 0)*100:.0f}%")


def print_paper(cfg, X):
    st, sn, stat = X["st"], X["stat"].get("paper"), X["stat"]
    print(f"\n=== พอร์ตจำลอง (สถานะ ณ ราคาปิด {stat['date']}) — อ่านอย่างเดียว ไม่บันทึก ===")
    if not st.get("created") or sn is None:
        print("  ยังไม่ได้เริ่มพอร์ตจำลอง (จะเริ่มเมื่อรัน PAPER.bat ในวันทำการสุดท้ายของเดือน)")
        return
    print(f"  เริ่ม {st['created']} | ลงยอดล่าสุด {st.get('last_rebalance')} ({st.get('last_regime')}) | ลงยอดครั้งถัดไป {stat.get('next_booking')}")
    for r in sn["rows"]:
        unit = "บาททองคำ" if r["sym"] == EN.GOLD else "หุ้น"
        pnl = "" if r["pnl"] is None else f"  กำไร/ขาดทุน {r['pnl']:+,.0f} บาท ({r['pnl_pct']*100:+.1f}%)"
        print(f"  {r['sym']:8s} {r['shares']:>9,} {unit}  ทุนเฉลี่ย {r['avg_cost']:,.2f}  ราคา {r['price'] or 0:,.2f}  มูลค่า {r['value'] or 0:,.0f}{pnl}")
    print(f"  เงินสด {sn['cash']:,.0f} บาท")
    print(f"  มูลค่ารวม {sn['equity']:,.0f} บาท | เทียบทุน {cfg.capital:,.0f}: {sn['pnl_total']:+,.0f} บาท ({sn['pnl_total_pct']*100:+.1f}%)"
          f" | ตั้งแต่ลงยอดล่าสุด {sn['since_booked']:+,.0f} บาท")
    pend = [a for a in stat["actions"] if a["action"] != "HOLD" and a["sym"] != "CASH"]
    print(f"  สัญญาณวันนี้: {TH[X['sig']['regime']]}" + ("" if not pend else
          " — ถ้าปิดสิ้นเดือนแบบนี้จะ " + ", ".join(f"{a['action']} {a['sym']} {abs(a['delta']):,}" for a in pend)))
    for al in stat["alerts"]:
        print(f"  [{al['level'].upper()}] {al['msg']}")


def export(cfg, X):
    RP.write_all(cfg, X["bt"], X["met"], X["years"], X["bench_met"], X["sig"], X["stat"],
                 X["st"] if X["st"]["created"] else None, X["ranking"], extra=X.get("extra"), checks=X["ctx"].get("checks"))
    print(f"  เขียน {_rel(os.path.join(C.OUT, 'ai_report.json'))} / ai_report.md / equity.csv / trades.csv / holdings.csv")


def dash(cfg, X, open_=False):
    p = DB.render(cfg, X["bt"], X["met"], X["years"], X["bench"], X["bench_met"], X["sig"], X["stat"],
                  X["ranking"], X["st"] if X["st"]["created"] else None, X["ctx"])
    print(f"  แดชบอร์ด: {_rel(p)}")
    if open_:
        webbrowser.open("file:///" + p.replace("\\", "/"))


def main():
    from hitrun3 import console as CON
    try:
        CON.setup(json.load(open(os.path.join(C.ROOT, 'config.json'), encoding='utf-8')).get('console_lang', 'auto'))
    except Exception:  # noqa
        CON.setup('auto')
    ap = argparse.ArgumentParser(description="HitRun TH V3")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("fetch")
    sp.add_parser("signal")
    p = sp.add_parser("daily", help="งานรายวันสำหรับ GitHub Actions")
    p.add_argument("--dry-run", action="store_true", help="พิมพ์ข้อความแทนส่ง และไม่บันทึกสถานะ")
    p.add_argument("--preview", action="store_true", help="แสดงตัวอย่างข้อความทุกแบบ (ไม่บันทึกสถานะ)")
    p.add_argument("--skip-fetch", action="store_true")
    sp.add_parser("telegram-test")
    p = sp.add_parser("import-csv", help="นำเข้า CSV ราคา เช่น ดัชนี SET จาก TradingView")
    p.add_argument("symbol"); p.add_argument("path")
    for n in ("backtest", "dashboard", "export"):
        p = sp.add_parser(n)
        p.add_argument("--start"); p.add_argument("--end")
        p.add_argument("--open", action="store_true")
    p = sp.add_parser("paper", help="ดูสถานะพอร์ตจำลอง (ไม่เขียนไฟล์); --book = ลงยอดถ้าถึงวันปรับพอร์ต")
    p.add_argument("--book", action="store_true", help="ลงยอดเฉพาะเมื่อถึงกำหนด (สิ้นเดือน) — ลงซ้ำไม่ได้")
    p.add_argument("--reset", action="store_true", help="ล้างพอร์ตจำลองเริ่มใหม่ (สำรองไฟล์เดิมไว้)")
    p.add_argument("--open", action="store_true")
    sp.add_parser("check", help="ตรวจข้อมูลราคา")
    p = sp.add_parser("sensitivity", help="ทดสอบความทนทาน")
    p.add_argument("--start"); p.add_argument("--end")
    a = ap.parse_args()
    cfg = C.load()
    if a.cmd == "fetch":
        D.fetch(cfg)
        return
    if a.cmd == "telegram-test":
        from hitrun3 import telegram as TG
        if not TG.configured():
            print("  ยังไม่ได้ตั้ง TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID -> แสดงแบบ dry-run")
        ok = TG.send("✅ ทดสอบจาก HitRun V3 — ถ้าเห็นข้อความนี้ แปลว่าตั้งค่า Telegram ถูกต้องแล้ว", cfg)
        sys.exit(0 if ok else 1)
    if a.cmd == "daily":
        from hitrun3 import daily as DL
        try:
            code = DL.run(cfg, dry_run=a.dry_run, preview=a.preview, skip_fetch=a.skip_fetch)
            X = context(cfg)
            m = X["met"]
            print(f"  Backtest {m['start']} -> {m['end']}: CAGR {m['cagr']*100:.1f}%  MaxDD {m['max_drawdown']*100:.1f}%")
            if not (a.dry_run or a.preview):
                write_alerts(cfg, X)
            export(cfg, X)
            dash(cfg, X, False)
        except Exception as e:  # noqa
            if not (a.dry_run or a.preview):
                DL.notify_crash(cfg, e)
            raise
        print("  daily เสร็จ" + (" (มีปัญหาข้อมูล — แจ้งแล้ว)" if code else ""))
        return
    if a.cmd == "import-csv":
        df = D.import_csv(a.symbol, a.path)
        print(f"  นำเข้า {a.symbol}: {df.index[0].date()} -> {df.index[-1].date()} ({len(df)} แท่ง)")
        return
    if a.cmd == "check":
        T, mkt, gold = D.load_panel(cfg)
        ws = D.validate(cfg, panel_last=T.index[-1])
        print(f"\n=== ตรวจข้อมูล ณ {T.index[-1].date()} : error {sum(w['level']=='error' for w in ws)} / warn {sum(w['level']=='warn' for w in ws)} / info {sum(w['level']=='info' for w in ws)} ===")
        for w in sorted(ws, key=lambda w: ("error", "warn", "info").index(w["level"])):
            print(f"  [{w['level'].upper():5s}] {w['msg']}")
        return
    if a.cmd == "sensitivity":
        from hitrun3 import sensitivity as SE
        SE.run(cfg, a.start or cfg.backtest_start, a.end or cfg.backtest_end)
        return
    if a.cmd == "paper":
        if a.reset:
            if os.path.exists(C.STATE):
                bak = C.STATE.replace(".json", f"_reset_{datetime.now():%Y%m%d_%H%M%S}.json")
                os.replace(C.STATE, bak)
                print(f"  ล้างพอร์ตจำลองแล้ว (สำรองเดิมไว้ที่ {_rel(bak)})")
            return
        X = context(cfg, need_bt=False)
        st = X["st"]
        if a.book:
            if not getattr(cfg, "paper_book_local", True):
                print("  paper_book_local=false — เครื่องนี้ไม่ลงยอด (GitHub Actions เป็นผู้ลงยอด) แสดงสถานะอย่างเดียว")
            else:
                st2, tr, info = PP.book_if_due(cfg, PP.load_state(cfg), X["T"], X["mkt"], X["gold"],
                                               set_fresh=D.LAST_HEALTH.get("set_fresh"))
                print(f"\n  {info['msg']}")
                if info["status"] == "booked":
                    PP.save_state(st2)
                    for t in tr:
                        print(f"  {t['side']:4s} {t['sym']:8s} {t['shares']:>9,} @ {t['price']:,.2f}  ค่าธรรมเนียม {t['fee']:,.0f}")
                    X = context(cfg, need_bt=False)
                    st = X["st"]
        print_paper(cfg, X)
        write_alerts(cfg, X)
        if a.open:
            X = context(cfg); export(cfg, X); dash(cfg, X, True)
        return
    if a.cmd == "signal":
        X = context(cfg, a, need_bt=False)
        write_alerts(cfg, X)
        print_signal(X)
        return
    X = context(cfg, a, force_bt=(a.cmd == "backtest"))
    X["cfg"] = cfg
    write_alerts(cfg, X)
    if a.cmd == "backtest":
        print_metrics(X)
        print_signal(X)
    else:
        m = X["met"]
        print(f"  Backtest {m['start']} -> {m['end']}: CAGR {m['cagr']*100:.1f}%  MaxDD {m['max_drawdown']*100:.1f}%")
    export(cfg, X)
    dash(cfg, X, getattr(a, "open", False))


if __name__ == "__main__":
    main()
