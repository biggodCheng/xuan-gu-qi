"""watchlist.json 持久化:读写、去重、覆盖式刷新、到期迁移、损坏兜底。

watchlist 结构见计划 File Structure。load 对损坏文件先备份为 *.bad 再返回空池,
保证主流程不崩。
"""
import datetime
import json
import os

REPORT_PERIOD = "2026H1"
REPORT_DATE = "2026-06-30"
THRESHOLD = {
    "predict_type": "预增",
    "yoy_lower_min": 50.0,
    "hold_days": 30,
    "base": "次日开盘",
}


def empty_pool() -> dict:
    return {
        "report_period": REPORT_PERIOD,
        "report_date": REPORT_DATE,
        "updated_at": "",
        "threshold": dict(THRESHOLD),
        "active": [],
        "expired": [],
        "skipped": [],
    }


def load_watchlist(path: str) -> dict:
    """加载 watchlist;不存在→空池;损坏→备份 *.bad 后返回空池。"""
    if not os.path.exists(path):
        return empty_pool()
    try:
        with open(path, "r", encoding="utf-8") as f:
            pool = json.load(f)
        for k in ("active", "expired", "skipped"):
            pool.setdefault(k, [])
        return pool
    except (json.JSONDecodeError, ValueError):
        bad = path + ".bad"
        # 不覆盖已存在的 .bad,加日期后缀
        if os.path.exists(bad):
            bad = f"{path}.bad.{datetime.date.today()}"
        try:
            os.replace(path, bad)
        except OSError:
            pass
        print(f"⚠️ watchlist 损坏,已备份到 {bad},重建空池", flush=True)
        return empty_pool()


def save_watchlist(pool: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pool["updated_at"] = datetime.date.today().strftime("%Y-%m-%d")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
