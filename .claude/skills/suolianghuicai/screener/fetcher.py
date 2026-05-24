import os
import time

import requests

for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False


def get_stock_kline(code: str, days: int = 30, retries: int = 3) -> list[dict]:
    """获取单只股票的K线数据（日期+收盘价+成交量）。

    Args:
        code: 股票代码（纯数字，如 600000）
        days: 获取最近多少个交易日的数据
        retries: 重试次数

    Returns:
        [{date: str, close: float, volume: float}, ...] 按日期正序。失败返回空列表。
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


def _get_prefix(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sz"
