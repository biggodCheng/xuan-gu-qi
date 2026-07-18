"""信号扫描与去重单测。"""
from backtest.signal_scan import dedup_signals


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
