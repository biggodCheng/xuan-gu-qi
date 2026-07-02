# 中报预报跟踪器（zhongbaoyubao）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个跨天持久化的 A 股中报业绩预告事件跟踪器——扫描"预增且同比下限≥50%"的公司入池,以公告次日开盘价为基准跟踪 30 个交易日的累计涨跌,每日生成 markdown 报告。

**Architecture:** 方案 A(持久化跟踪池)。`data/watchlist.json` 承载跨天状态(active/expired/skipped 三区)。每次执行幂等增量更新:扫描预告→新股入池→对 active 全量拉前复权日K重算涨跌(基准价与当前价同源,避免除权失真)→到期迁移→生成报告。基准价/当前价统一取自腾讯 fqkline 前复权序列。

**Tech Stack:** Python 3.10+、requests(直连禁代理)、pandas、concurrent.futures、pytest。零新依赖。

**Spec:** `docs/superpowers/specs/2026-07-02-zhongbaoyubao-design.md`

---

## File Structure（接口契约,后续任务严格遵循)

| 文件 | 职责 | 关键函数签名 |
|---|---|---|
| `screener/__init__.py` | 包标识 | 空 |
| `screener/fetcher.py` | 网络:业绩预告扫描 + 前复权日K + 名称解析 | 见下 |
| `screener/analyzer.py` | 纯逻辑:筛选/涨跌/到期 | 见下 |
| `screener/storage.py` | watchlist.json 读写/去重/迁移 | 见下 |
| `screener/reporter.py` | markdown 报告生成 | `render_report(pool, today_str) -> str` |
| `main.py` | 编排入口 + CHECKPOINT | `run(today_str=None) -> bool` |
| `tests/test_analyzer.py` `tests/test_storage.py` `tests/test_fetcher.py` | 单测 | pytest |
| `SKILL.md` | skill 说明 + 实测字段记录 | — |
| `requirements.txt` `.gitignore` `data/.gitkeep` `output/.gitkeep` | 工程文件 | — |

**fetcher.py 契约:**
```python
def resolve_stock_code(query: str) -> tuple[str | None, str | None]: ...
def get_announcements(report_date="2026-06-30", predict_type="预增",
                      yoy_lower_min=50.0) -> list[dict]: ...
#   返回 [{"code","name","industry","notice_date","yoy_lower","yoy_upper"}]
def get_kline_since(code: str, since_date: str) -> list[dict]: ...
#   返回 [{"date","open","close"}] 前复权正序, since_date 之后; 失败返回 []
```

**analyzer.py 契约(顶部常量):**
```python
PREDICT_TYPE = "预增"
YOY_LOWER_MIN = 50.0
HOLD_DAYS = 30
def filter_announcements(items, yoy_lower_min=YOY_LOWER_MIN, predict_type=PREDICT_TYPE) -> list[dict]: ...
def compute_chg_total(base_price, curr_close) -> float | None: ...
def compute_chg_today(prev_close, curr_close) -> float | None: ...
def build_daily(kline: list[dict], base_price: float) -> list[dict]: ...  # [{date,close,chg_total,chg_today}]
def held_days(daily: list[dict]) -> int: ...
def should_expire(held: int, hold_days=HOLD_DAYS) -> bool: ...
```

**storage.py 契约:**
```python
def empty_pool() -> dict: ...
def load_watchlist(path: str) -> dict: ...        # 不存在/损坏→空池(损坏先备份)
def save_watchlist(pool: dict, path: str) -> None: ...
def existing_codes(pool: dict) -> set[str]: ...    # active+expired+skipped 的 code 并集
def add_active(pool: dict, stock: dict) -> None: ...
def refresh_active(pool: dict, code: str, fields: dict) -> None: ...  # 覆盖式更新 base/daily/last_close/chg_*
def migrate_expired(pool: dict, hold_days=30) -> list[str]: ...        # 返回本次迁出的 code
def add_skipped(pool: dict, code: str, name: str, notice_date: str, reason: str) -> None: ...
```

**watchlist.json 结构(全流程统一):**
```json
{"report_period":"2026H1","report_date":"2026-06-30","updated_at":"...",
 "threshold":{...},
 "active":[{"code","name","industry","predict_type","yoy_lower","yoy_upper",
            "notice_date","base_date","base_price","held_days","remain_days",
            "last_close","chg_total","chg_today","base_note","daily":[{date,close,chg_total,chg_today}]}],
 "expired":[同active结构],
 "skipped":[{"code","name","notice_date","reason"}]}
```

---

## Task 0: 脚手架

**Files:**
- Create: `.claude/skills/zhongbaoyubao/screener/__init__.py`(空)
- Create: `.claude/skills/zhongbaoyubao/tests/__init__.py`(空)
- Create: `.claude/skills/zhongbaoyubao/requirements.txt`
- Create: `.claude/skills/zhongbaoyubao/.gitignore`
- Create: `.claude/skills/zhongbaoyubao/data/.gitkeep`
- Create: `.claude/skills/zhongbaoyubao/output/.gitkeep`

- [ ] **Step 1: 建目录与空文件**

```bash
mkdir -p .claude/skills/zhongbaoyubao/screener .claude/skills/zhongbaoyubao/tests .claude/skills/zhongbaoyubao/data .claude/skills/zhongbaoyubao/output
```

`screener/__init__.py` 与 `tests/__init__.py` 内容为空字符串。

- [ ] **Step 2: 写 requirements.txt**

```
pandas>=2.0.0
requests>=2.28.0
```

