# HitRun TH V3 — ระบบ Momentum รายเดือน (หุ้นไทย / ทอง / เงินสด)

โปรเจกต์ใหม่ แยกจาก V2 ทั้งหมด (ไม่ import ไม่แตะไฟล์ V2)

## กติกา (ทำเดือนละครั้ง วันทำการสุดท้ายของเดือน หลังตลาดปิด)
1. ถ้า **SET > SMA200** → ถือหุ้นไทย **5 ตัว** ที่ผลตอบแทน 12 เดือน (252 วันทำการ) สูงสุด และต้อง > 0 ตัวละ 1/5 ปัดล็อต 100 หุ้น
2. ถ้า SET ต่ำกว่าเส้น แต่ **ทอง (GLD แปลงเป็นบาท) > SMA200 ของตัวเอง** → ถือทอง 100%
3. ไม่งั้น → **เงินสด / กองทุนตลาดเงิน**
4. ทบต้น ขายก่อนซื้อ ต้นทุนหุ้นไทย 0.35%/ขา (ค่าคอม 0.15% + slippage 0.2%) ทอง/ต่างประเทศ 0.45%/ขา (รวม FX)

ค่าทั้งหมดแก้ที่ `config.json` · รายชื่อหุ้นแก้ที่ `data/universe.txt`

## ติดตั้งครั้งแรก
ดับเบิลคลิก `SETUP.bat` (หรือ `py -3.11 -m venv .venv` แล้ว `.venv\Scripts\python -m pip install -r requirements.txt`)

## ใช้งาน
| ทำอะไร | คำสั่ง | ปุ่มลัด |
|---|---|---|
| ดึงราคาล่าสุด (yfinance period=max, auto_adjust=True) | `python run.py fetch` | `FETCH.bat` |
| นำเข้าประวัติดัชนี/ราคาจาก CSV (เช่น TradingView) | `python run.py import-csv ^SET.BK ไฟล์.csv` | |
| ดูสัญญาณ + รายการซื้อ/ขายเดือนนี้ | `python run.py signal` | `SIGNAL.bat` |
| ทดสอบย้อนหลัง (+ รายงาน AI + แดชบอร์ด) | `python run.py backtest [--start 2012-07-31 --end 2026-10-30]` | `BACKTEST.bat` |
| ปรับพอร์ตจำลองเดือนนี้ | `python run.py paper` (`--force` ปรับซ้ำ, `--reset` เริ่มใหม่) | `PAPER.bat` |
| สร้าง/เปิดแดชบอร์ด | `python run.py dashboard` | `DASHBOARD.bat` |
| ส่งออกรายงานให้ AI | `python run.py export` | |
| ทดสอบโค้ด | `.venv\Scripts\python -m pytest -q` | |

ใช้ `.venv\Scripts\python.exe` แทน `python` ถ้าไม่ได้ activate venv

### แจ้งเตือน
- ทุกคำสั่งพิมพ์แจ้งเตือนในคอนโซล + เขียน `out/alerts.json` + แถบเด่นบนแดชบอร์ด
- ระดับ `due` = ถึง/เลยวันปรับพอร์ต · `regime` = สภาวะตลาดเปลี่ยน · `info` = ข้อมูลทั่วไป
- LINE Notify ปิดบริการแล้ว จึงไม่ใช้ — มีจุดเสียบ `notify_hook` ใน config (`"โมดูล:ฟังก์ชัน"` รับ list ของ alert) ไว้ต่อ Telegram/อีเมลภายหลัง

## โครงสร้าง
```
run.py              ประตูเดียว (CLI)
config.json         ค่าตั้งทั้งหมด
hitrun3/
  config.py         โหลด config + universe
  data.py           ดึง/โหลดราคา (yfinance) แปลงทองเป็นบาท
  strategy.py       กติกาล้วน: MA, regime, momentum, ปัดล็อต
  engine.py         backtest + rebalance (ใช้ร่วมกับ paper) + metrics
  paper.py          พอร์ตจำลอง + action list + alerts
  report.py         ai_report.json / .md / CSV
  dashboard.py      HTML ไฟล์เดียว (plotly ฝังในไฟล์ เปิดออฟไลน์ได้)
  notify.py         hook แจ้งเตือนอนาคต
data/universe.txt   รายชื่อหุ้น
data/prices/*.csv   ราคา (date,open,high,low,close,volume)
data/paper_state.json  สถานะพอร์ตจำลอง
out/                ผลลัพธ์ทั้งหมด
tests/              pytest
```

## ไฟล์ส่งออกสำหรับ AI (`out/`)
| ไฟล์ | เนื้อหา |
|---|---|
| `ai_report.json` | รายงานหลัก (schema ด้านล่าง) |
| `ai_report.md` | สรุป Markdown + **prompt สำเร็จรูป** ให้ AI ตัวอื่นวิเคราะห์ต่อ |
| `equity.csv` | date, equity, cash รายวัน |
| `trades.csv` | date, side, sym, shares, price, fee, value, pnl, pnl_pct |
| `holdings.csv` | date, regime, sym, shares (ทุกสิ้นเดือน) |
| `alerts.json` | date, regime, alerts[], actions[] |

