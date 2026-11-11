"""แสดงผลในคอนโซล: บังคับ UTF-8 และถ้าคอนโซลแสดงอักษรไทยไม่ได้ (cmd แบบเก่า) แปลข้อความเป็นอังกฤษ
console_lang: "auto" (ค่าเริ่มต้น) | "th" | "en" — ตั้งใน config.json หรือ env HITRUN_LANG"""
from __future__ import annotations
import os, re, sys

PHRASES = {
    "ข้ามที่เหลือ": "skipped remaining", "ตัว (ผิดพลาดแบบเดียวกันซ้ำ) — ใช้ข้อมูลเดิมในไฟล์": "(same error repeated) - using cached files",
    "... กำลังคำนวณ backtest ใหม่ (ข้อมูลหรือค่าตั้งเปลี่ยน)": "... recomputing backtest (data/config changed)",
    "ทองคำแท่ง 96.5%": "Thai gold 96.5%", "บาท/บาททองคำ": "THB/baht-weight", "หุ้น/อื่นๆ": "stocks",
    "ตัว ข้อมูลล่าสุด": "symbols, latest", "ล้มเหลว:": "failed:",
    "สัญญาณ ณ": "Signal @", "ถือหุ้นไทย": "HOLD THAI STOCKS", "ถือทองคำ": "HOLD GOLD", "ถือเงินสด": "HOLD CASH",
    "มูลค่าพอร์ตที่ใช้คำนวณ": "Portfolio value used", "มูลค่าพอร์ตจำลอง": "Paper portfolio value",
    "พอร์ตจำลอง ณ": "Paper portfolio @", "เงินสด": "cash", "ถือ": "hold", "เป้า": "target", "บาท": "THB",
    "ปิดไม้": "closed", "ชนะ": "win", "ระบบ": "System", "ปี": "yrs", "เขียน": "wrote", "แดชบอร์ด": "Dashboard",
    "นำเข้า": "imported", "แท่ง": "bars", "ค่าธรรมเนียม": "fee",
    "ล้างพอร์ตจำลองแล้ว (สำรองเดิมไว้ที่ paper_state.json.bak)": "Paper portfolio reset (backup: paper_state.json.bak)",
    "เดือนนี้ปรับแล้ว / ไม่มีรายการ (ใช้ --force ถ้าต้องการปรับซ้ำ)": "Already rebalanced this month / nothing to do (use --force to redo)",
    "ยังไม่ได้เริ่มพอร์ตจำลอง — รัน `python run.py paper` เพื่อเริ่ม": "Paper portfolio not started - run `python run.py paper`",
    "ถึงวันปรับพอร์ตแล้ว": "REBALANCE DAY", "เป็นวันทำการสุดท้ายของเดือน": "is the last trading day of the month",
    "ทำตามรายการซื้อขายด้านล่าง": "follow the orders below", "เลยกำหนดปรับพอร์ต": "Rebalance overdue",
    "ครั้งล่าสุด": "last", "ควรปรับทันที": "rebalance now", "สภาวะตลาดเปลี่ยน": "Regime changed",
    "สัญญาณเปลี่ยนจากพอร์ตปัจจุบัน แต่ยังไม่ถึงวันปรับพอร์ตสิ้นเดือน (ดูไว้ก่อน)": "Signal differs from portfolio, but not month-end yet (watch only)",
    "สมาคมค้าทองคำล้มเหลว": "Gold Traders Assoc. failed", "ใช้ราคาสังเคราะห์": "using synthetic price",
    "สมาคมค้าทองคำ": "GoldTraders", "ล้มเหลว": "failed", "ใช้ Yahoo แทน": "using Yahoo", "ส่งมาแค่": "returned only",
    "นำเข้าประวัติ": "to import history", "ใช้": "use", "เรียก hook ไม่สำเร็จ": "hook call failed",
    "เปิดแดชบอร์ดในเบราว์เซอร์": "Opening dashboard in browser",
}
_KEYS = sorted(PHRASES, key=len, reverse=True)
_THAI = re.compile(r"[\u0E00-\u0E7F]+")


def to_english(s: str) -> str:
    for k in _KEYS:
        if k in s:
            s = s.replace(k, PHRASES[k])
    return _THAI.sub("?", s)


class _EnStream:
    def __init__(self, base):
        self._b = base

    def write(self, s):
        return self._b.write(to_english(s))

    def __getattr__(self, n):
        return getattr(self._b, n)


def wants_english(lang: str | None) -> bool:
    lang = (os.environ.get("HITRUN_LANG") or lang or "auto").lower()
    if lang in ("th", "thai"):
        return False
    if lang in ("en", "english"):
        return True
    # auto: Windows Terminal / VS Code / ไฟล์ (redirect) แสดงไทยได้; cmd/conhost เดิมมักเป็นกล่อง □
    if os.name != "nt" or not sys.stdout.isatty():
        return False
    return not (os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))


def setup(lang: str | None = "auto"):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa
            pass
    if wants_english(lang):
        sys.stdout = _EnStream(sys.stdout)
        sys.stderr = _EnStream(sys.stderr)
