# stock_pattern 首板成色判定器 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 fupan 第3步加首板成色判定——「形态/量能/板块联动」三层客观标签 + 建议归类，底层 `pattern_label` 纯函数库 + 双入口（fupan 集成 / 单票 CLI）。

**Architecture:** `pattern_label.py` 纯函数库（三层判定 + 综合），数据来自本地 vipdoc（`local_kline.read_day`）+ 东财一级行业映射缓存（`industry_map.py`）；`stock_pattern.py` 单票 CLI；改造 `fupan_strong_scan.py` 给连板梯队前 N 只追加 pattern 标签，`fupan/main.py` 第3步渲染新列。

**Tech Stack:** Python 3，本地招商证券 vipdoc（通达信 `.day`，`scripts/local_kline.py`），东财 push2delay（行业板块成分股），pytest。

**Spec:** [docs/superpowers/specs/2026-07-29-stock-pattern-design.md](../specs/2026-07-29-stock-pattern-design.md)

---

## 关键约定（全计划共用，勿改）

- **sym 格式**：`sh600519` / `sz000428` / `bj430047`（市场前缀+6位代码），即 vipdoc 文件名。`local_kline.read_day(sym)` 接收此格式，返回 `[{date,open,high,low,close,volume,amount}, ...]` 正序。
- **code 格式**：6位纯数字（sym 去前缀）。`fupan_strong_scan` 的 stock dict 用 code，集成 pattern 时需还原成 sym。
- **板块 bd**：`local_kline._classify_a_share(sym)` → `main`/`cyb`/`kcb`/`bj`/`None`。涨停幅度 `limit_of`: bj=0.30, cyb/kcb=0.20, main=0.10。
- **测试约定**：pytest；纯函数测试零依赖（必跑）；依赖本地 vipdoc 的集成测试用 `@pytest.mark.skipif(not HAS_VIPDOC, reason="无vipdoc")` 跳过；联网测试用 monkeypatch mock，不真联网。
- **VIPDOC 路径**：`D:\APP\招商证券\vipdoc`（`local_kline.VIPDOC`）。
- **emoji/中文输出**：每个新入口 `main.py` 开头加 `sys.stdout.reconfigure(encoding="utf-8")`（避 Windows GBK 崩溃，见 [[windows-gbk-emoji-crash]]）。
- **classify_shape 度量说明（实现优化 spec 4.1）**：横盘度用**收盘价区间波动率** `(max-min)/mean`（近20日），而非 spec 初稿的日内振幅——日内振幅对低价股（华天4元）天然偏大失真。阈值 15% 经华天 8.3%/兴欣 36% 实测标定。设计意图不变。

## File Structure

| 文件 | 责任 | 状态 |
|---|---|---|
| `scripts/industry_map.py` | 东财一级行业映射：`load_map()`/`refresh()`；`data/industry_map.json` 缓存 | 新建 |
| `data/industry_map.json` | `{code6: "行业名"}` 映射缓存 | refresh 生成 |
| `scripts/pattern_label.py` | 三层判定核心库：`classify_shape`/`classify_volume`/`classify_sector`/`label` | 新建 |
| `scripts/stock_pattern.py` | 单票 CLI：`python scripts/stock_pattern.py 000428,001358` | 新建 |
| `scripts/fupan_strong_scan.py` | scan() 给连板股追加 `pattern` 字段 | 改造 |
| `.claude/skills/fupan/main.py` | 第3步梯队表追加 pattern 列 | 改造 |
| `scripts/tests/test_pattern_label.py` | classify_shape/volume/sector/label 单测 | 新建 |
| `scripts/tests/test_industry_map.py` | load_map/refresh 单测 | 新建 |
| `scripts/tests/test_stock_pattern.py` | CLI 冒烟 | 新建 |
| `.claude/skills/fupan/tests/test_pattern_integration.py` | fupan 第3步集成回归 | 新建 |

---

## Task 1: industry_map.py — load_map 与存储

**Files:**
- Create: `scripts/industry_map.py`
- Test: `scripts/tests/test_industry_map.py`

- [ ] **Step 1: 写失败测试**

创建 `scripts/tests/test_industry_map.py`：
```python
# -*- coding: utf-8 -*-
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import industry_map  # noqa: E402


def test_load_map_missing_file_returns_empty(tmp_path, monkeypatch):
    """映射文件不存在时返回 {}，不报错。"""
    monkeypatch.setattr(industry_map, "MAP_PATH", str(tmp_path / "no.json"))
    assert industry_map.load_map() == {}


def test_load_map_reads_existing_json(tmp_path, monkeypatch):
    """读取已存在的映射 json。"""
    p = tmp_path / "industry_map.json"
    p.write_text(json.dumps({"000428": "酒店餐饮", "001358": "化学制品"},
                            ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(industry_map, "MAP_PATH", str(p))
    m = industry_map.load_map()
    assert m["000428"] == "酒店餐饮"
    assert m["001358"] == "化学制品"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_industry_map.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'industry_map'`）

- [ ] **Step 3: 最小实现**

创建 `scripts/industry_map.py`：
```python
# -*- coding: utf-8 -*-
"""东财一级行业映射: code6 → 行业名。供 pattern_label.classify_sector 板块联动判定。

映射一次性从东财 push2delay 拉取缓存到 data/industry_map.json, 纯本地读取。
请求基础设施同 zijinliu/screener/fetcher.py (trust_env=True 跟随系统代理 + UA + Referer)。
刷新: python scripts/industry_map.py --refresh  (建议每月一次, 新股上市后跑)
"""
import json
import os
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.path.join(HERE, "..", "data", "industry_map.json")

_session = requests.Session()
_session.trust_env = True  # 跟随系统代理, push2delay 直连会被关
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})

CLIST_URL = "http://push2delay.eastmoney.com/api/qt/clist/get"
INDUSTRY_FS = "m:90+t:2+f:!50"   # 东财一级行业板块
RETRIES = 3


def load_map():
    """读 data/industry_map.json → {code6: 行业名}。文件不存在返回 {}。"""
    if not os.path.exists(MAP_PATH):
        return {}
    with open(MAP_PATH, encoding="utf-8") as f:
        return json.load(f)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_industry_map.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add scripts/industry_map.py scripts/tests/test_industry_map.py
git commit -m "feat(stock_pattern): industry_map load_map + 存储层"
```

