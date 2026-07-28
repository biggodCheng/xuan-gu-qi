"""zijin_<date>.json 读写。

文件名 zijin_<date>.json, 结构与 spec 一致。save 覆盖写(防覆盖由 main 的
CHECKPOINT 交互处理)。
"""
import datetime
import json
import os


def _now_iso() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def save_results(date_str: str, inflow: list, outflow: list,
                 output_dir: str, note: str | None = None) -> str:
    os.makedirs(output_dir, exist_ok=True)
    result = {
        "date": date_str,
        "fetched_at": _now_iso(),
        "source": "东方财富行业板块资金流(push2delay clist)",
        "sort": "流入端 po=1 降序 / 流出端 po=0 升序（各端已去重）",
        "inflow_count": len(inflow),
        "outflow_count": len(outflow),
        "count": len(inflow) + len(outflow),
        "inflow": inflow,
        "outflow": outflow,
    }
    # 盘前/非交易时段抓取时接口返回上一交易日数据；持久化警告，避免下游
    # （date/文件名标的是抓取日=今日）把上一交易日数据误读为今日。
    if note:
        result["note"] = note
        result["is_stale"] = True
    path = os.path.join(output_dir, f"zijin_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def load_results(date_str: str, output_dir: str):
    path = os.path.join(output_dir, f"zijin_{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
