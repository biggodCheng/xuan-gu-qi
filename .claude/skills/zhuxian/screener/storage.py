import json
import os


def save_results(date_str: str, sectors: list[dict], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    result = {
        "date": date_str,
        "description": "A股主线板块 - 趋势上涨、不断破新高、低点抬高",
        "count": len(sectors),
        "sectors": sectors,
    }
    filepath = os.path.join(output_dir, f"zx_{date_str}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return filepath


def load_results(date_str: str, output_dir: str) -> dict | None:
    filepath = os.path.join(output_dir, f"zx_{date_str}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
