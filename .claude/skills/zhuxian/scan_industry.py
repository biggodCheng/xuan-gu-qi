# -*- coding: utf-8 -*-
"""行业板块(t:2)盲区补扫 — 复用 zhuxian 的聚合/分析/排名管线。

背景: main.py 默认只扫概念板块(fs=m:90+t:3+f:!50), 行业板块(t:2, 如电力 BK0428 /
化学制药 BK0465)是已知盲区, 判行业方向需手动补扫。本脚本扫 t:2, 下游 get_sector_kline
(成分股聚合) / analyze_sector / rank_sectors 对 BKxxxx 通用, 直接复用。

输出 data/zx_industry_<date>.json, 不覆盖概念板块结果(zx_<date>.json)。
"""
import os
import sys
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

# Windows 中文控制台默认 GBK(cp936) 编不出 emoji, 统一 stdout/stderr 用 utf-8。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# 复用项目根 scripts/trading_day: 用新浪权威交易日, 免疫本机系统时钟漂移
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SKILL_DIR)))
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if os.path.isdir(_SCRIPTS_DIR) and _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
import trading_day  # noqa: E402

from screener.fetcher import get_sector_kline, _get_json, _CLIST_URL, _UT  # noqa: E402
from screener.analyzer import analyze_sector, rank_sectors  # noqa: E402


def get_industry_sectors(retries: int = 3) -> list[dict]:
    """东财行业板块(t:2)列表。行业板块皆为真实行业分类, 无需风格/元板块黑名单。"""
    sectors = []
    pn = 1
    while pn <= 10:
        params = {
            "pn": pn, "pz": 100, "po": 1, "np": 1, "ut": _UT,
            "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:90+t:2+f:!50",
            "fields": "f12,f14,f2,f3",
        }
        data = _get_json(_CLIST_URL, params=params, retries=retries)
        if not isinstance(data, dict) or not data.get("data"):
            break
        diff = data["data"].get("diff") or []
        if not diff:
            break
        for it in diff:
            code = it.get("f12"); name = it.get("f14")
            if not code or not name:
                continue
            sectors.append({
                "code": code, "name": name,
                "close": it.get("f2"), "change_pct": it.get("f3"),
            })
        if len(diff) < 100:
            break
        pn += 1
        time.sleep(0.2)
    return sectors


def _fetch_kline(sector: dict) -> tuple[str, list[dict]]:
    return sector["code"], get_sector_kline(sector["code"], days=120)


def run(top_n: int = 10) -> bool:
    start_time = time.time()
    date_str = trading_day.latest_trading_day()
    trading_day.warn_if_drift(date_str)

    print(f"[{date_str}] 开始获取行业板块(t:2)列表...", flush=True)
    sectors = get_industry_sectors()
    if not sectors:
        print("未获取到行业板块数据，可能是网络异常。", flush=True)
        return False

    print(f"共获取 {len(sectors)} 个行业板块，开始并发获取K线数据（成分股聚合，10线程）...", flush=True)

    kline_map = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_kline, s): s["code"] for s in sectors}
        done_count = 0
        for future in as_completed(futures):
            code, kline = future.result()
            kline_map[code] = kline
            done_count += 1
            if done_count % 20 == 0:
                print(f"  已获取 {done_count}/{len(sectors)} 个板块的K线数据...", flush=True)

    print("K线数据获取完成，开始趋势分析...", flush=True)

    analyzed = []
    for sector in sectors:
        code = sector["code"]
        kline = kline_map.get(code, [])
        if not kline:
            continue

        analysis = analyze_sector(kline)
        if analysis is None:
            continue

        # 口径同 main.py: close/change_pct 与均线同源(聚合均价), 东财板块指数备查
        close = round(kline[-1]["close"], 2)
        change_pct = round((kline[-1]["close"] / kline[-2]["close"] - 1) * 100, 2) if len(kline) >= 2 else None

        analyzed.append({
            "code": code,
            "name": sector["name"],
            "close": close,
            "change_pct": change_pct,
            "index_close": sector.get("close"),
            "index_change_pct": sector.get("change_pct"),
            **analysis,
        })

    print(f"共 {len(analyzed)} 个行业板块通过趋势筛选，开始排名...", flush=True)
    ranked = rank_sectors(analyzed, top_n=top_n)

    output_dir = os.path.join(_SKILL_DIR, "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"zx_industry_{date_str}.json")
    result = {
        "date": date_str,
        "description": "A股行业板块(t:2)主线补扫 - 趋势上涨/破新高/低点抬高(概念板块见 zx_<date>.json)",
        "count": len(ranked),
        "sectors": ranked,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    print(f"完成！共筛选出 {len(ranked)} 个行业主线板块，耗时 {elapsed:.1f} 秒", flush=True)
    print(f"结果已保存到: {output_path}", flush=True)

    for i, s in enumerate(ranked, 1):
        print(
            f"  {i}. {s['name']} ({s['code']}) - 趋势得分: {s['trend_score']}, "
            f"收盘: {s['close']}, 20日涨幅: {s.get('period_return_20d', 'N/A')}%",
            flush=True,
        )
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="行业板块(t:2)盲区补扫")
    parser.add_argument("--top", type=int, default=10, help="返回前N个板块（默认10）")
    args = parser.parse_args()
    sys.exit(0 if run(top_n=args.top) else 1)