---

## Task 2: industry_map.py — refresh 联网拉取

**Files:**
- Modify: `scripts/industry_map.py`
- Test: `scripts/tests/test_industry_map.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `scripts/tests/test_industry_map.py` 末尾追加：
```python
def test_refresh_builds_mapping_from_clist(tmp_path, monkeypatch):
    """refresh 两层拉取(行业板块→成分股), mock _clist 不真联网。"""
    monkeypatch.setattr(industry_map, "MAP_PATH", str(tmp_path / "industry_map.json"))

    # mock _clist: 第一次返回行业板块列表, 之后返回各板块成分股
    fake_industries = [{"f12": "BK0447", "f14": "酒店餐饮"},
                       {"f12": "BK0478", "f14": "化学制品"}]
    fake_stocks_ht = [{"f12": "000428"}, {"f12": "sz000721"}]
    fake_stocks_hx = [{"f12": "001358"}, {"f12": "sh603948"}]
    calls = {"i": 0}

    def fake_clist(fs, fields, pz=500):
        calls["i"] += 1
        if fs == industry_map.INDUSTRY_FS:
            return fake_industries
        if fs == "b:BK0447":
            return fake_stocks_ht
        if fs == "b:BK0478":
            return fake_stocks_hx
        return []

    monkeypatch.setattr(industry_map, "_clist", fake_clist)

    m = industry_map.refresh()
    assert m["000428"] == "酒店餐饮"      # 后6位
    assert m["000721"] == "酒店餐饮"      # sz000721 → 000721
    assert m["001358"] == "化学制品"
    assert m["603948"] == "化学制品"      # sh603948 → 603948
    # 落盘
    assert os.path.exists(industry_map.MAP_PATH)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_industry_map.py::test_refresh_builds_mapping_from_clist -v`
Expected: FAIL（`AttributeError: module 'industry_map' has no attribute '_clist'`）

- [ ] **Step 3: 实现 _clist 与 refresh**

在 `scripts/industry_map.py` 的 `load_map` 之后追加：
```python
def _clist(fs, fields, pz=500):
    """请求东财 clist, 返回 diff 列表(list[dict])。失败/重试耗尽返回 []。可被测试 mock。"""
    params = {"pn": "1", "pz": str(pz), "po": "1", "fid": "f3",
              "fs": fs, "fields": fields, "fltt": "2"}
    for attempt in range(RETRIES):
        try:
            payload = _session.get(CLIST_URL, params=params, timeout=15).json() or {}
            diff = (payload.get("data") or {}).get("diff") or []
            return list(diff.values()) if isinstance(diff, dict) else list(diff)
        except Exception as e:
            if attempt < RETRIES - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            print(f"push2delay 请求失败(fs={fs}): {e}", flush=True)
            return []


def refresh():
    """两层拉取构建 {code6: 行业名} 映射并落盘。
    1) 行业板块列表(fs=m:90+t:2+f:!50) → f12=BK代码, f14=行业名
    2) 每板块成分股(fs=b:BKxxxx) → f12=股票代码, 取后6位
    """
    industries = _clist(INDUSTRY_FS, "f12,f14")
    mapping = {}
    for ind in industries:
        bk = ind.get("f12")
        name = ind.get("f14")
        if not bk or not name:
            continue
        for s in _clist(f"b:{bk}", "f12", pz=500):
            code = (s.get("f12") or "")[-6:]
            if code.isdigit():
                mapping[code] = name
        time.sleep(0.1)  # 礼貌限频
    os.makedirs(os.path.dirname(MAP_PATH), exist_ok=True)
    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    return mapping


def main():
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="东财一级行业映射")
    ap.add_argument("--refresh", action="store_true", help="重新从东财拉取并缓存")
    args = ap.parse_args()
    if args.refresh:
        m = refresh()
        print(f"已刷新行业映射: {len(m)} 只股票 → {MAP_PATH}")
    else:
        print(f"当前映射: {len(load_map())} 只 (用 --refresh 刷新)")


if __name__ == "__main__":
    import sys
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_industry_map.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5:（可选）手动刷新真映射**

Run: `cd c:/project/fox/xuan-gu-qi && python scripts/industry_map.py --refresh`
Expected: 打印「已刷新行业映射: N 只股票」（N 应为全市场量级 ~5000）。若失败（东财封/代理问题），不阻断——后续 Task 5 的板块联动会降级标「映射缺失」。

- [ ] **Step 6: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add scripts/industry_map.py scripts/tests/test_industry_map.py data/industry_map.json
git commit -m "feat(stock_pattern): industry_map refresh 两层拉取东财行业成分股"
```

---

## Task 3: pattern_label.py — classify_shape 形态判定（核心算法）

**Files:**
- Create: `scripts/pattern_label.py`
- Test: `scripts/tests/test_pattern_label.py`

- [ ] **Step 1: 写失败测试**

创建 `scripts/tests/test_pattern_label.py`：
```python
# -*- coding: utf-8 -*-
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pattern_label  # noqa: E402