- [ ] **Step 3: 写 .gitignore**

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
data/*.json
output/*.md
```

- [ ] **Step 4: 建 .gitkeep 占位**

`data/.gitkeep` 与 `output/.gitkeep` 内容为空字符串(保证空目录入库)。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/zhongbaoyubao/
git commit -m "feat(zhongbaoyubao): 脚手架(目录/依赖/gitignore)"
```

---

## Task 1: 业绩预告接口字段探测(🔴 关键 CHECKPOINT)

> spec 第 6.1 节:东方财富业绩预告接口字段名需实测。本任务产出"确认后的字段名",写入下方常量,后续 fetcher 严格使用。**不可跳过**。

**Files:**
- Create: `.claude/skills/zhongbaoyubao/probe_yjyg.py`(临时探测脚本,实现后保留作排障工具)

- [ ] **Step 1: 写探测脚本**

```python
"""探测东方财富业绩预告接口字段名。

运行: python probe_yjyg.py
打印第一条预增样本的全部字段,人工确认 reportName 与字段名后,
把结果填入 screener/fetcher.py 顶部常量。
"""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))

_SESSION = requests.Session()
_SESSION.trust_env = False
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})

# 候选 reportName(优先试这个,失败换 RPT_PUBLIC_OP_PREDICT)
REPORT_NAMES = ["RPT_LICO_FN_CPD_GD", "RPT_PUBLIC_OP_PREDICT"]


def probe(report_date="2026-06-30"):
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    for rn in REPORT_NAMES:
        params = {
            "sortColumns": "NOTICE_DATE",
            "sortTypes": "-1",
            "pageSize": "5",
            "pageNumber": "1",
            "reportName": rn,
            "columns": "ALL",
            "filter": f'(REPORTDATE=\'{report_date}\')',
        }
        r = _SESSION.get(url, params=params, timeout=15)
        data = r.json()
        ok = data.get("success")
        rows = (data.get("result") or {}).get("data") or []
        print(f"\n=== reportName={rn} success={ok} rows={len(rows)} ===")
        if rows:
            print(json.dumps(rows[0], ensure_ascii=False, indent=2))
            print("\n-- 含 RATE/CHANGE/LOWER/UPPER/TYPE 的字段(候选同比/类型) --")
            for k, v in rows[0].items():
                kw = ("RATE", "CHANGE", "LOWER", "UPPER", "TYPE", "PREDICT", "NOTICE", "PROFIT")
                if any(x in k.upper() for x in kw):
                    print(f"  {k} = {v}")
            return rn
    print("两个 reportName 均无数据,需更换报告期或确认接口。")
    return None


if __name__ == "__main__":
    probe()
```

- [ ] **Step 2: 运行探测,记录字段**

```bash
cd .claude/skills/zhongbaoyubao && PYTHONUTF8=1 python probe_yjyg.py
```

Expected: 打印出某个 reportName 下的样本字段全表 + 候选字段清单。

人工对照样本,确认以下映射(填入 Task 9 的 fetcher 常量):
- 公告日字段(候选 `NOTICE_DATE`)
- 报告期字段(候选 `REPORTDATE`)
- 预告类型字段(候选 `PREDICT_TYPE`,值含"预增")
- 同比变动下限字段(候选 `CHANGE_RATE_LOWER`,单位 %)
- 同比变动上限字段(候选 `CHANGE_RATE_UPPER`)

- [ ] **Step 3: 把确认结果写进 SKILL.md 的"实测字段"小节(在 Task 12 一并完成;此处先在计划/草稿记下)**

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/zhongbaoyubao/probe_yjyg.py
git commit -m "chore(zhongbaoyubao): 业绩预告接口字段探测脚本"
```

---

## Task 2: analyzer — 筛选纯函数 filter_announcements

**Files:**
- Create: `.claude/skills/zhongbaoyubao/screener/analyzer.py`
- Test: `.claude/skills/zhongbaoyubao/tests/test_analyzer.py`

- [ ] **Step 1: 写失败测试**

`tests/test_analyzer.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.analyzer import filter_announcements


def test_keeps_preannounce_above_threshold():
    items = [{"code": "A", "predict_type": "预增", "yoy_lower": 50.0, "yoy_upper": 80.0}]
    out = filter_announcements(items)
    assert len(out) == 1 and out[0]["code"] == "A"


def test_rejects_below_threshold():
    items = [{"code": "B", "predict_type": "预增", "yoy_lower": 49.9, "yoy_upper": 60.0}]
    assert filter_announcements(items) == []


def test_rejects_non_preannounce():
    items = [{"code": "C", "predict_type": "扭亏", "yoy_lower": 999.0}]
    assert filter_announcements(items) == []


def test_rejects_missing_yoy_lower():
    items = [{"code": "D", "predict_type": "预增", "yoy_lower": None}]
    assert filter_announcements(items) == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd .claude/skills/zhongbaoyubao && PYTHONUTF8=1 python -m pytest tests/test_analyzer.py -v
```
Expected: FAIL (`ModuleNotFoundError: screener.analyzer`)

- [ ] **Step 3: 实现 analyzer.py(筛选部分)**

```python
"""分析层(纯逻辑,无网络):筛选预告、计算涨跌、到期判定。

可调阈值在顶部。watchlist 的 daily 系列计算口径:基准价=基准日(公告后首个交易日)开盘,
累计涨跌=(今收-基准价)/基准价;当日涨跌=(今收-昨收)/昨收。基准价与当前价同取自一条
前复权日K序列,避免除权失真。
"""

# ---- 可调阈值 ----
PREDICT_TYPE = "预增"      # 仅纳入预增(扭亏/续盈/略增本期不收)
YOY_LOWER_MIN = 50.0       # 同比下限 ≥ 50% 入池
HOLD_DAYS = 30             # 跟踪交易日数


def filter_announcements(items: list[dict], yoy_lower_min: float = YOY_LOWER_MIN,
                         predict_type: str = PREDICT_TYPE) -> list[dict]:
    """筛选达标预告:类型=预增 且同比下限≥阈值。

    Args:
        items: fetcher.get_announcements 返回的列表,每条含
               {code,name,industry,predict_type,notice_date,yoy_lower,yoy_upper}
    Returns:
        达标条目(原样透传,补 predict_type 缺省)。
    """
    out = []
    for it in items:
        if (it.get("predict_type") or "") != predict_type:
            continue
        lo = it.get("yoy_lower")
        if lo is None:
            continue
        try:
            lo_f = float(lo)
        except (TypeError, ValueError):
            continue
        if lo_f >= yoy_lower_min:
            out.append(it)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_analyzer.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add screener/analyzer.py tests/test_analyzer.py
git commit -m "feat(zhongbaoyubao): analyzer 筛选纯函数(filter_announcements)"
```

---

## Task 3: analyzer — 涨跌计算 compute_chg_*、build_daily、held_days

**Files:**
- Modify: `.claude/skills/zhongbaoyubao/screener/analyzer.py`(追加函数)
- Test: `.claude/skills/zhongbaoyubao/tests/test_analyzer.py`(追加用例)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_analyzer.py` 末尾追加:
```python
from screener.analyzer import compute_chg_total, compute_chg_today, build_daily, held_days


def test_chg_total_basic():
    assert compute_chg_total(10.0, 11.0) == 10.0


def test_chg_total_zero_base_protected():
    assert compute_chg_total(0.0, 5.0) is None


def test_chg_today_basic():
    assert compute_chg_today(10.0, 11.0) == 10.0


def test_chg_today_none_when_no_prev():
    assert compute_chg_today(None, 11.0) is None


def test_build_daily_first_row_chg_today_equals_total():
    kline = [{"date": "2026-07-11", "open": 10.0, "close": 10.5}]
    daily = build_daily(kline, base_price=10.0)
    assert len(daily) == 1
    assert daily[0]["chg_total"] == 5.0
    assert daily[0]["chg_today"] == 5.0  # 首日=累计


def test_build_daily_multi_rows():
    kline = [
        {"date": "2026-07-11", "open": 10.0, "close": 10.0},
        {"date": "2026-07-14", "open": 10.1, "close": 11.0},
    ]
    daily = build_daily(kline, base_price=10.0)
    assert daily[0]["chg_total"] == 0.0
    assert daily[1]["chg_total"] == 10.0
    assert daily[1]["chg_today"] == 10.0  # (11-10)/10


def test_held_days():
    kline = [{"date": f"2026-07-{d}", "open": 10.0, "close": 10.0} for d in (11, 12, 13)]
    daily = build_daily(kline, 10.0)
    assert held_days(daily) == 2  # len-1


def test_build_daily_empty():
    assert build_daily([], 10.0) == []
```

- [ ] **Step 2: 跑测试确认新用例失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_analyzer.py -v
```
Expected: 新用例 FAIL (ImportError)

- [ ] **Step 3: 在 analyzer.py 追加实现**

```python
def _r2(v):
    """保留 2 位小数,None 透传。"""
    return round(v, 2) if v is not None else None


def compute_chg_total(base_price, curr_close) -> float | None:
    """累计涨跌% = (今收 − 基准价)/基准价。基准为 0/None → None。"""
    if not base_price or curr_close is None:
        return None
    return _r2((curr_close - base_price) / base_price * 100)


def compute_chg_today(prev_close, curr_close) -> float | None:
    """当日涨跌% = (今收 − 昨收)/昨收。无昨收(首日)→ None。"""
    if not prev_close or curr_close is None:
        return None
    return _r2((curr_close - prev_close) / prev_close * 100)


def build_daily(kline: list[dict], base_price: float) -> list[dict]:
    """前复权日K序列 → 每日涨跌系列。

    kline: [{"date","open","close"}, ...] 正序,基准日=首条。
    返回 [{"date","close","chg_total","chg_today"}, ...],首条 chg_today=chg_total。
    """
    daily = []
    prev_close = None
    for bar in kline:
        close = bar.get("close")
        chg_total = compute_chg_total(base_price, close)
        chg_today = compute_chg_today(prev_close, close)
        if chg_today is None:  # 首条
            chg_today = chg_total
        daily.append({"date": bar.get("date"), "close": close,
                      "chg_total": chg_total, "chg_today": chg_today})
        prev_close = close
    return daily


def held_days(daily: list[dict]) -> int:
    """持有交易日数 = len(daily) − 1(基准日为第 0 天)。"""
    return max(0, len(daily) - 1)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_analyzer.py -v
```
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add screener/analyzer.py tests/test_analyzer.py
git commit -m "feat(zhongbaoyubao): analyzer 涨跌计算(build_daily/chg/held_days)"
```

---

## Task 4: analyzer — 到期判定 should_expire

**Files:**
- Modify: `.claude/skills/zhongbaoyubao/screener/analyzer.py`(追加)
- Test: `.claude/skills/zhongbaoyubao/tests/test_analyzer.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
from screener.analyzer import should_expire


def test_not_expired_at_29():
    assert should_expire(29) is False


def test_expired_at_30():
    assert should_expire(30) is True


def test_expired_above_30():
    assert should_expire(35) is True


def test_custom_hold_days():
    assert should_expire(9, hold_days=10) is False
    assert should_expire(10, hold_days=10) is True
```

- [ ] **Step 2: 跑确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_analyzer.py::test_expired_at_30 -v
```
Expected: FAIL (ImportError)

- [ ] **Step 3: 追加实现**

```python
def should_expire(held: int, hold_days: int = HOLD_DAYS) -> bool:
    """持有天数 ≥ 跟踪窗口 → 到期。"""
    return held >= hold_days
```

- [ ] **Step 4: 跑确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_analyzer.py -v
```
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add screener/analyzer.py tests/test_analyzer.py
git commit -m "feat(zhongbaoyubao): analyzer 到期判定(should_expire)"
```

---

## Task 5: storage — 基础读写 + 损坏兜底

**Files:**
- Create: `.claude/skills/zhongbaoyubao/screener/storage.py`
- Test: `.claude/skills/zhongbaoyubao/tests/test_storage.py`

- [ ] **Step 1: 写失败测试**

`tests/test_storage.py`:
```python
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.storage import empty_pool, load_watchlist, save_watchlist


def test_empty_pool_shape():
    p = empty_pool()
    assert p["active"] == [] and p["expired"] == [] and p["skipped"] == []
    assert p["report_date"] == "2026-06-30"
    assert p["threshold"]["yoy_lower_min"] == 50.0


def test_save_then_load_roundtrip(tmp_path):
    path = str(tmp_path / "watchlist.json")
    p = empty_pool()
    p["active"].append({"code": "000001", "name": "平安银行"})
    save_watchlist(p, path)
    loaded = load_watchlist(path)
    assert loaded["active"][0]["code"] == "000001"


def test_load_missing_returns_empty_pool(tmp_path):
    path = str(tmp_path / "nope.json")
    p = load_watchlist(path)
    assert p["active"] == []


def test_load_corrupt_backups_and_rebuilds(tmp_path):
    path = str(tmp_path / "watchlist.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not valid json ")
    p = load_watchlist(path)
    assert p["active"] == []  # 重建空池
    assert os.path.exists(path + ".bad")  # 损坏文件已备份
```

- [ ] **Step 2: 跑确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_storage.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 storage.py(基础部分)**

```python
"""watchlist.json 持久化:读写、去重、覆盖式刷新、到期迁移、损坏兜底。

watchlist 结构见计划 File Structure。load 对损坏文件先备份为 *.bad 再返回空池,
保证主流程不崩。
"""
import datetime
import json
import os

REPORT_PERIOD = "2026H1"
REPORT_DATE = "2026-06-30"
THRESHOLD = {
    "predict_type": "预增",
    "yoy_lower_min": 50.0,
    "hold_days": 30,
    "base": "次日开盘",
}


def empty_pool() -> dict:
    return {
        "report_period": REPORT_PERIOD,
        "report_date": REPORT_DATE,
        "updated_at": "",
        "threshold": dict(THRESHOLD),
        "active": [],
        "expired": [],
        "skipped": [],
    }


def load_watchlist(path: str) -> dict:
    """加载 watchlist;不存在→空池;损坏→备份 *.bad 后返回空池。"""
    if not os.path.exists(path):
        return empty_pool()
    try:
        with open(path, "r", encoding="utf-8") as f:
            pool = json.load(f)
        for k in ("active", "expired", "skipped"):
            pool.setdefault(k, [])
        return pool
    except (json.JSONDecodeError, ValueError):
        bad = path + ".bad"
        # 不覆盖已存在的 .bad,加日期后缀
        if os.path.exists(bad):
            bad = f"{path}.bad.{datetime.date.today()}"
        try:
            os.replace(path, bad)
        except OSError:
            pass
        print(f"⚠️ watchlist 损坏,已备份到 {bad},重建空池", flush=True)
        return empty_pool()


def save_watchlist(pool: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pool["updated_at"] = datetime.date.today().strftime("%Y-%m-%d")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 跑确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_storage.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add screener/storage.py tests/test_storage.py
git commit -m "feat(zhongbaoyubao): storage 基础读写+损坏兜底"
```

---

## Task 6: storage — 去重 existing_codes + add_active + refresh_active

**Files:**
- Modify: `.claude/skills/zhongbaoyubao/screener/storage.py`(追加)
- Test: `.claude/skills/zhongbaoyubao/tests/test_storage.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
from screener.storage import existing_codes, add_active, refresh_active


def test_existing_codes_union(tmp_path):
    p = empty_pool()
    p["active"] = [{"code": "A"}]
    p["expired"] = [{"code": "B"}]
    p["skipped"] = [{"code": "C"}]
    assert existing_codes(p) == {"A", "B", "C"}


def test_add_active_appends(tmp_path):
    p = empty_pool()
    add_active(p, {"code": "A", "name": "X", "notice_date": "2026-07-10"})
    assert len(p["active"]) == 1
    assert p["active"][0]["daily"] == []
    assert p["active"][0]["held_days"] == 0


def test_refresh_active_overwrites_daily_and_fields(tmp_path):
    p = empty_pool()
    add_active(p, {"code": "A", "name": "X", "notice_date": "2026-07-10"})
    daily = [{"date": "2026-07-11", "close": 11.0, "chg_total": 10.0, "chg_today": 10.0}]
    refresh_active(p, "A", {
        "base_date": "2026-07-11", "base_price": 10.0,
        "daily": daily, "last_close": 11.0,
        "chg_total": 10.0, "chg_today": 10.0,
        "held_days": 1, "remain_days": 29,
    })
    a = p["active"][0]
    assert a["base_price"] == 10.0
    assert a["daily"] == daily          # 覆盖式
    assert a["last_close"] == 11.0
    assert a["held_days"] == 1
```

- [ ] **Step 2: 跑确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_storage.py -v
```
Expected: 新用例 FAIL

- [ ] **Step 3: 追加实现**

```python
def existing_codes(pool: dict) -> set:
    """active+expired+skipped 的 code 并集(去重用)。"""
    codes = set()
    for sec in ("active", "expired", "skipped"):
        for s in pool.get(sec, []):
            if s.get("code"):
                codes.add(s["code"])
    return codes


def add_active(pool: dict, stock: dict) -> None:
    """新股入 active 占位(daily 待刷新填)。补默认字段。"""
    entry = {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "industry": stock.get("industry", ""),
        "predict_type": stock.get("predict_type", "预增"),
        "yoy_lower": stock.get("yoy_lower"),
        "yoy_upper": stock.get("yoy_upper"),
        "notice_date": stock.get("notice_date"),
        "base_date": "",
        "base_price": None,
        "held_days": 0,
        "remain_days": 30,
        "last_close": None,
        "chg_total": None,
        "chg_today": None,
        "base_note": "",
        "daily": [],
    }
    pool["active"].append(entry)


def refresh_active(pool: dict, code: str, fields: dict) -> None:
    """覆盖式更新某 active 股的 daily 及汇总字段(前复权口径每次整体覆盖)。"""
    for s in pool["active"]:
        if s["code"] == code:
            s.update(fields)
            return
    raise KeyError(f"active 中找不到 {code}")
```

- [ ] **Step 4: 跑确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_storage.py -v
```
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add screener/storage.py tests/test_storage.py
git commit -m "feat(zhongbaoyubao): storage 去重/入池/覆盖式刷新"
```

---

## Task 7: storage — 到期迁移 migrate_expired + skipped

**Files:**
- Modify: `.claude/skills/zhongbaoyubao/screener/storage.py`(追加)
- Test: `.claude/skills/zhongbaoyubao/tests/test_storage.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
from screener.storage import migrate_expired, add_skipped, remove_skipped


def test_migrate_expired_moves_qualifying(tmp_path):
    p = empty_pool()
    p["active"] = [
        {"code": "A", "held_days": 29, "daily": [{"date": "x"}]},
        {"code": "B", "held_days": 30, "daily": [{"date": "y"}]},
    ]
    moved = migrate_expired(p)
    assert moved == ["B"]
    assert [a["code"] for a in p["active"]] == ["A"]
    assert [e["code"] for e in p["expired"]] == ["B"]


def test_add_and_remove_skipped(tmp_path):
    p = empty_pool()
    add_skipped(p, "C", "X", "2026-07-10", "K线拉取失败")
    assert len(p["skipped"]) == 1
    remove_skipped(p, "C")
    assert p["skipped"] == []
```

- [ ] **Step 2: 跑确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_storage.py -v
```
Expected: 新用例 FAIL

- [ ] **Step 3: 追加实现**

```python
def migrate_expired(pool: dict, hold_days: int = 30) -> list:
    """把 active 中 held_days ≥ hold_days 的迁入 expired,返回迁出的 code 列表。"""
    stay, moved = [], []
    for s in pool["active"]:
        if (s.get("held_days") or 0) >= hold_days:
            moved.append(s)
        else:
            stay.append(s)
    pool["active"] = stay
    pool["expired"].extend(moved)
    return [m["code"] for m in moved]


def add_skipped(pool: dict, code: str, name: str, notice_date: str, reason: str) -> None:
    """入池失败(K线缺失等)记入 skipped,下次执行重试。"""
    pool["skipped"].append({
        "code": code, "name": name, "notice_date": notice_date, "reason": reason,
    })


def remove_skipped(pool: dict, code: str) -> None:
    """重试成功后从 skipped 移除。"""
    pool["skipped"] = [s for s in pool["skipped"] if s["code"] != code]
```

- [ ] **Step 4: 跑确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_storage.py -v
```
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add screener/storage.py tests/test_storage.py
git commit -m "feat(zhongbaoyubao): storage 到期迁移+skipped 重试"
```

---

## Task 8: fetcher — 前复权日K get_kline_since

**Files:**
- Create: `.claude/skills/zhongbaoyubao/screener/fetcher.py`(本任务建文件,先写 session + get_kline_since)
- Test: `.claude/skills/zhongbaoyubao/tests/test_fetcher.py`

> 复用 chuangxingao 腾讯 fqkline 模式,但取 open(item[1]) + close(item[2]) + date(item[0]),并按 since_date 截断。

- [ ] **Step 1: 写失败测试(mock 网络)**

`tests/test_fetcher.py`:
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener import fetcher


def test_get_kline_since_filters_before_since(monkeypatch):
    raw = [
        ["2026-07-10", "9.80", "10.00", "10.1", "9.7", "1000"],  # 公告日当天(应排除)
        ["2026-07-11", "10.00", "10.50", "10.6", "9.9", "2000"], # 基准日(次日)
        ["2026-07-14", "10.40", "11.00", "11.1", "10.3", "3000"],
    ]

    def fake_tencent(code, start):
        return raw

    monkeypatch.setattr(fetcher, "_fetch_tencent_kline", fake_tencent)
    out = fetcher.get_kline_since("600000", "2026-07-10")
    assert [r["date"] for r in out] == ["2026-07-11", "2026-07-14"]
    assert out[0]["open"] == 10.00 and out[0]["close"] == 10.50


def test_get_kline_since_empty_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(fetcher, "_fetch_tencent_kline", lambda c, s: [])
    monkeypatch.setattr(fetcher, "_fetch_sina_closes", lambda c: [])
    assert fetcher.get_kline_since("600000", "2026-07-10") == []
```

- [ ] **Step 2: 跑确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_fetcher.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 fetcher.py(session + get_kline_since)**

```python
"""数据获取层 — 业绩预告扫描 + 前复权日K + 名称解析。

数据源:
- 业绩预告:东方财富 datacenter-web(字段名见顶部常量,经 probe_yjyg.py 实测)
- 前复权日K:腾讯 fqkline(失败回退新浪,新浪仅 close 无 open → 基准价缺失时上游标 skipped)
- 股票搜索:东方财富 searchapi

禁用本地代理,避免干扰(与 q2zhanwang/chuangxingao 一致)。
"""
import os
import re
from datetime import datetime, timedelta

import requests

for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})


def _tencent_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def _sina_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def _fetch_tencent_kline(code: str, start_date: str) -> list[list]:
    """腾讯前复权日K,返回 [[date, open, close, high, low, amount], ...]。失败返回 []。"""
    symbol = _tencent_symbol(code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    # 拉足够长(公告后 30 交易日 ≈ 45 自然日,取 90 天余量)
    params = {"param": f"{symbol},day,{start_date},,90,qfq"}
    try:
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("code") != 0:
            return []
        sd = data.get("data", {}).get(symbol, {})
        rows = sd.get("qfqday", []) or sd.get("day", [])
        return rows or []
    except Exception:
        return []


def _fetch_sina_closes(code: str) -> list[str]:
    """新浪日K回退(仅 close,无 open)。返回 [close, ...] 或 []。"""
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {"symbol": _sina_symbol(code), "scale": "240", "ma": "no", "datalen": "60"}
    try:
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        return [item["close"] for item in (data or [])]
    except Exception:
        return []


def get_kline_since(code: str, since_date: str) -> list[dict]:
    """取 since_date 之后的前复权日K(腾讯),返回 [{date,open,close},...] 正序。

    since_date 当天排除(预告公告日 → 取其后首个交易日为基准日)。
    腾讯失败时回退新浪,但新浪无 open → 返回[](上游据此标 skipped)。
    """
    rows = _fetch_tencent_kline(code, since_date)
    if not rows:
        return []  # 回退新浪无 open,无法取基准价 → 空
    out = []
    for row in rows:
        try:
            d, o, c = row[0], float(row[1]), float(row[2])
        except (IndexError, ValueError, TypeError):
            continue
        if d <= since_date:  # 严格晚于公告日
            continue
        out.append({"date": d, "open": o, "close": c})
    return out
```

- [ ] **Step 4: 跑确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_fetcher.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add screener/fetcher.py tests/test_fetcher.py
git commit -m "feat(zhongbaoyubao): fetcher 前复权日K(get_kline_since)"
```

---

## Task 9: fetcher — 业绩预告扫描 get_announcements

> 依赖 Task 1 探测确认的字段名。下方常量用候选名,若 Task 1 实测不同,改顶部常量即可(单点修改)。

**Files:**
- Modify: `.claude/skills/zhongbaoyubao/screener/fetcher.py`(追加)
- Test: `.claude/skills/zhongbaoyubao/tests/test_fetcher.py`(追加)

- [ ] **Step 1: 追加失败测试(mock)**

```python
from screener import fetcher


def test_get_announcements_parses_rows(monkeypatch):
    payload = {
        "success": True,
        "result": {"data": [
            {"SECURITY_CODE": "600160", "SECURITY_NAME_ABBR": "巨化股份",
             "NOTICE_DATE": "2026-07-10", "REPORTDATE": "2026-06-30",
             "PREDICT_TYPE": "预增", "CHANGE_RATE_LOWER": 80.0, "CHANGE_RATE_UPPER": 120.0,
             "PUBLISHNAME": "化学制品"},
        ]},
    }
    monkeypatch.setattr(fetcher, "_request_announcements",
                        lambda report_date, page: (payload, True))
    out = fetcher.get_announcements(report_date="2026-06-30")
    assert out[0]["code"] == "600160"
    assert out[0]["name"] == "巨化股份"
    assert out[0]["notice_date"] == "2026-07-10"
    assert out[0]["yoy_lower"] == 80.0
    assert out[0]["yoy_upper"] == 120.0


def test_get_announcements_empty_when_api_fails(monkeypatch):
    monkeypatch.setattr(fetcher, "_request_announcements",
                        lambda report_date, page: ({}, False))
    assert fetcher.get_announcements() == []
```

- [ ] **Step 2: 跑确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_fetcher.py -v
```
Expected: 新用例 FAIL

- [ ] **Step 3: 在 fetcher.py 追加实现**

> 在文件顶部(常量区)追加字段常量;在文件末尾追加函数。

顶部追加(放在 import 之后、session 之前):
```python
# === 业绩预告接口(经 probe_yjyg.py 实测;若字段名不同仅改这里)===
YJYG_REPORT_NAME = "RPT_LICO_FN_CPD_GD"
FLD_CODE = "SECURITY_CODE"
FLD_NAME = "SECURITY_NAME_ABBR"
FLD_INDUSTRY = "PUBLISHNAME"
FLD_NOTICE_DATE = "NOTICE_DATE"
FLD_REPORT_DATE = "REPORTDATE"
FLD_PREDICT_TYPE = "PREDICT_TYPE"      # 值含"预增"
FLD_YOY_LOWER = "CHANGE_RATE_LOWER"    # 同比下限 %
FLD_YOY_UPPER = "CHANGE_RATE_UPPER"    # 同比上限 %
```

末尾追加:
```python
def _request_announcements(report_date: str, page: int) -> tuple[dict, bool]:
    """请求业绩预告一页,返回 (json, success)。"""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "sortColumns": FLD_NOTICE_DATE,
        "sortTypes": "-1",
        "pageSize": "100",
        "pageNumber": str(page),
        "reportName": YJYG_REPORT_NAME,
        "columns": "ALL",
        "filter": f"({FLD_REPORT_DATE}='{report_date}')",
    }
    try:
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        return data, bool(data.get("success"))
    except Exception as e:
        print(f"业绩预告请求失败(page {page}): {e}", flush=True)
        return {}, False


def _to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_announcements(report_date: str = "2026-06-30", predict_type: str = "预增",
                      yoy_lower_min: float = 50.0) -> list[dict]:
    """扫描全A某报告期的业绩预告,返回已按类型过滤的原始条目(幅度门槛由 analyzer 再筛)。

    返回 [{"code","name","industry","notice_date","predict_type","yoy_lower","yoy_upper"}]
    分页拉满(每页 100)。类型≠predict_type 的条目不返回。
    """
    out = []
    page = 1
    while True:
        data, ok = _request_announcements(report_date, page)
        if not ok:
            break
        rows = (data.get("result") or {}).get("data") or []
        if not rows:
            break
        for row in rows:
            if (row.get(FLD_PREDICT_TYPE) or "") != predict_type:
                continue
            out.append({
                "code": row.get(FLD_CODE),
                "name": row.get(FLD_NAME),
                "industry": row.get(FLD_INDUSTRY, ""),
                "notice_date": (row.get(FLD_NOTICE_DATE) or "")[:10],
                "predict_type": predict_type,
                "yoy_lower": _to_float(row.get(FLD_YOY_LOWER)),
                "yoy_upper": _to_float(row.get(FLD_YOY_UPPER)),
            })
        if len(rows) < 100:
            break
        page += 1
        if page > 20:  # 安全上限(2000 条)
            break
    return out
```

- [ ] **Step 4: 跑确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_fetcher.py -v
```
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add screener/fetcher.py tests/test_fetcher.py
git commit -m "feat(zhongbaoyubao): fetcher 业绩预告扫描(get_announcements)"
```

---

## Task 10: reporter — markdown 报告 render_report

**Files:**
- Create: `.claude/skills/zhongbaoyubao/screener/reporter.py`
- Test: `.claude/skills/zhongbaoyubao/tests/test_reporter.py`

- [ ] **Step 1: 写失败测试**

`tests/test_reporter.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.storage import empty_pool, add_active, refresh_active
from screener.reporter import render_report


def _pool_with_active():
    p = empty_pool()
    add_active(p, {"code": "600160", "name": "巨化股份", "yoy_lower": 80.0,
                   "yoy_upper": 120.0, "notice_date": "2026-07-10"})
    refresh_active(p, "600160", {
        "base_date": "2026-07-11", "base_price": 10.0, "daily": [{"date": "2026-07-11"}],
        "last_close": 11.0, "chg_total": 10.0, "chg_today": 1.0,
        "held_days": 1, "remain_days": 29,
    })
    return p


def test_report_contains_sections():
    md = render_report(_pool_with_active(), "2026-07-11", new_codes={"600160"}, expired_codes=[])
    assert "# 中报预报跟踪 · 2026-07-11" in md
    assert "## 今日新增" in md
    assert "巨化股份" in md
    assert "## 活跃跟踪" in md
    assert "## 涨跌分布" in md


def test_report_distribution_counts():
    md = render_report(_pool_with_active(), "2026-07-11", new_codes=set(), expired_codes=[])
    assert "为正 1" in md  # chg_total=10>0 → 1 只正
```

- [ ] **Step 2: 跑确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_reporter.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 reporter.py**

```python
"""markdown 报告生成(纯格式化,无网络/无 IO)。"""


def _f(v, suffix="%"):
    """数字格式化,None→N/A。"""
    if v is None:
        return "N/A"
    return f"{v:+.2f}{suffix}" if suffix else f"{v:.2f}"


def _row_active(s: dict) -> str:
    return ("| {code} | {name} | {yl} | {nd} | {bp} | {lc} | {ct} | {cd} | {hd} | {rd} |").format(
        code=s.get("code"), name=s.get("name"),
        yl=_f(s.get("yoy_lower"), ""), nd=s.get("notice_date", ""),
        bp=_f(s.get("base_price"), ""), lc=_f(s.get("last_close"), ""),
        ct=_f(s.get("chg_total")), cd=_f(s.get("chg_today")),
        hd=s.get("held_days", 0), rd=s.get("remain_days", 0),
    )


def render_report(pool: dict, today_str: str, new_codes: set, expired_codes: list) -> str:
    """生成每日 markdown 报告。

    new_codes: 今日入池的 code 集合;expired_codes: 今日迁出的 code 列表。
    """
    active = sorted(pool.get("active", []),
                    key=lambda s: (s.get("chg_total") if s.get("chg_total") is not None else -1e9),
                    reverse=True)
    new = [s for s in pool.get("active", []) + pool.get("expired", [])
           if s.get("code") in new_codes]
    expired = [s for s in pool.get("expired", []) if s.get("code") in set(expired_codes)]

    chg = [s.get("chg_total") for s in active if s.get("chg_total") is not None]
    pos = sum(1 for c in chg if c > 0)
    neg = sum(1 for c in chg if c < 0)
    avg = (sum(chg) / len(chg)) if chg else 0.0

    lines = [f"# 中报预报跟踪 · {today_str}", ""]
    th = pool.get("threshold", {})
    lines += [
        "## 概览",
        f"- 报告期:{pool.get('report_period','')}（预告对应 {pool.get('report_date','')}）",
        f"- 阈值:{th.get('predict_type','预增')} 且同比下限≥{th.get('yoy_lower_min',50)}%｜"
        f"跟踪{th.get('hold_days',30)}交易日｜基准={th.get('base','次日开盘')}｜口径=前复权累计涨跌",
        f"- 跟踪池:活跃 {len(active)} 只 / 已到期 {len(pool.get('expired',[]))} 只 / "
        f"待重试 {len(pool.get('skipped',[]))} 只",
        f"- 今日新增:{len(new)} 只 ｜ 今日到期:{len(expired)} 只",
        "",
    ]

    lines += ["## 今日新增（{} 只）".format(len(new)),
              "| 代码 | 名称 | 预增下限 | 预增上限 | 公告日 | 基准日 | 基准价 |",
              "|---|---|---|---|---|---|---|"]
    for s in new:
        lines.append("| {code} | {name} | {yl} | {yu} | {nd} | {bd} | {bp} |".format(
            code=s.get("code"), name=s.get("name"),
            yl=_f(s.get("yoy_lower"), ""), yu=_f(s.get("yoy_upper"), ""),
            nd=s.get("notice_date", ""), bd=s.get("base_date", ""),
            bp=_f(s.get("base_price"), "")))
    lines.append("")

    lines += ["## 活跃跟踪（按累计涨跌降序）",
              "| 代码 | 名称 | 预增下限 | 公告日 | 基准价 | 今收 | 累计涨跌% | 当日涨跌% | 持有天数 | 剩余天数 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for s in active:
        lines.append(_row_active(s))
    lines.append("")

    lines += ["## 今日到期（移出活跃）",
              "| 代码 | 名称 | 基准价 | 期末收 | 累计涨跌% | 持有天数 |",
              "|---|---|---|---|---|---|"]
    for s in expired:
        lines.append("| {c} | {n} | {bp} | {lc} | {ct} | {hd} |".format(
            c=s.get("code"), n=s.get("name"), bp=_f(s.get("base_price"), ""),
            lc=_f(s.get("last_close"), ""), ct=_f(s.get("chg_total")), hd=s.get("held_days", 0)))
    lines.append("")

    lines += ["## 涨跌分布（活跃股）",
              f"- 累计为正 {pos} 只 / 为负 {neg} 只 / 平均累计涨跌 {avg:+.2f}%",
              ""]
    return "\n".join(lines)
```

- [ ] **Step 4: 跑确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_reporter.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add screener/reporter.py tests/test_reporter.py
git commit -m "feat(zhongbaoyubao): reporter markdown 报告生成"
```

---

## Task 11: main — 编排入口 run()

**Files:**
- Create: `.claude/skills/zhongbaoyubao/main.py`
- Test: `.claude/skills/zhongbaoyubao/tests/test_main.py`

> 设计为可注入 fetcher(测试用 fake),默认用 screener.fetcher。

- [ ] **Step 1: 写失败测试(注入 fake fetcher,端到端)**

`tests/test_main.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener import storage
from main import run


class FakeFetcher:
    def __init__(self):
        self.ann = [{
            "code": "600160", "name": "巨化股份", "industry": "化学制品",
            "notice_date": "2026-07-10", "predict_type": "预增",
            "yoy_lower": 80.0, "yoy_upper": 120.0,
        }]
        self.kline = {
            "600160": [
                {"date": "2026-07-11", "open": 10.0, "close": 10.0},
                {"date": "2026-07-14", "open": 10.1, "close": 11.0},
            ]
        }

    def get_announcements(self, **kw):
        return self.ann

    def get_kline_since(self, code, since_date):
        return self.kline.get(code, [])


def test_run_end_to_end(tmp_path):
    wl = str(tmp_path / "watchlist.json")
    out = str(tmp_path / "output")
    ok = run(today_str="2026-07-14", watchlist_path=wl, output_dir=out, fetcher=FakeFetcher())
    assert ok is True
    pool = storage.load_watchlist(wl)
    assert len(pool["active"]) == 1
    a = pool["active"][0]
    assert a["code"] == "600160"
    assert a["base_price"] == 10.0          # 次日开盘
    assert a["held_days"] == 1
    assert a["chg_total"] == 10.0           # (11-10)/10
    assert os.path.exists(os.path.join(out, "2026-07-14.md"))


def test_run_dedups_existing(tmp_path):
    wl = str(tmp_path / "watchlist.json")
    # 预置已入池
    p = storage.empty_pool()
    storage.add_active(p, {"code": "600160", "name": "巨化股份", "notice_date": "2026-07-10"})
    storage.save_watchlist(p, wl)
    run(today_str="2026-07-14", watchlist_path=wl,
        output_dir=str(tmp_path / "o"), fetcher=FakeFetcher())
    pool = storage.load_watchlist(wl)
    assert len(pool["active"]) == 1  # 不重复入池
```

- [ ] **Step 2: 跑确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_main.py -v
```
Expected: FAIL (ImportError: main)

- [ ] **Step 3: 实现 main.py**

```python
"""中报预报跟踪器 — 编排入口。

流程:CHECKPOINT → 加载 watchlist → 扫描新股入池 → 并发刷新 active 前复权日K + 算涨跌
     → 到期迁移 → 生成报告 → 写回 watchlist。

可注入 fetcher(测试用);默认用 screener.fetcher。
"""
import datetime
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

from screener import fetcher as _default_fetcher
from screener import storage
from screener.analyzer import (
    filter_announcements, build_daily, held_days, should_expire, HOLD_DAYS,
)
from screener.reporter import render_report


def _refresh_one(code: str, notice_date: str, fetcher) -> tuple[str, dict | None]:
    """拉一只 active 股的前复权日K,算出 daily 与汇总字段。失败返回 (code, None)。"""
    kline = fetcher.get_kline_since(code, notice_date)
    if not kline:
        return code, None
    base_price = kline[0]["open"]
    base_date = kline[0]["date"]
    daily = build_daily(kline, base_price)
    last = daily[-1] if daily else {}
    hd = held_days(daily)
    return code, {
        "base_date": base_date, "base_price": base_price, "daily": daily,
        "last_close": last.get("close"), "chg_total": last.get("chg_total"),
        "chg_today": last.get("chg_today"), "held_days": hd,
        "remain_days": max(0, HOLD_DAYS - hd),
    }


def run(today_str: str | None = None, watchlist_path: str | None = None,
        output_dir: str | None = None, fetcher=None) -> bool:
    today_str = today_str or datetime.date.today().strftime("%Y-%m-%d")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    watchlist_path = watchlist_path or os.path.join(base_dir, "data", "watchlist.json")
    output_dir = output_dir or os.path.join(base_dir, "output")
    fetcher = fetcher or _default_fetcher

    start = time.time()
    report_path = os.path.join(output_dir, f"{today_str}.md")

    # 1. CHECKPOINT:今日报告已存在→提示覆盖(交互场景由调用方处理;此处已存在不阻断,仅提示)
    if os.path.exists(report_path):
        print(f"⚠️ 今日报告已存在:{report_path},将覆盖。", flush=True)

    # 2. 加载 watchlist
    pool = storage.load_watchlist(watchlist_path)
    print(f"[{today_str}] 跟踪池:活跃 {len(pool['active'])} / 到期 {len(pool['expired'])} "
          f"/ 待重试 {len(pool['skipped'])}", flush=True)

    # 3. 扫描新股
    existed = storage.existing_codes(pool)
    anns = fetcher.get_announcements()
    targets = filter_announcements(anns)
    new_items = [a for a in targets if a["code"] not in existed]
    for a in new_items:
        storage.add_active(pool, a)
    # skipped 中的也重新尝试(并入 active 待刷新,成功则移除 skipped)
    retry_codes = set(s["code"] for s in pool["skipped"])
    print(f"扫描预告 {len(anns)} 条,达标 {len(targets)},新增入池 {len(new_items)},"
          f"重试 skipped {len(retry_codes)}", flush=True)

    # 4. 并发刷新 active 日K + 算涨跌
    to_refresh = [(s["code"], s.get("notice_date") or "") for s in pool["active"]
                  if not s.get("daily") or s["code"] in retry_codes or s["code"] in {a["code"] for a in new_items}]
    # 简化:对所有 active 全量刷新(前复权覆盖式,保证口径一致)
    to_refresh = [(s["code"], s.get("notice_date") or "") for s in pool["active"]]

    new_codes = {a["code"] for a in new_items}
    failed_codes = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(_refresh_one, c, nd, fetcher): c for c, nd in to_refresh}
        for fut in as_completed(futs):
            code, fields = fut.result()
            if fields is None:
                failed_codes.append(code)
                continue
            try:
                storage.refresh_active(pool, code, fields)
                if code in retry_codes:
                    storage.remove_skipped(pool, code)
            except KeyError:
                pass  # 索引不一致,跳过

    # 5. 刷新失败的 active(daily 仍空)→ 降级 skipped 待下次重试,并清出 active
    #    (上次已成功、本次刷新失败的会保留旧 daily,不会被降级,下次自动重试覆盖)
    still_empty = [s for s in pool["active"] if not s.get("daily")]
    for s in still_empty:
        storage.add_skipped(pool, s["code"], s.get("name", ""),
                            s.get("notice_date", ""), "K线拉取失败")
    pool["active"] = [s for s in pool["active"] if s.get("daily")]

    # 6. 到期迁移
    expired_now = storage.migrate_expired(pool, HOLD_DAYS)

    # 6. 报告
    os.makedirs(output_dir, exist_ok=True)
    md = render_report(pool, today_str, new_codes, expired_now)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)

    # 7. 写回 watchlist
    storage.save_watchlist(pool, watchlist_path)

    print(f"完成:活跃 {len(pool['active'])} / 到期 {len(pool['expired'])} / "
          f"待重试 {len(pool['skipped'])},本次到期 {len(expired_now)},"
          f"刷新失败 {len(failed_codes)},耗时 {time.time()-start:.1f}s", flush=True)
    print(f"报告:{report_path}", flush=True)
    return True


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: 跑确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_main.py -v
```
Expected: 2 passed。再跑全量:
```bash
PYTHONUTF8=1 python -m pytest -v
```
Expected: 全部 passed(analyzer/storage/fetcher/reporter/main)

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat(zhongbaoyubao): main 编排入口(CHECKPOINT/扫描/并发刷新/报告)"
```

---

## Task 12: SKILL.md

**Files:**
- Create: `.claude/skills/zhongbaoyubao/SKILL.md`

- [ ] **Step 1: 写 SKILL.md**

```markdown
---
name: zhongbaoyubao
description: 中报预报跟踪器 — 扫描A股中报业绩预告(预增且同比下限≥50%),以公告次日开盘为基准,跟踪30交易日累计涨跌,每日生成markdown报告。当用户说"中报预报"、"中报预增"、"业绩预告大增"、"预报跟踪"、"预告大涨跟踪"时触发。
---

# 中报预报跟踪器

跟踪中报预告"大幅预增"公司的**披露后股价反应**(事件跟踪,非买卖建议)。

## 使用方式

输入 `/zhongbaoyubao` 触发。每日执行:扫描新预增预告入池 → 刷新跟踪池累计涨跌 → 生成报告。

## 执行步骤

1. 🔴 CHECKPOINT(运行前检查今日报告是否已存在):
   ```bash
   ls .claude/skills/zhongbaoyubao/output/$(date +%Y-%m-%d).md 2>/dev/null
   ```
   - 已存在 → 🛑 STOP,提示"今日报告已生成,重跑会重新刷新行情并覆盖",询问确认。
   - 不存在 → 继续。

2. 确认依赖:
   ```bash
   cd .claude/skills/zhongbaoyubao && pip install -r requirements.txt
   ```

3. 运行:
   ```bash
   cd .claude/skills/zhongbaoyubao && python main.py
   ```

4. 脚本会:扫描全A中报业绩预告(预增,同比下限≥50%)→ 新股入池(取公告次日开盘为基准)→ 并发刷新池内活跃股前复权日K → 算累计/当日涨跌 → 满30交易日迁出 → 生成 `output/<date>.md` → 写回 `data/watchlist.json`。

5. 读取 `output/<date>.md` 向用户展示:今日新增、活跃跟踪(按累计涨跌排序)、今日到期、涨跌分布。

## 实测字段(经 probe_yjyg.py 确认)

> 首次实现/接口变动时运行 `python probe_yjyg.py` 重新核对,改 `screener/fetcher.py` 顶部常量。

- reportName = `RPT_LICO_FN_CPD_GD`
- 公告日 = `NOTICE_DATE`、报告期 = `REPORTDATE`
- 预告类型 = `PREDICT_TYPE`(值含"预增")
- 同比下限/上限 = `CHANGE_RATE_LOWER` / `CHANGE_RATE_UPPER`

## 关键参数

| 项 | 值 | 改动位置 |
|---|---|---|
| 预告类型 | 预增 | analyzer.PREDICT_TYPE |
| 同比下限阈值 | 50% | analyzer.YOY_LOWER_MIN |
| 跟踪交易日 | 30 | analyzer.HOLD_DAYS |
| 基准价 | 公告次日开盘(前复权) | fetcher.get_kline_since |
| 报告期 | 2026-06-30(中报) | storage.REPORT_DATE |

## 边界条件

| 触发 | 处理 |
|---|---|
| 非交易日执行 | 仍扫预告;当前价=最近交易日收盘,报告标注 |
| 公告次日停牌 | 基准日顺延到复牌后首个交易日 |
| K线拉取失败 | 入 skipped,下次执行重试 |
| 业绩预告接口异常 | 本次不新增,提示稍后重试 |
| watchlist 损坏 | 备份 *.bad 后重建空池 |
| 跨报告期 | report_date 写死 2026-06-30,只扫中报 |

## ❌ 不要做

- 不要把"预增"当买卖建议(预告≠兑现,利好出尽或下跌)
- 不要用入池 1 天的单点涨跌下结论(噪声大,看 held_days≥5)
- 不要用不复权价配前复权基准价(除权失真;基准与当前同取一条前复权序列)
- 不要逐个串行刷新全池(用 20 线程并发)
- 不要忽略 CHECKPOINT 直接覆盖今日报告

## 局限

- 预告是公司指引,非实际数;正式中报(8月底前)可能修订
- 绝对涨跌,未剔除大盘/行业 beta
- 仅归母口径,预增可能含一次性损益
```

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "docs(zhongbaoyubao): SKILL.md"
```

---

## Task 13: 手动联调验证

> 全部单测通过后,做一次真实接口联调(非交易日则验证降级路径)。

- [ ] **Step 1: 确认接口字段(Task 1 已做则跳过)**

```bash
cd .claude/skills/zhongbaoyubao && PYTHONUTF8=1 python probe_yjyg.py
```
若有字段与 fetcher 常量不符,改 `screener/fetcher.py` 顶部 `FLD_*` 常量。

- [ ] **Step 2: 真实跑一轮**

```bash
cd .claude/skills/zhongbaoyubao && PYTHONUTF8=1 python main.py
```
Expected: 打印扫描/刷新进度与完成统计,生成 `output/<today>.md`,写出 `data/watchlist.json`。

- [ ] **Step 3: 人工核对报告**

读 `output/<today>.md`:
- 今日新增的预增股是否合理(同比下限≥50%)
- 基准价=公告次日开盘、累计涨跌口径正确
- 涨跌分布正负家数合理

- [ ] **Step 4: 再跑一次验证幂等(去重)**

```bash
PYTHONUTF8=1 python main.py
```
Expected: "新增入池 0"(已入池的不重复),活跃股 daily 被覆盖刷新。

- [ ] **Step 5: Commit(若有字段常量修正)**

```bash
git add screener/fetcher.py
git commit -m "fix(zhongbaoyubao): 业绩预告字段名实测修正"
```

---

## Self-Review(已自查)

- **Spec 覆盖**:筛选(Task 2)、涨跌口径(Task 3)、到期(Task 4)、持久化三区(Task 5-7)、前复权日K(Task 8)、预告扫描(Task 9)、报告(Task 10)、编排+CHECKPOINT(Task 11)、SKILL.md(Task 12)、联调(Task 13)——spec 各节均有任务承接。
- **占位符**:无 TBD/TODO;Task 1 的字段探测是真实必要的接口核对步骤,非占位(探测后填入 fetcher 单点常量)。
- **类型一致**:`filter_announcements`/`build_daily`/`held_days`/`should_expire`/`refresh_active`/`migrate_expired` 等签名跨任务统一;watchlist 字段(active 的 base_price/daily/last_close/chg_total/chg_today/held_days/remain_days)在 storage/reporter/main 三处一致。
- **已知简化**:main 对全 active 覆盖式刷新(而非仅新股),保证前复权口径一致;非交易日降级依赖接口返回最近交易日。
