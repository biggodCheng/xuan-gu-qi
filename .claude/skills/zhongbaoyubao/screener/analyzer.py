"""分析层(纯逻辑,无网络):筛选预告、计算涨跌、到期判定。

可调阈值在顶部。watchlist 的 daily 系列计算口径:基准价=基准日(公告后首个交易日)开盘,
累计涨跌=(今收-基准价)/基准价;当日涨跌=(今收-昨收)/昨收。基准价与当前价同取自一条
前复权日K序列,避免除权失真。
"""

# ---- 可调阈值 ----
PREDICT_TYPE = "预增"      # 仅纳入预增(扭亏/续盈/略增本期不收)
YOY_LOWER_MIN = 50.0       # 同比下限 ≥ 50% 入池
HOLD_DAYS = 30             # 跟踪交易日数


def filter_announcements(items: list[dict], yoy_lower_min: float = YOY_LOWER_MIN,
                         predict_type: str = PREDICT_TYPE) -> list[dict]:
    """筛选达标预告:类型=预增 且同比下限≥阈值。

    Args:
        items: fetcher.get_announcements 返回的列表,每条含
               {code,name,industry,predict_type,notice_date,yoy_lower,yoy_upper}
    Returns:
        达标条目(原样透传,补 predict_type 缺省)。
    """
    out = []
    for it in items:
        if (it.get("predict_type") or "") != predict_type:
            continue
        lo = it.get("yoy_lower")
        if lo is None:
            continue
        try:
            lo_f = float(lo)
        except (TypeError, ValueError):
            continue
        if lo_f >= yoy_lower_min:
            out.append(it)
    return out
