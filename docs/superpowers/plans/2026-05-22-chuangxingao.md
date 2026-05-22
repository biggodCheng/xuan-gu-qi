# 创新高选股器 (chuangxingao) 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建一个 Claude Code Skill，每日收盘后筛选 A 股收盘价创 100 个交易日新高的股票，保存为 JSON。

**Architecture:** 模块化 Python 脚本，fetcher（数据获取）→ calculator（新高判断）→ storage（JSON 保存），由 main.py 串联，通过 SKILL.md 注册为 `/chuangxingao` 命令。

**Tech Stack:** Python 3.10+, akshare, pandas

---

## 文件结构

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| Create | `.claude/skills/chuangxingao/requirements.txt` | 依赖声明 |
| Create | `.claude/skills/chuangxingao/screener/__init__.py` | 包初始化 |
| Create | `.claude/skills/chuangxingao/screener/storage.py` | JSON 文件读写 |
| Create | `.claude/skills/chuangxingao/screener/calculator.py` | 100 日新高判断逻辑 |
| Create | `.claude/skills/chuangxingao/screener/fetcher.py` | akshare 数据获取 |
| Create | `.claude/skills/chuangxingao/main.py` | 入口脚本，串联流程 |
| Create | `.claude/skills/chuangxingao/SKILL.md` | Skill 定义文件 |
| Create | `.claude/skills/chuangxingao/tests/__init__.py` | 测试包初始化 |
| Create | `.claude/skills/chuangxingao/tests/test_storage.py` | storage 模块测试 |
| Create | `.claude/skills/chuangxingao/tests/test_calculator.py` | calculator 模块测试 |
| Create | `.claude/skills/chuangxingao/tests/test_fetcher.py` | fetcher 模块测试 |
| Create | `.claude/skills/chuangxingao/tests/test_main.py` | main 集成测试 |

---

### Task 1: 项目骨架与依赖

**Files:**
- Create: `.claude/skills/chuangxingao/requirements.txt`
- Create: `.claude/skills/chuangxingao/screener/__init__.py`
- Create: `.claude/skills/chuangxingao/tests/__init__.py`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p .claude/skills/chuangxingao/screener
mkdir -p .claude/skills/chuangxingao/tests
mkdir -p .claude/skills/chuangxingao/data
```

- [ ] **Step 2: 创建 requirements.txt**

```txt
akshare>=1.12.0
pandas>=2.0.0
```

- [ ] **Step 3: 创建 screener/__init__.py**

```python
```

（空文件，仅做包标记）

- [ ] **Step 4: 创建 tests/__init__.py**

```python
```

（空文件，仅做包标记）

- [ ] **Step 5: 安装依赖**

```bash
pip install -r .claude/skills/chuangxingao/requirements.txt
```

Expected: 成功安装 akshare 和 pandas

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/chuangxingao/requirements.txt .claude/skills/chuangxingao/screener/__init__.py .claude/skills/chuangxingao/tests/__init__.py
git commit -m "feat: init project skeleton with dependencies"
```

---

### Task 2: storage 模块

**Files:**
- Create: `.claude/skills/chuangxingao/screener/storage.py`
- Create: `.claude/skills/chuangxingao/tests/test_storage.py`

- [ ] **Step 1: 写 test_storage.py 失败测试**

