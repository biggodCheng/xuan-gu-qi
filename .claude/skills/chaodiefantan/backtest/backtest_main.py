"""回测编排入口 — 串联数据→信号→模拟→报告。支持任意回测区间。

用法:
    python -m backtest.backtest_main                                # 默认 2024-01~2026-07
    python -m backtest.backtest_main --start 2018-01-02 --end 2026-07-17   # 8年长周期
    python -m backtest.backtest_main --smoke                        # 小样本冒烟
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)                     # chaodiefantan/
sys.path.insert(0, SKILL_DIR)

from screener.bridges import (  # noqa: E402  复用 kangdie fetcher
    get_all_stocks_today, get_market_cap_map, get_index_kline)
from backtest.data_loader import fetch_all, prefetch_waf_check  # noqa: E402
from backtest.market_cap import compute_float_shares  # noqa: E402
from backtest.signal_scan import scan_signals, dedup_signals  # noqa: E402
from backtest.simulator import simulate_exit  # noqa: E402
from backtest.report import (  # noqa: E402
    compute_trade_returns, aggregate_overall, aggregate_by_cap,
    aggregate_by_year, render_markdown, FEE_NET)

DEFAULT_START = "2024-01-02"
DEFAULT_END = "2026-07-17"
MAX_HOLD = 10
CACHE_DIR = os.path.join(HERE, "data")


def _fetch_start(start: str, buffer_days: int = 100) -> str:
    """start 往前推 buffer 天(留 70 日 K线 buffer)。"""
    from datetime import datetime, timedelta
    d = datetime.strptime(start, "%Y-%m-%d") - timedelta(days=buffer_days)
    return d.strftime("%Y-%m-%d")


def _report_path(start: str, end: str) -> str:
    return os.path.join(SKILL_DIR, "..", "..", "..", "docs",
                        f"chaodiefantan_backtest_{start}_{end}.md")


def load_pool_and_shares():
    """股票池(新浪) + 当前流通股本。"""
    df = get_all_stocks_today()
    if df.empty:
        raise RuntimeError("全A行情为空(非交易日?)")
    pool = df.to_dict("records")
    cap_map = get_market_cap_map()                   # {code: 流通市值(亿)}
    shares_by_code, names = {}, {}
    for s in pool:
        cap = cap_map.get(s["code"])
        if cap and s["close"] > 0:
            shares_by_code[s["code"]] = compute_float_shares(cap, s["close"])
            names[s["code"]] = s["name"]
    return pool, shares_by_code, names


def build_trades(signals, klines_qfq, mode, max_hold=MAX_HOLD):
    """对信号集模拟退出,合成 trade(含收益率)。mode: 'close'/'open'。"""
    trades = []
    for sig in signals:
        bars = klines_qfq.get(sig["code"], [])
        buy_idx = next((i for i, b in enumerate(bars)
                        if b["date"] == sig["signal_date"]), None)
        if buy_idx is None:
            continue
        buy_bars = bars[buy_idx:]                     # bars[0]=买入日
        if mode == "open":
            if len(buy_bars) < 2:
                continue
            buy_price = buy_bars[1]["open"]           # T+1 开盘
            sim_bars = buy_bars[1:]                   # 买入日=T+1
        else:
            buy_price = sig["close_T"]                # T 日收盘
            sim_bars = buy_bars
        exit_info = simulate_exit(sim_bars, buy_price, sig["stop_loss"], max_hold)
        trade = {**sig, **exit_info, "buy_price": buy_price, "mode": mode}
        trades.append(compute_trade_returns(trade, FEE_NET))
    return trades


def compute_elasticity(signals, klines_qfq):
    """固定持有 1/3/5/10 日原始收益 + MFE/MAE。"""
    if not signals:
        return {"n": 0}
    rets_by_n = {1: [], 3: [], 5: [], 10: []}
    mfes, maes = [], []
    for sig in signals:
        bars = klines_qfq.get(sig["code"], [])
        buy_idx = next((i for i, b in enumerate(bars)
                        if b["date"] == sig["signal_date"]), None)
        if buy_idx is None:
            continue
        after = bars[buy_idx + 1:]                    # T+1 起
        closes = [b["close"] for b in after]
        base = sig["close_T"]
        for n, lst in rets_by_n.items():
            if len(closes) >= n:
                lst.append((closes[n - 1] - base) / base * 100)
        if closes:
            mfes.append((max(closes[:10]) - base) / base * 100)
            maes.append((min(closes[:10]) - base) / base * 100)
    avg = lambda lst: round(sum(lst) / len(lst), 2) if lst else 0
    return {
        "n": len(signals),
        "hold_1": avg(rets_by_n[1]), "hold_3": avg(rets_by_n[3]),
        "hold_5": avg(rets_by_n[5]), "hold_10": avg(rets_by_n[10]),
        "mfe": avg(mfes), "mae": avg(maes),
        # avg_hold 不在此算(signals 无 hold_days)；报告二章用 overall['avg_hold']
    }


def run(smoke: bool = False, start: str = DEFAULT_START, end: str = DEFAULT_END):
    fetch_start = _fetch_start(start)
    report_path = _report_path(start, end)
    print(f"[回测区间] {start} ~ {end} (K线拉取起点 {fetch_start})", flush=True)

    print("[1] 股票池+股本 ...", flush=True)
    pool, shares_by_code, names = load_pool_and_shares()
    if smoke:
        # 冒烟取沪深股(排除北交所,新浪源对 bj 支持有限)
        pool = [s for s in pool if s["code"].startswith(("0", "3", "6"))][:5]
        shares_by_code = {c: shares_by_code[c] for c in [s["code"] for s in pool]}
    print(f"    池: {len(pool)} 只", flush=True)

    print("[2] 数据源预测试 ...", flush=True)
    rate = prefetch_waf_check(pool, fetch_start, end, sample=10 if smoke else 50)
    if rate < 0.8:
        raise RuntimeError(f"数据源预测试成功率 {rate:.0%} < 80%，中止(数据源不可用)")

    print("[3] 拉取前复权+不复权 K线 ...", flush=True)
    # 缓存按区间隔离(不同区间不混用)
    klines_qfq = fetch_all(pool, fetch_start, end, "qfq", CACHE_DIR,
                           f"qfq_{fetch_start}_{end}")
    klines_unadj = fetch_all(pool, fetch_start, end, "", CACHE_DIR,
                             f"unadj_{fetch_start}_{end}")

    print("[4] 逐日扫描信号 ...", flush=True)
    dates_q = sorted({b["date"] for kl in klines_qfq.values() for b in kl.to_dict("records")
                      if start <= b["date"] <= end})
    unadj_close = {c: dict(zip(kl["date"], kl["close"]))
                   for c, kl in klines_unadj.items()}
    klines_dict = {c: kl.to_dict("records") for c, kl in klines_qfq.items()}
    raw = scan_signals(klines_dict, shares_by_code, names, dates_q, unadj_close)
    signals = dedup_signals(raw, dates_q)
    print(f"    原始 {len(raw)} → 去重后 {len(signals)} 信号", flush=True)

    print("[5] 模拟退出(双口径) ...", flush=True)
    trades_close = build_trades(signals, klines_dict, "close")
    trades_open = build_trades(signals, klines_dict, "open")

    print("[6] 聚合+渲染 ...", flush=True)
    overall = aggregate_overall(trades_close)
    overall_open = aggregate_overall(trades_open)
    elasticity = compute_elasticity(signals, klines_dict)
    year_groups = aggregate_by_year(trades_close)
    cap_groups = aggregate_by_cap(trades_close)
    idx = get_index_kline("sz399006", days=2500)     # 8年+buffer
    idx_in = [k for k in idx if start <= k["date"] <= end]
    bench_ret = ((idx_in[-1]["close"] - idx_in[0]["close"]) / idx_in[0]["close"] * 100
                 if len(idx_in) >= 2 else 0)
    sl_trades = [t for t in trades_close if t["exit_reason"] == "stop_loss"]
    fit = {
        "total_signals": len(signals), "per_day": len(signals) / max(len(dates_q), 1),
        "avg_hold": overall["avg_hold"], "trading_days": len(dates_q),
        "stop_loss_share": len(sl_trades) / max(len(trades_close), 1),
        "stop_loss_saved": (sum(t["return_net"] for t in sl_trades) / len(sl_trades)
                            if sl_trades else 0),
    }
    biases = [
        {"name": "幸存者偏差", "direction": "高估收益",
         "note": "用当前全A池,已退市/ST股漏掉"},
        {"name": "市值近似", "direction": "部分小盘股误排除",
         "note": "不复权价×当前股本,忽略送转解禁"},
        {"name": "小样本", "direction": "非统计显著",
         "note": f"信号 {len(signals)} 个,探索性分析"},
        {"name": "流动性", "direction": "高估成交质量",
         "note": "假设stop_loss/close价成交,实盘滑点更大"},
    ]
    md = render_markdown(overall, overall_open, elasticity, year_groups,
                         cap_groups, fit, bench_ret, biases)

    os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[done] 报告: {os.path.abspath(report_path)}", flush=True)
    print(f"        信号 {len(signals)} | 胜率 {overall['win_rate']:.0f}% | "
          f"平均净收益 {overall['avg_ret_net']:+.2f}% | 基准 {bench_ret:+.2f}%",
          flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="小样本冒烟")
    p.add_argument("--start", default=DEFAULT_START, help="回测起点 YYYY-MM-DD")
    p.add_argument("--end", default=DEFAULT_END, help="回测终点 YYYY-MM-DD")
    args = p.parse_args()
    run(smoke=args.smoke, start=args.start, end=args.end)


if __name__ == "__main__":
    main()