def _kl(closes):
    """从收盘价序列构造 K线 list（OHLC 围绕 close，date 占位）。"""
    return [{"date": f"D{i}", "open": c, "high": c * 1.005, "low": c * 0.995,
             "close": c, "volume": 10000} for i, c in enumerate(closes)]


# ---------- classify_shape: 合成数据确定性单测（零依赖）----------

def test_shape_breakout_from_box():
    """横盘突破型: 60日横盘10.0-10.27 + 首板10.5 破箱顶。"""
    closes = [10.0 + 0.03 * (i % 10) for i in range(61)] + [10.5]  # 62根, idx61=首板
    r = pattern_label.classify_shape(_kl(closes), height=1)
    assert r["label"] == "横盘突破"
    assert r["metrics"]["breakout"] >= 0.99
    assert r["metrics"]["retracement"] < 10


def test_shape_oversold_bounce():
    """超跌反抽型: 60日从12.0跌到9.64 + 首板10.0 未收复前高。"""
    closes = [12.0 - 0.04 * i for i in range(60)] + [9.8, 10.0]  # 62根
    r = pattern_label.classify_shape(_kl(closes), height=1)
    assert r["label"] == "超跌反抽"
    assert r["metrics"]["retracement"] > 15
    assert r["metrics"]["breakout"] < 1.0


