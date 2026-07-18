# 超跌反弹策略回测系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 2024-01~2026-07 全市场超跌反弹信号的事件驱动回测系统，产出 4 目标有效性报告。

**Architecture:** 逐日事件循环——data_loader 用 akshare 拉前复权/不复权日K并缓存 parquet → signal_scan 逐日切片复用现有 `is_oversold_rebound` 纯函数判定信号并去重 → simulator 模拟纪律退出（硬止损+被动跟踪+10日强平）→ report 聚合 4 目标渲染 markdown。纯函数 TDD，网络层小样本验证。

**Tech Stack:** Python 3.10 / pandas / pyarrow(parquet) / akshare(东财前复权) / pytest / 新浪(股票池+市值+指数)

**Spec:** `docs/superpowers/specs/2026-07-18-chaodiefantan-backtest-design.md`
**Branch:** `chaodiefantan-backtest`

**数据类型约定（贯穿全部任务，保持一致）：**
- 标准化 bar：`{date:str("YYYY-MM-DD"), open:float, high:float, low:float, close:float, volume:float}`
- signal：`{signal_date, code, name, close_T, stop_loss, drop5, vol_ratio, market_cap_T}`
- simulate_exit 返回：`{exit_reason:"stop_loss"|"trailing"|"timeout"|"data_end", exit_date, exit_price, hold_days}`
- trade（报告层组装）：signal 字段 + exit_* + `return_gross / return_net / return_slip / mode`

**测试运行方式：** 所有 pytest 命令在 `.claude/skills/chaodiefantan/` 目录下执行（使 `screener` / `backtest` 可导入）。

---

## Task 1: 项目骨架 + 依赖声明

**Files:**
- Create: `.claude/skills/chaodiefantan/backtest/__init__.py`
- Create: `.claude/skills/chaodiefantan/backtest/tests/__init__.py`
- Modify: `.claude/skills/chaodiefantan/requirements.txt`

- [ ] **Step 1: 建目录与 __init__.py**

创建空文件 `.claude/skills/chaodiefantan/backtest/__init__.py`，内容：
```python
"""超跌反弹策略回测系统。"""
```
创建空文件 `.claude/skills/chaodiefantan/backtest/tests/__init__.py`（空文件即可）。

- [ ] **Step 2: 更新 requirements.txt**

把 `.claude/skills/chaodiefantan/requirements.txt` 改为：
```
pandas>=2.0.0
requests>=2.28.0
akshare>=1.10.0
pyarrow>=14.0.0
```

- [ ] **Step 3: smoke 测试验证 import 链路**

创建 `.claude/skills/chaodiefantan/backtest/tests/test_smoke.py`：
```python
"""骨架 import 冒烟测试。"""


def test_import_analyzer():
    from screener.analyzer import is_oversold_rebound
    assert callable(is_oversold_rebound)


def test_backtest_pkg():
    import backtest  # noqa: F401
    assert True
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_smoke.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/ .claude/skills/chaodiefantan/requirements.txt
git commit -m "feat(chaodiefantan): 回测系统骨架+依赖声明"
```

---

## Task 2: simulator.py — 纪律退出模拟（核心纯函数）

**Files:**
- Create: `.claude/skills/chaodiefantan/backtest/simulator.py`
- Test: `.claude/skills/chaodiefantan/backtest/tests/test_simulator.py`

这是回测引擎核心，TDD。退出逻辑见 spec §6.2。

- [ ] **Step 1: 写失败测试**

创建 `.claude/skills/chaodiefantan/backtest/tests/test_simulator.py`：
```python
"""纪律退出模拟单测 — 构造 K 线验三种出场。"""
from backtest.simulator import simulate_exit


def _bar(date, open_, close, high, low, volume=100):
    return {"date": date, "open": open_, "close": close, "high": high, "low": low, "volume": volume}


def _base_bars():
    """买入日 T + 之后若干日。buy_price=10.0, stop_loss=9.0(固定T-1最低)。"""
    return [
        _bar("2024-03-11", 9.5, 10.0, 10.2, 9.4),   # bars[0]=买入日T, 不判定
        _bar("2024-03-12", 10.0, 10.5, 10.6, 9.9),   # T+1
        _bar("2024-03-13", 10.5, 10.8, 11.0, 10.4),  # T+2
    ]


def test_stop_loss_triggered():
    """① 硬止损: T+1 当日 low<=stop_loss(9.0) -> 以 stop_loss 出局。"""
    bars = _base_bars()
    bars[1]["low"] = 8.8  # 盘中砸穿 stop_loss
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0)
    assert r["exit_reason"] == "stop_loss"
    assert r["exit_price"] == 9.0
    assert r["hold_days"] == 1
    assert r["exit_date"] == "2024-03-12"


def test_trailing_exit():
    """② 被动跟踪: T+2 close < T+1 low -> 以 T+2 close 出局。"""
    bars = _base_bars()
    # T+1 close=10.5 low=9.9; T+2 close 跌破 9.9
    bars[2]["close"] = 9.8
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0)
    assert r["exit_reason"] == "trailing"
    assert r["exit_price"] == 9.8
    assert r["hold_days"] == 2


def test_first_day_trailing():
    """② T+1 当天 close<T日low(买入日)即出局(基准=买入日low)。"""
    bars = _base_bars()
    bars[1]["close"] = 9.3  # < bars[0].low=9.4
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0)
    assert r["exit_reason"] == "trailing"
    assert r["hold_days"] == 1


def test_stop_loss_priority_over_trailing():
    """①②同日: low<=stop_loss 且 close<前日low -> 止损优先(以stop_loss价)。"""
    bars = _base_bars()
    bars[1]["low"] = 8.5    # 触发①
    bars[1]["close"] = 9.0  # 同时<T日low(9.4) 触发②
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0)
    assert r["exit_reason"] == "stop_loss"
    assert r["exit_price"] == 9.0


def test_timeout_force_close():
    """③ 持满10日未触发 -> 第10日(T+10)收盘强平。"""
    bars = [_bar(f"2024-03-{11+i:02d}", 10.0, 10.1, 10.3, 9.9) for i in range(12)]
    # 全程 low>9.0, close>=前日low(9.9), 不触发①②
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0, max_hold=10)
    assert r["exit_reason"] == "timeout"
    assert r["hold_days"] == 10
    assert r["exit_price"] == bars[10]["close"]


def test_data_end_before_hold():
    """K线在持有期内结束(数据不足) -> 以最后一根收盘,标记data_end。"""
    bars = _base_bars()  # 只有3根(T/T+1/T+2)
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0, max_hold=10)
    assert r["exit_reason"] == "data_end"
    assert r["hold_days"] == 2
    assert r["exit_date"] == "2024-03-13"


def test_buy_day_not_judged():
    """买入日(T)当天不判定(low下穿也不出场)。"""
    bars = _base_bars()
    bars[0]["low"] = 7.0  # 买入日盘中破stop_loss,但当天不判
    bars[1]["close"] = 10.5
    bars[2]["close"] = 11.0
    bars += [_bar("2024-03-14", 11.0, 11.1, 11.2, 10.9) for _ in range(9)]
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0, max_hold=10)
    assert r["exit_reason"] == "timeout"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_simulator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.simulator'`

