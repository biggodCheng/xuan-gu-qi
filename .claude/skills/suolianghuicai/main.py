import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import get_stock_kline
from screener.analyzer import STRATEGIES, filter_pullbacks
from screener.storage import load_source, save_results

STRATEGY_MAP = {
    "1": "shrinking_volume",
    "2": "below_average",
    "3": "single_day",
}


def _fetch_kline(code: str, days: int = 30) -> tuple[str, list[dict]]:
    return code, get_stock_kline(code, days=days)


def run_filter(json_path: str, strategy_key: str, params: dict) -> bool:
    start_time = time.time()
    json_path = os.path.abspath(json_path)

    if not os.path.exists(json_path):
        print(f"文件不存在: {json_path}", flush=True)
        return False

    strategy = STRATEGY_MAP.get(strategy_key)
    if not strategy:
        print(f"无效策略: {strategy_key}，可选: 1/2/3", flush=True)
        return False

    strategy_desc = STRATEGIES[strategy]

    source_data = load_source(json_path)
    stocks = source_data.get("stocks", [])
    date_str = source_data.get("date", "unknown")

    if not stocks:
        print("源文件中没有股票数据。", flush=True)
        return False

    print(
        f"[{date_str}] 策略: {strategy_desc}",
        flush=True,
    )
    print(f"源文件共 {len(stocks)} 只股票，开始获取K线数据（20线程）...", flush=True)

    kline_map = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(_fetch_kline, s["code"]): s["code"]
            for s in stocks
        }
        done_count = 0
        for future in as_completed(futures):
            code, kline = future.result()
            kline_map[code] = kline
            done_count += 1
            if done_count % 50 == 0:
                print(f"  已获取 {done_count}/{len(stocks)} 只股票的K线数据...", flush=True)

    print(f"K线数据获取完成，开始筛选缩量回踩股...", flush=True)

    result = filter_pullbacks(stocks, kline_map, strategy, **params)

    output_dir = os.path.dirname(json_path)
    output_path = save_results(
        os.path.basename(json_path),
        result,
        date_str,
        strategy,
        strategy_desc,
        output_dir,
    )

    elapsed = time.time() - start_time
    print(f"完成！共发现 {len(result)} 只缩量回踩股，耗时 {elapsed:.1f} 秒", flush=True)
    print(f"结果已保存到: {output_path}", flush=True)

    return True


def main():
    parser = argparse.ArgumentParser(description="缩量回踩筛选器")
    parser.add_argument("json_path", help="涨停股JSON文件路径")
    parser.add_argument(
        "--strategy",
        required=True,
        choices=["1", "2", "3"],
        help="策略选择：1=成交量递减+价格回落，2=成交量低于均量+价格回落，3=单日缩量回踩",
    )
    parser.add_argument(
        "--shrink-ratio",
        type=float,
        default=0.8,
        help="策略1参数：每天缩量比例阈值（默认0.8）",
    )
    parser.add_argument(
        "--ma-days",
        type=int,
        default=5,
        help="策略2参数：均量计算天数（默认5）",
    )
    parser.add_argument(
        "--volume-ratio",
        type=float,
        default=None,
        help="策略2/3参数：成交量比例阈值（不传则策略2用0.6、策略3用0.7）",
    )
    parser.add_argument(
        "--min-days",
        type=int,
        default=2,
        help="策略1参数：最少连续缩量天数（默认2）",
    )

    args = parser.parse_args()

    params = {}
    if args.strategy == "1":
        params["shrink_ratio"] = args.shrink_ratio
        params["min_days"] = args.min_days
    elif args.strategy == "2":
        params["ma_days"] = args.ma_days
        params["volume_ratio"] = args.volume_ratio if args.volume_ratio is not None else 0.6
    elif args.strategy == "3":
        params["volume_ratio"] = args.volume_ratio if args.volume_ratio is not None else 0.7

    success = run_filter(args.json_path, args.strategy, params)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
