"""fetcher 测试: parse / dedup / fetch_top_flows。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener import fetcher


def test_parse_maps_all_fields():
    raw = {"f12": "BK1283", "f14": "银行", "f3": 1.04,
           "f62": 1527127040, "f184": 4.3, "f66": 1108062464, "f72": 419064576}
    r = fetcher.parse(raw)
    assert r["code"] == "BK1283"
    assert r["name"] == "银行"
    assert r["change_pct"] == 1.04
    assert r["main_net"] == 1527127040
    assert r["main_net_yi"] == 15.27          # ÷1e8 保留两位
    assert r["main_pct"] == 4.3
    assert r["super_large_net"] == 1108062464
    assert r["large_net"] == 419064576


def test_parse_negative_flow():
    raw = {"f12": "BK0xxx", "f14": "电子", "f3": -4.23,
           "f62": -559410000, "f184": -8.64, "f66": -300000000, "f72": -150000000}
    r = fetcher.parse(raw)
    assert r["main_net_yi"] == -5.59
    assert r["change_pct"] == -4.23


def test_dedup_merges_same_flow_keeps_no_suffix():
    """银行(一级) 与 银行Ⅱ(二级) f62/f184 相同 → 合并为一个, 保留无后缀的'银行'。"""
    items = [
        {"name": "银行Ⅱ", "main_net": 1527127040, "main_pct": 4.3},
        {"name": "银行",   "main_net": 1527127040, "main_pct": 4.3},
    ]
    out = fetcher.dedup(items)
    assert len(out) == 1
    assert out[0]["name"] == "银行"


def test_dedup_keeps_different_flows():
    """通信(-212) 与 通信设备(-209) f62 不同 → 都保留。"""
    items = [
        {"name": "通信",     "main_net": -21205000000, "main_pct": -11.24},
        {"name": "通信设备", "main_net": -20909000000, "main_pct": -11.89},
    ]
    out = fetcher.dedup(items)
    assert len(out) == 2


def test_dedup_skips_none_main_net():
    items = [
        {"name": "停牌行业", "main_net": None, "main_pct": None},
        {"name": "银行", "main_net": 1000, "main_pct": 5},
    ]
    out = fetcher.dedup(items)
    assert len(out) == 1
    assert out[0]["name"] == "银行"


def test_fetch_top_flows_calls_both_orders(monkeypatch):
    """应发 po=1(降序/流入) + po=0(升序/流出) 两次请求, 返回 inflow/outflow。"""
    calls = []

    def fake_request(po, pz):
        calls.append((po, pz))
        if po == 1:
            return {"data": {"diff": {"1": {"f12": "BK1", "f14": "银行",
                    "f3": 1.0, "f62": 1000, "f184": 5, "f66": 500, "f72": 300}}}}
        return {"data": {"diff": {"1": {"f12": "BK2", "f14": "电子",
                "f3": -2.0, "f62": -2000, "f184": -8, "f66": -1000, "f72": -500}}}}

    monkeypatch.setattr(fetcher, "_request", fake_request)
    r = fetcher.fetch_top_flows(per_end=50)
    assert calls == [(1, 50), (0, 50)]
    assert len(r["inflow"]) == 1 and r["inflow"][0]["name"] == "银行"
    assert len(r["outflow"]) == 1 and r["outflow"][0]["name"] == "电子"
    assert r["inflow"][0]["main_net_yi"] == 0.0   # 1000/1e8


def test_fetch_top_flows_dedup_applied(monkeypatch):
    """两端各自做端内去重。"""
    def fake_request(po, pz):
        if po == 1:
            return {"data": {"diff": [
                {"f12": "BK1", "f14": "银行", "f62": 1000, "f184": 5},
                {"f12": "BK2", "f14": "银行Ⅱ", "f62": 1000, "f184": 5},
            ]}}
        return {"data": {"diff": []}}
    monkeypatch.setattr(fetcher, "_request", fake_request)
    r = fetcher.fetch_top_flows(per_end=100)
    assert len(r["inflow"]) == 1          # 银行/银行Ⅱ 合并
    assert len(r["outflow"]) == 0


def test_dedup_order_independent():
    """无论 银行/银行Ⅱ 谁先, 都保留无后缀的'银行'。"""
    a = [{"name": "银行", "main_net": 1000, "main_pct": 5},
         {"name": "银行Ⅱ", "main_net": 1000, "main_pct": 5}]
    b = list(reversed(a))
    assert fetcher.dedup(a)[0]["name"] == "银行"
    assert fetcher.dedup(b)[0]["name"] == "银行"
