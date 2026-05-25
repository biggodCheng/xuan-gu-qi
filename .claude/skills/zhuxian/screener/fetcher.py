import os
import time
from datetime import datetime, timedelta

import requests

# 清除代理，直连东方财富
for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False


def get_concept_sectors() -> list[dict]:
    """获取所有 A 股概念板块列表（东方财富数据源）。

    Returns:
        板块列表，每项包含 code, name, close, change_pct。
    """
    all_sectors = []
    page = 1
    per_page = 200

    while True:
        try:
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": page,
                "pz": per_page,
                "po": 1,
                "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": "m:90+t:3",
                "fields": "f2,f3,f4,f12,f14",
            }
            r = _session.get(url, params=params, timeout=15)
            data = r.json()

            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break

            for item in diff:
                try:
                    code = item.get("f12", "")
                    name = item.get("f14", "")
                    close = float(item.get("f2", 0))
                    change_pct = float(item.get("f3", 0))

                    if not code or not name or close <= 0:
                        continue

                    all_sectors.append({
                        "code": code,
                        "name": name,
                        "close": close,
                        "change_pct": change_pct,
                    })
                except (ValueError, TypeError):
                    continue

            total = data.get("data", {}).get("total", 0)
            if page * per_page >= total:
                break
            page += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"获取板块列表第 {page} 页失败: {e}", flush=True)
            break

    return all_sectors


def get_sector_kline(bk_code: str, days: int = 120, retries: int = 3) -> list[dict]:
    """获取单个概念板块的日 K 线数据（东方财富数据源）。

    Args:
        bk_code: 板块代码，如 BK0477
        days: 获取最近多少个交易日的数据
        retries: 重试次数

    Returns:
        K 线列表，每项包含 date, open, close, high, low, volume。失败返回空列表。
    """
    for attempt in range(retries):
        try:
            # beg 设为 200 天前，确保获取到最近的数据
            beg_date = (datetime.now() - timedelta(days=200)).strftime("%Y%m%d")
            url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                "secid": f"90.{bk_code}",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101,
                "fqt": 1,
                "beg": beg_date,
                "end": "20500101",
            }
            r = _session.get(url, params=params, timeout=15)
            data = r.json()

            klines = data.get("data", {}).get("klines", [])
            if not klines:
                return []

            result = []
            for line in klines[-days:]:
                try:
                    parts = line.split(",")
                    result.append({
                        "date": parts[0],
                        "open": float(parts[1]),
                        "close": float(parts[2]),
                        "high": float(parts[3]),
                        "low": float(parts[4]),
                        "volume": float(parts[5]),
                    })
                except (ValueError, IndexError):
                    continue

            return result

        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
            continue

    return []
