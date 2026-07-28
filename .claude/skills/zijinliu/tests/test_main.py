import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener import storage
import main


class _FakeFetcher:
    @staticmethod
    def fetch_top_flows(per_end=100):
        return {
            "inflow": [{"code": "BK1", "name": "银行", "change_pct": 1.04,
                        "main_net_yi": 15.27, "main_pct": 4.3,
                        "super_large_net": 1108062464, "main_net": 1527127040,
                        "large_net": 419064576}],
            "outflow": [{"code": "BK2", "name": "电子", "change_pct": -4.23,
                         "main_net_yi": -5.59, "main_pct": -8.64,
                         "super_large_net": -1000, "main_net": -559410000,
                         "large_net": -500}],
        }


def test_run_creates_snapshot_and_prints(tmp_path, capsys):
    ok = main.run(today_str="2026-07-28", output_dir=str(tmp_path),
                  top=20, outflow_top=10, fetcher=_FakeFetcher)
    assert ok is True
    assert os.path.exists(os.path.join(str(tmp_path), "zijin_2026-07-28.json"))
    out = capsys.readouterr().out
    assert "银行" in out
    assert "电子" in out
    assert "主力净流入" in out and "主力净流出" in out


def test_run_checkpoint_blocks_without_force(tmp_path, capsys):
    # 预置一个已存在的快照
    open(os.path.join(str(tmp_path), "zijin_2026-07-28.json"), "w").close()
    ok = main.run(today_str="2026-07-28", output_dir=str(tmp_path),
                  fetcher=_FakeFetcher)
    assert ok is False
    assert "已存在" in capsys.readouterr().out


def test_run_force_overwrites(tmp_path):
    open(os.path.join(str(tmp_path), "zijin_2026-07-28.json"), "w").close()
    ok = main.run(today_str="2026-07-28", output_dir=str(tmp_path),
                  force=True, fetcher=_FakeFetcher)
    assert ok is True
    data = storage.load_results("2026-07-28", str(tmp_path))
    assert data["inflow"][0]["name"] == "银行"


class _EmptyFetcher:
    @staticmethod
    def fetch_top_flows(per_end=100):
        return {"inflow": [], "outflow": []}


def test_run_network_failure_returns_false_no_save(tmp_path, capsys):
    """接口失败(两端空) → 不保存、返回 False、打印失败提示。"""
    ok = main.run(today_str="2026-07-28", output_dir=str(tmp_path), fetcher=_EmptyFetcher)
    assert ok is False
    assert not os.path.exists(os.path.join(str(tmp_path), "zijin_2026-07-28.json"))
    assert "失败" in capsys.readouterr().out
