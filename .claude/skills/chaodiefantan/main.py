"""超跌反弹 — 扫全A找"近5日急跌 + T-1日缩量长下影 + T日放量阳包阴"的标的。

捕捉超跌后资金进场的反抽信号。左侧短线，严止损（破T-1最低）。
独立运行（不吃上游输入）：python main.py
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from screener.bridges import (
    get_all_stocks_today, get_stock_kline, get_market_cap_map, get_index_kline)
from screener.analyzer import is_oversold_rebound
from screener.market_filter import is_market_crash, INDICES
from screener.storage import save_results

_STOCK_KLINE_DAYS = 70  # 满足 5 日跌幅 + 长下影 + 均量判定
_MAX_WORKERS = 20


def run_screener(output_dir: str | None = None) -> bool:
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    start = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"[{date_str}] 超跌反弹扫描启动...", flush=True)

    # ---- 大盘环境开关(宽松:仅排除三指数同步加速阴跌段) ----
    print("检查大盘环境...", flush=True)
    index_klines = {}
    for sym, _name in INDICES:
        try:
            index_klines[sym] = get_index_kline(sym, 30)
        except Exception:
            pass
    if is_market_crash(index_klines):
        print("  ⚠️ 三大指数同步加速阴跌(空头排列+缩量),跳过扫描(下跌市禁做)。", flush=True)
        save_results(date_str, [], output_dir,
                     trigger={"signal": "oversold_rebound", "market_crash": True})
        return False
    print("  大盘非加速阴跌,继续扫描。", flush=True)

    # ---- 全A行情 ----
    print("获取全A股行情...", flush=True)
    stocks_df = get_all_stocks_today()
    if stocks_df.empty:
        print("  未获取到行情数据，可能是非交易日。", flush=True)
        save_results(date_str, [], output_dir, trigger={"error": "no_market_data"})
        return False
    stocks = stocks_df.to_dict("records")
    print(f"  共 {len(stocks)} 只。", flush=True)

    # ---- 市值(展示用,不做过滤) ----
    print("获取全A市值数据(展示用,不过滤)...", flush=True)
    cap_map = get_market_cap_map()
    for s in stocks:
        cap = cap_map.get(s["code"])
        if cap:
            s["market_cap"] = round(cap, 2)
    print(
        f"  全A {len(stocks)} 只(已过滤 ST/*ST/新股,退市不在列表),不卡市值。",
        flush=True,
    )

    # ---- 并发拉个股 OHLCV ----
    print(f"并发拉取个股 {_STOCK_KLINE_DAYS} 日OHLCV（{_MAX_WORKERS}线程）...", flush=True)
    klines_map: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(get_stock_kline, s["code"], _STOCK_KLINE_DAYS): s["code"]
            for s in stocks
        }
        done = 0
        total = len(stocks)
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

    # ---- 超跌反弹判定(不卡市值) ----
    candidates = []
    for s in stocks:
        bars = klines_map.get(s["code"], [])
        detail = is_oversold_rebound(bars, s.get("market_cap"))
        if detail:
            candidates.append({
                "code": s["code"],
                "name": s["name"],
                "close": s["close"],
                "market_cap": s.get("market_cap"),
                **detail,
            })
    print(f"  超跌反弹信号通过：{len(candidates)} 只。", flush=True)

    # ---- 保存 ----
    save_results(date_str, candidates, output_dir, trigger={"signal": "oversold_rebound"})

    elapsed = time.time() - start
    print(
        f"完成！超跌反弹 {len(candidates)} 只，耗时 {elapsed:.0f} 秒。"
        f"结果：{os.path.join(output_dir, f'cj_{date_str}.json')}",
        flush=True,
    )
    print(
        "  纪律：止损=破T-1最低(stop_loss字段)，止盈+5-8%，仓位<=10%，"
        "反弹是兑现窗口不恋战。",
        flush=True,
    )
    return True


if __name__ == "__main__":
    run_screener()
