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
    """获取单只股票的历史收盘价（新浪财经数据源）。

    Args:
        code: 股票代码（纯数字，如 600000）
        days: 获取最近多少个交易日的数据
        exclude_last: 是否排除最后一个交易日
        retries: 重试次数

    Returns:
        收盘价列表，按时间正序。失败返回空列表。
    """
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


def _get_prefix(code: str) -> str:
    """根据股票代码判断市场前缀（sh/sz/bj）。"""
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sz"
