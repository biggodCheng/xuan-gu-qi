# eval-stock 第⑦维度「承接」实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 eval-stock 新增第⑦维度「承接」（3 信号：下跌缩量 / 不破支撑 / 砸盘收回），作为参考维度输出灯标，不参与漏斗淘汰。

**Architecture:** 纯函数 `check_support(kline)` 加在 analyzer.py，复用现有日K数据源（零新依赖）。main.py 调一行打包进 stock dict；reporter.py 加⑦行输出 + 承接弱软警示；`_lamp` 靠 pass 键三态约定（hit≥2 带 True / hit==0 带 False / hit==1 或 None 省略）自动兼容，无需改动。

**Tech Stack:** Python 3.10、pytest、纯标准库（无新依赖）

**Spec:** [../specs/2026-07-19-eval-stock-support-dimension-design.md](../specs/2026-07-19-eval-stock-support-dimension-design.md)

---

## File Structure

| 文件 | 责任 | 改动 |
|------|------|------|
| `.claude/skills/eval-stock/screener/analyzer.py` | 纯函数分析层 | 新增 5 个常量 + `check_support` 函数 |
| `.claude/skills/eval-stock/tests/test_analyzer.py` | analyzer 单测 | 新增 `_kline_ohlc` helper + 5 个 `check_support` 用例 |
| `.claude/skills/eval-stock/main.py` | CLI 编排 | `evaluate_one` 调 `check_support` + 打包 `stock["support"]` |
| `.claude/skills/eval-stock/screener/reporter.py` | 终端 markdown | `format_report` 加⑦行 + `_oneliner` 加承接弱警示 |
| `.claude/skills/eval-stock/tests/test_reporter.py` | reporter 单测 | 新增 `_base_stock` helper + 2 个⑦维度用例 |
| `.claude/skills/eval-stock/SKILL.md` | skill 文档 | 6→7维度、输出示例、反例 |

---

## Task 1: analyzer.py — 常量 + `check_support` 纯函数（TDD）

**Files:**
- Modify: `.claude/skills/eval-stock/screener/analyzer.py`（顶部常量区 + 文件末尾加函数）
- Test: `.claude/skills/eval-stock/tests/test_analyzer.py`（末尾追加）

- [ ] **Step 1: 写失败测试**

在 `tests/test_analyzer.py` **末尾**追加：

```python
from screener.analyzer import check_support


def _kline_ohlc(records):
    """records: [(open, high, low, close, volume), ...] → kline。"""
    return [{"date": f"d{i}", "open": o, "high": h, "low": l, "close": c, "volume": v}
            for i, (o, h, l, c, v) in enumerate(records)]


def test_support_all_hit():
    # base 20 根平台 low=9.0；recent 10 根：缩量下跌 + 不破支撑 + 长下影收回
    base = [(10, 10.3, 9.0, 10, 100)] * 20
    recent = [
        (10.0, 10.3, 9.8, 10.1, 100),
        (10.1, 10.3, 9.9, 9.9, 70),    # 缩量下跌：close 9.9<10.1，vol 70<100*0.8
        (10.0, 10.3, 9.0, 10.2, 100),  # 长下影收回：下影比 0.77
    ] + [(10.2, 10.3, 9.5, 10.0, 100)] * 7
    r = check_support(_kline_ohlc(base + recent))
    assert r["hit_count"] == 3
    assert r["pass"] is True


def test_support_only_shadow():
    # 仅砸盘收回：recent 无下跌日（信号1✗）、跌破前平台（信号2✗）、有长下影（信号3✓）
    base = [(10, 10.3, 9.0, 10, 100)] * 20
    recent = [
        (10.0, 10.3, 8.5, 10.1, 200),  # low 8.5 跌破 9.0*0.98；close 涨
        (10.1, 10.3, 8.5, 10.2, 150),  # 长下影收回：下影比 0.89
    ] + [(10.2, 10.5, 8.5, 10.3, 120)] * 8
    r = check_support(_kline_ohlc(base + recent))
    assert r["hit_count"] == 1
    assert "pass" not in r  # 一般 ➖


def test_support_none():
    # 全不命中：放量下跌破支撑、无长下影
    base = [(10, 10.3, 9.0, 10, 100)] * 20
    recent = [
        (10.0, 10.1, 9.8, 9.5, 200),   # 下跌放量
        (9.5, 9.6, 8.5, 8.6, 250),     # 继续下跌破支撑
    ] + [(8.6, 8.7, 8.0, 8.1, 300)] * 8
    r = check_support(_kline_ohlc(base + recent))
    assert r["hit_count"] == 0
    assert r["pass"] is False


def test_support_insufficient():
    r = check_support(_kline_ohlc([(10, 10, 9, 10, 100)] * 20))
    assert r["hit_count"] is None
    assert "数据不足" in r["label"]
    assert "pass" not in r


def test_support_bearish_candle_not_counted():
    # 大阴线（open高 close低）下影比必 <0.5，不应被算作砸盘收回
    base = [(10, 10.3, 9.0, 10, 100)] * 20
    recent = [
        (10.0, 10.2, 9.9, 10.0, 100),  # 小实体无下影
        (10.1, 10.3, 9.9, 9.9, 70),    # 缩量下跌 → 信号1 ✓
        (10.5, 10.6, 8.9, 9.0, 100),   # 大阴线：下影比 0.06 → 信号3 ✗
    ] + [(9.0, 10.3, 9.0, 10.0, 100)] * 7  # recent_low 8.9 ≥ 8.82 → 信号2 ✓
    r = check_support(_kline_ohlc(base + recent))
    assert r["hit_count"] == 2  # 信号1+2，大阴线未贡献信号3
    assert r["pass"] is True
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd .claude/skills/eval-stock && python -m pytest tests/test_analyzer.py -v`
Expected: FAIL — `ImportError: cannot import name 'check_support'`

