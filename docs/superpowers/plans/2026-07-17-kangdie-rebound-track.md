# 抗跌反弹跟踪系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 kangdie 增加反弹跟踪复盘能力——扫所有历史 `kd_*.json` 种子，拉其暴跌日 D 之后的日K，算各窗口涨幅+MFE，对照创业板，累积验证"抗跌→反弹领涨"假设。

**Architecture:** 独立脚本 `kangdie/track.py`（IO 层）+ 纯函数模块 `kangdie/screener/track_analyzer.py`（对齐/窗口/MFE/判定，可单测）。复用 kangdie 现有 `fetcher`（拉K线）、`storage`（读 kd）。对标 `qsht-agent/backtest_pullback.py`。

**Tech Stack:** Python 3.10、requests（新浪接口）、pytest。与 kangdie 现有技术栈一致。

**Spec:** [docs/superpowers/specs/2026-07-17-kangdie-rebound-track-design.md](../specs/2026-07-17-kangdie-rebound-track-design.md)

---

## File Structure

| 文件 | 责任 | 动作 |
|------|------|------|
| `kangdie/screener/track_analyzer.py` | 纯函数：对齐D后bars、窗口涨幅、MFE/MAE、末值、第一时间反弹判定、成熟度 | Create |
| `kangdie/tests/test_track_analyzer.py` | track_analyzer 纯函数单测 | Create |
| `kangdie/track.py` | IO 主脚本：扫kd、拉K线、对齐、算指标、组装events、写track_history.json+track_review.md | Create |
| `kangdie/SKILL.md` | 加"反弹跟踪"章节说明用法 | Modify |
| `kangdie/data/track_history.json` | 累积跟踪数据（运行时生成） | 运行时生成 |
| `kangdie/output/track_review_<date>.md` | 人读报告（运行时生成，新建 output 目录） | 运行时生成 |

**关键约定**：`after_bars[0]` = D+1（暴跌日 D 的下一个交易日）。个股 bars 用 `day` 键、指数 bars 用 `date` 键（fetcher 行为），`align_after` 兼容两者。

---

## Task 1: track_analyzer — align_after（对齐 D 之后的 bars）

**Files:**
- Create: `kangdie/screener/track_analyzer.py`
- Test: `kangdie/tests/test_track_analyzer.py`

- [ ] **Step 1: 写失败测试**

创建 `kangdie/tests/test_track_analyzer.py`：

```python
"""抗跌反弹跟踪纯函数单测。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.track_analyzer import align_after


def _bars(closes, key="day"):
    """构造 K 线序列（按日期正序），close 序列 → bars。key=day(个股)/date(指数)。"""
    return [{
        key: f"2026-07-{10 + i:02d}",
        "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100.0,
    } for i, c in enumerate(closes)]


def test_align_after_found():
    # closes: [D=100, D+1=101, D+2=99]；drop_date = 2026-07-10
    bars = _bars([100.0, 101.0, 99.0])
    after, d_close = align_after(bars, "2026-07-10")
    assert d_close == 100.0
    assert len(after) == 2
    assert after[0]["close"] == 101.0  # D+1


def test_align_after_index_uses_date_key():
    # 指数 bars 用 date 键也能对齐
    bars = _bars([200.0, 198.0], key="date")
    after, d_close = align_after(bars, "2026-07-10")
    assert d_close == 200.0
    assert len(after) == 1


def test_align_after_not_found():
    bars = _bars([100.0, 101.0])
    assert align_after(bars, "2025-01-01") is None


def test_align_after_d_is_last():
    # D 是最后一条（暴跌当天，尚无 D+1）→ after 为空
    bars = _bars([100.0, 101.0])
    after, d_close = align_after(bars, "2026-07-11")
    assert d_close == 101.0
    assert after == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/test_track_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'screener.track_analyzer'`

- [ ] **Step 3: 写最小实现**

创建 `kangdie/screener/track_analyzer.py`：

