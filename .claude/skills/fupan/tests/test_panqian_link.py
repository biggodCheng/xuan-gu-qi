import os, sys
import importlib.util

# 显式加载 fupan/main.py(独立模块名, 避免与 panqian/main.py 跨 skill 的 `import main` 冲突)
_FUPAN_MAIN = os.path.join(os.path.dirname(__file__), "..", "main.py")
_spec = importlib.util.spec_from_file_location("fupan_main_for_test", _FUPAN_MAIN)
main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main)


def test_render_panqian_link_when_exists(tmp_path, monkeypatch):
    pq = tmp_path / "2026-07-23.md"
    pq.write_text(
        "# 盘前外部温度计 · 2026-07-23\n## 0. 隔夜定调\n外部环境:**偏冷**\n"
        "## 2. A50期货 + 中概\nA50期货:13210(-0.60%)", encoding="utf-8")
    monkeypatch.setattr(main, "PANQIAN_DIR", str(tmp_path))
    block = main.render_panqian_link("2026-07-23", sh_chg=-0.4)
    assert "隔夜信号 vs 今日实际" in block
    assert "偏冷" in block            # 引用了 panqian 定调
    assert "兑现" in block or "背离" in block


def test_render_panqian_link_missing(monkeypatch):
    monkeypatch.setattr(main, "PANQIAN_DIR", "/nonexistent/path")
    block = main.render_panqian_link("2026-07-23", sh_chg=0.0)
    assert "建议盘前先跑" in block or "/panqian" in block


def test_realize_degree():
    assert main.realize_degree(predicted_low=True, chg=-0.4) == "兑现"
    assert main.realize_degree(predicted_low=True, chg=0.5) == "背离"
    assert main.realize_degree(predicted_low=True, chg=0.0) == "部分兑现"
    assert main.realize_degree(predicted_low=False, chg=0.3) == "兑现"
