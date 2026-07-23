# -*- coding: utf-8 -*-
"""维度1(美股+VIX)parser 测试。基于 probe 真实 fixture。"""
import os
from pk import us_stock

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sina_us.txt")


def _load_fix():
    with open(FIX, encoding="utf-8") as f:
        return f.read()


def test_parse_us_extracts_name_price_pct():
    items = us_stock.parse_us(_load_fix())
    # fixture 含 3 个真实指数条目(ixic/inx/dji),VIX 空 payload 应被跳过
    assert len(items) == 3
    # NAME_MAP 用 config 展示名(纳指/标普500/道指),非 Sina 原始名
    names = {it["name"] for it in items}
    assert "纳指" in names and "标普500" in names and "道指" in names
    for it in items:
        assert "price" in it and "pct" in it and "code" in it
        assert isinstance(it["pct"], float)
        assert isinstance(it["price"], float)


def test_parse_us_strips_hq_str_prefix():
    # Sina 实际返回 key 带 hq_str_ 前缀;parser 必须剥掉后再查 NAME_MAP
    items = us_stock.parse_us('var hq_str_gb_ixic="纳斯达克,25690.9029,-0.57,ts,-1";')
    assert len(items) == 1
    assert items[0]["code"] == "gb_ixic"
    assert items[0]["pct"] == -0.57


def test_parse_us_ignores_empty_payload():
    items = us_stock.parse_us('var gb_zzz="";')
    assert items == []


def test_parse_us_ignores_unknown_code():
    # 已知前缀但不在 NAME_MAP 的 code 应跳过(防 VIX 之外的噪声)
    items = us_stock.parse_us('var hq_str_gb_baba="阿里巴巴,80.0,1.2,ts";')
    assert items == []


def test_parse_us_skips_malformed_fields():
    # 字段不足 / 非数字应跳过该条而不崩
    items = us_stock.parse_us('var hq_str_gb_ixic="纳斯达克";')  # 只有 name,无 price/pct
    assert items == []