```python
"""抗跌反弹跟踪纯函数 — 无网络、无副作用，可单测。

对齐暴跌日 D 之后的 K 线切片，算各窗口涨幅 / MFE·MAE / 第一时间反弹判定。
约定: after_bars[0] = D+1（D 的下一个交易日）。
个股 bars 用 day 键、指数 bars 用 date 键（fetcher 行为），本模块两者兼容。
"""

# 跟踪窗口（D 之后第 N 个交易日）
WINDOWS = (1, 3, 5, 10, 20)
MATURE_DAYS = 20  # D+20 后视为成熟，停止更新


def align_after(bars: list[dict], drop_date: str) -> tuple[list[dict], float] | None:
    """在 bars 中定位 drop_date，返回 (bars[i+1:], 该日收盘价)；找不到返回 None。

    兼容 day/date 键。after_bars[0] 即 D+1。
    """
    for i, b in enumerate(bars):
        d = b.get("day") or b.get("date")
        if d == drop_date:
            return bars[i + 1:], b["close"]
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/test_track_analyzer.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/kangdie/screener/track_analyzer.py .claude/skills/kangdie/tests/test_track_analyzer.py
git commit -m "feat(kangdie): track_analyzer.align_after 对齐暴跌日D之后的K线切片"
```

---

## Task 2: track_analyzer — window_return（D+N 涨幅）

**Files:**
- Modify: `kangdie/screener/track_analyzer.py`
- Test: `kangdie/tests/test_track_analyzer.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_track_analyzer.py` 末尾追加：

```python
from screener.track_analyzer import window_return


def test_window_return_normal():
    # d_close=100, D+5 收盘 105 → +5.0%
    after = _bars([101.0, 102.0, 103.0, 104.0, 105.0])  # D+1..D+5
    assert window_return(after, 100.0, 5) == 5.0


def test_window_return_insufficient():
    after = _bars([101.0, 102.0])  # 只有 D+1,D+2
    assert window_return(after, 100.0, 5) is None


def test_window_return_negative():
    after = _bars([98.0, 97.0, 96.0])
    assert window_return(after, 100.0, 3) == -4.0


def test_window_return_zero_base():
    after = _bars([101.0])
    assert window_return(after, 0.0, 1) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/test_track_analyzer.py -v`
Expected: 新 4 个 test_window_return* FAIL（`ImportError: cannot import name 'window_return'`）

- [ ] **Step 3: 追加实现**

在 `track_analyzer.py` 末尾追加：

```python
def window_return(after_bars: list[dict], d_close: float, n: int) -> float | None:
    """D+N 累计涨幅(%)：(close[D+N] - d_close) / d_close × 100。

    after_bars[n-1] = D+N。数据不足（after_bars 少于 n）或 d_close=0 返回 None。
    """
    if len(after_bars) < n or d_close == 0:
        return None
    c = after_bars[n - 1]["close"]
    return round((c - d_close) / d_close * 100, 2)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/test_track_analyzer.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/kangdie/screener/track_analyzer.py .claude/skills/kangdie/tests/test_track_analyzer.py
git commit -m "feat(kangdie): track_analyzer.window_return D+N窗口涨幅"
```

---

## Task 3: track_analyzer — mfe_mae + end_return（极值与末值）

**Files:**
- Modify: `kangdie/screener/track_analyzer.py`
- Test: `kangdie/tests/test_track_analyzer.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_track_analyzer.py` 末尾追加：

```python
from screener.track_analyzer import mfe_mae, end_return


def test_mfe_mae_normal():
    # d_close=100；D 之后 high 最高 108、low 最低 94
    after = _bars([101.0, 105.0, 99.0])
    # _bars 的 high=close+1, low=close-1 → high=[102,106,100] max=106; low=[100,104,98] min=98
    mfe, mae = mfe_mae(after, 100.0)
    assert mfe == 6.0   # (106-100)/100
    assert mae == -2.0  # (98-100)/100


def test_mfe_mae_empty():
    assert mfe_mae([], 100.0) == (None, None)
    assert mfe_mae([{"close": 1}], 0.0) == (None, None)


def test_end_return_normal():
    after = _bars([101.0, 102.0, 98.0])
    assert end_return(after, 100.0) == -2.0  # 最后一根 98


def test_end_return_empty():
    assert end_return([], 100.0) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/test_track_analyzer.py -v`
