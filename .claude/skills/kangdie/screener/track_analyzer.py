"""抗跌反弹跟踪纯函数 — 无网络、无副作用，可单测。

对齐暴跌日 D 之后的 K 线切片，算各窗口涨幅 / MFE·MAE / 第一时间反弹判定。
约定: after_bars[0] = D+1（D 的下一个交易日）。
个股 bars 用 day 键、指数 bars 用 date 键（fetcher 行为），本模块两者兼容。
"""

# 跟踪窗口（D 之后第 N 个交易日）
WINDOWS = (1, 3, 5, 10, 20)
MATURE_DAYS = 20  # D+20 后视为成熟，停止更新


def align_after(bars: list[dict], drop_date: str) -> tuple[list[dict], float] | None:
    """在 bars 中定位 drop_date，返回 (bars[i+1:], 该日收盘价)；找不到返回 None。

    兼容 day/date 键。after_bars[0] 即 D+1。
    """
    for i, b in enumerate(bars):
        d = b.get("day") or b.get("date")
        if d == drop_date:
            return bars[i + 1:], b["close"]
    return None


def window_return(after_bars: list[dict], d_close: float, n: int) -> float | None:
    """D+N 累计涨幅(%)：(close[D+N] - d_close) / d_close × 100。

    after_bars[n-1] = D+N。数据不足或 d_close=0 返回 None。
    """
    if len(after_bars) < n or d_close == 0:
        return None
    c = after_bars[n - 1]["close"]
    return round((c - d_close) / d_close * 100, 2)


def mfe_mae(after_bars: list[dict], d_close: float) -> tuple[float | None, float | None]:
    """D 之后区间最大涨幅 MFE / 最大跌幅 MAE(%)，相对 d_close。空数据返回 (None, None)。"""
    if not after_bars or d_close == 0:
        return None, None
    highs = [b["high"] for b in after_bars]
    lows = [b["low"] for b in after_bars]
    mfe = round((max(highs) - d_close) / d_close * 100, 2)
    mae = round((min(lows) - d_close) / d_close * 100, 2)
    return mfe, mae


def end_return(after_bars: list[dict], d_close: float) -> float | None:
    """末值收益(%)：D 之后最后一根收盘相对 d_close。空数据返回 None。"""
    if not after_bars or d_close == 0:
        return None
    return round((after_bars[-1]["close"] - d_close) / d_close * 100, 2)
