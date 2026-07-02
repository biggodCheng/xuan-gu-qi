"""数据获取层 — 业绩预告扫描 + 前复权日K + 名称解析。

数据源:
- 业绩预告:东方财富 datacenter-web(字段名见顶部常量,经 probe_yjyg.py 实测)
- 前复权日K:腾讯 fqkline(失败返回空 → 上游标 skipped,无新浪回退因其无 open)
- 股票搜索:东方财富 searchapi

禁用本地代理,避免干扰(与 q2zhanwang/chuangxingao 一致)。
"""
import os

import requests

# === 业绩预告接口(经 probe_yjyg.py 实测;若字段名不同仅改这里)===
YJYG_REPORT_NAME = "RPT_PUBLIC_OP_PREDICT"
FLD_CODE = "SECURITY_CODE"
FLD_NAME = "SECURITY_NAME_ABBR"
FLD_INDUSTRY = "PUBLISHNAME"
FLD_NOTICE_DATE = "NOTICE_DATE"
FLD_REPORT_DATE = "REPORTDATE"
FLD_PREDICT_TYPE = "FORECASTTYPE"        # 值含"预增"
FLD_YOY_LOWER = "INCREASEL"              # 同比下限 %
FLD_YOY_UPPER = "INCREASET"              # 同比上限 %

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


def get_kline_since(code: str, since_date: str) -> list[dict]:
    """取 since_date 之后的前复权日K(腾讯),返回 [{date,open,close},...] 正序。

    since_date 当天排除(预告公告日 → 取其后首个交易日为基准日)。
    腾讯失败/无数据 → 返回 [](上游据此标 skipped)。
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


def _request_announcements(report_date: str, page: int) -> tuple[dict, bool]:
    """请求业绩预告一页,返回 (json, success)。"""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "sortColumns": FLD_NOTICE_DATE,
        "sortTypes": "-1",
        "pageSize": "100",
        "pageNumber": str(page),
        "reportName": YJYG_REPORT_NAME,
        "columns": "ALL",
        "filter": f"({FLD_REPORT_DATE}='{report_date}')",
    }
    try:
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        return data, bool(data.get("success"))
    except Exception as e:
        print(f"业绩预告请求失败(page {page}): {e}", flush=True)
        return {}, False


def _to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_announcements(report_date: str = "2026-06-30", predict_type: str = "预增",
                      yoy_lower_min: float = 50.0) -> list[dict]:
    """扫描全A某报告期的业绩预告,返回已按类型过滤的原始条目(幅度门槛由 analyzer 再筛)。

    返回 [{"code","name","industry","notice_date","predict_type","yoy_lower","yoy_upper"}]
    分页拉满(每页 100)。类型≠predict_type 的条目不返回。
    """
    out = []
    page = 1
    while True:
        data, ok = _request_announcements(report_date, page)
        if not ok:
            break
        rows = (data.get("result") or {}).get("data") or []
        if not rows:
            break
        for row in rows:
            if (row.get(FLD_PREDICT_TYPE) or "") != predict_type:
                continue
            out.append({
                "code": row.get(FLD_CODE),
                "name": row.get(FLD_NAME),
                "industry": row.get(FLD_INDUSTRY, ""),
                "notice_date": (row.get(FLD_NOTICE_DATE) or "")[:10],
                "predict_type": predict_type,
                "yoy_lower": _to_float(row.get(FLD_YOY_LOWER)),
                "yoy_upper": _to_float(row.get(FLD_YOY_UPPER)),
            })
        if len(rows) < 100:
            break
        page += 1
        if page > 20:  # 安全上限(2000 条)
            break
    return out
