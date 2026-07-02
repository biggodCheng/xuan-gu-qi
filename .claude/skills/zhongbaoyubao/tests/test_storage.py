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


from screener.storage import existing_codes, add_active, refresh_active


def test_existing_codes_union(tmp_path):
    p = empty_pool()
    p["active"] = [{"code": "A"}]
    p["expired"] = [{"code": "B"}]
    p["skipped"] = [{"code": "C"}]
    assert existing_codes(p) == {"A", "B", "C"}


def test_add_active_appends(tmp_path):
    p = empty_pool()
    add_active(p, {"code": "A", "name": "X", "notice_date": "2026-07-10"})
    assert len(p["active"]) == 1
    assert p["active"][0]["daily"] == []
    assert p["active"][0]["held_days"] == 0


def test_refresh_active_overwrites_daily_and_fields(tmp_path):
    p = empty_pool()
    add_active(p, {"code": "A", "name": "X", "notice_date": "2026-07-10"})
    daily = [{"date": "2026-07-11", "close": 11.0, "chg_total": 10.0, "chg_today": 10.0}]
    refresh_active(p, "A", {
        "base_date": "2026-07-11", "base_price": 10.0,
        "daily": daily, "last_close": 11.0,
        "chg_total": 10.0, "chg_today": 10.0,
        "held_days": 1, "remain_days": 29,
    })
    a = p["active"][0]
    assert a["base_price"] == 10.0
    assert a["daily"] == daily          # 覆盖式
    assert a["last_close"] == 11.0
    assert a["held_days"] == 1


from screener.storage import migrate_expired, add_skipped, remove_skipped


def test_migrate_expired_moves_qualifying(tmp_path):
    p = empty_pool()
    p["active"] = [
        {"code": "A", "held_days": 29, "daily": [{"date": "x"}]},
        {"code": "B", "held_days": 30, "daily": [{"date": "y"}]},
    ]
    moved = migrate_expired(p)
    assert moved == ["B"]
    assert [a["code"] for a in p["active"]] == ["A"]
    assert [e["code"] for e in p["expired"]] == ["B"]


def test_add_and_remove_skipped(tmp_path):
    p = empty_pool()
    add_skipped(p, "C", "X", "2026-07-10", "K线拉取失败")
    assert len(p["skipped"]) == 1
    remove_skipped(p, "C")
    assert p["skipped"] == []
