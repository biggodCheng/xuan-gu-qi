"""纪律退出模拟单测 — 构造 K 线验三种出场。"""
from backtest.simulator import simulate_exit


def _bar(date, open_, close, high, low, volume=100):
    return {"date": date, "open": open_, "close": close, "high": high, "low": low, "volume": volume}


def _base_bars():
    """买入日 T + 之后若干日。buy_price=10.0, stop_loss=9.0(固定T-1最低)。"""
    return [
        _bar("2024-03-11", 9.5, 10.0, 10.2, 9.4),   # bars[0]=买入日T, 不判定
        _bar("2024-03-12", 10.0, 10.5, 10.6, 9.9),   # T+1
        _bar("2024-03-13", 10.5, 10.8, 11.0, 10.4),  # T+2
    ]


def test_stop_loss_triggered():
    """① 硬止损: T+1 当日 low<=stop_loss(9.0) -> 以 stop_loss 出局。"""
    bars = _base_bars()
    bars[1]["low"] = 8.8  # 盘中砸穿 stop_loss
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0)
    assert r["exit_reason"] == "stop_loss"
    assert r["exit_price"] == 9.0
    assert r["hold_days"] == 1
    assert r["exit_date"] == "2024-03-12"


def test_trailing_exit():
    """② 被动跟踪: T+2 close < T+1 low -> 以 T+2 close 出局。"""
    bars = _base_bars()
    # T+1 close=10.5 low=9.9; T+2 close 跌破 9.9
    bars[2]["close"] = 9.8
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0)
    assert r["exit_reason"] == "trailing"
    assert r["exit_price"] == 9.8
    assert r["hold_days"] == 2


def test_first_day_trailing():
    """② T+1 当天 close<T日low(买入日)即出局(基准=买入日low)。"""
    bars = _base_bars()
    bars[1]["close"] = 9.3  # < bars[0].low=9.4
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0)
    assert r["exit_reason"] == "trailing"
    assert r["hold_days"] == 1


def test_stop_loss_priority_over_trailing():
    """①②同日: low<=stop_loss 且 close<前日low -> 止损优先(以stop_loss价)。"""
    bars = _base_bars()
    bars[1]["low"] = 8.5    # 触发①
    bars[1]["close"] = 9.0  # 同时<T日low(9.4) 触发②
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0)
    assert r["exit_reason"] == "stop_loss"
    assert r["exit_price"] == 9.0


def test_timeout_force_close():
    """③ 持满10日未触发 -> 第10日(T+10)收盘强平。"""
    bars = [_bar(f"2024-03-{11+i:02d}", 10.0, 10.1, 10.3, 9.9) for i in range(12)]
    # 全程 low>9.0, close>=前日low(9.9), 不触发①②
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0, max_hold=10)
    assert r["exit_reason"] == "timeout"
    assert r["hold_days"] == 10
    assert r["exit_price"] == bars[10]["close"]


def test_data_end_before_hold():
    """K线在持有期内结束(数据不足) -> 以最后一根收盘,标记data_end。"""
    bars = _base_bars()  # 只有3根(T/T+1/T+2)
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0, max_hold=10)
    assert r["exit_reason"] == "data_end"
    assert r["hold_days"] == 2
    assert r["exit_date"] == "2024-03-13"


def test_buy_day_not_judged():
    """买入日(T)当天不判定(low下穿也不出场)。"""
    bars = _base_bars()
    bars[0]["low"] = 7.0  # 买入日盘中破stop_loss,但当天不判
    bars[1]["close"] = 10.5
    bars[2]["close"] = 11.0
    bars += [_bar("2024-03-14", 11.0, 11.1, 11.2, 10.9) for _ in range(9)]
    r = simulate_exit(bars, buy_price=10.0, stop_loss=9.0, max_hold=10)
    assert r["exit_reason"] == "timeout"
