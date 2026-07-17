"""超跌反弹判定纯函数 — 无网络、无副作用，可单测。

核心逻辑：找"近5日急跌 + T-1日缩量长下影 + T日放量阳包阴"的标的，
捕捉超跌后资金进场的反抽信号（左侧短线，严止损）。

bar 格式：{day/date, open, high, low, close, volume/vol}，按日期正序，
最后一个元素为当日T，倒数第二个为昨日T-1。
"""

# ---- 阈值 ----
DROP_5D = -15.0            # 近5日跌幅阈值(%)，跌幅 <= 此值才算急跌
LOWER_SHADOW_MULT = 2.0    # T-1下影 >= 实体的 2 倍
LOWER_SHADOW_PCT = 0.03    # T-1下影 >= 当日价格的 3%
VOL_CONFIRM_RATIO = 1.5    # T日放量 >= T-1日的 1.5 倍
VOL_SHRINK_RATIO = 0.8     # T-1日相对前4日均量缩到此比例以下
MARKET_CAP_MIN = 50        # 流通市值下限（亿）
MARKET_CAP_MAX = 500       # 流通市值上限（亿）


def _get(bar: dict, *keys):
    """从 bar 取第一个存在的键值（兼容 volume/vol、day/date、low）。"""
    for k in keys:
        if k in bar:
            return bar[k]
    raise KeyError(f"none of {keys} found in bar")


def is_oversold_rebound(bars: list[dict], market_cap: float) -> dict | None:
    """判断个股是否出现超跌反弹信号（5 条全满足）。

    Args:
        bars: 个股日K列表（按日期正序），需 >= 7 条。
        market_cap: 流通市值（亿元）。

    Returns:
        通过时返回 {drop5, stop_loss, vol_ratio}；不通过返回 None。
        stop_loss = T-1日最低（破即止损）。
    """
    if len(bars) < 7:
        return None

    closes = [b["close"] for b in bars]
    vols = [_get(b, "volume", "vol") for b in bars]

    # 条件1：近5日急跌（跌幅 <= -15%）
    if closes[-6] <= 0:
        return None
    drop5 = (closes[-1] - closes[-6]) / closes[-6] * 100
    if drop5 > DROP_5D:
        return None

    # 条件2：T-1日长下影（下影 >= 2×实体 且 >= 价格3%）
    t2 = bars[-2]
    o2, c2 = t2["open"], t2["close"]
    low2 = _get(t2, "low")
    body2 = abs(o2 - c2)
    if body2 <= 0:
        return None  # 一字板无实体，下影判定无意义
    lower2 = min(o2, c2) - low2
    if lower2 < LOWER_SHADOW_MULT * body2:
        return None
    if c2 <= 0 or lower2 / c2 < LOWER_SHADOW_PCT:
        return None

    # 条件3：T-1日缩量（相对前4日均量）
    vol_prev_mean = sum(vols[-6:-2]) / 4
    if vol_prev_mean <= 0 or vols[-2] >= vol_prev_mean * VOL_SHRINK_RATIO:
        return None

    # 条件4：T日放量阳包阴
    t1 = bars[-1]
    o1, c1 = t1["open"], t1["close"]
    high1 = _get(t1, "high")
    v1 = _get(t1, "volume", "vol")
    v2 = vols[-2]
    if c1 <= o1:
        return None  # 非阳线
    if v2 <= 0 or v1 <= v2 * VOL_CONFIRM_RATIO:
        return None  # 未放量
    if c1 <= o2:
        return None  # 未收复前日开盘
    if high1 <= _get(t2, "high"):
        return None  # 未突破前日高点

    # 条件5：市值
    if not (MARKET_CAP_MIN <= market_cap <= MARKET_CAP_MAX):
        return None

    return {
        "drop5": round(drop5, 2),
        "stop_loss": round(low2, 2),  # 止损位 = T-1日最低
        "vol_ratio": round(v1 / v2, 2),
    }