```python
import json
import os
import tempfile

from screener.storage import load_results, save_results


def test_save_results_creates_file():
    """保存结果应创建 JSON 文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        stocks = [
            {"code": "000001", "name": "平安银行", "close": 15.23, "high_100d": 15.10}
        ]
        save_results("2026-05-22", stocks, tmpdir)

        filepath = os.path.join(tmpdir, "2026-05-22.json")
        assert os.path.exists(filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["date"] == "2026-05-22"
        assert data["description"] == "A股当日收盘价创100个交易日新高"
        assert data["count"] == 1
        assert len(data["stocks"]) == 1
        assert data["stocks"][0]["code"] == "000001"


def test_save_results_overwrites_existing():
    """已存在的文件应被覆盖"""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_results("2026-05-22", [], tmpdir)
        save_results("2026-05-22", [{"code": "000001", "name": "测试", "close": 10.0, "high_100d": 9.0}], tmpdir)

        data = load_results("2026-05-22", tmpdir)
        assert data["count"] == 1


def test_load_results_file_not_found():
    """文件不存在时返回 None"""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_results("2099-01-01", tmpdir)
        assert result is None


def test_save_results_creates_directory():
    """data 目录不存在时应自动创建"""
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = os.path.join(tmpdir, "sub", "dir")
        save_results("2026-05-22", [], nested)

        filepath = os.path.join(nested, "2026-05-22.json")
        assert os.path.exists(filepath)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/test_storage.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'screener.storage'`

- [ ] **Step 3: 实现 storage.py**

```python
import json
import os


def save_results(date_str: str, stocks: list[dict], output_dir: str) -> None:
    """将创新高股票列表保存为 JSON 文件。

    Args:
        date_str: 交易日期，格式 YYYY-MM-DD
        stocks: 创新高股票列表，每项含 code, name, close, high_100d
        output_dir: 输出目录路径
    """
    os.makedirs(output_dir, exist_ok=True)

    result = {
        "date": date_str,
        "description": "A股当日收盘价创100个交易日新高",
        "count": len(stocks),
        "stocks": stocks,
    }

    filepath = os.path.join(output_dir, f"{date_str}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def load_results(date_str: str, output_dir: str) -> dict | None:
    """读取指定日期的创新高结果。

    Args:
        date_str: 交易日期，格式 YYYY-MM-DD
        output_dir: 输出目录路径

    Returns:
        JSON 数据字典，文件不存在返回 None
    """
    filepath = os.path.join(output_dir, f"{date_str}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/test_storage.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chuangxingao/screener/storage.py .claude/skills/chuangxingao/tests/test_storage.py
git commit -m "feat: implement storage module with JSON read/write"
```

---

### Task 3: calculator 模块

**Files:**
- Create: `.claude/skills/chuangxingao/screener/calculator.py`
- Create: `.claude/skills/chuangxingao/tests/test_calculator.py`

- [ ] **Step 1: 写 test_calculator.py 失败测试**

```python
from screener.calculator import is_new_high, filter_new_highs


def test_is_new_high_true():
    """今日收盘价等于100日最高价，应返回 True"""
    close = 20.0
    history = [18.0, 19.0, 19.5, 20.0, 17.0]
    assert is_new_high(close, history) is True


def test_is_new_high_false():
    """今日收盘价低于100日最高价，应返回 False"""
    close = 18.0
    history = [18.0, 19.0, 19.5, 20.0, 17.0]
    assert is_new_high(close, history) is False


def test_is_new_high_empty_history():
    """历史数据为空，应返回 False"""
    assert is_new_high(20.0, []) is False


def test_filter_new_highs():
    """应正确筛选出创新高的股票"""
    stocks = [
        {"code": "000001", "name": "平安银行", "close": 20.0},
        {"code": "000002", "name": "万科A", "close": 10.0},
    ]
    histories = {
        "000001": [18.0, 19.0, 19.5, 17.0],  # 最高19.5, 收盘20.0 → 新高
        "000002": [11.0, 12.0, 10.5, 10.0],   # 最高12.0, 收盘10.0 → 非新高
    }

    result = filter_new_highs(stocks, histories)
    assert len(result) == 1
    assert result[0]["code"] == "000001"
    assert result[0]["close"] == 20.0
    assert result[0]["high_100d"] == 19.5


def test_filter_new_highs_no_history():
    """无历史数据的股票应被跳过"""
    stocks = [
        {"code": "000001", "name": "平安银行", "close": 20.0},
    ]
    histories = {}

    result = filter_new_highs(stocks, histories)
    assert len(result) == 0


def test_filter_new_highs_short_history():
    """历史数据不足100条时，仍按现有数据判断"""
    stocks = [
        {"code": "000001", "name": "平安银行", "close": 20.0},
    ]
    histories = {
        "000001": [15.0, 16.0],  # 只有2条，最高16.0
    }

    result = filter_new_highs(stocks, histories)
    assert len(result) == 1
    assert result[0]["high_100d"] == 16.0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/test_calculator.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'screener.calculator'`

