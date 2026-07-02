import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener import storage
from main import run


class FakeFetcher:
    def __init__(self):
        self.ann = [{
            "code": "600160", "name": "巨化股份", "industry": "化学制品",
            "notice_date": "2026-07-10", "predict_type": "预增",
            "yoy_lower": 80.0, "yoy_upper": 120.0,
        }]
        self.kline = {
            "600160": [
                {"date": "2026-07-11", "open": 10.0, "close": 10.0},
                {"date": "2026-07-14", "open": 10.1, "close": 11.0},
            ]
        }

    def get_announcements(self, **kw):
        return self.ann

    def get_kline_since(self, code, since_date):
        return self.kline.get(code, [])


def test_run_end_to_end(tmp_path):
    wl = str(tmp_path / "watchlist.json")
    out = str(tmp_path / "output")
    ok = run(today_str="2026-07-14", watchlist_path=wl, output_dir=out, fetcher=FakeFetcher())
    assert ok is True
    pool = storage.load_watchlist(wl)
    assert len(pool["active"]) == 1
    a = pool["active"][0]
    assert a["code"] == "600160"
    assert a["base_price"] == 10.0          # 次日开盘
    assert a["held_days"] == 1
    assert a["chg_total"] == 10.0           # (11-10)/10
    assert os.path.exists(os.path.join(out, "2026-07-14.md"))


def test_run_dedups_existing(tmp_path):
    wl = str(tmp_path / "watchlist.json")
    p = storage.empty_pool()
    storage.add_active(p, {"code": "600160", "name": "巨化股份", "notice_date": "2026-07-10"})
    storage.save_watchlist(p, wl)
    run(today_str="2026-07-14", watchlist_path=wl,
        output_dir=str(tmp_path / "o"), fetcher=FakeFetcher())
    pool = storage.load_watchlist(wl)
    assert len(pool["active"]) == 1  # 不重复入池


def test_run_retries_skipped(tmp_path):
    """skipped 中的股票应在下次执行时移回 active 重试,成功则清出 skipped。"""
    wl = str(tmp_path / "watchlist.json")
    p = storage.empty_pool()
    storage.add_skipped(p, "600160", "巨化股份", "2026-07-10", "K线拉取失败")
    storage.save_watchlist(p, wl)
    run(today_str="2026-07-14", watchlist_path=wl,
        output_dir=str(tmp_path / "o"), fetcher=FakeFetcher())
    pool = storage.load_watchlist(wl)
    assert len(pool["active"]) == 1   # skipped 转为 active
    assert len(pool["skipped"]) == 0  # skipped 清空
    assert pool["active"][0]["base_price"] == 10.0
