# 波段超跌反弹信号 实施计划（阶段 1：回测验证）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 chaodiefantan/backtest/ 新增波段超跌信号（20日超跌+放量阳包阴，去长下影）的判定函数 + 网格回测，跑 2018-2026 全量验证正期望，作为新 skill 上线前的决策依据。

**Architecture:** 新写 `is_band_rebound`（纯判定）+ `scan_band_signals`（逐日逐股扫描）+ `grid_backtest.py`（网格编排）。复用现有 `dedup_signals`/`simulate_exit`/`build_trades`/`aggregate_*`/数据加载，**不改任何现有模块**（signal_scan/simulator/market_cap/report/backtest_main 只 import）。

**Tech Stack:** Python 3，pandas，requests（复用 kangdie fetcher），pytest，新浪日 K（前复权 qfq）。

**Spec:** `docs/superpowers/specs/2026-08-08-band-oversold-rebound-design.md`

---

## 文件结构

- **Create:** `.claude/skills/chaodiefantan/backtest/band_signal.py` — `is_band_rebound` 判定纯函数（无网络、可单测）
- **Create:** `.claude/skills/chaodiefantan/backtest/grid_backtest.py` — `scan_band_signals` + `run_grid` 编排 + `render_grid_report` 报告
- **Create:** `.claude/skills/chaodiefantan/backtest/tests/test_band_signal.py` — `is_band_rebound` 单测
- **Create:** `.claude/skills/chaodiefantan/backtest/tests/test_grid_scan.py` — `scan_band_signals` 单测
- **不修改：** signal_scan.py / simulator.py / market_cap.py / report.py / backtest_main.py（只 import 复用）

---

## Task 1: `is_band_rebound` 判定纯函数（TDD）

**Files:**
- Create: `.claude/skills/chaodiefantan/backtest/band_signal.py`
- Test: `.claude/skills/chaodiefantan/backtest/tests/test_band_signal.py`

- [ ] **Step 1: 写失败测试**

Create `.claude/skills/chaodiefantan/backtest/tests/test_band_signal.py`:

```python
# -*- coding: utf-8 -*-
"""is_band_rebound 单测 — 波段超跌反弹判定(20日超跌+T日放量阳包阴,去长下影)。"""
from backtest.band_signal import is_band_rebound


def _bar(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _down_bars(n, start_close=100.0, end_close=75.0, base_vol=1000):
    """生成 n 根递减阴线(每根 open>close, 从 start_close 跌到 end_close)。"""
    bars = []
    step = (start_close - end_close) / (n - 1)
    for i in range(n):
        c = start_close - step * i
        bars.append(_bar(f"2024-01-{i+1:02d}", c + 0.5, c + 1, c - 1, c, base_vol))
    return bars


def _build(prev_close_t1, t_open, t_high, t_low, t_close, t_vol, n_prev=20, start_close=100.0):
    """前 n_prev 根跌到 prev_close_t1, 再加一根 T 日(给定 OHLCV)。"""
    bars = _down_bars(n_prev, start_close, prev_close_t1)
    bars.append(_bar("2024-01-21", t_open, t_high, t_low, t_close, t_vol))
    return bars


def test_pass_basic():
    # 20日 100→70(-30%) + T日阳包阴放量
    bars = _build(prev_close_t1=70.0, t_open=70.3, t_high=71.5, t_low=69.0,
                  t_close=72.0, t_vol=2000)
    r = is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5)
    assert r is not None
    assert r["drop20"] <= -20
    assert r["stop_loss"] == 69.0           # T-1 最低
    assert r["vol_ratio"] == 2.0


def test_fail_no_oversold():
    # 20日只跌 100→85(-15%), 不满足 -20%
    bars = _build(prev_close_t1=85.0, t_open=85.3, t_high=86.5, t_low=84,
                  t_close=87, t_vol=2000, start_close=100.0)
    # 注: 85→这里 start 100 跌到 85 需要 _down_bars 内部; _build 用 start_close=100
    # 实际 close[T]=87, close[T-20]=100 → -13%, 不满足
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5) is None


def test_fail_not_yangbaoyin():
    # T 日收阴(不阳包阴)
    bars = _build(prev_close_t1=70.0, t_open=72.0, t_high=72.5, t_low=69,
                  t_close=70.5, t_vol=2000)   # close70.5 < open72 → 阴线
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5) is None


def test_fail_no_volume():
    # T 日未放量(vol=1200 < 1500 阈值)
    bars = _build(prev_close_t1=70.0, t_open=70.3, t_high=71.5, t_low=69,
                  t_close=72, t_vol=1200)
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5) is None


def test_shrink_on_rejects_churning():
    # use_shrink=True: T-1 未缩量(vol[T-1]=1000=前4日均量)→ 应被拒
    bars = _build(prev_close_t1=70.0, t_open=70.3, t_high=71.5, t_low=69,
                  t_close=72, t_vol=2000)   # 所有 bar vol=1000, T-1 未缩量
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5, use_shrink=True) is None


def test_short_history_returns_none():
    bars = _down_bars(15, 100, 70)          # 只有 15 根 < 21
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5) is None
```