### Schema `ai_report.json` (`hitrun3.ai_report.v1`)
```
schema            "hitrun3.ai_report.v1"
strategy          {name, rules[]}
config            ค่าใน config.json + universe[]
period            {start, end, years}
metrics           {start,end,years,start_value,final_value,total_return,cagr,max_drawdown,sharpe,
                   n_trades,n_closed,win_rate,total_fees}       (สัดส่วน เช่น 0.22 = 22%)
benchmarks        {SET:{...metrics}, EW_BH:{...metrics}}      SET = ดัชนีราคา (ไม่รวมปันผล)
per_year_returns  {"2013":0.12, ...}
regime_history    [{date, regime: STOCKS|GOLD|CASH, set_above_ma, gold_above_ma}]
monthly_holdings  [{date, regime, holdings:{sym:shares}}]       GOLD = ทอง
trades            [{date, side, sym, shares, price, fee, value, pnl, pnl_pct}]
current_signal    {date, regime, picks[], set_above_ma, gold_above_ma,
                   ranking_top[{rank,sym,ret12m,close}], actions[{sym,action,current,target,delta,price,value}], alerts[]}
paper_portfolio   {created,cash,holdings{sym:{shares,cost}},trades[],history[{date,equity}],last_rebalance,last_regime} | null
caveats           []
```

## ข้อควรระวัง
- **Survivorship bias**: รายชื่อหุ้นคือหุ้นที่ยังอยู่วันนี้ ผลย้อนหลังดีเกินจริง
- ก่อนมีข้อมูล SET พอคำนวณ SMA200 ระบบถือหุ้นตลอด (ไม่มีตัวกรอง)
- ราคา auto_adjust รวมปันผล (ยังไม่หักภาษี 10% — กระทบ ~0.3%/ปี)
- ส่วนเกินช่วง 2019+ มาจากทองขึ้นแรงเป็นหลัก
- ไม่ใช่คำแนะนำการลงทุน

### หมายเหตุข้อมูลดัชนี SET
ตอนนี้ (พ.ย. 2026) Yahoo ส่งประวัติ `^SET.BK` มาแค่แท่งล่าสุด `fetch` จึง **รวมกับไฟล์เดิม** ไม่เขียนทับ
ประวัติตั้งต้นนำเข้าด้วย `import-csv` (ชุดแรกคัดลอกจาก CSV ของ V2 แบบอ่านอย่างเดียว เริ่ม 2014-06-09) — ถ้ามี CSV จาก TradingView ที่ยาวกว่า นำเข้าซ้ำได้

## แหล่งข้อมูลดัชนี SET (อัปเดต 2026-11-01)
- `fetch` ดึง SET จาก WSJ (CSV สาธารณะ ตั้งแต่ 2008-12-30) ถ้าถูกบล็อกจะใช้ CNBC (.SETI รายวัน ~2 ปี) แล้วรวมกับไฟล์เดิม; ถ้าทั้งสองล้มเหลวจึงใช้ Yahoo
- ประวัติเต็มนำเข้าจาก data/backup/SET_wsj_20081230_20261030.csv; ไฟล์ก่อนแก้สำรองไว้ใน data/backup/


## ทองคำ: ทองคำแท่ง 96.5% (บาท/บาททองคำ) — อัปเดต 2026-11-01
- ค่าเริ่มต้น `gold_source: "THGOLD"` ใช้ราคาประกาศสมาคมค้าทองคำ (API สาธารณะ goldtraders.or.th, ตั้งแต่ 2006-05-01) ราคาปิด = ทองคำแท่ง "ขายออก" ประกาศสุดท้ายของวัน ไฟล์ `data/prices/THGOLD_D1.csv`
- ถ้าดึงไม่ได้ ใช้ราคาสังเคราะห์ GC=F × THB=X × 0.47295 (15.244 g × 0.965 / 31.1035) × 1.001 เฉพาะวันที่ยังขาด
- ต้นทุน: ซื้อเสียค่าธนาคาร `gold_fee_thb` (5 บาท/รายการ) ขายเสียส่วนต่าง `gold_spread_thb` (200 บาท/บาททองคำ) — ซื้อเป็นเศษได้ทีละ `gold_unit_step` (0.0001 บาททองคำ แบบ ออม NOW; GOLD NOW ซื้อขายขั้นต่ำ 5 บาททองคำ)
- กลับไปใช้แบบเดิม: ตั้ง `"gold_source": "GLD"` (ใช้ GLD×THB=X และ cost_foreign)