- [ ] **Step 3: 写实现**

创建 `.claude/skills/chaodiefantan/backtest/simulator.py`：
```python
"""纪律退出模拟纯函数 — 硬止损① + 被动跟踪② + 10日强平③。

输入买入日起的日K(bars[0]=买入日T)，逐日判定出场。TDD 可单测。
详见 spec §6.2。
"""
MAX_HOLD_DAYS = 10


def simulate_exit(bars: list[dict], buy_price: float, stop_loss: float,
                  max_hold: int = MAX_HOLD_DAYS) -> dict:
    """模拟纪律退出。

    Args:
        bars: 买入日起的日K(按日期正序)，bars[0]=买入日T(不判定)，bars[1]=T+1…。
              每项需含 date/open/high/low/close。
        buy_price: 买入价(T日收盘 或 T+1开盘)。
        stop_loss: 硬止损位(信号日 T-1 最低，固定值)。
        max_hold: 最大持有交易日数(默认10)，含买入日算第0日。

    Returns:
        {exit_reason, exit_date, exit_price, hold_days}
        exit_reason ∈ {'stop_loss','trailing','timeout','data_end'}
        hold_days = 从买入日算起的出场日序号(T+1出场=1)。
    """
    if len(bars) < 2:
        return {"exit_reason": "data_end",
                "exit_date": bars[0]["date"] if bars else None,
                "exit_price": bars[0]["close"] if bars else buy_price,
                "hold_days": 0}

    last_idx = min(max_hold, len(bars) - 1)

    for i in range(1, len(bars)):               # 从 T+1 起
        bar = bars[i]
        prev_low = bars[i - 1]["low"]
        # ① 硬止损: 盘中触及即以 stop_loss 出局(不看收盘)
        if bar["low"] <= stop_loss:
            return {"exit_reason": "stop_loss", "exit_date": bar["date"],
                    "exit_price": stop_loss, "hold_days": i}
        # ② 被动跟踪: 收盘跌破前一日最低 -> 当日收盘出局
        if bar["close"] < prev_low:
            return {"exit_reason": "trailing", "exit_date": bar["date"],
                    "exit_price": bar["close"], "hold_days": i}
        # ③ 持满 max_hold 日强平
        if i >= max_hold:
            return {"exit_reason": "timeout", "exit_date": bar["date"],
                    "exit_price": bar["close"], "hold_days": i}

    # 数据在持有期内结束(K线不够)
    last = bars[-1]
    return {"exit_reason": "data_end", "exit_date": last["date"],
            "exit_price": last["close"], "hold_days": len(bars) - 1}
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_simulator.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/simulator.py .claude/skills/chaodiefantan/backtest/tests/test_simulator.py
git commit -m "feat(chaodiefantan): 纪律退出模拟simulator(硬止损+被动跟踪+强平)"
```

---

## Task 3: market_cap.py — 流通股本 + 历史市值估算

**Files:**
- Create: `.claude/skills/chaodiefantan/backtest/market_cap.py`
- Test: `.claude/skills/chaodiefantan/backtest/tests/test_market_cap.py`

- [ ] **Step 1: 写失败测试**

创建 `.claude/skills/chaodiefantan/backtest/tests/test_market_cap.py`：
```python
"""市值估算纯函数单测。"""
from backtest.market_cap import compute_float_shares, estimate_cap_yi, in_cap_band


def test_compute_float_shares():
    # 流通市值 150 亿, 收盘价 15 元 -> 股本 10 亿股
    assert compute_float_shares(cap_yi=150.0, close=15.0) == 1_000_000_000.0


def test_estimate_cap_yi():
    # 股本 10 亿股, 历史不复权价 12 元 -> 市值 120 亿
    assert estimate_cap_yi(close_unadj=12.0, float_shares=1_000_000_000.0) == 120.0


def test_in_cap_band():
    assert in_cap_band(50.0) is True
    assert in_cap_band(500.0) is True
    assert in_cap_band(49.9) is False
    assert in_cap_band(500.1) is False
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_market_cap.py -v`
Expected: FAIL `No module named 'backtest.market_cap'`

- [ ] **Step 3: 写实现**

创建 `.claude/skills/chaodiefantan/backtest/market_cap.py`：
```python
"""流通股本与历史市值估算 — 纯函数。

市值过滤口径 50-500 亿(流通市值)。股本视为 2.5 年常数(忽略解禁/增发)。
详见 spec §4.3。
"""
from screener.analyzer import MARKET_CAP_MIN, MARKET_CAP_MAX  # 50 / 500

_WAN_TO_YI = 1_0000  # 万元→亿元(kangdie fetcher 已转亿元,这里不用)


def compute_float_shares(cap_yi: float, close: float) -> float:
    """流通股本(股) = 流通市值(亿元)×1e8 ÷ 收盘价(元)。"""
    return cap_yi * 1e8 / close


def estimate_cap_yi(close_unadj: float, float_shares: float) -> float:
    """历史流通市值(亿元) = 不复权收盘价 × 流通股本 ÷ 1e8。"""
    return close_unadj * float_shares / 1e8


def in_cap_band(cap_yi: float) -> bool:
    """是否落在 50-500 亿市值带。"""
    return MARKET_CAP_MIN <= cap_yi <= MARKET_CAP_MAX
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_market_cap.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/market_cap.py .claude/skills/chaodiefantan/backtest/tests/test_market_cap.py
git commit -m "feat(chaodiefantan): 流通股本+历史市值估算"
```

---

## Task 4: signal_scan.py — 信号去重（纯函数）

**Files:**
- Modify: `.claude/skills/chaodiefantan/backtest/signal_scan.py` (Create)
- Test: `.claude/skills/chaodiefantan/backtest/tests/test_signal_scan.py`

- [ ] **Step 1: 写失败测试（去重部分）**