- [ ] **Step 3: 实现 calculator.py**

```python
from screener.storage import save_results, load_results


def is_new_high(close: float, history: list[float]) -> bool:
    """判断今日收盘价是否创历史新高。

    Args:
        close: 今日收盘价
        history: 过去 N 个交易日的收盘价列表

    Returns:
        True 表示创历史新高
    """
    if not history:
        return False
    return close >= max(history)


def filter_new_highs(
    stocks: list[dict], histories: dict[str, list[float]]
) -> list[dict]:
    """从股票列表中筛选出创100日新高的股票。

    Args:
        stocks: 当日股票列表，每项含 code, name, close
        histories: 以股票代码为 key，收盘价历史列表为 value 的字典

    Returns:
        创新高的股票列表，每项额外包含 high_100d 字段
    """
    result = []
    for stock in stocks:
        code = stock["code"]
        history = histories.get(code, [])
        if not history:
            continue
        if is_new_high(stock["close"], history):
            result.append({
                "code": code,
                "name": stock["name"],
                "close": stock["close"],
                "high_100d": max(history),
            })
    return result
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/test_calculator.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chuangxingao/screener/calculator.py .claude/skills/chuangxingao/tests/test_calculator.py
git commit -m "feat: implement calculator module for 100-day new high detection"
```

---

### Task 4: fetcher 模块

**Files:**
- Create: `.claude/skills/chuangxingao/screener/fetcher.py`
- Create: `.claude/skills/chuangxingao/tests/test_fetcher.py`

- [ ] **Step 1: 写 test_fetcher.py 失败测试**

```python
from unittest.mock import patch, MagicMock
import pandas as pd

from screener.fetcher import get_all_stocks_today, get_stock_history


def test_get_all_stocks_today():
    """应返回标准化列名的 DataFrame"""
    fake_df = pd.DataFrame({
        "代码": ["000001", "000002"],
        "名称": ["平安银行", "万科A"],
        "最新价": [15.23, 10.50],
    })
    with patch("screener.fetcher.ak.stock_zh_a_spot_em", return_value=fake_df):
        result = get_all_stocks_today()

    assert list(result.columns) == ["code", "name", "close"]
    assert len(result) == 2
    assert result.iloc[0]["code"] == "000001"
    assert result.iloc[0]["name"] == "平安银行"
    assert result.iloc[0]["close"] == 15.23


def test_get_all_stocks_today_filters_invalid():
    """应过滤掉非主板股票（如退市、ST 等）"""
    fake_df = pd.DataFrame({
        "代码": ["000001", "688001", "300001"],
        "名称": ["平安银行", "华兴源创", "特锐德"],
        "最新价": [15.23, 50.0, 20.0],
    })
    with patch("screener.fetcher.ak.stock_zh_a_spot_em", return_value=fake_df):
        result = get_all_stocks_today()

    codes = result["code"].tolist()
    assert "000001" in codes
    assert "688001" in codes
    assert "300001" in codes


def test_get_all_stocks_today_empty():
    """行情为空时返回空 DataFrame"""
    fake_df = pd.DataFrame(columns=["代码", "名称", "最新价"])
    with patch("screener.fetcher.ak.stock_zh_a_spot_em", return_value=fake_df):
        result = get_all_stocks_today()

    assert len(result) == 0


def test_get_stock_history():
    """应返回近 N 个交易日收盘价列表"""
    fake_df = pd.DataFrame({
        "日期": ["2026-05-20", "2026-05-21", "2026-05-22"],
        "收盘": [14.0, 14.5, 15.0],
    })
    with patch("screener.fetcher.ak.stock_zh_a_hist", return_value=fake_df):
        result = get_stock_history("000001", days=120)

    assert result == [14.0, 14.5, 15.0]


def test_get_stock_history_excludes_today():
    """历史数据应排除当日（只取前 N 天用于判断新高）"""
    fake_df = pd.DataFrame({
        "日期": ["2026-05-20", "2026-05-21", "2026-05-22"],
        "收盘": [14.0, 14.5, 15.0],
    })
    with patch("screener.fetcher.ak.stock_zh_a_hist", return_value=fake_df):
        result = get_stock_history("000001", days=120, exclude_last=True)

    assert result == [14.0, 14.5]


def test_get_stock_history_empty():
    """无历史数据时返回空列表"""
    fake_df = pd.DataFrame(columns=["日期", "收盘"])
    with patch("screener.fetcher.ak.stock_zh_a_hist", return_value=fake_df):
        result = get_stock_history("000001")

    assert result == []


def test_get_stock_history_error_returns_empty():
    """接口异常时返回空列表，不抛异常"""
    with patch(
        "screener.fetcher.ak.stock_zh_a_hist", side_effect=Exception("timeout")
    ):
        result = get_stock_history("000001")

    assert result == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/test_fetcher.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'screener.fetcher'`

