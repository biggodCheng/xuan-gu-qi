# -*- coding: utf-8 -*-
"""涨停事件后续表现回测 (细化版)。

扫描 .claude/skills/chuangxingao/data/zt_*.json 所有涨停事件 (code, zt_date)，
以涨停日收盘为标尺 + 次日开盘为真实追入价，跟踪 D+1/D+3/D+5/持有至今涨跌，
按 连板高度 / 板块 / 月份 分组。回答"涨停之后表现如何 + 追入能否赚钱"。

口径:
  - close-to-close: 涨停日收盘(封板买不到)→后续收盘, 标尺用
  - 追入口径: 次日开盘买入→后续收盘, 真实可执行(暴露高开成本)

数据源: 本地招商证券 vipdoc (local_kline.read_day, 含OHLC, 零网络)。
用法: python scripts/backtest_zt_performance.py
"""
import glob
import json
import os
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import local_kline  # noqa: E402  本地vipdoc, 含OHLC

_SKILLS = os.path.normpath(os.path.join(_HERE, "..", ".claude", "skills"))
DATA_DIR = os.path.join(_SKILLS, "chuangxingao", "data")
OUT_JSON = os.path.join(_HERE, "zt_performance.json")


def _prefix(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sz"


def limit_of(code: str) -> float:
    if code.startswith(("4", "8", "92")):
        return 0.30
    if code.startswith(("30", "68")):
        return 0.20
    return 0.10


def board_of(code: str) -> str:
    if code.startswith(("4", "8", "92")):
        return "北交"
    if code.startswith("30"):
        return "创业板"
    if code.startswith("68"):
        return "科创板"
    return "主板"


def board_height(code: str, kline: list[dict], zt_idx: int) -> int:
    """从涨停日往回数连续涨停日数(首板=1)。"""
    lim = limit_of(code)
    h, j = 1, zt_idx - 1
    while j >= 1:
        pc, dc = kline[j - 1]["close"], kline[j]["close"]
        if pc <= 0:
            break
        if (dc - pc) / pc >= lim * 0.97:
            h += 1
            j -= 1
        else:
            break
    return h


def collect_events() -> list[dict]:
    seen: set[tuple] = set()
    events: list[dict] = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "zt_*.json"))):
        with open(path, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
        if not isinstance(data, dict) or not isinstance(data.get("stocks"), list):
            continue
        for s in data["stocks"]:
            code, name = s.get("code"), s.get("name", "")
            for zd in s.get("zt_dates", []):
                if code and zd and (code, zd) not in seen:
                    seen.add((code, zd))
                    events.append({"code": code, "name": name, "zt_date": zd})
    return events


def fetch_klines(codes: list[str], recent: int = 120) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}

    def _task(c):
        rows = local_kline.read_day(f"{_prefix(c)}{c}") or []
        return c, rows[-recent:] if len(rows) > recent else rows

    with ThreadPoolExecutor(max_workers=10) as ex:
        for c, rows in ex.map(_task, codes):
            out[c] = rows
    return out


def analyze(ev: dict, kline: list[dict]) -> dict | None:
    idx = {k["date"]: i for i, k in enumerate(kline)}
    if ev["zt_date"] not in idx:
        return None
    i = idx[ev["zt_date"]]
    base = kline[i]["close"]
    if base <= 0:
        return None
    after = kline[i + 1:]
    closes = [k["close"] for k in after]

    def ret_n(seq, n, ref):
        return round((seq[n - 1] - ref) / ref * 100, 2) if n - 1 < len(seq) else None

    r = {
        "code": ev["code"], "name": ev["name"], "zt_date": ev["zt_date"],
        "board": board_of(ev["code"]), "height": board_height(ev["code"], kline, i),
        "base": round(base, 2),
        "ret_1": ret_n(closes, 1, base), "ret_3": ret_n(closes, 3, base),
        "ret_5": ret_n(closes, 5, base),
        "hold_ret": round((closes[-1] - base) / base * 100, 2) if closes else None,
        "n_after": len(closes),
    }
    # 追入口径: 次日开盘买入
    if after and after[0].get("open") and after[0]["open"] > 0:
        no = after[0]["open"]
        r["gap"] = round((no - base) / base * 100, 2)              # 次日高开幅度
        r["open_ret_1"] = ret_n(closes, 1, no)                     # 开盘买→次日收盘(日内)
        r["open_ret_3"] = ret_n(closes, 3, no)
        r["open_ret_5"] = ret_n(closes, 5, no)
        r["open_hold"] = round((closes[-1] - no) / no * 100, 2) if closes else None
    return r


