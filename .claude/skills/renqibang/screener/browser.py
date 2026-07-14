"""榜单抓取层 — Playwright 渲染东方财富股吧人气榜 + DOM 解析。

榜单接口返回 AES 密文(window.d() 解密),纯 Python 逆向不可行,
改由 Playwright 渲染页面让浏览器自动解密,直接读 DOM。

selector/列顺序经 probe_rank.py 实测(2026-07-14);前端改版会导致失效,
失效时重跑 probe_rank.py 修正。

DOM 列结构(每行 10 个 td):
  td0=rank(前3空) td1=rank_change td2=历史趋势 td3=code td4=name(DOM空)
  td5=链接 td6-8=价格 td9=新晋%/铁杆%
榜单无独立热度值列 → 人气即 rank; popularity 取 td9 新晋粉丝%。
"""
import re

# === 经 probe_rank.py 实测的 selector ===
RANK_URL = "https://guba.eastmoney.com/rank/"
RANK_ROW_SELECTOR = "table tbody tr"
RANK_CELL_SELECTOR = "td"
NEXT_PAGE_SELECTOR = "a:has-text('下一页')"
HOT_TAB_SELECTOR = ""   # 默认 tab 即热度榜(.ranktit.hotrank.active)

# === 列索引(经 probe_rank.py 实测)===
IDX_CHG = 1    # rank_change
IDX_CODE = 3
IDX_NAME = 4   # DOM 文本为空, 后续由 fetcher push2 f58 补
IDX_FANS = 9   # 新晋% / 铁杆%

_CODE_RE = re.compile(r"(\d{6})")
_PCT_RE = re.compile(r"([\d.]+)\s*%")


def _first_percent(text, default=None):
    """取文本里第一个百分比数值,无则 default。"""
    m = _PCT_RE.search(str(text))
    return float(m.group(1)) if m else default


def parse_one(cells: list, base_rank: int):
    """一行 td 文本列表 → {rank, code, name, popularity, rank_change}。

    rank 用 base_rank(榜单已按 rank 排序, 前3名 DOM 文本空, 用序号最可靠)。
    code 取 td[IDX_CODE] 中的 6 位数字(允许含前缀如 SH600000)。
    name 取 td[IDX_NAME] 文本(DOM 通常为空, 由 fetcher 后续补)。
    popularity 取 td[IDX_FANS] 第一个百分比(新晋粉丝%, 榜单无独立热度值)。
    解析不出 6 位代码 → None(跳过表头/噪声行)。
    """
    if not cells or len(cells) <= IDX_CODE:
        return None
    code_cell = str(cells[IDX_CODE])
    m = _CODE_RE.search(code_cell)
    if not m:
        return None
    name = str(cells[IDX_NAME]).strip() if len(cells) > IDX_NAME else ""
    rank_change = str(cells[IDX_CHG]).strip() if len(cells) > IDX_CHG else ""
    popularity = _first_percent(cells[IDX_FANS]) if len(cells) > IDX_FANS else None
    return {
        "rank": base_rank,
        "code": m.group(1),
        "name": name,
        "popularity": popularity,
        "rank_change": rank_change,
    }
