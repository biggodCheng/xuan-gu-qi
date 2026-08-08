# boduan(波段)skill 实施计划 — 阶段 2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 把阶段1验证的波段超跌信号(is_band_rebound, 最优 X=30 R=2.5)落地为独立 `boduan` skill,与 chaodiefantan 并行。

**Architecture:** boduan 很薄——SKILL.md + main.py。main.py **复用** 阶段1的 `chaodiefantan/backtest/band_signal.is_band_rebound`(判定) + `chaodiefantan/screener/bridges`(数据层),只写编排(拉数据→判定→存 bd_*.json→展示)。build_candidates 为可 TDD 的纯函数。

**Tech Stack:** Python 3,新浪日K(经 kangdie fetcher,money host),本地 vipdoc 优先。

**Spec:** `docs/superpowers/specs/2026-08-08-boduan-skill-design.md`

---

## 文件结构

- **Create:** `.claude/skills/boduan/SKILL.md` — 触发文档
- **Create:** `.claude/skills/boduan/main.py` — 脚本(build_candidates 纯函数 + run 编排 + main)
- **Create:** `.claude/skills/boduan/tests/test_main.py` — build_candidates 单测
- **输出(gitignore):** `.claude/skills/boduan/data/bd_YYYY-MM-DD.json`
- **复用(不改):** `chaodiefantan/backtest/band_signal.py` / `chaodiefantan/screener/bridges.py` / `scripts/trading_day.py`

---

## Task 1: SKILL.md 触发文档

**Files:** Create `.claude/skills/boduan/SKILL.md`

- [ ] **Step 1: 写 SKILL.md**

```markdown
# boduan — 波段超跌反弹

月度级超跌后的反弹启动信号:**近 20 日跌>30% + T 日放量(2.5×)阳包阴**。捕捉深度超跌后资金进场的反抽,左侧短线,严止损。结果仅作信号参考,**不构成买卖建议**。

## 设计理念

7 月级超跌后,能逆势放量阳包阴的个股,常是反弹启动信号。区别 chaodiefantan(5日急跌+T-1长下影,抓短线反抽),boduan 用**月度窗口+去长下影**,抓更深超跌后的反弹——回测验证信号数 6 倍于 chaodiefantan 且熊市全正。

## 使用方式

输入 `/boduan` 触发。**收盘后跑**(日K类 skill,盘中日K未更新)。

```bash
cd .claude/skills/boduan && python main.py
```
> 全程约 2-8 分钟(全A ~5300 只,20 线程并发拉 OHLCV)。

## 执行步骤

1. 🔴 CHECKPOINT:`ls data/bd_$(date +%Y-%m-%d).json`——已存在则 STOP 询问。
2. 运行:`cd .claude/skills/boduan && python main.py`
3. 脚本:拉全A(过滤ST/新股)+市值(展示)→并发拉 25 日OHLCV→判定 is_band_rebound(X=30,R=2.5)→存 `data/bd_YYYY-MM-DD.json`。
4. 展示候选(代码/名称/收盘/20日跌幅/止损位/量比/市值)+纪律提醒。

## 筛选条件(全满足;不卡市值;不加大盘开关)

| 条件 | 判定 | 含义 |
|------|------|------|
| 近20日深度超跌 | `(close[T]-close[T-20])/close[T-20] <= -30%` | 月度级深度超跌 |
| T 日阳包阴 | `close[T]>open[T] 且 close[T]>open[T-1] 且 high[T]>high[T-1]` | 阳线收复前日开+破前日高 |
| T 日放量 | `vol[T] >= vol[T-1] × 2.5` | 倍量资金进场 |

> 参数固定(回测最优):drop_pct=30 / vol_ratio=2.5 / 不要求T-1缩量 / 不加大盘开关。改参数改 `main.py` 常量。

## 回测依据(2018-2026 全量,31/36 组达标)

最优 X=30 R=2.5:**190 信号 / 胜率 59% / 盈亏比 2.98 / +5.06%**;2018 熊市 +5.90% / 2022 熊市 +1.02%(全正)。对比 chaodiefantan(30 信号/+3.27%):信号 6 倍 + 收益更高。详见 `docs/band_grid_2018-01-02_2026-07-17.md`。

## 纪律(铁律)

- 🛑 **止损**:破 T-1 日最低(stop_loss 字段),**禁止补仓摊平**
- 💰 **止盈**:纪律退出(收盘破前低跟踪 + 10 日强平),反弹是兑现窗口不恋战
- 📊 **仓位**:单只 ≤ 10%
- ⚠️ 只做阳包阴确认的,不抄阴跌股;反弹多一日游,不当中线持有

## ❌ 反例黑名单

| 不要 | 正确做法 |
|---|---|
| 抄底阴跌股(无阳包阴确认) | 只做 T 日阳包阴确认的 |
| 放宽阈值凑数 | count=0 诚实退出 |
| 补仓摊平套牢 | 破 stop_loss 认错 |
| 当中线持有 | 纪律退出兑现 |

## 输出格式

```json
{"date":"...","trigger":{"signal":"band_oversold_rebound"},"count":5,
 "stocks":[{"code":"...","name":"...","close":9.5,"drop20":-32.1,"stop_loss":8.3,"vol_ratio":2.8,"market_cap":80.0}]}
