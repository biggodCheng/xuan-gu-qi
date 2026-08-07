# -*- coding: utf-8 -*-
"""波段超跌信号网格回测 — 扫 X/R/缩量/开关 找正期望组合。

复用 chaodiefantan/backtest 框架(数据加载/simulator/report), 不改任何现有模块。
详见 spec docs/superpowers/specs/2026-08-08-band-oversold-rebound-design.md

用法:
    python -m backtest.grid_backtest --smoke                 # 小样本冒烟
    python -m backtest.grid_backtest --start 2018-01-02 --end 2026-08-07   # 全量
"""
import argparse
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)                     # chaodiefantan/
sys.path.insert(0, SKILL_DIR)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from backtest.band_signal import is_band_rebound  # noqa: E402
from backtest.data_loader import (  # noqa: E402
    fetch_all, prefetch_waf_check, fetch_all_dividends)
from backtest.market_cap import (  # noqa: E402
    estimate_cap_yi, in_cap_band, shares_at_date)
from backtest.signal_scan import dedup_signals  # noqa: E402
from backtest.report import aggregate_overall, aggregate_by_year  # noqa: E402
from backtest.backtest_main import (  # noqa: E402
    load_pool_and_shares, _compute_crash_dates, _fetch_start, build_trades)

DEFAULT_START = "2018-01-02"
DEFAULT_END = "2026-08-07"
CACHE_DIR = os.path.join(HERE, "data")


def scan_band_signals(klines_by_code: dict, shares_func, names: dict,
                      dates: list, unadj_close: dict,
                      drop_pct: float, vol_ratio: float, use_shrink: bool,
                      use_t1_drop: bool = False) -> list[dict]:
    """逐日逐股扫描波段超跌信号。

    与 backtest.signal_scan.scan_signals 同结构, 但调 is_band_rebound + 字段用 drop20。
    市值用 shares_func(code, date) 时变股本(in_cap_band 默认关闭=不卡市值)。
    use_t1_drop 透传给 is_band_rebound(超跌口径, spec §3)。
    """
    signals: list[dict] = []
    date_set = set(dates)
    for code, bars in klines_by_code.items():
        if len(bars) < 21:
            continue
        unadj = unadj_close.get(code, {})
        name = names.get(code, code)
        for i in range(20, len(bars)):                 # bars[i]=候选T日, 需之前>=20根
            t_date = bars[i]["date"]
            if t_date not in date_set:
                continue
            shares_t = shares_func(code, t_date)
            if not shares_t:
                continue
            window = bars[: i + 1]
            close_unadj = unadj.get(t_date, window[-1]["close"])
            cap_t = estimate_cap_yi(close_unadj, shares_t)
            if not in_cap_band(cap_t):
                continue
            detail = is_band_rebound(window, cap_t, drop_pct, vol_ratio, use_shrink,
                                     use_t1_drop)
            if detail is None:
                continue
            signals.append({
                "signal_date": t_date, "code": code, "name": name,
                "close_T": window[-1]["close"], "stop_loss": detail["stop_loss"],
                "drop20": detail["drop20"], "vol_ratio": detail["vol_ratio"],
                "market_cap_T": round(cap_t, 2),
            })
    return signals


# 网格参数(spec §4): 超跌幅度 X × 放量倍数 R × T-1缩量 × 大盘开关
GRID_X = [20.0, 25.0, 30.0]
GRID_R = [1.5, 2.0, 2.5]
GRID_SHRINK = [False, True]
GRID_SWITCH = [False, True]
BEAR_YEARS = ("2018", "2022")          # 成功标准③: 熊市单年期望 > -3%
SIGNAL_FLOOR = 50                       # 成功标准②: 信号数 >= 50


def _eval_combo(klines_dict, shares_func, names, dates_q, unadj_close,
                crash_dates, drop_pct, vol_ratio, use_shrink, use_switch):
    """跑单个参数组合, 返回结果 dict。"""
    raw = scan_band_signals(klines_dict, shares_func, names, dates_q, unadj_close,
                           drop_pct, vol_ratio, use_shrink)
    sigs = dedup_signals(raw, dates_q)
    if use_switch:                                     # 大盘开关: 排除 crash 日
        sigs = [s for s in sigs if s["signal_date"] not in crash_dates]
    if not sigs:
        return {"n": 0, "raw": len(raw), "win": 0, "payoff": 0, "avg": 0,
                "bear": {y: None for y in BEAR_YEARS}, "expect": 0}
    trades = build_trades(sigs, klines_dict, "open")   # T+1 开盘口径, 纪律退出
    o = aggregate_overall(trades)
    yg = aggregate_by_year(trades)
    return {
        "n": len(sigs), "raw": len(raw),
        "win": o["win_rate"], "payoff": o["payoff"], "avg": o["avg_ret_net"],
        "bear": {y: (yg.get(y, {}) or {}).get("avg_ret_net") for y in BEAR_YEARS},
        "expect": (o["win_rate"] / 100 * o["payoff"]) if o["n"] else 0,
    }


def _ok(r: dict) -> bool:
    """成功标准达标判定(spec §5): 正期望 + 信号>=50 + 熊市单年>-3%。"""
    if r["n"] < SIGNAL_FLOOR:
        return False
    if r["avg"] <= 0 or r["expect"] <= 1:
        return False
    for y in BEAR_YEARS:
        v = r["bear"].get(y)
        if v is not None and v <= -3.0:
            return False
    return True


