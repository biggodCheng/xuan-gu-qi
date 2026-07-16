"""抗跌判定纯函数 — 无网络、无副作用，可单测。

核心逻辑：大盘创新低时，筛"大盘跌但个股不跌"的抗跌股。

bar 格式（个股/指数统一）：
    {day/date: str, open: float, high: float, low: float, close: float, volume/vol: float}
按日期正序排列，最后一个元素为当日。
"""

# ---- 阈值 ----
OUTPERFORM_GAP = 5.0       # 20日跑赢大盘至少 5 个百分点
VOL_SHRINK_THRESHOLD = 0.8  # 近5日均量 < 近20日均量 × 0.8
MARKET_CAP_MIN = 50         # 流通市值下限（亿）
MARKET_CAP_MAX = 500        # 流通市值上限（亿）


def _get(bar: dict, *keys):
    """从 bar 中取第一个存在的键值（兼容 day/date、volume/vol）。"""
    for k in keys:
        if k in bar:
            return bar[k]
    raise KeyError(f"none of {keys} found in bar")


def market_big_drop(index_bars: list[dict], threshold: float = -1.5) -> tuple[bool, float, float]:
    """判断大盘今日是否大跌（当日跌幅 ≤ threshold 即触发）。

    判定：(close[-1] - close[-2]) / close[-2] × 100 ≤ threshold。

    Args:
        index_bars: 指数日K列表（按日期正序）。
        threshold: 触发阈值(%)，当日跌幅 ≤ 此值即触发。默认 -1.5。

    Returns:
        (is_triggered, chg_pct, today_close)
    """
    if len(index_bars) < 2:
        return False, 0.0, 0.0
    today = index_bars[-1]["close"]
    prev = index_bars[-2]["close"]
    if prev == 0:
        return False, 0.0, 0.0
    chg = (today - prev) / prev * 100
    return chg <= threshold, round(chg, 2), round(today, 2)


def compute_ret20(bars: list[dict]) -> float | None:
    """计算近 20 个交易日涨跌幅。

    ret20 = (close[-1] - close[-21]) / close[-21] * 100

    数据不足返回 None。
    """
    if len(bars) < 21:
        return None
    closes = [b["close"] for b in bars]
    base = closes[-21]
    if base == 0:
        return None
    return (closes[-1] - base) / base * 100


def is_anticorrection(
    stock_bars: list[dict],
    index_ret20: float,
    market_cap: float,
) -> dict | None:
    """判断个股是否抗跌（4 条全满足）。

    Args:
        stock_bars: 个股日K列表（按日期正序），需 >= 60 条。
        index_ret20: 大盘近 20 日涨跌幅（%）。
        market_cap: 流通市值（亿元）。

    Returns:
        通过时返回 {ret20, rs_vs_idx, vol_shrink, market_cap}，
        不通过返回 None。
    """
    if len(stock_bars) < 60:
        return None

    lows = [_get(b, "low") for b in stock_bars]
    closes = [b["close"] for b in stock_bars]
    vols = [_get(b, "volume", "vol") for b in stock_bars]

    # 条件1：近20日最低 ≥ 前40日最低（近20日没破前低）
    # 比较 min(近20日low) vs min(前40日low)，即 lows[-20:] vs lows[-60:-20]。
    # 近20日是近60日的子集，若直接比 lows[-20:] vs lows[-60:] 恒成立（无意义）；
    # 故取近20日之前的一段（-60:-20，共40日）作为"前低"基准。
    min_low_20 = min(lows[-20:])
    min_low_prev40 = min(lows[-60:-20])
    if min_low_20 < min_low_prev40:
        return None

    # 条件2：20日跑赢大盘至少 5 个百分点
    stock_ret20 = compute_ret20(stock_bars)
    if stock_ret20 is None:
        return None
    rs_vs_idx = stock_ret20 - index_ret20
    if rs_vs_idx < OUTPERFORM_GAP:
        return None

    # 条件3：近5日缩量（近5日均量 < 近20日均量 × 0.8）
    vol5_avg = sum(vols[-5:]) / 5
    vol20_avg = sum(vols[-20:]) / 20
    if vol20_avg <= 0:
        return None
    vol_shrink = vol5_avg / vol20_avg
    if vol_shrink >= VOL_SHRINK_THRESHOLD:
        return None

    # 条件4：流通市值 50-500 亿
    if not (MARKET_CAP_MIN <= market_cap <= MARKET_CAP_MAX):
        return None

    return {
        "ret20": round(stock_ret20, 2),
        "rs_vs_idx": round(rs_vs_idx, 2),
        "vol_shrink": round(vol_shrink, 3),
        "market_cap": round(market_cap, 2),
    }
