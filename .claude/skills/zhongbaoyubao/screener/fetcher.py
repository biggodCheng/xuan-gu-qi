"""数据获取层 — 业绩预告扫描 + 前复权日K + 名称解析。

数据源:
- 业绩预告:东方财富 datacenter-web(字段名见顶部常量,经 probe_yjyg.py 实测)
- 前复权日K:腾讯 fqkline(失败回退新浪,新浪仅 close 无 open → 基准价缺失时上游标 skipped)
- 股票搜索:东方财富 searchapi

禁用本地代理,避免干扰(与 q2zhanwang/chuangxingao 一致)。
"""
import os
import re
from datetime import datetime, timedelta

import requests

for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})


def _tencent_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def _sina_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def _fetch_tencent_kline(code: str, start_date: str) -> list[list]:
    """腾讯前复权日K,返回 [[date, open, close, high, low, amount], ...]。失败返回 []。"""
    symbol = _tencent_symbol(code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    # 拉足够长(公告后 30 交易日 ≈ 45 自然日,取 90 天余量)
    params = {"param": f"{symbol},day,{start_date},,90,qfq"}
    try:
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("code") != 0:
            return []
        sd = data.get("data", {}).get(symbol, {})
        rows = sd.get("qfqday", []) or sd.get("day", [])
        return rows or []
    except Exception:
        return []


def _fetch_sina_closes(code: str) -> list[str]:
    """新浪日K回退(仅 close,无 open)。返回 [close, ...] 或 []。"""
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {"symbol": _sina_symbol(code), "scale": "240", "ma": "no", "datalen": "60"}
    try:
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        return [item["close"] for item in (data or [])]
    except Exception:
        return []


def get_kline_since(code: str, since_date: str) -> list[dict]:
    """取 since_date 之后的前复权日K(腾讯),返回 [{date,open,close},...] 正序。

    since_date 当天排除(预告公告日 → 取其后首个交易日为基准日)。
    腾讯失败时回退新浪,但新浪无 open → 返回[](上游据此标 skipped)。
    """
    rows = _fetch_tencent_kline(code, since_date)
    if not rows:
        return []  # 回退新浪无 open,无法取基准价 → 空
    out = []
    for row in rows:
        try:
            d, o, c = row[0], float(row[1]), float(row[2])
        except (IndexError, ValueError, TypeError):
            continue
        if d <= since_date:  # 严格晚于公告日
            continue
        out.append({"date": d, "open": o, "close": c})
    return out
