"""抗跌反弹跟踪纯函数单测。"""
import sys, os
import warnings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.track_analyzer import align_after


def _bars(closes, key="day"):
    """构造 K 线序列（按日期正序），close 序列 → bars。key=day(个股)/date(指数)。"""
    return [{
        key: f"2026-07-{10 + i:02d}",
        "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100.0,
    } for i, c in enumerate(closes)]


def test_align_after_found():
    bars = _bars([100.0, 101.0, 99.0])
    after, d_close = align_after(bars, "2026-07-10")
    assert d_close == 100.0
    assert len(after) == 2
    assert after[0]["close"] == 101.0


def test_align_after_index_uses_date_key():
    bars = _bars([200.0, 198.0], key="date")
    after, d_close = align_after(bars, "2026-07-10")
    assert d_close == 200.0
    assert len(after) == 1


def test_align_after_not_found():
    bars = _bars([100.0, 101.0])
    assert align_after(bars, "2025-01-01") is None


def test_align_after_d_is_last():
    bars = _bars([100.0, 101.0])
    after, d_close = align_after(bars, "2026-07-11")
    assert d_close == 101.0
    assert after == []


def _gap_bars():
    """构造跳过周末的交易日序列: 07-16(周四)/07-17(周五)/07-20(周一)。"""
    return [{"day": d, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100.0}
            for d, c in zip(["2026-07-16", "2026-07-17", "2026-07-20"], [10.0, 11.0, 12.0])]


def test_align_after_fallback_to_prior_trading_day():
    """drop_date 是非交易日(K线不存在,如周末命名错位)时,回退到 <=drop_date 的最近交易日作 D,并告警。

    复现 2026-07 修复的 bug: kd 文件名错用 07-18(周六),K线只有交易日,严格匹配会返回 None。
    """
    bars = _gap_bars()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        after, d_close = align_after(bars, "2026-07-18")  # 周六,K线里不存在
    assert d_close == 11.0                              # 回退到 07-17 周五收盘
    assert [b["day"] for b in after] == ["2026-07-20"]   # D 之后只剩 07-20
    assert len(w) == 1 and "2026-07-17" in str(w[0].message)  # 告警指明回退到的交易日


from screener.track_analyzer import window_return


def test_window_return_normal():
    after = _bars([101.0, 102.0, 103.0, 104.0, 105.0])
    assert window_return(after, 100.0, 5) == 5.0


def test_window_return_insufficient():
    after = _bars([101.0, 102.0])
    assert window_return(after, 100.0, 5) is None


def test_window_return_negative():
    after = _bars([98.0, 97.0, 96.0])
    assert window_return(after, 100.0, 3) == -4.0


def test_window_return_zero_base():
    after = _bars([101.0])
    assert window_return(after, 0.0, 1) is None


from screener.track_analyzer import mfe_mae, end_return


def test_mfe_mae_normal():
    after = _bars([101.0, 105.0, 99.0])
    mfe, mae = mfe_mae(after, 100.0)
    assert mfe == 6.0
    assert mae == -2.0


def test_mfe_mae_empty():
    assert mfe_mae([], 100.0) == (None, None)
    assert mfe_mae([{"close": 1}], 0.0) == (None, None)


def test_end_return_normal():
    after = _bars([101.0, 102.0, 98.0])
    assert end_return(after, 100.0) == -2.0


def test_end_return_empty():
    assert end_return([], 100.0) is None


from screener.track_analyzer import first_rebound, is_mature


def test_first_rebound_true():
    after = _bars([101.0, 103.0, 105.0])
    idx_after = _bars([100.5, 101.0, 102.0], key="date")
    assert first_rebound(after, 100.0, idx_after, 100.0) is True


def test_first_rebound_stock_dropped():
    after = _bars([99.0, 98.5, 98.0])
    idx_after = _bars([99.0, 98.0, 97.0], key="date")
    assert first_rebound(after, 100.0, idx_after, 100.0) is False


def test_first_rebound_stock_up_but_underperform():
    after = _bars([101.0, 101.5, 102.0])
    idx_after = _bars([103.0, 104.0, 105.0], key="date")
    assert first_rebound(after, 100.0, idx_after, 100.0) is False


def test_first_rebound_insufficient():
    after = _bars([101.0, 102.0])
    idx_after = _bars([101.0, 102.0], key="date")
    assert first_rebound(after, 100.0, idx_after, 100.0) is None


def test_is_mature():
    assert is_mature([]) is False
    assert is_mature(_bars([1.0] * 19)) is False
    assert is_mature(_bars([1.0] * 20)) is True
    assert is_mature(_bars([1.0] * 25)) is True
