import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.fetcher import get_concept_sectors, get_sector_kline


def test_get_concept_sectors_parses_response():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "total": 2,
            "diff": [
                {"f12": "BK0001", "f14": "测试板块A", "f2": 1234.56, "f3": 2.35, "f4": 28.5},
                {"f12": "BK0002", "f14": "测试板块B", "f2": 5678.90, "f3": -1.20, "f4": -68.3},
            ],
        }
    }

    with patch("screener.fetcher._session") as mock_session:
        mock_session.get.return_value = mock_resp
        result = get_concept_sectors()

    assert len(result) == 2
    assert result[0]["code"] == "BK0001"
    assert result[0]["name"] == "测试板块A"
    assert result[0]["close"] == 1234.56
    assert result[0]["change_pct"] == 2.35


def test_get_concept_sectors_filters_zero_close():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "total": 2,
            "diff": [
                {"f12": "BK0001", "f14": "有效板块", "f2": 100.0, "f3": 1.0, "f4": 1.0},
                {"f12": "BK0002", "f14": "无效板块", "f2": 0, "f3": 0, "f4": 0},
            ],
        }
    }

    with patch("screener.fetcher._session") as mock_session:
        mock_session.get.return_value = mock_resp
        result = get_concept_sectors()

    assert len(result) == 1
    assert result[0]["code"] == "BK0001"


def test_get_concept_sectors_empty_response():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"total": 0, "diff": []}}

    with patch("screener.fetcher._session") as mock_session:
        mock_session.get.return_value = mock_resp
        result = get_concept_sectors()

    assert result == []


def test_get_sector_kline_parses_response():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "klines": [
                "2026-05-20,1000,1010,1020,990,5000000",
                "2026-05-21,1010,1020,1030,1000,6000000",
            ]
        }
    }

    with patch("screener.fetcher._session") as mock_session:
        mock_session.get.return_value = mock_resp
        result = get_sector_kline("BK0001")

    assert len(result) == 2
    assert result[0]["date"] == "2026-05-20"
    assert result[0]["close"] == 1010.0
    assert result[0]["high"] == 1020.0
    assert result[0]["low"] == 990.0
    assert result[1]["volume"] == 6000000.0


def test_get_sector_kline_empty_response():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"klines": []}}

    with patch("screener.fetcher._session") as mock_session:
        mock_session.get.return_value = mock_resp
        result = get_sector_kline("BK0001")

    assert result == []


def test_get_sector_kline_error_returns_empty():
    with patch("screener.fetcher._session") as mock_session:
        mock_session.get.side_effect = Exception("network error")
        result = get_sector_kline("BK0001")

    assert result == []
