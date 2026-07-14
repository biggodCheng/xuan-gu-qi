# 人气榜（renqibang）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个抓取东方财富股吧个股人气榜 Top100 的 skill，每只股票保存人气排名、代码、名称、热度、排名变动、所属行业、题材（作为"上榜原因"），结果存为本地 JSON 并终端打印摘要。

**Architecture:** 混合抓取——榜单本体用 Playwright 渲染页面读解密后 DOM（接口 AES 加密、纯 Python 解密不可行）；行业 + 题材用 push2 明文接口并发补全（`f127`/`f129`）。`main.py` 编排：CHECKPOINT 防覆盖 → 渲染榜单取 Top100 → 并发补行业/题材 → 存 `data/popularity_<date>.json` → 打印 markdown 摘要。

**Tech Stack:** Python 3.10+、requests（直连禁代理）、playwright（新增，渲染绕加密）、concurrent.futures、pytest。

**Spec:** `docs/superpowers/specs/2026-07-14-renqibang-design.md`

---

## File Structure（接口契约，后续任务严格遵循）

| 文件 | 职责 | 关键函数签名 |
|---|---|---|
| `screener/__init__.py` | 包标识 | 空 |
| `screener/storage.py` | popularity_<date>.json 读写 | 见下 |
| `screener/fetcher.py` | push2 明文接口：行业 + 题材 | 见下 |
| `screener/browser.py` | Playwright 渲染榜单 + DOM 解析纯函数 | 见下 |
| `main.py` | 编排入口 + CHECKPOINT + 摘要 | `run(today_str=None, output_dir=None, browser=None, fetcher=None) -> bool` |
| `tests/test_storage.py` `tests/test_fetcher.py` `tests/test_browser.py` `tests/test_main.py` | 单测 | pytest |
| `probe_rank.py` | 🔴 榜单 DOM 结构探测脚本（实现期用，保留作排障） | — |
| `SKILL.md` | skill 说明 + 实测 selector 记录 | — |
| `requirements.txt` `.gitignore` `data/.gitkeep` | 工程文件 | — |

**storage.py 契约:**
```python
def save_results(date_str: str, sort: str, stocks: list[dict], output_dir: str) -> str: ...
#   写 data/popularity_<date_str>.json，返回路径；stocks 每条见下 JSON 结构
def load_results(date_str: str, output_dir: str) -> dict | None: ...
#   不存在→None；存在→dict
```

**fetcher.py 契约:**
```python
def build_secid(code: str) -> str: ...                    # 6 开头→"1.600000"，其余→"0.000001"
def fetch_industry_concepts(code: str) -> dict: ...       # {"industry": str, "concepts": list[str]}，失败字段为空
def fetch_industry_for_stocks(stocks: list[dict], max_workers: int = 10) -> None: ...
#   就地为 stocks 每条补 industry / concepts / reason（线程池并发）
```

**browser.py 契约（顶部 selector 常量，经 probe_rank.py 实测后填入）:**
```python
RANK_URL = "https://guba.eastmoney.com/rank/"
RANK_ROW_SELECTOR = "<探测填>"   # 榜单每一行
RANK_CELL_SELECTOR = "<探测填>"  # 行内单元格（td）
NEXT_PAGE_SELECTOR = "<探测填>"  # "下一页"按钮
HOT_TAB_SELECTOR = "<探测填>"    # "热度榜"tab（若页面非默认热度榜）

def parse_one(cells: list[str], base_rank: int) -> dict | None: ...
#   单元格文本列表 → {rank, code, name, popularity, rank_change}；无法解析→None
def fetch_top100(sort: str = "热度榜", headless: bool = True) -> list[dict]: ...
#   Playwright 渲染翻页取 Top100，返回 list[{rank,code,name,popularity,rank_change}]
```

**popularity_<date>.json 结构（全流程统一）:**
```json
{"date":"2026-07-14","fetched_at":"2026-07-14T15:02:30",
 "source":"东方财富股吧个股人气榜","sort":"热度榜","count":100,
 "stocks":[{"rank":1,"code":"600000","name":"浦发银行","popularity":426283,
            "rank_change":"+5","industry":"银行",
            "concepts":["沪股通","融资融券"],"reason":"沪股通,融资融券"}]}
```

---

## Task 0: 脚手架 + 依赖

**Files:**
- Create: `.claude/skills/renqibang/screener/__init__.py`（空）
- Create: `.claude/skills/renqibang/tests/__init__.py`（空）
- Create: `.claude/skills/renqibang/requirements.txt`
- Create: `.claude/skills/renqibang/.gitignore`
- Create: `.claude/skills/renqibang/data/.gitkeep`

- [ ] **Step 1: 建目录与空文件**

```bash
mkdir -p .claude/skills/renqibang/screener .claude/skills/renqibang/tests .claude/skills/renqibang/data
```

`screener/__init__.py` 与 `tests/__init__.py` 内容为空字符串。

- [ ] **Step 2: 写 requirements.txt**

```
requests>=2.28.0
playwright>=1.40.0
```