- [ ] **Step 3: 加常量**

在 `analyzer.py` 顶部常量区（`MKTCAP_THRESHOLD = 500` 之后）追加：

```python
SUPPORT_WINDOW = 10        # 承接观察窗口（近 N 交易日）
SUPPORT_LOOKBACK = 20      # 支撑基准回看（回调前平台）
SUPPORT_TOLERANCE = 0.98   # 不破支撑容忍度（防假跌破）
LOWER_SHADOW_RATIO = 0.5   # 长下影阈值（下影占振幅比）
SUPPORT_HIT_THRESHOLD = 2  # "承接有力"命中信号门槛
```

注：`SHRINK_RATIO = 0.8` 已存在，信号1 直接复用，不重复定义。

- [ ] **Step 4: 实现 `check_support`**

在 `analyzer.py` 末尾（`check_marketcap` 之后）追加：

```python
def check_support(kline: list[dict]) -> dict:
    """承接 3 信号：下跌缩量 / 不破支撑 / 砸盘收回(长下影代理)。

    返回 {hit_count, signals, label, detail}。pass 键按 hit_count 三态：
    >= SUPPORT_HIT_THRESHOLD → True（✅）；==0 → False（❌）；
    ==1 或数据不足(None) → 省略该键（reporter._lamp 走 else → ➖）。
    """
    need = SUPPORT_WINDOW + SUPPORT_LOOKBACK
    if len(kline) < need:
        return {"hit_count": None, "label": "数据不足",
                "detail": f"K线仅 {len(kline)} 根，需 ≥{need}"}

    start = len(kline) - SUPPORT_WINDOW
    recent = kline[start:]
    base = kline[start - SUPPORT_LOOKBACK:start]

    # 信号1：下跌缩量 — 近窗口内存在 close<prev_close 且 volume<prev*SHRINK_RATIO
    s1 = False
    s1_ratio = None
    for i in range(start, len(kline)):
        prev = kline[i - 1]
        if kline[i]["close"] < prev["close"] and prev["volume"] > 0:
            ratio = kline[i]["volume"] / prev["volume"]
            if ratio < SHRINK_RATIO:
                s1, s1_ratio = True, ratio
                break

    # 信号2：不破支撑 — 近窗口最低价 ≥ 回调前平台低点 × 容忍度
    base_low = min(d["low"] for d in base)
    recent_low = min(d["low"] for d in recent)
    s2 = recent_low >= base_low * SUPPORT_TOLERANCE

    # 信号3：砸盘收回 — 近窗口内存在长下影K（下影占振幅 ≥ LOWER_SHADOW_RATIO）
    s3 = False
    s3_ratio = None
    for d in recent:
        hi, lo = d["high"], d["low"]
        if hi <= lo:
            continue
        ratio = (min(d["open"], d["close"]) - lo) / (hi - lo)
        if ratio >= LOWER_SHADOW_RATIO:
            s3, s3_ratio = True, ratio
            break

    signals = [s1, s2, s3]
    hit = sum(signals)
    names = []
    if s1: names.append("缩量")
    if s2: names.append("不破支撑")
    if s3: names.append("砸盘收回")

    detail_parts = []
    if s1_ratio is not None:
        detail_parts.append(f"量比{s1_ratio:.2f}")
    detail_parts.append(f"低{recent_low:.2f}/撑{base_low:.2f}")
    if s3_ratio is not None:
        detail_parts.append(f"下影{s3_ratio:.2f}")
    detail = "；".join(detail_parts)

    if hit >= SUPPORT_HIT_THRESHOLD:
        return {"hit_count": hit, "signals": signals, "pass": True,
                "label": f"有力（{hit}/3：{'、'.join(names)}）", "detail": detail}
    if hit == 0:
        return {"hit_count": 0, "signals": signals, "pass": False,
                "label": "弱（0/3）", "detail": detail}
    return {"hit_count": 1, "signals": signals,
            "label": f"一般（1/3：{names[0]}）", "detail": detail}
```

