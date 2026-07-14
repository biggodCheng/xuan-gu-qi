"""榜单抓取层 — Playwright 渲染东方财富股吧人气榜 + DOM 解析。

榜单接口返回 AES 密文(window.d() 解密),纯 Python 逆向不可行,
改由 Playwright 渲染页面让浏览器自动解密,直接读 DOM。

selector/列顺序经 probe_rank.py 实测(2026-07-14);前端改版会导致失效,
失效时重跑 probe_rank.py 修正。

DOM 列结构(每行 ≥10 个 td,经 2026-07-14 联调修正):
  td0=rank(前3空) td1=rank_change td2=历史趋势 td3=code td4=热帖摘要(非名称!)
  ... td9=新晋%/铁杆%
注:td[4] 实为"热门帖子标题+讨论数+浏览+摘要"列(probe 误判为名称);
榜单 DOM 不含股票名称,name 全部由 fetcher push2 f58 补。
榜单无独立热度值列 → 人气即 rank; popularity 取 td9 新晋粉丝%。
"""
import re

# === 经 probe_rank.py 实测的 selector ===
RANK_URL = "https://guba.eastmoney.com/rank/"
RANK_ROW_SELECTOR = "table tbody tr"
RANK_CELL_SELECTOR = "td"
NEXT_PAGE_SELECTOR = "a:has-text('下一页')"
HOT_TAB_SELECTOR = ""   # 默认 tab 即热度榜(.ranktit.hotrank.active)

# === 列索引(经 probe_rank.py + 2026-07-14 联调修正)===
IDX_CHG = 1    # rank_change
IDX_CODE = 3
IDX_FANS = 9   # 新晋% / 铁杆%
# 注:无 IDX_NAME — td[4] 是热帖摘要列非名称,name 全部由 fetcher push2 f58 补。

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
    name 留空(""):DOM 不含名称(td[4] 是热帖摘要), 由 fetcher push2 f58 补。
    popularity 取 td[IDX_FANS] 第一个百分比(新晋粉丝%, 榜单无独立热度值)。
    解析不出 6 位代码 → None(跳过表头/噪声行)。
    """
    if not cells or len(cells) <= IDX_CODE:
        return None
    code_cell = str(cells[IDX_CODE])
    m = _CODE_RE.search(code_cell)
    if not m:
        return None
    rank_change = str(cells[IDX_CHG]).strip() if len(cells) > IDX_CHG else ""
    popularity = _first_percent(cells[IDX_FANS]) if len(cells) > IDX_FANS else None
    return {
        "rank": base_rank,
        "code": m.group(1),
        "name": "",   # DOM 无名称, fetcher push2 f58 补
        "popularity": popularity,
        "rank_change": rank_change,
    }


def _row_cells(row_locator) -> list:
    """取一行的 td 文本列表（每项 strip）。"""
    return [c.strip() for c in row_locator.locator(RANK_CELL_SELECTOR).all_text_contents()]


def fetch_top100(sort: str = "热度榜", headless: bool = True, max_pages: int = 8) -> list:
    """Playwright 渲染东方财富人气榜，ajax 翻页取 Top100。

    返回 list[{rank, code, name, popularity, rank_change}]（不足 100 取实际条数）。
    rank 用累计序号(榜单已按 rank 排序)。按 code 去重。HOT_TAB_SELECTOR 非空时先点 tab
    (当前默认即热度榜，留空则跳过)。
    """
    from playwright.sync_api import sync_playwright

    stocks = []
    seen = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(RANK_URL, wait_until="domcontentloaded", timeout=30000)

        # 切到热度榜(若需要)
        if HOT_TAB_SELECTOR:
            try:
                page.locator(HOT_TAB_SELECTOR).first.click()
                page.wait_for_timeout(1500)
            except Exception:
                pass

        # 等 JS 解密 + 渲染
        page.wait_for_selector(RANK_ROW_SELECTOR, timeout=20000)
        page.wait_for_timeout(3000)

        for _ in range(max_pages):
            if len(stocks) >= 100:
                break
            rows = page.locator(RANK_ROW_SELECTOR).all()
            for row in rows:
                if len(stocks) >= 100:
                    break
                try:
                    cells = _row_cells(row)
                except Exception:
                    continue
                base_rank = len(stocks) + 1
                one = parse_one(cells, base_rank)
                if not one or one["code"] in seen:
                    continue
                seen.add(one["code"])
                stocks.append(one)

            if len(stocks) >= 100:
                break
            # 翻下一页(ajax)
            if not NEXT_PAGE_SELECTOR:
                break
            try:
                btn = page.locator(NEXT_PAGE_SELECTOR).first
                if btn.count() == 0:
                    break
                btn.click()
                page.wait_for_selector(RANK_ROW_SELECTOR, timeout=15000)
                page.wait_for_timeout(2000)
            except Exception:
                break

        browser.close()
    return stocks[:100]