- [ ] **Step 2: 跑测试验证失败**

```bash
cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_band_signal.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.band_signal'`

- [ ] **Step 3: 实现 `is_band_rebound`**

Create `.claude/skills/chaodiefantan/backtest/band_signal.py`:

```python
# -*- coding: utf-8 -*-
"""波段超跌反弹判定纯函数 — 无网络、无副作用, 可单测。

与 screener.analyzer.is_oversold_rebound 的区别(直击痛点):
  - 超跌窗口 5日→20日(月度级波段, 对齐"跌一个月")
  - 删除 T-1 长下影条件(现有策略 37→1 的瓶颈, 抓不到突发反弹)
  - 保留 T日放量阳包阴(资金进场确认)
  - T-1缩量改为可选(use_shrink, 回测对比有/无)

bar 格式: {date/open/high/low/close, volume 或 vol}, 按日期正序,
最后一个=T日, 倒数第二=T-1。详见 spec §3。
"""
DROP_WINDOW = 20          # 近20日超跌窗口(≈一个月)
SHRINK_RATIO = 0.8        # T-1 相对前4日均量的缩量阈值


def _get(bar: dict, *keys):
    for k in keys:
        if k in bar:
            return bar[k]
    raise KeyError(f"none of {keys} found in bar")


def is_band_rebound(bars: list[dict], market_cap: float | None = None,
                    drop_pct: float = 20.0, vol_ratio: float = 1.5,
                    use_shrink: bool = False, use_t1_drop: bool = False
                    ) -> dict | None:
    """波段超跌反弹判定。

    Args:
        bars: 日K列表(正序), bars[-1]=T日, 需 >= DROP_WINDOW+1=21 根(use_t1_drop 需 22)。
        market_cap: 流通市值(亿, 仅展示, 不过滤)。
        drop_pct: 超跌幅度阈值(%), 跌幅 <= -drop_pct 才算超跌。
        vol_ratio: T日放量倍数, vol[T] >= vol[T-1] * vol_ratio。
        use_shrink: 是否要求 T-1 缩量(vol[T-1] < 前4日均量×0.8)。
        use_t1_drop: 超跌口径。False=含T日 close[T]/close[T-20](标准20日跌幅);
            True=不含T日 close[T-1]/close[T-21](避免 T 日反弹抵消跌幅, spec §3 待对比项)。

    Returns:
        通过返回 {drop20, vol_ratio, stop_loss}; 不通过 None。
        stop_loss = T-1 日最低(破即止损)。
    """
    if len(bars) < DROP_WINDOW + 1:
        return None

    t1 = bars[-1]      # T 日
    t2 = bars[-2]      # T-1 日
    t20 = bars[-(DROP_WINDOW + 1)]   # 20 日前

    # 条件A: 近20日超跌(两种口径, spec §3 对比)
    if use_t1_drop:
        if len(bars) < DROP_WINDOW + 2:
            return None
        base_close = bars[-(DROP_WINDOW + 2)]["close"]   # close[T-21]
        ref_close = t2["close"]                          # close[T-1]
    else:
        base_close = t20["close"]                        # close[T-20]
        ref_close = t1["close"]                          # close[T]
    if base_close <= 0:
        return None
    drop20 = (ref_close - base_close) / base_close * 100
    if drop20 > -drop_pct:
        return None

    # 条件B: T 日阳包阴(阳线 + 收复前日开盘 + 破前日高)
    o1, c1 = t1["open"], t1["close"]
    o2 = t2["open"]
    if c1 <= o1:                        # 非阳线
        return None
    if c1 <= o2:                        # 未收复前日开盘
        return None
    if _get(t1, "high") <= _get(t2, "high"):   # 未突破前日高
        return None

    # 条件C: T 日放量
    v1 = _get(t1, "volume", "vol")
    v2 = _get(t2, "volume", "vol")
    if v2 <= 0 or v1 < v2 * vol_ratio:
        return None

    # 条件D(可选): T-1 缩量(相对前 4 日均量)
    if use_shrink:
        prev4 = [_get(bars[i], "volume", "vol") for i in range(-6, -2)]
        vol_prev_mean = sum(prev4) / 4
        if vol_prev_mean <= 0 or v2 >= vol_prev_mean * SHRINK_RATIO:
            return None

    return {
        "drop20": round(drop20, 2),
        "vol_ratio": round(v1 / v2, 2),
        "stop_loss": round(_get(t2, "low"), 2),   # 止损 = T-1 最低
    }
```

