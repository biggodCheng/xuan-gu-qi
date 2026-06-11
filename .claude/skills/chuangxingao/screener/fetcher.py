import json
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

# 清除代理，直连新浪财经
for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False


def get_all_stocks_today() -> pd.DataFrame:
    """获取全 A 股当日行情（新浪财经数据源）。

    Returns:
        DataFrame，列名：code, name, close
    """
    all_stocks = []
    page = 1
    per_page = 80

    while True:
        try:
            url = (
                "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
                "json_v2.php/Market_Center.getHQNodeData"
            )
            params = {
                "page": page,
                "num": per_page,
                "sort": "symbol",
                "asc": 1,
                "node": "hs_a",
                "_s_r_a": "auto",
            }
            r = _session.get(url, params=params, timeout=15)
            data = r.json()

            if not data:
                break

            for item in data:
                try:
                    close_price = float(item.get("trade", 0))
                    if close_price <= 0:
                        continue
                    name = item["name"]
                    if name.startswith("ST") or name.startswith("*ST") or name.startswith("N"):
                        continue
                    code = item["code"]
                    all_stocks.append(
                        {"code": code, "name": name, "close": close_price}
                    )
                except (ValueError, KeyError):
                    continue

            page += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"获取行情第 {page} 页失败: {e}")
            break

    if not all_stocks:
        return pd.DataFrame(columns=["code", "name", "close"])

    return pd.DataFrame(all_stocks).reset_index(drop=True)


def get_stock_history(
    code: str, days: int = 100, exclude_last: bool = False, retries: int = 3
) -> list[float]:
    """获取单只股票的历史收盘价。

    优先使用腾讯财经 API，失败时回退到新浪 API。

    Args:
        code: 股票代码（纯数字，如 600000）
        days: 获取最近多少个交易日的数据
        exclude_last: 是否排除最后一个交易日
        retries: 重试次数

    Returns:
        收盘价列表，按时间正序。失败返回空列表。
    """
    # 优先腾讯 API
    for attempt in range(retries):
        try:
            closes = _fetch_tencent_closes(code, days)
            if closes:
                if exclude_last and len(closes) > 1:
                    closes = closes[:-1]
                return closes
        except Exception:
            pass
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
                "datalen": days + 10,
            }
            r = _session.get(url, params=params, timeout=15)
            data = r.json()

            if not data:
                return []

            closes = [float(item["close"]) for item in data]
            if exclude_last and len(closes) > 1:
                closes = closes[:-1]
            return closes

        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
            continue

    return []


def _fetch_tencent_closes(code: str, days: int) -> list[float]:
    """通过腾讯财经 API 获取历史收盘价。"""
    symbol = _get_tencent_symbol(code)
    start_date = (datetime.now() - timedelta(days=days * 2 + 60)).strftime("%Y-%m-%d")
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{symbol},day,{start_date},,{days + 10},qfq",
    }
    r = _session.get(url, params=params, timeout=15)
    data = r.json()
    if data.get("code") != 0:
        return []

    stock_data = data.get("data", {}).get(symbol, {})
    day_data = stock_data.get("qfqday", []) or stock_data.get("day", [])
    if not day_data:
        return []

    return [float(item[2]) for item in day_data]


def _get_tencent_symbol(code: str) -> str:
    """腾讯 API 的代码格式: sh600000, sz000001, bj920001。"""
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def _get_prefix(code: str) -> str:
    """根据股票代码判断市场前缀（sh/sz/bj）。"""
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sz"