创建 `.claude/skills/chaodiefantan/backtest/tests/test_signal_scan.py`：
```python
"""信号扫描与去重单测。"""
from backtest.signal_scan import dedup_signals


TRADING_DATES = [f"2024-03-{d:02d}" for d in range(11, 21)]  # 10个交易日


def _sig(code, date):
    return {"signal_date": date, "code": code, "name": code,
            "close_T": 10.0, "stop_loss": 9.0, "drop5": -18.0,
            "vol_ratio": 2.0, "market_cap_T": 100.0}


def test_dedup_same_stock_within_window():
    """同股5日内重复信号只留最早。"""
    sigs = [_sig("000001", "2024-03-11"), _sig("000001", "2024-03-13")]  # 差2日<=5
    out = dedup_signals(sigs, TRADING_DATES, window=5)
    assert len(out) == 1
    assert out[0]["signal_date"] == "2024-03-11"


def test_dedup_keep_after_window():
    """同股超过5日再触发,保留。"""
    sigs = [_sig("000001", "2024-03-11"), _sig("000001", "2024-03-18")]  # 差5个交易日index=7>5? 实际index差5
    # TRADING_DATES: 03-11(idx0)...03-18(idx5), 差5 <=5 应去重
    out = dedup_signals(sigs, TRADING_DATES, window=5)
    assert len(out) == 1
    # 03-19(idx6) 差6>5 保留
    sigs2 = [_sig("000001", "2024-03-11"), _sig("000001", "2024-03-19")]
    out2 = dedup_signals(sigs2, TRADING_DATES, window=5)
    assert len(out2) == 2


def test_dedup_different_stocks_independent():
    """不同股票互不影响。"""
    sigs = [_sig("000001", "2024-03-11"), _sig("000002", "2024-03-11")]
    out = dedup_signals(sigs, TRADING_DATES, window=5)
    assert len(out) == 2


def test_dedup_unsorted_input():
    """输入乱序也能正确去重(内部按code+date排序)。"""
    sigs = [_sig("000001", "2024-03-13"), _sig("000001", "2024-03-11")]
    out = dedup_signals(sigs, TRADING_DATES, window=5)
    assert len(out) == 1
    assert out[0]["signal_date"] == "2024-03-11"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_signal_scan.py -v`
Expected: FAIL `No module named 'backtest.signal_scan'`

- [ ] **Step 3: 写实现（去重部分，scan 占位下个任务填）**

创建 `.claude/skills/chaodiefantan/backtest/signal_scan.py`：
```python
"""信号扫描与去重 — 逐日切片复用 is_oversold_rebound 判定信号,同波去重。

去重: 同股 window 个交易日内重复信号只留最早一个(同一波反弹)。
"""
from screener.analyzer import is_oversold_rebound

DEDUP_WINDOW = 5  # 同股去重窗口(交易日)


def dedup_signals(signals: list[dict], trading_dates: list[str],
                  window: int = DEDUP_WINDOW) -> list[dict]:
    """同股 window 个交易日内的信号只保留最早一个。

    Args:
        signals: 信号列表(可乱序)。
        trading_dates: 全局交易日序列(升序),用于算交易日 index 差。
        window: 去重窗口(交易日数)。
    """
    date_idx = {d: i for i, d in enumerate(trading_dates)}
    ordered = sorted(signals, key=lambda s: (s["code"], s["signal_date"]))
    result: list[dict] = []
    last_date_by_code: dict[str, str] = {}
    for s in ordered:
        code, d = s["code"], s["signal_date"]
        if d not in date_idx:
            continue  # 信号日不在交易日序列(异常),丢弃
        last = last_date_by_code.get(code)
        if last is not None and date_idx[d] - date_idx[last] <= window:
            continue  # 同波,跳过
        result.append(s)
        last_date_by_code[code] = d
    return result
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_signal_scan.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/signal_scan.py .claude/skills/chaodiefantan/backtest/tests/test_signal_scan.py
git commit -m "feat(chaodiefantan): 信号去重逻辑(同波5日窗口)"
```

---

## Task 5: signal_scan.py — 逐日扫描（scan_signals）

**Files:**
- Modify: `.claude/skills/chaodiefantan/backtest/signal_scan.py`
- Modify: `.claude/skills/chaodiefantan/backtest/tests/test_signal_scan.py`

- [ ] **Step 1: 追加 scan_signals 测试**

在 `test_signal_scan.py` 顶部 import 改为：
```python
from backtest.signal_scan import dedup_signals, scan_signals
from backtest.market_cap import compute_float_shares
```
并在文件末尾追加：
```python
def _make_kline():
    """构造一只股 7 日前复权K线,末日(T)满足超跌反弹。
    市值: close_T=10.5, 股本算成市值落在50-500亿。
    用与 test_analyzer._good_bars 类似形态。
    """
    bars = []
    for d in ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"]:
        bars.append({"date": d, "open": 12.5, "close": 12.5, "high": 13.0, "low": 12.0, "volume": 100})
    bars.append({"date": "2024-03-11", "open": 10.0, "close": 9.0, "high": 10.5, "low": 7.0, "volume": 50})   # T-1
    bars.append({"date": "2024-03-12", "open": 9.2, "close": 10.5, "high": 11.0, "low": 9.0, "volume": 100})  # T 阳包阴
    return bars


def test_scan_signals_finds_signal():
    bars = _make_kline()
    float_shares = compute_float_shares(cap_yi=200.0, close=10.5)  # 让市值=200亿
    sigs = scan_signals(
        klines_by_code={"000001": bars},
        float_shares_by_code={"000001": float_shares},
        names_by_code={"000001": "测试股"},
        trading_dates=["2024-03-12"],
    )
    assert len(sigs) == 1
    s = sigs[0]
    assert s["code"] == "000001"
    assert s["signal_date"] == "2024-03-12"
    assert s["stop_loss"] == 7.0
    assert 50 <= s["market_cap_T"] <= 500


def test_scan_signals_skips_when_cap_out_of_band():
    bars = _make_kline()
    float_shares = compute_float_shares(cap_yi=200.0, close=10.5)
    # 但历史市值用极小股本 -> 落在带外
    sigs = scan_signals(
        klines_by_code={"000001": bars},
        float_shares_by_code={"000001": 1_000_000.0},  # 极小股本->市值<50亿
        names_by_code={"000001": "测试股"},
        trading_dates=["2024-03-12"],
    )
    assert len(sigs) == 0


def test_scan_signals_insufficient_history():
    """T 日之前不足 6 根(无法算 drop5) -> 不出信号。"""
    bars = _make_kline()[:6]  # 砍掉最早一根,只剩6根(含T),closes[-6]会越界→is_oversold_rebound返回None或不足
    float_shares = compute_float_shares(cap_yi=200.0, close=10.5)
    sigs = scan_signals(
        klines_by_code={"000001": bars},
        float_shares_by_code={"000001": float_shares},
        names_by_code={"000001": "测试股"},
        trading_dates=[bars[-1]["date"]],
    )
    assert len(sigs) == 0
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_signal_scan.py -v`
Expected: FAIL `cannot import name 'scan_signals'`

