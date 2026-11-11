"""จุดเสียบการแจ้งเตือนในอนาคต (LINE Notify ปิดบริการแล้ว — ไม่ใช้)
ตั้ง config.json -> "notify_hook": "mymodule:func" เพื่อเรียก func(alerts: list[dict]) ของคุณเอง"""
from __future__ import annotations
import importlib


def send(cfg, alerts: list[dict]) -> None:
    if not cfg.notify_hook or not alerts:
        return
    try:
        mod, fn = cfg.notify_hook.split(":")
        getattr(importlib.import_module(mod), fn)(alerts)
    except Exception as e:  # noqa
        print(f"[notify] เรียก hook ไม่สำเร็จ: {e}")
