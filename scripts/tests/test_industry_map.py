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
