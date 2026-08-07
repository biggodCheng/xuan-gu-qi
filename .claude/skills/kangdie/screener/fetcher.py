"""抗跌观察池数据获取层 — 全程新浪接口，不走腾讯/东财 push2。

数据源（均直连新浪，禁用代理）：
- 全A股列表: Market_Center.getHQNodeData (node=hs_a 分页)  [抄 chuangxingao]
- 个股OHLCV: CN_MarketData.getKLineData (scale=240 日K)    [抄 zhuxian]
- 大盘指数: CN_MarketData.getKLineData (原生支持指数代码)     [抄 qsht-agent/market_env]
- 市值:     getHQNodeData 的 mktcap 字段 (万元)              [抄 shizhi]
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# 接入本地日K源(招商证券 vipdoc, scripts/local_kline.py) — 三 skill 共用本 fetcher
# 本地 vol(手) 与新浪 volume 逐位等价(实测比值 1.0); 本地为空自动 fallback 新浪
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
try:
    import local_kline
    _HAS_LOCAL = True
except Exception:
    _HAS_LOCAL = False

# 清除代理，直连新浪财经（照抄 chuangxingao）
for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
})

# host 用 money.finance(非 vip.stock.finance):后者 2026-08-07 起返回 HTTP 456 限封
_HQNODE_DATA_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/"
    "json_v2.php/Market_Center.getHQNodeData"
)
_KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/"
    "json_v2.php/CN_MarketData.getKLineData"
)

# 万元 → 亿元
_WAN_TO_YI = 1_0000


# ============================================================
# 全A股列表（零改动照抄 chuangxingao.fetcher.get_all_stocks_today）
# ============================================================

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
            params = {
                "page": page,
                "num": per_page,
                "sort": "symbol",
                "asc": 1,
                "node": "hs_a",
                "_s_r_a": "auto",
            }
            r = _session.get(_HQNODE_DATA_URL, params=params, timeout=15)
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


# ============================================================
# 个股 OHLCV 日K（抄 zhuxian._get_stock_kline，改接收纯数字 code）
# ============================================================

def _sina_symbol(code: str) -> str:
    """股票代码 → 新浪符号（sh/sz/bj 前缀）。"""
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def get_stock_kline(code: str, days: int = 70, retries: int = 3) -> list[dict]:
    """获取个股日 K（scale=240 即日K），直连新浪。

    Args:
        code: 纯数字股票代码（如 600000）。
        days: 获取最近多少个交易日（默认 70，满足 60 日最低价比较）。
        retries: 请求失败重试次数。

    Returns:
        K线列表（按日期正序），每项 {day, open, high, low, close, volume}。
        失败返回空列表。本地优先(招商证券 vipdoc); 本地为空 fallback 新浪。
    """
    if _HAS_LOCAL:
        rows = local_kline.read_day(_sina_symbol(code))
        if rows:
            if days:
                rows = rows[-days:]
            return [{"day": r["date"], "open": r["open"], "high": r["high"],
                     "low": r["low"], "close": r["close"],
                     "volume": float(r["volume"])} for r in rows]
    symbol = _sina_symbol(code)
    params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": days}

    for attempt in range(retries):
        try:
            r = _session.get(_KLINE_URL, params=params, timeout=15)
            data = r.json()
            if not isinstance(data, list):
                return []
            result = []
            for k in data:
                try:
                    result.append({
                        "day": k["day"],
                        "open": float(k["open"]),
                        "close": float(k["close"]),
                        "high": float(k["high"]),
                        "low": float(k["low"]),
                        "volume": float(k.get("volume", 0) or 0),
                    })
                except (KeyError, ValueError, TypeError):
                    continue
            return result
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    return []


# ============================================================
# 大盘指数 OHLCV（抄 qsht-agent/market_env.fetch，加重试）
# ============================================================

def get_index_kline(symbol: str, days: int = 150, retries: int = 3) -> list[dict]:
    """获取指数日 K（新浪原生支持指数代码如 sz399006）。

    Args:
        symbol: 指数代码（如 sz399006 创业板指、sh000001 上证指数）。
        days: 获取最近多少个交易日。
        retries: 请求失败重试次数。

    Returns:
        K线列表（按日期正序），每项 {date, open, high, low, close, volume}。
        失败返回空列表。本地优先(招商证券 vipdoc); 本地为空 fallback 新浪。
    """
    if _HAS_LOCAL:
        rows = local_kline.read_day(symbol)
        if rows:
            if days:
                rows = rows[-days:]
            return [{"date": r["date"], "open": r["open"], "high": r["high"],
                     "low": r["low"], "close": r["close"],
                     "volume": float(r["volume"])} for r in rows]
    params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": days}

    for attempt in range(retries):
        try:
            r = _session.get(_KLINE_URL, params=params, timeout=15)
            data = r.json()
            if not isinstance(data, list):
                return []
            result = []
            for k in data:
                try:
                    result.append({
                        "date": k["day"],
                        "open": float(k["open"]),
                        "close": float(k["close"]),
                        "high": float(k["high"]),
                        "low": float(k["low"]),
                        "volume": float(k.get("volume", 0) or 0),
                    })
                except (KeyError, ValueError, TypeError):
                    continue
            return result
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    return []


# ============================================================
# 全A市值映射（抄 shizhi._fetch_all_sina_with_retry，转亿元）
# ============================================================

def get_market_cap_map(max_retries: int = 3) -> dict[str, float]:
    """通过新浪 getHQNodeData 分页获取全市场市值。

    Returns:
        {code: 流通市值（亿元）}。mktcap 字段单位为万元，本函数转换为亿元。
    """
    cap_map: dict[str, float] = {}

    for attempt in range(1, max_retries + 1):
        cap_map.clear()
        page = 1
        per_page = 80
        failed = False

        while True:
            try:
                params = {
                    "page": page,
                    "num": per_page,
                    "sort": "symbol",
                    "asc": 1,
                    "node": "hs_a",
                    "_s_r_a": "auto",
                }
                r = _session.get(_HQNODE_DATA_URL, params=params, timeout=15)

                if r.status_code != 200:
                    print(
                        f"新浪API返回非200状态: {r.status_code} (第{attempt}次重试)",
                        flush=True,
                    )
                    failed = True
                    break

                data = r.json()
                if not data:
                    break

                for item in data:
                    try:
                        code = item.get("code", "")
                        mktcap = item.get("mktcap", "")
                        if code and mktcap:
                            cap_map[code] = float(mktcap) / _WAN_TO_YI
                    except (ValueError, TypeError):
                        continue

                page += 1
                time.sleep(0.5)

            except Exception as e:
                print(
                    f"获取市值第 {page} 页失败: {e} (第{attempt}次重试)",
                    flush=True,
                )
                failed = True
                break

        if not failed and cap_map:
            return cap_map

        if attempt < max_retries:
            wait = attempt * 10
            print(f"等待 {wait} 秒后重试...", flush=True)
            time.sleep(wait)

    return cap_map