```

## 数据源

复用 kangdie fetcher(chaodiefantan 同源):个股 OHLCV 优先本地招商证券 vipdoc,本地无 fallback 新浪;全A列表+市值走新浪(money host)。前提:客户端「盘后下载日线」。
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/boduan/SKILL.md
git commit -m "feat(boduan): 加波段超跌反弹 skill 触发文档 SKILL.md" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: main.py(build_candidates TDD + run 编排)

**Files:**
- Create: `.claude/skills/boduan/tests/test_main.py`
- Create: `.claude/skills/boduan/main.py`

- [ ] **Step 1: 写失败测试**

Create `.claude/skills/boduan/tests/test_main.py`:

```python
# -*- coding: utf-8 -*-
"""build_candidates 单测 — 波段超跌反弹候选筛选纯函数。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # boduan/
from main import build_candidates


def _bar(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_build_candidates_finds_qualified_skips_unqualified():
    # 合格股: 20日 100→65(跌35%>30%) + T日阳包阴+放量2.5倍
    bars_good = []
    for i in range(20):
        c = 100 - (100 - 65) / 19 * i
        bars_good.append(_bar(f"2024-01-{i+1:02d}", c + 0.5, c + 1, c - 1, c, 1000))
    bars_good.append(_bar("2024-01-21", 65.3, 66.5, 64, 67, 2500))  # close67>open65.3阳, >open[T-1]65.5, high66.5>66, vol2500=2.5×
    # 不合格股: 未超跌(平盘)
    bars_bad = [_bar(f"2024-01-{i+1:02d}", 10, 11, 9, 10, 100) for i in range(21)]

    stocks = [{"code": "001", "name": "合格股", "close": 67, "market_cap": 50.0},
              {"code": "002", "name": "不合格", "close": 10, "market_cap": 50.0}]
    klines = {"001": bars_good, "002": bars_bad}

    cands = build_candidates(stocks, klines, drop_pct=30.0, vol_ratio=2.5)
    assert len(cands) == 1
    assert cands[0]["code"] == "001"
    assert cands[0]["name"] == "合格股"
    assert cands[0]["drop20"] <= -30
    assert cands[0]["stop_loss"] == 64.0       # T-1(bars_good[-2])最低
    assert cands[0]["vol_ratio"] == 2.5
    assert cands[0]["market_cap"] == 50.0


def test_build_candidates_empty_klines_skipped():
    stocks = [{"code": "X", "name": "X", "close": 10, "market_cap": 30.0}]
    assert build_candidates(stocks, {}, drop_pct=30.0, vol_ratio=2.5) == []
```

- [ ] **Step 2: 跑测试验证失败**

```bash
cd .claude/skills/boduan && python -m pytest tests/test_main.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: 实现 main.py**

Create `.claude/skills/boduan/main.py`:

```python
# -*- coding: utf-8 -*-
"""boduan — 波段超跌反弹选股(月度级超跌+放量阳包阴)。

复用 chaodiefantan/backtest/band_signal.is_band_rebound(判定) +
chaodiefantan/screener/bridges(数据层), 不重写。参数固定回测最优 X=30 R=2.5。
独立运行: python main.py
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# 复用 chaodiefantan 的判定 + 数据层 + 项目根 trading_day
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_CHAODIE_DIR = os.path.join(os.path.dirname(_SKILL_DIR), "chaodiefantan")
if os.path.isdir(_CHAODIE_DIR) and _CHAODIE_DIR not in sys.path:
    sys.path.insert(0, _CHAODIE_DIR)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SKILL_DIR)))
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if os.path.isdir(_SCRIPTS_DIR) and _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import trading_day  # noqa: E402
from screener.bridges import (  # noqa: E402  复用 chaodiefantan bridges(数据层)
    get_all_stocks_today, get_stock_kline, get_market_cap_map)
from backtest.band_signal import is_band_rebound  # noqa: E402  阶段1 建成

# 回测最优参数(固定, 改这里即改策略)
DROP_PCT = 30.0          # 近20日跌 > 30%
VOL_RATIO = 2.5          # T日放量 >= 2.5 倍
_KLINE_DAYS = 25         # >= DROP_WINDOW+1=21
_MAX_WORKERS = 20


def build_candidates(stocks: list[dict], klines_map: dict,
                     drop_pct: float = DROP_PCT, vol_ratio: float = VOL_RATIO
                     ) -> list[dict]:
    """逐股判定波段超跌反弹, 返回候选列表(纯函数, 可单测)。

    Args:
        stocks: [{code, name, close, market_cap?}]。
        klines_map: {code: 日K列表}。
        drop_pct/vol_ratio: 透传 is_band_rebound。
    """
    candidates = []
    for s in stocks:
        bars = klines_map.get(s["code"], [])
        detail = is_band_rebound(bars, s.get("market_cap"), drop_pct, vol_ratio)
        if detail:
            candidates.append({
                "code": s["code"], "name": s["name"], "close": s["close"],
                "market_cap": s.get("market_cap"), **detail,
            })
    return candidates


