"""流通股本与历史市值估算 — 纯函数。

市值过滤口径 50-500 亿(流通市值)。股本视为 2.5 年常数(忽略解禁/增发)。
详见 spec §4.3。
"""
from screener.analyzer import MARKET_CAP_MIN, MARKET_CAP_MAX  # 50 / 500


def compute_float_shares(cap_yi: float, close: float) -> float:
    """流通股本(股) = 流通市值(亿元)×1e8 ÷ 收盘价(元)。"""
    return cap_yi * 1e8 / close


def estimate_cap_yi(close_unadj: float, float_shares: float) -> float:
    """历史流通市值(亿元) = 不复权收盘价 × 流通股本 ÷ 1e8。"""
    return close_unadj * float_shares / 1e8


def in_cap_band(cap_yi: float) -> bool:
    """是否落在 50-500 亿市值带。"""
    return MARKET_CAP_MIN <= cap_yi <= MARKET_CAP_MAX
