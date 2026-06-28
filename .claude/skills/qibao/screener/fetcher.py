import os
import time
from datetime import datetime, timedelta

import requests

# 清除代理，直连数据源
for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False


def _parse_tencent_item(item: list) -> dict:
    """腾讯日K项 [日期, 开盘, 收盘, 最高, 最低, 成交量] → OHLCV dict。"""
    return {
        "date": item[0],
        "open": float(item[1]),
        "close": float(item[2]),
        "high": float(item[3]),
        "low": float(item[4]),
        "volume": float(item[5]),
    }


def _parse_sina_item(item: dict) -> dict:
    """新浪日K项 {day,open,high,low,close,volume} → OHLCV dict。"""
    return {
        "date": item["day"],
        "open": float(item["open"]),
        "close": float(item["close"]),
        "high": float(item["high"]),
        "low": float(item["low"]),
        "volume": float(item["volume"]),
    }


def get_stock_kline(code: str, days: int = 120, retries: int = 3) -> list[dict]:
    """获取单只股票日K线（OHLCV）。腾讯优先，失败或残缺回退新浪。

    Returns:
        [{date,open,high,low,close,volume}, ...] 按日期正序。失败返回空列表。
    """
    for attempt in range(retries):
        result = _fetch_tencent_kline(code, days)
        if result:
            return result
        if attempt < retries - 1:
            time.sleep(0.5)

    for attempt in range(retries):
        result = _fetch_sina_kline(code, days)
        if result:
            return result
        if attempt < retries - 1:
            time.sleep(1)

    return []


def _fetch_tencent_kline(code: str, days: int) -> list[dict]:
    symbol = _get_tencent_symbol(code)
    start_date = (datetime.now() - timedelta(days=days * 2 + 60)).strftime("%Y-%m-%d")
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{symbol},day,{start_date},,{days + 5},qfq"}
    try:
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("code") != 0:
            return []
        stock_data = data.get("data", {}).get(symbol, {})
        day_data = stock_data.get("qfqday", []) or stock_data.get("day", [])
        if not day_data:
            return []
        return [_parse_tencent_item(item) for item in day_data]
    except Exception:
        return []


def _fetch_sina_kline(code: str, days: int) -> list[dict]:
    symbol = f"{_get_sina_prefix(code)}{code}"
    try:
        url = (
            "https://money.finance.sina.com.cn/quotes_service/api/"
            "json_v2.php/CN_MarketData.getKLineData"
        )
        params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": days + 5}
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        if not data:
            return []
        return [_parse_sina_item(item) for item in data]
    except Exception:
        return []


def _get_tencent_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def _get_sina_prefix(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sz"
