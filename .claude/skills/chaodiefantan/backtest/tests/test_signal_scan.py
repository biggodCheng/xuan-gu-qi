"""信号扫描与去重单测。"""
from backtest.signal_scan import dedup_signals, scan_signals
from backtest.market_cap import compute_float_shares


TRADING_DATES = [f"2024-03-{d:02d}" for d in range(11, 21)]  # 10个交易日


def _sig(code, date):
    return {"signal_date": date, "code": code, "name": code,
            "close_T": 10.0, "stop_loss": 9.0, "drop5": -18.0,
            "vol_ratio": 2.0, "market_cap_T": 100.0}


def test_dedup_same_stock_within_window():
    """同股5日内重复信号只留最早。"""
    sigs = [_sig("000001", "2024-03-11"), _sig("000001", "2024-03-13")]  # 差2日<=5
    out = dedup_signals(sigs, TRADING_DATES, window=5)
    assert len(out) == 1
    assert out[0]["signal_date"] == "2024-03-11"


def test_dedup_keep_after_window():
    """同股超过5日再触发,保留。"""
    # TRADING_DATES: 03-11(idx0), 03-16(idx5) 差5 <=5 去重
    sigs = [_sig("000001", "2024-03-11"), _sig("000001", "2024-03-16")]
    out = dedup_signals(sigs, TRADING_DATES, window=5)
    assert len(out) == 1
    # 03-17(idx6) 差6>5 保留
    sigs2 = [_sig("000001", "2024-03-11"), _sig("000001", "2024-03-17")]
    out2 = dedup_signals(sigs2, TRADING_DATES, window=5)
    assert len(out2) == 2


def test_dedup_different_stocks_independent():
    """不同股票互不影响。"""
    sigs = [_sig("000001", "2024-03-11"), _sig("000002", "2024-03-11")]
    out = dedup_signals(sigs, TRADING_DATES, window=5)
    assert len(out) == 2


def test_dedup_unsorted_input():
    """输入乱序也能正确去重(内部按code+date排序)。"""
    sigs = [_sig("000001", "2024-03-13"), _sig("000001", "2024-03-11")]
    out = dedup_signals(sigs, TRADING_DATES, window=5)
    assert len(out) == 1
    assert out[0]["signal_date"] == "2024-03-11"


def _make_kline():
    """构造一只股 7 日前复权K线,末日(T=2024-03-12)满足超跌反弹。"""
    bars = []
    for d in ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"]:
        bars.append({"date": d, "open": 12.5, "close": 12.5, "high": 13.0, "low": 12.0, "volume": 100})
    bars.append({"date": "2024-03-11", "open": 10.0, "close": 9.0, "high": 10.5, "low": 7.0, "volume": 50})   # T-1
    bars.append({"date": "2024-03-12", "open": 9.2, "close": 10.5, "high": 11.0, "low": 9.0, "volume": 100})  # T 阳包阴
    return bars


def test_scan_signals_finds_signal():
    bars = _make_kline()
    float_shares = compute_float_shares(cap_yi=200.0, close=10.5)  # 让市值=200亿
    sigs = scan_signals(
        klines_by_code={"000001": bars},
        float_shares_by_code={"000001": float_shares},
        names_by_code={"000001": "测试股"},
        trading_dates=["2024-03-12"],
    )
    assert len(sigs) == 1
    s = sigs[0]
    assert s["code"] == "000001"
    assert s["signal_date"] == "2024-03-12"
    assert s["stop_loss"] == 7.0
    assert 50 <= s["market_cap_T"] <= 500


def test_scan_signals_skips_when_cap_out_of_band():
    bars = _make_kline()
    sigs = scan_signals(
        klines_by_code={"000001": bars},
        float_shares_by_code={"000001": 1_000_000.0},  # 极小股本->市值<50亿
        names_by_code={"000001": "测试股"},
        trading_dates=["2024-03-12"],
    )
    assert len(sigs) == 0


def test_scan_signals_insufficient_history():
    """T 日之前不足 7 根 -> 不出信号。"""
    bars = _make_kline()[:6]  # 只6根
    float_shares = compute_float_shares(cap_yi=200.0, close=10.5)
    sigs = scan_signals(
        klines_by_code={"000001": bars},
        float_shares_by_code={"000001": float_shares},
        names_by_code={"000001": "测试股"},
        trading_dates=[bars[-1]["date"]],
    )
    assert len(sigs) == 0