- [ ] **Step 3: 写 .gitignore**

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
data/*.json
```

- [ ] **Step 4: 建 data/.gitkeep 占位**

`data/.gitkeep` 内容为空字符串（保证空目录入库）。

- [ ] **Step 5: 安装依赖（含 chromium，首次较慢）**

```bash
cd .claude/skills/renqibang && pip install -r requirements.txt && python -m playwright install chromium
```

Expected: `requests`、`playwright` 安装成功；chromium 下载完成（约 150MB，1-3 分钟）。

- [ ] **Step 6: Commit**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/
git commit -m "feat(renqibang): 脚手架(目录/依赖/gitignore)"
```

---

## Task 1: storage — 读写

**Files:**
- Create: `.claude/skills/renqibang/screener/storage.py`
- Test: `.claude/skills/renqibang/tests/test_storage.py`

- [ ] **Step 1: 写失败测试**

`tests/test_storage.py`:
```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.storage import save_results, load_results


def test_save_then_load_roundtrip(tmp_path):
    out = str(tmp_path)
    stocks = [{"rank": 1, "code": "600000", "name": "浦发银行",
               "popularity": 426283, "rank_change": "+5",
               "industry": "银行", "concepts": ["沪股通"], "reason": "沪股通"}]
    path = save_results("2026-07-14", "热度榜", stocks, out)
    assert path.endswith("popularity_2026-07-14.json")
    loaded = load_results("2026-07-14", out)
    assert loaded["date"] == "2026-07-14"
    assert loaded["sort"] == "热度榜"
    assert loaded["count"] == 1
    assert loaded["stocks"][0]["code"] == "600000"
    assert loaded["stocks"][0]["concepts"] == ["沪股通"]


def test_load_missing_returns_none(tmp_path):
    assert load_results("2099-01-01", str(tmp_path)) is None


def test_save_overwrites_same_date(tmp_path):
    out = str(tmp_path)
    save_results("2026-07-14", "热度榜", [], out)
    save_results("2026-07-14", "热度榜", [{"rank": 1, "code": "000001"}], out)
    loaded = load_results("2026-07-14", out)
    assert loaded["count"] == 1  # 覆盖而非追加
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd .claude/skills/renqibang && PYTHONUTF8=1 python -m pytest tests/test_storage.py -v
```
Expected: FAIL (`ModuleNotFoundError: screener.storage`)

- [ ] **Step 3: 实现 storage.py**

```python
"""popularity_<date>.json 读写。

文件名 popularity_<date>.json，结构与 spec 第 8 节一致。
save 覆盖写（同 date 重跑直接替换，防覆盖由 main 的 CHECKPOINT 交互处理）。
"""
import datetime
import json
import os


def _now_iso() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def save_results(date_str: str, sort: str, stocks: list, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    result = {
        "date": date_str,
        "fetched_at": _now_iso(),
        "source": "东方财富股吧个股人气榜",
        "sort": sort,
        "count": len(stocks),
        "stocks": stocks,
    }
    path = os.path.join(output_dir, f"popularity_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def load_results(date_str: str, output_dir: str):
    path = os.path.join(output_dir, f"popularity_{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_storage.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/screener/storage.py .claude/skills/renqibang/tests/test_storage.py
git commit -m "feat(renqibang): storage 读写(popularity_<date>.json)"
```

---

## Task 2: fetcher — push2 行业 + 题材

**Files:**
- Create: `.claude/skills/renqibang/screener/fetcher.py`
- Test: `.claude/skills/renqibang/tests/test_fetcher.py`

- [ ] **Step 1: 写失败测试（mock 网络）**

`tests/test_fetcher.py`:
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener import fetcher


def test_build_secid_sh():
    assert fetcher.build_secid("600000") == "1.600000"


def test_build_secid_sz():
    assert fetcher.build_secid("000001") == "0.000001"


def test_build_secid_cy():
    assert fetcher.build_secid("300750") == "0.300750"


def test_build_secid_bj():
    assert fetcher.build_secid("920001") == "0.920001"


def test_fetch_industry_concepts_parses(monkeypatch):
    payload = {"data": {"f57": "600000", "f58": "浦发银行",
                        "f127": "银行", "f129": "沪股通,融资融券,标准券"}}
    monkeypatch.setattr(fetcher, "_request_push2", lambda secid: payload)
    r = fetcher.fetch_industry_concepts("600000")
    assert r["industry"] == "银行"
    assert r["concepts"] == ["沪股通", "融资融券", "标准券"]


def test_fetch_industry_concepts_empty_fields(monkeypatch):
    payload = {"data": {"f127": "", "f129": ""}}
    monkeypatch.setattr(fetcher, "_request_push2", lambda secid: payload)
    r = fetcher.fetch_industry_concepts("600000")
    assert r["industry"] == ""
    assert r["concepts"] == []


def test_fetch_industry_concepts_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(fetcher, "_request_push2", lambda secid: {})
    r = fetcher.fetch_industry_concepts("600000")
    assert r == {"industry": "", "concepts": []}


def test_fetch_industry_for_stocks_fills_inplace(monkeypatch):
    monkeypatch.setattr(fetcher, "_request_push2",
                        lambda secid: {"data": {"f127": "电子", "f129": "AI算力,芯片"}})
    stocks = [{"code": "600000"}, {"code": "000001"}]
    fetcher.fetch_industry_for_stocks(stocks, max_workers=2)
    assert stocks[0]["industry"] == "电子"
    assert stocks[0]["concepts"] == ["AI算力", "芯片"]
    assert stocks[0]["reason"] == "AI算力,芯片"
    assert stocks[1]["industry"] == "电子"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_fetcher.py -v
```
Expected: FAIL (`ModuleNotFoundError: screener.fetcher`)

- [ ] **Step 3: 实现 fetcher.py**

```python
"""数据获取层 — push2 明文接口补行业(f127) + 题材/概念(f129)。

榜单本体(加密)由 browser.py 用 Playwright 渲染;本模块只负责明文字段补全。
禁用本地代理(与 chuangxingao/zhongbaoyubao 一致)。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
})

PUSH2_URL = "https://push2.eastmoney.com/api/qt/stock/get"
FIELDS = "f57,f58,f127,f129"   # 代码 / 名称 / 行业 / 概念


def build_secid(code: str) -> str:
    """东方财富 secid:6 开头(沪)→'1'，其余(深/创业板/北交所)→'0'。"""
    prefix = "1" if code.startswith("6") else "0"
    return f"{prefix}.{code}"


def _request_push2(secid: str) -> dict:
    """请求 push2 stock/get，返回 json(失败返回 {})。可被测试 mock。"""
    params = {"secid": secid, "fields": FIELDS, "fltt": "2"}
    try:
        r = _session.get(PUSH2_URL, params=params, timeout=10)
        return r.json() or {}
    except Exception as e:
        print(f"push2 请求失败({secid}): {e}", flush=True)
        return {}


def fetch_industry_concepts(code: str) -> dict:
    """取一只股票的行业 + 概念。失败/缺字段返回空(不抛)。"""
    data = (_request_push2(build_secid(code)) or {}).get("data") or {}
    industry = (data.get("f127") or "").strip()
    raw = (data.get("f129") or "").strip()
    concepts = [c.strip() for c in raw.split(",") if c.strip()]
    return {"industry": industry, "concepts": concepts}


def fetch_industry_for_stocks(stocks: list, max_workers: int = 10) -> None:
    """并发为 stocks 每条就地补 industry / concepts / reason。"""
    codes = [s.get("code") for s in stocks if s.get("code")]
    result = {}

    def _one(code):
        return code, fetch_industry_concepts(code)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_one, c) for c in codes]
        for fut in as_completed(futs):
            try:
                code, info = fut.result()
                result[code] = info
            except Exception:
                continue

    for s in stocks:
        info = result.get(s.get("code"), {"industry": "", "concepts": []})
        s["industry"] = info["industry"]
        s["concepts"] = info["concepts"]
        s["rank_change"] = s.get("rank_change", "")
        s["reason"] = ",".join(info["concepts"])
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_fetcher.py -v
```
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/screener/fetcher.py .claude/skills/renqibang/tests/test_fetcher.py
git commit -m "feat(renqibang): fetcher push2 行业+题材(f127/f129)"
```

---

## Task 3: 🔴 榜单 DOM 结构探测（关键 CHECKPOINT）

> spec 第 6.2 节:榜单页渲染后的 DOM 结构需实测。本任务产出"确认后的 selector"与"一行样本文本"，写入 browser.py 常量与 test fixture，后续任务严格使用。**不可跳过**——纯 Python 解密不可行，必须靠渲染后 DOM，selector 错则全盘错。

**Files:**
- Create: `.claude/skills/renqibang/probe_rank.py`
- Create: `.claude/skills/renqibang/tests/fixtures/rank_row_sample.txt`（探测产出）

- [ ] **Step 1: 写探测脚本**

`probe_rank.py`:
```python
"""探测东方财富股吧人气榜渲染后 DOM 结构。

运行: python probe_rank.py
打印: 页面默认 tab、榜单每行单元格文本、分页按钮、tab 切换 selector。
把确认结果填入 screener/browser.py 顶部常量,并把第一行单元格文本
存为 tests/fixtures/rank_row_sample.txt 供 test_browser 使用。
"""
from playwright.sync_api import sync_playwright

URL = "https://guba.eastmoney.com/rank/"


def probe():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)  # 等 JS 解密 + 渲染

        print("=== 页面标题 ===")
        print(page.title())

        print("\n=== 可见表格行数(尝试常见 selector)===")
        for sel in ["table tbody tr", ".rank_list li", ".list_item",
                    "[class*='rank'] tr", "tr[class*='stock']"]:
            try:
                n = page.locator(sel).count()
                print(f"  {sel}: {n} 行")
            except Exception as e:
                print(f"  {sel}: 异常 {e}")

        print("\n=== 取第一条数据行的外层 HTML(找最像数据的 selector)===")
        # 按行数最多的 selector 取首行
        best = None
        for sel in ["table tbody tr", ".rank_list li", ".list_item"]:
            try:
                if page.locator(sel).count() > 5:
                    best = sel
                    break
            except Exception:
                continue
        if best:
            html = page.locator(best).first.inner_html()
            print(f"selector={best}")
            print(html[:1200])
            print("\n=== 首行单元格纯文本 ===")
            texts = page.locator(best).first.inner_text().split()
            print(texts)

        print("\n=== 分页/tab 元素(含'下一页''热度''人气'文本的元素)===")
        for kw in ["下一页", "热度", "人气", "飙升"]:
            loc = page.get_by_text(kw, exact=False)
            try:
                cnt = loc.count()
                print(f"  '{kw}': {cnt} 个")
                if cnt:
                    print("    tag:", loc.first.evaluate("e => e.tagName + '|' + e.className"))
            except Exception:
                pass

        browser.close()


if __name__ == "__main__":
    probe()
```

- [ ] **Step 2: 运行探测，记录结构**

```bash
cd .claude/skills/renqibang && PYTHONUTF8=1 python probe_rank.py
```

Expected: 打印行数统计、首行 HTML、首行单元格文本、分页/tab 元素。

人工对照输出，确认并记录（填入 Task 4 browser.py 常量）：
- `RANK_ROW_SELECTOR`：行数最多、含数据的那个 selector
- `RANK_CELL_SELECTOR`：行内单元格 selector（如 `td` 或具体 class）
- `NEXT_PAGE_SELECTOR`：含"下一页"文本的可点击元素 selector
- `HOT_TAB_SELECTOR`：若页面默认非"热度榜"，记录切到热度榜的 selector；若默认就是热度榜，常量留空字符串
- 单元格列顺序：rank / code / name / popularity / rank_change 在 cells 中的索引（用于 `parse_one`）

- [ ] **Step 3: 存一行样本文本到 fixture**

把探测打印的"首行单元格文本"（list 形式，如 `['1', '600000', '浦发银行', '426283', '+5']`）原样写入：

`tests/fixtures/rank_row_sample.txt`（内容为探测输出的真实文本，逗号分隔一行，例如）：
```
1,600000,浦发银行,426283,+5
```

> 若实际单元格更多/顺序不同，按真实顺序写；Task 4 的 `parse_one` 与 `test_browser` 据此对齐。

- [ ] **Step 4: Commit**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/probe_rank.py .claude/skills/renqibang/tests/fixtures/rank_row_sample.txt
git commit -m "chore(renqibang): 榜单 DOM 探测脚本+样本 fixture"
```

---

## Task 4: browser — DOM 解析纯函数 parse_one

> 依赖 Task 3 探测确认的单元格列顺序。下方 `parse_one` 假设列顺序为 [rank, code, name, popularity, rank_change]；若探测结果不同，调整索引常量（单点修改）。

**Files:**
- Create: `.claude/skills/renqibang/screener/browser.py`（先写常量 + parse_one，fetch_top100 在 Task 5 追加）
- Test: `.claude/skills/renqibang/tests/test_browser.py`

- [ ] **Step 1: 写失败测试**

`tests/test_browser.py`:
```python
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.browser import parse_one


def test_parse_one_basic():
    cells = ["1", "600000", "浦发银行", "426283", "+5"]
    r = parse_one(cells, base_rank=1)
    assert r["rank"] == 1
    assert r["code"] == "600000"
    assert r["name"] == "浦发银行"
    assert r["popularity"] == 426283
    assert r["rank_change"] == "+5"


def test_parse_one_uses_base_rank_when_rank_cell_missing():
    # 某些榜单行首无排名单元格,用累计序号兜底
    cells = ["", "600000", "浦发银行", "426283", "+5"]
    r = parse_one(cells, base_rank=7)
    assert r["rank"] == 7


def test_parse_one_extracts_code_from_mixed_text():
    # 单元格可能含市场前缀如"SH600000"或括号
    cells = ["1", "SH600000", "浦发银行", "426283", "+5"]
    r = parse_one(cells, base_rank=1)
    assert r["code"] == "600000"


def test_parse_one_invalid_code_returns_none():
    cells = ["1", "不是代码", "浦发银行", "426283", "+5"]
    assert parse_one(cells, base_rank=1) is None


def test_parse_one_popularity_non_numeric_to_zero():
    cells = ["1", "600000", "浦发银行", "-", "+5"]
    r = parse_one(cells, base_rank=1)
    assert r["popularity"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_browser.py -v
```
Expected: FAIL (`ModuleNotFoundError: screener.browser`)

- [ ] **Step 3: 实现 browser.py（常量 + parse_one）**

```python
"""榜单抓取层 — Playwright 渲染东方财富股吧人气榜 + DOM 解析。

榜单接口返回 AES 密文(window.d() 解密),纯 Python 逆向不可行(spec 6.2),
改由 Playwright 渲染页面让浏览器自动解密,直接读 DOM。

selector 常量经 probe_rank.py 实测填入;前端改版会导致 selector 失效,
属可接受维护点——失效时重跑 probe_rank.py 修正。
"""
import re

# === selector 常量(候选默认值;若 probe_rank.py 探测结果不同,改这里单点)===
RANK_URL = "https://guba.eastmoney.com/rank/"
RANK_ROW_SELECTOR = "table tbody tr"          # 榜单每一行
RANK_CELL_SELECTOR = "td"                      # 行内单元格
NEXT_PAGE_SELECTOR = "a:has-text('下一页')"    # 下一页按钮
HOT_TAB_SELECTOR = ""                          # 切到热度榜的 tab;默认即热度榜则留空

# === 单元格列顺序(经 Task3 探测确认;若不同仅改这里)===
# cells = [rank, code, name, popularity, rank_change]
IDX_RANK = 0
IDX_CODE = 1
IDX_NAME = 2
IDX_POP = 3
IDX_CHG = 4

_CODE_RE = re.compile(r"(\d{6})")


def _safe_int(s, default=0):
    try:
        return int(str(s).strip().replace(",", ""))
    except (TypeError, ValueError):
        return default


def parse_one(cells: list, base_rank: int):
    """一行单元格文本 → {rank, code, name, popularity, rank_change}。

    cells 顺序见顶部 IDX_* 常量。code 单元格允许含前缀(如 SH600000),取其中的 6 位数字。
    无法解析出 6 位代码 → 返回 None(跳过表头/广告行)。
    """
    if not cells or len(cells) <= max(IDX_CODE, IDX_NAME):
        return None
    code_cell = str(cells[IDX_CODE]) if len(cells) > IDX_CODE else ""
    m = _CODE_RE.search(code_cell)
    if not m:
        return None
    code = m.group(1)

    rank_cell = cells[IDX_RANK].strip() if len(cells) > IDX_RANK and cells[IDX_RANK] else ""
    rank = _safe_int(rank_cell) if rank_cell else base_rank
    name = str(cells[IDX_NAME]).strip() if len(cells) > IDX_NAME else ""
    popularity = _safe_int(cells[IDX_POP]) if len(cells) > IDX_POP else 0
    rank_change = str(cells[IDX_CHG]).strip() if len(cells) > IDX_CHG else ""

    return {
        "rank": rank,
        "code": code,
        "name": name,
        "popularity": popularity,
        "rank_change": rank_change,
    }
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_browser.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/screener/browser.py .claude/skills/renqibang/tests/test_browser.py
git commit -m "feat(renqibang): browser DOM 解析纯函数(parse_one)"
```

---

## Task 5: browser — Playwright 抓取 fetch_top100

> 用 Task 3 探测填入的 selector。本函数驱动真实浏览器，以联调验证为主（单测覆盖其依赖的 parse_one）。`base_rank` 用累计计数保证排名连续。

**Files:**
- Modify: `.claude/skills/renqibang/screener/browser.py`（追加 fetch_top100）

- [ ] **Step 1: 在 browser.py 末尾追加实现**

```python
def _row_cells(page, row_locator):
    """取一行的单元格文本列表。"""
    if RANK_CELL_SELECTOR:
        return [c.strip() for c in row_locator.locator(RANK_CELL_SELECTOR).all_text_contents()]
    # 无 cell selector 时退化为整行文本按空白切分
    txt = row_locator.inner_text()
    return [t for t in txt.split() if t]


def fetch_top100(sort: str = "热度榜", headless: bool = True, max_pages: int = 8) -> list:
    """Playwright 渲染人气榜，翻页取 Top100。

    返回 list[{rank, code, name, popularity, rank_change}]（不足 100 取实际条数）。
    sort 当前仅"热度榜"；若页面默认非热度榜且 HOT_TAB_SELECTOR 非空，先点 tab。
    """
    from playwright.sync_api import sync_playwright

    stocks = []
    seen = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(RANK_URL, wait_until="domcontentloaded", timeout=30000)

        # 切到热度榜(若需要)
        if HOT_TAB_SELECTOR:
            try:
                page.locator(HOT_TAB_SELECTOR).first.click()
                page.wait_for_timeout(1500)
            except Exception:
                pass

        page.wait_for_selector(RANK_ROW_SELECTOR, timeout=20000)

        for _ in range(max_pages):
            if len(stocks) >= 100:
                break
            rows = page.locator(RANK_ROW_SELECTOR).all()
            for row in rows:
                if len(stocks) >= 100:
                    break
                try:
                    cells = _row_cells(page, row)
                except Exception:
                    continue
                base_rank = len(stocks) + 1
                one = parse_one(cells, base_rank)
                if not one or one["code"] in seen:
                    continue
                seen.add(one["code"])
                one["rank"] = len(stocks) + 1   # 连续排名
                stocks.append(one)

            if len(stocks) >= 100:
                break
            # 翻下一页
            if not NEXT_PAGE_SELECTOR:
                break
            try:
                btn = page.locator(NEXT_PAGE_SELECTOR).first
                if btn.count() == 0:
                    break
                btn.click()
                page.wait_for_selector(RANK_ROW_SELECTOR, timeout=15000)
                page.wait_for_timeout(800)
            except Exception:
                break

        browser.close()
    return stocks[:100]
```

- [ ] **Step 2: 语法自检（不联调）**

```bash
cd .claude/skills/renqibang && PYTHONUTF8=1 python -c "from screener.browser import fetch_top100; print('import ok')"
```
Expected: `import ok`（确认无语法错误；真实抓取在 Task 8 联调）

- [ ] **Step 3: 回归 browser 单测仍通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_browser.py -v
```
Expected: 5 passed（parse_one 未受影响）

- [ ] **Step 4: Commit**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/screener/browser.py
git commit -m "feat(renqibang): browser Playwright 抓取(fetch_top100)"
```

---

## Task 6: main — 编排入口 run()

**Files:**
- Create: `.claude/skills/renqibang/main.py`
- Test: `.claude/skills/renqibang/tests/test_main.py`

> 设计为可注入 browser/fetcher（测试用 fake），默认用 screener.browser / screener.fetcher。

- [ ] **Step 1: 写失败测试（注入 fake browser + fake fetcher，端到端）**

`tests/test_main.py`:
```python
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener import storage
from main import run


class FakeBrowser:
    def fetch_top100(self, sort="热度榜", headless=True):
        return [
            {"rank": 1, "code": "600000", "name": "浦发银行", "popularity": 426283, "rank_change": "+5"},
            {"rank": 2, "code": "000001", "name": "平安银行", "popularity": 300000, "rank_change": "-2"},
        ]


class FakeFetcher:
    def fetch_industry_for_stocks(self, stocks, max_workers=10):
        m = {"600000": ("银行", ["沪股通", "融资融券"]),
             "000001": ("银行", ["沪深300"])}
        for s in stocks:
            ind, concepts = m.get(s["code"], ("", []))
            s["industry"] = ind
            s["concepts"] = concepts
            s["reason"] = ",".join(concepts)


def test_run_end_to_end(tmp_path):
    out = str(tmp_path)
    ok = run(today_str="2026-07-14", output_dir=out,
             browser=FakeBrowser(), fetcher=FakeFetcher())
    assert ok is True
    loaded = storage.load_results("2026-07-14", out)
    assert loaded["count"] == 2
    s0 = loaded["stocks"][0]
    assert s0["code"] == "600000"
    assert s0["industry"] == "银行"
    assert s0["concepts"] == ["沪股通", "融资融券"]
    assert s0["reason"] == "沪股通,融资融券"


def test_run_overwrites_same_date(tmp_path):
    out = str(tmp_path)
    run(today_str="2026-07-14", output_dir=out, browser=FakeBrowser(), fetcher=FakeFetcher())
    run(today_str="2026-07-14", output_dir=out, browser=FakeBrowser(), fetcher=FakeFetcher())
    loaded = storage.load_results("2026-07-14", out)
    assert loaded["count"] == 2  # 覆盖不追加


def test_run_empty_list_still_saves(tmp_path):
    out = str(tmp_path)

    class EmptyBrowser:
        def fetch_top100(self, sort="热度榜", headless=True):
            return []

    ok = run(today_str="2026-07-14", output_dir=out,
             browser=EmptyBrowser(), fetcher=FakeFetcher())
    assert ok is True
    loaded = storage.load_results("2026-07-14", out)
    assert loaded["count"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONUTF8=1 python -m pytest tests/test_main.py -v
```
Expected: FAIL (`ImportError: main`)

- [ ] **Step 3: 实现 main.py**

```python
"""人气榜 — 编排入口。

流程:CHECKPOINT(防覆盖) → Playwright 渲染榜单取 Top100 → 并发补行业/题材
     → 存 popularity_<date>.json → 终端打印 markdown 摘要。

可注入 browser/fetcher(测试用);默认用 screener.browser / screener.fetcher。
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from screener import browser as _default_browser
from screener import fetcher as _default_fetcher
from screener.storage import save_results

SORT = "热度榜"


def _print_summary(stocks: list, date_str: str) -> None:
    """终端打印 markdown 摘要:Top10 + 行业分布 + 热门题材。"""
    print(f"\n# 人气榜快照 · {date_str}（东方财富·{SORT}）")
    print(f"共 {len(stocks)} 只 | 来源：guba.eastmoney.com/rank\n")
    print("## Top 10")
    print("| 排名 | 代码 | 名称 | 行业 | 热度 | 变动 | 题材 |")
    print("|---|---|---|---|---|---|---|")
    for s in stocks[:10]:
        print(f"| {s.get('rank')} | {s.get('code')} | {s.get('name')} | "
              f"{s.get('industry','')} | {s.get('popularity')} | "
              f"{s.get('rank_change','')} | {s.get('reason','')} |")

    # 行业分布 Top5
    from collections import Counter
    ind_cnt = Counter(s.get("industry") for s in stocks if s.get("industry"))
    print("\n## 行业分布（Top 5）")
    print("| 行业 | 数量 |")
    print("|---|---|")
    for ind, n in ind_cnt.most_common(5):
        print(f"| {ind} | {n} |")

    # 热门题材 Top8
    conc_cnt = Counter()
    for s in stocks:
        for c in s.get("concepts", []):
            conc_cnt[c] += 1
    print("\n## 热门题材（Top 8，按出现频次）")
    print("| 题材 | 出现次数 |")
    print("|---|---|")
    for c, n in conc_cnt.most_common(8):
        print(f"| {c} | {n} |")


def run(today_str: str | None = None, output_dir: str | None = None,
        browser=None, fetcher=None) -> bool:
    today_str = today_str or datetime.date.today().strftime("%Y-%m-%d")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = output_dir or os.path.join(base_dir, "data")
    browser = browser or _default_browser
    fetcher = fetcher or _default_fetcher

    # 1. CHECKPOINT:今日快照已存在→提示覆盖(交互场景由调用方处理;此处仅提示)
    import json
    path = os.path.join(output_dir, f"popularity_{today_str}.json")
    if os.path.exists(path):
        print(f"⚠️ 今日人气榜快照已存在:{path},将覆盖。", flush=True)

    # 2. 渲染榜单取 Top100
    print(f"[{today_str}] Playwright 渲染东方财富人气榜({SORT})...", flush=True)
    stocks = browser.fetch_top100(sort=SORT, headless=True)
    print(f"榜单获取完成:{len(stocks)} 只", flush=True)
    if not stocks:
        print("⚠️ 未获取到榜单数据(可能页面改版或网络异常)", flush=True)

    # 3. 并发补行业 + 题材
    if stocks:
        print("并发补行业/题材(push2)...", flush=True)
        fetcher.fetch_industry_for_stocks(stocks, max_workers=10)

    # 4. 保存
    saved = save_results(today_str, SORT, stocks, output_dir)
    print(f"已保存:{saved}", flush=True)

    # 5. 摘要
    _print_summary(stocks, today_str)
    return True


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONUTF8=1 python -m pytest tests/test_main.py -v
```
Expected: 3 passed。再跑全量:
```bash
PYTHONUTF8=1 python -m pytest -v
```
Expected: 全部 passed（storage/fetcher/browser/main）

- [ ] **Step 5: Commit**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/main.py .claude/skills/renqibang/tests/test_main.py
git commit -m "feat(renqibang): main 编排(CHECKPOINT/渲染/补字段/摘要)"
```

---

## Task 7: SKILL.md

**Files:**
- Create: `.claude/skills/renqibang/SKILL.md`

- [ ] **Step 1: 写 SKILL.md**

```markdown
---
name: renqibang
description: 人气榜 — 抓取东方财富股吧个股人气榜前100(热度榜)，保存人气排名、所属行业、题材(上榜原因)、热度、排名变动到本地JSON。当用户说"人气榜"、"股吧人气"、"热门股人气"、"东方财富人气榜"、"人气排名"、"renqibang"时触发。
---

# 人气榜（东方财富股吧人气榜 Top100）

抓取东方财富股吧个股人气榜 Top100 快照，作为**市场情绪观察参考**。

> ⚠️ 高人气 ≠ 买点。人气榜反映市场关注度，利好出尽时高人气股常兑现下跌。须结合 qsht 选股体系的趋势/回踩/市值/业绩纪律使用，避免追涨。

## 使用方式

输入 `/renqibang` 触发。

## 执行步骤

1. 🔴 CHECKPOINT（运行前检查今日快照是否已存在）:
   ```bash
   ls .claude/skills/renqibang/data/popularity_$(date +%Y-%m-%d).json 2>/dev/null
   ```
   - 已存在 → 🛑 STOP，提示"今日人气榜快照已抓取，重跑会覆盖"，询问确认。
   - 不存在 → 继续。

2. 确认依赖（首次需装 chromium）:
   ```bash
   cd .claude/skills/renqibang && pip install -r requirements.txt && python -m playwright install chromium
   ```

3. 运行:
   ```bash
   cd .claude/skills/renqibang && python main.py
   ```
   > Playwright 会启动 headless chromium 渲染页面（约 10-30 秒）。

4. 脚本会:渲染 `guba.eastmoney.com/rank`（浏览器自动解密人气榜密文）→ 翻页取 Top100 → 并发请求 push2 补行业/题材 → 存 `data/popularity_<date>.json` → 终端打印 Top10 + 行业分布 + 热门题材。

5. 读取 `data/popularity_<date>.json` 或终端摘要向用户展示。

## 实测 selector（经 probe_rank.py 确认）

> 榜单页前端改版会导致 selector 失效。失效时重跑 `python probe_rank.py`，按输出更新 `screener/browser.py` 顶部常量（RANK_ROW_SELECTOR / RANK_CELL_SELECTOR / NEXT_PAGE_SELECTOR / HOT_TAB_SELECTOR）。

- RANK_ROW_SELECTOR = `<Task3 填入>`
- RANK_CELL_SELECTOR = `<Task3 填入>`
- NEXT_PAGE_SELECTOR = `<Task3 填入>`
- HOT_TAB_SELECTOR = `<Task3 填入>`

## 字段来源

| 字段 | 来源 |
|---|---|
| 人气排名 / 热度 / 排名变动 | 榜单渲染后 DOM |
| 代码 / 名称 | 榜单渲染后 DOM |
| 所属行业 | push2 stock/get `f127` |
| 题材（上榜原因） | push2 stock/get `f129`（概念板块） |

## 边界条件

| 触发 | 处理 |
|---|---|
| Playwright/chromium 未装 | 提示 `pip install playwright && python -m playwright install chromium` |
| 非交易日 | 人气榜基于股吧行为仍有数据，正常抓取，摘要标注 |
| 榜单不足 100 | 取实际条数，count 如实显示 |
| 榜单 selector 失效（前端改版） | 报错提示，重跑 probe_rank.py 更新 selector |
| push2 字段为空（部分北交所/新股） | 行业/题材留空，不阻断 |
| 今日快照已存在 | CHECKPOINT 询问是否覆盖 |

## ❌ 不要做

- 不要把高人气当买入信号（高人气≠会涨，常是兑现下跌窗口）
- 不要为"上榜原因"抓股吧帖子+LLM（题材用 push2 f129 轻量获取）
- 不要纯 Python 逆向榜单接口（加密动态派生+改版即失效；用 Playwright 渲染）
- 不要忽略 CHECKPOINT 直接覆盖今日快照

## 局限

- 人气榜是股吧用户行为衍生的热度，不代表基本面
- "上榜原因"=题材概念（f129），是所沾概念，未必是当日催化事件
- 仅抓热度榜 Top100 快照，不反映盘中动态
- 依赖 chromium；前端改版可能导致 selector/加密逻辑变化，需维护
```

- [ ] **Step 2: Commit**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/SKILL.md
git commit -m "docs(renqibang): SKILL.md"
```

---

## Task 8: 手动联调验证

> 全部单测通过后，做一次真实接口 + 浏览器联调。依赖 Task 3 已填好 browser.py 的 selector 常量。

- [ ] **Step 1: 确认 selector 已填**

打开 `.claude/skills/renqibang/screener/browser.py`，确认 `RANK_ROW_SELECTOR` 等常量已由 Task 3 探测填入（非空字符串）。若仍为空，先跑 `python probe_rank.py` 补填。

- [ ] **Step 2: 真实跑一轮**

```bash
cd .claude/skills/renqibang && PYTHONUTF8=1 python main.py
```
Expected: chromium 启动渲染，打印"榜单获取完成: N 只"（N 接近 100），并发补字段，生成 `data/popularity_<today>.json`，终端打印 Top10 + 行业分布 + 热门题材。

- [ ] **Step 3: 人工核对**

读 `data/popularity_<today>.json`:
- rank 1-100 连续、code 为 6 位、name 正确
- popularity 为数值、rank_change 有值（+/-/新进/-）
- industry / concepts 非空（多数股票），reason = concepts 拼接

读终端摘要:Top10 表格、行业分布、热门题材合理。

- [ ] **Step 4: 若 selector 或列顺序需修正**

重跑 `python probe_rank.py`，按输出改 `screener/browser.py` 常量或 `IDX_*` 索引，回到 Step 2 复验。

- [ ] **Step 5: Commit（若有 selector/索引修正）**

```bash
cd /c/project/fox/xuan-gu-qi
git add .claude/skills/renqibang/screener/browser.py
git commit -m "fix(renqibang): 榜单 selector/列顺序实测修正"
```

---

## Self-Review（已自查）

- **Spec 覆盖**:storage 读写(Task 1)、push2 行业+题材(Task 2)、榜单 DOM 探测 CHECKPOINT(Task 3)、DOM 解析(Task 4)、Playwright 抓取(Task 5)、编排+CHECKPOINT+摘要(Task 6)、SKILL.md(Task 7)、联调(Task 8)——spec 各节均有任务承接;字段来源映射(排名/热度/变动→DOM,行业→f127,题材→f129)、加密规避(Playwright)、CHECKPOINT 防覆盖、行业分布/热门题材摘要均已覆盖。
- **占位符**:无 TBD/TODO。browser.py selector 常量给候选默认值(`table tbody tr` / `td` / `a:has-text('下一页')`),经 Task3 probe_rank.py 探测后单点修正;parse_one 列顺序由 IDX_* 常量驱动,探测后可单点调整;fixture `rank_row_sample.txt` 由探测产出(示例值已标注按真实替换)。
- **类型一致**:`parse_one`→`fetch_top100`→`main.run`→`storage.save_results` 的 stock dict 字段(rank/code/name/popularity/rank_change + 补 industry/concepts/reason)跨任务一致;`fetch_industry_for_stocks` 就地补字段签名与 main 调用一致;`build_secid` 在 fetcher 内部自洽。
- **已知简化**:`fetch_top100` 因驱动真实浏览器不写单测,靠 parse_one 单测 + Task 8 联调;`sort` 当前固定"热度榜"(spec 第 12 节 CHECKPOINT 留飙升榜为可选交互,本期不实现)。

---

## 实现偏差记录（2026-07-14 探测 + 联调后，实现已据此调整）

实现中发现与 plan 早期假设的几处偏差（已实现，记录供维护）：

1. **榜单 DOM 列结构**（Task 3 探测确认，覆盖 plan File Structure 里假设的 `[rank,code,name,pop,chg]`）：
   - 真实 td 顺序：`td[0]`=rank（前 3 名 DOM 文本空，用累计序号 base_rank）、`td[1]`=rank_change、`td[2]`=历史趋势、`td[3]`=code、`td[4]`=**热帖摘要列（不是 name！）**、`td[5]`=链接、`td[6..8]`=价格、`td[9]`=新晋%/铁杆%
   - `browser.py` 用 `IDX_CHG=1 / IDX_CODE=3 / IDX_FANS=9`（`IDX_NAME=4` 定义保留但 parse_one 不再读，因 td[4] 非名称）。
2. **popularity 语义**：榜单**无独立热度值列**，人气即 rank 本身；`popularity` 取 `td[9]` 第一个百分比（新晋粉丝%）。
3. **name 来源**：DOM 不含名称（td[4] 是热帖摘要），**完全由 push2 `f58` 补**——`fetch_industry_concepts` 返回加 `name`；`fetch_industry_for_stocks` 在 DOM name 为空时用 f58 补，不覆盖非空。
4. **push2 网络适配**（Task 8 联调确认）：当前网络环境 push2 直连（trust_env=False）被服务端 RemoteDisconnected，需**走系统代理**（`trust_env=True`）+ `http`（非 https，代理下 https 成功率低）+ 重试（`RETRIES=3`）+ **多轮 sweep**（`sweeps=3`，每轮只重试仍缺 name 的 code，应对代理突发空响应）。与 chuangxingao 的"禁代理直连新浪/腾讯"不同——push2 服务端拒绝直连。参考 `zhuxian/screener/fetcher.py` 同问题。
5. **selector 实测值**：`RANK_ROW_SELECTOR="table tbody tr"`（每页 20 行，5 页=100）、`RANK_CELL_SELECTOR="td"`、`NEXT_PAGE_SELECTOR="a:has-text('下一页')"`（ajax 翻页）、`HOT_TAB_SELECTOR=""`（默认 tab 即热度榜 `.ranktit.hotrank.active`）。
6. **联调 concern（外部网络，非代码 bug）**：Clash 代理对 push2 间歇 502 时，部分股票的 name/industry/concepts 暂空；但 rank/code/popularity/rank_change 始终可靠（来自 DOM）。代理恢复后多轮 sweep 会自动补全。
7. **fetch_industry_for_stocks 签名扩展**：加 `sweeps: int = 3` 参数（多轮扫描），`max_workers` 默认 10。

实测样本（2026-07-14 联调）：东山精密(002384) rank1 / 元件 / 新晋粉丝 29.77% / 题材 [创投, LED概念, 苹果概念, 5G概念, ...]。