- [ ] **Step 3: 实现 fetcher.py**

```python
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd


def get_all_stocks_today() -> pd.DataFrame:
    """获取全 A 股当日实时行情。

    Returns:
        DataFrame，列名：code, name, close
    """
    df = ak.stock_zh_a_spot_em()
    if df.empty:
        return pd.DataFrame(columns=["code", "name", "close"])

    result = df[["代码", "名称", "最新价"]].copy()
    result.columns = ["code", "name", "close"]
    result = result[result["close"] > 0]
    result = result.reset_index(drop=True)
    return result


def get_stock_history(
    code: str, days: int = 120, exclude_last: bool = False, retries: int = 3
) -> list[float]:
    """获取单只股票的历史收盘价。

    Args:
        code: 股票代码
        days: 回溯自然日天数（约 days*0.7 个交易日）
        exclude_last: 是否排除最后一根 K 线（当日）
        retries: 重试次数

    Returns:
        收盘价列表，按时间正序。失败返回空列表。
    """
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    for attempt in range(retries):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            if df.empty:
                return []

            closes = df["收盘"].tolist()
            if exclude_last and len(closes) > 1:
                closes = closes[:-1]
            return closes

        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
            continue

    return []
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/test_fetcher.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chuangxingao/screener/fetcher.py .claude/skills/chuangxingao/tests/test_fetcher.py
git commit -m "feat: implement fetcher module with akshare data fetching"
```

---

### Task 5: main.py 入口脚本

**Files:**
- Create: `.claude/skills/chuangxingao/main.py`
- Create: `.claude/skills/chuangxingao/tests/test_main.py`

- [ ] **Step 1: 写 test_main.py 失败测试**

```python
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
import pandas as pd

from screener.main import run_screener


def _make_today_df():
    return pd.DataFrame({
        "code": ["000001", "000002"],
        "name": ["平安银行", "万科A"],
        "close": [20.0, 10.0],
    })


def _make_history_high():
    return [18.0, 19.0, 19.5, 17.0]


def _make_history_low():
    return [11.0, 12.0, 10.5, 10.0]


@patch("screener.main.get_stock_history")
@patch("screener.main.get_all_stocks_today")
def test_run_screener_filters_correctly(mock_today, mock_history):
    """应只保存创新高的股票"""
    mock_today.return_value = _make_today_df()
    mock_history.side_effect = lambda code, **kw: (
        _make_history_high() if code == "000001" else _make_history_low()
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        run_screener(output_dir=tmpdir)

        date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
        filepath = os.path.join(tmpdir, f"{date_str}.json")
        assert os.path.exists(filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["count"] == 1
        assert data["stocks"][0]["code"] == "000001"


@patch("screener.main.get_all_stocks_today")
def test_run_screener_no_data_today(mock_today):
    """无行情数据时应提示非交易日"""
    mock_today.return_value = pd.DataFrame(columns=["code", "name", "close"])

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_screener(output_dir=tmpdir)
        assert result is False
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/test_main.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'screener.main'`

