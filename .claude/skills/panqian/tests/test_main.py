from unittest.mock import patch
from pk.base import FetchResult
import importlib.util, os

# 显式加载 panqian/main.py(独立模块名, 避免与 fupan/main.py 跨 skill 的 `import main` 冲突)
_MAIN_PATH = os.path.join(os.path.dirname(__file__), "..", "main.py")
_spec = importlib.util.spec_from_file_location("panqian_main_for_test", _MAIN_PATH)
mainmod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mainmod)


def _ok_results():
    return {
        "us": FetchResult("us", ok=True,
                          data={"indices": [{"name": "纳指", "price": 18123, "pct": -1.8}], "vix": 22.0},
                          detail="✓"),
        "a50": FetchResult("a50", ok=True,
                           data={"a50": {"price": 13210, "pct": -0.6}, "cnr": []}, detail="✓"),
        "fx": FetchResult("fx", ok=True, data={"fx": [], "comm": []}, detail="✓"),
        "news": FetchResult("news", ok=True, data={"items": [], "sources_ok": []}, detail="✓"),
    }


def test_build_report_data_assembles_tone():
    data = mainmod.build_report_data("2026-07-23", _ok_results(), note="")
    assert data["tone"] in ("偏冷", "偏暖", "中性", "恐慌")
    assert data["critical_missing"] is False
    assert data["quality"]["us"] == "✓"


def test_build_report_data_critical_missing_when_a50_fail():
    res = _ok_results()
    res["a50"] = FetchResult("a50", ok=False, data={"a50": None, "cnr": []},
                             detail="⚠️ A50 取数失败(关键维缺失)")
    data = mainmod.build_report_data("2026-07-23", res, note="")
    assert data["critical_missing"] is True
    assert "⚠️" in data["quality"]["a50"]


def test_build_report_data_critical_missing_when_us_fail():
    res = _ok_results()
    res["us"] = FetchResult("us", ok=False, data=None, detail="⚠️ 美股失败")
    data = mainmod.build_report_data("2026-07-23", res, note="")
    assert data["critical_missing"] is True


def test_main_writes_output(tmp_path, monkeypatch):
    monkeypatch.setattr(mainmod, "OUT_DIR", str(tmp_path))
    with patch.object(mainmod, "fetch_all", return_value=_ok_results()):
        out = mainmod.run(date_str="2026-07-23", note="")
    assert (tmp_path / "2026-07-23.md").exists()
    assert out.endswith("2026-07-23.md")


def test_run_uses_local_day_before_open(tmp_path, monkeypatch):
    """盘前(date_str=None, 权威交易日=昨日 → drift<=-1)时报告日用本地日(今天)。

    latest_trading_day()(=新浪最新日K日)在 A股未开盘的盘前返回昨日; panqian 服务于
    "即将开盘的交易日", 此时本地日才是正确报告日。否则盘前报告少标1天、覆盖昨日报告、
    并误报时钟漂移(<=-1 同时覆盖长假后首个交易日盘前)。
    """
    monkeypatch.setattr(mainmod, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(mainmod.trading_day, "latest_trading_day", lambda: "2026-07-30")
    monkeypatch.setattr(mainmod.trading_day, "local_today_str", lambda: "2026-07-31")
    with patch.object(mainmod, "fetch_all", return_value=_ok_results()):
        out = mainmod.run(note="")
    assert (tmp_path / "2026-07-31.md").exists()
    assert not (tmp_path / "2026-07-30.md").exists()
    assert out.endswith("2026-07-31.md")


def test_run_uses_trading_day_when_aligned(tmp_path, monkeypatch):
    """收盘后/对齐场景(drift=0)沿用权威交易日, 回归保护。"""
    monkeypatch.setattr(mainmod, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(mainmod.trading_day, "latest_trading_day", lambda: "2026-07-31")
    monkeypatch.setattr(mainmod.trading_day, "local_today_str", lambda: "2026-07-31")
    with patch.object(mainmod, "fetch_all", return_value=_ok_results()):
        out = mainmod.run(note="")
    assert (tmp_path / "2026-07-31.md").exists()
    assert out.endswith("2026-07-31.md")
