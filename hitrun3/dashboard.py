"""แดชบอร์ด HTML ไฟล์เดียว (ฝัง plotly.js — เปิดออฟไลน์ได้)"""
from __future__ import annotations
import html, os
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from .config import OUT

REG_TH = {"STOCKS": ("ถือหุ้นไทย", "#16a34a"), "GOLD": ("ถือทองคำ", "#ca8a04"), "CASH": ("ถือเงินสด", "#64748b"),
          "HOLD": ("ถือของเดิม — ข้อมูล SET ขาด/เก่า", "#dc2626")}
ACT = {"BUY": ("ซื้อ", "#16a34a"), "SELL": ("ขาย", "#dc2626"), "HOLD": ("ถือต่อ", "#64748b")}


def _fig_html(fig, first):
    fig.update_layout(template="plotly_white", margin=dict(l=40, r=20, t=40, b=30), height=360,
                      font=dict(family="Tahoma, Sarabun, sans-serif"), legend=dict(orientation="h", y=1.12))
    return pio.to_html(fig, include_plotlyjs=True if first else False, full_html=False,
                       config={"displaylogo": False, "responsive": True})


def _badge(ok, yes, no):
    if ok is None:
        return '<span class="b" style="background:#94a3b8">ไม่มีข้อมูล</span>'
    return f'<span class="b" style="background:{"#16a34a" if ok else "#dc2626"}">{yes if ok else no}</span>'


