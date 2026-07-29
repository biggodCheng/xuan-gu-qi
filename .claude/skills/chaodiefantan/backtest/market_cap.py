"""流通股本与历史市值估算 — 纯函数。

市值过滤:默认不卡市值(对齐实盘/策略意图);CAP_FILTER_ENABLED=1 时卡 30-100 亿。
股本视为 2.5 年常数(忽略解禁/增发)。详见 spec §4.3。
"""
from screener.analyzer import (  # noqa: E402
    CAP_FILTER_ENABLED, MARKET_CAP_MIN, MARKET_CAP_MAX)


def compute_float_shares(cap_yi: float, close: float) -> float:
    """流通股本(股) = 流通市值(亿元)×1e8 ÷ 收盘价(元)。"""
    return cap_yi * 1e8 / close


def estimate_cap_yi(close_unadj: float, float_shares: float) -> float:
    """历史流通市值(亿元) = 不复权收盘价 × 流通股本 ÷ 1e8。"""
    return close_unadj * float_shares / 1e8


def in_cap_band(cap_yi: float) -> bool:
    """是否落在市值带内。

    CAP_FILTER_ENABLED=1 时卡 30-100 亿;默认关闭(返回 True,不过滤)。
    """
    if not CAP_FILTER_ENABLED:
        return True
    return MARKET_CAP_MIN <= cap_yi <= MARKET_CAP_MAX


def shares_at_date(current_shares: float, div_records: list[dict],
                   date: str) -> float:
    """送转回推历史流通股本(修正市值偏差)。

    t日股本 = 当前股本 ÷ Π(t日之后所有送转事件的 (1+(送+转)/10))。
    派息不影响股本,忽略。详见 spec §4.3。

    Args:
        current_shares: 当前(最新)流通股本。
        div_records: 除权记录,每项含 ex_date('YYYY-MM-DD')/song(送股,每10股)/zhuan(转增)。
        date: 目标历史日 'YYYY-MM-DD'。
    """
    factor = 1.0
    for r in div_records:
        ex_date = r.get("ex_date")
        if not ex_date or ex_date <= date:
            continue                     # 只算 t 日之后的送转
        song = float(r.get("song") or 0)
        zhuan = float(r.get("zhuan") or 0)
        if song + zhuan > 0:
            factor *= 1 + (song + zhuan) / 10
    return current_shares / factor if factor > 0 else current_shares
