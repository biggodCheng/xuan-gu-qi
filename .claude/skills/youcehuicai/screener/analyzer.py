"""右侧趋势回踩判定纯函数 — 无网络、无副作用，可单测。

核心逻辑：大盘企稳（三指站稳MA20）时，找"上涨趋势中缩量回踩MA10/MA20"
的标的。这是回踩策略在上涨市的正确用法（区别于下跌市失效的 suolianghuicai）。

bar 格式（个股/指数统一）：
    {day/date: str, open: float, high: float, low: float, close: float, volume/vol: float}
按日期正序排列，最后一个元素为当日。
"""

# ---- 阈值 ----
MARKET_CAP_MIN = 100        # 流通市值下限（亿）— 原spec，流动性+龙头
MARKET_CAP_MAX = 500        # 流通市值上限（亿）
PULLBACK_TOLERANCE = 0.02   # 回踩均线容差：收盘距均线 2% 内视为"回踩到该均线"
VOL_SHRINK_RATIO = 0.8      # 缩量阈值：近3日均量 < 近17日均量(x) * 0.8


def _get(bar: dict, *keys):
    """从 bar 中取第一个存在的键值（兼容 day/date、volume/vol）。"""
    for k in keys:
        if k in bar:
            return bar[k]
    raise KeyError(f"none of {keys} found in bar")


def compute_ma(closes: list[float], n: int) -> float | None:
    """计算最近 n 日均线值 = mean(closes[-n:])。数据不足返回 None。"""
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


# ============================================================
# 企稳门控（前置，必须先满足）
# ============================================================

def index_above_ma20(index_bars: list[dict]) -> bool | None:
    """指数收盘是否站上 MA20（close[-1] > MA20）。

    Args:
        index_bars: 指数日K列表（按日期正序）。

    Returns:
        True=站上MA20，False=跌破MA20，None=数据不足(<20条)。
    """
    if len(index_bars) < 20:
        return None
    closes = [b["close"] for b in index_bars]
    ma20 = compute_ma(closes, 20)
    return closes[-1] > ma20


def market_stabilized(index_bars_map: dict[str, list[dict]]) -> tuple[bool, list[dict]]:
    """企稳门控：三指 all close > MA20（即 not below_ma20）。

    Args:
        index_bars_map: {指数名: 指数日K列表}，通常传入 上证/沪深300/创业板指。

    Returns:
        (stabilized, details)
        - stabilized: True 表示三指全部站上MA20（企稳，可继续选股）。
        - details: [{name, close, ma20, above_ma20}, ...]，每个指数的判定明细。
          数据不足时 above_ma20=False、ma20=None（保守判为未企稳）。
    """
    details = []
    all_above = True
    for name, bars in index_bars_map.items():
        above = index_above_ma20(bars)
        if above is None:
            close = round(bars[-1]["close"], 2) if bars else 0.0
            details.append({
                "name": name,
                "close": close,
                "ma20": None,
                "above_ma20": False,
                "note": "data_insufficient",
            })
            all_above = False
        else:
            closes = [b["close"] for b in bars]
            ma20 = round(sum(closes[-20:]) / 20, 2)
            details.append({
                "name": name,
                "close": round(closes[-1], 2),
                "ma20": ma20,
                "above_ma20": above,
            })
            if not above:
                all_above = False
    return all_above, details


# ============================================================
# 个股右侧趋势回踩判定
# ============================================================

def is_right_side_pullback(
    stock_bars: list[dict],
    market_cap: float,
) -> dict | None:
    """判断个股是否为"上涨趋势中缩量回踩均线"（4 条全满足）。

    Args:
        stock_bars: 个股日K列表（按日期正序），需 >= 60 条。
        market_cap: 流通市值（亿元）。

    Returns:
        通过时返回：
            {pullback_ma, pullback_price, vol_shrink, stop_loss, market_cap, ma10, ma20, ma60}
        不通过返回 None。

    条件：
        1. 上涨趋势（均线多头）：close[-1] > MA20 > MA60
        2. 回踩MA10或MA20（满足其一，优先MA10）：
           - 回踩MA10：abs(close[-1]-MA10)/MA10 < 0.02
           - 回踩MA20：abs(close[-1]-MA20)/MA20 < 0.02
        3. 缩量：mean(vol[-3:]) < mean(vol[-20:-3]) * 0.8
        4. 市值 100-500 亿
    """
    if len(stock_bars) < 60:
        return None

    closes = [b["close"] for b in stock_bars]
    vols = [_get(b, "volume", "vol") for b in stock_bars]

    ma10 = compute_ma(closes, 10)
    ma20 = compute_ma(closes, 20)
    ma60 = compute_ma(closes, 60)
    last_close = closes[-1]

    # ---- 条件1：上涨趋势（均线多头）close[-1] > MA20 > MA60 ----
    if not (last_close > ma20 > ma60):
        return None

    # ---- 条件2：回踩MA10或MA20（优先MA10）----
    pullback_ma = None
    pullback_price = None
    # 先判 MA10
    if ma10 and abs(last_close - ma10) / ma10 < PULLBACK_TOLERANCE:
        pullback_ma = "MA10"
        pullback_price = round(ma10, 2)
    # 再判 MA20
    elif abs(last_close - ma20) / ma20 < PULLBACK_TOLERANCE:
        pullback_ma = "MA20"
        pullback_price = round(ma20, 2)

    if pullback_ma is None:
        return None

    # ---- 条件3：缩量 mean(vol[-3:]) < mean(vol[-20:-3]) * 0.8 ----
    # vol[-20:-3] 为近3日之前的17日窗口（排除最近3日，避免自污染）
    recent_vol = sum(vols[-3:]) / 3
    base_window = vols[-20:-3]
    if len(base_window) < 1:
        return None
    base_vol = sum(base_window) / len(base_window)
    if base_vol <= 0:
        return None
    vol_shrink = recent_vol / base_vol
    if vol_shrink >= VOL_SHRINK_RATIO:
        return None

    # ---- 条件4：市值 100-500 亿 ----
    if not (MARKET_CAP_MIN <= market_cap <= MARKET_CAP_MAX):
        return None

    return {
        "pullback_ma": pullback_ma,
        "pullback_price": pullback_price,
        "vol_shrink": round(vol_shrink, 3),
        "stop_loss": round(ma20, 2),  # 破MA20即止损
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "market_cap": round(market_cap, 2),
    }
