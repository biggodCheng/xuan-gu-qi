import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import get_stock_kline
from screener.analyzer import filter_limit_ups
from screener.storage import load_source, save_results


def _fetch_kline(code: str, days: int = 20) -> tuple[str, list[dict]]:
    """获取单只股票K线数据，失败时自动重试一次。"""
    kline = get_stock_kline(code, days=days)
    if not kline:
        # 首次失败，等待后重试
        time.sleep(2)
        kline = get_stock_kline(code, days=days)
    return code, kline


def run_filter(json_path: str) -> bool:
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

    print(f"[{date_str}] 源文件共 {len(stocks)} 只股票，开始获取K线数据（20线程）...", flush=True)

    kline_map = {}
    # 降低并发到 5 线程，避免触发 API 限速
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_fetch_kline, s["code"]): s["code"]
            for s in stocks
        }
        done_count = 0
        for future in as_completed(futures):
            code, kline = future.result()
            kline_map[code] = kline
            done_count += 1
            if done_count % 10 == 0:
                print(f"  已获取 {done_count}/{len(stocks)} 只股票的K线数据...", flush=True)

    print(f"K线数据获取完成，开始筛选涨停股（主板>=9.5%, 科创板/创业板>=19.5%, 北交所>=29.5%）...", flush=True)

    result = filter_limit_ups(stocks, kline_map)

    output_dir = os.path.dirname(json_path)
    output_path = save_results(
        os.path.basename(json_path),
        result,
        date_str,
        output_dir,
    )

    elapsed = time.time() - start_time
    print(f"完成！共发现 {len(result)} 只股票近15天有涨停，耗时 {elapsed:.1f} 秒", flush=True)
    print(f"结果已保存到: {output_path}", flush=True)

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python main.py <json文件路径>", flush=True)
        sys.exit(1)
    run_filter(sys.argv[1])
