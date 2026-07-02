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


def existing_codes(pool: dict) -> set:
    """active+expired+skipped 的 code 并集(去重用)。"""
    codes = set()
    for sec in ("active", "expired", "skipped"):
        for s in pool.get(sec, []):
            if s.get("code"):
                codes.add(s["code"])
    return codes


def add_active(pool: dict, stock: dict) -> None:
    """新股入 active 占位(daily 待刷新填)。补默认字段。"""
    entry = {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "industry": stock.get("industry", ""),
        "predict_type": stock.get("predict_type", "预增"),
        "yoy_lower": stock.get("yoy_lower"),
        "yoy_upper": stock.get("yoy_upper"),
        "notice_date": stock.get("notice_date"),
        "base_date": "",
        "base_price": None,
        "held_days": 0,
        "remain_days": 30,
        "last_close": None,
        "chg_total": None,
        "chg_today": None,
        "base_note": "",
        "daily": [],
    }
    pool["active"].append(entry)


def refresh_active(pool: dict, code: str, fields: dict) -> None:
    """覆盖式更新某 active 股的 daily 及汇总字段(前复权口径每次整体覆盖)。"""
    for s in pool["active"]:
        if s["code"] == code:
            s.update(fields)
            return
    raise KeyError(f"active 中找不到 {code}")


def migrate_expired(pool: dict, hold_days: int = 30) -> list:
    """把 active 中 held_days ≥ hold_days 的迁入 expired,返回迁出的 code 列表。"""
    stay, moved = [], []
    for s in pool["active"]:
        if (s.get("held_days") or 0) >= hold_days:
            moved.append(s)
        else:
            stay.append(s)
    pool["active"] = stay
    pool["expired"].extend(moved)
    return [m["code"] for m in moved]


def add_skipped(pool: dict, code: str, name: str, notice_date: str, reason: str) -> None:
    """入池失败(K线缺失等)记入 skipped,下次执行重试。"""
    pool["skipped"].append({
        "code": code, "name": name, "notice_date": notice_date, "reason": reason,
    })


def remove_skipped(pool: dict, code: str) -> None:
    """重试成功后从 skipped 移除。"""
    pool["skipped"] = [s for s in pool["skipped"] if s["code"] != code]