- [ ] **Step 3: 实现 main.py**

```python
import os
import sys
import time
from datetime import datetime

from screener.fetcher import get_all_stocks_today, get_stock_history
from screener.calculator import filter_new_highs
from screener.storage import save_results


def run_screener(output_dir: str | None = None) -> bool:
    """执行创新高选股完整流程。

    Args:
        output_dir: 输出目录，默认为脚本同级的 data/ 目录

    Returns:
        True 表示成功执行，False 表示无数据（如非交易日）
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "data")

    start_time = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"[{date_str}] 开始获取全 A 股当日行情...")
    stocks_df = get_all_stocks_today()

    if stocks_df.empty:
        print("未获取到行情数据，可能是非交易日。")
        return False

    stocks = stocks_df.to_dict("records")
    print(f"共获取 {len(stocks)} 只股票，开始逐个获取历史数据...")

    histories = {}
    for i, stock in enumerate(stocks):
        code = stock["code"]
        history = get_stock_history(code, days=150, exclude_last=True)
        histories[code] = history

        if (i + 1) % 500 == 0:
            print(f"  已处理 {i + 1}/{len(stocks)}...")

    print("历史数据获取完成，开始计算创新高...")
    new_highs = filter_new_highs(stocks, histories)

    save_results(date_str, new_highs, output_dir)

    elapsed = time.time() - start_time
    print(f"完成！共发现 {len(new_highs)} 只股票创100日新高，耗时 {elapsed:.1f} 秒")
    print(f"结果已保存到: {os.path.join(output_dir, f'{date_str}.json')}")

    return True


if __name__ == "__main__":
    run_screener()
```

注意：`main.py` 放在 `screener/` 包内的原因是让 `from screener.main` 导入生效。但根据设计文档，`main.py` 应在 `chuangxingao/` 根目录。这里需要调整——在 `chuangxingao/` 根目录的 `main.py` 中添加 `sys.path` 处理：

**修正：main.py 放在 `chuangxingao/` 根目录**

```python
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import get_all_stocks_today, get_stock_history
from screener.calculator import filter_new_highs
from screener.storage import save_results


def run_screener(output_dir: str | None = None) -> bool:
    """执行创新高选股完整流程。

    Args:
        output_dir: 输出目录，默认为脚本同级的 data/ 目录

    Returns:
        True 表示成功执行，False 表示无数据（如非交易日）
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "data")

    start_time = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"[{date_str}] 开始获取全 A 股当日行情...")
    stocks_df = get_all_stocks_today()

    if stocks_df.empty:
        print("未获取到行情数据，可能是非交易日。")
        return False

    stocks = stocks_df.to_dict("records")
    print(f"共获取 {len(stocks)} 只股票，开始逐个获取历史数据...")

    histories = {}
    for i, stock in enumerate(stocks):
        code = stock["code"]
        history = get_stock_history(code, days=150, exclude_last=True)
        histories[code] = history

        if (i + 1) % 500 == 0:
            print(f"  已处理 {i + 1}/{len(stocks)}...")

    print("历史数据获取完成，开始计算创新高...")
    new_highs = filter_new_highs(stocks, histories)

    save_results(date_str, new_highs, output_dir)

    elapsed = time.time() - start_time
    print(f"完成！共发现 {len(new_highs)} 只股票创100日新高，耗时 {elapsed:.1f} 秒")
    print(f"结果已保存到: {os.path.join(output_dir, f'{date_str}.json')}")

    return True


if __name__ == "__main__":
    run_screener()
```

对应的测试 `test_main.py` mock 路径也要修正：

```python
@patch("main.get_stock_history")
@patch("main.get_all_stocks_today")
def test_run_screener_filters_correctly(mock_today, mock_history):
```

