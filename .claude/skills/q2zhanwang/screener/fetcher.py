"""数据获取层 — 解析股票代码 + 拉取财报数据。

数据源:
- 股票搜索:东方财富 searchapi(名称→代码)
- 股票名称:新浪行情接口
- 财报数据:东方财富 datacenter 业绩报表(RPT_LICO_FN_CPD,累计口径)

注意:push2.eastmoney.com 在部分网络被阻断,改用 datacenter-web(已验证可达)。
禁用本地代理,避免干扰。
"""

import os
import re

import requests

# 禁用代理,避免本地代理干扰
for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_search_session = requests.Session()
_search_session.trust_env = False
_search_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
})

_sina_session = requests.Session()
_sina_session.trust_env = False
_sina_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
})

_finance_session = requests.Session()
_finance_session.trust_env = False
_finance_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})


def search_stock(keyword: str) -> list[dict]:
    """通过关键词搜索股票,返回匹配列表(仅 A 股)。"""
    url = "https://searchapi.eastmoney.com/api/suggest/get"
    params = {
        "input": keyword,
        "type": "14",  # A 股
        "token": "D43BF722C8E33BDC906FB84D85E326E8",
        "count": "10",
    }
    try:
        r = _search_session.get(url, params=params, timeout=10)
        data = r.json()
        results = []
        # Data 字段搜不到时可能为 null,用 or [] 兜底
        table = data.get("QuotationCodeTable") or {}
        for item in (table.get("Data") or []):
            code = item.get("Code", "")
            name = item.get("Name", "")
            # 只保留 A 股(6/0/3/4/8 开头的纯数字代码)
            if not re.match(r"^[03468]\d{5}$", code):
                continue
            results.append({"code": code, "name": name})
        return results
    except Exception as e:
        print(f"搜索股票失败: {e}", flush=True)
        return []


def _get_sina_prefix(code: str) -> str:
    """新浪行情接口的市场前缀。"""
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8")):
        return "bj"
    return "sz"


def _get_stock_name(code: str) -> str:
    """通过新浪行情接口获取股票名称。"""
    prefix = _get_sina_prefix(code)
    symbol = f"{prefix}{code}"
    url = f"https://hq.sinajs.cn/list={symbol}"
    try:
        r = _sina_session.get(url, timeout=10)
        r.encoding = "gbk"
        # 格式: var hq_str_sz002594="比亚迪,90.100,...";
        match = re.search(r'="([^,]+)', r.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""


def resolve_stock_code(query: str) -> tuple[str, str]:
    """解析用户输入,返回 (股票代码, 股票名称)。

    支持纯数字代码(600519)、带前缀代码(sh600519)、股票名称(比亚迪)。
    """
    query = query.strip()

    if re.match(r"^[03468]\d{5}$", query):
        name = _get_stock_name(query)
        return query, name

    m = re.match(r"^(sh|sz|bj)(\d{6})$", query, re.IGNORECASE)
    if m:
        code = m.group(2)
        name = _get_stock_name(code)
        return code, name

    results = search_stock(query)
    if results:
        for r in results:
            if r["name"] == query:
                return r["code"], r["name"]
        return results[0]["code"], results[0]["name"]

    return None, None


def get_financial(code: str, periods: int = 9) -> dict:
    """获取近 N 期财报(累计口径)。

    Args:
        code: 股票代码
        periods: 取最近几期(默认 9,覆盖 2024Q1~2026Q1,够算单季化与势头)

    Returns:
        {
            "code": "002594",
            "name": "比亚迪",
            "industry": "乘用车",
            "reports": [
                {
                    "report_date": "2026-03-31",
                    "qdate": "2026Q1",
                    "year": 2026, "quarter": 1,
                    "revenue": 150225314000.0,        # 累计,元
                    "parent_netprofit": 4084551000.0, # 累计,元
                    "gross_margin": 18.81,            # 毛利率 %
                },
                ...按报告期倒序
            ],
        }
    """
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "sortColumns": "REPORTDATE",
        "sortTypes": "-1",
        "pageSize": str(periods),
        "pageNumber": "1",
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
    }
    try:
        r = _finance_session.get(url, params=params, timeout=15)
        data = r.json()
    except Exception as e:
        print(f"获取财报失败: {e}", flush=True)
        return {"code": code, "name": "", "industry": "", "reports": []}

    if not data.get("success"):
        return {"code": code, "name": "", "industry": "", "reports": []}

    rows = (data.get("result") or {}).get("data") or []
    reports = []
    for row in rows:
        report_date = (row.get("REPORTDATE") or "")[:10]
        qdate = row.get("QDATE") or ""
        year, quarter = _parse_year_quarter(report_date)
        reports.append({
            "report_date": report_date,
            "qdate": qdate,
            "year": year,
            "quarter": quarter,
            "revenue": _to_float(row.get("TOTAL_OPERATE_INCOME")),
            "parent_netprofit": _to_float(row.get("PARENT_NETPROFIT")),
            "gross_margin": _to_float(row.get("XSMLL")),
        })

    name = rows[0].get("SECURITY_NAME_ABBR", "") if rows else ""
    industry = rows[0].get("PUBLISHNAME", "") if rows else ""

    return {"code": code, "name": name, "industry": industry, "reports": reports}


def _parse_year_quarter(report_date: str) -> tuple[int, int]:
    """从 '2026-03-31' 返回 (2026, 1)。无法解析返回 (0, 0)。"""
    try:
        y, m, _ = report_date.split("-")
        return int(y), (int(m) - 1) // 3 + 1  # 3→1, 6→2, 9→3, 12→4
    except Exception:
        return 0, 0


def _to_float(v) -> float | None:
    """安全转 float,None/空保持 None。"""
    if v is None:
        return None
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None
