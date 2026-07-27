# -*- coding: utf-8 -*-
"""共享请求 helper + 结果容器。对齐 fupan:屏蔽环境代理 + trust_env=False。"""
import os
import re
import requests

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

sess = requests.Session()
sess.trust_env = False
sess.headers.update({"Referer": "https://finance.sina.com.cn"})

SINA_HQ = "https://hq.sinajs.cn/list="


class FetchResult:
    """单维采集结果。ok=False 时 detail 写失败原因。"""
    def __init__(self, dim, ok=False, data=None, detail=""):
        self.dim = dim
        self.ok = ok
        self.data = data
        self.detail = detail


def sina_quote(codes):
    """拉新浪 hq.sinajs.cn 行情。返回 dict: code -> 原始字段 list。失败返回 {}。

    返回 dict 的 key 是 **bare code**(已剥新浪 var 名的 hq_str_ 前缀),
    与 config 代码常量一致,调用方可直接 raw.get(code)。例:请求 gb_ixic 时
    新浪返回 'var hq_str_gb_ixic="..."',本函数剥前缀后 key 存为 'gb_ixic'。
    """
    try:
        r = sess.get(SINA_HQ + ",".join(codes), timeout=15)
        r.encoding = "gbk"
        out = {}
        for line in r.text.splitlines():
            m = re.match(r'var\s+(\w+)="([^"]*)"', line.strip())
            if not m:
                continue
            code, payload = m.group(1), m.group(2)
            if code.startswith("hq_str_"):   # 新浪 var 名带 hq_str_ 前缀,统一剥掉返回 bare code
                code = code[7:]
            out[code] = payload.split(",") if payload else []
        return out
    except Exception:
        return {}


def proxy_get(url, proxy, headers=None, **kw):
    """Yahoo 等 fallback 用:显式走代理。失败返回 None。

    默认带浏览器 UA:Yahoo v8 chart API 拒绝 requests 默认 python-requests UA
    (2026-07-27 实测:不加 UA → ^VIX meta=None → VIX 永久缺;加 Mozilla UA 后
    regularMarketPrice 正常返回)。调用方传 headers 则合并覆盖。
    """
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"}
    if headers:
        h.update(headers)
    try:
        r = requests.get(url, proxies=proxy, timeout=20, headers=h, **kw)
        r.raise_for_status()
        return r
    except Exception:
        return None