- [ ] **Step 4: 跑测试验证通过**

```bash
cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_band_signal.py -v
```
Expected: PASS（6 个测试全绿）

- [ ] **Step 5: 确认未破坏现有回测测试**

```bash
cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/ -v
```
Expected: 全绿（现有测试 + 新 test_band_signal 都过）

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/band_signal.py .claude/skills/chaodiefantan/backtest/tests/test_band_signal.py
git commit -m "feat(chaodiefantan): 加波段超跌信号判定 is_band_rebound(20日超跌+阳包阴,去长下影)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: `scan_band_signals` 逐日逐股扫描（TDD）

**Files:**
- Create: `.claude/skills/chaodiefantan/backtest/grid_backtest.py`（本任务只写 scan 函数 + import 头）
- Test: `.claude/skills/chaodiefantan/backtest/tests/test_grid_scan.py`

- [ ] **Step 1: 写失败测试**

Create `.claude/skills/chaodiefantan/backtest/tests/test_grid_scan.py`:

```python
# -*- coding: utf-8 -*-
"""scan_band_signals 单测 — 逐日逐股扫描波段信号。"""
from backtest.grid_backtest import scan_band_signals


def _bar(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_scan_finds_signal_on_qualified_day():
    # 构造一只股: 前20日跌 100→70, 第21日(T)阳包阴放量
    bars = []
    for i in range(20):
        c = 100 - (100 - 70) / 19 * i
        bars.append(_bar(f"2024-01-{i+1:02d}", c + 0.5, c + 1, c - 1, c, 1000))
    bars.append(_bar("2024-01-21", 70.3, 71.5, 69, 72, 2000))   # T 日合格

    klines = {"600001": bars}
    dates = ["2024-01-21"]
    shares = lambda code, date: 1e8                      # 1亿股
    names = {"600001": "测试股"}
    unadj = {"600001": {"2024-01-21": 72.0}}             # 不复权收盘

    sigs = scan_band_signals(klines, shares, names, dates, unadj,
                            drop_pct=20.0, vol_ratio=1.5, use_shrink=False)
    assert len(sigs) == 1
    s = sigs[0]
    assert s["code"] == "600001" and s["name"] == "测试股"
    assert s["signal_date"] == "2024-01-21"
    assert s["stop_loss"] == 69.0
    assert s["market_cap_T"] > 0


def test_scan_skips_non_target_date():
    bars = [_bar(f"2024-01-{i+1:02d}", 10, 11, 9, 10, 100) for i in range(25)]
    sigs = scan_band_signals({"600001": bars}, lambda c, d: 1e8,
                            {"600001": "X"}, ["2099-12-31"], {},
                            drop_pct=20.0, vol_ratio=1.5)
    assert sigs == []                                    # T 日不在 dates → 无信号
```