def stat(vals) -> dict | None:
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {
        "n": len(vals),
        "win": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
        "avg": round(statistics.mean(vals), 2),
        "median": round(statistics.median(vals), 2),
    }


def row(label, s):
    if not s:
        return f"{label:14}{'—':>20}"
    return f"{label:14}{s['n']:>5} {s['win']:>5.0f}% {s['avg']:>+7.2f}% {s['median']:>+7.2f}%"


def main():
    events = collect_events()
    codes = sorted({e["code"] for e in events})
    print(f"去重涨停事件: {len(events)} 个 | 独立股票: {len(codes)} 只")
    print(f"拉取本地K线({len(codes)}只, OHLC)...", flush=True)
    klines = fetch_klines(codes)
    results = [r for r in (analyze(e, klines.get(e["code"], [])) for e in events) if r]
    print(f"有效事件: {len(results)}\n")

    print("===== A. close-to-close (涨停日收盘标尺·封板买不到) =====")
    print(f"{'窗口':14}{'样本':>5} {'胜率':>6} {'均值':>8} {'中位':>8}")
    for k, lb in [("ret_1", "D+1"), ("ret_3", "D+3"), ("ret_5", "D+5"), ("hold_ret", "持有至今")]:
        print(row(lb, stat([r.get(k) for r in results])))

    print("\n===== B. 追入口径 (次日开盘买入·真实可执行) =====")
    gaps = stat([r.get("gap") for r in results])
    if gaps:
        print(f"{'次日高开':14}{gaps['n']:>5} {'':>6} {'均值':>8}{gaps['avg']:>+7.2f}% {'中位':>8}{gaps['median']:>+7.2f}%")
    for k, lb in [("open_ret_1", "买→次日收"), ("open_ret_3", "买→D+3"), ("open_ret_5", "买→D+5"), ("open_hold", "买→持有至今")]:
        print(row(lb, stat([r.get(k) for r in results])))

    print("\n===== C. 按连板高度 (close-close, 胜率%/均值%) =====")
    print(f"{'高度':10}{'样本':>5}  {'D+1':>16}  {'D+3':>16}  {'D+5':>16}")
    for h, lbl in [(1, "首板"), (2, "2板"), (None, "3+板")]:
        rs = [r for r in results if (r["height"] >= 3 if h is None else r["height"] == h)]
        cells = [f"{lbl:10}{len(rs):>5}"]
        for k in ("ret_1", "ret_3", "ret_5"):
            s = stat([r.get(k) for r in rs])
            cells.append(f"{(str(s['win'])+'%') if s else '—':>6}/{s['avg']:+.1f}%" if s else "—".center(16))
        print("".join(cells).rstrip())

    print("\n===== D. 按板块 (close-close, 胜率%/均值%) =====")
    print(f"{'板块':10}{'样本':>5}  {'D+1':>16}  {'D+3':>16}  {'D+5':>16}")
    for b in ("主板", "创业板", "科创板", "北交"):
        rs = [r for r in results if r["board"] == b]
        if not rs:
            continue
        cells = [f"{b:10}{len(rs):>5}"]
        for k in ("ret_1", "ret_3", "ret_5"):
            s = stat([r.get(k) for r in rs])
            cells.append(f"{(str(s['win'])+'%') if s else '—':>6}/{s['avg']:+.1f}%" if s else "—".center(16))
        print("".join(cells).rstrip())

    print("\n===== E. 按涨停月 (close-close, 胜率%/均值%) =====")
    by_month = defaultdict(list)
    for r in results:
        by_month[r["zt_date"][:7]].append(r)
    print(f"{'月':10}{'样本':>5}  {'D+1':>16}  {'D+3':>16}  {'D+5':>16}")
    for m in sorted(by_month):
        rs = by_month[m]
        cells = [f"{m:10}{len(rs):>5}"]
        for k in ("ret_1", "ret_3", "ret_5"):
            s = stat([r.get(k) for r in rs])
            cells.append(f"{(str(s['win'])+'%') if s else '—':>6}/{s['avg']:+.1f}%" if s else "—".center(16))
        print("".join(cells).rstrip())

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "count": len(results),
            "summary_close": {k: stat([r.get(k) for r in results]) for k in ("ret_1", "ret_3", "ret_5", "hold_ret")},
            "summary_open": {k: stat([r.get(k) for r in results]) for k in ("gap", "open_ret_1", "open_ret_3", "open_ret_5", "open_hold")},
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n明细已保存: {OUT_JSON}")


if __name__ == "__main__":
    main()
