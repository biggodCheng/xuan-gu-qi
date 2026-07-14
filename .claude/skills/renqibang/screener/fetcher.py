"""数据获取层 — push2 明文接口补行业(f127) + 题材/概念(f129)。

榜单本体(加密)由 browser.py 用 Playwright 渲染;本模块只负责明文字段补全。
禁用本地代理(与 chuangxingao/zhongbaoyubao 一致)。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
})

PUSH2_URL = "https://push2.eastmoney.com/api/qt/stock/get"
FIELDS = "f57,f58,f127,f129"   # 代码 / 名称 / 行业 / 概念


def build_secid(code: str) -> str:
    """东方财富 secid:6 开头(沪)→'1'，其余(深/创业板/北交所)→'0'。"""
    prefix = "1" if code.startswith("6") else "0"
    return f"{prefix}.{code}"


def _request_push2(secid: str) -> dict:
    """请求 push2 stock/get，返回 json(失败返回 {})。可被测试 mock。"""
    params = {"secid": secid, "fields": FIELDS, "fltt": "2"}
    try:
        r = _session.get(PUSH2_URL, params=params, timeout=10)
        return r.json() or {}
    except Exception as e:
        print(f"push2 请求失败({secid}): {e}", flush=True)
        return {}


def fetch_industry_concepts(code: str) -> dict:
    """取一只股票的行业 + 概念 + 名称。失败/缺字段返回空(不抛)。"""
    data = (_request_push2(build_secid(code)) or {}).get("data") or {}
    industry = (data.get("f127") or "").strip()
    raw = (data.get("f129") or "").strip()
    concepts = [c.strip() for c in raw.split(",") if c.strip()]
    name = (data.get("f58") or "").strip()
    return {"industry": industry, "concepts": concepts, "name": name}


def fetch_industry_for_stocks(stocks: list, max_workers: int = 10) -> None:
    """并发为 stocks 每条就地补 industry / concepts / reason。"""
    codes = [s.get("code") for s in stocks if s.get("code")]
    result = {}

    def _one(code):
        return code, fetch_industry_concepts(code)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_one, c) for c in codes]
        for fut in as_completed(futs):
            try:
                code, info = fut.result()
                result[code] = info
            except Exception:
                continue

    for s in stocks:
        info = result.get(s.get("code"), {"industry": "", "concepts": [], "name": ""})
        s["industry"] = info["industry"]
        s["concepts"] = info["concepts"]
        s["reason"] = ",".join(info["concepts"])
        if not s.get("name"):               # DOM name 空 → 用 push2 f58 补
            s["name"] = info.get("name", "")
        s["rank_change"] = s.get("rank_change", "")
