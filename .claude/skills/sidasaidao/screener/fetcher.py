"""获取股票的行业分类和概念板块数据。

数据源：
- 股票搜索：东方财富 searchapi（resolve 名称→代码）
- 行业 & 概念：新浪财经 HTML 页面解析

注意：push2.eastmoney.com 在部分网络环境下被阻断，
所以改用新浪财经的 HTML 页面来获取概念板块数据。
"""

import os
import re
import time

import requests

# 禁用代理，避免本地代理干扰
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

# 需要从概念列表中过滤的非概念条目
_NOISE_PATTERNS = {
    "所属行业板块", "备注：此为申万行业分类", "所属概念板块",
    "同概念板块", "概念板块", "行业板块",
    "同行业板块", "点击查看", "查看",
}


def search_stock(keyword: str) -> list[dict]:
    """通过关键词搜索股票，返回匹配列表。

    支持股票代码（如 600519）或名称（如 贵州茅台）。

    Returns:
        [{"code": "600519", "name": "贵州茅台", "market": "sh"}, ...]
    """
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
        for item in data.get("QuotationCodeTable", {}).get("Data", []):
            code = item.get("Code", "")
            name = item.get("Name", "")
            # 只保留 A 股（6/0/3/4/8 开头的纯数字代码）
            if not re.match(r"^[03468]\d{5}$", code):
                continue
            mkt = item.get("MktNum", "")
            if mkt == "1":
                market_tag = "sh"
            elif mkt == "0":
                market_tag = "sz"
            else:
                market_tag = "bj"
            results.append({
                "code": code,
                "name": name,
                "market": market_tag,
            })
        return results
    except Exception as e:
        print(f"搜索股票失败: {e}", flush=True)
        return []


def get_stock_detail(code: str) -> dict:
    """获取股票详细信息：行业 + 概念板块。

    通过新浪财经 HTML 页面解析获取。

    Returns:
        {
            "code": "002594",
            "name": "比亚迪",
            "industry": "乘用车",
            "concepts": ["新能源车", "锂电池", "储能", ...],
        }
    """
    # 确定新浪前缀
    prefix = _get_sina_prefix(code)

    # 获取股票名称（从行情接口）
    name = _get_stock_name(code)

    # 获取行业和概念板块（从新浪 HTML）
    industry, concepts = _parse_sina_page(code, prefix)

    return {
        "code": code,
        "name": name,
        "industry": industry,
        "concepts": concepts,
    }


def _get_sina_prefix(code: str) -> str:
    """新浪 API 的市场前缀。"""
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
        # 格式: var hq_str_sz002594="比亚迪,90.100,90.310,...";
        match = re.search(r'="([^,]+)', r.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""


def _parse_sina_page(code: str, prefix: str) -> tuple[str, list[str]]:
    """解析新浪财经 HTML 页面，提取行业和概念板块。

    Returns:
        (industry, concepts)
    """
    url = (
        f"https://vip.stock.finance.sina.com.cn/corp/go.php/"
        f"vCI_CorpOtherInfo/stockid/{code}/menuvtype/hqtype/hq.phtml"
    )
    try:
        r = _sina_session.get(url, timeout=15)
        r.encoding = "gb2312"
        text = r.text
    except Exception as e:
        print(f"获取新浪页面失败: {e}", flush=True)
        return "", []

    # ---- 提取行业 ----
    industry = ""
    # 策略1：找"所属行业板块"后面的第一个非噪声 td
    ind_start = text.find("所属行业板块")
    if ind_start != -1:
        chunk = text[ind_start:ind_start + 2000]
        tds = re.findall(r'<td[^>]*class="ct"[^>]*>([^<]+)</td>', chunk)
        for td in tds:
            td = td.strip()
            if td and td not in _NOISE_PATTERNS and len(td) >= 2:
                industry = td
                break

    # ---- 提取概念板块 ----
    concepts = []
    # 找"所属概念板块"之后的内容
    cpt_start = text.find("所属概念板块")
    if cpt_start == -1:
        cpt_start = text.find("概念板块")

    if cpt_start != -1:
        # 往后取足够长的文本
        chunk = text[cpt_start:cpt_start + 30000]
        # 提取 td 中 align=center 的概念名称
        raw_tds = re.findall(r'<td[^>]*class="ct"[^>]*>([^<]+)</td>', chunk)
        for td in raw_tds:
            td = td.strip()
            # 过滤噪声
            if (td
                    and td not in _NOISE_PATTERNS
                    and len(td) >= 2
                    and not td.startswith("备注")
                    and not td.startswith("同")
                    and "板块" not in td
                    and "行业" not in td):
                concepts.append(td)

    # 去重但保持顺序
    seen = set()
    unique_concepts = []
    for c in concepts:
        if c not in seen:
            seen.add(c)
            unique_concepts.append(c)

    return industry, unique_concepts


def resolve_stock_code(query: str) -> tuple[str, str]:
    """解析用户输入，返回 (股票代码, 股票名称)。

    支持以下输入格式：
    - 纯数字代码：600519, 002594
    - 带前缀代码：sh600519, sz002594
    - 股票名称：贵州茅台, 比亚迪

    Returns:
        (code, name) 或 (None, None) 如果未找到
    """
    query = query.strip()

    # 纯数字 → 直接作为代码
    if re.match(r"^[03468]\d{5}$", query):
        name = _get_stock_name(query)
        return query, name

    # 带前缀的代码
    m = re.match(r"^(sh|sz|bj)(\d{6})$", query, re.IGNORECASE)
    if m:
        code = m.group(2)
        name = _get_stock_name(code)
        return code, name

    # 按名称搜索
    results = search_stock(query)
    if results:
        # 精确匹配优先
        for r in results:
            if r["name"] == query:
                return r["code"], r["name"]
        # 否则返回第一个
        return results[0]["code"], results[0]["name"]

    return None, None
