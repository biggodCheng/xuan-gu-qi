"""popularity_<date>.json 读写。

文件名 popularity_<date>.json，结构与 spec 第 8 节一致。
save 覆盖写（同 date 重跑直接替换，防覆盖由 main 的 CHECKPOINT 交互处理）。
"""
import datetime
import json
import os


def _now_iso() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def save_results(date_str: str, sort: str, stocks: list, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    result = {
        "date": date_str,
        "fetched_at": _now_iso(),
        "source": "东方财富股吧个股人气榜",
        "sort": sort,
        "count": len(stocks),
        "stocks": stocks,
    }
    path = os.path.join(output_dir, f"popularity_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def load_results(date_str: str, output_dir: str):
    path = os.path.join(output_dir, f"popularity_{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
