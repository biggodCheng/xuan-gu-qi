"""数据获取层 — 东财行业板块资金流(push2delay clist)。

网络要点(同 renqibang/screener/fetcher.py):
  push2delay 直连(trust_env=False)会被服务端关连接; 必须跟随系统代理
  (trust_env=True), 用 http 非 https, 带浏览器 UA + Referer。
  偶发空响应, 带 RETRIES 退避重试。
"""
import re
import time

import requests

_session = requests.Session()
_session.trust_env = True
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})

CLIST_URL = "http://push2delay.eastmoney.com/api/qt/clist/get"
FS = "m:90+t:2+f:!50"
FIELDS = "f12,f14,f3,f62,f184,f66,f72"
RETRIES = 3
_SUF = re.compile(r"[ⅡⅢⅣⅤⅥ]")


def parse(row: dict) -> dict:
    """单条原始 dict → 统一结构(含 main_net_yi 亿元换算)。"""
    return {
        "code": row.get("f12", ""),
        "name": row.get("f14", ""),
        "change_pct": row.get("f3"),
        "main_net": row.get("f62"),
        "main_net_yi": round((row.get("f62") or 0) / 1e8, 2),
        "main_pct": row.get("f184"),
        "super_large_net": row.get("f66"),
        "large_net": row.get("f72"),
    }


def dedup(industries: list) -> list:
    """端内去重: 同行业多层级 BK 的 (main_net, main_pct) 相同, 合并为一个。

    同值多条中优先保留行业名不含罗马后缀(ⅡⅢⅣⅤⅥ)者(即一级名)。
    main_net 为 None(停牌/缺字段)的条目跳过。
    """
    best = {}
    for it in industries:
        if it.get("main_net") is None:
            continue
        key = (it["main_net"], it.get("main_pct"))
        cur = best.get(key)
        if cur is None or (_SUF.search(cur.get("name", "")) and not _SUF.search(it.get("name", ""))):
            best[key] = it
    return list(best.values())


def _request(po: int, pz: int) -> dict:
    """请求 clist, 返回原始 json(失败/重试耗尽返回 {})。可被测试 mock。"""
    params = {"pn": "1", "pz": str(pz), "po": str(po),
              "fid": "f62", "fs": FS, "fields": FIELDS, "fltt": "2"}
    for attempt in range(RETRIES):
        try:
            r = _session.get(CLIST_URL, params=params, timeout=15)
            return r.json() or {}
        except Exception as e:
            if attempt < RETRIES - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            print(f"push2delay 请求失败(po={po}): {e}", flush=True)
            return {}


def _diff_list(payload: dict) -> list:
    """从 clist 响应取 diff 列表(接口返回 dict, 按 .values() 取)。"""
    data = payload.get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        return list(diff.values())
    return list(diff)


def fetch_top_flows(per_end: int = 100) -> dict:
    """两端各取 Top per_end: po=1 降序(流入端) + po=0 升序(流出端)。

    各端 parse + dedup 后返回 {"inflow": [...], "outflow": [...]}。
    """
    inflow = dedup([parse(r) for r in _diff_list(_request(po=1, pz=per_end))])
    outflow = dedup([parse(r) for r in _diff_list(_request(po=0, pz=per_end))])
    return {"inflow": inflow, "outflow": outflow}