- [ ] **Step 3: 实现 scan_signals（追加到 signal_scan.py 末尾）**

在 `.claude/skills/chaodiefantan/backtest/signal_scan.py` 末尾追加（同时在文件顶部 import 区加 `from backtest.market_cap import estimate_cap_yi, in_cap_band`）：
```python
from backtest.market_cap import estimate_cap_yi, in_cap_band  # 顶部import区


def scan_signals(klines_by_code: dict[str, list[dict]],
                 float_shares_by_code: dict[str, float],
                 names_by_code: dict[str, str],
                 trading_dates: list[str],
                 unadj_close_by_code: dict[str, dict[str, float]] | None = None,
                 ) -> list[dict]:
    """逐日逐股扫描超跌反弹信号。

    Args:
        klines_by_code: {code: 前复权日K列表}，每项含 date/open/high/low/close/volume。
        float_shares_by_code: {code: 流通股本(股)}。
        names_by_code: {code: 股票名称}。
        trading_dates: 要扫描的交易日序列(升序)。每个 T 日切片判定。
        unadj_close_by_code: {code: {date: 不复权收盘价}}，用于市值估算。
            若 None 则用前复权 close 近似(有偏差,仅冒烟用)。

    Returns:
        信号列表(未去重)，每项 {signal_date, code, name, close_T, stop_loss,
        drop5, vol_ratio, market_cap_T}。
    """
    signals: list[dict] = []
    date_set = set(trading_dates)

    for code, bars in klines_by_code.items():
        if len(bars) < 7:
            continue
        float_shares = float_shares_by_code.get(code)
        if not float_shares:
            continue
        unadj = (unadj_close_by_code or {}).get(code, {})
        name = names_by_code.get(code, code)

        for i in range(6, len(bars)):                  # bars[i]=候选T日,需之前>=6根
            t_date = bars[i]["date"]
            if t_date not in date_set:
                continue                                # 非回测交易日,跳过
            window = bars[: i + 1]                      # T及之前所有K线
            # 市值估算(优先用不复权价)
            close_unadj = unadj.get(t_date, window[-1]["close"])
            cap_t = estimate_cap_yi(close_unadj, float_shares)
            if not in_cap_band(cap_t):
                continue
            detail = is_oversold_rebound(window, cap_t)
            if detail is None:
                continue
            signals.append({
                "signal_date": t_date,
                "code": code,
                "name": name,
                "close_T": window[-1]["close"],
                "stop_loss": detail["stop_loss"],
                "drop5": detail["drop5"],
                "vol_ratio": detail["vol_ratio"],
                "market_cap_T": round(cap_t, 2),
            })
    return signals
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_signal_scan.py -v`
Expected: 7 passed (4 去重 + 3 扫描)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/signal_scan.py .claude/skills/chaodiefantan/backtest/tests/test_signal_scan.py
git commit -m "feat(chaodiefantan): 逐日信号扫描(复用is_oversold_rebound+市值估算)"
```

---

## Task 6: data_loader.py — akshare 拉取 + parquet 缓存 + WAF 退避

**Files:**
- Create: `.claude/skills/chaodiefantan/backtest/data_loader.py`
- Test: `.claude/skills/chaodiefantan/backtest/tests/test_data_loader.py`

网络层用小样本真实拉取验证（茅台除权日复权连续性），不 mock。

- [ ] **Step 1: 写测试（列名标准化 + parquet 缓存往返 + 茅台复权 sanity）**

创建 `.claude/skills/chaodiefantan/backtest/tests/test_data_loader.py`：
```python
"""数据加载层测试 — 列名标准化/缓存往返/茅台复权sanity。"""
import os
import tempfile

import pandas as pd

from backtest.data_loader import standardize_kline, save_cache, load_cache, fetch_kline


def test_standardize_kline_renames_columns():
    df = pd.DataFrame([{
        "日期": "2024-06-19", "股票代码": "600519", "开盘": 1497.99,
        "收盘": 1501.0, "最高": 1504.0, "最低": 1482.1, "成交量": 41262,
    }])
    out = standardize_kline(df)
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["close"] == 1501.0
    assert out.iloc[0]["date"] == "2024-06-19"


def test_cache_roundtrip(tmp_path):
    df = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "open": [10.0, 10.5],
                       "high": [10.5, 10.8], "low": [9.8, 10.3],
                       "close": [10.2, 10.6], "volume": [100, 200]})
    path = str(tmp_path / "k.parquet")
    save_cache(df, path)
    loaded = load_cache(path)
    assert len(loaded) == 2
    assert loaded.iloc[1]["close"] == 10.6


