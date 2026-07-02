"""中报预报跟踪器 — 编排入口。

流程:CHECKPOINT → 加载 watchlist → 扫描新股入池 → skipped 移回 active 重试
     → 并发刷新 active 前复权日K + 算涨跌 → 刷新失败降级 skipped
     → 到期迁移 → 生成报告 → 写回 watchlist。

可注入 fetcher(测试用);默认用 screener.fetcher。
"""
import datetime
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

from screener import fetcher as _default_fetcher
from screener import storage
from screener.analyzer import (
    filter_announcements, build_daily, held_days, HOLD_DAYS,
)
from screener.reporter import render_report


def _refresh_one(code, notice_date, fetcher):
    """拉一只 active 股前复权日K,算 daily 与汇总字段。失败返回 (code, None)。"""
    kline = fetcher.get_kline_since(code, notice_date)
    if not kline:
        return code, None
    base_price = kline[0]["open"]
    base_date = kline[0]["date"]
    daily = build_daily(kline, base_price)
    last = daily[-1] if daily else {}
    hd = held_days(daily)
    return code, {
        "base_date": base_date, "base_price": base_price, "daily": daily,
        "last_close": last.get("close"), "chg_total": last.get("chg_total"),
        "chg_today": last.get("chg_today"), "held_days": hd,
        "remain_days": max(0, HOLD_DAYS - hd),
    }


def run(today_str=None, watchlist_path=None, output_dir=None, fetcher=None) -> bool:
    today_str = today_str or datetime.date.today().strftime("%Y-%m-%d")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    watchlist_path = watchlist_path or os.path.join(base_dir, "data", "watchlist.json")
    output_dir = output_dir or os.path.join(base_dir, "output")
    fetcher = fetcher or _default_fetcher

    start = time.time()
    report_path = os.path.join(output_dir, f"{today_str}.md")

    # 1. CHECKPOINT:今日报告已存在则提示(此处不阻断,仅提示)
    if os.path.exists(report_path):
        print(f"⚠️ 今日报告已存在:{report_path},将覆盖。", flush=True)

    # 2. 加载 watchlist
    pool = storage.load_watchlist(watchlist_path)
    print(f"[{today_str}] 跟踪池:活跃 {len(pool['active'])} / 到期 {len(pool['expired'])} "
          f"/ 待重试 {len(pool['skipped'])}", flush=True)

    # 3. 扫描新股(去重)
    existed = storage.existing_codes(pool)
    anns = fetcher.get_announcements()
    targets = filter_announcements(anns)
    new_items = [a for a in targets if a["code"] not in existed]
    new_codes = {a["code"] for a in new_items}
    for a in new_items:
        storage.add_active(pool, a)

    # 4. skipped 移回 active 重试(之前入池但K线拉取失败)
    reactivated = [s["code"] for s in pool["skipped"]]
    for s in list(pool["skipped"]):
        storage.add_active(pool, {"code": s["code"], "name": s.get("name", ""),
                                  "notice_date": s.get("notice_date", ""), "industry": ""})
        storage.remove_skipped(pool, s["code"])

    print(f"扫描预告 {len(anns)} 条,达标 {len(targets)},新增 {len(new_items)},"
          f"重试 skipped {len(reactivated)}", flush=True)

    # 5. 并发刷新全量 active(前复权覆盖式,保证口径一致)
    to_refresh = [(s["code"], s.get("notice_date") or "") for s in pool["active"]]
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(_refresh_one, c, nd, fetcher): c for c, nd in to_refresh}
        for fut in as_completed(futs):
            code, fields = fut.result()
            if fields is None:
                continue
            try:
                storage.refresh_active(pool, code, fields)
            except KeyError:
                pass

    # 6. 刷新失败的(daily 仍空)→ 降级 skipped;清出 active
    still_empty = [s for s in pool["active"] if not s.get("daily")]
    for s in still_empty:
        storage.add_skipped(pool, s["code"], s.get("name", ""),
                            s.get("notice_date", ""), "K线拉取失败")
    pool["active"] = [s for s in pool["active"] if s.get("daily")]

    # 7. 到期迁移
    expired_now = storage.migrate_expired(pool, HOLD_DAYS)

    # 8. 报告
    os.makedirs(output_dir, exist_ok=True)
    md = render_report(pool, today_str, new_codes, expired_now)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)

    # 9. 写回 watchlist
    storage.save_watchlist(pool, watchlist_path)

    print(f"完成:活跃 {len(pool['active'])} / 到期 {len(pool['expired'])} / "
          f"待重试 {len(pool['skipped'])},本次到期 {len(expired_now)},"
          f"耗时 {time.time()-start:.1f}s", flush=True)
    print(f"报告:{report_path}", flush=True)
    return True


if __name__ == "__main__":
    run()