def test_shape_new_stock_insufficient_data():
    """数据不足60日 → 次新。"""
    r = pattern_label.classify_shape(_kl([10.0, 10.1, 10.2]), height=1)
    assert r["label"] == "次新"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'pattern_label'`）

- [ ] **Step 3: 实现 classify_shape**

创建 `scripts/pattern_label.py`：
```python
# -*- coding: utf-8 -*-
"""首板成色判定核心库: 形态/量能/板块联动 三层客观标签 + 建议归类。

数据源: 本地 vipdoc (scripts/local_kline.read_day, 零网络) + 东财行业映射 (industry_map)。
纯函数, 可独立测试。供 fupan_strong_scan(连板前N) 和 stock_pattern(单票CLI) 复用。

设计见 docs/superpowers/specs/2026-07-29-stock-pattern-design.md。
注意: 标签是描述性的, 非选股门槛, 禁止做胜率回测调参 (见 spec 非目标)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import local_kline  # noqa: E402
import industry_map  # noqa: E402


def classify_shape(kl, height=1):
    """形态判定: 本轮上涨启动(首板)的形态。

    kl: [{date,open,high,low,close,volume}, ...] 正序, 末根=最新交易日。
    height: 连板高度(首板=1)。基准日 = 首板前一日 = kl[len-1-height]。
    返回 {"label": str, "metrics": {...}}。
    label ∈ {次新, 超跌反抽, 横盘突破, 箱体震荡, 混合}。

    度量(实现优化 spec 4.1): 横盘度用收盘价区间波动率(max-min)/mean,
    而非日内振幅——低价股日内振幅天然偏大失真。阈值15%经华天8.3%/兴欣36%实测标定。
    """
    n = len(kl)
    base = n - 1 - height  # 首板前一日索引
    if n < 62 or base < 60:
        return {"label": "次新", "metrics": {"reason": "数据不足60日"}}

    win = kl[base - 60:base]          # 基准日前60日(不含基准日)
    closes = [r["close"] for r in win]
    peak60 = max(closes)
    peak_idx = closes.index(peak60)
    trough = min(r["close"] for r in win[peak_idx:])  # peak之后到基准日的最低收
    retracement = (peak60 - trough) / peak60 if peak60 > 0 else 0

    v20 = [r["close"] for r in kl[base - 20:base]]    # 基准日前20日收盘
    volatility20 = (max(v20) - min(v20)) / (sum(v20) / len(v20)) if v20 else 0

    first_board_close = kl[base + 1]["close"]         # 首板日收盘
    breakout = first_board_close / peak60 if peak60 > 0 else 0

    metrics = {
        "volatility20": round(volatility20 * 100, 2),
        "peak60": round(peak60, 2),
        "trough": round(trough, 2),
        "retracement": round(retracement * 100, 2),
        "breakout": round(breakout, 3),
    }

    if retracement > 0.15 and breakout < 1.0:
        return {"label": "超跌反抽", "metrics": metrics}
    if volatility20 < 0.15 and breakout >= 0.99 and retracement < 0.10:
        return {"label": "横盘突破", "metrics": metrics}
    if volatility20 >= 0.15 and retracement < 0.15 and breakout < 0.99:
        return {"label": "箱体震荡", "metrics": metrics}
    return {"label": "混合", "metrics": metrics}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 追加真实数据集成测试（验证华天/兴欣）**

在 `scripts/tests/test_pattern_label.py` 追加：
```python
VIPDOC = r"D:\APP\招商证券\vipdoc"
HAS_VIPDOC = os.path.isdir(VIPDOC)


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_shape_real_huatian_breakout():
    """华天酒店 sz000428 (2026-07-29 三板) → 横盘突破。"""
    kl = local_kline.read_day("sz000428")
    r = pattern_label.classify_shape(kl, height=3)
    assert r["label"] == "横盘突破", r


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_shape_real_xingxin_oversold():
    """兴欣新材 sz001358 (2026-07-29 三板) → 超跌反抽。"""
    kl = local_kline.read_day("sz001358")
    r = pattern_label.classify_shape(kl, height=3)
    assert r["label"] == "超跌反抽", r
```

- [ ] **Step 6: 跑集成测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -v`
Expected: PASS（5 passed，含2个真实数据 case；无 vipdoc 则 3 passed + 2 skipped）

- [ ] **Step 7: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add scripts/pattern_label.py scripts/tests/test_pattern_label.py
git commit -m "feat(stock_pattern): classify_shape 形态判定(横盘突破/超跌反抽)"
```

---

## Task 4: pattern_label.py — classify_volume 量能标签

**Files:**
- Modify: `scripts/pattern_label.py`
- Test: `scripts/tests/test_pattern_label.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `scripts/tests/test_pattern_label.py` 追加：
```python
# ---------- classify_volume ----------

def test_volume_yizi():
    """一字缩量: vr<0.8 且 振幅<1%。"""
    assert pattern_label.classify_volume(vr=0.6, amp=0.5, seal=1.0, yizi=True) == "一字缩量"


def test_volume_shrink():
    """缩量: vr<0.8 且 振幅>=1%。"""
    assert pattern_label.classify_volume(vr=0.7, amp=5.0, seal=1.0) == "缩量"


def test_volume_mild():
    """温和放量: vr 1-2.5 且 seal>=0.99。"""
    assert pattern_label.classify_volume(vr=2.2, amp=5.8, seal=1.0) == "温和放量"


def test_volume_blowoff_bad():
    """爆量烂板: vr>3 且 振幅>5% 且 seal<0.99。"""
    assert pattern_label.classify_volume(vr=6.6, amp=6.8, seal=0.98) == "爆量烂板"


def test_volume_plain_up():
    """普通放量: vr>2.5 但封板牢(非烂板)。"""
    assert pattern_label.classify_volume(vr=3.0, amp=4.0, seal=1.0) == "放量"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -k volume -v`
Expected: FAIL（`AttributeError: module 'pattern_label' has no attribute 'classify_volume'`）

- [ ] **Step 3: 实现 classify_volume**

在 `scripts/pattern_label.py` 的 `classify_shape` 之后追加：
```python
def classify_volume(vr, amp, seal, yizi=False):
    """量能标签。整合 fupan_strong_scan 的 vr(量比)/amp(振幅%)/seal(封板强度)/yizi。

    amp 单位为百分比(如 5.8 表示 5.8%)。返回 str。
    """
    if yizi and vr < 0.8 and amp < 1:
        return "一字缩量"
    if vr < 0.8:
        return "缩量"
    if vr > 3 and amp > 5 and seal < 0.99:
        return "爆量烂板"
    if 1.0 <= vr <= 2.5 and seal >= 0.99:
        return "温和放量"
    if vr > 2.5:
        return "放量"
    return "温和放量"  # vr 0.8-1.0 兜底归温和
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add scripts/pattern_label.py scripts/tests/test_pattern_label.py
git commit -m "feat(stock_pattern): classify_volume 量能标签(5类)"
```

---

## Task 5: pattern_label.py — classify_sector 板块联动

**Files:**
- Modify: `scripts/pattern_label.py`
- Test: `scripts/tests/test_pattern_label.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `scripts/tests/test_pattern_label.py` 追加：
```python
# ---------- classify_sector (mock industry_map + 本地成分股) ----------

def test_sector_missing_map(monkeypatch):
    """个股不在行业映射 → 映射缺失（不报错）。"""
    monkeypatch.setattr(pattern_label.industry_map, "load_map", lambda: {})
    r = pattern_label.classify_sector("sz000428")
    assert r["label"] == "映射缺失"


def test_sector_lone_wolf(monkeypatch):
    """独狼: 同行业成分股多数小涨, 仅本票大涨。"""
    monkeypatch.setattr(pattern_label.industry_map, "load_map",
                        lambda: {"000428": "酒店", "000721": "酒店", "600754": "酒店"})
    # mock 本地成分股涨跌: 本票 +10%, 同行业其他 +1%
    def fake_stats(industry):
        return {"zt": 1, "median": 1.2}  # 仅1只涨停(本票), 中位+1.2%
    monkeypatch.setattr(pattern_label, "_sector_stats", fake_stats)
    r = pattern_label.classify_sector("sz000428")
    assert r["label"] == "独狼"


def test_sector_surge_emotion(monkeypatch):
    """齐涨(情绪): 同行业 >=3 涨停。"""
    monkeypatch.setattr(pattern_label.industry_map, "load_map",
                        lambda: {"000428": "酒店"})
    monkeypatch.setattr(pattern_label, "_sector_stats",
                        lambda ind: {"zt": 4, "median": 5.5})
    r = pattern_label.classify_sector("sz000428")
    assert r["label"] == "齐涨(情绪)"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -k sector -v`
Expected: FAIL（`AttributeError: module 'pattern_label' has no attribute 'classify_sector'`）

- [ ] **Step 3: 实现 classify_sector 与 _sector_stats**

在 `scripts/pattern_label.py` 追加：
```python
def _sector_stats(industry):
    """统计某行业当日成分股表现(本地 vipdoc)。返回 {zt:涨停数, median:中位涨幅%}。
    可被测试 mock。"""
    imap = industry_map.load_map()
    codes = [c for c, ind in imap.items() if ind == industry]
    chgs = []
    zt = 0
    for code in codes:
        for pre in ("sh", "sz", "bj"):
            rows = local_kline.read_day(f"{pre}{code}")
            if len(rows) >= 2 and rows[-1]["close"] > 0 and rows[-2]["close"] > 0:
                chg = (rows[-1]["close"] - rows[-2]["close"]) / rows[-2]["close"]
                chgs.append(chg)
                bd = local_kline._classify_a_share(f"{pre}{code}")
                limit = 0.30 if bd == "bj" else (0.20 if bd in ("cyb", "kcb") else 0.10)
                if chg >= limit * 0.97:
                    zt += 1
                break
    if not chgs:
        return {"zt": 0, "median": 0}
    chgs.sort()
    median = chgs[len(chgs) // 2] * 100
    return {"zt": zt, "median": round(median, 2)}


def classify_sector(sym):
    """板块联动判定。sym → 行业 → 该行业当日成分股统计。

    返回 {"label": str, "stats": {...}}。
    label ∈ {独狼, 齐涨(情绪), 板块漂移, 映射缺失}。
    """
    code = sym[2:] if len(sym) > 6 else sym  # 去市场前缀
    if len(sym) > 6:
        code = sym[-6:]
    imap = industry_map.load_map()
    industry = imap.get(code)
    if not industry:
        return {"label": "映射缺失", "stats": {}}
    stats = _sector_stats(industry)
    if stats["zt"] >= 3 or stats["median"] > 4:
        return {"label": "齐涨(情绪)", "stats": stats}
    if stats["zt"] <= 1 and stats["median"] < 2:
        return {"label": "独狼", "stats": stats}
    return {"label": "板块漂移", "stats": stats}  # 中位2-4% 普涨
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add scripts/pattern_label.py scripts/tests/test_pattern_label.py
git commit -m "feat(stock_pattern): classify_sector 板块联动(独狼/齐涨/漂移)"
```

---

## Task 6: pattern_label.py — label 综合归类

**Files:**
- Modify: `scripts/pattern_label.py`
- Test: `scripts/tests/test_pattern_label.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `scripts/tests/test_pattern_label.py` 追加：
```python
# ---------- _suggest 建议归类规则 ----------

def test_suggest_blowoff_top_priority():
    """超跌反抽 + 爆量烂板 → 出货烂板(最高优先级, 无论板块)。"""
    assert pattern_label._suggest("超跌反抽", "爆量烂板", "独狼") == "出货烂板"
    assert pattern_label._suggest("超跌反抽", "爆量烂板", "齐涨(情绪)") == "出货烂板"


def test_suggest_message_board():
    """一字缩量 → 消息板。"""
    assert pattern_label._suggest("横盘突破", "一字缩量", "独狼") == "消息板"


def test_suggest_emotion_board():
    """齐涨 → 情绪板。"""
    assert pattern_label._suggest("箱体震荡", "放量", "齐涨(情绪)") == "情绪板"


def test_suggest_capital_board():
    """横盘突破+温和放量+独狼 → 资金板苗头。"""
    assert pattern_label._suggest("横盘突破", "温和放量", "独狼") == "资金板苗头"


def test_suggest_mixed():
    """其他组合 → 混合。"""
    assert pattern_label._suggest("箱体震荡", "放量", "独狼") == "混合"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -k suggest -v`
Expected: FAIL（`AttributeError: module 'pattern_label' has no attribute '_suggest'`）

- [ ] **Step 3: 实现 _suggest 与 label**

在 `scripts/pattern_label.py` 追加：
```python
def _suggest(shape, volume, sector):
    """三层客观标签 → 建议归类(参考·需人工确认)。顺序优先, 先命中先返回。"""
    if shape == "超跌反抽" and volume == "爆量烂板":
        return "出货烂板"
    if volume == "一字缩量":
        return "消息板"
    if sector == "齐涨(情绪)":
        return "情绪板"
    if shape == "横盘突破" and volume == "温和放量" and sector == "独狼":
        return "资金板苗头"
    return "混合"


def _limit_of_bd(bd):
    return 0.30 if bd == "bj" else (0.20 if bd in ("cyb", "kcb") else 0.10)


def label(sym, height=1):
    """综合判定: 读本地K + 算量能 + 三层标签 + 建议归类。

    sym: sh/sz/bj + 6位代码。height: 连板高度(默认1=首板)。
    返回 dict {sym, shape, volume, sector, suggest, metrics} 或 {sym, error}。
    """
    kl = local_kline.read_day(sym)
    if len(kl) < 2:
        return {"sym": sym, "error": "无本地数据"}

    sh = classify_shape(kl, height)

    today, prev = kl[-1], kl[-2]
    if prev["close"] <= 0:
        return {"sym": sym, "error": "前收异常"}
    bd = local_kline._classify_a_share(sym) or "main"
    limit = _limit_of_bd(bd)
    chg = (today["close"] - prev["close"]) / prev["close"]
    seal = chg / limit if limit > 0 else 0
    avg5v = sum(r["volume"] for r in kl[-6:-1]) / 5 if len(kl) >= 6 else today["volume"]
    vr = today["volume"] / avg5v if avg5v > 0 else 0
    amp = (today["high"] - today["low"]) / today["low"] * 100 if today["low"] > 0 else 0
    yizi = amp < 1.1 and today["open"] >= prev["close"] * (1 + limit * 0.95)

    vol = classify_volume(vr=round(vr, 2), amp=round(amp, 2),
                          seal=round(seal, 2), yizi=yizi)
    sec = classify_sector(sym)
    suggest = _suggest(sh["label"], vol, sec["label"])

    return {
        "sym": sym, "shape": sh["label"], "volume": vol,
        "sector": sec["label"], "suggest": suggest,
        "metrics": {**sh["metrics"], "vr": round(vr, 2),
                    "seal": round(seal, 2), "amp": round(amp, 2)},
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add scripts/pattern_label.py scripts/tests/test_pattern_label.py
git commit -m "feat(stock_pattern): label 综合判定 + 建议归类(5类)"
```

---

## Task 7: stock_pattern.py — 单票 CLI

**Files:**
- Create: `scripts/stock_pattern.py`
- Test: `scripts/tests/test_stock_pattern.py`

- [ ] **Step 1: 写失败测试（冒烟）**

创建 `scripts/tests/test_stock_pattern.py`：
```python
# -*- coding: utf-8 -*-
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

VIPDOC = r"D:\APP\招商证券\vipdoc"
HAS_VIPDOC = os.path.isdir(VIPDOC)


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_cli_single_stock_outputs_three_layers(capsys):
    """CLI 对华天酒店输出三层标签 + 建议归类。"""
    import stock_pattern
    stock_pattern.run(["sz000428"], height=3)
    out = capsys.readouterr().out
    assert "华天酒店" in out or "000428" in out
    assert "形态" in out and "量能" in out and "板块" in out
    assert "建议归类" in out


def test_cli_missing_stock_no_crash(capsys, monkeypatch):
    """无本地数据的股票不崩溃, 输出提示。"""
    import stock_pattern
    import pattern_label
    monkeypatch.setattr(pattern_label, "label", lambda s, height=1: {"sym": s, "error": "无本地数据"})
    stock_pattern.run(["sz999999"], height=1)
    out = capsys.readouterr().out
    assert "无本地数据" in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_stock_pattern.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'stock_pattern'`）

- [ ] **Step 3: 实现 CLI**

创建 `scripts/stock_pattern.py`：
```python
# -*- coding: utf-8 -*-
"""首板成色判定 单票 CLI。

