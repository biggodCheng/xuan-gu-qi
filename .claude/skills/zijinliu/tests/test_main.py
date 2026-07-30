import sys, os, datetime
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


# ---- 盘前/非交易日 数据日警告 ----
def test_session_warning_before_open_weekday():
    """周一盘前(<9:30) → 警告数据为上一交易日。"""
    now = datetime.datetime(2026, 7, 27, 8, 0)  # 周一 08:00
    w = main._market_session_warning(now)
    assert "盘前" in w


def test_session_warning_weekend():
    """周末 → 警告非交易日。"""
    now = datetime.datetime(2026, 8, 1, 10, 0)  # 周六
    w = main._market_session_warning(now)
    assert "非交易日" in w


def test_session_no_warning_during_session():
    """周一盘中(10:30) → 无警告(数据为今日实时)。"""
    now = datetime.datetime(2026, 7, 27, 10, 30)
    assert main._market_session_warning(now) == ""


def test_session_no_warning_after_close():
    """周一盘后(16:00) → 无警告(数据为今日收盘)。"""
    now = datetime.datetime(2026, 7, 27, 16, 0)
    assert main._market_session_warning(now) == ""


def test_run_prints_session_warning(tmp_path, capsys, monkeypatch):
    """盘前跑 → 摘要前打印数据日警告。"""
    monkeypatch.setattr(main, "_market_session_warning", lambda now=None: "⚠️ 数据日警告TEST")
    ok = main.run(today_str="2026-07-29", output_dir=str(tmp_path), fetcher=_FakeFetcher)
    assert ok is True
    assert "数据日警告TEST" in capsys.readouterr().out


def test_run_stale_session_persists_to_json(tmp_path, monkeypatch):
    """盘前跑 → 警告持久化进 JSON(is_stale=true)，下游可识别非今日数据。"""
    monkeypatch.setattr(main, "_market_session_warning", lambda now=None: "⚠️ 盘前数据为上一交易日")
    main.run(today_str="2026-07-29", output_dir=str(tmp_path), fetcher=_FakeFetcher)
    data = storage.load_results("2026-07-29", str(tmp_path))
    assert data["is_stale"] is True
    assert "上一交易日" in data["note"]


# ---- 权威交易日 / 时钟漂移自检 ----
def test_run_uses_authoritative_day_when_clock_drifts(tmp_path, capsys, monkeypatch):
    """today_str 未传 → 用新浪权威交易日(非本地时钟); 本地偏慢1天 → 打印漂移警告、文件名用权威日。"""
    monkeypatch.setattr(main.trading_day, "latest_trading_day", lambda: "2026-07-30")
    monkeypatch.setattr(main.trading_day, "local_today_str", lambda: "2026-07-29")
    ok = main.run(today_str=None, output_dir=str(tmp_path), fetcher=_FakeFetcher)
    assert ok is True
    # 文件名采用权威交易日(07-30), 而非本地时钟(07-29)
    assert os.path.exists(os.path.join(str(tmp_path), "zijin_2026-07-30.json"))
    assert not os.path.exists(os.path.join(str(tmp_path), "zijin_2026-07-29.json"))
    out = capsys.readouterr().out
    assert "相差 1 天" in out          # 漂移警告
    assert "权威交易日" in out
    assert "2026-07-30" in out


def test_run_no_drift_warning_when_clock_aligned(tmp_path, capsys, monkeypatch):
    """本地时钟与权威交易日一致 → 不打印漂移警告。"""
    monkeypatch.setattr(main.trading_day, "latest_trading_day", lambda: "2026-07-30")
    monkeypatch.setattr(main.trading_day, "local_today_str", lambda: "2026-07-30")
    main.run(today_str=None, output_dir=str(tmp_path), fetcher=_FakeFetcher)
    out = capsys.readouterr().out
    assert "相差" not in out
    assert "权威交易日" not in out
