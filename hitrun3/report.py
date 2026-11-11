"""ส่งออกผลให้ AI ตัวอื่นอ่าน: out/ai_report.json, out/ai_report.md, CSV"""
from __future__ import annotations
import json, os
import pandas as pd
from .config import OUT

SCHEMA_VERSION = "hitrun3.ai_report.v1"

CAVEATS = [
    "Survivorship bias: จักรวาลหุ้นคือรายชื่อหุ้นที่ยังอยู่ในตลาดวันนี้ (ไม่มีรายชื่อ SET50/SET100 ย้อนหลังจริง) ผลย้อนหลังจึงดีเกินจริง ประมาณ 3-5%/ปี",
    "ผลช่วง 2019+ ได้แรงหนุนจากทองขึ้นแรงผิดปกติ (2020, 2024, 2025) ถ้าช่วงนั้นเป็นเงินสด CAGR จะเหลือราว 15-16%",
    "โหมด original: ราคา auto_adjust รวมปันผล (ลงทุนต่อ ไม่หักภาษี), ล็อต 100 หน่วยราคาปรับ — โหมด realistic: ราคาจริง ล็อต 100 หุ้นจริง ปันผลหักภาษี 10% ดอกเบี้ยเงินสดตาม cash_rate",
    "ซื้อขายที่ราคาปิดวันทำการสุดท้ายของเดือน (ทำจริงวันทำการแรกของเดือนถัดไปได้ผลต่างราว ±1%/ปี); ไม่จำลองสภาพคล่อง",
    "SET TR (ประมาณ) = ดัชนีราคา + ปันผลคงที่ set_div_yield/ปี ไม่ใช่ข้อมูล SET TRI จริง",
    "ทอง = ทองคำแท่ง 96.5% บาท/บาททองคำ (สมาคมค้าทองคำ ตั้งแต่ 2006-05) ซื้อที่ราคาขายออก คิดมูลค่าที่ราคารับซื้อ (หัก gold_spread_thb)",
    "ราคาที่แก้มือ: data/corrections.csv (TRUE ควบรวม DTAC 2023-03-03, SCB แท่งแรก 2022-04-20); ราคา <= 0 ถูกตัดทิ้ง",
    "ผลอดีตไม่รับประกันอนาคต; ไม่ใช่คำแนะนำการลงทุน",
]