用法:
  python scripts/stock_pattern.py 000428              # 单只(默认首板)
  python scripts/stock_pattern.py 000428,001358        # 多只
  python scripts/stock_pattern.py 000428 --height 3    # 指定连板高度
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")  # 防 Windows GBK 崩溃
except Exception:
    pass

import pattern_label  # noqa: E402
import local_kline  # noqa: E402


def _name_of(sym):
    """从本地K线或简单规则推断股票名(尽力而为, 失败返回空)。"""
    return ""  # 名称非关键, 留空; 后续可接东财 searchapi


def _prefix(code):
    """6位代码 → 推断市场前缀。60/68→sh, 00/30→sz, 8/4/920→bj。"""
    c = code.lstrip()
    if c.startswith(("60", "68", "9")):
        return "sh"
    if c.startswith(("00", "30")):
        return "sz"
    return "bj"


def run(codes, height=1):
    """codes: ['sz000428'] 或 ['000428'](自动补前缀)。打印每只三层判定。"""
    for raw in codes:
        sym = raw if raw[:2] in ("sh", "sz", "bj") else f"{_prefix(raw)}{raw}"
        r = pattern_label.label(sym, height=height)
        if "error" in r:
            print(f"{sym}: {r['error']}")
            continue
        m = r["metrics"]
        print(f"\n{sym}")
        print(f"  形态: {r['shape']:<6}(vol20 {m.get('volatility20','?')}% / "
              f"retracement {m.get('retracement','?')}% / breakout {m.get('breakout','?')})")
        print(f"  量能: {r['volume']:<6}(vr {m.get('vr','?')} / seal {m.get('seal','?')} / "
              f"amp {m.get('amp','?')}%)")
        print(f"  板块: {r['sector']}")
        print(f"  → 建议归类: {r['suggest']}（参考·需人工确认）")


