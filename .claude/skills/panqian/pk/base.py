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
    """拉新浪 hq.sinajs.cn 行情。返回 dict: code -> 原始字段 list。失败返回 {}。"""
    try:
        r = sess.get(SINA_HQ + ",".join(codes), timeout=15)
        r.encoding = "gbk"
        out = {}
        for line in r.text.splitlines():
            m = re.match(r'var\s+(\w+)="([^"]*)"', line.strip())
            if not m:
                continue
            code, payload = m.group(1), m.group(2)
            out[code] = payload.split(",") if payload else []
        return out
    except Exception:
        return {}


def proxy_get(url, proxy, **kw):
    """Yahoo 等 fallback 用:显式走代理。失败返回 None。"""
    try:
        r = requests.get(url, proxies=proxy, timeout=20, **kw)
        r.raise_for_status()
        return r
    except Exception:
        return None