def render_grid_report(rows: list, start: str, end: str, out_path: str):
    L = [f"# 波段超跌信号 网格回测报告（{start} ~ {end}）\n"]
    L.append("> T+1 开盘口径 + 纪律退出(max_hold=10)。"
             "达标 = 正期望(胜率×盈亏比>1) + 信号≥50 + 2018/2022 单年>-3%。\n")
    L.append("## 网格结果\n")
    L.append("| X% | R | 缩量 | 开关 | 原始 | 去重信号 | 胜率 | 盈亏比 | 期望 | 平均净收益 | 2018 | 2022 | 达标 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        b18 = r["bear"].get("2018"); b22 = r["bear"].get("2022")
        fmt = lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else "—"
        if r["n"] == 0:
            L.append(f"| {r['X']} | {r['R']} | {r['shrink']} | {r['switch']} | "
                     f"{r['raw']} | 0 | — | — | — | — | — | — | ❌ |")
        else:
            L.append(f"| {r['X']} | {r['R']} | {r['shrink']} | {r['switch']} | "
                     f"{r['raw']} | {r['n']} | {r['win']:.0f}% | {r['payoff']} | "
                     f"{r['expect']:.2f} | {r['avg']:+.2f}% | {fmt(b18)} | {fmt(b22)} | "
                     f"{'✅' if r['ok'] else '❌'} |")
    winners = [r for r in rows if r["ok"]]
    L.append(f"\n## 达标组合: {len(winners)} / {len(rows)}\n")
    if winners:
        best = max(winners, key=lambda r: r["avg"])
        L.append(f"- 最优(平均净收益最高): X={best['X']}% R={best['R']} "
                 f"缩量={best['shrink']} 开关={best['switch']} → "
                 f"{best['n']}信号 / {best['win']:.0f}% / 盈亏比{best['payoff']} / "
                 f"{best['avg']:+.2f}%\n")
    else:
        L.append("- 无组合达标 → 按 spec §6 决策规则: 放弃或加约束, **禁止降阈值凑**。\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def run_grid(start: str = DEFAULT_START, end: str = DEFAULT_END, smoke: bool = False):
    fetch_start = _fetch_start(start)
    print(f"[网格回测] {start} ~ {end} (K线起点 {fetch_start})", flush=True)

    print("[1] 股票池+股本 ...", flush=True)
    pool, shares_by_code, names = load_pool_and_shares()
    if smoke:
        pool = [s for s in pool if s["code"].startswith(("0", "3", "6"))][:5]
        shares_by_code = {c: shares_by_code[c] for c in [s["code"] for s in pool]}
    print(f"    池: {len(pool)} 只", flush=True)

    print("[2] 数据源预测试 ...", flush=True)
    rate = prefetch_waf_check(pool, fetch_start, end, sample=10 if smoke else 50)
    if rate < 0.8:
        raise RuntimeError(f"数据源预测试成功率 {rate:.0%} < 80%, 中止")

    print("[3] 拉取前复权+不复权 K线(一次性, 全网格共享) ...", flush=True)
    klines_qfq = fetch_all(pool, fetch_start, end, "qfq", CACHE_DIR,
                           f"qfq_{fetch_start}_{end}")
    klines_unadj = fetch_all(pool, fetch_start, end, "", CACHE_DIR,
                             f"unadj_{fetch_start}_{end}")
    print("[3.5] 拉除权日历 ...", flush=True)
    dividends = fetch_all_dividends(pool, CACHE_DIR)

    dates_q = sorted({b["date"] for kl in klines_qfq.values()
                      for b in kl.to_dict("records") if start <= b["date"] <= end})
    unadj_close = {c: dict(zip(kl["date"], kl["close"]))
                   for c, kl in klines_unadj.items()}
    klines_dict = {c: kl.to_dict("records") for c, kl in klines_qfq.items()}

    def _shares_func(code, date):
        cur = shares_by_code.get(code)
        if not cur:
            return None
        return shares_at_date(cur, dividends.get(code, []), date)

    print("[4] 预算大盘 crash 日(用于开关组合) ...", flush=True)
    crash_dates = _compute_crash_dates(start, end)
    print(f"    crash 交易日 {len(crash_dates)} 个", flush=True)

    total = len(GRID_X) * len(GRID_R) * len(GRID_SHRINK) * len(GRID_SWITCH)
    print(f"[5] 跑 {total} 组网格 ...", flush=True)
    rows = []
    for X, R, use_shrink, use_switch in itertools.product(
            GRID_X, GRID_R, GRID_SHRINK, GRID_SWITCH):
        r = _eval_combo(klines_dict, _shares_func, names, dates_q, unadj_close,
                        crash_dates, X, R, use_shrink, use_switch)
        r.update({"X": X, "R": R, "shrink": use_shrink, "switch": use_switch,
                  "ok": _ok(r) if r["n"] else False})
        rows.append(r)
        print(f"    X={X} R={R} shrink={use_shrink} switch={use_switch} → "
              f"{r['n']}信号 {r.get('avg', 0):+.2f}%", flush=True)

    out_path = os.path.join(SKILL_DIR, "..", "..", "..", "docs",
                            f"band_grid_{start}_{end}.md")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    render_grid_report(rows, start, end, out_path)
    print(f"[done] 报告: {os.path.abspath(out_path)}", flush=True)
    print(f"        达标 {sum(1 for r in rows if r['ok'])} / {len(rows)} 组", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="小样本冒烟(5只)")
    p.add_argument("--start", default=DEFAULT_START)
    p.add_argument("--end", default=DEFAULT_END)
    args = p.parse_args()
    run_grid(start=args.start, end=args.end, smoke=args.smoke)


if __name__ == "__main__":
    main()
