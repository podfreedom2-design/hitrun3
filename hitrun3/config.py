"""โหลดค่าตั้งจาก config.json ที่เดียว"""
from __future__ import annotations
import json, os
from dataclasses import dataclass, asdict, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PRICES = os.path.join(DATA, "prices")
OUT = os.path.join(ROOT, "out")
STATE = os.path.join(DATA, "paper_state.json")


@dataclass
class Config:
    capital: float = 120000
    top_n: int = 5
    lookback_days: int = 252
    ma_days: int = 200
    ma_type: str = "SMA"
    lot_size: int = 100
    market_symbol: str = "^SET.BK"
    gold_symbol: str = "GLD"
    gold_currency: str = "USD"
    fx_symbol: str = "THB=X"
    gold_source: str = "THGOLD"          # THGOLD = ทองคำแท่ง 96.5% บาท/บาททองคำ (สมาคมค้าทองคำ) | GLD = แบบเดิม
    gold_spread_thb: float = 200.0       # ส่วนต่างรับซื้อ-ขายออก ต่อ 1 บาททองคำ (หักตอนขาย)
    gold_fee_thb: float = 5.0            # ค่าธรรมเนียมธนาคารต่อรายการซื้อ (Gold Now/ออม NOW 3-5 บาท)
    gold_unit_step: float = 0.0001       # หน่วยซื้อทองขั้นต่ำ (บาททองคำ) — ออม NOW ซื้อเป็นเศษได้
    cost_thai: float = 0.0035
    cost_foreign: float = 0.0045
    cash_rate: float = 0.015             # ดอกเบี้ยเงินสด/กองทุนตลาดเงิน ต่อปี (ใช้ในโหมด realistic เท่านั้น)
    dividend_tax: float = 0.10           # ภาษีปันผลหัก ณ ที่จ่าย (โหมด realistic)
    universe_file: str = "data/universe.txt"
    backtest_start: str | None = None
    backtest_end: str | None = None
    notify_hook: str | None = None
    console_lang: str = "auto"           # auto | th | en (คอนโซล cmd เก่าแสดงไทยเป็นกล่อง → auto ใช้อังกฤษ)
    dashboard_url: str | None = None     # ลิงก์ GitHub Pages (env DASHBOARD_URL มาก่อน)
    alert_ma_band: float = 0.015         # เตือนเมื่อ SET/ทอง ห่างเส้น SMA ไม่เกิน 1.5%
    alert_days_before_month_end: int = 3 # เตือนช่วง N วันทำการสุดท้ายของเดือน
    stale_days: int = 4                  # ข้อมูลเก่าเกิน N วันทำการ = แจ้งปัญหา
    # --- ตรวจข้อมูล / การป้องกัน (เพิ่ม 2026-11-11) ---
    jump_threshold: float = 0.35         # ราคาเปลี่ยน > 35%/วัน = ผิดปกติ (ตลาดไทยจำกัด ±30%)
    set_max_lag_bars: int = 1            # ดัชนี SET ขาดเกิน N แท่ง (เทียบแท่งล่าสุดของหุ้น) = ข้อมูลเก่า → ถือของเดิม ไม่ปรับพอร์ต
    corrections_file: str = "data/corrections.csv"   # แก้ราคาเอง (ควบรวม/แตกพาร์/แท่งเสีย)
    set_div_yield: float = 0.032         # ปันผล SET เฉลี่ยต่อปี ใช้ทำ benchmark "SET TR (ประมาณ)"
    unadj_max_age_days: int = 7          # ข้อมูลราคาไม่ปรับปันผล (โหมด realistic) ดึงใหม่ทุก N วัน
    # --- พอร์ตจำลอง ---
    paper_book_local: bool = True        # False = ให้ GitHub Actions ลงยอดอย่างเดียว (เครื่องนี้ดูสถานะอย่างเดียว)
    # --- จักรวาลหุ้นย้อนหลัง (survivorship) ---
    membership_file: str = "data/membership.csv"     # sym,index,start,end (ยังไม่มีข้อมูลจริง)
    use_membership: bool = False
    universe: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def path_of(p: str) -> str:
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def read_universe(path: str) -> list[str]:
    syms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0]
            syms += [s.strip().upper().replace(".BK", "") for s in line.split() if s.strip()]
    return list(dict.fromkeys(syms))


def load(path: str | None = None) -> Config:
    path = path or os.path.join(ROOT, "config.json")
    d = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    cfg = Config(**{k: v for k, v in d.items() if k in Config.__dataclass_fields__})
    up = cfg.universe_file if os.path.isabs(cfg.universe_file) else os.path.join(ROOT, cfg.universe_file)
    if not cfg.universe and os.path.exists(up):
        cfg.universe = read_universe(up)
    return cfg