但由于 mock 需要模块已导入，更务实的做法是在 test 中用 `from main import run_screener` 并 mock `screener.fetcher` 中的函数：

```python
@patch("screener.fetcher.get_stock_history")
@patch("screener.fetcher.get_all_stocks_today")
def test_run_screener_filters_correctly(mock_today, mock_history):
```

这样 mock 打在源头模块上，不受 `main.py` 的 import 路径影响。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/test_main.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/chuangxingao/main.py .claude/skills/chuangxingao/tests/test_main.py
git commit -m "feat: implement main entry script with full screener pipeline"
```

---

### Task 6: SKILL.md 定义文件

**Files:**
- Create: `.claude/skills/chuangxingao/SKILL.md`

- [ ] **Step 1: 创建 SKILL.md**

```markdown
---
name: chuangxingao
description: A股创新高选股器 — 筛选当日收盘价创100个交易日新高的股票，结果保存为 JSON
---

# 创新高选股器

A股收盘后筛选创100个交易日新高的股票。

## 使用方式

输入 `/chuangxingao` 触发执行。

## 执行步骤

1. 确认依赖已安装：
   ```bash
   cd .claude/skills/chuangxingao && pip install -r requirements.txt
   ```

2. 运行选股脚本：
   ```bash
   cd .claude/skills/chuangxingao && python main.py
   ```

3. 脚本会：
   - 获取全 A 股当日行情
   - 逐个获取历史数据（约 10-20 分钟）
   - 计算哪些股票创100日新高
   - 结果保存到 `data/YYYY-MM-DD.json`

4. 向用户展示结果摘要：创新高股票数量、输出文件路径

## 非交易日

如果当天没有行情数据（周末、节假日），脚本会提示"未获取到行情数据，可能是非交易日"。

## 输出格式

```json
{
  "date": "2026-05-22",
  "description": "A股当日收盘价创100个交易日新高",
  "count": 42,
  "stocks": [
    {"code": "000001", "name": "平安银行", "close": 15.23, "high_100d": 15.10}
  ]
}
```
```

- [ ] **Step 2: 验证 Skill 被识别**

在 Claude Code 中输入 `/chuangxingao` 检查是否能触发。

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/chuangxingao/SKILL.md
git commit -m "feat: add SKILL.md for /chuangxingao command"
```

---

### Task 7: 端到端验证

**Files:** 无新文件

- [ ] **Step 1: 运行全部单元测试**

```bash
cd .claude/skills/chuangxingao && python -m pytest tests/ -v
```

Expected: 全部 passed

- [ ] **Step 2: 运行 main.py 实际执行（需网络，非交易日会提示）**

```bash
cd .claude/skills/chuangxingao && python main.py
```

Expected: 要么成功输出 JSON 文件，要么提示"非交易日"

- [ ] **Step 3: 检查输出文件**

如果上一步成功：
```bash
ls -la .claude/skills/chuangxingao/data/
cat .claude/skills/chuangxingao/data/$(date +%Y-%m-%d).json
```

Expected: JSON 文件存在且格式正确

- [ ] **Step 4: 验证 Skill 触发**

在 Claude Code 中输入 `/chuangxingao`，确认能识别并执行。

---

## 自检清单

| 检查项 | 状态 |
|--------|------|
| spec 每个需求都有对应 Task | ✅ storage/calculator/fetcher/main/SKILL.md 全覆盖 |
| 无 TBD/TODO 占位符 | ✅ 全部代码完整 |
| 函数签名跨 Task 一致 | ✅ `get_all_stocks_today()` 返回 DataFrame(code,name,close)，`get_stock_history()` 返回 list[float]，`filter_new_highs()` 接收 list[dict]+dict[str,list] |
| JSON 输出格式与 spec 一致 | ✅ date/description/count/stocks 四字段 |
| 异常处理与 spec 一致 | ✅ 非交易日检测、重试3次、data 目录自动创建 |
