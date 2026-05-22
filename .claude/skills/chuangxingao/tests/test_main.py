import json
import os
import sys
import tempfile
from unittest.mock import patch

import pandas as pd

# Ensure chuangxingao root is on sys.path so main module can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import run_screener


def _make_today_df():
    return pd.DataFrame({
        "code": ["000001", "000002"],
        "name": ["平安银行", "万科A"],
        "close": [20.0, 10.0],
    })


def _make_history_high():
    return [18.0, 19.0, 19.5, 17.0]


def _make_history_low():
    return [11.0, 12.0, 10.5, 10.0]


@patch("main.get_stock_history")
@patch("main.get_all_stocks_today")
def test_run_screener_filters_correctly(mock_today, mock_history):
    """应只保存创新高的股票"""
    mock_today.return_value = _make_today_df()
    mock_history.side_effect = lambda code, **kw: (
        _make_history_high() if code == "000001" else _make_history_low()
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        run_screener(output_dir=tmpdir)

        date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
        filepath = os.path.join(tmpdir, f"{date_str}.json")
        assert os.path.exists(filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["count"] == 1
        assert data["stocks"][0]["code"] == "000001"


@patch("main.get_stock_history")
@patch("main.get_all_stocks_today")
def test_run_screener_no_data_today(mock_today, mock_history):
    """无行情数据时应提示非交易日"""
    mock_today.return_value = pd.DataFrame(columns=["code", "name", "close"])

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_screener(output_dir=tmpdir)
        assert result is False
