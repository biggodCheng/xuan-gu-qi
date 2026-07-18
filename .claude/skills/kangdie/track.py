"""抗跌反弹跟踪 — 扫描所有历史 kd_*.json 种子，回看其在暴跌日 D 之后的表现。

验证假设：暴跌日抗跌的种子，大盘反弹时是否第一时间领涨、反弹高度如何。
独立于"今天是否暴跌"，任何一天都能跑。结果为小样本探索性，非买卖建议。

用法:
  python track.py                # 扫所有历史 kd_*.json
  python track.py --date 2026-07-17   # 只跟踪指定批次
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import get_stock_kline, get_index_kline
from screener.track_analyzer import (
    WINDOWS,
    align_after,
    window_return,
    mfe_mae,
    end_return,
    first_rebound,
    is_mature,
)

_INDEX_SYMBOL = "sz399006"   # 创业板指
_KLINE_DAYS = 60             # 覆盖 D+20 + 对齐缓冲
_MAX_WORKERS = 20

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_HERE, "data")
_OUTPUT_DIR = os.path.join(_HERE, "output")
_HISTORY_FILE = os.path.join(_DATA_DIR, "track_history.json")


def _empty_event(stock: dict, drop_date: str) -> dict:
    """15 键空 event 模板，供 _compute_event 初始化与异常兜底共用。"""
    return {
        "drop_date": drop_date,
        "code": stock["code"],
        "name": stock.get("name", ""),
        "d_close": stock.get("close"),
        "d1": None, "d3": None, "d5": None, "d10": None, "d20": None,
        "mfe": None, "mae": None, "end_ret": None,
        "idx_end": None, "first_rebound": None, "mature": False,
    }


def _compute_event(stock: dict, drop_date: str, idx_aligned) -> dict:
    """对单只种子算跟踪指标。idx_aligned = (idx_after_bars, idx_d_close) 或 None。"""
    code = stock["code"]
    event = _empty_event(stock, drop_date)

    bars = get_stock_kline(code, _KLINE_DAYS)
    aligned = align_after(bars, drop_date) if bars else None
    if not aligned:
        return event
    after_bars, d_close = aligned

    for n in WINDOWS:
        event[f"d{n}"] = window_return(after_bars, d_close, n)
    event["mfe"], event["mae"] = mfe_mae(after_bars, d_close)
    event["end_ret"] = end_return(after_bars, d_close)
    event["mature"] = is_mature(after_bars)

    if idx_aligned:
        idx_after, idx_d_close = idx_aligned
        event["idx_end"] = end_return(idx_after, idx_d_close)
        event["first_rebound"] = first_rebound(after_bars, d_close, idx_after, idx_d_close)

    return event


def run_track(date_filter: str | None = None) -> bool:
    start = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    kd_files = sorted(glob.glob(os.path.join(_DATA_DIR, "kd_*.json")))
    if date_filter:
        kd_files = [f for f in kd_files if f"kd_{date_filter}.json" in f]
    if not kd_files:
        print("无历史 kd_*.json，尚无暴跌批次可跟踪。", flush=True)
        return True

    events: list[dict] = []
    for kd_file in kd_files:
        m = re.search(r"kd_(\d{4}-\d{2}-\d{2})\.json$", os.path.basename(kd_file))
        if not m:
            continue
        drop_date = m.group(1)
        with open(kd_file, "r", encoding="utf-8") as f:
            kd = json.load(f)
        stocks = kd.get("stocks", [])
        if not stocks:
            print(f"[{drop_date}] 该批次无种子（count=0），跳过。", flush=True)
            continue

        idx_bars = get_index_kline(_INDEX_SYMBOL, _KLINE_DAYS)
        idx_aligned = align_after(idx_bars, drop_date) if idx_bars else None
        print(f"[{drop_date}] 跟踪 {len(stocks)} 只种子...", flush=True)

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            futures = {ex.submit(_compute_event, s, drop_date, idx_aligned): s for s in stocks}
            for fut in as_completed(futures):
                try:
                    events.append(fut.result())
                except Exception as e:
                    print(f"[{drop_date}] {futures[fut].get('code', '')} 跟踪失败: {e}", flush=True)
                    events.append(_empty_event(futures[fut], drop_date))

    stats = _summarize(events)
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    report_file = os.path.join(_OUTPUT_DIR, f"track_review_{today}.md")
    _write_report(report_file, events, stats, today)

    history = {
        "as_of": today,
        "span": _span(events),
        "events": events,
        "stats": stats,
    }
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start
    print(f"完成！跟踪 {len(events)} 事件，耗时 {elapsed:.0f} 秒。", flush=True)
    print(f"累积数据: {_HISTORY_FILE}", flush=True)
    print(f"人读报告: {report_file}", flush=True)
    return True


def _summarize(events: list[dict]) -> dict:
    """汇总统计：胜率/平均MFE/第一时间反弹占比/各窗口均值。"""
    valid = [e for e in events if e.get("end_ret") is not None]
    n = len(valid)
    fr = [e for e in events if e.get("first_rebound") is True]

    def avg(key):
        vals = [e[key] for e in valid if e.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    by_window = {}
    for w in WINDOWS:
        key = f"d{w}"
        by_window[key] = avg(key)

    return {
        "n": n,
        "stocks_total": len({e["code"] for e in valid if e.get("code")}),
        "avg_end_ret": avg("end_ret"),
        "avg_mfe": avg("mfe"),
        "avg_mae": avg("mae"),
        "win": sum(1 for e in valid if e["end_ret"] > 0),
        "first_rebound_cnt": len(fr),
        "first_rebound_total": sum(1 for e in events if e.get("first_rebound") is not None),
        "by_window": by_window,
    }


def _span(events: list[dict]) -> str:
    dates = sorted({e["drop_date"] for e in events if e.get("drop_date")})
    if not dates:
        return "—"
    return dates[0] if len(dates) == 1 else f"{dates[0]}–{dates[-1]}"


def _cell(e, k):
    v = e.get(k)
    return "—" if v is None else (f"{v}%" if isinstance(v, (int, float)) else v)


def _fmt_pct(v):
    """百分比格式化：None → —，否则 v%。"""
    return "—" if v is None else f"{v}%"


def _write_report(path: str, events: list[dict], stats: dict, as_of: str) -> None:
    """写人读 markdown 报告（汇总+明细表）。"""
    lines = [
        f"# 抗跌反弹跟踪报告 · {as_of}",
        "",
        f"> 累积样本验证「抗跌→反弹领涨」假设；小样本探索性结论，非统计显著，非买卖建议。",
        "",
        f"样本跨度 {_span(events)} · {stats['n']} 事件 / {stats['stocks_total']} 股",
        "",
        "## 汇总",
        f"- 平均末值收益: {_fmt_pct(stats['avg_end_ret'])} ｜ 平均 MFE {_fmt_pct(stats['avg_mfe'])} / MAE {_fmt_pct(stats['avg_mae'])}",
        f"- 末值正收益(胜率): {stats['win']}/{stats['n']}",
        f"- 第一时间反弹(D+1~3 跑赢创业板): {stats['first_rebound_cnt']}/{stats['first_rebound_total']}",
        "- 各窗口平均涨幅:",
    ]
    for w in WINDOWS:
        v = stats["by_window"][f"d{w}"]
        lines.append(f"  - D+{w}: {_fmt_pct(v)}")
    lines.append("")
    lines.append("## 明细（按 drop_date、code）")
    lines.append("")
    lines.append("| drop_date | code | name | D收盘 | D+1 | D+3 | D+5 | D+10 | D+20 | MFE | 末值 | 第一时间 | 成熟 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for e in events:
        fr = e.get("first_rebound")
        fr_s = "—" if fr is None else ("✅" if fr else "❌")
        mature_s = "✅" if e.get("mature") else "·"
        lines.append(
            f"| {e['drop_date']} | {e['code']} | {e.get('name','')} | {e.get('d_close','—')} | "
            f"{_cell(e, 'd1')} | {_cell(e, 'd3')} | {_cell(e, 'd5')} | {_cell(e, 'd10')} | {_cell(e, 'd20')} | "
            f"{_cell(e, 'mfe')} | {_cell(e, 'end_ret')} | {fr_s} | {mature_s} |"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抗跌反弹跟踪")
    parser.add_argument("--date", default=None, help="只跟踪指定暴跌日(YYYY-MM-DD)")
    args = parser.parse_args()
    run_track(date_filter=args.date)
