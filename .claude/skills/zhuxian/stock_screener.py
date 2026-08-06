# -*- coding: utf-8 -*-
"""主线板块个股下钻筛选器 — 从主线板块成分股里筛"创100日新高"的个股。

是 zhuxian(主线板块筛选)的个股层延伸:zhuxian 选出主线板块(如医药三剑客),
本脚本下钻到板块成分股,挑出趋势最强的创新高股,并标注量能/起爆。

数据源:
  - 成分股:东财 clist?fs=b:BKxxxx(与 zhuxian fetcher 同源,真实板块成分股)。
  - 个股 OHLCV:本地招商证券 vipdoc(scripts/local_kline.py,零网络、不复权)。

口径对齐 chuangxingao:
  - 新高 = 当日收盘(东财实时价 f2) >= 最近100个交易日(排除当日)的最高收盘价。
  - 历史不足 60 日的跳过(数据残缺不纳入)。

起爆(辅助标注,非买点承诺):
  - 创新高 + 当日倍量(量/MA5 ≥ 2)+ 当日收阳。本地无 L2,近似"放量阳线突破"。

注意:本地 vipdoc 不复权,跨除权日的新高可能有跳空误差;短期窗口影响小。
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean

# 统一 stdout/stderr 用 utf-8(失败则忽略, 不阻断)。修中文/emoji 在 GBK 控制台崩溃。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

_ROOT = Path(__file__).resolve().parents[3]  # 项目根
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ROOT / ".claude" / "skills" / "zhuxian" / "screener"))

import local_kline  # noqa: E402
from fetcher import _CLIST_URL, _UT, _get_json  # noqa: E402  东财直连组件

# 默认主线:医药(创新药 + CRO + 医药外包CXO)
DEFAULT_BOARDS = {
    "BK1106": "创新药",
    "BK0899": "CRO",
    "BK0939": "医药外包CXO",
}


def _prefix(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sz"


def fetch_board_members(boards: dict[str, str]) -> dict[str, dict]:
    """拉多个板块的成分股并去重。返回 {code: {name, close, chg, mcap, boards: set}}。"""
    pool = {}
    for bk, bk_name in boards.items():
        for pn in range(1, 6):
            params = {
                "pn": pn, "pz": 100, "po": 1, "np": 1, "ut": _UT,
                "fltt": 2, "invt": 2, "fid": "f20", "fs": f"b:{bk}",
                "fields": "f12,f14,f2,f3,f20",
            }
            d = _get_json(_CLIST_URL, params=params)
            diff = (d or {}).get("data", {}).get("diff") or []
            if not diff:
                break
            for it in diff:
                code = it.get("f12")
                if not code:
                    continue
                name = it.get("f14") or ""
                if name.startswith(("ST", "*ST")):
                    continue
                if code not in pool:
                    pool[code] = {
                        "code": code,
                        "name": name,
                        "close": it.get("f2"),   # 当日实时价
                        "chg": it.get("f3"),      # 当日涨跌%
                        "mcap": it.get("f20"),    # 总市值(元)
                        "boards": set(),
                    }
                pool[code]["boards"].add(bk_name)
            if len(diff) < 100:
                break
            time.sleep(0.15)
    return pool


def _analyze(code: str, stock: dict, today_str: str) -> dict | None:
    """读本地 OHLCV → 新高/量能/收阳判定。本地无数据返回 None。"""
    rows = local_kline.read_day(f"{_prefix(code)}{code}")
    if len(rows) < 60:
        return None  # 历史不足,跳过

    recent = rows[-100:]
    if recent and recent[-1]["date"] == today_str:
        recent = recent[:-1]  # 排除当日,用前99日
    if not recent:
        return None
    prev_high = max(r["close"] for r in recent)

    close_today = stock["close"]
    if not isinstance(close_high := close_today, (int, float)) or close_high <= 0:
        return None
    is_new_high = close_today >= prev_high

    # 量能/收阳用本地最后一根(最近交易日)
    last = rows[-1]
    prev5_vols = [r["volume"] for r in rows[-6:-1]]
    # 起爆倍量口径对齐 qibao skill 的 b2: 今量 / 近5日"峰值"(非均量), >=2 为倍量
    max5_vol = max(prev5_vols) if prev5_vols else 0
    vol_ratio = round(last["volume"] / max5_vol, 2) if max5_vol > 0 else 0.0
    up = last["close"] > last["open"]
    qibao = is_new_high and vol_ratio >= 2.0 and up

    return {
        "prev_high": round(prev_high, 2),
        "vol_ratio": vol_ratio,
        "up": up,
        "is_new_high": is_new_high,
        "qibao": qibao,
        "last_date": last["date"],  # 量能/收阳所对应的交易日
    }


def screen(boards: dict[str, str], date_str: str) -> dict:
    pool = fetch_board_members(boards)
    print(f"成分股去重合计 {len(pool)} 只,开始读本地K线判定...", flush=True)

    results = []
    missing = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(_analyze, c, s, date_str): c for c, s in pool.items()}
        done = 0
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                meta = fut.result()
            except Exception:
                meta = None
            if meta is None:
                missing += 1
                done += 1
                continue
            s = pool[code]
            if not meta["is_new_high"]:
                done += 1
                continue
            results.append({
                "code": code,
                "name": s["name"],
                "close": s["close"],
                "chg": s["chg"],
                "mcap_yi": round((s["mcap"] or 0) / 1e8, 1),
                "prev_high": meta["prev_high"],
                "vol_ratio": meta["vol_ratio"],
                "qibao": meta["qibao"],
                "up": meta["up"],
                "last_date": meta["last_date"],
                "boards": sorted(s["boards"]),
            })
            done += 1

    # 按市值降序(大票优先,稳定性高)
    results.sort(key=lambda x: x["mcap_yi"], reverse=True)
    print(f"判定完成:{len(results)} 只创100日新高 | 本地无数据/历史不足跳过 {missing} 只", flush=True)
    return {
        "date": date_str,
        "boards": boards,
        "pool_size": len(pool),
        "new_high_count": len(results),
        "qibao_count": sum(1 for r in results if r["qibao"]),
        "missing": missing,
        "stocks": results,
    }


def main():
    ap = argparse.ArgumentParser(description="主线板块个股创新高筛选")
    ap.add_argument("--boards", default=",".join(DEFAULT_BOARDS.keys()),
                    help="东财板块BK代码,逗号分隔(默认医药三板块)")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--force", action="store_true", help="覆盖已有输出")
    args = ap.parse_args()

    codes = [c.strip() for c in args.boards.split(",") if c.strip()]
    boards = {c: DEFAULT_BOARDS.get(c, c) for c in codes}

    out_dir = _ROOT / ".claude" / "skills" / "zhuxian" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"zx_stocks_{args.date}.json"
    if out_path.exists() and not args.force:
        print(f"今日个股数据已存在: {out_path}\n使用 --force 强制重跑。")
        return

    t0 = time.time()
    data = screen(boards, args.date)
    data["elapsed_sec"] = round(time.time() - t0, 1)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成!新高 {data['new_high_count']} 只(其中起爆 {data['qibao_count']} 只),"
          f"耗时 {data['elapsed_sec']} 秒")
    print(f"结果已保存: {out_path}")


if __name__ == "__main__":
    main()
