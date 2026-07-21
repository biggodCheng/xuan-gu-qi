import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# 本地日K源(招商证券 vipdoc)优先 — 不复权(原腾讯qfq前复权, 用户接受降级)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
try:
    import local_kline
    _HAS_LOCAL = True
except Exception:
    _HAS_LOCAL = False

for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False


def get_stock_kline(code: str, days: int = 30, retries: int = 3) -> list[dict]:
    """获取单只股票的K线数据（日期+收盘价+成交量）。

    优先使用腾讯财经 API，失败时回退到新浪 API。

    Args:
        code: 股票代码（纯数字，如 600000）
        days: 获取最近多少个交易日的数据
        retries: 重试次数

    Returns:
        [{date: str, close: float, volume: float}, ...] 按日期正序。失败返回空列表。
    """
    if _HAS_LOCAL:
        rows = local_kline.read_day(f"{_get_prefix(code)}{code}")
        if rows:
            if len(rows) > days:
                rows = rows[-days:]
            return [{"date": r["date"], "close": r["close"], "volume": float(r["volume"])} for r in rows]
    # 优先腾讯 API
    for attempt in range(retries):
        result = _fetch_tencent_kline(code, days)
        if result:
            return result
        if attempt < retries - 1:
            time.sleep(0.5)

    # 回退新浪 API
    prefix = _get_prefix(code)
    symbol = f"{prefix}{code}"

    for attempt in range(retries):
        try:
            url = (
                "https://money.finance.sina.com.cn/quotes_service/api/"
                "json_v2.php/CN_MarketData.getKLineData"
            )
            params = {
                "symbol": symbol,
                "scale": 240,
                "ma": "no",
                "datalen": days + 5,
            }
            r = _session.get(url, params=params, timeout=15)
            data = r.json()

            if not data:
                return []

            result = []
            for item in data:
                result.append({
                    "date": item["day"],
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                })
            return result

        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
            continue

    return []


def _fetch_tencent_kline(code: str, days: int) -> list[dict]:
    """通过腾讯财经 API 获取K线数据（含成交量）。"""
    symbol = _get_tencent_symbol(code)
    start_date = (datetime.now() - timedelta(days=days * 2 + 60)).strftime("%Y-%m-%d")
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{symbol},day,{start_date},,{days + 5},qfq",
    }
    try:
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("code") != 0:
            return []

        stock_data = data.get("data", {}).get(symbol, {})
        day_data = stock_data.get("qfqday", []) or stock_data.get("day", [])
        if not day_data:
            return []

        # 格式: [日期, 开盘, 收盘, 最高, 最低, 成交量]
        result = []
        for item in day_data:
            result.append({
                "date": item[0],
                "close": float(item[2]),
                "volume": float(item[5]),
            })
        return result

    except Exception:
        return []


def _get_tencent_symbol(code: str) -> str:
    """腾讯 API 的代码格式: sh600000, sz000001, bj920001。"""
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def _get_prefix(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sz"
