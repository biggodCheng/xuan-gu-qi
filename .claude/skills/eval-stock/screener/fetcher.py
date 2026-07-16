# -*- coding: utf-8 -*-
"""数据获取层 — 新浪日K(不复权) + 腾讯qt市值。

腾讯日K接口(web.ifzq.gtimg.cn)于 2026-07-16 被 WAF 拦截(返回反爬跳转页),
K线源改用新浪 CN_MarketData.getKLineData(直连可达)。腾讯qt简版行情
(qt.gtimg.cn)未受影响,市值接口保留。

新浪 getKLineData 返回不复权数据;100日趋势窗口内除权跳空影响有限
(与 zhuxian 板块聚合一致),对新高/涨停/缩量回踩判断可接受。

IO 函数(fetch_kline/fetch_marketcap)调网络后委托给纯解析函数。
"""
import os

import requests

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
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

_SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"


# ---- 代码/板块/阈值（纯函数）----

def tencent_symbol(code: str) -> str:
    """A 股行情前缀（新浪/腾讯通用）：6→sh，4/8/92→bj，其余→sz。"""
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def get_board(code: str) -> str:
    """main / kc_cy(科创创业) / bj。

    北交所覆盖：4(43xxxx/40xxxx)、8(83xxxx/87xxxx/88xxxx)、92(920xxx 新代码)。
    前缀元组与 tencent_symbol 完全对齐，防漂移。
    """
    if code.startswith(("68", "30")):
        return "kc_cy"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "main"


def zt_threshold(code: str) -> float:
    return {"main": 9.5, "kc_cy": 19.5, "bj": 29.5}[get_board(code)]


# ---- 响应解析（纯函数）----

def _parse_sina_kline(payload) -> list[dict]:
    """新浪 getKLineData 返回 [{day,open,close,high,low,volume}] → 统一为 date 字段。

    volume 缺失/空串容错为 0；非 list 载荷返回空。
    """
    if not isinstance(payload, list):
        return []
    out = []
    for k in payload:
        try:
            out.append({"date": k["day"], "open": float(k["open"]),
                        "close": float(k["close"]), "high": float(k["high"]),
                        "low": float(k["low"]), "volume": float(k.get("volume") or 0)})
        except (KeyError, ValueError, TypeError):
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
    try:
        r = _session.get(_SINA_KLINE_URL,
                         params={"symbol": sym, "scale": 240, "ma": "no", "datalen": days},
                         timeout=15)
        return _parse_sina_kline(r.json())
    except Exception:
        return []


def fetch_marketcap(code: str) -> tuple:
    sym = tencent_symbol(code)
    try:
        r = _session.get(f"https://qt.gtimg.cn/q={sym}", timeout=15)
        return _parse_qt(r.text)
    except Exception:
        return None, None
