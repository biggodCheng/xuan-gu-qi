import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import get_market_cap_map
from screener.storage import load_source, save_results

WAN_TO_YI = 1e-4


def run_filter(json_path: str, threshold_yi: int = 500) -> bool:
    start_time = time.time()
    json_path = os.path.abspath(json_path)

    if not os.path.exists(json_path):
        print(f"文件不存在: {json_path}", flush=True)
        return False

    source_data = load_source(json_path)
    stocks = source_data.get("stocks", [])
    date_str = source_data.get("date", "unknown")

    if not stocks:
        print("源文件中没有股票数据。", flush=True)
        return False

    print(
        f"[{date_str}] 市值阈值: {threshold_yi}亿",
        flush=True,
    )
    print(f"源文件共 {len(stocks)} 只股票，开始获取全市场市值数据...", flush=True)

    codes = [s["code"] for s in stocks]
    cap_map = get_market_cap_map(codes)
    print(f"获取到 {len(cap_map)} 只股票的市值数据", flush=True)

    threshold_wan = threshold_yi / WAN_TO_YI

    result = []
    not_found = 0
    for s in stocks:
        code = s["code"]
        mktcap_wan = cap_map.get(code)
        if mktcap_wan is None:
            not_found += 1
            continue
        if mktcap_wan < threshold_wan:
            result.append(
                {
                    "code": code,
                    "name": s["name"],
                    "close": s["close"],
                    "market_cap_yi": round(mktcap_wan * WAN_TO_YI, 2),
                }
            )

    if not_found:
        print(f"警告: {not_found} 只股票未找到市值数据", flush=True)

    result.sort(key=lambda x: x["market_cap_yi"])

    output_dir = os.path.join(os.path.dirname(__file__), "data")
    output_path = save_results(
        os.path.basename(json_path),
        result,
        date_str,
        threshold_yi,
        len(stocks),
        output_dir,
    )

    elapsed = time.time() - start_time
    print(
        f"完成！共筛选出 {len(result)} 只市值 < {threshold_yi}亿 的股票，"
        f"耗时 {elapsed:.1f} 秒",
        flush=True,
    )
    if result:
        print(
            f"市值范围: {result[0]['market_cap_yi']}亿 ~ {result[-1]['market_cap_yi']}亿",
            flush=True,
        )
    print(f"结果已保存到: {output_path}", flush=True)

    return True


def main():
    parser = argparse.ArgumentParser(description="市值筛选器")
    parser.add_argument("json_path", help="涨停股JSON文件路径")
    parser.add_argument(
        "--threshold",
        type=int,
        default=500,
        help="市值上限，单位：亿（默认500）",
    )

    args = parser.parse_args()
    if args.threshold <= 0:
        parser.error(f"--threshold 必须为正数（单位：亿），当前值: {args.threshold}")
    success = run_filter(args.json_path, args.threshold)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
