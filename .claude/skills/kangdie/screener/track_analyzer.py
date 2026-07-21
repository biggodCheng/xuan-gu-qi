"""抗跌反弹跟踪纯函数 — 无网络、无副作用，可单测。

对齐暴跌日 D 之后的 K 线切片，算各窗口涨幅 / MFE·MAE / 第一时间反弹判定。
约定: after_bars[0] = D+1（D 的下一个交易日）。
个股 bars 用 day 键、指数 bars 用 date 键（fetcher 行为），本模块两者兼容。
"""
import warnings

# 跟踪窗口（D 之后第 N 个交易日）
WINDOWS = (1, 3, 5, 10, 20)
MATURE_DAYS = 20  # D+20 后视为成熟，停止更新


def align_after(bars: list[dict], drop_date: str) -> tuple[list[dict], float] | None:
    """在 bars 中定位 drop_date，返回 (bars[i+1:], 该日收盘价)；找不到返回 None。

    兼容 day/date 键。after_bars[0] 即 D+1。
    精确匹配不到时(如 drop_date 是非交易日/文件名命名错位),回退到 <=drop_date 的最近
    交易日作 D 并 warnings.warn——防止 K 线无该日导致静默返回 None、反弹指标全部归空。
    """
    for i, b in enumerate(bars):
        d = b.get("day") or b.get("date")
        if d == drop_date:
            return bars[i + 1:], b["close"]

    # 精确匹配失败:回退到 <= drop_date 的最近一个交易日(bars 按日期正序,取最后一个满足的)
    fallback_idx = None
    for i, b in enumerate(bars):
        d = b.get("day") or b.get("date")
        if d is not None and d <= drop_date:
            fallback_idx = i
    if fallback_idx is not None:
        fb = bars[fallback_idx]
        fb_date = fb.get("day") or fb.get("date")
        warnings.warn(
            f"align_after: drop_date={drop_date} 在K线中不存在(可能为非交易日/命名错位),"
            f"已回退到最近交易日 {fb_date} 作为 D 日",
            stacklevel=2,
        )
        return bars[fallback_idx + 1:], fb["close"]
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


def first_rebound(
    after_bars: list[dict],
    d_close: float,
    idx_after_bars: list[dict],
    idx_d_close: float,
) -> bool | None:
    """第一时间反弹判定：D+1~D+3 区间，个股累计涨幅 > 0 且 > 创业板同期累计 → True。

    数据不足或基准为 0 返回 None。
    """
    if len(after_bars) < 3 or len(idx_after_bars) < 3:
        return None
    if d_close == 0 or idx_d_close == 0:
        return None
    stock_cum = (after_bars[2]["close"] - d_close) / d_close * 100
    idx_cum = (idx_after_bars[2]["close"] - idx_d_close) / idx_d_close * 100
    return stock_cum > 0 and stock_cum > idx_cum


def is_mature(after_bars: list[dict]) -> bool:
    """是否已过 D+MATURE_DAYS 个交易日（数据成熟，停止更新）。"""
    return len(after_bars) >= MATURE_DAYS