def render(cfg, bt, met, years, bench, bench_met, sig, stat, ranking, paper_state, ctx) -> str:
    os.makedirs(OUT, exist_ok=True)
    e = bt["equity"]["equity"]
    f1 = go.Figure()
    f1.add_scatter(x=e.index, y=e, name="ระบบ V3", line=dict(width=2.5, color="#2563eb"))
    rl = ((ctx.get("extra") or {}).get("realistic") or {})
    if rl.get("equity") is not None:
        f1.add_scatter(x=rl["equity"].index, y=rl["equity"], name="ระบบ V3 (realistic)", line=dict(width=1.5, color="#7c3aed", dash="dot"))
    for k, lab, c in (("EW_BH", "ซื้อถือเท่ากันทุกตัว", "#f59e0b"), ("SET_TR_est", "SET รวมปันผล (ประมาณ)", "#64748b"),
                      ("SET", "ดัชนี SET (ราคา)", "#94a3b8")):
        if k in bench:
            f1.add_scatter(x=bench[k].index, y=bench[k], name=lab, line=dict(color=c))
    f1.update_yaxes(type="log", title="บาท (สเกล log)")
    f1.update_layout(title="มูลค่าพอร์ต เทียบ Buy & Hold")
    dd = e / e.cummax() - 1
    f2 = go.Figure(go.Scatter(x=dd.index, y=dd * 100, fill="tozeroy", line=dict(color="#dc2626"), name="DD"))
    f2.update_layout(title="Drawdown (%) — ลดลงจากจุดสูงสุด", yaxis_title="%")
    ys = list(years)
    f3 = go.Figure(go.Bar(x=ys, y=[years[y] * 100 for y in ys],
                          marker_color=["#16a34a" if years[y] >= 0 else "#dc2626" for y in ys],
                          text=[f"{years[y]*100:.1f}%" for y in ys], textposition="outside"))
    f3.update_layout(title="ผลตอบแทนรายปี (%)")
    regs = pd.DataFrame(bt["regimes"])
    f4 = go.Figure()
    if len(regs):
        cmap = {"STOCKS": 2, "GOLD": 1, "CASH": 0, "HOLD": -1}
        f4.add_scatter(x=pd.to_datetime(regs.date), y=regs.regime.map(cmap), mode="lines", line_shape="hv",
                       line=dict(color="#7c3aed"))
        f4.update_yaxes(tickvals=[-1, 0, 1, 2], ticktext=["ถือเดิม", "เงินสด", "ทอง", "หุ้น"])
    f4.update_layout(title="สภาวะตลาดรายเดือน", height=260)
    figs = [_fig_html(f1, True), _fig_html(f2, False), _fig_html(f3, False), _fig_html(f4, False)]
    paper_fig = ""
    if paper_state and paper_state.get("history"):
        h = pd.DataFrame(paper_state["history"])
        f5 = go.Figure(go.Scatter(x=pd.to_datetime(h.date), y=h.equity, mode="lines+markers", line=dict(color="#0891b2")))
        f5.update_layout(title="มูลค่าพอร์ตจำลอง (paper)")
        paper_fig = _fig_html(f5, False)

    reg_lab, reg_col = REG_TH[sig["regime"]]
    alerts_html = "".join(
        f'<div class="alert {a["level"]}">{"🔔" if a["level"]=="due" else "⛔" if a["level"]=="error" else "⚠️" if a["level"]=="regime" else "ℹ️"} {html.escape(a["msg"])}</div>'
        for a in stat["alerts"]) or '<div class="alert ok">✅ ไม่มีงานต้องทำตอนนี้</div>'
    rows = ""
    for a in stat["actions"]:
        lab, col = ACT[a["action"]]
        name = ("ทองคำแท่ง 96.5% (บาท/บาททองคำ)" if ctx.get("gold_source", "THGOLD") == "THGOLD" else "ทองคำ (GLD เป็นบาท)") if a["sym"] == "GOLD" else ("เงินสด" if a["sym"] == "CASH" else a["sym"])
        unit = ("บาททองคำ" if ctx.get("gold_source", "THGOLD") == "THGOLD" else "หน่วย") if a["sym"] == "GOLD" else "หุ้น"
        pstr = "" if a["price"] is None else f"{a['price']:,.2f}"
        vstr = "" if a["value"] is None else f"{a['value']:,.0f}"
        rows += (f'<tr><td><b>{name}</b></td><td><span class="b" style="background:{col}">{lab}</span></td>'
                 f'<td>{a["current"]:,} </td><td>{a["target"]:,}</td>'
                 f'<td><b>{"+" if a["delta"]>0 else ""}{a["delta"]:,} {unit}</b></td>'
                 f'<td>{pstr}</td><td>{vstr}</td></tr>')
    rank_rows = "".join(
        f'<tr class="{"pick" if r["sym"] in sig["picks"] else ""}"><td>{r["rank"]}</td><td><b>{r["sym"]}</b></td>'
        f'<td style="color:{"#16a34a" if r["ret12m"]>0 else "#dc2626"}">{r["ret12m"]*100:+.1f}%</td><td>{r["close"]:,.2f}</td>'
        f'<td>{"⭐ เลือก" if r["sym"] in sig["picks"] else ""}</td></tr>' for r in ranking)

    def kpi(t, v, sub=""):
        return f'<div class="kpi"><div class="kt">{t}</div><div class="kv">{v}</div><div class="ks">{sub}</div></div>'
    bm = bench_met.get("EW_BH", {})
    kpis = (kpi("ผลตอบแทนต่อปี (CAGR)", f"{met['cagr']*100:.1f}%", f"ซื้อถือ {bm.get('cagr',0)*100:.1f}%")
            + kpi("มูลค่าสุดท้าย", f"{met['final_value']:,.0f}", f"จากทุน {cfg.capital:,.0f} บาท")
            + kpi("ลดลงลึกสุด", f"{met['max_drawdown']*100:.1f}%", f"ซื้อถือ {bm.get('max_drawdown',0)*100:.1f}%")
            + kpi("Sharpe", f"{met['sharpe']:.2f}", f"{met['start']} → {met['end']}")
            + kpi("ปิดไม้จริง / ชนะ", f"{met.get('n_closed',0)} / {(met.get('win_rate') or 0)*100:.0f}%", f"นับแบบ round trip · ค่าธรรมเนียมรวม {met.get('total_fees',0):,.0f}"))
    rm = rl.get("metrics")
    st_ = bench_met.get("SET_TR_est", {})
    if rm:
        kpis += kpi("แบบสมจริง (realistic)", f"{rm['cagr']*100:.1f}%", f"DD {rm['max_drawdown']*100:.1f}% · มูลค่า {rm['final_value']:,.0f}")
    if st_:
        kpis += kpi("SET รวมปันผล (ประมาณ)", f"{st_.get('cagr',0)*100:.1f}%", f"DD {st_.get('max_drawdown',0)*100:.1f}%")
    ps = ""
    sn = stat.get("paper")
    if paper_state and paper_state.get("created") and sn:
        prow = "".join(
            f'<tr><td><b>{"ทองคำ" if r["sym"]=="GOLD" else r["sym"]}</b></td><td>{r["shares"]:,}</td><td>{r["avg_cost"]:,.2f}</td>'
            f'<td>{(r["price"] or 0):,.2f}</td><td>{(r["value"] or 0):,.0f}</td>'
            f'<td style="color:{"#16a34a" if (r["pnl"] or 0)>=0 else "#dc2626"}">{(r["pnl"] or 0):+,.0f} ({(r["pnl_pct"] or 0)*100:+.1f}%)</td></tr>'
            for r in sn["rows"])
        ps = (f'<div class="card"><h2>พอร์ตจำลอง (paper) — สถานะ ณ ราคาปิด {stat["date"]}</h2>'
              f'<p>เริ่ม {paper_state["created"]} · ลงยอดล่าสุด {paper_state.get("last_rebalance")} · ลงยอดครั้งถัดไป {stat.get("next_booking")} '
              f'(ลงยอดเฉพาะวันปรับพอร์ตสิ้นเดือน — ตัวเลขด้านล่างเป็นมูลค่าตลาดวันนี้ ไม่บันทึก)</p>'
              f'<p>มูลค่ารวม <b>{sn["equity"]:,.0f}</b> บาท · เงินสด {sn["cash"]:,.0f} บาท · '
              f'เทียบทุน {cfg.capital:,.0f}: <b style="color:{"#16a34a" if sn["pnl_total"]>=0 else "#dc2626"}">{sn["pnl_total"]:+,.0f} บาท ({sn["pnl_total_pct"]*100:+.1f}%)</b></p>'
              f'<table><tr><th>สินทรัพย์</th><th>จำนวน</th><th>ทุนเฉลี่ย</th><th>ราคาล่าสุด</th><th>มูลค่า</th><th>กำไร/ขาดทุน (บาท)</th></tr>{prow}</table>{paper_fig}</div>')
    chk = [w for w in (ctx.get("checks") or []) if w["level"] in ("error", "warn")]
    ninfo = sum(1 for w in (ctx.get("checks") or []) if w["level"] == "info")
    if chk or ninfo:
        ps += ('<div class="card"><h2>ตรวจข้อมูลราคา</h2>' + "".join(
            f'<div class="alert {"error" if w["level"]=="error" else "info"}">{"⛔" if w["level"]=="error" else "⚠️"} {html.escape(w["msg"])}</div>' for w in chk)
            + f'<p class="foot">ข้อสังเกตเก่า/รู้แล้ว {ninfo} รายการ (ดูทั้งหมด: python run.py check)</p></div>')
    css = """body{font-family:Tahoma,'Sarabun',sans-serif;background:#f1f5f9;margin:0;color:#0f172a}
.wrap{max-width:1200px;margin:auto;padding:18px}h1{margin:4px 0}h2{margin:0 0 10px;font-size:19px}
.card{background:#fff;border-radius:14px;padding:16px 18px;margin:14px 0;box-shadow:0 1px 3px #0002}
.b{color:#fff;border-radius:999px;padding:3px 12px;font-size:14px;white-space:nowrap}
.reg{font-size:26px;font-weight:bold;color:#fff;border-radius:12px;padding:10px 18px;display:inline-block}
.alert{border-radius:10px;padding:12px 16px;margin:8px 0;font-size:17px;font-weight:bold}
.alert.due{background:#fef3c7;border:2px solid #f59e0b}.alert.regime{background:#fee2e2;border:2px solid #ef4444}
.alert.error{background:#fee2e2;border:2px solid #b91c1c}.alert.info{background:#e0f2fe;border:1px solid #38bdf8;font-weight:normal}.alert.ok{background:#dcfce7}
table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left}
th{background:#f8fafc}tr.pick{background:#f0fdf4}.kpis{display:flex;gap:12px;flex-wrap:wrap}
.kpi{flex:1;min-width:170px;background:#fff;border-radius:14px;padding:14px;box-shadow:0 1px 3px #0002}
.kt{color:#64748b;font-size:13px}.kv{font-size:26px;font-weight:bold}.ks{color:#64748b;font-size:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:900px){.grid{grid-template-columns:1fr}}
.foot{color:#64748b;font-size:12px}"""
    doc = f"""<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HitRun TH V3</title><style>{css}</style></head><body><div class="wrap">
<h1>📈 HitRun TH V3 — แดชบอร์ดรายเดือน</h1><div class="foot">ข้อมูลล่าสุด {stat['date']} · สร้างเมื่อ {ctx['generated']}</div>
<div class="card">{alerts_html}</div>
<div class="card"><h2>สภาวะตลาดตอนนี้</h2><span class="reg" style="background:{reg_col}">{reg_lab}</span>
<p>SET {ctx['set_close']:,.2f} vs {cfg.ma_type}{cfg.ma_days} {ctx['set_ma']:,.2f} → {_badge(ctx['set_up'],'เหนือเส้น ✓','ต่ำกว่าเส้น ✗')}
&nbsp;&nbsp; {ctx.get('gold_label','ทอง')} {ctx['gold_close']:,.2f} บาท vs {ctx['gold_ma']:,.2f} → {_badge(ctx['gold_up'],'เหนือเส้น ✓','ต่ำกว่าเส้น ✗')}</p></div>
<div class="card"><h2>🛒 รายการที่ต้องทำเดือนนี้ (ปรับพอร์ตที่ราคาปิดวันทำการสุดท้ายของเดือน)</h2>
<p>มูลค่าพอร์ตที่ใช้คำนวณ: <b>{stat['equity']:,.0f}</b> บาท · ตัวละ ~{stat['equity']/cfg.top_n:,.0f} บาท · ปัดล็อต {cfg.lot_size} หุ้น</p>
<table><tr><th>สินทรัพย์</th><th>คำสั่ง</th><th>ถืออยู่</th><th>เป้าหมาย</th><th>ซื้อ/ขาย</th><th>ราคาปิดล่าสุด</th><th>มูลค่า (บาท)</th></tr>{rows}</table></div>
<div class="kpis">{kpis}</div>
<div class="card">{figs[0]}</div>
<div class="grid"><div class="card">{figs[1]}</div><div class="card">{figs[2]}</div></div>
<div class="grid"><div class="card"><h2>อันดับโมเมนตัม 12 เดือน (Top 15)</h2><table><tr><th>#</th><th>หุ้น</th><th>12 เดือน</th><th>ราคา</th><th></th></tr>{rank_rows}</table></div>
<div class="card">{figs[3]}</div></div>
{ps}
<div class="card foot"><b>ข้อควรระวัง:</b> {'<br>'.join(html.escape(c) for c in ctx['caveats'])}</div>
</div></body></html>"""
    p = os.path.join(OUT, "dashboard.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(doc)
    return p
