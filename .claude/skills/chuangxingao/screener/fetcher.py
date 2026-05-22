import os
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd
import requests

# 东方财富是境内服务，绕过系统代理直连
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
