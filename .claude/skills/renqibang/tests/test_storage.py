import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.storage import save_results, load_results


def test_save_then_load_roundtrip(tmp_path):
    out = str(tmp_path)
    stocks = [{"rank": 1, "code": "600000", "name": "浦发银行",
               "popularity": 426283, "rank_change": "+5",
               "industry": "银行", "concepts": ["沪股通"], "reason": "沪股通"}]
    path = save_results("2026-07-14", "热度榜", stocks, out)
    assert path.endswith("popularity_2026-07-14.json")
    loaded = load_results("2026-07-14", out)
    assert loaded["date"] == "2026-07-14"
    assert loaded["sort"] == "热度榜"
    assert loaded["count"] == 1
    assert loaded["stocks"][0]["code"] == "600000"
    assert loaded["stocks"][0]["concepts"] == ["沪股通"]


def test_load_missing_returns_none(tmp_path):
    assert load_results("2099-01-01", str(tmp_path)) is None


def test_save_overwrites_same_date(tmp_path):
    out = str(tmp_path)
    save_results("2026-07-14", "热度榜", [], out)
    save_results("2026-07-14", "热度榜", [{"rank": 1, "code": "000001"}], out)
    loaded = load_results("2026-07-14", out)
    assert loaded["count"] == 1  # 覆盖而非追加