def test_mtf_dividend_qfq_smooth():
    """茅台 2024-06-19 除权日: 前复权下 6-19 相对 6-18 不应有大跌跳口(不复权约-1.3%)。"""
    df = fetch_kline("600519", start="20240617", end="20240621", adjust="qfq")
    if df is None or len(df) < 3:
        import pytest
        pytest.skip("akshare/东财网络不可用,跳过复权sanity")
    by_date = {r["date"]: r["close"] for _, r in df.iterrows()}
    c18, c19 = by_date.get("2024-06-18"), by_date.get("2024-06-19")
    assert c18 is not None and c19 is not None
    chg = (c19 - c18) / c18 * 100
    # 不复权约-1.3%除权跳口;前复权应消除,chg 在 [-1, 3] 区间(非-1.3以下)
    assert chg > -1.0, f"前复权除权日仍跳口 {chg:.2f}%，复权异常"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_data_loader.py -v`
Expected: FAIL `No module named 'backtest.data_loader'`

- [ ] **Step 3: 写实现**

创建 `.claude/skills/chaodiefantan/backtest/data_loader.py`：
```python
"""数据加载层 — akshare 东财前复权/不复权日K + parquet 缓存 + WAF 退避。

WAF 缓解: 并发≤4、指数退避(1/2/4/8s)、断点续拉、每100只sleep。
详见 spec §4.2。
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd

_COL_MAP = {
    "日期": "date", "开盘": "open", "收盘": "close",
    "最高": "high", "最低": "low", "成交量": "volume",
}


def standardize_kline(df: pd.DataFrame) -> pd.DataFrame:
    """akshare 中文列名 → 标准 {date,open,high,low,close,volume}，按日期升序。"""
    out = df.rename(columns=_COL_MAP)[["date", "open", "high", "low", "close", "volume"]]
    out = out.sort_values("date").reset_index(drop=True)
    return out


def fetch_kline(code: str, start: str, end: str, adjust: str = "qfq",
                retries: int = 3) -> pd.DataFrame | None:
    """拉单只日K。start/end 为 'YYYYMMDD'。adjust: 'qfq'前复权 / ''不复权。

    Returns:
        标准化 DataFrame，或失败返回 None。
    """
    for attempt in range(retries):
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date=start, end_date=end, adjust=adjust)
            if df is None or len(df) == 0:
                return None
            return standardize_kline(df)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)        # 1/2/4s 退避
            else:
                print(f"[data_loader] {code} adjust={adjust} 拉取失败: {e}")
                return None


def save_cache(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)


def load_cache(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


def _fmt(date_str: str) -> str:
    """'2024-01-02' → '20240102'。"""
    return date_str.replace("-", "")


def fetch_all(pool: list[dict], start: str, end: str, adjust: str,
              cache_dir: str, tag: str, max_workers: int = 4,
              sleep_every: int = 100) -> dict[str, pd.DataFrame]:
    """批量拉取全池日K并缓存。断点续拉: 已有缓存则跳过。

    Args:
        pool: [{code, name, ...}] 股票池。
        start/end: 'YYYY-MM-DD'。
        adjust: 'qfq' / ''。
        cache_dir: 缓存目录。
        tag: 缓存子目录名(如 'qfq' / 'unadj')。
    Returns:
        {code: DataFrame}。
    """
    sub_dir = os.path.join(cache_dir, tag)
    os.makedirs(sub_dir, exist_ok=True)
    start_fmt, end_fmt = _fmt(start), _fmt(end)
    result: dict[str, pd.DataFrame] = {}
    todo = []
    for s in pool:
        cache_path = os.path.join(sub_dir, f"{s['code']}.parquet")
        if os.path.exists(cache_path):
            try:
                result[s["code"]] = load_cache(cache_path)
                continue
            except Exception:
                pass
        todo.append((s["code"], cache_path))

    def _task(item):
        code, cache_path = item
        df = fetch_kline(code, start_fmt, end_fmt, adjust=adjust)
        if df is not None:
            save_cache(df, cache_path)
        return code, df

    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_task, it): it[0] for it in todo}
        for fut in as_completed(futs):
            code, df = fut.result()
            if df is not None:
                result[code] = df
            done += 1
            if done % sleep_every == 0:
                time.sleep(0.3)
                print(f"[data_loader] {tag}: {done}/{len(todo)}", flush=True)
    return result


def prefetch_waf_check(pool: list[dict], start: str, end: str,
                       sample: int = 50) -> float:
    """正式拉取前 WAF 预测试: 连拉 sample 只,返回成功率。<0.8 则中止。"""
    import random
    sample_pool = pool if len(pool) <= sample else random.sample(pool, sample)
    ok = 0
    start_fmt, end_fmt = _fmt(start), _fmt(end)
    for s in sample_pool:
        df = fetch_kline(s["code"], start_fmt, end_fmt, adjust="qfq")
        if df is not None and len(df) > 0:
            ok += 1
    rate = ok / len(sample_pool) if sample_pool else 0
    print(f"[data_loader] WAF 预测试成功率: {ok}/{len(sample_pool)} = {rate:.0%}",
          flush=True)
    return rate
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_data_loader.py -v`
Expected: 3 passed（第三个若东财网络不可用会 skip，非 fail）

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/data_loader.py .claude/skills/chaodiefantan/backtest/tests/test_data_loader.py
git commit -m "feat(chaodiefantan): akshare数据加载层(parquet缓存+WAF退避+列名标准化)"
```

---

## Task 7: report.py — 4 目标聚合 + markdown 渲染

**Files:**
- Create: `.claude/skills/chaodiefantan/backtest/report.py`
- Test: `.claude/skills/chaodiefantan/backtest/tests/test_report.py`

- [ ] **Step 1: 写测试（聚合指标 + 渲染含关键章节）**

创建 `.claude/skills/chaodiefantan/backtest/tests/test_report.py`：
```python
"""报告聚合与渲染测试。"""
from backtest.report import compute_trade_returns, aggregate_overall, render_markdown


def _trade(exit_price, buy_price, exit_reason="trailing", hold_days=2,
           market_cap_T=120.0, mode="close"):
    return {"buy_price": buy_price, "exit_price": exit_price,
            "exit_reason": exit_reason, "hold_days": hold_days,
            "market_cap_T": market_cap_T, "mode": mode,
            "code": "000001", "signal_date": "2024-03-12"}


def test_compute_trade_returns_gross_and_net():
    t = _trade(exit_price=10.6, buy_price=10.0)
    r = compute_trade_returns(t, fee=0.0008)
    # 毛收益 (10.6-10)/10 = 6%
    assert abs(r["return_gross"] - 6.0) < 0.01
    # 净收益 = 6% - (10+10.6)/10 * 0.0008*100 = 6 - 0.1648 ≈ 5.84
    assert r["return_net"] < r["return_gross"]
    assert r["return_net"] > 5.5


def test_aggregate_overall_metrics():
    trades = [
        compute_trade_returns(_trade(10.6, 10.0), 0.0008),   # 盈
        compute_trade_returns(_trade(9.5, 10.0), 0.0008),    # 亏
    ]
    agg = aggregate_overall(trades)
    assert agg["n"] == 2
    assert agg["wins"] == 1
    assert agg["win_rate"] == 50.0
    assert agg["avg_hold"] == 2.0
    # 盈亏比 = 平均盈/平均亏绝对值
    assert agg["payoff"] > 0


def test_render_markdown_has_four_sections():
    trades = [compute_trade_returns(_trade(10.6, 10.0), 0.0008)]
    md = render_markdown(
        overall=aggregate_overall(trades),
        overall_open={"n": 1, "win_rate": 100.0, "avg_ret_net": 5.8,
                       "payoff": 0, "avg_hold": 2.0, "max_drawdown": 0,
                       "wins": 1, "avg_ret_gross": 6.0},
        elasticity={"hold_1": 1.0, "hold_3": 2.0, "hold_5": 1.5, "hold_10": 0.8,
                    "mfe": 3.0, "mae": -2.0, "avg_hold": 2.0, "n": 1},
        cap_groups={},
        fit={"total_signals": 1, "per_day": 0.0, "avg_hold": 2.0,
             "stop_loss_share": 0.0, "stop_loss_saved": 0.0,
             "trading_days": 600},
        benchmark_ret=10.0,
        biases=[],
    )
    assert "一、策略整体有效性" in md
    assert "二、信号弹性" in md
    assert "三、市值阈值" in md
    assert "四、与实盘契合度" in md
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_report.py -v`
Expected: FAIL `No module named 'backtest.report'`

- [ ] **Step 3: 写实现**

创建 `.claude/skills/chaodiefantan/backtest/report.py`：
```python
"""报告聚合 + markdown 渲染 — 4 目标对应章节。详见 spec §7。"""

FEE_NET = 0.0008       # 净费(印花0.05%卖+双边万2.5佣金+过户)
FEE_SLIP = 0.002       # 含滑点保守
CAP_BANDS = [(0, 50), (50, 100), (100, 300), (300, 500), (500, float("inf"))]


def compute_trade_returns(trade: dict, fee: float = FEE_NET) -> dict:
    """计算单笔毛/净收益率(%)。fee 按双边(买额+卖额)×fee 扣。"""
    buy, exit_ = trade["buy_price"], trade["exit_price"]
    ret_gross = (exit_ - buy) / buy * 100
    cost_pct = (buy + exit_) / buy * fee * 100     # 双边费占买入价比
    out = dict(trade)
    out["return_gross"] = ret_gross
    out["return_net"] = ret_gross - cost_pct
    return out


def aggregate_overall(trades: list[dict]) -> dict:
    """整体有效性聚合: 胜率/盈亏比/平均持有/最大单笔回撤。"""
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0, "payoff": 0, "avg_hold": 0,
                "avg_ret_net": 0, "avg_ret_gross": 0, "max_drawdown": 0, "wins": 0}
    rets = [t["return_net"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    payoff = avg_win / avg_loss if avg_loss > 0 else float("inf") if wins else 0
    return {
        "n": n,
        "wins": len(wins),
        "win_rate": len(wins) / n * 100,
        "payoff": round(payoff, 2),
        "avg_hold": round(sum(t["hold_days"] for t in trades) / n, 2),
        "avg_ret_net": round(sum(rets) / n, 2),
        "avg_ret_gross": round(sum(t["return_gross"] for t in trades) / n, 2),
        "max_drawdown": round(min(rets), 2) if rets else 0,
    }


def aggregate_by_cap(trades: list[dict]) -> dict:
    """按市值分带聚合(各带 n/胜率/盈亏比/平均净收益)。"""
    out = {}
    for lo, hi in CAP_BANDS:
        sub = [t for t in trades if lo <= t.get("market_cap_T", 0) < hi]
        if not sub:
            out[f"{lo}-{hi}"] = {"n": 0}
            continue
        agg = aggregate_overall(sub)
        out[f"{lo}-{hi}"] = agg
    return out


def render_markdown(overall: dict, overall_open: dict, elasticity: dict,
                    cap_groups: dict, fit: dict, benchmark_ret: float,
                    biases: list[dict]) -> str:
    """渲染 4 目标 markdown 报告。"""
    L = []
    L.append("# 超跌反弹策略回测报告（2024-01 ~ 2026-07）\n")
    L.append("> 探索性小样本分析，结论非统计显著。详见偏差声明。\n")

    # 一、整体有效性
    L.append("## 一、策略整体有效性（主口径：T日收盘买入）\n")
    o = overall
    if o["n"] == 0:
        L.append("无信号。\n")
    else:
        L.append(f"- 信号数: **{o['n']}**  | 胜率: **{o['win_rate']:.0f}%**  | "
                 f"盈亏比: **{o['payoff']}**  | 平均持有: **{o['avg_hold']}日**")
        L.append(f"- 平均每笔净收益: **{o['avg_ret_net']:+.2f}%**  "
                 f"(毛 {o['avg_ret_gross']:+.2f}%)  | 最大单笔回撤: **{o['max_drawdown']:.2f}%**")
        L.append(f"- vs 创业板指同期: **{benchmark_ret:+.2f}%**")
        oo = overall_open
        L.append(f"\n**对照口径（T+1开盘买入）**: n={oo.get('n',0)} "
                 f"胜率 {oo.get('win_rate',0):.0f}% 平均净收益 {oo.get('avg_ret_net',0):+.2f}% "
                 f"(差异大=信号次日普遍高开吞噬收益)")

    # 二、信号弹性
    L.append("\n## 二、信号弹性与最佳持有期\n")
    e = elasticity
    if e.get("n", 0):
        L.append(f"- 固定持有 1/3/5/10 日平均收益: "
                 f"{e['hold_1']:+.2f}% / {e['hold_3']:+.2f}% / "
                 f"{e['hold_5']:+.2f}% / {e['hold_10']:+.2f}%")
        L.append(f"- MFE(平均最大涨幅) **{e['mfe']:+.2f}%** / "
                 f"MAE(平均最大回撤) **{e['mae']:+.2f}%**")
        L.append(f"- 平均实际持有: **{overall['avg_hold']:.1f}日** "
                 f"(短=印证反弹多一日游)")

    # 三、市值阈值
    L.append("\n## 三、市值阈值合理性（分市值带）\n")
    L.append("| 市值带(亿) | 笔数 | 胜率 | 盈亏比 | 平均净收益 |")
    L.append("|---|---|---|---|---|")
    for band, agg in cap_groups.items():
        if agg.get("n", 0) == 0:
            L.append(f"| {band} | 0 | — | — | — |")
        else:
            L.append(f"| {band} | {agg['n']} | {agg['win_rate']:.0f}% | "
                     f"{agg['payoff']} | {agg['avg_ret_net']:+.2f}% |")

    # 四、契合度
    L.append("\n## 四、与实盘契合度\n")
    f = fit
    L.append(f"- 2.5年信号总数 **{f['total_signals']}** ≈ 日均 **{f['per_day']:.2f}个** "
             f"(交易日{f['trading_days']})")
    L.append(f"- 平均持有 **{f['avg_hold']:.1f}日** → 年化换手强度评估")
    L.append(f"- 硬止损①触发占比 **{f['stop_loss_share']:.0%}**，"
             f"避免损失约 **{f['stop_loss_saved']:+.2f}%**/笔")
    L.append("\n> 结合用户'过度交易/不止损/补仓'画像: 信号频率与换手是否助长过度交易，"
             "见正文评估。")

    # 偏差声明
    if biases:
        L.append("\n## 已知偏差声明\n")
        L.append("| 偏差 | 方向 | 说明 |")
        L.append("|---|---|---|")
        for b in biases:
            L.append(f"| {b['name']} | {b['direction']} | {b['note']} |")

    return "\n".join(L)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/test_report.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/report.py .claude/skills/chaodiefantan/backtest/tests/test_report.py
git commit -m "feat(chaodiefantan): 报告聚合+markdown渲染(4目标+偏差声明)"
```

---

## Task 8: backtest_main.py — 编排 + 端到端冒烟

**Files:**
- Create: `.claude/skills/chaodiefantan/backtest/backtest_main.py`
- Modify: `.claude/skills/chaodiefantan/backtest/tests/test_data_loader.py` (无需改)

编排串联全流程。先用极小样本（5 只股、3 个月）冒烟，再 Task 9 全量。

- [ ] **Step 1: 写实现**

创建 `.claude/skills/chaodiefantan/backtest/backtest_main.py`：
```python
"""回测编排入口 — 串联数据→信号→模拟→报告。

