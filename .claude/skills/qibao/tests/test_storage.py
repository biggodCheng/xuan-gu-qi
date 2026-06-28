import json
import os

from screener.storage import load_source, save_results


def test_save_and_load(tmp_path):
    src = os.path.join(tmp_path, "cxg_2026-06-29.json")
    with open(src, "w", encoding="utf-8") as f:
        json.dump({"date": "2026-06-29", "stocks": [{"code": "600001"}]}, f)

    data = load_source(src)
    assert data["date"] == "2026-06-29"

    out = save_results("cxg_2026-06-29.json", [{"code": "600001"}], "2026-06-29", str(tmp_path))
    assert out.endswith("qb_2026-06-29.json")
    with open(out, "r", encoding="utf-8") as f:
        result = json.load(f)
    assert result["count"] == 1
    assert result["source"] == "cxg_2026-06-29.json"
    assert "起爆" in result["description"]
