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
