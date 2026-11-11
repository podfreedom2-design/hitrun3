"""ส่งข้อความ Telegram ผ่าน Bot API (ไม่ต้องติดตั้งไลบรารีเพิ่ม)
ใช้ env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (ถ้าไม่มี -> พิมพ์ข้อความออกจอแทน = dry-run)
ลิงก์แดชบอร์ด: env DASHBOARD_URL หรือ config.json "dashboard_url" """
from __future__ import annotations
import json, os, urllib.parse, urllib.request

MAX_LEN = 4000  # Telegram จำกัด 4096 ตัวอักษร/ข้อความ


def dashboard_url(cfg=None) -> str:
    return (os.environ.get("DASHBOARD_URL") or (getattr(cfg, "dashboard_url", None) if cfg else None) or "").strip()


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _chunks(text: str):
    while len(text) > MAX_LEN:
        cut = text.rfind("\n", 0, MAX_LEN)
        cut = cut if cut > 0 else MAX_LEN
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


def send(text: str, cfg=None, dry_run: bool = False) -> bool:
    """คืน True ถ้าส่งสำเร็จ (หรือ dry-run พิมพ์แล้ว) — ไม่ raise ออกไป"""
    url = dashboard_url(cfg)
    if url and url not in text:
        text = f"{text}\n\n📊 แดชบอร์ด: {url}"
    if dry_run or not configured():
        print("----- [Telegram dry-run] -----")
        print(text)
        print("------------------------------")
        return True
    tok, chat = os.environ["TELEGRAM_BOT_TOKEN"].strip(), os.environ["TELEGRAM_CHAT_ID"].strip()
    ok = True
    for part in _chunks(text):
        body = urllib.parse.urlencode({"chat_id": chat, "text": part, "disable_web_page_preview": "true"}).encode()
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", body, timeout=20) as r:
                ok &= bool(json.loads(r.read().decode()).get("ok"))
        except Exception as e:  # noqa — ห้ามพิมพ์ token
            msg = str(e).replace(tok, "***")
            print(f"  [telegram] ส่งไม่สำเร็จ: {type(e).__name__}: {msg}")
            ok = False
    if ok:
        print("  [telegram] ส่งข้อความแล้ว")
    return ok
