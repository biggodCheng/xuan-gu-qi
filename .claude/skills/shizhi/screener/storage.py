import json
import os


def load_source(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_results(
    source_filename: str,
    stocks: list[dict],
    date_str: str,
    threshold_yi: int,
    total_input: int,
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    result = {
        "date": date_str,
        "source": source_filename,
        "description": f"涨停股中市值小于{threshold_yi}亿的股票",
        "threshold_yi": threshold_yi,
        "total_input": total_input,
        "count": len(stocks),
        "stocks": stocks,
    }
    filepath = os.path.join(output_dir, f"sz_{date_str}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return filepath