## วิธีใช้แบบง่าย (อัปเดต 2026-11-01)
- ดับเบิลคลิก **HITRUN.bat** (เมนูหลัก): ดึงราคา → สัญญาณ → พอร์ตจำลอง → สร้างแดชบอร์ด แล้วเปิด out\dashboard.html ในเบราว์เซอร์อัตโนมัติ — ดูทุกอย่างในแดชบอร์ดเป็นหลัก
- SIGNAL.bat / PAPER.bat / BACKTEST.bat / DASHBOARD.bat ก็เปิดแดชบอร์ดให้เมื่อจบ
- จอดำ (cmd) แบบเก่าไม่มีฟอนต์ไทย จะเห็นเป็นกล่อง □ จึงตั้ง `console_lang: auto` = แสดงอังกฤษใน cmd เก่า, ไทยใน Windows Terminal/VS Code; บังคับได้ด้วย `th` / `en` ใน config.json หรือ env HITRUN_LANG
- ทดสอบโดยไม่เปิดเบราว์เซอร์/ไม่ pause: `set HITRUN_NO_OPEN=1` ก่อนรัน .bat

---

## อัปเดต 2026-11-11 (แก้ตามผลตรวจ audit — กติกากลยุทธ์ไม่เปลี่ยน)

**ใช้งาน**
- `HITRUN.bat` = ใช้ทุกวัน: ดึงราคา → สัญญาณ → **สถานะพอร์ตจำลอง (อ่านอย่างเดียว ไม่ลงยอด)** → แดชบอร์ด
- `PAPER.bat` = ลงยอดพอร์ตจำลอง **เฉพาะวันทำการสุดท้ายของเดือน** (รันหลังตลาดปิด) — วันอื่นแค่แสดงสถานะ, รันซ้ำไม่ลงซ้ำ, ถ้าพลาดจะลงย้อนหลังด้วยราคาปิดสิ้นเดือน
- `BACKTEST.bat` = ผล original + realistic + benchmark SET รวมปันผล (ประมาณ)
- `CHECK.bat` = ตรวจข้อมูลราคา, `SENSITIVITY.bat` = ทดสอบความทนทาน (out/sensitivity.md)

**สิ่งที่แก้**
1. พอร์ตจำลอง: รีเซ็ตกลับเป็นสถานะสิ้นเดือน 2026-10-30 (ไฟล์ที่ขายผิดกลางเดือนเก็บไว้ที่ `data/backup/paper_state_WRONG_midmonth_sell_20261109.json`); ลงยอดได้เฉพาะวันปรับพอร์ต; ไม่บันทึกมูลค่ารายวัน
   - ถ้าเปิดใช้ GitHub Actions แล้ว ตั้ง `"paper_book_local": false` ใน config.json เพื่อให้ Actions เป็นผู้ลงยอดคนเดียว (กันไฟล์ชนกัน)
2. ตรวจข้อมูล: ราคา ≤ 0 (ตัดทิ้ง), เปลี่ยน > 35%/วัน, ประวัติเริ่มช้า, หุ้น/ทอง/SET ข้อมูลค้าง, หุ้นราคานิ่งวอลุ่ม 0 (อาจ SP) — `data/corrections.csv` แก้ราคาเอง (TRUE ควบรวม DTAC, SCB แท่งแรก, EA = ของจริง)
   - fetch: ถ้ามีปันผล/แตกพาร์ใหม่ ดึงประวัติหุ้นตัวนั้นใหม่ทั้งชุด (กันรอยต่อราคาปลอม)
3. ข้อมูล SET ขาด/เก่า → สัญญาณ `HOLD` = ถือของเดิม ไม่ปรับพอร์ต + แจ้งเตือน (แดชบอร์ด/Telegram) — เดิมเดาเป็น "ถือหุ้น"
4. Win rate นับแบบไม้ที่ปิดจริง (round trip) + benchmark "SET TR (ประมาณ)" = ดัชนีราคา + ปันผล `set_div_yield` (3.2%/ปี, ไม่ใช่ SET TRI จริง)
5. Backtest โหมด realistic: ราคาจริง (ไม่ปรับปันผล) ล็อต 100 หุ้นจริง, ปันผลเงินสดหักภาษี 10%, ดอกเบี้ยเงินสด `cash_rate` 1.5%/ปี (ข้อมูล `data/unadj_panel.csv` ดึงใหม่ทุก 7 วัน)
6. จักรวาลหุ้นย้อนหลัง: รองรับ `data/membership.csv` (sym,index,start,end) + `"use_membership": true` — **ยังไม่มีข้อมูลจริง** (รายชื่อ SET50/SET100 ย้อนหลังอยู่ใน PDF ของ set.or.th ต้องล็อกอิน และราคาหุ้นที่ถูกถอน/ควบรวมไม่มีใน Yahoo)
7. ทองคิดมูลค่าที่ราคารับซื้อ (หักส่วนต่าง), ซื้อหุ้นตามอันดับโมเมนตัม, รายงาน sensitivity; แท่งกลางเดือนล่าสุดไม่ถูกนับเป็นวันปรับพอร์ตใน backtest อีกต่อไป
