# -*- coding: utf-8 -*-
"""全A股 code→name 映射 (展示用)。数据源: 新浪 Market_Center.getHQNodeData 全市场。

用途: 给"只有本地K线、无股票名称"的输出补股票名字 —— fupan 强势股/失败扫描
(本地 vipdoc 只有 OHLCV)、eval-stock 的 _SID 桥接不可用兜底。

进程内缓存, 单进程只拉一次; 拉取失败返回 {} (调用方退化为纯代码, 不阻断)。

注意: 与选股池(kangdie 等)不同, 本映射 **不过滤 st/新股** —— fupan 涨停/断板池
含 st 股与 N 新股, name 映射必须覆盖全市场, 否则这些票名字缺失。
"""
import os
import time

import requests

# 屏蔽代理, 直连新浪 (与 kangdie/fupan fetcher 一致)
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

_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
    "json_v2.php/Market_Center.getHQNodeData"
)

_cache = None  # None=未加载; dict=已加载(可能为空)


def load_name_map() -> dict:
    """返回 {code: name} 全市场映射。进程内缓存, 首次调用拉取(~15s)。失败返回 {}。"""
    global _cache
    if _cache is not None:
        return _cache
    m = {}
    page = 1
    per_page = 100
    while True:
        try:
            r = _session.get(_URL, params={
                "page": page, "num": per_page, "sort": "symbol",
                "asc": 1, "node": "hs_a", "_s_r_a": "auto",
            }, timeout=15)
            data = r.json()
        except Exception as e:
            print(f"  [WARN] 股票名称映射拉取失败(page={page}): {e}", flush=True)
            break
        if not data:
            break
        for item in data:
            code = item.get("code")
            name = item.get("name")
            if code and name:
                m[code] = name
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.2)
    if not m:
        print("  [WARN] 股票名称映射为空, 相关输出将退化为纯代码", flush=True)
    _cache = m
    return m


def name_of(code: str) -> str:
    """查单只股票名字, 找不到返回空串。"""
    return load_name_map().get(code, "")


def label(code: str) -> str:
    """行内展示用: 返回「名字(代码)」; name 缺失时退化为纯「代码」。

    用于 md/终端正文里夹带股票的行内场景(非表格)。表格场景请用单独的名称列。
    """
    nm = load_name_map().get(code)
    return f"{nm}({code})" if nm else code
