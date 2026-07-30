import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

# Windows 中文控制台默认 GBK(cp936) 编不出 emoji(⚠️), warn_if_drift 警告会崩;
# 统一 stdout/stderr 用 utf-8(失败则忽略)。
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
import trading_day

from screener.fetcher import get_concept_sectors, get_sector_kline
from screener.analyzer import analyze_sector, rank_sectors
from screener.storage import save_results, load_results


def _fetch_kline(sector: dict) -> tuple[str, list[dict]]:
    return sector["code"], get_sector_kline(sector["code"], days=120)


def run_screener(output_dir: str | None = None, top_n: int = 10, force: bool = False, date_str: str | None = None) -> bool:
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    start_time = time.time()
    date_str = date_str or trading_day.latest_trading_day()
    trading_day.warn_if_drift(date_str)

    # 检查是否已有当天数据
    if not force:
        existing = load_results(date_str, output_dir)
        if existing is not None:
            print(f"今日数据已存在: {os.path.join(output_dir, f'zx_{date_str}.json')}", flush=True)
            print("使用 --force 参数覆盖已有数据", flush=True)
            return True

    print(f"[{date_str}] 开始获取概念板块列表...", flush=True)
    sectors = get_concept_sectors()

    if not sectors:
        print("未获取到板块数据，可能是网络异常或非交易日。", flush=True)
        return False

    print(f"共获取 {len(sectors)} 个概念板块，开始并发获取K线数据（成分股聚合，10线程）...", flush=True)

    kline_map = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_kline, s): s["code"] for s in sectors}
        done_count = 0
        for future in as_completed(futures):
            code, kline = future.result()
            kline_map[code] = kline
            done_count += 1
            if done_count % 50 == 0:
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

        # 口径统一: close/change_pct 必须与均线/涨幅同源(本地全成分聚合均价),
        # 否则 close(东财板块指数点位,几千) 与 ma/recent_high(聚合均价,几十) 脱节,无法对照读数。
        # 东财真实板块指数点位/涨跌另存为 index_close/index_change_pct 备查(不同口径,勿与 close 混用)。
        close = round(kline[-1]["close"], 2)
        change_pct = round((kline[-1]["close"] / kline[-2]["close"] - 1) * 100, 2) if len(kline) >= 2 else None

        analyzed.append({
            "code": code,
            "name": sector["name"],
            "close": close,
            "change_pct": change_pct,
            "index_close": sector.get("close"),            # 东财板块指数点位(备查)
            "index_change_pct": sector.get("change_pct"),  # 东财板块指数当日涨跌(备查)
            **analysis,
        })

    print(f"共 {len(analyzed)} 个板块通过趋势筛选，开始排名...", flush=True)

    ranked = rank_sectors(analyzed, top_n=top_n)

    output_path = save_results(date_str, ranked, output_dir)

    elapsed = time.time() - start_time
    print(f"完成！共筛选出 {len(ranked)} 个主线板块，耗时 {elapsed:.1f} 秒", flush=True)
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

    parser = argparse.ArgumentParser(description="主线板块筛选器")
    parser.add_argument("--top", type=int, default=10, help="返回前N个板块（默认10）")
    parser.add_argument("--force", action="store_true", help="覆盖已有数据")
    args = parser.parse_args()
    success = run_screener(top_n=args.top, force=args.force)
    sys.exit(0 if success else 1)
