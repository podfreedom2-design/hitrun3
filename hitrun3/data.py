"""ดึงและโหลดราคา (yfinance, period=max, auto_adjust=True = รวมปันผล/แตกพาร์)"""
from __future__ import annotations
import os
import pandas as pd
from .config import PRICES, Config



def _ascii_ca():
    """curl (yfinance/curl_cffi) อ่าน CA ไม่ได้ถ้า path มีภาษาไทย -> คัดลอก cacert.pem ไปที่ path ASCII"""
    try:
        import certifi, shutil
        src = certifi.where()
        if src.isascii():
            return
        d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "hitrun3")
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, "cacert.pem")
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
        if dst.isascii():
            certifi.where = lambda: dst
            for k in ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
                os.environ.setdefault(k, dst)
    except Exception:  # noqa
        pass


_ascii_ca()

def _fname(sym: str) -> str:
    # ต่อท้าย _D1 เพราะ Windows ห้ามชื่อไฟล์ COM7 / CON / PRN ฯลฯ
    return os.path.join(PRICES, sym.replace("^", "IDX_").replace("=", "_") + "_D1.csv")


def _read(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    dc = next(c for c in df.columns if c.lower() in ("date", "datetime", "time", "timestamp"))
    d = pd.to_datetime(df[dc], errors="coerce", utc=False)
    if getattr(d.dt, "tz", None) is not None:
        d = d.dt.tz_localize(None)
    df = df.drop(columns=[dc])
    df.columns = [c.lower() for c in df.columns]
    df.index = d.dt.normalize()
    df.index.name = "date"
    df = df[~df.index.isna()]
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    return df[keep].astype(float).sort_index()


def merge_save(sym: str, new: pd.DataFrame) -> pd.DataFrame:
    """รวมกับไฟล์เดิม (ข้อมูลใหม่ทับวันซ้ำ) — กัน Yahoo ส่งข้อมูลสั้นผิดปกติมาทับของดี"""
    p = _fname(sym)
    if os.path.exists(p):
        old = _read(p)
        new = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
    new.index.name = "date"
    new.to_csv(p)
    return new


def import_csv(sym: str, path: str) -> pd.DataFrame:
    """นำเข้า CSV ภายนอก (เช่น export จาก TradingView) คอลัมน์ date/datetime/time + open,high,low,close"""
    os.makedirs(PRICES, exist_ok=True)
    return merge_save(sym, _read(path))


WSJ_SET_URL = ("https://www.wsj.com/market-data/quotes/index/TH/XBKK/SET/historical-prices/download"
               "?num_rows=20000&range_days=20000&startDate=01/01/1975&endDate={end}")


def fetch_wsj_set() -> pd.DataFrame:
    """ดัชนี SET รายวันจาก WSJ (CSV สาธารณะ, ตั้งแต่ 2008-12-30) — Yahoo ^SET.BK ส่งมาแค่ 1 แท่ง"""
    import io, urllib.request
    url = WSJ_SET_URL.format(end=pd.Timestamp.today().strftime("%m/%d/%Y"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130"})
    txt = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    df = pd.read_csv(io.StringIO(txt), skipinitialspace=True)
    df.columns = [c.strip().lower() for c in df.columns]
    df.index = pd.to_datetime(df.pop("date"), format="%m/%d/%y")
    df.index.name = "date"
    df = df[["open", "high", "low", "close"]].astype(float).sort_index()
    df["volume"] = 0.0
    if len(df) < 250:
        raise ValueError(f"WSJ ส่งมาแค่ {len(df)} แท่ง")
    return df


def fetch_cnbc_set() -> pd.DataFrame:
    """ดัชนี SET รายวันย้อนหลัง ~2 ปี จาก CNBC (.SETI) — สำรองเมื่อ WSJ บล็อก"""
    import json, urllib.request
    req = urllib.request.Request("https://ts-api.cnbc.com/harmony/app/charts/1Y.json?symbol=.SETI",
                                 headers={"User-Agent": "Mozilla/5.0"})
    bars = json.loads(urllib.request.urlopen(req, timeout=60).read())["barData"]["priceBars"]
    df = pd.DataFrame(bars)
    df.index = pd.to_datetime(df["tradeTime"].str[:8], format="%Y%m%d")
    df.index.name = "date"
    df = df[["open", "high", "low", "close"]].astype(float).sort_index()
    df["volume"] = 0.0
    if len(df) < 200:
        raise ValueError(f"CNBC ส่งมาแค่ {len(df)} แท่ง")
    return df


def fetch_set_index() -> tuple:
    errs = []
    for name, fn in (("WSJ", fetch_wsj_set), ("CNBC", fetch_cnbc_set)):
        try:
            return fn(), name
        except Exception as e:  # noqa
            errs.append(f"{name}: {e}")
    raise RuntimeError("; ".join(errs))


THGOLD = "THGOLD"
BAHT_WEIGHT_FACTOR = 15.244 * 0.965 / 31.1035   # 1 บาททองคำ 96.5% = 15.244 g × 0.965 ทองบริสุทธิ์ / 31.1035 g ต่อ oz


def thai_gold_from_usd(usd_per_oz, usd_thb, premium: float = 0.001):
    """ราคาทองแท่ง 96.5% (บาท/บาททองคำ) แบบสังเคราะห์จาก spot USD/oz × USDTHB (premium เฉลี่ยจริง ~0.1%)"""
    return usd_per_oz * usd_thb * BAHT_WEIGHT_FACTOR * (1 + premium)


GTA_URL = "https://www.goldtraders.or.th/api/GoldPricesDaily/pricechanges?StartDate={s}&EndDate={e}"


def fetch_gta_gold(start_year: int = 2006) -> pd.DataFrame:
    """ราคาประกาศสมาคมค้าทองคำ (ทุกครั้งที่ประกาศ) → รายวัน: close = ทองคำแท่งขายออก ณ ประกาศสุดท้ายของวัน"""
    import json, urllib.request
    rows = []
    for y in range(start_year, pd.Timestamp.today().year + 1):
        req = urllib.request.Request(GTA_URL.format(s=f"{y}-01-01", e=f"{y}-12-31"), headers={"User-Agent": "Mozilla/5.0"})
        j = json.loads(urllib.request.urlopen(req, timeout=120).read())
        if isinstance(j, list):
            rows += j
    if not rows:
        raise ValueError("สมาคมค้าทองคำไม่ส่งข้อมูล")
    d = pd.DataFrame(rows)
    d = d[(d["bL_SellPrice"] > 0) & (d["bL_BuyPrice"] > 0)]
    d["t"] = pd.to_datetime(d["asTime"])
    d = d.sort_values(["t", "seq"])
    d["date"] = d["t"].dt.normalize()
    g = d.groupby("date").agg(open=("bL_SellPrice", "first"), high=("bL_SellPrice", "max"),
                              low=("bL_SellPrice", "min"), close=("bL_SellPrice", "last"))
    g["volume"] = 0.0
    g.index.name = "date"
    return g.astype(float)


def fetch_thai_gold(cfg: Config) -> tuple:
    """คืน (DataFrame, แหล่ง) — ใช้ของจริงจากสมาคมฯ ก่อน, ถ้าล้มเหลวใช้สังเคราะห์ GC=F × THB=X เฉพาะวันที่ยังไม่มี"""
    p = _fname(THGOLD)
    start = 2006
    if os.path.exists(p):
        start = max(2006, _read(p).index[-1].year)
    try:
        return fetch_gta_gold(start), "สมาคมค้าทองคำ"
    except Exception as e:  # noqa
        import yfinance as yf
        print(f"  WARN THGOLD: สมาคมค้าทองคำล้มเหลว ({e}) — ใช้ราคาสังเคราะห์ GC=F × THB=X")
        def _c(t):
            x = yf.download(t, period="2y", auto_adjust=True, progress=False, threads=False)["Close"]
            x = x.iloc[:, 0] if isinstance(x, pd.DataFrame) else x
            x.index = pd.to_datetime(x.index).tz_localize(None).normalize()
            return x
        s = thai_gold_from_usd(_c("GC=F"), _c(cfg.fx_symbol)).dropna()
        if os.path.exists(p):
            s = s[s.index > _read(p).index[-1]]
        df = pd.DataFrame({"open": s, "high": s, "low": s, "close": s, "volume": 0.0})
        df.index.name = "date"
        return df, "สังเคราะห์ GC=F×THB"


def _quiet():
    """ปิด warning/log ของ yfinance+pandas (Pandas4Warning, cookie/crumb) — เราพิมพ์สถานะเองแทน"""
    import contextlib, io, logging, warnings
    for n in ("yfinance", "peewee", "urllib3", "curl_cffi"):
        logging.getLogger(n).setLevel(logging.CRITICAL)
        logging.getLogger(n).propagate = False
    @contextlib.contextmanager
    def cm():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                yield
    return cm()


def _yf_one(yt: str, start=None, tries: int = 3) -> pd.DataFrame:
    import time
    with _quiet():
        import yfinance as yf
    last = None
    for k in range(tries):
        try:
            with _quiet():
                t = yf.Ticker(yt)
                df = (t.history(start=start.strftime("%Y-%m-%d"), auto_adjust=True, raise_errors=True)
                      if start is not None else t.history(period="max", auto_adjust=True, raise_errors=True))
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.rename(columns=str.lower)
            if df.empty or "close" not in df:
                raise ValueError("Yahoo returned no data")
            idx = pd.to_datetime(df.index).tz_localize(None).normalize()
            act = pd.Series(0.0, index=idx)
            for c in ("dividends", "stock splits"):
                if c in df:
                    act = act + pd.Series(df[c].fillna(0).values, index=idx).abs()
            df = df[["open", "high", "low", "close", "volume"]]
            df.index = idx
            df = df.dropna(subset=["close"])
            df.attrs["action_dates"] = list(act[act > 0].index)
            return df
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"{type(last).__name__}: {str(last)[:120] or 'no detail'}")


def fetch(cfg: Config, verbose: bool = True) -> dict:
    """ดึงแบบต่อยอด (จากวันล่าสุดในไฟล์ − 10 วัน) แทน period=max; GLD/THB=X ดึงเฉพาะเมื่อ gold_source=GLD"""
    os.makedirs(PRICES, exist_ok=True)
    report, errs = {}, []
    if cfg.gold_source.upper() == THGOLD:
        try:
            new, src = fetch_thai_gold(cfg)
            df = merge_save(THGOLD, new) if len(new) else _read(_fname(THGOLD))
            report[THGOLD] = (str(df.index[0].date()), str(df.index[-1].date()), len(df))
            print(f"  OK  ทองคำแท่ง 96.5% ({src}) -> {report[THGOLD][1]}  {df['close'].iloc[-1]:,.0f} บาท/บาททองคำ")
        except Exception as e:  # noqa
            report[THGOLD] = ("ERROR", str(e), 0); print(f"  ERR THGOLD: {type(e).__name__}: {e}")
    try:
        new, src = fetch_set_index()
        df = merge_save(cfg.market_symbol, new)
        report[cfg.market_symbol] = (str(df.index[0].date()), str(df.index[-1].date()), len(df))
        print(f"  OK  SET ({src}) -> {report[cfg.market_symbol][1]}  {df['close'].iloc[-1]:,.2f}")
    except Exception as e:  # noqa
        print(f"  WARN SET: WSJ/CNBC {type(e).__name__} -> Yahoo")
        try:
            df = merge_save(cfg.market_symbol, _yf_one(cfg.market_symbol))
            report[cfg.market_symbol] = (str(df.index[0].date()), str(df.index[-1].date()), len(df))
        except Exception as e2:  # noqa
            print(f"  ERR SET: {e2}")
    tickers = {s: s + ".BK" for s in cfg.universe}
    if cfg.gold_source.upper() != THGOLD:
        tickers[cfg.gold_symbol] = cfg.gold_symbol
        tickers[cfg.fx_symbol] = cfg.fx_symbol
    n_ok, last = 0, None
    for sym, yt in tickers.items():
        p = _fname(sym)
        old_last = _read(p).index[-1] if os.path.exists(p) else None
        start = (old_last - pd.Timedelta(days=10)) if old_last is not None else None
        try:
            chunk = _yf_one(yt, start)
            # มีปันผล/แตกพาร์ใหม่ -> Yahoo ปรับราคาย้อนหลังทั้งชุด; ดึงต่อยอดจะทำให้เกิดรอยต่อปลอม -> ดึงใหม่ทั้งหมด
            if old_last is not None and any(d > old_last for d in chunk.attrs.get("action_dates", [])):
                print(f"  ... {sym}: มีปันผล/แตกพาร์ใหม่ ดึงประวัติใหม่ทั้งชุด")
                chunk = _yf_one(yt, None)
            df = merge_save(sym, chunk)
            report[sym] = (str(df.index[0].date()), str(df.index[-1].date()), len(df))
            n_ok += 1
            last = max(last or df.index[-1], df.index[-1])
        except Exception as e:  # noqa
            report[sym] = ("ERROR", str(e), 0)
            errs.append(sym)
            print(f"  ERR {sym}: {e}")
            if len(errs) >= 3 and n_ok == 0 and len({report[x][1] for x in errs[-3:]}) == 1:
                rest = [x for x in tickers if x not in report]
                errs += rest
                print(f"  ERR ข้ามที่เหลือ {len(rest)} ตัว (ผิดพลาดแบบเดียวกันซ้ำ) — ใช้ข้อมูลเดิมในไฟล์")
                break
    print(f"  OK  หุ้น/อื่นๆ {n_ok}/{len(tickers)} ตัว ข้อมูลล่าสุด {last.date() if last is not None else '-'}"
          + (f"  (ล้มเหลว: {', '.join(errs)})" if errs else ""))
    try:
        fetch_unadj(cfg)
    except Exception as e:  # noqa — ไม่กระทบสัญญาณหลัก
        print(f"  WARN ราคาไม่ปรับปันผล (realistic): {type(e).__name__}: {e}")
    return report


# ---------- แก้ราคาเอง (corporate actions / แท่งเสีย) ----------
_CORR = None


def load_corrections(cfg: Config | None = None) -> pd.DataFrame:
    """data/corrections.csv: sym,action,date,value,note
    action = scale_before (คูณราคาทุกแท่งก่อน date ด้วย value) | drop (ลบแท่ง date) | set_close (ตั้งราคาปิด date = value)
             | ack_jump (ราคากระโดดวันนั้นเป็นของจริง ไม่ต้องเตือน — ไม่แก้ราคา)"""
    global _CORR
    from .config import path_of
    p = path_of(getattr(cfg, "corrections_file", None) or "data/corrections.csv")
    if not os.path.exists(p):
        return pd.DataFrame(columns=["sym", "action", "date", "value", "note"])
    if _CORR is not None and _CORR[0] == (p, os.path.getmtime(p)):
        return _CORR[1]
    c = pd.read_csv(p, dtype={"sym": str, "action": str})
    c["sym"] = c["sym"].str.strip().str.upper()
    c["action"] = c["action"].str.strip().str.lower()
    c["date"] = pd.to_datetime(c["date"])
    _CORR = ((p, os.path.getmtime(p)), c)
    return c


def apply_corrections(sym: str, s: pd.Series, cfg: Config | None = None) -> pd.Series:
    c = load_corrections(cfg)
    c = c[c["sym"] == sym.upper().replace(".BK", "")]
    s = s.copy()
    for _, r in c.iterrows():
        if r["action"] == "scale_before":
            s[s.index < r["date"]] *= float(r["value"])
        elif r["action"] == "drop":
            s = s[s.index != r["date"]]
        elif r["action"] == "set_close" and r["date"] in s.index:
            s[r["date"]] = float(r["value"])
    return s


def load_close(sym: str, cfg: Config | None = None, corrected: bool = True) -> pd.Series | None:
    """ราคาปิด; corrected=True: ใช้ corrections.csv และทิ้งราคา <= 0 (ข้อมูลเสีย)"""
    p = _fname(sym)
    if not os.path.exists(p):
        return None
    s = _read(p)["close"].astype(float)
    s = s[~s.index.duplicated()].sort_index()
    if corrected:
        s = apply_corrections(sym, s, cfg)
        s = s[s > 0]
    return s


# ---------- ตรวจข้อมูล ----------
LAST_HEALTH: dict = {}


def validate(cfg: Config, raw: dict | None = None, panel_last=None, recent_bars: int = 10) -> list[dict]:
    """คืนรายการคำเตือนข้อมูล [{level, sym, kind, msg}]
    level: 'error' = กระทบสัญญาณตอนนี้ | 'warn' = ผิดปกติช่วงล่าสุด/ในช่วง backtest | 'info' = เก่ามาก/รู้แล้ว"""
    out = []
    jt = float(getattr(cfg, "jump_threshold", 0.35))
    bt0 = pd.Timestamp(cfg.backtest_start or "2012-01-01")
    win0 = bt0 - pd.Timedelta(days=int(cfg.lookback_days * 1.5))     # ช่วงที่ backtest ใช้คำนวณโมเมนตัม
    syms = list(cfg.universe) + [cfg.market_symbol] + ([THGOLD] if cfg.gold_source.upper() == THGOLD else [cfg.gold_symbol])
    raw = raw or {}
    series = {}
    for s in syms:
        r = raw.get(s)
        if r is None:
            p = _fname(s)
            if not os.path.exists(p):
                out.append({"level": "error" if s in (cfg.market_symbol, THGOLD) else "warn", "sym": s, "kind": "missing",
                            "msg": f"{s}: ไม่มีไฟล์ราคา"})
                continue
            r = _read(p)["close"].astype(float)
            r = r[~r.index.duplicated()].sort_index()
        nonpos = r[r <= 0]
        if len(nonpos):
            recent = nonpos[nonpos.index >= win0]
            lvl = "warn" if len(recent) else "info"
            out.append({"level": lvl, "sym": s, "kind": "nonpositive",
                        "msg": f"{s}: ราคา <= 0 จำนวน {len(nonpos)} แท่ง ({nonpos.index[0].date()}..{nonpos.index[-1].date()}) — ตัดทิ้งแล้ว"})
        c = load_close(s, cfg) if s not in raw else apply_corrections(s, r[r > 0], cfg)
        series[s] = c
        if c is None or not len(c):
            continue
        ret = c.pct_change()
        jumps = ret[(ret.abs() > jt) & (c.index >= win0)]
        cc = load_corrections(cfg)
        ack = set(cc[(cc["sym"] == s) & (cc["action"] == "ack_jump")]["date"])
        if ack:
            ok = jumps[jumps.index.isin(ack)]
            if len(ok):
                out.append({"level": "info", "sym": s, "kind": "jump_ack",
                            "msg": f"{s}: ราคาเปลี่ยนแรงที่ตรวจแล้วว่าเป็นของจริง " + ", ".join(f"{d.date()} {v*100:+.0f}%" for d, v in ok.items())})
            jumps = jumps[~jumps.index.isin(ack)]
        if len(jumps):
            lst = ", ".join(f"{d.date()} {v*100:+.0f}%" for d, v in jumps.head(4).items())
            recent = jumps.index[-1] >= c.index[max(0, len(c) - recent_bars)]
            out.append({"level": "error" if recent else "warn", "sym": s, "kind": "jump",
                        "msg": f"{s}: ราคาเปลี่ยนเกิน {jt*100:.0f}%/วัน {len(jumps)} ครั้ง ({lst}) — ตรวจ corporate action แล้วเพิ่มใน corrections.csv"})
        old_j = ret[(ret.abs() > jt) & (c.index < win0)]
        if len(old_j):
            out.append({"level": "info", "sym": s, "kind": "jump_old",
                        "msg": f"{s}: ราคากระโดด >{jt*100:.0f}% {len(old_j)} ครั้งก่อน {win0.date()} (ไม่กระทบ backtest)"})
        if s in cfg.universe and c.index[0] > bt0:
            out.append({"level": "info", "sym": s, "kind": "late_start",
                        "msg": f"{s}: ประวัติเริ่ม {c.index[0].date()} (หลังเริ่ม backtest) — เข้าคำนวณโมเมนตัมได้ตั้งแต่ ~{(c.index[0] + pd.Timedelta(days=int(cfg.lookback_days*1.45))).date()}"})
    # ข้อมูลค้าง (stale) เทียบแท่งล่าสุดของทั้งชุด
    lasts = {s: v.index[-1] for s, v in series.items() if v is not None and len(v)}
    if lasts:
        ref = pd.Timestamp(panel_last) if panel_last is not None else max(lasts.values())
        for s, d in lasts.items():
            lag = len(pd.bdate_range(d, ref)) - 1
            core = s in (cfg.market_symbol, THGOLD, cfg.gold_symbol)
            lim = int(getattr(cfg, "set_max_lag_bars", 1)) if s == cfg.market_symbol else int(getattr(cfg, "stale_days", 4))
            if lag > lim or (core and lag > 0):
                out.append({"level": "error" if (core and lag > lim) else "warn", "sym": s, "kind": "stale",
                            "msg": f"{s}: ข้อมูลล่าสุด {d.date()} ช้ากว่าแท่งล่าสุด {ref.date()} อยู่ {lag} วันทำการ (ระบบเติมราคาเดิมให้ — ระวัง)"})
        # หุ้นราคานิ่งไม่มีวอลุ่มต่อเนื่องปลายข้อมูล = อาจถูกพักการซื้อขาย (SP)
        for s in cfg.universe:
            p = _fname(s)
            if s in lasts and os.path.exists(p):
                v = _read(p).tail(5)
                if len(v) == 5 and (v["volume"].fillna(0) == 0).all() and v["close"].nunique() == 1:
                    out.append({"level": "warn", "sym": s, "kind": "suspended",
                                "msg": f"{s}: 5 แท่งล่าสุดราคานิ่ง วอลุ่ม 0 — อาจถูกพักซื้อขาย (SP)"})
    return out


def load_panel(cfg: Config, corrections: bool = True):
    """คืน (หุ้นไทย DataFrame, ดัชนี SET Series, ทองเป็นบาท Series) วางบนปฏิทินวันทำการไทย
    corrections=False = ข้อมูลดิบแบบเดิม (โหมด legacy เพื่อเทียบผล)
    D.LAST_HEALTH: set_fresh (Series bool: SET มีข้อมูลจริงไม่เกิน set_max_lag_bars แท่ง), last_dates, ffill_tail"""
    th = {s: load_close(s, cfg, corrected=corrections) for s in cfg.universe}
    th = {k: v for k, v in th.items() if v is not None and len(v)}
    if not th:
        raise SystemExit("ไม่มีข้อมูลหุ้น — รัน: python run.py fetch")
    T0 = pd.DataFrame(th).sort_index()
    idx = T0.index
    T = T0.ffill()

    def align(s):
        if s is None:
            return pd.Series(index=idx, dtype=float)
        return s.reindex(idx.union(s.index)).ffill().reindex(idx)

    mraw = load_close(cfg.market_symbol, cfg, corrected=corrections)
    mkt = align(mraw)
    lag = int(getattr(cfg, "set_max_lag_bars", 1))
    if mraw is not None and len(mraw):
        has = pd.Series(idx.isin(mraw.index), index=idx).astype(float).replace(0, float("nan"))
        set_fresh = has.ffill(limit=lag).notna() & mkt.notna()
    else:
        set_fresh = pd.Series(False, index=idx)
    if cfg.gold_source.upper() == THGOLD:
        graw = load_close(THGOLD, cfg, corrected=corrections)
        gold = align(graw)                        # บาท/บาททองคำ (ทองคำแท่ง 96.5% ขายออก)
    else:
        graw = load_close(cfg.gold_symbol, cfg, corrected=corrections)
        gold = align(graw)
        if cfg.gold_currency.upper() == "USD":
            gold = gold * align(load_close(cfg.fx_symbol, cfg, corrected=corrections))
    tail = T0.tail(20)
    LAST_HEALTH.clear()
    LAST_HEALTH.update(set_fresh=set_fresh, set_last=None if mraw is None or not len(mraw) else mraw.index[-1],
                       gold_last=None if graw is None or not len(graw) else graw.index[-1],
                       last_dates={k: v.index[-1] for k, v in th.items()},
                       ffill_tail={k: int(n) for k, n in tail.isna().sum().items() if n > 0})
    return T, mkt, gold


# ---------- ราคาไม่ปรับปันผล (โหมด realistic) ----------
UNADJ = os.path.join(os.path.dirname(PRICES), "unadj_panel.csv")   # date,sym,close,div,split (ไฟล์เดียว)


def fetch_unadj(cfg: Config, force: bool = False) -> dict:
    """Yahoo ราคาปิดปรับแตกพาร์อย่างเดียว (ไม่รวมปันผล) + ปันผลเงินสด + แตกพาร์ -> data/unadj_panel.csv
    ดึงใหม่เมื่อไฟล์เก่ากว่า unadj_max_age_days วัน (ใช้กับ backtest โหมด realistic เท่านั้น)"""
    import time
    age = int(getattr(cfg, "unadj_max_age_days", 7))
    if not force and os.path.exists(UNADJ) and (time.time() - os.path.getmtime(UNADJ)) < age * 86400:
        return {}
    with _quiet():
        import yfinance as yf
    old = pd.read_csv(UNADJ, parse_dates=["date"]) if os.path.exists(UNADJ) else None
    rows, rep = [], {}
    for s in cfg.universe:
        h = None
        for k in range(3):
            try:
                with _quiet():
                    h = yf.Ticker(s + ".BK").history(start="2010-01-01", auto_adjust=False, actions=True, raise_errors=True)
                break
            except Exception:  # noqa
                h = None
                time.sleep(1.5 * (k + 1))
        if h is None or h.empty:
            rep[s] = "ERROR"
            if old is not None:
                rows.append(old[old["sym"] == s])
            continue
        h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
        rows.append(pd.DataFrame({"date": h.index, "sym": s, "close": h["Close"].values,
                                  "div": h["Dividends"].values if "Dividends" in h else 0.0,
                                  "split": h["Stock Splits"].values if "Stock Splits" in h else 0.0}))
        rep[s] = str(h.index[-1].date())
    if rows:
        tmp = UNADJ + ".tmp"
        pd.concat(rows).to_csv(tmp, index=False)
        os.replace(tmp, UNADJ)
    bad = [k for k, v in rep.items() if v == "ERROR"]
    print(f"  OK  ราคาไม่ปรับปันผล (realistic) อัปเดต {len(rep) - len(bad)}/{len(rep)} ตัว" + (f" ล้มเหลว {bad}" if bad else ""))
    return rep


def load_unadj(cfg: Config, idx: pd.DatetimeIndex):
    """คืน (CL ราคาจริงปรับแตกพาร์, DIV ปันผล/หุ้น (หน่วยเดียวกับ CL), LOTF ตัวคูณล็อต 100 หุ้นจริง) หรือ None"""
    if not os.path.exists(UNADJ):
        return None
    U = pd.read_csv(UNADJ, parse_dates=["date"])
    U = U[U["sym"].isin(cfg.universe)]
    if U.empty:
        return None
    piv = lambda c: U.pivot_table(index="date", columns="sym", values=c, aggfunc="last")
    CL = piv("close")
    for s in CL.columns:
        c = apply_corrections(s, CL[s].dropna(), cfg)
        CL[s] = c[c > 0].reindex(CL.index)
    CL = CL.reindex(idx.union(CL.index)).ffill().reindex(idx)
    DIV = piv("div").fillna(0.0)
    # ปันผลที่ XD ตรงวันที่ไม่มีในปฏิทิน -> เลื่อนไปแท่งถัดไป
    DIV.index = idx[idx.searchsorted(DIV.index).clip(0, len(idx) - 1)]
    DIV = DIV.groupby(level=0).sum().reindex(idx).fillna(0.0)
    SPL = piv("split").fillna(0.0)
    LOTF = pd.DataFrame(1.0, index=idx, columns=CL.columns)
    for s in SPL.columns:
        for d, ratio in SPL[s][SPL[s] > 0].items():
            LOTF.loc[LOTF.index < d, s] *= float(ratio)
    return CL, DIV, LOTF


def load_membership(cfg: Config):
    """data/membership.csv: sym,index,start,end — ช่วงที่หุ้นอยู่ใน SET50/SET100 จริง (end ว่าง = ยังอยู่)
    คืน DataFrame หรือ None ถ้าไม่มีข้อมูล (ตอนนี้ยังไม่มีข้อมูลจริง)"""
    from .config import path_of
    p = path_of(getattr(cfg, "membership_file", "data/membership.csv"))
    if not os.path.exists(p):
        return None
    m = pd.read_csv(p, dtype=str)
    if m.empty:
        return None
    m["sym"] = m["sym"].str.strip().str.upper()
    m["start"] = pd.to_datetime(m["start"])
    m["end"] = pd.to_datetime(m["end"]).fillna(pd.Timestamp("2100-01-01"))
    return m


def member_mask(m, idx: pd.DatetimeIndex, cols) -> pd.DataFrame:
    M = pd.DataFrame(False, index=idx, columns=cols)
    for _, r in m.iterrows():
        if r["sym"] in M.columns:
            M.loc[(M.index >= r["start"]) & (M.index <= r["end"]), r["sym"]] = True
    return M
