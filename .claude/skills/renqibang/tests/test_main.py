import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener import storage
from main import run


class FakeBrowser:
    def fetch_top100(self, sort="热度榜", headless=True):
        # 模拟 DOM name 为空(真实情况), 由 FakeFetcher 补
        return [
            {"rank": 1, "code": "600000", "name": "", "popularity": 13.42, "rank_change": "+5"},
            {"rank": 2, "code": "000001", "name": "", "popularity": 20.0, "rank_change": "-2"},
        ]


class FakeFetcher:
    def fetch_industry_for_stocks(self, stocks, max_workers=10):
        m = {"600000": ("银行", ["沪股通", "融资融券"], "浦发银行"),
             "000001": ("银行", ["沪深300"], "平安银行")}
        for s in stocks:
            ind, concepts, name = m.get(s["code"], ("", [], ""))
            s["industry"] = ind
            s["concepts"] = concepts
            s["reason"] = ",".join(concepts)
            if not s.get("name"):
                s["name"] = name
            s["rank_change"] = s.get("rank_change", "")


def test_run_end_to_end(tmp_path):
    out = str(tmp_path)
    ok = run(today_str="2026-07-14", output_dir=out,
             browser=FakeBrowser(), fetcher=FakeFetcher())
    assert ok is True
    loaded = storage.load_results("2026-07-14", out)
    assert loaded["count"] == 2
    s0 = loaded["stocks"][0]
    assert s0["code"] == "600000"
    assert s0["name"] == "浦发银行"   # DOM 空 → 被 fetcher 补全
    assert s0["industry"] == "银行"
    assert s0["concepts"] == ["沪股通", "融资融券"]
    assert s0["reason"] == "沪股通,融资融券"


def test_run_overwrites_same_date(tmp_path):
    out = str(tmp_path)
    run(today_str="2026-07-14", output_dir=out, browser=FakeBrowser(), fetcher=FakeFetcher())
    run(today_str="2026-07-14", output_dir=out, browser=FakeBrowser(), fetcher=FakeFetcher())
    loaded = storage.load_results("2026-07-14", out)
    assert loaded["count"] == 2  # 覆盖不追加


def test_run_empty_list_still_saves(tmp_path):
    out = str(tmp_path)

    class EmptyBrowser:
        def fetch_top100(self, sort="热度榜", headless=True):
            return []

    ok = run(today_str="2026-07-14", output_dir=out,
             browser=EmptyBrowser(), fetcher=FakeFetcher())
    assert ok is True
    loaded = storage.load_results("2026-07-14", out)
    assert loaded["count"] == 0
