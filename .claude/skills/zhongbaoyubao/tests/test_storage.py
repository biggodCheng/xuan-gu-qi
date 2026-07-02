import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.storage import empty_pool, load_watchlist, save_watchlist


def test_empty_pool_shape():
    p = empty_pool()
    assert p["active"] == [] and p["expired"] == [] and p["skipped"] == []
    assert p["report_date"] == "2026-06-30"
    assert p["threshold"]["yoy_lower_min"] == 50.0


def test_save_then_load_roundtrip(tmp_path):
    path = str(tmp_path / "watchlist.json")
    p = empty_pool()
    p["active"].append({"code": "000001", "name": "平安银行"})
    save_watchlist(p, path)
    loaded = load_watchlist(path)
    assert loaded["active"][0]["code"] == "000001"


def test_load_missing_returns_empty_pool(tmp_path):
    path = str(tmp_path / "nope.json")
    p = load_watchlist(path)
    assert p["active"] == []


def test_load_corrupt_backups_and_rebuilds(tmp_path):
    path = str(tmp_path / "watchlist.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not valid json ")
    p = load_watchlist(path)
    assert p["active"] == []  # 重建空池
    assert os.path.exists(path + ".bad")  # 损坏文件已备份
