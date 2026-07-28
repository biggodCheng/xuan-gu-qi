import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener import storage


def test_save_load_roundtrip(tmp_path):
    inflow = [{"code": "BK1", "name": "银行", "main_net_yi": 15.27}]
    outflow = [{"code": "BK2", "name": "电子", "main_net_yi": -5.59}]
    path = storage.save_results("2026-07-28", inflow, outflow, str(tmp_path))
    assert os.path.exists(path)
    assert path.endswith("zijin_2026-07-28.json")

    data = storage.load_results("2026-07-28", str(tmp_path))
    assert data["date"] == "2026-07-28"
    assert data["inflow_count"] == 1
    assert data["outflow_count"] == 1
    assert data["count"] == 2
    assert data["inflow"][0]["name"] == "银行"
    assert data["outflow"][0]["name"] == "电子"
    assert data["source"] == "东方财富行业板块资金流(push2delay clist)"


def test_load_missing_returns_none(tmp_path):
    assert storage.load_results("2099-01-01", str(tmp_path)) is None


def test_save_overwrites(tmp_path):
    storage.save_results("2026-07-28", [{"name": "旧"}], [], str(tmp_path))
    storage.save_results("2026-07-28", [{"name": "新"}], [], str(tmp_path))
    data = storage.load_results("2026-07-28", str(tmp_path))
    assert data["inflow"][0]["name"] == "新"
