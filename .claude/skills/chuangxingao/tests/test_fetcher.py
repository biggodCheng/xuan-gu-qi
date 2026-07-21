from unittest.mock import patch, MagicMock

import pytest
from screener.fetcher import get_all_stocks_today, get_stock_history


@pytest.fixture(autouse=True)
def _disable_local_kline(monkeypatch):
    """既有网络测试默认禁用本地源(走腾讯/新浪, 测原 fallback 逻辑)。
    本地优先逻辑由 test_fetcher_local.py 单独覆盖。"""
    from screener import fetcher
    if hasattr(fetcher, "local_kline"):
        monkeypatch.setattr(fetcher.local_kline, "read_day", lambda *a, **k: [])


def _fake_stock_list():
    return [
        {"code": "000001", "name": "平安银行", "trade": "15.23"},
        {"code": "000002", "name": "万科A", "trade": "10.50"},
    ]


def _fake_kline():
    return [
        {"day": "2026-05-20", "close": "14.0"},
        {"day": "2026-05-21", "close": "14.5"},
        {"day": "2026-05-22", "close": "15.0"},
    ]


def test_get_all_stocks_today():
    mock_resp_page1 = MagicMock()
    mock_resp_page1.json.return_value = _fake_stock_list()
    mock_resp_page2 = MagicMock()
    mock_resp_page2.json.return_value = []  # 第二页返回空，终止分页

    with patch("screener.fetcher._session.get", side_effect=[mock_resp_page1, mock_resp_page2]):
        result = get_all_stocks_today()

    assert list(result.columns) == ["code", "name", "close"]
    assert len(result) == 2
    assert result.iloc[0]["code"] == "000001"
    assert result.iloc[0]["name"] == "平安银行"
    assert result.iloc[0]["close"] == 15.23


def test_get_all_stocks_today_filters_zero_price():
    data = [
        {"code": "000001", "name": "平安银行", "trade": "15.23"},
        {"code": "000002", "name": "停牌股", "trade": "0"},
    ]
    mock_resp1 = MagicMock()
    mock_resp1.json.return_value = data
    mock_resp2 = MagicMock()
    mock_resp2.json.return_value = []

    with patch("screener.fetcher._session.get", side_effect=[mock_resp1, mock_resp2]):
        result = get_all_stocks_today()

    assert len(result) == 1
    assert result.iloc[0]["code"] == "000001"


def test_get_all_stocks_today_empty():
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    with patch("screener.fetcher._session.get", return_value=mock_resp):
        result = get_all_stocks_today()
    assert len(result) == 0


def test_get_stock_history():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _fake_kline()
    with patch("screener.fetcher._session.get", return_value=mock_resp):
        result = get_stock_history("000001", days=100)
    assert result == [14.0, 14.5, 15.0]


def test_get_stock_history_excludes_today():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _fake_kline()
    with patch("screener.fetcher._session.get", return_value=mock_resp):
        result = get_stock_history("000001", days=100, exclude_last=True)
    assert result == [14.0, 14.5]


def test_get_stock_history_empty():
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    with patch("screener.fetcher._session.get", return_value=mock_resp):
        result = get_stock_history("000001")
    assert result == []


def test_get_stock_history_error_returns_empty():
    with patch("screener.fetcher._session.get", side_effect=Exception("timeout")):
        result = get_stock_history("000001")
    assert result == []


def test_get_stock_history_fallback_when_tencent_sparse():
    """腾讯返回数据过少（残缺，如北交所只给 1 条）时应回退新浪取完整历史。

    复现真实 bug：腾讯对 920xxx 只返回 1 条（=今日价），新浪却有完整数据。
    """
    fake_sina = MagicMock()
    fake_sina.json.return_value = [
        {"day": f"2026-01-{i:02d}", "close": str(10 + i)} for i in range(1, 11)
    ]
    with patch("screener.fetcher._fetch_tencent_closes", return_value=[12.02]), \
         patch("screener.fetcher._session.get", return_value=fake_sina):
        result = get_stock_history("920000", days=100)

    assert len(result) == 10  # 用新浪的完整 10 条，而非腾讯残缺的 1 条
    assert result != [12.02]
