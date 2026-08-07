# -*- coding: utf-8 -*-
"""波段超跌反弹判定纯函数 — 无网络、无副作用, 可单测。

与 screener.analyzer.is_oversold_rebound 的区别(直击痛点):
  - 超跌窗口 5日→20日(月度级波段, 对齐"跌一个月")
  - 删除 T-1 长下影条件(现有策略 37→1 的瓶颈, 抓不到突发反弹)
  - 保留 T日放量阳包阴(资金进场确认)
  - T-1缩量改为可选(use_shrink, 回测对比有/无)
  - 超跌口径可选(use_t1_drop, 对比含T日 vs 不含T日, spec §3)

bar 格式: {date/open/high/low/close, volume 或 vol}, 按日期正序,
最后一个=T日, 倒数第二=T-1。详见 spec §3。
"""
DROP_WINDOW = 20          # 近20日超跌窗口(≈一个月)
SHRINK_RATIO = 0.8        # T-1 相对前4日均量的缩量阈值


def _get(bar: dict, *keys):
    """从 bar 取第一个存在的键值(兼容 volume/vol)。"""
    for k in keys:
        if k in bar:
            return bar[k]
    raise KeyError(f"none of {keys} found in bar")


def is_band_rebound(bars: list[dict], market_cap: float | None = None,
                    drop_pct: float = 20.0, vol_ratio: float = 1.5,
                    use_shrink: bool = False, use_t1_drop: bool = False
                    ) -> dict | None:
    """波段超跌反弹判定。

    Args:
        bars: 日K列表(正序), bars[-1]=T日, 需 >= DROP_WINDOW+1=21 根(use_t1_drop 需 22)。
        market_cap: 流通市值(亿, 仅展示, 不过滤)。
        drop_pct: 超跌幅度阈值(%), 跌幅 <= -drop_pct 才算超跌。
        vol_ratio: T日放量倍数, vol[T] >= vol[T-1] * vol_ratio。
        use_shrink: 是否要求 T-1 缩量(vol[T-1] < 前4日均量×0.8)。
        use_t1_drop: 超跌口径。False=含T日 close[T]/close[T-20](标准20日跌幅);
            True=不含T日 close[T-1]/close[T-21](避免 T 日反弹抵消跌幅, spec §3 待对比项)。

    Returns:
        通过返回 {drop20, vol_ratio, stop_loss}; 不通过 None。
        stop_loss = T-1 日最低(破即止损)。
    """
    if len(bars) < DROP_WINDOW + 1:
        return None

    t1 = bars[-1]      # T 日
    t2 = bars[-2]      # T-1 日
    t20 = bars[-(DROP_WINDOW + 1)]   # 20 日前

    # 条件A: 近20日超跌(两种口径, spec §3 对比)
    if use_t1_drop:
        if len(bars) < DROP_WINDOW + 2:
            return None
        base_close = bars[-(DROP_WINDOW + 2)]["close"]   # close[T-21]
        ref_close = t2["close"]                          # close[T-1]
    else:
        base_close = t20["close"]                        # close[T-20]
        ref_close = t1["close"]                          # close[T]
    if base_close <= 0:
        return None
    drop20 = (ref_close - base_close) / base_close * 100
    if drop20 > -drop_pct:
        return None

    # 条件B: T 日阳包阴(阳线 + 收复前日开盘 + 破前日高)
    o1, c1 = t1["open"], t1["close"]
    o2 = t2["open"]
    if c1 <= o1:                        # 非阳线
        return None
    if c1 <= o2:                        # 未收复前日开盘
        return None
    if _get(t1, "high") <= _get(t2, "high"):   # 未突破前日高
        return None

    # 条件C: T 日放量
    v1 = _get(t1, "volume", "vol")
    v2 = _get(t2, "volume", "vol")
    if v2 <= 0 or v1 < v2 * vol_ratio:
        return None

    # 条件D(可选): T-1 缩量(相对前 4 日均量)
    if use_shrink:
        prev4 = [_get(bars[i], "volume", "vol") for i in range(-6, -2)]
        vol_prev_mean = sum(prev4) / 4
        if vol_prev_mean <= 0 or v2 >= vol_prev_mean * SHRINK_RATIO:
            return None

    return {
        "drop20": round(drop20, 2),
        "vol_ratio": round(v1 / v2, 2),
        "stop_loss": round(_get(t2, "low"), 2),   # 止损 = T-1 最低
    }