Expected: 新 test_mfe_mae*/test_end_return* FAIL（ImportError）

- [ ] **Step 3: 追加实现**

在 `track_analyzer.py` 末尾追加：

```python
def mfe_mae(after_bars: list[dict], d_close: float) -> tuple[float | None, float | None]:
    """D 之后区间最大涨幅 MFE / 最大跌幅 MAE(%)，相对 d_close。空数据返回 (None, None)。"""
    if not after_bars or d_close == 0:
        return None, None
    highs = [b["high"] for b in after_bars]
    lows = [b["low"] for b in after_bars]
    mfe = round((max(highs) - d_close) / d_close * 100, 2)
    mae = round((min(lows) - d_close) / d_close * 100, 2)
    return mfe, mae


def end_return(after_bars: list[dict], d_close: float) -> float | None:
    """末值收益(%)：D 之后最后一根收盘相对 d_close。空数据返回 None。"""
    if not after_bars or d_close == 0:
        return None
    return round((after_bars[-1]["close"] - d_close) / d_close * 100, 2)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/test_track_analyzer.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/kangdie/screener/track_analyzer.py .claude/skills/kangdie/tests/test_track_analyzer.py
git commit -m "feat(kangdie): track_analyzer.mfe_mae/end_return 极值与末值收益"
```

---

## Task 4: track_analyzer — first_rebound + is_mature

**Files:**
- Modify: `kangdie/screener/track_analyzer.py`
- Test: `kangdie/tests/test_track_analyzer.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_track_analyzer.py` 末尾追加：

```python
from screener.track_analyzer import first_rebound, is_mature


def test_first_rebound_true():
    # 个股 D+3 收盘 105 (d_close=100, +5%)；创业板 D+3 收盘 102 (idx_d_close=100, +2%)
    # 个股涨>0 且 跑赢创业板 → True
    after = _bars([101.0, 103.0, 105.0])
    idx_after = _bars([100.5, 101.0, 102.0], key="date")
    assert first_rebound(after, 100.0, idx_after, 100.0) is True


def test_first_rebound_stock_dropped():
    # 个股 D+3 跌到 98 → False
    after = _bars([99.0, 98.5, 98.0])
    idx_after = _bars([99.0, 98.0, 97.0], key="date")
    assert first_rebound(after, 100.0, idx_after, 100.0) is False


def test_first_rebound_stock_up_but_underperform():
    # 个股 D+3 = 102 (+2%)，创业板 D+3 = 105 (+5%) → 涨但跑输 → False
    after = _bars([101.0, 101.5, 102.0])
    idx_after = _bars([103.0, 104.0, 105.0], key="date")
    assert first_rebound(after, 100.0, idx_after, 100.0) is False


def test_first_rebound_insufficient():
    after = _bars([101.0, 102.0])  # 不足 3 天
    idx_after = _bars([101.0, 102.0], key="date")
    assert first_rebound(after, 100.0, idx_after, 100.0) is None


def test_is_mature():
    assert is_mature([]) is False
    assert is_mature(_bars([1.0] * 19)) is False
    assert is_mature(_bars([1.0] * 20)) is True
    assert is_mature(_bars([1.0] * 25)) is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/test_track_analyzer.py -v`
Expected: 新 test_first_rebound*/test_is_mature FAIL（ImportError）

- [ ] **Step 3: 追加实现**

在 `track_analyzer.py` 末尾追加：

