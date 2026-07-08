# -*- coding: utf-8 -*-
"""数据获取层 — 腾讯前复权日K + 腾讯qt市值。
IO 函数（fetch_kline/fetch_marketcap）调网络后委托给纯解析函数。
"""
import os
from datetime import datetime, timedelta

import requests

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
_session = requests.Session()
_session.trust_env = False


# ---- 代码/板块/阈值（纯函数）----

def tencent_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def get_board(code: str) -> str:
    """main / kc_cy(科创创业) / bj。"""
    if code.startswith(("68", "30")):
        return "kc_cy"
    if code.startswith(("8", "4", "9")):
        return "bj"
    return "main"


def zt_threshold(code: str) -> float:
    return {"main": 9.5, "kc_cy": 19.5, "bj": 29.5}[get_board(code)]


# ---- 响应解析（纯函数）----

def _parse_tencent_kline(payload: dict, symbol: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("code") != 0:
        return []
    sd = payload.get("data", {}).get(symbol, {})
    rows = sd.get("qfqday", []) or sd.get("day", [])
    out = []
    for x in rows:
        try:
            out.append({"date": x[0], "open": float(x[1]), "close": float(x[2]),
                        "high": float(x[3]), "low": float(x[4]), "volume": float(x[5])})
        except (ValueError, IndexError, TypeError):
            continue
    return out


def _parse_qt(raw: str) -> tuple:
    try:
        line = raw.strip().split(";")[0].strip()
        parts = line.split('="', 1)[1].rstrip('";').split("~")
        total = float(parts[44]) if len(parts) > 44 else None
        circ = float(parts[45]) if len(parts) > 45 else None
        return total, circ
    except Exception:
        return None, None


# ---- IO（网络 + 解析）----

def fetch_kline(code: str, days: int = 130) -> list[dict]:
    sym = tencent_symbol(code)
    start = (datetime.now() - timedelta(days=days * 2 + 90)).strftime("%Y-%m-%d")
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    try:
        r = _session.get(url, params={"param": f"{sym},day,{start},,{days + 10},qfq"}, timeout=15)
        return _parse_tencent_kline(r.json(), sym)
    except Exception:
        return []


def fetch_marketcap(code: str) -> tuple:
    sym = tencent_symbol(code)
    try:
        r = _session.get(f"https://qt.gtimg.cn/q={sym}", timeout=15)
        return _parse_qt(r.text)
    except Exception:
        return None, None
