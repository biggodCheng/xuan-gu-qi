# eval-stock 个股评估器 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一个独立 skill `.claude/skills/eval-stock/`，输入任意股票（代码/名称），跑 qsht 的 6 个维度（趋势新高/涨停/缩量回踩/市值/Q2展望/赛道），终端打印 markdown 汇总与漏斗达标判定。

**Architecture:** 分层——`fetcher`（数据获取，腾讯日K+市值，含纯解析函数）/ `analyzer`（4 个维度纯函数）/ `bridges`（importlib 加载 q2zhanwang、sidasaidao 复用 Q2 与赛道）/ `reporter`（markdown 格式化）/ `main`（CLI 编排）。第①步采用"近一月新高"放宽规则（仅 eval-stock，qsht-agent 不变）。

**Tech Stack:** Python 3.10+、requests、pytest。无新增依赖。

**Spec:** [docs/superpowers/specs/2026-07-08-eval-stock-design.md](../specs/2026-07-08-eval-stock-design.md)

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `.claude/skills/eval-stock/SKILL.md` | 触发说明 |
| `.claude/skills/eval-stock/main.py` | CLI 入口：解析参数 → evaluate_one() 编排 → 打印 |
| `.claude/skills/eval-stock/screener/__init__.py` | 包标识（空） |
| `.claude/skills/eval-stock/screener/fetcher.py` | 日K + 市值获取 + 代码/板块/阈值纯函数 + 腾讯响应解析纯函数 |
| `.claude/skills/eval-stock/screener/analyzer.py` | check_new_high / check_recent_zt / check_pullback / check_marketcap 纯函数 |
| `.claude/skills/eval-stock/screener/bridges.py` | importlib 临时包加载 q2zhanwang / sidasaidao 核心函数 |
| `.claude/skills/eval-stock/screener/reporter.py` | format_report(stock_result) → markdown 字符串 |
| `.claude/skills/eval-stock/tests/test_analyzer.py` | analyzer 纯函数单测 |
| `.claude/skills/eval-stock/tests/test_fetcher.py` | fetcher 纯函数单测（解析逻辑） |
| `.claude/skills/eval-stock/tests/test_reporter.py` | reporter 格式快照测 |

## 数据结构约定（main 组装，reporter 消费）

```python
stock_result = {
    "code": "000021", "name": "深科技", "industry": "消费电子",
    "last_date": "2026-07-07", "last_close": 54.07, "intraday": False,
    "new_high":  {"pass": bool, "label": str},          # Task 3
    "zt":        {"pass": bool, "label": str, "count": int, "_raw": list},  # Task 4
    "pullback":  {"pass": bool, "label": str},          # Task 5
    "marketcap": {"pass": bool, "label": str, "total": float|None, "circ": float|None},  # Task 6
    "q2":        {"verdict": str, "confidence": str, "netprofit_yoy": float|None,
                  "revenue_yoy": float|None, "summary": str},   # Task 7
    "track":     {"tracks": [str], "main": str, "main_conf": str},  # Task 7
    "error": None,
}
```

> 每个维度统一 `{"pass": bool, "label": str}` 形状，reporter 据此亮灯。`zt._raw` 供 check_pullback 内部用，reporter 不打印。

---

### Task 1: 脚手架 + fetcher 纯函数（代码/板块/阈值 + 响应解析）

**Files:**
- Create: `.claude/skills/eval-stock/screener/__init__.py`
- Create: `.claude/skills/eval-stock/screener/fetcher.py`
- Create: `.claude/skills/eval-stock/tests/__init__.py`
- Create: `.claude/skills/eval-stock/tests/test_fetcher.py`

- [ ] **Step 1: 建空 `__init__.py`**

`.claude/skills/eval-stock/screener/__init__.py` 与 `.claude/skills/eval-stock/tests/__init__.py` 内容均为空文件。

- [ ] **Step 2: 写 fetcher 纯函数的失败测试**

`.claude/skills/eval-stock/tests/test_fetcher.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.fetcher import (
    tencent_symbol, get_board, zt_threshold,
    _parse_tencent_kline, _parse_qt,
)


def test_tencent_symbol():
    assert tencent_symbol("600206") == "sh600206"
    assert tencent_symbol("000021") == "sz000021"
    assert tencent_symbol("920019") == "bj920019"


def test_get_board():
    assert get_board("600206") == "main"
    assert get_board("000021") == "main"
    assert get_board("300001") == "kc_cy"
    assert get_board("688001") == "kc_cy"
    assert get_board("830001") == "bj"


def test_zt_threshold():
    assert zt_threshold("000021") == 9.5
    assert zt_threshold("300001") == 19.5
    assert zt_threshold("830001") == 29.5


def test_parse_tencent_kline_ok():
    # 腾讯返回 data.<symbol>.qfqday = [[date,open,close,high,low,vol], ...]
    payload = {"code": 0, "data": {"sz000021": {"qfqday": [
        ["2026-07-01", "10.0", "10.5", "10.6", "9.9", "1000"],
        ["2026-07-02", "10.5", "11.0", "11.1", "10.4", "1200"],
    ]}}}
    rows = _parse_tencent_kline(payload, "sz000021")
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-07-01"
    assert rows[0]["close"] == 10.5
    assert rows[0]["volume"] == 1000.0


def test_parse_tencent_kline_fallback_day():
    # qfqday 缺失时回退 day 字段
    payload = {"code": 0, "data": {"sz000021": {"day": [
        ["2026-07-01", "10.0", "10.5", "10.6", "9.9", "1000"],
    ]}}}
    rows = _parse_tencent_kline(payload, "sz000021")
    assert len(rows) == 1 and rows[0]["close"] == 10.5


def test_parse_tencent_kline_bad_code():
    assert _parse_tencent_kline({"code": 1, "data": {}}, "sz000021") == []


def test_parse_qt_ok():
    # 腾讯 qt 文本：v_sz000021="名称~~...~总市值~~流通市值~..."
    # 构造 parts[44]=800.5(总市值) parts[45]=790.0(流通)
    parts = [""] * 50
    parts[44] = "800.5"
    parts[45] = "790.0"
    raw = f'v_sz000021="{"~".join(parts)}";'
    total, circ = _parse_qt(raw)
    assert total == 800.5 and circ == 790.0


def test_parse_qt_bad():
    assert _parse_qt("garbage") == (None, None)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest .claude/skills/eval-stock/tests/test_fetcher.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'screener.fetcher'`）

