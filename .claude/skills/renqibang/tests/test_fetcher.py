import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener import fetcher


def test_build_secid_sh():
    assert fetcher.build_secid("600000") == "1.600000"


def test_build_secid_sz():
    assert fetcher.build_secid("000001") == "0.000001"


def test_build_secid_cy():
    assert fetcher.build_secid("300750") == "0.300750"


def test_build_secid_bj():
    assert fetcher.build_secid("920001") == "0.920001"


def test_fetch_industry_concepts_parses(monkeypatch):
    payload = {"data": {"f57": "600000", "f58": "浦发银行",
                        "f127": "银行", "f129": "沪股通,融资融券,标准券"}}
    monkeypatch.setattr(fetcher, "_request_push2", lambda secid: payload)
    r = fetcher.fetch_industry_concepts("600000")
    assert r["industry"] == "银行"
    assert r["concepts"] == ["沪股通", "融资融券", "标准券"]
    assert r["name"] == "浦发银行"


def test_fetch_industry_concepts_empty_fields(monkeypatch):
    payload = {"data": {"f127": "", "f129": "", "f58": ""}}
    monkeypatch.setattr(fetcher, "_request_push2", lambda secid: payload)
    r = fetcher.fetch_industry_concepts("600000")
    assert r["industry"] == ""
    assert r["concepts"] == []
    assert r["name"] == ""


def test_fetch_industry_concepts_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(fetcher, "_request_push2", lambda secid: {})
    r = fetcher.fetch_industry_concepts("600000")
    assert r == {"industry": "", "concepts": [], "name": ""}


def test_fetch_industry_for_stocks_fills_inplace(monkeypatch):
    monkeypatch.setattr(fetcher, "_request_push2",
                        lambda secid: {"data": {"f127": "电子", "f129": "AI算力,芯片", "f58": "东方电子"}})
    stocks = [{"code": "600000"}, {"code": "000001"}]
    fetcher.fetch_industry_for_stocks(stocks, max_workers=2)
    assert stocks[0]["industry"] == "电子"
    assert stocks[0]["concepts"] == ["AI算力", "芯片"]
    assert stocks[0]["reason"] == "AI算力,芯片"
    assert stocks[1]["industry"] == "电子"
    assert stocks[0]["name"] == "东方电子"   # DOM name 空 → 被 f58 补全

    stocks2 = [{"code": "600000", "name": "已有名"}]
    fetcher.fetch_industry_for_stocks(stocks2, max_workers=2)
    assert stocks2[0]["name"] == "已有名"   # 不覆盖非空 name


def test_sweep_retries_empty_then_succeeds(monkeypatch):
    """首轮 push2 空响应(突发), sweep 重试后补全。"""
    seen = {}

    def fake(secid):
        code = secid.split(".")[-1]
        n = seen.get(code, 0) + 1
        seen[code] = n
        if n == 1:
            return {}   # 首轮空(模拟突发空响应)
        return {"data": {"f127": "电子", "f129": "芯片", "f58": "东晶"}}

    monkeypatch.setattr(fetcher, "_request_push2", fake)
    stocks = [{"code": "000001"}]
    fetcher.fetch_industry_for_stocks(stocks, max_workers=2, sweeps=3)
    assert stocks[0]["industry"] == "电子"
    assert stocks[0]["name"] == "东晶"
    assert seen["000001"] >= 2   # 被重试过
