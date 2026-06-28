import json
import os

DESCRIPTION = "起爆=突破布林上轨+倍量+MACD水上金叉；蓄势=横盘+放量阳线(无L2资金流)"


def load_source(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_results(
    source_filename: str, stocks: list[dict], date_str: str, output_dir: str
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    result = {
        "date": date_str,
        "source": source_filename,
        "description": DESCRIPTION,
        "count": len(stocks),
        "stocks": stocks,
    }
    filepath = os.path.join(output_dir, f"qb_{date_str}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return filepath