- [ ] **Step 4: 写 fetcher.py 纯函数实现**

`.claude/skills/eval-stock/screener/fetcher.py`:
```python
# -*- coding: utf-8 -*-
"""数据获取层 — 腾讯前复权日K + 腾讯qt市值。
IO 函数（fetch_kline/fetch_marketcap）调网络后委托给纯解析函数。
"""
import os
from datetime import datetime, timedelta

import requests

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
_session = requests.Session()
_session.trust_env = False


# ---- 代码/板块/阈值（纯函数）----

def tencent_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def get_board(code: str) -> str:
    """main / kc_cy(科创创业) / bj。"""
    if code.startswith(("68", "30")):
        return "kc_cy"
    if code.startswith(("8", "4", "9")):
        return "bj"
    return "main"


def zt_threshold(code: str) -> float:
    return {"main": 9.5, "kc_cy": 19.5, "bj": 29.5}[get_board(code)]


# ---- 响应解析（纯函数）----

def _parse_tencent_kline(payload: dict, symbol: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("code") != 0:
        return []
    sd = payload.get("data", {}).get(symbol, {})
    rows = sd.get("qfqday", []) or sd.get("day", [])
    out = []
    for x in rows:
        try:
            out.append({"date": x[0], "open": float(x[1]), "close": float(x[2]),
                        "high": float(x[3]), "low": float(x[4]), "volume": float(x[5])})
        except (ValueError, IndexError, TypeError):
            continue
    return out


def _parse_qt(raw: str) -> tuple:
    try:
        line = raw.strip().split(";")[0].strip()
        parts = line.split('="', 1)[1].rstrip('";').split("~")
        total = float(parts[44]) if len(parts) > 44 else None
        circ = float(parts[45]) if len(parts) > 45 else None
        return total, circ
    except Exception:
        return None, None


# ---- IO（网络 + 解析）----

def fetch_kline(code: str, days: int = 130) -> list[dict]:
    sym = tencent_symbol(code)
    start = (datetime.now() - timedelta(days=days * 2 + 90)).strftime("%Y-%m-%d")
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    try:
        r = _session.get(url, params={"param": f"{sym},day,{start},,{days + 10},qfq"}, timeout=15)
        return _parse_tencent_kline(r.json(), sym)
    except Exception:
        return []


def fetch_marketcap(code: str) -> tuple:
    sym = tencent_symbol(code)
    try:
        r = _session.get(f"https://qt.gtimg.cn/q={sym}", timeout=15)
        return _parse_qt(r.text)
    except Exception:
        return None, None
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest .claude/skills/eval-stock/tests/test_fetcher.py -v`
Expected: 8 passed

- [ ] **Step 6: 提交**

```bash
git add .claude/skills/eval-stock/screener/__init__.py .claude/skills/eval-stock/screener/fetcher.py .claude/skills/eval-stock/tests/__init__.py .claude/skills/eval-stock/tests/test_fetcher.py
git commit -m "feat(eval-stock): 脚手架 + fetcher 纯函数(代码/板块/阈值/腾讯响应解析)"
```

---

### Task 2: analyzer — 趋势新高（近一月新高规则）

**Files:**
- Create: `.claude/skills/eval-stock/screener/analyzer.py`
- Create: `.claude/skills/eval-stock/tests/test_analyzer.py`

- [ ] **Step 1: 写失败测试**

`.claude/skills/eval-stock/tests/test_analyzer.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.analyzer import check_new_high


def _kline(closes):
    """按收盘价列表构造 K 线，日期用占位。"""
    return [{"date": f"2026-01-{i+1:02d}", "close": c, "volume": 100.0} for i, c in enumerate(closes)]


def test_new_high_today():
    # 前100日最高10，今日11 → 今日新高
    closes = [8.0] * 99 + [10.0] + [11.0]
    r = check_new_high(_kline(closes))
    assert r["pass"] is True
    assert "今日新高" in r["label"]


def test_new_high_within_recent_20():
    # 今天没新高（今日10 < 前高11），但3天前创过新高(11>=此前最高10)
    # 构造：前97日 ≤10，第98日(=今天前3天)收11创新高，之后回落，今日10
    closes = [9.0] * 97 + [11.0, 10.5, 10.2, 10.0]
    r = check_new_high(_kline(closes))
    assert r["pass"] is True
    assert "近" in r["label"] and "日前" in r["label"]


def test_new_high_fail():
    # 近20日均未创新高：前100日最高12（远在20日外），近20日最高10
    closes = [12.0] + [8.0] * 99 + [10.0] * 20
    r = check_new_high(_kline(closes))
    assert r["pass"] is False
    assert "距高点" in r["label"]


def test_new_high_insufficient_data():
    r = check_new_high(_kline([10.0] * 50))
    assert r["pass"] is False
    assert "数据不足" in r["label"]
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest .claude/skills/eval-stock/tests/test_analyzer.py::test_new_high_today -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 写 analyzer.check_new_high**

`.claude/skills/eval-stock/screener/analyzer.py`:
```python
# -*- coding: utf-8 -*-
"""分析层 — 趋势新高/涨停/缩量回踩/市值门槛 纯函数。"""

