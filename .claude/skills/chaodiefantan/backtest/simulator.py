"""纪律退出模拟纯函数 — 硬止损① + 被动跟踪② + 10日强平③。

输入买入日起的日K(bars[0]=买入日T)，逐日判定出场。TDD 可单测。
详见 spec §6.2。
"""
MAX_HOLD_DAYS = 10


def simulate_exit(bars: list[dict], buy_price: float, stop_loss: float,
                  max_hold: int = MAX_HOLD_DAYS) -> dict:
    """模拟纪律退出。

    Args:
        bars: 买入日起的日K(按日期正序)，bars[0]=买入日T(不判定)，bars[1]=T+1…。
              每项需含 date/open/high/low/close。
        buy_price: 买入价(T日收盘 或 T+1开盘)。
        stop_loss: 硬止损位(信号日 T-1 最低，固定值)。
        max_hold: 最大持有交易日数(默认10)，含买入日算第0日。

    Returns:
        {exit_reason, exit_date, exit_price, hold_days}
        exit_reason ∈ {'stop_loss','trailing','timeout','data_end'}
        hold_days = 从买入日算起的出场日序号(T+1出场=1)。
    """
    if len(bars) < 2:
        return {"exit_reason": "data_end",
                "exit_date": bars[0]["date"] if bars else None,
                "exit_price": bars[0]["close"] if bars else buy_price,
                "hold_days": 0}

    for i in range(1, len(bars)):               # 从 T+1 起
        bar = bars[i]
        prev_low = bars[i - 1]["low"]
        # ① 硬止损: 盘中触及即以 stop_loss 出局(不看收盘)
        if bar["low"] <= stop_loss:
            return {"exit_reason": "stop_loss", "exit_date": bar["date"],
                    "exit_price": stop_loss, "hold_days": i}
        # ② 被动跟踪: 收盘跌破前一日最低 -> 当日收盘出局
        if bar["close"] < prev_low:
            return {"exit_reason": "trailing", "exit_date": bar["date"],
                    "exit_price": bar["close"], "hold_days": i}
        # ③ 持满 max_hold 日强平
        if i >= max_hold:
            return {"exit_reason": "timeout", "exit_date": bar["date"],
                    "exit_price": bar["close"], "hold_days": i}

    # 数据在持有期内结束(K线不够)
    last = bars[-1]
    return {"exit_reason": "data_end", "exit_date": last["date"],
            "exit_price": last["close"], "hold_days": len(bars) - 1}