```python
def first_rebound(
    after_bars: list[dict],
    d_close: float,
    idx_after_bars: list[dict],
    idx_d_close: float,
) -> bool | None:
    """第一时间反弹判定：D+1~D+3 区间，个股累计涨幅 > 0 且 > 创业板同期累计 → True。

    数据不足（个股或创业板 D+3 不够 3 天）或基准为 0 返回 None。
    """
    if len(after_bars) < 3 or len(idx_after_bars) < 3:
        return None
    if d_close == 0 or idx_d_close == 0:
        return None
    stock_cum = (after_bars[2]["close"] - d_close) / d_close * 100
    idx_cum = (idx_after_bars[2]["close"] - idx_d_close) / idx_d_close * 100
    return stock_cum > 0 and stock_cum > idx_cum


def is_mature(after_bars: list[dict]) -> bool:
    """是否已过 D+MATURE_DAYS 个交易日（数据成熟，停止更新）。"""
    return len(after_bars) >= MATURE_DAYS
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/test_track_analyzer.py -v`
Expected: 17 passed

- [ ] **Step 5: 全量回归 + Commit**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/ -q`
Expected: 全部通过（含原 test_analyzer.py）

```bash
git add .claude/skills/kangdie/screener/track_analyzer.py .claude/skills/kangdie/tests/test_track_analyzer.py
git commit -m "feat(kangdie): track_analyzer.first_rebound/is_mature 第一时间反弹判定与成熟度"
```

---

## Task 5: track.py — 主流程（扫 kd → 拉K线 → 对齐 → 算指标 → 写 track_history.json）

**Files:**
- Create: `kangdie/track.py`

> IO 层不做单测（spec 约定），靠 Task 8 端到端验证。

- [ ] **Step 1: 写 track.py**

创建 `kangdie/track.py`：

```python
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


