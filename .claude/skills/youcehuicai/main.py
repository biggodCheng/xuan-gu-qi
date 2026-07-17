"""右侧趋势回踩 — 大盘企稳(三指站稳MA20)时，扫"上涨趋势缩量回踩MA10/MA20"的标的。

回踩策略在上涨市的正确用法（区别于下跌市失效的 suolianghuicai）。
独立运行（不吃上游输入）：python main.py
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from screener.bridges import (
    get_all_stocks_today,
    get_stock_kline,
    get_market_cap_map,
    get_index_kline,
)
from screener.analyzer import (
    MARKET_CAP_MIN,
    MARKET_CAP_MAX,
    market_stabilized,
    is_right_side_pullback,
)
from screener.storage import save_results

_INDEXES = {"上证指数": "sh000001", "沪深300": "sh000300", "创业板指": "sz399006"}
_INDEX_DAYS = 60
_STOCK_KLINE_DAYS = 70
_MAX_WORKERS = 20


def run_screener(output_dir: str | None = None) -> bool:
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    start = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"[{date_str}] 右侧趋势回踩扫描启动...", flush=True)

    # ---- Step 1: 企稳门控（三指站稳MA20）----
    print("拉取指数判定企稳...", flush=True)
    idx_map = {name: get_index_kline(sym, days=_INDEX_DAYS) for name, sym in _INDEXES.items()}
    stabilized, details = market_stabilized(idx_map)
    above_cnt = sum(1 for d in details if d.get("above_ma20"))
    print(f"  企稳判定：{above_cnt}/{len(details)} 指站上MA20。", flush=True)

    if not stabilized:
        below = [d["name"] for d in details if not d.get("above_ma20")]
        print(
            f"  大盘未企稳（{','.join(below)} 仍跌破MA20），右侧回踩不适用。",
            flush=True,
        )
        save_results(
            date_str, [], output_dir,
            trigger={"stabilized": False, "above": above_cnt, "total": len(details)},
        )
        print(f"  已写空结果到 yc_{date_str}.json（count=0）。", flush=True)
        return True

    print(f"  [企稳] 三指站稳MA20，启动右侧回踩扫描。", flush=True)
    trigger = {"stabilized": True, "above": above_cnt, "total": len(details)}

    # ---- Step 2: 全A行情 + 市值过滤 ----
    print("获取全A股行情...", flush=True)
    stocks_df = get_all_stocks_today()
    if stocks_df.empty:
        print("  未获取到行情数据，可能是非交易日。", flush=True)
        save_results(date_str, [], output_dir, trigger=trigger)
        return False
    stocks = stocks_df.to_dict("records")
    print(f"  共 {len(stocks)} 只。", flush=True)

    print("获取全A市值数据...", flush=True)
    cap_map = get_market_cap_map()
    cap_filtered = []
    for s in stocks:
        cap = cap_map.get(s["code"])
        if cap and MARKET_CAP_MIN <= cap <= MARKET_CAP_MAX:
            s["market_cap"] = round(cap, 2)
            cap_filtered.append(s)
    print(
        f"  市值[{MARKET_CAP_MIN}-{MARKET_CAP_MAX}]亿过滤后 {len(cap_filtered)}/{len(stocks)} 只。",
        flush=True,
    )
    if not cap_filtered:
        save_results(date_str, [], output_dir, trigger=trigger)
        return True

    # ---- Step 3: 并发拉个股 OHLCV ----
    print(f"并发拉取个股 {_STOCK_KLINE_DAYS} 日OHLCV（{_MAX_WORKERS}线程）...", flush=True)
    klines_map: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(get_stock_kline, s["code"], _STOCK_KLINE_DAYS): s["code"]
            for s in cap_filtered
        }
        done = 0
        total = len(cap_filtered)
        for future in as_completed(futures):
            code = futures[future]
            try:
                klines_map[code] = future.result()
            except Exception:
                pass
            done += 1
            if done % 500 == 0:
                print(f"  OHLCV 已拉取 {done}/{total}...", flush=True)
    print(f"  OHLCV 拉取完成（{len(klines_map)} 只有数据）。", flush=True)

    # ---- Step 4: 右侧回踩判定 ----
    candidates = []
    for s in cap_filtered:
        bars = klines_map.get(s["code"], [])
        detail = is_right_side_pullback(bars, s["market_cap"])
        if detail:
            candidates.append({
                "code": s["code"],
                "name": s["name"],
                "close": s["close"],
                **detail,
            })
    print(f"  右侧回踩信号通过：{len(candidates)} 只。", flush=True)

    # ---- Step 5: 保存 ----
    save_results(date_str, candidates, output_dir, trigger=trigger)

    elapsed = time.time() - start
    print(
        f"完成！右侧回踩 {len(candidates)} 只，耗时 {elapsed:.0f} 秒。"
        f"结果：{os.path.join(output_dir, f'yc_{date_str}.json')}",
        flush=True,
    )
    print(
        "  纪律：买点=回踩均线缩量，止损=破MA20(stop_loss字段)，"
        "止盈=破MA10或加速后跟踪止盈。",
        flush=True,
    )
    return True


if __name__ == "__main__":
    run_screener()
