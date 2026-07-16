import json
import os


def save_results(
    date_str: str,
    stocks: list[dict],
    output_dir: str,
    trigger: dict | None = None,
) -> None:
    """保存抗跌观察池结果到 kd_<date>.json。"""
    os.makedirs(output_dir, exist_ok=True)
    result = {
        "date": date_str,
        "trigger": trigger or {},
        "count": len(stocks),
        "stocks": stocks,
    }
    filepath = os.path.join(output_dir, f"kd_{date_str}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def load_results(date_str: str, output_dir: str) -> dict | None:
    """读取 kd_<date>.json，不存在返回 None。"""
    filepath = os.path.join(output_dir, f"kd_{date_str}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