用法:
    python -m backtest.backtest_main                 # 全量(2024-01~2026-07)
    python -m backtest.backtest_main --smoke         # 小样本冒烟
"""
import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)                     # chaodiefantan/
sys.path.insert(0, SKILL_DIR)

from screener.bridges import (  # noqa: E402  复用 kangdie fetcher
    get_all_stocks_today, get_market_cap_map, get_index_kline)
from backtest.data_loader import fetch_all, prefetch_waf_check, load_cache  # noqa: E402
from backtest.market_cap import compute_float_shares, estimate_cap_yi  # noqa: E402
from backtest.signal_scan import scan_signals, dedup_signals  # noqa: E402
from backtest.simulator import simulate_exit  # noqa: E402
from backtest.report import (  # noqa: E402
    compute_trade_returns, aggregate_overall, aggregate_by_cap,
    render_markdown, FEE_NET, FEE_SLIP)

START = "2024-01-02"
END = "2026-07-17"
FETCH_START = "2023-09-01"                            # 留 70 日 buffer
MAX_HOLD = 10
CACHE_DIR = os.path.join(HERE, "data")
REPORT_PATH = os.path.join(
    SKILL_DIR, "..", "..", "..", "docs",
    "chaodiefantan_backtest_2024-01_2026-07.md")


def load_pool_and_shares():
    """股票池(新浪) + 当前流通股本。"""
    df = get_all_stocks_today()
    if df.empty:
        raise RuntimeError("全A行情为空(非交易日?)")
    pool = df.to_dict("records")
    cap_map = get_market_cap_map()                   # {code: 流通市值(亿)}
    shares_by_code, names = {}, {}
    for s in pool:
        cap = cap_map.get(s["code"])
        if cap and s["close"] > 0:
            shares_by_code[s["code"]] = compute_float_shares(cap, s["close"])
            names[s["code"]] = s["name"]
    return pool, shares_by_code, names


def build_trades(signals, klines_qfq, mode, max_hold=MAX_HOLD):
    """对信号集模拟退出,合成 trade(含收益率)。mode: 'close'/'open'。"""
    trades = []
    for sig in signals:
        bars = klines_qfq.get(sig["code"], [])
        # 定位买入日(信号日 T)
        buy_idx = next((i for i, b in enumerate(bars)
                        if b["date"] == sig["signal_date"]), None)
        if buy_idx is None:
            continue
        buy_bars = bars[buy_idx:]                     # bars[0]=买入日
        if mode == "open":
            if len(buy_bars) < 2:
                continue
            buy_price = buy_bars[1]["open"]           # T+1 开盘
            sim_bars = buy_bars[1:]                   # 买入日=T+1
        else:
            buy_price = sig["close_T"]                # T 日收盘
            sim_bars = buy_bars
        exit_info = simulate_exit(sim_bars, buy_price, sig["stop_loss"], max_hold)
        trade = {**sig, **exit_info, "buy_price": buy_price, "mode": mode}
        trades.append(compute_trade_returns(trade, FEE_NET))
    return trades


def compute_elasticity(signals, klines_qfq):
    """固定持有 1/3/5/10 日原始收益 + MFE/MAE。"""
    if not signals:
        return {"n": 0}
    rets_by_n = {1: [], 3: [], 5: [], 10: []}
    mfes, maes = [], []
    for sig in signals:
        bars = klines_qfq.get(sig["code"], [])
        buy_idx = next((i for i, b in enumerate(bars)
                        if b["date"] == sig["signal_date"]), None)
        if buy_idx is None:
            continue
        after = bars[buy_idx + 1:]                    # T+1 起
        closes = [b["close"] for b in after]
        base = sig["close_T"]
        for n, lst in rets_by_n.items():
            if len(closes) >= n:
                lst.append((closes[n - 1] - base) / base * 100)
        if closes:
            mfes.append((max(closes[:10]) - base) / base * 100)
            maes.append((min(closes[:10]) - base) / base * 100)
    avg = lambda lst: round(sum(lst) / len(lst), 2) if lst else 0
    return {
        "n": len(signals),
        "hold_1": avg(rets_by_n[1]), "hold_3": avg(rets_by_n[3]),
        "hold_5": avg(rets_by_n[5]), "hold_10": avg(rets_by_n[10]),
        "mfe": avg(mfes), "mae": avg(maes),
        # avg_hold 不在此算(signals 无 hold_days)；报告二章用 overall['avg_hold']
    }


def run(smoke: bool = False):
    print("[1] 股票池+股本 ...", flush=True)
    pool, shares_by_code, names = load_pool_and_shares()
    if smoke:
        pool = pool[:5]
        shares_by_code = {c: shares_by_code[c] for c in [s["code"] for s in pool]}
    print(f"    池: {len(pool)} 只", flush=True)

    print("[2] WAF 预测试 ...", flush=True)
    rate = prefetch_waf_check(pool, FETCH_START, END, sample=10 if smoke else 50)
    if rate < 0.8:
        raise RuntimeError(f"WAF 预测试成功率 {rate:.0%} < 80%，中止(东财限频)")

    print("[3] 拉取前复权+不复权 K线 ...", flush=True)
    klines_qfq = fetch_all(pool, FETCH_START, END, "qfq", CACHE_DIR, "qfq")
    klines_unadj = fetch_all(pool, FETCH_START, END, "", CACHE_DIR, "unadj")

    print("[4] 逐日扫描信号 ...", flush=True)
    dates_q = sorted({b["date"] for kl in klines_qfq.values() for b in kl.to_dict("records")
                      if START <= b["date"] <= END})
    # 不复权收盘价 {code: {date: close}}
    unadj_close = {c: dict(zip(kl["date"], kl["close"]))
                   for c, kl in klines_unadj.items()}
    klines_dict = {c: kl.to_dict("records") for c, kl in klines_qfq.items()}
    raw = scan_signals(klines_dict, shares_by_code, names, dates_q, unadj_close)
    signals = dedup_signals(raw, dates_q)
    print(f"    原始 {len(raw)} → 去重后 {len(signals)} 信号", flush=True)

    print("[5] 模拟退出(双口径) ...", flush=True)
    trades_close = build_trades(signals, klines_dict, "close")
    trades_open = build_trades(signals, klines_dict, "open")

    print("[6] 聚合+渲染 ...", flush=True)
    overall = aggregate_overall(trades_close)
    overall_open = aggregate_overall(trades_open)
    elasticity = compute_elasticity(signals, klines_dict)
    cap_groups = aggregate_by_cap(trades_close)
    # 创业板指基准
    idx = get_index_kline("sz399006", days=800)
    idx_in = [k for k in idx if START <= k["date"] <= END]
    bench_ret = ((idx_in[-1]["close"] - idx_in[0]["close"]) / idx_in[0]["close"] * 100
                 if len(idx_in) >= 2 else 0)
    # 硬止损贡献度
    sl_trades = [t for t in trades_close if t["exit_reason"] == "stop_loss"]
    fit = {
        "total_signals": len(signals), "per_day": len(signals) / max(len(dates_q), 1),
        "avg_hold": overall["avg_hold"], "trading_days": len(dates_q),
        "stop_loss_share": len(sl_trades) / max(len(trades_close), 1),
        "stop_loss_saved": (sum(t["return_net"] for t in sl_trades) / len(sl_trades)
                            if sl_trades else 0),
    }
    biases = [
        {"name": "幸存者偏差", "direction": "高估收益",
         "note": "用当前全A池,已退市/ST股漏掉"},
        {"name": "市值近似", "direction": "部分小盘股误排除",
         "note": "不复权价×当前股本,忽略送转解禁"},
        {"name": "小样本", "direction": "非统计显著",
         "note": f"信号 {len(signals)} 个,探索性分析"},
        {"name": "流动性", "direction": "高估成交质量",
         "note": "假设stop_loss/close价成交,实盘滑点更大"},
    ]
    md = render_markdown(overall, overall_open, elasticity, cap_groups,
                         fit, bench_ret, biases)

    os.makedirs(os.path.dirname(os.path.abspath(REPORT_PATH)), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[done] 报告: {os.path.abspath(REPORT_PATH)}", flush=True)
    print(f"        信号 {len(signals)} | 胜率 {overall['win_rate']:.0f}% | "
          f"平均净收益 {overall['avg_ret_net']:+.2f}% | 基准 {bench_ret:+.2f}%",
          flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="小样本冒烟")
    args = p.parse_args()
    run(smoke=args.smoke)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 端到端冒烟（小样本 5 只）**

Run: `cd .claude/skills/chaodiefantan && PYTHONIOENCODING=utf-8 python -m backtest.backtest_main --smoke`
Expected: 不崩溃，输出 `报告: <path>` + 信号数/胜率/基准。冒烟样本小，信号数可能为 0（正常，5 只股 3 个月难出超跌反弹信号）——重点是不报错、报告文件生成。

- [ ] **Step 3: 验证报告文件生成**

Run: `ls -la ../../../docs/chaodiefantan_backtest_2024-01_2026-07.md`
Expected: 文件存在。打开确认含"一、策略整体有效性"等 4 章标题。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/chaodiefantan/backtest/backtest_main.py
git commit -m "feat(chaodiefantan): 回测编排入口+双口径+基准+端到端冒烟"
```

---

## Task 9: 全量运行 + 报告 + 对账

**Files:**
- Run: 全市场回测
- Verify: 报告对账

- [ ] **Step 1: 全量运行（全市场 2024-01~2026-07）**

Run: `cd .claude/skills/chaodiefantan && PYTHONIOENCODING=utf-8 python -m backtest.backtest_main`
Expected: 拉取 ~5314 只 × 2（前复权+不复权）约 16-40 分钟；输出信号数（预期几十~几百）、胜率、平均净收益、基准。

> 若中途因东财 WAF 中断，重跑同命令——`fetch_all` 有断点续拉（已缓存的 parquet 跳过）。

- [ ] **Step 2: 数据 sanity 检查**

Run: `cd .claude/skills/chaodiefantan && PYTHONIOENCODING=utf-8 python -c "
import pandas as pd
df = pd.read_parquet('backtest/data/qfq/600519.parquet')
sub = df[(df['date']>='2024-06-17')&(df['date']<='2024-06-20')]
print(sub[['date','close']])
print('6-18→6-19 涨幅:', ((sub[sub.date=='2024-06-19'].close.values[0]-sub[sub.date=='2024-06-18'].close.values[0])/sub[sub.date=='2024-06-18'].close.values[0]*100))
"`
Expected: 茅台 6-18→6-19 前复权涨幅 > -1%（除权跳口已消除，印证 §4.1）。

- [ ] **Step 3: 对账抽查（3-5 个信号手工核对）**

打开报告 `docs/chaodiefantan_backtest_2024-01_2026-07.md`，挑 3-5 个信号：
- 核对 signal_date 当日 K 线确为"近5日急跌+T-1缩量长下影+T放量阳包阴"
- 核对 stop_loss = T-1 日最低
- 核对 exit_reason/exit_price 符合退出逻辑

若发现系统性偏差（如 exit_price 与手算不符），回查 simulator/build_trades。

- [ ] **Step 4: 全量测试回归**

Run: `cd .claude/skills/chaodiefantan && python -m pytest backtest/tests/ -v`
Expected: 全部 passed（数据相关 test 可能 skip 东财网络）。

- [ ] **Step 5: Commit 报告**

```bash
git add docs/chaodiefantan_backtest_2024-01_2026-07.md
git commit -m "docs(chaodiefantan): 全量回测报告(2024-01~2026-07)"
```

- [ ] **Step 6: 更新 memory（若有非显而易见的发现）**

若回测产出非显而易见的策略洞察（如"某市值带显著占优"、"信号频率对过度交易的影响量化结论"），写入 memory（type: project）。若结果平平无新洞察，跳过此步。

---

## 完成标准

- [ ] 9 个任务全部 commit，全量测试通过
- [ ] 报告 `docs/chaodiefantan_backtest_2024-01_2026-07.md` 产出，含 4 章 + 偏差声明
- [ ] 茅台除权日复权 sanity 通过（§4.1 印证）
- [ ] 3-5 个信号对账无误
- [ ] 答出 4 目标的核心结论