- [ ] **Step 5: 跑测试验证通过**

Run: `cd .claude/skills/eval-stock && python -m pytest tests/test_analyzer.py -v`
Expected: PASS（全部 analyzer 用例含新增 5 个）

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/eval-stock/screener/analyzer.py .claude/skills/eval-stock/tests/test_analyzer.py
git commit -m "feat(eval-stock): 新增⑦承接维度check_support纯函数(3信号+5测试)"
```

---

## Task 2: main.py — 接入调用

**Files:**
- Modify: `.claude/skills/eval-stock/main.py`

- [ ] **Step 1: 扩展 import**

把 [main.py:13-15](../../../.claude/skills/eval-stock/main.py#L13-L15) 的 import 改为：

```python
from screener.analyzer import (
    check_new_high, check_recent_zt, check_pullback, check_marketcap,
    check_support,
)
```

- [ ] **Step 2: 在 evaluate_one 中调用**

在 [main.py:124](../../../.claude/skills/eval-stock/main.py#L124) `mc = check_marketcap(total, circ)` 之后插入一行：

```python
    sp = check_support(kline)
```

- [ ] **Step 3: 打包进返回 dict**

在 [main.py:137](../../../.claude/skills/eval-stock/main.py#L137) 返回 dict 的字段列表中，`"marketcap": mc,` 之后加：

```python
        "marketcap": mc, "support": sp,
```

（即把原 `"marketcap": mc,` 替换为 `"marketcap": mc, "support": sp,`）

- [ ] **Step 4: 跑现有 main 测试确认未破坏**

Run: `cd .claude/skills/eval-stock && python -m pytest tests/test_main.py -v`
Expected: PASS（全绿）

- [ ] **Step 5: 单只冒烟确认 support 字段存在**

Run: `cd .claude/skills/eval-stock && python -c "import sys; sys.path.insert(0,'.'); from main import evaluate_one; r=evaluate_one('000021'); print(r.get('support'))"`
Expected: 打印一个 dict，含 `hit_count` 和 `label`（网络取数失败时为 `{"hit_count": None, "label": "数据不足", ...}` 也算正常通过——证明字段已接入）

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/eval-stock/main.py
git commit -m "feat(eval-stock): evaluate_one接入check_support,打包support字段"
```

---

## Task 3: reporter.py — ⑦行输出 + 承接弱警示（TDD）

**Files:**
- Modify: `.claude/skills/eval-stock/screener/reporter.py`
- Test: `.claude/skills/eval-stock/tests/test_reporter.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_reporter.py` **末尾**追加：

```python
def _base_stock():
    """基本达标 stock（①②③④全过），用于⑦维度测试。"""
    return {
        "code": "000021", "name": "深科技", "industry": "消费电子",
        "last_date": "2026-07-07", "last_close": 54.07, "intraday": False,
        "new_high": {"pass": True, "label": "今日新高"},
        "zt": {"pass": True, "label": "2 次"},
        "pullback": {"pass": True, "label": "d6 起 2 天"},
        "marketcap": {"pass": True, "label": "150 亿", "total": 150, "circ": 150},
        "q2": {"verdict": "中性", "confidence": "中", "netprofit_yoy": 35.35,
               "revenue_yoy": 10.67, "summary": "..."},
        "track": {"tracks": ["AI硬件和基础设施"], "main": "AI硬件和基础设施",
                  "main_conf": "中"},
        "support": {"hit_count": 2, "pass": True, "label": "有力（2/3：缩量、不破支撑）"},
        "error": None,
    }


def test_format_report_support_strong():
    stock = _base_stock()
    out = format_report(stock)
    assert "⑦ 承接" in out
    assert "有力" in out


def test_format_report_support_weak_warns():
    stock = _base_stock()
    stock["support"] = {"hit_count": 0, "pass": False, "label": "弱（0/3）"}
    out = format_report(stock)
    assert "⑦ 承接" in out
    assert "承接偏弱，等买点" in out  # 软警示出现在"一句话"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd .claude/skills/eval-stock && python -m pytest tests/test_reporter.py::test_format_report_support_strong tests/test_reporter.py::test_format_report_support_weak_warns -v`
Expected: FAIL — `AssertionError: assert "⑦ 承接" in out`（reporter 还没输出⑦行）