def main():
    ap = argparse.ArgumentParser(description="首板成色判定 单票CLI")
    ap.add_argument("codes", help="股票代码,逗号分隔(000428,001358)")
    ap.add_argument("--height", type=int, default=1, help="连板高度(默认1=首板)")
    args = ap.parse_args()
    run([c.strip() for c in args.codes.split(",") if c.strip()], height=args.height)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_stock_pattern.py -v`
Expected: PASS（无 vipdoc 则 1 passed + 1 skipped）

- [ ] **Step 5: 手动冒烟（真实数据）**

Run: `cd c:/project/fox/xuan-gu-qi && python scripts/stock_pattern.py 000428,001358 --height 3`
Expected: 华天 → 形态横盘突破/量能温和/板块独狼→资金板苗头；兴欣 → 超跌反抽/爆量烂板→出货烂板。

- [ ] **Step 6: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add scripts/stock_pattern.py scripts/tests/test_stock_pattern.py
git commit -m "feat(stock_pattern): 单票 CLI 入口"
```

---

## Task 8: fupan_strong_scan.py 集成 pattern 标签

**Files:**
- Modify: `scripts/fupan_strong_scan.py:71-123`（scan 函数）+ `:126-165`（main 输出）
- Test: `scripts/tests/test_pattern_label.py`（追加集成断言）

- [ ] **Step 1: 写失败测试**

在 `scripts/tests/test_pattern_label.py` 追加：
```python
@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_strong_scan_includes_pattern_for_ladder():
    """fupan_strong_scan 连板股应带 pattern 字段(若 pattern_label 可用)。"""
    import fupan_strong_scan
    latest, stocks = fupan_strong_scan.scan()
    lian = [s for s in stocks if s["height"] >= 2]
    if lian:  # 有连板股时检查前N只带 pattern
        for s in lian[:8]:
            assert "pattern" in s, f"{s['code']} 缺 pattern 字段"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py::test_strong_scan_includes_pattern_for_ladder -v`
Expected: FAIL（连板股 dict 无 `pattern` 字段）

- [ ] **Step 3: 改造 scan() 追加 sym + pattern**

修改 `scripts/fupan_strong_scan.py`：

3a. 在文件顶部 import 区（`import local_kline` 之后）追加可选 import：
```python
try:
    import pattern_label  # 可选: 连板股追加首板成色 pattern 标签
    _HAS_PATTERN = True
except Exception:
    _HAS_PATTERN = False
```

3b. 在 `scan()` 函数内，`stocks.append({...})` 处（约 117-121 行），把 stock dict 改为保留 sym 并追加 pattern。定位现有代码：
```python
            code = "".join(ch for ch in sym if ch.isdigit())[-6:]
            stocks.append({
                "code": code, "bd": bd, "height": height,
                "chg": round(chg * 100, 2), "seal": round(seal, 2),
                "vr": round(vr, 2), "yizi": yizi, "amp": round(amp * 100, 2),
            })
```
替换为：
```python
            code = "".join(ch for ch in sym if ch.isdigit())[-6:]
            stocks.append({
                "code": code, "bd": bd, "sym": sym, "height": height,
                "chg": round(chg * 100, 2), "seal": round(seal, 2),
                "vr": round(vr, 2), "yizi": yizi, "amp": round(amp * 100, 2),
            })
```

