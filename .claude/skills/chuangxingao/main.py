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

from screener.fetcher import get_all_stocks_today, get_stock_history
from screener.calculator import filter_new_highs
from screener.storage import save_results


def _fetch_history(code: str) -> tuple[str, list[float]]:
    return code, get_stock_history(code, days=100, exclude_last=True)


def run_screener(output_dir: str | None = None, date_str: str | None = None) -> bool:
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    start_time = time.time()
    date_str = date_str or trading_day.latest_trading_day()
    trading_day.warn_if_drift(date_str)

    print(f"[{date_str}] 开始获取全 A 股当日行情...", flush=True)
    stocks_df = get_all_stocks_today()

    if stocks_df.empty:
        print("未获取到行情数据，可能是非交易日。", flush=True)
        return False

    stocks = stocks_df.to_dict("records")
    print(f"共获取 {len(stocks)} 只股票，开始并发获取历史数据（20线程）...", flush=True)

    histories = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(_fetch_history, s["code"]): s["code"] for s in stocks}
        done_count = 0
        for future in as_completed(futures):
            code, history = future.result()
            histories[code] = history
            done_count += 1
            if done_count % 500 == 0:
                print(f"  已处理 {done_count}/{len(stocks)}...", flush=True)

    print("历史数据获取完成，开始计算创新高...", flush=True)
    new_highs = filter_new_highs(stocks, histories)

    save_results(date_str, new_highs, output_dir)

    elapsed = time.time() - start_time
    print(f"完成！共发现 {len(new_highs)} 只股票创100日新高，耗时 {elapsed:.1f} 秒", flush=True)
    print(f"结果已保存到: {os.path.join(output_dir, f'{date_str}.json')}", flush=True)

    return True


if __name__ == "__main__":
    run_screener()