def run(output_dir: str | None = None, date_str: str | None = None) -> bool:
    if output_dir is None:
        output_dir = os.path.join(_SKILL_DIR, "data")
    os.makedirs(output_dir, exist_ok=True)

    start = time.time()
    date_str = date_str or trading_day.latest_trading_day()
    trading_day.warn_if_drift(date_str)
    print(f"[{date_str}] boduan 波段超跌反弹扫描启动...", flush=True)

    print("获取全A股行情...", flush=True)
    stocks_df = get_all_stocks_today()
    if stocks_df.empty:
        print("  未获取到行情数据,可能是非交易日。", flush=True)
        _save(output_dir, date_str, [], trigger={"error": "no_market_data"})
        return False
    stocks = stocks_df.to_dict("records")
    print(f"  共 {len(stocks)} 只。", flush=True)

    print("获取全A市值数据(展示用,不过滤)...", flush=True)
    cap_map = get_market_cap_map()
    for s in stocks:
        cap = cap_map.get(s["code"])
        if cap:
            s["market_cap"] = round(cap, 2)
    print(f"  全A {len(stocks)} 只(已过滤ST/*ST/新股),不卡市值。", flush=True)

    print(f"并发拉取个股 {_KLINE_DAYS} 日OHLCV({_MAX_WORKERS}线程)...", flush=True)
    klines_map: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {executor.submit(get_stock_kline, s["code"], _KLINE_DAYS): s["code"]
                   for s in stocks}
        done = 0
        total = len(stocks)
        for future in as_completed(futures):
            code = futures[future]
            try:
                klines_map[code] = future.result()
            except Exception:
                pass
            done += 1
            if done % 1000 == 0:
                print(f"  OHLCV 已拉取 {done}/{total}...", flush=True)
    print(f"  OHLCV 拉取完成({len(klines_map)} 只有数据)。", flush=True)

    candidates = build_candidates(stocks, klines_map)
    print(f"  波段超跌信号通过:{len(candidates)} 只。", flush=True)

    _save(output_dir, date_str, candidates,
          trigger={"signal": "band_oversold_rebound"})
    elapsed = time.time() - start
    path = os.path.join(output_dir, f"bd_{date_str}.json")
    print(f"完成!波段超跌 {len(candidates)} 只,耗时 {elapsed:.0f} 秒。结果:{path}", flush=True)
    print("  纪律:止损=破T-1最低(stop_loss),纪律退出(跟踪+10日强平),仓位<=10%,"
          "反弹是兑现窗口不恋战。", flush=True)
    return True


def _save(output_dir: str, date_str: str, candidates: list, trigger: dict) -> None:
    out = {"date": date_str, "trigger": trigger,
           "count": len(candidates), "stocks": candidates}
    path = os.path.join(output_dir, f"bd_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: 跑测试验证通过**

```bash
cd .claude/skills/boduan && python -m pytest tests/test_main.py -v
```
Expected: PASS（2 个测试绿）

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/boduan/main.py .claude/skills/boduan/tests/test_main.py
git commit -m "feat(boduan): main.py 复用 is_band_rebound+bridges, build_candidates TDD" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 实跑验证(08-07 收盘数据)

**Files:** 无新代码,运行 main.py

- [ ] **Step 1: 实跑 boduan(08-07 数据已收盘)**

```bash
cd .claude/skills/boduan && python main.py 2>&1 | tail -20
```
> 拉全A ~5300 只 + 25 日 OHLCV,约 2-5 分钟。预期输出候选数 + `bd_2026-08-07.json`。

- [ ] **Step 2: 读取输出验证字段**

```bash
cat .claude/skills/boduan/data/bd_2026-08-07.json
```
核验:`date=2026-08-07` / `trigger.signal=band_oversold_rebound` / `stocks[]` 字段(code/name/close/drop20/stop_loss/vol_ratio/market_cap)齐全。

- [ ] **Step 3: 决策**

- 有候选 → boduan 可用,阶段 2 完成。向用户展示结果 + 纪律。
- 0 候选 → 正常(08-07 连涨,深度超跌股少),诚实 count=0,不凑数。

- [ ] **Step 4: Commit 输出样本(可选,若想留档)**

```bash
# 仅当想留档时;data/ 通常 gitignore,跳过也可
git add -f .claude/skills/boduan/data/bd_2026-08-07.json
git commit -m "docs(boduan): 08-07 首跑输出样本" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 完成后

回到主对话:报告 boduan 落地结果(候选数/样本/纪律),用 finishing-a-development-branch 决定合并。skill 上线后,用户 `/boduan` 即用。
