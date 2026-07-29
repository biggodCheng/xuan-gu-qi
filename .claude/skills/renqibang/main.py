"""人气榜 — 编排入口。

流程:CHECKPOINT(防覆盖) → Playwright 渲染榜单取 Top100 → 并发补行业/题材/名称
     → 存 popularity_<date>.json → 终端打印 markdown 摘要。

可注入 browser/fetcher(测试用);默认用 screener.browser / screener.fetcher。
"""
import datetime
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

# Windows 中文控制台默认 GBK(cp936) 编不出 emoji(⚠️), print 会 UnicodeEncodeError;
# 统一 stdout/stderr 用 utf-8(失败则忽略, 不阻断)。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from screener import browser as _default_browser
from screener import fetcher as _default_fetcher
from screener.storage import save_results

SORT = "热度榜"


def _print_summary(stocks: list, date_str: str) -> None:
    """终端打印 markdown 摘要:Top10 + 行业分布 + 热门题材。"""
    print(f"\n# 人气榜快照 · {date_str}（东方财富·{SORT}）")
    print(f"共 {len(stocks)} 只 | 来源：guba.eastmoney.com/rank")
    print("（popularity = 新晋粉丝%；榜单无独立热度值，热度以排名体现）\n")

    print("## Top 10")
    print("| 排名 | 代码 | 名称 | 行业 | 新晋粉丝% | 变动 | 题材 |")
    print("|---|---|---|---|---|---|---|")
    for s in stocks[:10]:
        pop = s.get("popularity")
        pop_s = f"{pop}" if pop is not None else "-"
        print(f"| {s.get('rank')} | {s.get('code')} | {s.get('name')} | "
              f"{s.get('industry', '')} | {pop_s} | "
              f"{s.get('rank_change', '')} | {s.get('reason', '')} |")

    ind_cnt = Counter(s.get("industry") for s in stocks if s.get("industry"))
    print("\n## 行业分布（Top 5）")
    print("| 行业 | 数量 |")
    print("|---|---|")
    for ind, n in ind_cnt.most_common(5):
        print(f"| {ind} | {n} |")

    conc_cnt = Counter()
    for s in stocks:
        for c in s.get("concepts", []):
            conc_cnt[c] += 1
    print("\n## 热门题材（Top 8，按出现频次）")
    print("| 题材 | 出现次数 |")
    print("|---|---|")
    for c, n in conc_cnt.most_common(8):
        print(f"| {c} | {n} |")


def run(today_str: str | None = None, output_dir: str | None = None,
        browser=None, fetcher=None) -> bool:
    today_str = today_str or datetime.date.today().strftime("%Y-%m-%d")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = output_dir or os.path.join(base_dir, "data")
    browser = browser or _default_browser
    fetcher = fetcher or _default_fetcher

    # 1. CHECKPOINT:今日快照已存在→提示覆盖
    path = os.path.join(output_dir, f"popularity_{today_str}.json")
    if os.path.exists(path):
        print(f"⚠️ 今日人气榜快照已存在:{path},将覆盖。", flush=True)

    # 2. 渲染榜单取 Top100
    print(f"[{today_str}] Playwright 渲染东方财富人气榜({SORT})...", flush=True)
    stocks = browser.fetch_top100(sort=SORT, headless=True)
    print(f"榜单获取完成:{len(stocks)} 只", flush=True)
    if not stocks:
        print("⚠️ 未获取到榜单数据(可能页面改版或网络异常)", flush=True)

    # 3. 并发补行业 + 题材 + 名称(push2)
    if stocks:
        print("并发补行业/题材/名称(push2)...", flush=True)
        fetcher.fetch_industry_for_stocks(stocks, max_workers=10)

    # 4. 保存
    saved = save_results(today_str, SORT, stocks, output_dir)
    print(f"已保存:{saved}", flush=True)

    # 5. 摘要
    _print_summary(stocks, today_str)
    return True


if __name__ == "__main__":
    run()
