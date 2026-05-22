import json
import os
import tempfile

from screener.storage import load_results, save_results


def test_save_results_creates_file():
    """保存结果应创建 JSON 文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        stocks = [
            {"code": "000001", "name": "平安银行", "close": 15.23, "high_100d": 15.10}
        ]
        save_results("2026-05-22", stocks, tmpdir)

        filepath = os.path.join(tmpdir, "2026-05-22.json")
        assert os.path.exists(filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["date"] == "2026-05-22"
        assert data["description"] == "A股当日收盘价创100个交易日新高"
        assert data["count"] == 1
        assert len(data["stocks"]) == 1
        assert data["stocks"][0]["code"] == "000001"


def test_save_results_overwrites_existing():
    """已存在的文件应被覆盖"""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_results("2026-05-22", [], tmpdir)
        save_results("2026-05-22", [{"code": "000001", "name": "测试", "close": 10.0, "high_100d": 9.0}], tmpdir)

        data = load_results("2026-05-22", tmpdir)
        assert data["count"] == 1


def test_load_results_file_not_found():
    """文件不存在时返回 None"""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_results("2099-01-01", tmpdir)
        assert result is None


def test_save_results_creates_directory():
    """data 目录不存在时应自动创建"""
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = os.path.join(tmpdir, "sub", "dir")
        save_results("2026-05-22", [], nested)

        filepath = os.path.join(nested, "2026-05-22.json")
        assert os.path.exists(filepath)