- [ ] **Step 3: format_report 加⑦行**

在 [reporter.py:80](../../../.claude/skills/eval-stock/screener/reporter.py#L80) ⑥赛道 else 分支之后、`lines.append("─" * 45)` 之前插入：

```python

    # 承接（参考维度，不进漏斗）
    sp = stock.get("support", {})
    lines.append(f"⑦ 承接        {_lamp(sp)}  {sp.get('label', '')}")
```

- [ ] **Step 4: _oneliner 加承接弱警示**

在 [reporter.py:42-43](../../../.claude/skills/eval-stock/screener/reporter.py#L42-L43) `if q2v == "偏负": parts.append("Q2偏负")` 之后插入：

```python
    if stock.get("support", {}).get("hit_count") == 0:
        parts.append("承接偏弱，等买点")
```

- [ ] **Step 5: 跑测试验证通过**

Run: `cd .claude/skills/eval-stock && python -m pytest tests/test_reporter.py -v`
Expected: PASS（全部 reporter 用例含新增 2 个）

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/eval-stock/screener/reporter.py .claude/skills/eval-stock/tests/test_reporter.py
git commit -m "feat(eval-stock): reporter输出⑦承接行+承接弱软警示(等买点)"
```

---

## Task 4: SKILL.md 文档 + 端到端冒烟

**Files:**
- Modify: `.claude/skills/eval-stock/SKILL.md`

- [ ] **Step 1: 更新 description / 标题**

把 [SKILL.md:3](../../../.claude/skills/eval-stock/SKILL.md#L3) description 中的「6 个维度」改为「7 个维度」，维度列表括号补充「/ 承接」：

```
description: 个股定点体检器 — 给定任意一只 A 股（代码或名称），跑 qsht 选股体系的 7 个维度（趋势新高 / 近期涨停 / 缩量回踩 / 市值 / Q2 业绩展望 / 四大赛道 / 承接），...
```

- [ ] **Step 2: 维度列表加⑦**

把 [SKILL.md:19](../../../.claude/skills/eval-stock/SKILL.md#L19) 的 `## 6 维度` 改为 `## 7 维度`，并在第 6 项后追加：

```markdown
6. **赛道**：复用 sidasaidao（四大赛道）。
7. **承接**（参考维度，不进漏斗）：3 信号 — 下跌缩量(量比<0.8) / 不破支撑(近10日低点≥回调前20日低点×0.98) / 砸盘收回(长下影占振幅≥50%)。命中≥2 ✅有力 / =1 ➖一般 / =0 ❌弱。数据源=日K，无新依赖。
```

- [ ] **Step 3: 输出示例加⑦行**

在 [SKILL.md:40](../../../.claude/skills/eval-stock/SKILL.md#L40) ⑥赛道示例行之后插入：

```
⑦ 承接        ✅  有力（3/3：缩量、不破支撑、砸盘收回）
```

- [ ] **Step 4: 反例黑名单加一行**

在 [SKILL.md:64](../../../.claude/skills/eval-stock/SKILL.md#L64) 反例表末尾追加一行：

```markdown
| 承接弱就弃单 | 承接是买点维度非成色筛选，承接弱=等买点 ≠ 不买 | 趋势在但承接弱 → 等买点；⑦为参考维度不参与漏斗淘汰 |
```

- [ ] **Step 5: 端到端冒烟（实盘 2 只）**

Run: `cd .claude/skills/eval-stock && python main.py 深科技,有研新材`
Expected: 每只输出含 `⑦ 承接 {灯标} {label}` 行；灯标与 label 合理（非异常崩溃）。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/eval-stock/SKILL.md
git commit -m "docs(eval-stock): SKILL.md更新7维度+⑦承接说明+输出示例+反例"
```

---

## Self-Review（计划自检结果）

**Spec 覆盖**：spec §2 决策 → Task 1 常量/口径；§3 三信号 → Task 1 实现；§4.1-4.4 接入点 → Task 1-4 逐文件；§5 测试 5 用例 → Task 1 Step 1（含数据不足 None、大阴线边界）；§6 边界 → Task 1 数据不足兜底 + Task 4 冒烟。无遗漏。

**Placeholder**：无 TBD/TODO，所有代码块完整。

**Type 一致性**：`check_support` 返回 `{hit_count, signals, pass(三态), label, detail}`，main 打包为 `stock["support"]`，reporter `_lamp(sp)` 与 `_oneliner` 读 `hit_count`/`pass`——字段名跨任务一致。

**Spec 同步**：写计划时发现信号3 的 `close>=中点` 条件冗余（ratio≥0.5 已数学蕴含），已同步修正 spec §3.3，计划与 spec 一致。
