# -*- coding: utf-8 -*-
"""boduan — 波段超跌反弹选股(月度级超跌+放量阳包阴)。

复用 chaodiefantan/backtest/band_signal.is_band_rebound(判定) +
chaodiefantan/screener/bridges(数据层), 不重写。参数固定回测最优 X=30 R=2.5。
独立运行: python main.py
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# 复用 chaodiefantan 的判定 + 数据层 + 项目根 trading_day
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_CHAODIE_DIR = os.path.join(os.path.dirname(_SKILL_DIR), "chaodiefantan")
if os.path.isdir(_CHAODIE_DIR) and _CHAODIE_DIR not in sys.path:
    sys.path.insert(0, _CHAODIE_DIR)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SKILL_DIR)))
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if os.path.isdir(_SCRIPTS_DIR) and _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import trading_day  # noqa: E402
from screener.bridges import (  # noqa: E402  复用 chaodiefantan bridges(数据层)
    get_all_stocks_today, get_stock_kline, get_market_cap_map)
from backtest.band_signal import is_band_rebound  # noqa: E402  阶段1 建成

# 回测最优参数(固定, 改这里即改策略)
DROP_PCT = 30.0          # 近20日跌 > 30%
VOL_RATIO = 2.5          # T日放量 >= 2.5 倍
_KLINE_DAYS = 25         # >= DROP_WINDOW+1=21
_MAX_WORKERS = 20


def build_candidates(stocks: list[dict], klines_map: dict,
                     drop_pct: float = DROP_PCT, vol_ratio: float = VOL_RATIO
                     ) -> list[dict]:
    """逐股判定波段超跌反弹, 返回候选列表(纯函数, 可单测)。

    Args:
        stocks: [{code, name, close, market_cap?}]。
        klines_map: {code: 日K列表}。
        drop_pct/vol_ratio: 透传 is_band_rebound。
    """
    candidates = []
    for s in stocks:
        bars = klines_map.get(s["code"], [])
        detail = is_band_rebound(bars, s.get("market_cap"), drop_pct, vol_ratio)
        if detail:
            candidates.append({
                "code": s["code"], "name": s["name"], "close": s["close"],
                "market_cap": s.get("market_cap"), **detail,
            })
    return candidates


def run(output_dir: str | None = None, date_str: str | None = None) -> bool:
    if output_dir is None:
        output_dir = os.path.join(_SKILL_DIR, "data")
    os.makedirs(output_dir, exist_ok=True)

    start = time.time()
    date_str = date_str or trading_day.latest_trading_day()
    trading_day.warn_if_drift(date_str)
    print(f"[{date_str}] boduan 波段超跌反弹扫描启动...", flush=True)

    print("获取全A股行情...", flush=True)
    stocks_df = get_all_stocks_today()
    if stocks_df.empty:
        print("  未获取到行情数据,可能是非交易日。", flush=True)
        _save(output_dir, date_str, [], trigger={"error": "no_market_data"})
        return False
    stocks = stocks_df.to_dict("records")
    print(f"  共 {len(stocks)} 只。", flush=True)

    print("获取全A市值数据(展示用,不过滤)...", flush=True)
    cap_map = get_market_cap_map()
    for s in stocks:
        cap = cap_map.get(s["code"])
        if cap:
            s["market_cap"] = round(cap, 2)
    print(f"  全A {len(stocks)} 只(已过滤ST/*ST/新股),不卡市值。", flush=True)

    print(f"并发拉取个股 {_KLINE_DAYS} 日OHLCV({_MAX_WORKERS}线程)...", flush=True)
    klines_map: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {executor.submit(get_stock_kline, s["code"], _KLINE_DAYS): s["code"]
                   for s in stocks}
        done = 0
        total = len(stocks)
        for future in as_completed(futures):
            code = futures[future]
            try:
                klines_map[code] = future.result()
            except Exception:
                pass
            done += 1
            if done % 1000 == 0:
                print(f"  OHLCV 已拉取 {done}/{total}...", flush=True)
    print(f"  OHLCV 拉取完成({len(klines_map)} 只有数据)。", flush=True)

    candidates = build_candidates(stocks, klines_map)
    print(f"  波段超跌信号通过:{len(candidates)} 只。", flush=True)

    _save(output_dir, date_str, candidates,
          trigger={"signal": "band_oversold_rebound"})
    elapsed = time.time() - start
    path = os.path.join(output_dir, f"bd_{date_str}.json")
    print(f"完成!波段超跌 {len(candidates)} 只,耗时 {elapsed:.0f} 秒。结果:{path}", flush=True)
    print("  纪律:止损=破T-1最低(stop_loss),纪律退出(跟踪+10日强平),仓位<=10%,"
          "反弹是兑现窗口不恋战。", flush=True)
    return True


def _save(output_dir: str, date_str: str, candidates: list, trigger: dict) -> None:
    out = {"date": date_str, "trigger": trigger,
           "count": len(candidates), "stocks": candidates}
    path = os.path.join(output_dir, f"bd_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    run()