def _compute_event(stock: dict, drop_date: str, idx_aligned) -> dict:
    """对单只种子算跟踪指标。idx_aligned = (idx_after_bars, idx_d_close) 或 None。"""
    code = stock["code"]
    event = {
        "drop_date": drop_date,
        "code": code,
        "name": stock.get("name", ""),
        "d_close": stock.get("close"),
        "d1": None, "d3": None, "d5": None, "d10": None, "d20": None,
        "mfe": None, "mae": None, "end_ret": None,
        "idx_end": None, "first_rebound": None, "mature": False,
    }

    bars = get_stock_kline(code, _KLINE_DAYS)
    aligned = align_after(bars, drop_date) if bars else None
    if not aligned:
        return event  # D 不在 K 线范围 / 拉取失败 → 指标全 None
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

        # 创业板指对齐（每批次只拉一次）
        idx_bars = get_index_kline(_INDEX_SYMBOL, _KLINE_DAYS)
        idx_aligned = align_after(idx_bars, drop_date) if idx_bars else None
        print(f"[{drop_date}] 跟踪 {len(stocks)} 只种子...", flush=True)

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            futures = {ex.submit(_compute_event, s, drop_date, idx_aligned): s for s in stocks}
            for fut in as_completed(futures):
                try:
                    events.append(fut.result())
                except Exception:
                    events.append({  # 兜底：失败也留 event 框架
                        "drop_date": drop_date,
                        "code": futures[fut].get("code", ""),
                        "name": futures[fut].get("name", ""),
                        "d_close": futures[fut].get("close"),
                        "mature": False,
                    })

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
        by_window[key] = {
            "stock": avg(key),
            "idx": None,  # 创业板各窗口均值从 idx 单独算（见下）
        }
    # 创业板各窗口均值：用 first_rebound 之外的 idx 字段需单独跟踪，此处用 idx_end 近似整体
    # （创业板逐窗口均值在本期不展开，保持 YAGNI；报告里展示个股窗口均值即可）

    return {
        "n": n,
        "stocks_total": len({e["code"] for e in events if e.get("code")}),
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


def _write_report(path: str, events: list[dict], stats: dict, as_of: str) -> None:
    """写人读 markdown 报告。"""
    lines = [
        f"# 抗跌反弹跟踪报告 · {as_of}",
        "",
        f"> 累积样本验证「抗跌→反弹领涨」假设；小样本探索性结论，非统计显著，非买卖建议。",
        "",
        f"样本跨度 {stats.get('span', _span(events))} · {stats['n']} 事件 / {stats['stocks_total']} 股",
        "",
        "## 汇总",
        f"- 平均末值收益: {stats['avg_end_ret']}% ｜ 平均 MFE {stats['avg_mfe']}% / MAE {stats['avg_mae']}%",
        f"- 末值正收益(胜率): {stats['win']}/{stats['n']}",
        f"- 第一时间反弹(D+1~3 跑赢创业板): {stats['first_rebound_cnt']}/{stats['first_rebound_total']}",
        "- 各窗口平均涨幅:",
    ]
    for w in WINDOWS:
        v = stats["by_window"][f"d{w}"]["stock"]
        lines.append(f"  - D+{w}: {v}%")
    lines.append("")
    lines.append("## 明细（按 drop_date、code）")
    lines.append("")
    lines.append("| drop_date | code | name | D收盘 | D+1 | D+3 | D+5 | D+10 | D+20 | MFE | 末值 | 第一时间 | 成熟 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for e in events:
        def cell(k):
            v = e.get(k)
            return "—" if v is None else (f"{v}%" if isinstance(v, (int, float)) and k != "mature" else v)
        fr = e.get("first_rebound")
        fr_s = "—" if fr is None else ("✅" if fr else "❌")
        mature_s = "✅" if e.get("mature") else "·"
        lines.append(
            f"| {e['drop_date']} | {e['code']} | {e.get('name','')} | {e.get('d_close','—')} | "
            f"{cell('d1')} | {cell('d3')} | {cell('d5')} | {cell('d10')} | {cell('d20')} | "
            f"{cell('mfe')} | {cell('end_ret')} | {fr_s} | {mature_s} |"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抗跌反弹跟踪")
    parser.add_argument("--date", default=None, help="只跟踪指定暴跌日(YYYY-MM-DD)")
    args = parser.parse_args()
    run_track(date_filter=args.date)
```

- [ ] **Step 2: 冒烟测试（不崩即可，今天 D+1 未发生，各窗口应为 null）**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python track.py --date 2026-07-17 2>&1 | tail -10`
Expected: 打印"跟踪 42 只种子"、无异常、生成 `data/track_history.json` + `output/track_review_2026-07-17.md`

- [ ] **Step 3: 确认输出文件存在且结构正确**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -c "import json; d=json.load(open('data/track_history.json',encoding='utf-8')); print('as_of',d['as_of'],'events',len(d['events']),'n',d['stats']['n']); print(d['events'][0])"`
Expected: as_of=2026-07-17, events=42, n=0（D+1 未发生，end_ret 全 None → n=0，属正常）；首个 event 各窗口为 null、mature=False

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/kangdie/track.py
git commit -m "feat(kangdie): track.py 抗跌反弹跟踪主脚本(扫kd/拉K线/算指标/写history+report)"
```

---

## Task 6: SKILL.md 加"反弹跟踪"章节

**Files:**
- Modify: `kangdie/SKILL.md`

- [ ] **Step 1: 读 SKILL.md 确认插入位置**

Run: Read `kangdie/SKILL.md`，定位"## 数据源"章节之前（"## 边界条件"之后）作为插入点。

- [ ] **Step 2: 追加章节**

在 `kangdie/SKILL.md` 的"## 边界条件"表格之后、"## 输出格式"或"## 数据源"之前，插入：

```markdown
## 反弹跟踪（反弹复盘）

`track.py` 跟踪历史抗跌种子在暴跌日 D 之后的反弹表现，验证"抗跌→反弹领涨"假设。独立于"今天是否暴跌"，任何一天都能跑。

```bash
cd .claude/skills/kangdie && python track.py                 # 扫所有历史 kd_*.json
cd .claude/skills/kangdie && python track.py --date 2026-07-17  # 只跟踪指定批次
```

- **工作流**：暴跌当天跑 `main.py` 存种子（`kd_<date>.json`）→ 后续（尤其大盘反弹后）跑 `track.py` 复盘。
- **衡量**：以 D 收盘为基准，算 D+1/3/5/10/20 涨幅 + 区间最大涨幅 MFE + 末值；对照创业板同期；"第一时间反弹"= D+1~3 跑赢创业板。
- **生命周期**：种子从 D 起跟踪到 D+20 个交易日后成熟（停止更新）。
- **输出**：`data/track_history.json`（累积数据）+ `output/track_review_<date>.md`（人读报告）。
- 小样本探索性结论，非统计显著，**非买卖建议**。
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/kangdie/SKILL.md
git commit -m "docs(kangdie): SKILL.md 加反弹跟踪(track.py)章节"
```

---

## Task 7: 端到端验证 + 全量回归

- [ ] **Step 1: 全量单测回归**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python -m pytest tests/ -q`
Expected: 全部通过（原 test_analyzer.py + 新 test_track_analyzer.py，17+ 测试）

- [ ] **Step 2: 端到端跑全量跟踪**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 python track.py 2>&1 | tail -6`
Expected: 扫描所有历史 kd_*.json（至少 7-17 这批），无异常，生成/更新 track_history.json + track_review_<today>.md

- [ ] **Step 3: 抽查报告可读性**

Run: `cd .claude/skills/kangdie && PYTHONIOENCODING=utf-8 head -20 output/track_review_*.md`
Expected: 报告含标题、汇总、明细表头；7-17 批次各窗口为 —（D+1 未发生，正常）

- [ ] **Step 4: 最终 commit（若有遗留改动）**

```bash
git status -s   # 确认只剩运行时生成的 data/track_history.json 等（可不入库或单独决定）
```
> 注：`data/track_history.json` 和 `output/track_review_*.md` 是运行产物，是否入库同 kd_*.json 惯例（kd_*.json 已入库，建议一并入库以保留复盘历史）。

---

## Self-Review

**1. Spec 覆盖**：
- 独立 track.py 复用 fetcher/analyzer/storage → Task 5 ✓
- 纯函数 track_analyzer 可单测 → Task 1-4 ✓
- 固定窗口 D+1/3/5/10/20 + MFE → Task 2,3 ✓
- 对照创业板（idx_end + first_rebound）→ Task 4, Task5 _compute_event ✓
- 累积 track_history.json + track_review.md → Task 5 ✓
- 跟踪到 D+20（is_mature）→ Task 4 ✓
- SKILL.md 章节 → Task 6 ✓
- 边界（退市/数据不足/创业板失败）→ Task5 _compute_event 兜底 None + idx_aligned None ✓

**2. Placeholder 扫描**：无 TBD/TODO；Task 5 `_summarize` 里创业板逐窗口均值标注"本期不展开保持 YAGNI"——这是有意的范围限定（spec 的 by_window 在汇总面板只需个股窗口均值看节奏，创业板对照已由每 event 的 idx_end + first_rebound 承载），非占位符。

**3. 类型/命名一致性**：
- `align_after` 返回 `(after_bars, d_close)` — Task1 定义，Task5 `_compute_event` 使用一致 ✓
- `window_return(after_bars, d_close, n)` — Task2 定义，Task5 调用 `window_return(after_bars, d_close, n)` ✓
- `first_rebound(after_bars, d_close, idx_after_bars, idx_d_close)` — Task4 定义，Task5 调用一致 ✓
- `WINDOWS=(1,3,5,10,20)`、`MATURE_DAYS=20` — Task1 定义，后续一致引用 ✓
- event 字段名（d1/d3/d5/d10/d20/mfe/mae/end_ret/idx_end/first_rebound/mature）— Task5 定义，Task6 报告、spec 一致 ✓
