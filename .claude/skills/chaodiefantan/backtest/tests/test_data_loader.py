"""数据加载层测试 — 列名标准化/缓存往返/茅台复权sanity。"""
import pandas as pd

from backtest.data_loader import standardize_kline, save_cache, load_cache, fetch_kline


def test_standardize_kline_renames_columns():
    df = pd.DataFrame([{
        "日期": "2024-06-19", "股票代码": "600519", "开盘": 1497.99,
        "收盘": 1501.0, "最高": 1504.0, "最低": 1482.1, "成交量": 41262,
    }])
    out = standardize_kline(df)
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["close"] == 1501.0
    assert out.iloc[0]["date"] == "2024-06-19"


def test_cache_roundtrip(tmp_path):
    df = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "open": [10.0, 10.5],
                       "high": [10.5, 10.8], "low": [9.8, 10.3],
                       "close": [10.2, 10.6], "volume": [100, 200]})
    path = str(tmp_path / "k.parquet")
    save_cache(df, path)
    loaded = load_cache(path)
    assert len(loaded) == 2
    assert loaded.iloc[1]["close"] == 10.6


def test_mtf_dividend_qfq_smooth():
    """茅台 2024-06-19 除权日: 前复权下 6-19 相对 6-18 不应有大跌跳口(不复权约-1.3%)。"""
    df = fetch_kline("600519", start="2024-06-17", end="2024-06-21", adjust="qfq")
    if df is None or len(df) < 3:
        import pytest
        pytest.skip("akshare/东财网络不可用,跳过复权sanity")
    by_date = {r["date"]: r["close"] for _, r in df.iterrows()}
    c18, c19 = by_date.get("2024-06-18"), by_date.get("2024-06-19")
    assert c18 is not None and c19 is not None
    chg = (c19 - c18) / c18 * 100
    # 不复权约-1.3%除权跳口;前复权应消除,chg 在 [-1, 3] 区间(非-1.3以下)
    assert chg > -1.0, f"前复权除权日仍跳口 {chg:.2f}%，复权异常"