RECENT_HIGH_DAYS = 20   # 近一月窗口（交易日）
LOOKBACK = 100          # 新高回看交易日
RECENT_ZT_DAYS = 15
SHRINK_RATIO = 0.8
MIN_PULLBACK_DAYS = 2
MKTCAP_THRESHOLD = 200  # 亿元


def check_new_high(kline: list[dict],
                   recent_days: int = RECENT_HIGH_DAYS,
                   lookback: int = LOOKBACK) -> dict:
    """近 recent_days 内任一天创该日前 lookback 日新高 → 通过。

    优先标"今日新高"，否则标"近N日前 创新高"，否则标"距高点 -X%"。
    """
    if len(kline) < lookback + 1:
        return {"pass": False, "label": "数据不足", "detail": f"K线仅 {len(kline)} 根"}

    today_close = kline[-1]["close"]
    # 今日是否新高（与前 lookback 根比）
    if today_close >= max(d["close"] for d in kline[-(lookback + 1):-1]):
        return {"pass": True, "label": "今日新高",
                "detail": f"今日 {today_close:.2f} 创 {lookback} 日新高"}

    # 近 recent_days 内是否曾新高（从最近往远找，取最近一次）
    for i in range(len(kline) - 1, len(kline) - recent_days - 1, -1):
        if i < lookback:
            break
        before = kline[i - lookback:i]
        if kline[i]["close"] >= max(d["close"] for d in before):
            days_ago = len(kline) - 1 - i
            return {"pass": True,
                    "label": f"近 {days_ago} 日前 {kline[i]['date']} 创 {lookback} 日新高",
                    "detail": f"当日 {kline[i]['close']:.2f}"}

    high_recent = max(d["close"] for d in kline[-lookback:])
    pct = (today_close / high_recent - 1) * 100 if high_recent else 0
    return {"pass": False, "label": f"距高点 {pct:.1f}%",
            "detail": f"近 {recent_days} 日均未创新高"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest .claude/skills/eval-stock/tests/test_analyzer.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/eval-stock/screener/analyzer.py .claude/skills/eval-stock/tests/test_analyzer.py
git commit -m "feat(eval-stock): 趋势新高判定(近一月新高放宽规则)"
```

---

### Task 3: analyzer — 近期涨停

**Files:**
- Modify: `.claude/skills/eval-stock/screener/analyzer.py`（追加函数）
- Modify: `.claude/skills/eval-stock/tests/test_analyzer.py`（追加测试）

- [ ] **Step 1: 追加失败测试**

在 `test_analyzer.py` 末尾追加：
```python
from screener.analyzer import check_recent_zt


def test_recent_zt_hit():
    # 最近15日内有一天涨幅 10%（>= 9.5%）
    closes = [10.0] * 20 + [11.0] + [10.5] * 5  # 第21日 +10%
    k = [{"date": f"d{i}", "close": c, "volume": 100.0} for i, c in enumerate(closes)]
    r = check_recent_zt(k, threshold=9.5)
    assert r["pass"] is True
    assert r["count"] == 1
    assert r["dates"][0]["chg"] == 10.0


def test_recent_zt_outside_window():
    # 涨停在20天前（窗口外）
    closes = [10.0] * 5 + [11.0] + [10.0] * 20
    k = [{"date": f"d{i}", "close": c, "volume": 100.0} for i, c in enumerate(closes)]
    r = check_recent_zt(k, threshold=9.5)
    assert r["pass"] is False
    assert r["count"] == 0


def test_recent_zt_raw_keeps_close_volume():
    closes = [10.0] * 10 + [11.0]
    k = [{"date": f"d{i}", "close": c, "volume": float(i) * 100} for i, c in enumerate(closes)]
    r = check_recent_zt(k, threshold=9.5)
    assert r["_raw"][0]["close"] == 11.0
    assert r["_raw"][0]["volume"] == 1000.0
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest .claude/skills/eval-stock/tests/test_analyzer.py::test_recent_zt_hit -v`
Expected: FAIL（`ImportError: cannot import name 'check_recent_zt'`）

- [ ] **Step 3: 追加 check_recent_zt 实现**

在 `analyzer.py` 末尾追加：
```python
def check_recent_zt(kline: list[dict], threshold: float,
                    recent_days: int = RECENT_ZT_DAYS) -> dict:
    """近 recent_days 天内单日涨幅(close vs prev_close) >= threshold。"""
    if len(kline) < 2:
        return {"pass": False, "count": 0, "dates": [], "_raw": []}
    window = kline[-(recent_days + 1):]
    raw = []
    for i in range(1, len(window)):
        prev = window[i - 1]["close"]
        if prev <= 0:
            continue
        chg = (window[i]["close"] - prev) / prev * 100
        if chg >= threshold:
            raw.append({"date": window[i]["date"], "chg": round(chg, 2),
                        "close": window[i]["close"], "volume": window[i]["volume"]})
    return {
        "pass": len(raw) > 0,
        "count": len(raw),
        "dates": [{"date": z["date"], "chg": z["chg"]} for z in raw],
        "_raw": raw,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest .claude/skills/eval-stock/tests/test_analyzer.py -v`
Expected: 7 passed（原 4 + 新 3）

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/eval-stock/screener/analyzer.py .claude/skills/eval-stock/tests/test_analyzer.py
git commit -m "feat(eval-stock): 近期涨停判定(按板块阈值)"
```

---

### Task 4: analyzer — 缩量回踩（策略1）

**Files:**
- Modify: `.claude/skills/eval-stock/screener/analyzer.py`
- Modify: `.claude/skills/eval-stock/tests/test_analyzer.py`

- [ ] **Step 1: 追加失败测试**

在 `test_analyzer.py` 末尾追加：
```python
from screener.analyzer import check_pullback


def _kline_cv(series):
    """series: [(close, volume), ...] → kline。"""
    return [{"date": f"d{i}", "close": c, "volume": v} for i, (c, v) in enumerate(series)]


def test_pullback_hit():
    # 涨停日 d5: close=11 vol=1000；之后连续2天 close<11 且量递减(<prev*0.8)
    zt = [{"date": "d5", "chg": 10.0, "close": 11.0, "volume": 1000.0}]
    k = _kline_cv([(10, 100)] * 5 + [(11, 1000), (10.5, 700), (10.2, 500), (10.0, 800)])
    r = check_pullback(k, zt)
    assert r["pass"] is True
    assert "d6" in r["label"]


def test_pullback_no_zt():
    assert check_pullback(_kline_cv([(10, 100), (11, 200)]), []).get("pass") is False


def test_pullback_volume_not_shrink():
    # 涨停后价格回落但量不缩 → 不命中
    zt = [{"date": "d1", "chg": 10.0, "close": 11.0, "volume": 1000.0}]
    k = _kline_cv([(10, 100), (11, 1000), (10.5, 950), (10.2, 920)])  # 量仅微降
    r = check_pullback(k, zt)
    assert r["pass"] is False


def test_pullback_price_recovers_resets():
    # 中途价格回到>=涨停收盘，则中断
    zt = [{"date": "d1", "chg": 10.0, "close": 11.0, "volume": 1000.0}]
    k = _kline_cv([(10, 100), (11, 1000), (10.5, 700), (11.5, 600), (10.8, 400), (10.6, 300)])
    r = check_pullback(k, zt)
    # d4/d5/d6 连续缩量2天 → 命中
    assert r["pass"] is True
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest .claude/skills/eval-stock/tests/test_analyzer.py::test_pullback_hit -v`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 追加 check_pullback 实现**

在 `analyzer.py` 末尾追加（复刻 suolianghuicai 策略1 逻辑）：
```python
def check_pullback(kline: list[dict], zt_raw: list[dict],
                   shrink_ratio: float = SHRINK_RATIO,
                   min_days: int = MIN_PULLBACK_DAYS) -> dict:
    """策略1：最后一次涨停后连续 close<zt_close 且 volume<prev*shrink_ratio。"""
    if not zt_raw:
        return {"pass": False, "label": "无近期涨停"}
    lz = zt_raw[-1]
    zt_date, zt_close = lz["date"], lz["close"]
    idx = next((i for i, d in enumerate(kline) if d["date"] == zt_date), None)
    if idx is None:
        return {"pass": False, "label": "涨停日不在K线"}
    after = kline[idx + 1:]
    if len(after) < min_days:
        return {"pass": False, "label": "涨停后交易日不足"}

    best_len = cur_len = 0
    best_start = cur_start = -1
    for i in range(len(after)):
        if after[i]["close"] >= zt_close:
            cur_start, cur_len = -1, 0
            continue
        if cur_start == -1:
            cur_start, cur_len = i, 1
        elif after[i]["volume"] < after[i - 1]["volume"] * shrink_ratio:
            cur_len += 1
        else:
            if cur_len > best_len:
                best_len, best_start = cur_len, cur_start
            cur_start, cur_len = i, 1
    if cur_len > best_len:
        best_len, best_start = cur_len, cur_start

    if best_len >= min_days and best_start >= 0:
        seg = after[best_start:best_start + best_len]
        fv = seg[0]["volume"] or 1
        ratio = seg[-1]["volume"] / fv
        return {"pass": True,
                "label": f"{seg[0]['date']} 起 {best_len} 天，量比 {ratio:.2f}"}
    return {"pass": False, "label": "未形成缩量回踩"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest .claude/skills/eval-stock/tests/test_analyzer.py -v`
Expected: 11 passed（原 7 + 新 4）

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/eval-stock/screener/analyzer.py .claude/skills/eval-stock/tests/test_analyzer.py
git commit -m "feat(eval-stock): 缩量回踩判定(策略1, 复刻 suolianghuicai)"
```

---

### Task 5: analyzer — 市值门槛

**Files:**
- Modify: `.claude/skills/eval-stock/screener/analyzer.py`
- Modify: `.claude/skills/eval-stock/tests/test_analyzer.py`

- [ ] **Step 1: 追加失败测试**

```python
from screener.analyzer import check_marketcap


def test_marketcap_pass():
    r = check_marketcap(150.0)
    assert r["pass"] is True and r["total"] == 150.0


def test_marketcap_fail():
    r = check_marketcap(851.15)
    assert r["pass"] is False


def test_marketcap_none():
    r = check_marketcap(None)
    assert r["pass"] is False and "不可用" in r["label"]
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest .claude/skills/eval-stock/tests/test_analyzer.py::test_marketcap_pass -v`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 追加 check_marketcap 实现**

在 `analyzer.py` 末尾追加：
```python
def check_marketcap(total: float | None, circ: float | None = None,
                    threshold: float = MKTCAP_THRESHOLD) -> dict:
    if total is None:
        return {"pass": False, "label": "市值数据不可用", "total": None, "circ": circ}
    return {"pass": total < threshold,
            "label": f"{total:.0f} 亿" + (f" / 流通 {circ:.0f} 亿" if circ else ""),
            "total": total, "circ": circ}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest .claude/skills/eval-stock/tests/test_analyzer.py -v`
Expected: 14 passed（原 11 + 新 3）

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/eval-stock/screener/analyzer.py .claude/skills/eval-stock/tests/test_analyzer.py
git commit -m "feat(eval-stock): 市值门槛判定(<200亿)"
```

---

### Task 6: bridges — importlib 加载 q2zhanwang / sidasaidao

**Files:**
- Create: `.claude/skills/eval-stock/screener/bridges.py`

> 说明：q2zhanwang 模块为绝对 import；sidasaidao/analyzer.py 有相对 import（`from .tracks import`），故用"临时包"加载法——在 sys.modules 注册一个命名空间包并设 `__path__` 指向 skill 的 screener 目录，使相对 import 解析为 `<pkg>.tracks`。

- [ ] **Step 1: 写 bridges.py**

`.claude/skills/eval-stock/screener/bridges.py`:
```python
# -*- coding: utf-8 -*-
"""用 importlib 复用 q2zhanwang / sidasaidao 的核心函数，绕开多个 screener 包名冲突。
不写文件、无副作用。sidasaidao/analyzer 有相对 import，用临时包加载法。
"""
import importlib.util
import sys
import types
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]   # .../xuan-gu-qi
_SKILLS_DIR = _PROJECT_ROOT / ".claude" / "skills"


def _ensure_pkg(pkg_name: str, screener_dir: Path) -> str:
    """注册临时命名空间包 pkg_name，__path__ 指向 screener_dir。返回包名。"""
    if pkg_name not in sys.modules:
        m = types.ModuleType(pkg_name)
        m.__path__ = [str(screener_dir)]
        sys.modules[pkg_name] = m
    return pkg_name


def _load_sub(pkg_name: str, sub: str, path: Path):
    full = f"{pkg_name}.{sub}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_skill(skill: str):
    screener_dir = _SKILLS_DIR / skill / "screener"
    pkg = _ensure_pkg(f"eval_{skill}", screener_dir)
    fetcher = _load_sub(pkg, "fetcher", screener_dir / "fetcher.py")
    analyzer = _load_sub(pkg, "analyzer", screener_dir / "analyzer.py")
    return fetcher, analyzer


# ---- Q2 ----

def get_q2_funcs():
    """返回 (get_financial, analyze)。失败抛异常，由调用方兜底。"""
    f, a = _load_skill("q2zhanwang")
    return f.get_financial, a.analyze


# ---- 赛道 ----

def get_sid_funcs():
    """返回 (resolve_stock_code, get_stock_detail, match_tracks)。"""
    f, a = _load_skill("sidasaidao")
    return f.resolve_stock_code, f.get_stock_detail, a.match_tracks
```

- [ ] **Step 2: 写集成测试（真实加载，不走网络）**

`.claude/skills/eval-stock/tests/test_bridges.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.bridges import get_q2_funcs, get_sid_funcs


def test_load_q2_funcs_callable():
    get_financial, analyze = get_q2_funcs()
    assert callable(get_financial) and callable(analyze)
    # analyze 是纯函数，喂空 reports 应回数据不足
    r = analyze({"code": "000000", "name": "", "industry": "", "reports": []})
    assert r["q2_outlook"]["verdict"] == "数据不足"


def test_load_sid_funcs_callable():
    resolve, get_detail, match = get_sid_funcs()
    assert callable(resolve) and callable(get_detail) and callable(match)
    # match_tracks 纯函数：空输入返回空列表
    assert match("", []) == []
```

- [ ] **Step 3: 运行测试确认通过**

Run: `pytest .claude/skills/eval-stock/tests/test_bridges.py -v`
Expected: 2 passed

> 若失败为相对 import 相关，确认 `_ensure_pkg` 已把 `__path__` 设到 `sidasaidao/screener`，且 `_load_sub` 先加载 analyzer 时它请求的 `eval_sidasaidao.tracks` 能经包 `__path__` 找到 tracks.py。

- [ ] **Step 4: 提交**

```bash
git add .claude/skills/eval-stock/screener/bridges.py .claude/skills/eval-stock/tests/test_bridges.py
git commit -m "feat(eval-stock): bridges 用 importlib 复用 q2zhanwang/sidasaidao"
```

---

### Task 7: reporter — markdown 格式化

**Files:**
- Create: `.claude/skills/eval-stock/screener/reporter.py`
- Create: `.claude/skills/eval-stock/tests/test_reporter.py`

- [ ] **Step 1: 写失败测试**

`.claude/skills/eval-stock/tests/test_reporter.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.reporter import format_report, _lamp, _funnel_verdict


def test_lamp():
    assert _lamp({"pass": True}) == "✅"
    assert _lamp({"pass": False}) == "❌"
    assert _lamp({"verdict": "中性"}) == "➖"
    assert _lamp({}) == "➖"


def test_funnel_pass_all():
    r = {"new_high": {"pass": True}, "zt": {"pass": True},
         "pullback": {"pass": True}, "marketcap": {"pass": True}}
    verdict, where = _funnel_verdict(r)
    assert verdict == "达标" and where == ""


def test_funnel_fail_at_marketcap():
    r = {"new_high": {"pass": True}, "zt": {"pass": True},
         "pullback": {"pass": True}, "marketcap": {"pass": False}}
    verdict, where = _funnel_verdict(r)
    assert verdict == "不达标" and "市值" in where


def test_funnel_fail_at_new_high():
    r = {"new_high": {"pass": False}, "zt": {"pass": True},
         "pullback": {"pass": False}, "marketcap": {"pass": True}}
    verdict, where = _funnel_verdict(r)
    assert verdict == "不达标" and "趋势新高" in where


def test_format_report_contains_core_lines():
    stock = {
        "code": "000021", "name": "深科技", "industry": "消费电子",
        "last_date": "2026-07-07", "last_close": 54.07, "intraday": False,
        "new_high": {"pass": True, "label": "今日新高"},
        "zt": {"pass": True, "label": "2 次"},
        "pullback": {"pass": True, "label": "d6 起 2 天"},
        "marketcap": {"pass": False, "label": "851 亿"},
        "q2": {"verdict": "中性", "confidence": "中", "netprofit_yoy": 35.35,
               "revenue_yoy": 10.67, "summary": "..."},
        "track": {"tracks": ["AI硬件和基础设施", "大工业"], "main": "AI硬件和基础设施",
                  "main_conf": "中"},
        "error": None,
    }
    out = format_report(stock)
    assert "深科技(000021)" in out
    assert "851 亿" in out
    assert "不达标" in out
    assert "市值" in out  # 漏斗在市值淘汰
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest .claude/skills/eval-stock/tests/test_reporter.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 写 reporter.py**

`.claude/skills/eval-stock/screener/reporter.py`:
```python
# -*- coding: utf-8 -*-
"""终端 markdown 格式化。"""

_FUNNEL_STEPS = [
    ("① 趋势新高", "new_high", "趋势新高"),
    ("② 近15天涨停", "zt", "涨停"),
    ("③ 缩量回踩", "pullback", "缩量回踩"),
    ("④ 市值<200亿", "marketcap", "市值"),
]


def _lamp(dim) -> str:
    if "pass" in dim:
        return "✅" if dim["pass"] else "❌"
    if dim.get("verdict") == "偏正":
        return "✅"
    if dim.get("verdict") == "偏负":
        return "❌"
    return "➖"   # 中性 / 数据不足


def _funnel_verdict(stock: dict) -> tuple:
    """按 ①→②→③→④ 串联，任一不过即淘汰。返回 (达标/不达标, 淘汰步说明)。"""
    for label, key, name in _FUNNEL_STEPS:
        dim = stock.get(key, {})
        if not dim.get("pass", False):
            return "不达标", f"{label} 淘汰（{name}未过）"
    return "达标", ""


def _oneliner(stock: dict) -> str:
    verdict, where = _funnel_verdict(stock)
    parts = []
    if verdict == "不达标":
        parts.append(where)
    if not stock.get("new_high", {}).get("pass", False):
        parts.append("非新高/趋势走弱")
    if stock.get("marketcap", {}).get("total") and stock["marketcap"]["total"] >= 200:
        parts.append("大票")
    q2v = stock.get("q2", {}).get("verdict")
    if q2v == "偏负":
        parts.append("Q2偏负")
    tail = "；".join(parts) if parts else "各维度通过"
    prefix = "非体系标的，不建议追" if verdict == "不达标" else "符合体系，可重点跟踪"
    return f"{prefix}（{tail}）"


def format_report(stock: dict) -> str:
    if stock.get("error"):
        return f"{stock.get('name', stock.get('code', '?'))}: 取数失败 — {stock['error']}"

    lines = []
    header = (f"{stock['name']}({stock['code']}) · {stock.get('industry') or '—'}"
              f" · 数据截至 {stock.get('last_date', '?')}"
              f" · 最新 {stock.get('last_close', '?')}")
    if stock.get("intraday"):
        header += "（盘中未收盘）"
    lines.append(header)
    lines.append("─" * 45)

    for label, key, _ in _FUNNEL_STEPS:
        dim = stock.get(key, {})
        lines.append(f"{label}   {_lamp(dim)}  {dim.get('label', '')}")

    # Q2
    q2 = stock.get("q2", {})
    np = q2.get("netprofit_yoy")
    rev = q2.get("revenue_yoy")
    np_s = f"{np:+.0f}%" if np is not None else "N/A"
    rev_s = f"{rev:+.0f}%" if rev is not None else "N/A"
    lines.append(f"⑤ Q2展望      {_lamp(q2)}  {q2.get('verdict', '?')}"
                 f"（净利 {np_s} / 营收 {rev_s}）")

    # 赛道
    tr = stock.get("track", {})
    if tr.get("tracks"):
        main = f"主 {tr['main']}({tr.get('main_conf', '')})" if tr.get("main") else ""
        lines.append(f"⑥ 赛道        ✅  {'、'.join(tr['tracks'])} {main}")
    else:
        lines.append("⑥ 赛道        ❌  不属于四大赛道")

    lines.append("─" * 45)
    verdict, where = _funnel_verdict(stock)
    lines.append(f"qsht 漏斗判定：{where or '①②③④ 全通过 → 达标'}")
    lines.append(f"一句话：{_oneliner(stock)}")
    return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest .claude/skills/eval-stock/tests/test_reporter.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/eval-stock/screener/reporter.py .claude/skills/eval-stock/tests/test_reporter.py
git commit -m "feat(eval-stock): reporter markdown 格式化 + 漏斗达标判定"
```

---

### Task 8: main.py — CLI 编排

**Files:**
- Create: `.claude/skills/eval-stock/main.py`

- [ ] **Step 1: 写 main.py**

`.claude/skills/eval-stock/main.py`:
```python
# -*- coding: utf-8 -*-
"""eval-stock CLI：python main.py <代码或名称>[,...]
对每只股票跑 qsht 6 维度，终端打印 markdown 汇总。
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import fetch_kline, fetch_marketcap, zt_threshold
from screener.analyzer import (
    check_new_high, check_recent_zt, check_pullback, check_marketcap,
)
from screener.bridges import get_q2_funcs, get_sid_funcs
from screener.reporter import format_report

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KLINE_DAYS = 130
_Q2 = None   # lazy
_SID = None


def _lazy_load():
    global _Q2, _SID
    if _Q2 is None:
        _Q2 = get_q2_funcs()       # (get_financial, analyze)
        _SID = get_sid_funcs()     # (resolve, get_detail, match_tracks)


def _is_intraday(last_date: str) -> bool:
    if not last_date:
        return False
    now = datetime.now()
    if last_date != now.strftime("%Y-%m-%d"):
        return False
    # 交易时段粗判
    return 9 <= now.hour < 15


def _eval_q2(code: str) -> dict:
    try:
        get_financial, analyze = _Q2
        fin = get_financial(code)
        if not fin.get("reports"):
            return {"verdict": "数据不足", "confidence": "低",
                    "netprofit_yoy": None, "revenue_yoy": None, "summary": "无财报"}
        r = analyze(fin)
        q1 = r.get("q1", {})
        out = r.get("q2_outlook", {})
        return {
            "verdict": out.get("verdict", "数据不足"),
            "confidence": out.get("confidence", "低"),
            "netprofit_yoy": q1.get("netprofit_yoy"),
            "revenue_yoy": q1.get("revenue_yoy"),
            "summary": out.get("summary", ""),
        }
    except Exception as e:
        return {"verdict": "数据不可用", "confidence": "低",
                "netprofit_yoy": None, "revenue_yoy": None, "summary": f"加载失败: {e}"}


def _eval_track(code: str) -> tuple:
    """返回 (track_dict, industry)。"""
    try:
        _, get_detail, match = _SID
        detail = get_detail(code)
        industry = detail.get("industry", "")
        matched = match(industry, detail.get("concepts", []))
        tracks = [m["track"] for m in matched]
        main = matched[0]["track"] if matched else ""
        main_conf = matched[0]["confidence"] if matched else ""
        return {"tracks": tracks, "main": main, "main_conf": main_conf}, industry
    except Exception:
        return {"tracks": [], "main": "", "main_conf": ""}, ""


def evaluate_one(query: str) -> dict:
    _lazy_load()
    resolve, _, _ = _SID
    try:
        code, name = resolve(query)
    except Exception:
        code, name = None, None
    if not code:
        return {"code": "", "name": query, "error": f"未找到股票: {query}"}

    kline = fetch_kline(code, KLINE_DAYS)
    total, circ = fetch_marketcap(code)

    threshold = zt_threshold(code)
    nh = check_new_high(kline)
    zt = check_recent_zt(kline, threshold)
    pb = check_pullback(kline, zt.get("_raw", []))
    mc = check_marketcap(total, circ)
    q2 = _eval_q2(code)
    track, industry = _eval_track(code)
    if not industry:
        industry = q2.get("summary", "") and ""  # 兜底留空

    last_date = kline[-1]["date"] if kline else ""
    last_close = kline[-1]["close"] if kline else None

    return {
        "code": code, "name": name, "industry": industry,
        "last_date": last_date, "last_close": last_close,
        "intraday": _is_intraday(last_date),
        "new_high": nh, "zt": zt, "pullback": pb, "marketcap": mc,
        "q2": q2, "track": track, "error": None,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python main.py <代码或名称>[,...]")
        print("示例: python main.py 深科技,有研新材")
        sys.exit(1)
    queries = [q.strip() for q in sys.argv[1].split(",") if q.strip()]
    for i, q in enumerate(queries):
        stock = evaluate_one(q)
        if i:
            print("\n")
        print(format_report(stock))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 端到端集成测试（真实拉数，需网络）**

Run: `python .claude/skills/eval-stock/main.py 000021`
Expected: 打印深科技 6 维度报告，①趋势新高应显示近一月新高或距高点，④市值应 ❌（约 850 亿），漏斗判定为"不达标"。

Run: `python .claude/skills/eval-stock/main.py 深科技,有研新材`
Expected: 打印两只股票报告。

- [ ] **Step 3: 若名称解析/Q2/赛道失败，检查 bridges 加载**

常见问题：`resolve_stock_code` 依赖东方财富 searchapi + 新浪行情，网络不通时返回 (None, None)。此时报告显示"未找到股票"。确认网络对 `searchapi.eastmoney.com`、`hq.sinajs.cn` 可达。

- [ ] **Step 4: 提交**

```bash
git add .claude/skills/eval-stock/main.py
git commit -m "feat(eval-stock): main.py CLI 编排 6 维度评估"
```

---

### Task 9: SKILL.md

**Files:**
- Create: `.claude/skills/eval-stock/SKILL.md`

- [ ] **Step 1: 写 SKILL.md**

`.claude/skills/eval-stock/SKILL.md`:
```markdown
---
name: eval-stock
description: 个股定点体检器 — 给定任意一只 A 股（代码或名称），跑 qsht 选股体系的 6 个维度（趋势新高 / 近期涨停 / 缩量回踩 / 市值 / Q2 业绩展望 / 四大赛道），终端打印 markdown 汇总与 qsht 漏斗达标判定。与 qsht-agent（全市场筛选）互补：广撒网 vs 定点体检。当用户说"评估/体检/看成色/过一遍流水线/能不能买/帮我分析一下"某只股票时触发。
---

# eval-stock — 个股定点体检器

## 用途
对**指定的一两只股票**快速评估其在 qsht 选股体系各维度的成色。区别于 qsht-agent（全市场扫描、10-25 分钟、落盘大报告），本工具是秒级定点体检、终端直接输出。

## 运行
\`\`\`bash
python .claude/skills/eval-stock/main.py <代码或名称>[,...]
\`\`\`
示例：`python main.py 深科技,有研新材`、`python main.py 000021`

## 6 维度（阈值与 qsht 各子 skill 默认一致）
1. **趋势新高**（eval-stock 放宽）：近 20 交易日内任一天创该日前 100 日新高 → 通过。标注"今日新高 / 近N日前创新高 / 距高点-X%"。
2. **近 15 天涨停**：按板块阈值（主板 9.5% / 科创创业 19.5% / 北交所 29.5%）。
3. **缩量回踩（策略1）**：涨停后连续 close<zt_close 且 volume<prev×0.8，≥2 天。
4. **市值**：总市值 < 200 亿。
5. **Q2 业绩展望**：复用 q2zhanwang（一季报同比势头 + 营收-净利背离推断）。
6. **赛道**：复用 sidasaidao（四大赛道）。

## 与 qsht-agent 的差异
- 第①步：eval-stock 用"近一月新高"（体检语义，趋势是否还在）；**qsht-agent 用"今日新高"**（选股语义）。同一只票可能这里①通过而 qsht 当日筛不中——这是设计意图。
- 其余维度阈值完全一致。

## 输出示例
\`\`\`
深科技(000021) · 消费电子 · 数据截至 2026-07-07 · 最新 54.07
─────────────────────────────────────────
① 趋势新高    ✅  近 7 日前 6/30 创 100 日新高
② 近15天涨停   ✅  2 次（6/24, 6/29）
③ 缩量回踩    ✅  7/3 起 2 天，量比 0.70
④ 市值<200亿   ❌  851 亿
⑤ Q2展望     ➖  中性（净利 +35% / 营收 +11%）
⑥ 赛道       ✅  四大赛道全覆盖，主 AI硬件(中)
─────────────────────────────────────────
qsht 漏斗判定：④ 市值<200亿 淘汰 → 不达标
一句话：非体系标的，不建议追（④市值淘汰；大票）
\`\`\`

## 注意
- 数据截至最新交易日收盘；盘中运行会标注"盘中未收盘"。
- 单只取数失败不阻断其他股票。
- 纯终端输出，不落盘、不写其他 skill 的 data 目录。
- ⑤⑥ 为参考维度，不参与漏斗淘汰（漏斗仅 ①→②→③→④）。
```

- [ ] **Step 2: 提交**

```bash
git add .claude/skills/eval-stock/SKILL.md
git commit -m "docs(eval-stock): SKILL.md 触发说明与用法"
```

---

## Self-Review（计划自检）

**1. Spec 覆盖：**
- 6 维度 → Task 2-6（新高/涨停/回踩/市值）+ Task 6（Q2/赛道经 bridges）。✓
- 近一月新高规则 → Task 2（RECENT_HIGH_DAYS=20，从近往远找）。✓
- importlib 复用、不写文件 → Task 6 bridges（含相对 import 的临时包加载法）。✓
- 终端打印、漏斗判定、一句话 → Task 7 reporter。✓
- 输入代码/名称多只 → Task 8 main。✓
- 错误处理（单股失败不阻断、数据不足、盘中提示）→ Task 8（evaluate_one 兜底 + _is_intraday）。✓
- 测试 → Task 1-7 各有单测，Task 8 端到端集成。✓
- 验收标准 1-6 → 由各 Task 覆盖（<30s 由网络决定；近一月新高 Task2；达标判定 Task7；单股失败 Task8；不写文件 Task6 设计保证；阈值一致 各 Task 与 qsht 默认对齐）。✓

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码或确切命令。✓

**3. 类型/命名一致性：**
- `check_new_high/check_recent_zt/check_pullback/check_marketcap` 在 analyzer 定义、main 调用、命名一致。✓
- `stock_result` 各键（new_high/zt/pullback/marketcap/q2/track）在 Task 2-8 一致；`zt._raw` 在 Task 3 产出、Task 4 消费、Task 8 传递。✓
- bridges `get_q2_funcs/get_sid_funcs` 在 Task 6 定义、Task 8 调用一致。✓
- reporter `_lamp/_funnel_verdict/format_report` 定义与测试一致。✓

---

## 执行说明

- 依赖：仅需 `requests`、`pytest`（项目已用）。
- 网络：需可达 `web.ifzq.gtimg.cn`、`qt.gtimg.cn`、`searchapi.eastmoney.com`、`hq.sinajs.cn`、`datacenter-web.eastmoney.com`。
- Task 间有依赖（Task 2-5 都改 analyzer.py，须顺序执行；Task 8 依赖全部）。
