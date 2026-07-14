"""东方财富股吧人气榜渲染后 DOM 探测/排障工具。

榜单接口返回 AES 加密密文, 前端 JS 解密后渲染成 table. 本脚本用 Playwright
渲染页面, 直接读 DOM, 用于:
  1. 校验 selector / 列顺序是否仍有效 (前端改版后排障)
  2. 查看 rank/rank_change/name 等字段的实际渲染值

用法:
  cd .claude/skills/renqibang
  PYTHONUTF8=1 python probe_rank.py            # 默认等待 5s, 探测首页 + 翻页
  PYTHONUTF8=1 python probe_rank.py 8000       # 加长等待

DOM 结构要点 (2026-07-14 探测确认):
  - 行 selector: table tbody tr  (等价 .rank_table tbody tr), 每页 20 行, 共 5 页
  - 单元格 selector: td (每行 10 个; 表头 11 个 th, 新晋/铁杆粉丝合并末列)
  - td[0]=rank      rank1/2/3 文本空(看 b.icon_rank1/2/3), rank>=4 数字文本
  - td[1]=rank_change 文本自带符号('52'/'-2'), int(text) 可直接解析
  - td[3]=code      纯数字, 可靠
  - td[4]=name      DOM 为空(二次 quote 填充, 实测不填) -> 须 push2 f58 补
  - td[9]=新晋%/铁杆% 合并, 'left%\\nright%'
  - 默认 tab 即 人气榜(.ranktit.hotrank.active); 飙升榜=.ranktit.rankup
  - 翻页 ajax 不跳 URL, 点 a:has-text('下一页') 刷新表格; 页码 a.go_page
"""
import sys

from playwright.sync_api import sync_playwright

URL = "https://guba.eastmoney.com/rank/"
ROW_SEL = "table tbody tr"


def _icon_classes(el):
    try:
        return el.locator("b").evaluate_all("els => els.map(e => e.className)")
    except Exception:
        return []


def _parse_rank(td0, row_idx):
    """rank 解析: icon_rankN > 文本数字 > 行序号(表格已按 rank 排序)。"""
    txt = td0.inner_text().strip()
    if txt.isdigit():
        return txt, "text"
    for cls in _icon_classes(td0):
        for tok in cls.split():
            if tok.startswith("icon_rank") and tok[9:].isdigit():
                return tok[9:], "icon"
    return str(row_idx + 1), "idx"


def dump_page(page, label=""):
    n = page.locator(ROW_SEL).count()
    print(f"\n===== {label} 数据行 {n} (url={page.url}) =====")
    if not n:
        print("  (无数据行 — 可能等待不足或 selector 失效)")
        return
    print(f"{'i':>3} {'rank':>5} {'src':>4} {'chg':>5} {'code':<8} {'name':<10} fans(L/R)")
    for ri in range(n):
        row = page.locator(ROW_SEL).nth(ri)
        tds = row.locator("td")
        td0, td1 = tds.nth(0), tds.nth(1)
        rank, src = _parse_rank(td0, ri)
        chg = td1.inner_text().strip()
        code = tds.nth(3).inner_text().strip()
        name = tds.nth(4).inner_text().strip().split("\n")[0]
        fans = tds.nth(9).inner_text().strip().replace("\n", "/") if tds.count() > 9 else ""
        print(f"{ri:>3} {rank:>5} {src:>4} {chg:>5} {code:<8} {name:<10} {fans}")


def probe(wait_ms: int = 5000):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"goto {URL} (wait {wait_ms}ms)", flush=True)
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(wait_ms)
        print("title:", page.title())

        dump_page(page, "首页")

        # tab 状态
        print("\n===== tab 状态 =====")
        for sel, name in [(".ranktit.hotrank", "人气榜"), (".ranktit.rankup", "飙升榜")]:
            cls = page.locator(sel).first.evaluate("e => e.className") if page.locator(sel).count() else "(无)"
            print(f"  {name} {sel}: {cls}  -> active={'active' in cls}")

        # 首行逐格 raw (排障用)
        print("\n===== 首行逐格 raw td =====")
        if page.locator(ROW_SEL).count():
            first = page.locator(ROW_SEL).first
            for i in range(first.locator("td").count()):
                cell = first.locator("td").nth(i)
                print(f"  td[{i}]: text={cell.inner_text().strip()!r}")

        # 翻页 (ajax)
        print("\n===== 翻页实测 (ajax) =====")
        before_url = page.url
        try:
            nxt = page.locator("a:has-text('下一页')")
            if nxt.count():
                nxt.first.click(timeout=5000)
                page.wait_for_timeout(3000)
                same = (page.url == before_url)
                print(f"  点击后 url{'未变(ajax)' if same else '已变: ' + page.url}")
                dump_page(page, "第2页")
            else:
                print("  未找到 '下一页' 按钮")
        except Exception as e:
            print(f"  翻页失败: {e}")

        browser.close()


if __name__ == "__main__":
    wait = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    probe(wait_ms=wait)
