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
