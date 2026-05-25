import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.storage import save_results, load_results


def test_save_results_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sectors = [{"code": "BK0001", "name": "测试板块", "trend_score": 80}]
        path = save_results("2026-05-25", sectors, tmpdir)

        assert os.path.exists(path)
        assert path.endswith("zx_2026-05-25.json")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["date"] == "2026-05-25"
        assert data["count"] == 1
        assert data["sectors"][0]["name"] == "测试板块"


def test_save_results_overwrites_existing():
    with tempfile.TemporaryDirectory() as tmpdir:
        save_results("2026-05-25", [{"name": "A"}], tmpdir)
        save_results("2026-05-25", [{"name": "B"}], tmpdir)

        result = load_results("2026-05-25", tmpdir)
        assert result["sectors"][0]["name"] == "B"


def test_load_results_file_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_results("2026-05-25", tmpdir)
        assert result is None
