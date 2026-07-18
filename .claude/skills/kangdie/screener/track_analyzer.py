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
