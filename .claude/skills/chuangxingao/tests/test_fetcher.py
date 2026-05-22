from unittest.mock import patch
import pandas as pd

from screener.fetcher import get_all_stocks_today, get_stock_history


def test_get_all_stocks_today():
    fake_df = pd.DataFrame({
        "代码": ["000001", "000002"],
        "名称": ["平安银行", "万科A"],
        "最新价": [15.23, 10.50],
    })
    with patch("screener.fetcher.ak.stock_zh_a_spot_em", return_value=fake_df):
        result = get_all_stocks_today()

    assert list(result.columns) == ["code", "name", "close"]
    assert len(result) == 2
    assert result.iloc[0]["code"] == "000001"
    assert result.iloc[0]["name"] == "平安银行"
    assert result.iloc[0]["close"] == 15.23


def test_get_all_stocks_today_filters_invalid():
    fake_df = pd.DataFrame({
        "代码": ["000001", "688001", "300001"],
        "名称": ["平安银行", "华兴源创", "特锐德"],
        "最新价": [15.23, 50.0, 20.0],
    })
    with patch("screener.fetcher.ak.stock_zh_a_spot_em", return_value=fake_df):
        result = get_all_stocks_today()

    codes = result["code"].tolist()
    assert "000001" in codes
    assert "688001" in codes
    assert "300001" in codes


def test_get_all_stocks_today_empty():
    fake_df = pd.DataFrame(columns=["代码", "名称", "最新价"])
    with patch("screener.fetcher.ak.stock_zh_a_spot_em", return_value=fake_df):
        result = get_all_stocks_today()
    assert len(result) == 0


def test_get_stock_history():
    fake_df = pd.DataFrame({
        "日期": ["2026-05-20", "2026-05-21", "2026-05-22"],
        "收盘": [14.0, 14.5, 15.0],
    })
    with patch("screener.fetcher.ak.stock_zh_a_hist", return_value=fake_df):
        result = get_stock_history("000001", days=120)
    assert result == [14.0, 14.5, 15.0]


def test_get_stock_history_excludes_today():
    fake_df = pd.DataFrame({
        "日期": ["2026-05-20", "2026-05-21", "2026-05-22"],
        "收盘": [14.0, 14.5, 15.0],
    })
    with patch("screener.fetcher.ak.stock_zh_a_hist", return_value=fake_df):
        result = get_stock_history("000001", days=120, exclude_last=True)
    assert result == [14.0, 14.5]


def test_get_stock_history_empty():
    fake_df = pd.DataFrame(columns=["日期", "收盘"])
    with patch("screener.fetcher.ak.stock_zh_a_hist", return_value=fake_df):
        result = get_stock_history("000001")
    assert result == []


def test_get_stock_history_error_returns_empty():
    with patch("screener.fetcher.ak.stock_zh_a_hist", side_effect=Exception("timeout")):
        result = get_stock_history("000001")
    assert result == []
