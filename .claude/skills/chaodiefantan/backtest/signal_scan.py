"""信号扫描与去重 — 逐日切片复用 is_oversold_rebound 判定信号,同波去重。

去重: 同股 window 个交易日内重复信号只留最早一个(同一波反弹)。
市值用 shares_func(code, date) 时变股本(送转回推修正,见 market_cap.shares_at_date)。
"""
from screener.analyzer import is_oversold_rebound
from backtest.market_cap import estimate_cap_yi, in_cap_band

DEDUP_WINDOW = 5  # 同股去重窗口(交易日)


def dedup_signals(signals: list[dict], trading_dates: list[str],
                  window: int = DEDUP_WINDOW) -> list[dict]:
    """同股 window 个交易日内的信号只保留最早一个。

    Args:
        signals: 信号列表(可乱序)。
        trading_dates: 全局交易日序列(升序),用于算交易日 index 差。
        window: 去重窗口(交易日数)。
    """
    date_idx = {d: i for i, d in enumerate(trading_dates)}
    ordered = sorted(signals, key=lambda s: (s["code"], s["signal_date"]))
    result: list[dict] = []
    last_date_by_code: dict[str, str] = {}
    for s in ordered:
        code, d = s["code"], s["signal_date"]
        if d not in date_idx:
            continue  # 信号日不在交易日序列(异常),丢弃
        last = last_date_by_code.get(code)
        if last is not None and date_idx[d] - date_idx[last] <= window:
            continue  # 同波,跳过
        result.append(s)
        last_date_by_code[code] = d
    return result


def scan_signals(klines_by_code: dict[str, list[dict]],
                 shares_func,
                 names_by_code: dict[str, str],
                 trading_dates: list[str],
                 unadj_close_by_code: dict[str, dict[str, float]] | None = None,
                 ) -> list[dict]:
    """逐日逐股扫描超跌反弹信号。

    Args:
        klines_by_code: {code: 前复权日K列表}，每项含 date/open/high/low/close/volume。
        shares_func: callable(code, date) -> 流通股本(股)。支持送转回推的时变股本。
        names_by_code: {code: 股票名称}。
        trading_dates: 要扫描的交易日序列(升序)。
        unadj_close_by_code: {code: {date: 不复权收盘价}}，用于市值估算。
            若 None 则用前复权 close 近似。

    Returns:
        信号列表(未去重)，每项 {signal_date, code, name, close_T, stop_loss,
        drop5, vol_ratio, market_cap_T}。
    """
    signals: list[dict] = []
    date_set = set(trading_dates)

    for code, bars in klines_by_code.items():
        if len(bars) < 7:
            continue
        unadj = (unadj_close_by_code or {}).get(code, {})
        name = names_by_code.get(code, code)

        for i in range(6, len(bars)):                  # bars[i]=候选T日,需之前>=6根
            t_date = bars[i]["date"]
            if t_date not in date_set:
                continue                                # 非回测交易日,跳过
            shares_t = shares_func(code, t_date)        # 时变股本(送转回推)
            if not shares_t:
                continue
            window = bars[: i + 1]                      # T及之前所有K线
            close_unadj = unadj.get(t_date, window[-1]["close"])
            cap_t = estimate_cap_yi(close_unadj, shares_t)
            if not in_cap_band(cap_t):
                continue
            detail = is_oversold_rebound(window, cap_t)
            if detail is None:
                continue
            signals.append({
                "signal_date": t_date,
                "code": code,
                "name": name,
                "close_T": window[-1]["close"],
                "stop_loss": detail["stop_loss"],
                "drop5": detail["drop5"],
                "vol_ratio": detail["vol_ratio"],
                "market_cap_T": round(cap_t, 2),
            })
    return signals