- [ ] **Step 2: 跑测试验证失败**

```bash
cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_grid_scan.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.grid_backtest'`

- [ ] **Step 3: 写 `grid_backtest.py` 的 import 头 + `scan_band_signals`**

Create `.claude/skills/chaodiefantan/backtest/grid_backtest.py`:

```python
# -*- coding: utf-8 -*-
"""波段超跌信号网格回测 — 扫 X/R/缩量/开关/持仓 找正期望组合。

复用 chaodiefantan/backtest 框架(数据加载/simulator/report), 不改任何现有模块。
详见 spec docs/superpowers/specs/2026-08-08-band-oversold-rebound-design.md

用法:
    python -m backtest.grid_backtest --smoke                 # 小样本冒烟
    python -m backtest.grid_backtest --start 2018-01-02 --end 2026-08-07   # 全量
"""
import argparse
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)                     # chaodiefantan/
sys.path.insert(0, SKILL_DIR)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from backtest.band_signal import is_band_rebound  # noqa: E402
from backtest.market_cap import estimate_cap_yi, in_cap_band  # noqa: E402

DEFAULT_START = "2018-01-02"
DEFAULT_END = "2026-08-07"
CACHE_DIR = os.path.join(HERE, "data")


def scan_band_signals(klines_by_code: dict, shares_func, names: dict,
                      dates: list, unadj_close: dict,
                      drop_pct: float, vol_ratio: float, use_shrink: bool,
                      use_t1_drop: bool = False) -> list[dict]:
    """逐日逐股扫描波段超跌信号。

    与 backtest.signal_scan.scan_signals 同结构, 但调 is_band_rebound + 字段用 drop20。
    市值用 shares_func(code, date) 时变股本(in_cap_band 默认关闭=不卡市值)。
    use_t1_drop 透传给 is_band_rebound(超跌口径, spec §3)。
    """
    signals: list[dict] = []
    date_set = set(dates)
    for code, bars in klines_by_code.items():
        if len(bars) < 21:
            continue
        unadj = unadj_close.get(code, {})
        name = names.get(code, code)
        for i in range(20, len(bars)):                 # bars[i]=候选T日, 需之前>=20根
            t_date = bars[i]["date"]
            if t_date not in date_set:
                continue
            shares_t = shares_func(code, t_date)
            if not shares_t:
                continue
            window = bars[: i + 1]
            close_unadj = unadj.get(t_date, window[-1]["close"])
            cap_t = estimate_cap_yi(close_unadj, shares_t)
            if not in_cap_band(cap_t):
                continue
            detail = is_band_rebound(window, cap_t, drop_pct, vol_ratio, use_shrink,
                                     use_t1_drop)
            if detail is None:
                continue
            signals.append({
                "signal_date": t_date, "code": code, "name": name,
                "close_T": window[-1]["close"], "stop_loss": detail["stop_loss"],
                "drop20": detail["drop20"], "vol_ratio": detail["vol_ratio"],
                "market_cap_T": round(cap_t, 2),
            })
    return signals
```

- [ ] **Step 4: 跑测试验证通过**

```bash
cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_grid_scan.py -v
```
Expected: PASS（2 个测试绿）

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/grid_backtest.py .claude/skills/chaodiefantan/backtest/tests/test_grid_scan.py
git commit -m "feat(chaodiefantan): 加 scan_band_signals 逐日扫描波段超跌信号

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 网格回测编排 + 报告（冒烟验证）

**Files:**
- Modify: `.claude/skills/chaodiefantan/backtest/grid_backtest.py`（追加 `run_grid` + `render_grid_report` + `main`）

