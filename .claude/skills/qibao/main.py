import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

# Windows 中文控制台默认 GBK(cp936), print 中文会乱码;
# 统一 stdout/stderr 用 utf-8(失败则忽略, 不阻断)。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from screener.fetcher import get_stock_kline
from screener.analyzer import MIN_HISTORY, filter_qibao
from screener.storage import load_source, save_results

DAYS = 120  # K线获取天数（覆盖布林20+MACD26+9的warmup，留余量）


def _fetch_kline(code: str, days: int) -> tuple[str, list[dict]]:
    return code, get_stock_kline(code, days=days)


def run_filter(json_path: str, days: int = DAYS) -> bool:
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

    print(f"[{date_str}] 起爆点筛选，源文件共 {len(stocks)} 只股票，"
          f"获取K线（20线程）...", flush=True)

    kline_map: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(_fetch_kline, s["code"], days): s["code"] for s in stocks}
        done = 0
        for future in as_completed(futures):
            code, kline = future.result()
            kline_map[code] = kline
            done += 1
            if done % 50 == 0:
                print(f"  已获取 {done}/{len(stocks)} ...", flush=True)

    skipped = sum(1 for k in kline_map.values() if len(k) < MIN_HISTORY)
    print(f"K线获取完成（历史不足{MIN_HISTORY}日跳过 {skipped} 只），筛选起爆点...", flush=True)

    result = filter_qibao(stocks, kline_map)

    output_dir = os.path.join(os.path.dirname(__file__), "data")
    output_path = save_results(os.path.basename(json_path), result, date_str, output_dir)

    xushi_count = sum(1 for r in result if r.get("xushi"))
    elapsed = time.time() - start_time
    print(f"完成！起爆 {len(result)} 只（其中兼蓄势 {xushi_count} 只），耗时 {elapsed:.1f}s", flush=True)
    print(f"结果已保存到: {output_path}", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="起爆点筛选器")
    parser.add_argument("json_path", help="创新高股JSON文件路径")
    parser.add_argument("--days", type=int, default=DAYS, help=f"K线获取天数（默认{DAYS}）")
    args = parser.parse_args()
    success = run_filter(args.json_path, args.days)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
