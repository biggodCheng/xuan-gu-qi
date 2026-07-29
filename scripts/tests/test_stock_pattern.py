# -*- coding: utf-8 -*-
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

VIPDOC = r"D:\APP\招商证券\vipdoc"
HAS_VIPDOC = os.path.isdir(VIPDOC)


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_cli_single_stock_outputs_three_layers(capsys):
    """CLI 对华天酒店输出三层标签 + 建议归类。"""
    import stock_pattern
    stock_pattern.run(["sz000428"], height=3)
    out = capsys.readouterr().out
    assert "000428" in out
    assert "形态" in out and "量能" in out and "板块" in out
    assert "建议归类" in out


def test_cli_missing_stock_no_crash(capsys, monkeypatch):
    """无本地数据的股票不崩溃, 输出提示。"""
    import stock_pattern
    import pattern_label
    monkeypatch.setattr(pattern_label, "label", lambda s, height=1: {"sym": s, "error": "无本地数据"})
    stock_pattern.run(["sz999999"], height=1)
    out = capsys.readouterr().out
    assert "无本地数据" in out