- [ ] **Step 1: 追加 `run_grid` + `render_grid_report` + `main`**

在 `grid_backtest.py` 末尾追加（import 头部已在 Task 2 写好，这里补 import 复用模块 + 函数）。

先在文件 import 区追加（`from backtest.band_signal ...` 那行之后）:

```python
from backtest.data_loader import (  # noqa: E402
    fetch_all, prefetch_waf_check, fetch_all_dividends)
from backtest.market_cap import shares_at_date  # noqa: E402
from backtest.signal_scan import dedup_signals  # noqa: E402
from backtest.report import aggregate_overall, aggregate_by_year  # noqa: E402
from backtest.backtest_main import (  # noqa: E402
    load_pool_and_shares, _compute_crash_dates, _fetch_start, build_trades)
```

再在文件末尾追加:

```python
# 网格参数(spec §4): 超跌幅度 X × 放量倍数 R × T-1缩量 × 大盘开关
GRID_X = [20.0, 25.0, 30.0]
GRID_R = [1.5, 2.0, 2.5]
GRID_SHRINK = [False, True]
GRID_SWITCH = [False, True]
BEAR_YEARS = ("2018", "2022")          # 成功标准③: 熊市单年期望 > -3%
SIGNAL_FLOOR = 50                       # 成功标准②: 信号数 >= 50


def _eval_combo(klines_dict, shares_func, names, dates_q, unadj_close,
                crash_dates, drop_pct, vol_ratio, use_shrink, use_switch):
    """跑单个参数组合, 返回结果 dict。"""
    raw = scan_band_signals(klines_dict, shares_func, names, dates_q, unadj_close,
                           drop_pct, vol_ratio, use_shrink)
    sigs = dedup_signals(raw, dates_q)
    if use_switch:                                     # 大盘开关: 排除 crash 日
        sigs = [s for s in sigs if s["signal_date"] not in crash_dates]
    if not sigs:
        return {"n": 0, "raw": len(raw)}
    trades = build_trades(sigs, klines_dict, "open")   # T+1 开盘口径, 纪律退出
    o = aggregate_overall(trades)
    yg = aggregate_by_year(trades)
    return {
        "n": len(sigs), "raw": len(raw),
        "win": o["win_rate"], "payoff": o["payoff"], "avg": o["avg_ret_net"],
        "bear": {y: (yg.get(y, {}) or {}).get("avg_ret_net") for y in BEAR_YEARS},
        "expect": (o["win_rate"] / 100 * o["payoff"]) if o["n"] else 0,
    }


def _ok(r: dict) -> bool:
    """成功标准达标判定(spec §5): 正期望 + 信号>=50 + 熊市单年>-3%。"""
    if r["n"] < SIGNAL_FLOOR:
        return False
    if r["avg"] <= 0 or r["expect"] <= 1:
        return False
    for y in BEAR_YEARS:
        v = r["bear"].get(y)
        if v is not None and v <= -3.0:
            return False
    return True


def render_grid_report(rows: list, start: str, end: str, out_path: str):
    L = [f"# 波段超跌信号 网格回测报告（{start} ~ {end}）\n"]
    L.append("> T+1 开盘口径 + 纪律退出(max_hold=10)。"
             "达标 = 正期望(胜率×盈亏比>1) + 信号≥50 + 2018/2022 单年>-3%。\n")
    L.append("## 网格结果\n")
    L.append("| X% | R | 缩量 | 开关 | 原始 | 去重信号 | 胜率 | 盈亏比 | 期望 | 平均净收益 | 2018 | 2022 | 达标 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        b18 = r["bear"].get("2018"); b22 = r["bear"].get("2022")
        fmt = lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "—"
        if r["n"] == 0:
            L.append(f"| {r['X']} | {r['R']} | {r['shrink']} | {r['switch']} | "
                     f"{r['raw']} | 0 | — | — | — | — | — | — | ❌ |")
        else:
            L.append(f"| {r['X']} | {r['R']} | {r['shrink']} | {r['switch']} | "
                     f"{r['raw']} | {r['n']} | {r['win']:.0f}% | {r['payoff']} | "
                     f"{r['expect']:.2f} | {r['avg']:+.2f}% | {fmt(b18)} | {fmt(b22)} | "
                     f"{'✅' if r['ok'] else '❌'} |")
    winners = [r for r in rows if r["ok"]]
    L.append(f"\n## 达标组合: {len(winners)} / {len(rows)}\n")
    if winners:
        best = max(winners, key=lambda r: r["avg"])
        L.append(f"- 最优(平均净收益最高): X={best['X']}% R={best['R']} "
                 f"缩量={best['shrink']} 开关={best['switch']} → "
                 f"{best['n']}信号 / {best['win']:.0f}% / 盈亏比{best['payoff']} / "
                 f"{best['avg']:+.2f}%\n")
    else:
        L.append("- 无组合达标 → 按 spec §6 决策规则: 放弃或加约束, **禁止降阈值凑**。\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def run_grid(start: str = DEFAULT_START, end: str = DEFAULT_END, smoke: bool = False):
    fetch_start = _fetch_start(start)
    print(f"[网格回测] {start} ~ {end} (K线起点 {fetch_start})", flush=True)

    print("[1] 股票池+股本 ...", flush=True)
    pool, shares_by_code, names = load_pool_and_shares()
    if smoke:
        pool = [s for s in pool if s["code"].startswith(("0", "3", "6"))][:5]
        shares_by_code = {c: shares_by_code[c] for c in [s["code"] for s in pool]}
    print(f"    池: {len(pool)} 只", flush=True)

    print("[2] 数据源预测试 ...", flush=True)
    rate = prefetch_waf_check(pool, fetch_start, end, sample=10 if smoke else 50)
    if rate < 0.8:
        raise RuntimeError(f"数据源预测试成功率 {rate:.0%} < 80%, 中止")

    print("[3] 拉取前复权+不复权 K线(一次性, 全网格共享) ...", flush=True)
    klines_qfq = fetch_all(pool, fetch_start, end, "qfq", CACHE_DIR,
                           f"qfq_{fetch_start}_{end}")
    klines_unadj = fetch_all(pool, fetch_start, end, "", CACHE_DIR,
                             f"unadj_{fetch_start}_{end}")
    print("[3.5] 拉除权日历 ...", flush=True)
    dividends = fetch_all_dividends(pool, CACHE_DIR)

    dates_q = sorted({b["date"] for kl in klines_qfq.values()
                      for b in kl.to_dict("records") if start <= b["date"] <= end})
    unadj_close = {c: dict(zip(kl["date"], kl["close"]))
                   for c, kl in klines_unadj.items()}
    klines_dict = {c: kl.to_dict("records") for c, kl in klines_qfq.items()}

    def _shares_func(code, date):
        cur = shares_by_code.get(code)
        if not cur:
            return None
        return shares_at_date(cur, dividends.get(code, []), date)

    print("[4] 预算大盘 crash 日(用于开关组合) ...", flush=True)
    crash_dates = _compute_crash_dates(start, end)
    print(f"    crash 交易日 {len(crash_dates)} 个", flush=True)

    print(f"[5] 跑 {len(GRID_X)*len(GRID_R)*len(GRID_SHRINK)*len(GRID_SWITCH)} 组网格 ...",
          flush=True)
    rows = []
    for X, R, use_shrink, use_switch in itertools.product(
            GRID_X, GRID_R, GRID_SHRINK, GRID_SWITCH):
        r = _eval_combo(klines_dict, _shares_func, names, dates_q, unadj_close,
                        crash_dates, X, R, use_shrink, use_switch)
        r.update({"X": X, "R": R, "shrink": use_shrink, "switch": use_switch,
                  "ok": _ok(r) if r["n"] else False})
        rows.append(r)
        print(f"    X={X} R={R} shrink={use_shrink} switch={use_switch} → "
              f"{r['n']}信号 {r.get('avg', 0):+.2f}%", flush=True)

    out_path = os.path.join(SKILL_DIR, "..", "..", "..", "docs",
                            f"band_grid_{start}_{end}.md")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    render_grid_report(rows, start, end, out_path)
    print(f"[done] 报告: {os.path.abspath(out_path)}", flush=True)
    print(f"        达标 {sum(1 for r in rows if r['ok'])} / {len(rows)} 组", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="小样本冒烟(5只)")
    p.add_argument("--start", default=DEFAULT_START)
    p.add_argument("--end", default=DEFAULT_END)
    args = p.parse_args()
    run_grid(start=args.start, end=args.end, smoke=args.smoke)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 冒烟测试（5 只股，验证不报错 + 输出报告）**

```bash
cd .claude/skills/chaodiefantan && python -m backtest.grid_backtest --smoke 2>&1 | tail -20
```
Expected: 输出 36 组网格结果（冒烟样本下信号多为 0，正常），生成 `docs/band_grid_*.md`，无报错。

- [ ] **Step 3: 确认现有测试仍全绿**

```bash
cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/ -v
```
Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/grid_backtest.py
git commit -m "feat(chaodiefantan): 波段超跌信号网格回测编排+报告(36组 X/R/缩量/开关)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: 全量回测 + 成功标准核验 + 决策

**Files:**
- 无新代码，运行 Task 3 的脚本

- [ ] **Step 1: 跑全量回测 2018-01 ~ 2026-08**

```bash
cd .claude/skills/chaodiefantan && python -m backtest.grid_backtest --start 2018-01-02 --end 2026-08-07 2>&1 | tail -45
```
> 全量拉 ~5300 只 × 8 年 K 线 + 36 组扫描。数据缓存命中后主要是扫描耗时（tail 优化后秒级/组）。预计首次拉数据 20-40 分钟（取决于网络），扫描 < 5 分钟。

- [ ] **Step 2: 读取报告核验成功标准**

```bash
cat docs/band_grid_2018-01-02_2026-08-07.md
```
核验 spec §5 四项（对每组合）：
1. 正期望：平均净收益 > 0 且 期望(胜率×盈亏比) > 1
2. 信号 ≥ 50
3. 2018/2022 单年期望 > -3%（**回答"无开关熊市亏不亏"**）
4. 报告已标 ✅/❌

- [ ] **Step 3: 按结果决策（spec §6）**

- 若有达标组合 → 选最优，**记录是否需要开关**（看无开关组熊市是否暴亏）；进入阶段 2（新 skill 落地，另起 plan）
- 若无开关组在熊市暴亏但有开关组达标 → 加开关（用数据替我劝用户）
- **若含T日口径(use_t1_drop=False)全不达标** → 给 `grid_backtest.py` 的 `_eval_combo`/`scan_band_signals` 调用补传 `use_t1_drop=True`，**重跑不含T日口径**(spec §3 对比项: close[T-1]/close[T-21]，避免 T 日反弹抵消跌幅)，重跑 Step 1-2 再决策
- 两种口径都不达标 → **诚实报告放弃，禁止降阈值凑正期望**

- [ ] **Step 4: 清理临时诊断脚本**

```bash
git rm .claude/skills/chaodiefantan/diagnose_zero.py
```
（diagnose_zero.py 是 brainstorming 前的诊断工具，逻辑已沉淀到 band_signal.py + 测试，删除避免遗留）

- [ ] **Step 5: Commit 回测结果报告**

```bash
git add docs/band_grid_2018-01-02_2026-08-07.md
git commit -m "docs(chaodiefantan): 波段超跌信号2018-2026全量网格回测结果

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 实施完成后

回到主对话，依据报告结果决策：
- 达标 → 和用户确认最优组合（含开关取舍），启动阶段 2（新 skill 落地，另起 brainstorm/plan）
- 不达标 → 诚实汇报，讨论是否调整方向或放弃
