# -*- coding: utf-8 -*-
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import industry_map  # noqa: E402


def test_load_map_missing_file_returns_empty(tmp_path, monkeypatch):
    """映射文件不存在时返回 {}，不报错。"""
    monkeypatch.setattr(industry_map, "MAP_PATH", str(tmp_path / "no.json"))
    assert industry_map.load_map() == {}


def test_load_map_reads_existing_json(tmp_path, monkeypatch):
    """读取已存在的映射 json。"""
    p = tmp_path / "industry_map.json"
    p.write_text(json.dumps({"000428": "酒店餐饮", "001358": "化学制品"},
                            ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(industry_map, "MAP_PATH", str(p))
    m = industry_map.load_map()
    assert m["000428"] == "酒店餐饮"
    assert m["001358"] == "化学制品"


def test_refresh_builds_mapping_from_clist(tmp_path, monkeypatch):
    """refresh 两层拉取(行业板块→成分股), mock _clist 不真联网。"""
    monkeypatch.setattr(industry_map, "MAP_PATH", str(tmp_path / "industry_map.json"))

    # mock _clist: 第一次返回行业板块列表, 之后返回各板块成分股
    fake_industries = [{"f12": "BK0447", "f14": "酒店餐饮"},
                       {"f12": "BK0478", "f14": "化学制品"}]
    fake_stocks_ht = [{"f12": "000428"}, {"f12": "sz000721"}]
    fake_stocks_hx = [{"f12": "001358"}, {"f12": "sh603948"}]
    calls = {"i": 0}

    def fake_clist(fs, fields, pz=500):
        calls["i"] += 1
        if fs == industry_map.INDUSTRY_FS:
            return fake_industries
        if fs == "b:BK0447":
            return fake_stocks_ht
        if fs == "b:BK0478":
            return fake_stocks_hx
        return []

    monkeypatch.setattr(industry_map, "_clist", fake_clist)

    m = industry_map.refresh()
    assert m["000428"] == "酒店餐饮"      # 后6位
    assert m["000721"] == "酒店餐饮"      # sz000721 → 000721
    assert m["001358"] == "化学制品"
    assert m["603948"] == "化学制品"      # sh603948 → 603948
    # 落盘
    assert os.path.exists(industry_map.MAP_PATH)