def _ser(o):
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def write_all(cfg, bt: dict, met: dict, years: dict, bench_met: dict, sig: dict, stat: dict,
              paper_state: dict | None, ranking: list, extra: dict | None = None, checks: list | None = None) -> dict:
    os.makedirs(OUT, exist_ok=True)
    bt["equity"].to_csv(os.path.join(OUT, "equity.csv"), encoding="utf-8-sig")
    pd.DataFrame(bt["trades"]).to_csv(os.path.join(OUT, "trades.csv"), index=False, encoding="utf-8-sig")
    rows = [{"date": h["date"], "regime": h["regime"], "sym": s, "shares": n}
            for h in bt["holdings"] for s, n in (h["holdings"].items() or [("CASH", 0)])]
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "holdings.csv"), index=False, encoding="utf-8-sig")
    cfgd = cfg.to_dict()
    cfgd.pop("notify_hook", None)
    rep = {
        "schema": SCHEMA_VERSION,
        "generated_from": "HitRun TH V3",
        "strategy": {
            "name": "Thai momentum + SET SMA filter + gold fallback (monthly)",
            "rules": [
                f"ทุกวันทำการสุดท้ายของเดือน ดูราคาปิด",
                f"ถ้า SET > {cfg.ma_type}{cfg.ma_days}: ถือหุ้นไทย {cfg.top_n} ตัวที่ผลตอบแทน {cfg.lookback_days} วันสูงสุดและ > 0 ตัวละ 1/{cfg.top_n} ปัดล็อต {cfg.lot_size}",
                f"ไม่งั้น ถ้าทอง (บาท) > {cfg.ma_type}{cfg.ma_days} ของตัวเอง: ถือทอง 100%",
                "ไม่งั้น ถือเงินสด/กองทุนตลาดเงิน",
            ],
        },
        "config": cfgd,
        "period": {"start": met["start"], "end": met["end"], "years": met["years"]},
        "metrics": met,
        "metrics_realistic": (extra or {}).get("realistic", {}) and {k: v for k, v in extra["realistic"].items() if k != "equity"},
        "benchmarks": bench_met,
        "benchmark_notes": {"SET": "ดัชนีราคา ไม่รวมปันผล", "SET_TR_est": f"ประมาณ: ราคา + ปันผล {getattr(cfg, 'set_div_yield', 0.032)*100:.1f}%/ปี (ไม่ใช่ SET TRI จริง)",
                            "EW_BH": "ซื้อถือเท่ากันทุกตัวในจักรวาล"},
        "data_checks": checks or [],
        "per_year_returns": years,
        "regime_history": bt["regimes"],
        "monthly_holdings": bt["holdings"],
        "trades": bt["trades"],
        "current_signal": {
            "date": str(pd.Timestamp(sig["date"]).date()), "regime": sig["regime"], "picks": sig["picks"],
            "set_above_ma": None if pd.isna(sig["set_up"]) else bool(sig["set_up"]),
            "gold_above_ma": None if pd.isna(sig["gold_up"]) else bool(sig["gold_up"]),
            "ranking_top": ranking, "actions": stat["actions"], "alerts": stat["alerts"]},
        "paper_portfolio": paper_state,
        "paper_snapshot": stat.get("paper"),
        "caveats": CAVEATS,
    }
    with open(os.path.join(OUT, "ai_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2, default=_ser)
    md = _markdown(rep)
    with open(os.path.join(OUT, "ai_report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    return rep


def _pct(x):
    return "-" if x is None else f"{x*100:.1f}%"


def _markdown(r) -> str:
    m = r["metrics"]
    L = [f"# HitRun TH V3 — รายงานสำหรับ AI", "",
         f"ช่วงทดสอบ {r['period']['start']} → {r['period']['end']} ({r['period']['years']} ปี)", "",
         "## กติกา", *[f"- {x}" for x in r["strategy"]["rules"]], "",
         "## ผลลัพธ์", "| ตัวชี้วัด | ระบบ | " + " | ".join(r["benchmarks"]) + " |",
         "|---|---|" + "---|" * len(r["benchmarks"])]
    for k, lab in (("final_value", "มูลค่าสุดท้าย"), ("cagr", "CAGR"), ("max_drawdown", "Max DD"), ("sharpe", "Sharpe")):
        f = (lambda v: f"{v:,.0f}") if k == "final_value" else (lambda v: f"{v:.2f}") if k == "sharpe" else _pct
        L.append(f"| {lab} | {f(m[k])} | " + " | ".join(f(b.get(k)) if b.get(k) is not None else "-" for b in r["benchmarks"].values()) + " |")
    rr = (r.get("metrics_realistic") or {}).get("metrics")
    if rr:
        L.append(f"| realistic (ราคาจริง/ภาษีปันผล/ดอกเบี้ย) | มูลค่า {rr['final_value']:,.0f} | CAGR {_pct(rr['cagr'])} | MaxDD {_pct(rr['max_drawdown'])} |")
    L += ["", f"จำนวนรายการซื้อขาย {m.get('n_trades')} | ปิดไม้จริง (round trip) {m.get('n_closed')} | ชนะ {_pct(m.get('win_rate'))} "
          f"(หุ้น {_pct(m.get('win_rate_stocks'))}, ทอง {_pct(m.get('win_rate_gold'))}; แบบเดิมนับทุกการขาย {_pct(m.get('win_rate_sells'))}) | ค่าธรรมเนียมรวม {m.get('total_fees'):,.0f} บาท", "",
          "## ผลรายปี", "| ปี | % |", "|---|---|", *[f"| {y} | {_pct(v)} |" for y, v in r["per_year_returns"].items()], "",
          "## สัญญาณล่าสุด", f"วันที่ {r['current_signal']['date']} — สภาวะ **{r['current_signal']['regime']}** — ถือ: {', '.join(r['current_signal']['picks']) or 'เงินสด'}", "",
          "| หุ้น | คำสั่ง | ถืออยู่ | เป้าหมาย |", "|---|---|---|---|",
          *[f"| {a['sym']} | {a['action']} | {a['current']} | {a['target']} |" for a in r["current_signal"]["actions"]], "",
          "## ข้อควรระวัง", *[f"- {c}" for c in r["caveats"]], "",
          "## Prompt สำหรับ AI ตัวอื่น", "```",
          "คุณคือนักวิเคราะห์เชิงปริมาณ อ่านไฟล์ ai_report.json (schema hitrun3.ai_report.v1) และ equity.csv/trades.csv/holdings.csv แนบมา",
          "1) ประเมินว่าผลตอบแทนน่าเชื่อถือแค่ไหน โดยคำนึงถึง survivorship bias, ช่วงไม่มีตัวกรองตลาด, ต้นทุน และการพึ่งทอง",
          "2) วิเคราะห์ drawdown และปีที่แย่ที่สุด ว่าเกิดจากสภาวะใด (regime_history)",
          "3) เสนอการปรับปรุงไม่เกิน 3 ข้อที่ไม่ overfit พร้อมวิธีทดสอบนอกตัวอย่าง",
          "4) ตรวจคำสั่งเดือนนี้ (current_signal.actions) ว่าสอดคล้องกับกติกาหรือไม่",
          "ตอบเป็นภาษาไทย กระชับ ใช้ตัวเลขจากไฟล์เท่านั้น", "```", ""]
    return "\n".join(L)