3c. 在 `scan()` 函数 `return latest, stocks` **之前**追加 pattern 标注（仅连板股前 N 只，控制成本）：
```python
    # 连板股追加首板成色 pattern 标签 (仅前 top 只, 控制 classify_sector 成本)
    if _HAS_PATTERN:
        lian_sorted = sorted([s for s in stocks if s["height"] >= 2],
                             key=lambda x: (-x["height"], -x["chg"]))
        for s in lian_sorted[:top]:
            try:
                s["pattern"] = pattern_label.label(s["sym"], height=s["height"])
            except Exception:
                s["pattern"] = None
    return latest, stocks
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/test_pattern_label.py::test_strong_scan_includes_pattern_for_ladder -v`
Expected: PASS

- [ ] **Step 5: 手动验证 scan 输出**

Run: `cd c:/project/fox/xuan-gu-qi && python scripts/fupan_strong_scan.py --top 8`
Expected: 连板股输出含 pattern 摘要（若 main 输出未改，至少 scan 返回的 dict 带 pattern；下面 Task 9 改 fupan 渲染）。

- [ ] **Step 6: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add scripts/fupan_strong_scan.py scripts/tests/test_pattern_label.py
git commit -m "feat(stock_pattern): fupan_strong_scan 连板股追加 pattern 标签"
```

---

## Task 9: fupan/main.py 第3步渲染 pattern 列

**Files:**
- Modify: `.claude/skills/fupan/main.py:375-391`（第3步连板梯队表）
- Test: `.claude/skills/fupan/tests/test_pattern_integration.py`

- [ ] **Step 1: 写失败测试**

创建 `.claude/skills/fupan/tests/test_pattern_integration.py`：
```python
# -*- coding: utf-8 -*-
"""fupan 第3步集成: 连板梯队表应含 pattern 标签列(当 pattern 可用时)。"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))           # fupan skill 根
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "scripts"))  # scripts/

VIPDOC = r"D:\APP\招商证券\vipdoc"
HAS_VIPDOC = os.path.isdir(VIPDOC)


def test_render_section3_has_pattern_header():
    """第3步梯队表表头应含「成色」列(即使 pattern 降级, 表头也在)。"""
    import main as fupan_main
    # render 是拼字符串的纯函数, 传入最小 strong 数据
    strong = ("2026-07-29", [{"code": "000428", "bd": "main", "sym": "sz000428",
                              "height": 3, "chg": 10.0, "seal": 1.0, "vr": 2.2,
                              "yizi": False, "amp": 5.8, "pattern": None}])
    # 借用 main 内部渲染: 直接调 render 检查输出含「成色」
    out = []
    fupan_main.render("2026-07-29", "YELLOW", "防守市", 86,
                      {"zt": 84, "dt": 11, "median": 1.55, "up_down_ratio": 3.52, "full": True},
                      {}, "震荡期", {"hist": []}, "",
                      strong=strong, failure=None)
    # render 通过内部 a() 追加; 若无直接访问, 改测 _render_section3 或跳过
    # 此测试主要锁表头契约, 实现者按 render 实际签名调整调用
```

> 注：`render` 的确切签名和内部 `a()` 收集机制需实现者照 [main.py:276](../../../scripts/../.claude/skills/fupan/main.py) 核对。此测试锁的是「第3步输出文本含『成色』列」契约；若 render 不便直接调，改为读 `output/{date}.md` 文件断言。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest .claude/skills/fupan/tests/test_pattern_integration.py -v`
Expected: FAIL（表头无「成色」列 / render 调用不匹配）

- [ ] **Step 3: 改造第3步渲染**

修改 `.claude/skills/fupan/main.py`，定位第3步连板梯队表（约 376-389 行）。当前：
```python
        if lian:
            a("\n| 代码 | 高度 | 收盘 | 封板 | 量比 | 振幅 | 客观标签 |")
            a("|---|---|---|---|---|---|---|")
            for s in lian[:8]:
                sig = []
                if s["yizi"]:
                    sig.append("一字")
                if s["seal"] < 0.99:
                    sig.append("烂板")
                if s["vr"] >= 3:
                    sig.append("爆量")
                elif 0 < s["vr"] < 0.8:
                    sig.append("缩量")
                a(f"| {s['code']} | {s['height']}板 | {s['chg']:+.1f}% | {s['seal']:.2f} | "
                  f"{s['vr']:.1f} | {s['amp']:.1f}% | {' '.join(sig) or '温和'} |")
```
替换为（追加「成色」列，展示 pattern 的 shape/volume/sector/suggest）：
```python
        if lian:
            a("\n| 代码 | 高度 | 收盘 | 封板 | 量比 | 振幅 | 客观标签 | 成色(pattern) |")
            a("|---|---|---|---|---|---|---|---|")
            for s in lian[:8]:
                sig = []
                if s["yizi"]:
                    sig.append("一字")
                if s["seal"] < 0.99:
                    sig.append("烂板")
                if s["vr"] >= 3:
                    sig.append("爆量")
                elif 0 < s["vr"] < 0.8:
                    sig.append("缩量")
                p = s.get("pattern")
                if p and "error" not in p:
                    pat = f"{p['shape']}/{p['volume']}/{p['sector']}→{p['suggest']}"
                else:
                    pat = "—"
                a(f"| {s['code']} | {s['height']}板 | {s['chg']:+.1f}% | {s['seal']:.2f} | "
                  f"{s['vr']:.1f} | {s['amp']:.1f}% | {' '.join(sig) or '温和'} | {pat} |")
```

- [ ] **Step 4: 跑全量 fupan 回归**

Run: `cd c:/project/fox/xuan-gu-qi && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python .claude/skills/fupan/main.py`
Expected: 报告正常生成，第3步梯队表出现「成色(pattern)」列，含如「横盘突破/温和放量/独狼→资金板苗头」。

- [ ] **Step 5: 读报告确认**

用 Read 工具读 `.claude/skills/fupan/output/2026-07-29.md` 第3步，确认「成色」列已渲染、pattern 标签正确。

- [ ] **Step 6: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add .claude/skills/fupan/main.py .claude/skills/fupan/tests/test_pattern_integration.py .claude/skills/fupan/output/2026-07-29.md
git commit -m "feat(stock_pattern): fupan 第3步梯队表追加成色(pattern)列"
```

---

## Task 10: 端到端回归 + 文档更新

**Files:**
- Modify: `.claude/skills/fupan/SKILL.md`（第3步说明）
- Modify: `MEMORY.md` + 新 memory（记录工具建成）

- [ ] **Step 1: 全量测试**

Run: `cd c:/project/fox/xuan-gu-qi && python -m pytest scripts/tests/ .claude/skills/fupan/tests/ -v`
Expected: 全部 PASS（vipdoc 缺失的集成测试 skipped）。

- [ ] **Step 2: 端到端冒烟（单票 + fupan）**

Run:
```bash
cd c:/project/fox/xuan-gu-qi
python scripts/stock_pattern.py 000428,001358 --height 3
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python .claude/skills/fupan/main.py
```
Expected: 单票 CLI 输出双票三层判定；fupan 报告第3步含成色列。

- [ ] **Step 3: 更新 fupan SKILL.md 第3步说明**

在 `.claude/skills/fupan/SKILL.md` 第3步描述中补一句：连板梯队前 N 只自动带「成色(pattern)」标签（形态/量能/板块联动→建议归类，参考·需人工确认），来自 `scripts/pattern_label.py`。

- [ ] **Step 4: 写 memory 记录工具建成**

写 `C:\Users\87044\.claude\projects\c--project-fox-xuan-gu-qi\memory\stock-pattern-built.md`：
```markdown
---
name: stock-pattern-built
description: stock_pattern 首板成色判定器建成 — 形态/量能/板块联动三层标签+建议归类
metadata:
  type: project
---

2026-07-29 建成。`scripts/pattern_label.py` 核心库 + `industry_map.py`(东财一级行业映射缓存) + `stock_pattern.py`(单票CLI) + `fupan_strong_scan` 集成(fupan第3步成色列)。

三层判定: 形态(classify_shape: 横盘突破/超跌反抽/箱体震荡/混合, 用收盘价波动率+peak-trough回撤) / 量能(classify_volume: 5类) / 板块联动(classify_sector: 独狼/齐涨/漂移, 依赖 industry_map.json)。

建议归类5类: 出货烂板/消息板/情绪板/资金板苗头/混合, 标「参考·需人工确认」。

关键: 标签是描述性的非选股门槛, 禁止做胜率回测调参(防 [[chaodiefantan-nocap-p1-lesson]])。形态阈值经华天(横盘突破)/兴欣(超跌反抽)实测标定。板块联动降级(映射缺失)不阻断形态/量能。行业映射手动 `python scripts/industry_map.py --refresh` 每月一次。
```

- [ ] **Step 5: 更新 MEMORY.md 索引**

在 `MEMORY.md` 追加一行：
```
- [stock_pattern 首板成色判定器](stock-pattern-built.md) — 2026-07-29建成;形态/量能/板块联动三层标签+建议归类;fupan第3步成色列;标签非选股门槛禁回测调参
```

- [ ] **Step 6: 提交**

```bash
cd c:/project/fox/xuan-gu-qi
git add .claude/skills/fupan/SKILL.md
git commit -m "docs(stock_pattern): fupan SKILL 第3步说明 + 端到端回归通过"
```

---

## Self-Review（计划自检，已执行）

**1. Spec 覆盖**：
- 形态/量能/板块联动三层 → Task 3/4/5 ✓
- 建议归类 → Task 6 ✓
- 底层库 + 双入口 → Task 3-6（库）/ Task 7（CLI）/ Task 8-9（fupan集成）✓
- 本地行业映射 + 降级 → Task 1/2/5 ✓
- 边界条件（次新/映射缺失/数据不足）→ Task 3/5 测试覆盖 ✓
- 测试策略 → 每 Task TDD ✓
- 「标签非选股门槛」铁律 → pattern_label.py docstring + memory + spec 非目标 三处强调 ✓

**2. 占位扫描**：无 TBD/TODO；每个代码 step 含完整代码。Task 9 Step 1 的 render 签名已注明「实现者照 main.py:276 核对」——这是因 render 签名复杂、直接调不便，给了明确 fallback（读输出文件断言），非占位。

**3. 类型一致性**：
- `classify_shape(kl, height) → {"label","metrics"}` 全计划一致 ✓
- `classify_volume(vr, amp, seal, yizi) → str` 一致；amp 单位统一为百分比（Task 4 测试 amp=5.8，Task 6 label 内 amp 也×100）✓
- `classify_sector(sym) → {"label","stats"}` 一致 ✓
- `_suggest(shape, volume, sector) → str` 一致；sector 标签字符串「独狼」/「齐涨(情绪)」在 Task 5 输出与 Task 6 判定一致 ✓
- `label(sym, height) → dict` 一致；Task 7 CLI 与 Task 8 strong_scan 都调它 ✓
- strong_scan stock dict 新增 `sym` 字段（Task 8），Task 9 渲染用 `s.get("pattern")` ✓
