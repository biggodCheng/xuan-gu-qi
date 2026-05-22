import os
import socket
import time
from datetime import datetime, timedelta
from urllib.request import getproxies

import akshare as ak
import pandas as pd
import requests


def _check_proxy_available(proxy_url: str) -> bool:
    """检测代理是否可用（尝试连接代理端口）。"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 7897
        with socket.create_connection((host, port), timeout=2):
            return True
    except (OSError, socket.timeout):
        return False


# 检测系统代理，可用则保留，不可用则清除避免连接失败
_system_proxies = getproxies()
_proxy_url = _system_proxies.get("https") or _system_proxies.get("http")

if _proxy_url and _check_proxy_available(_proxy_url):
    _original_init = requests.Session.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        self.proxies = {"http": _proxy_url, "https": _proxy_url}

    requests.Session.__init__ = _patched_init
else:
    # 代理不可用，清除环境变量和系统代理，走直连
    for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(_key, None)
    os.environ["NO_PROXY"] = "*"
    _original_init = requests.Session.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        self.trust_env = False

    requests.Session.__init__ = _patched_init


def get_all_stocks_today() -> pd.DataFrame:
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        print(f"获取行情数据失败: {e}")
        return pd.DataFrame(columns=["code", "name", "close"])

    if df is None or df.empty:
        return pd.DataFrame(columns=["code", "name", "close"])

    result = df[["代码", "名称", "最新价"]].copy()
    result.columns = ["code", "name", "close"]
    result = result[result["close"] > 0]
    result = result.reset_index(drop=True)
    return result


def get_stock_history(
    code: str, days: int = 120, exclude_last: bool = False, retries: int = 3
) -> list[float]:
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
