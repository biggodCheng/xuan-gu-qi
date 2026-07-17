"""抗跌观察池 — 大盘大跌时，全市场扫描抗跌个股。

逻辑：创业板指当日跌幅 ≤ -1.5%（可 --drop 调） → 扫全A → 筛"不破前低 +
跑赢大盘 + 缩量 + 市值50-500亿 + Q2偏正"的抗跌股，作为企稳后备选种子（只看不动）。

独立运行（不吃上游输入）：python main.py [--no-q2] [--drop -1.5]
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import (
    get_all_stocks_today,
    get_index_kline,
    get_market_cap_map,
    get_stock_kline,
)
from screener.analyzer import (
    OUTPERFORM_GAP,
    MARKET_CAP_MIN,
    MARKET_CAP_MAX,
    compute_ret20,
    is_anticorrection,
    market_big_drop,
)
from screener.storage import save_results

# 创业板指（基准指数）
_INDEX_NAME = "创业板指"
_INDEX_SYMBOL = "sz399006"
_INDEX_DAYS = 150
_STOCK_KLINE_DAYS = 70  # 满足 60 日最低价比较 + 21 日 ret20
_MAX_WORKERS = 20


def run_screener(
    output_dir: str | None = None,
    use_q2: bool = True,
    drop_threshold: float = -1.5,
    use_sid: bool = True,
) -> bool:
    """执行抗跌观察池扫描。

    Args:
        output_dir: 输出目录，默认 <skill>/data。
        use_q2: 是否启用 Q2 业绩展望过滤（默认开）。
        drop_threshold: 大盘大跌触发阈值(%)，当日跌幅 ≤ 此值即触发。默认 -1.5。
        use_sid: 是否启用四大赛道标注（默认开，经 bridges 桥接 sidasaidao）。

    Returns:
        True 表示流程正常完成（无论是否命中），False 表示异常。
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    start_time = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")

    # ---- Step 1: 拉创业板指，判大盘是否大跌 ----
    print(f"[{date_str}] 拉取{_INDEX_NAME}({_INDEX_SYMBOL}) 近{_INDEX_DAYS}日K线...", flush=True)
    index_bars = get_index_kline(_INDEX_SYMBOL, days=_INDEX_DAYS)
    if not index_bars or len(index_bars) < 2:
        print(f"  {_INDEX_NAME}数据获取失败或不足，退出。", flush=True)
        save_results(date_str, [], output_dir, trigger={
            "index": _INDEX_NAME,
            "big_drop": False,
            "chg_pct": 0,
            "close": 0,
            "threshold": drop_threshold,
            "error": "index_data_unavailable",
        })
        return False

    is_drop, idx_chg, idx_close = market_big_drop(index_bars, threshold=drop_threshold)
    index_ret20 = compute_ret20(index_bars)
    if index_ret20 is None:
        index_ret20 = 0.0

    if not is_drop:
        print(
            f"  今日{_INDEX_NAME}未大跌（跌幅{idx_chg:+.2f}% > 阈值{drop_threshold}%），抗跌池不适用。",
            flush=True,
        )
        save_results(date_str, [], output_dir, trigger={
            "index": _INDEX_NAME,
            "big_drop": False,
            "chg_pct": idx_chg,
            "close": idx_close,
            "threshold": drop_threshold,
        })
        print(f"  已写空结果到 kd_{date_str}.json（count=0）。", flush=True)
        return True

    print(
        f"  [触发] {_INDEX_NAME}大跌：跌幅{idx_chg:+.2f}% <= 阈值{drop_threshold}%"
        f"（20日涨幅{index_ret20:+.1f}%），启动抗跌扫描。",
        flush=True,
    )

    trigger = {
        "index": _INDEX_NAME,
        "big_drop": True,
        "chg_pct": idx_chg,
        "close": idx_close,
        "threshold": drop_threshold,
    }

    # ---- Step 2: 全A股列表 ----
    print("获取全A股当日行情...", flush=True)
    stocks_df = get_all_stocks_today()
    if stocks_df.empty:
        print("  未获取到行情数据，可能是非交易日。", flush=True)
        save_results(date_str, [], output_dir, trigger=trigger)
        return False
    stocks = stocks_df.to_dict("records")
    print(f"  共 {len(stocks)} 只。", flush=True)

    # ---- Step 3: 市值映射，先按 50-500 亿过滤（减少 OHLCV 拉取量）----
    print("获取全A市值数据...", flush=True)
    cap_map = get_market_cap_map()
    cap_filtered = []
    for s in stocks:
        cap = cap_map.get(s["code"])
        if cap and MARKET_CAP_MIN <= cap <= MARKET_CAP_MAX:
            s["market_cap"] = round(cap, 2)
            cap_filtered.append(s)
    print(
        f"  市值[{MARKET_CAP_MIN}-{MARKET_CAP_MAX}]亿过滤后 {len(cap_filtered)}/{len(stocks)} 只。",
        flush=True,
    )

    if not cap_filtered:
        print("  市值过滤后无候选，退出。", flush=True)
        save_results(date_str, [], output_dir, trigger=trigger)
        return True

    # ---- Step 4: 并发拉个股 OHLCV（20 线程）----
    print(f"并发拉取个股 {_STOCK_KLINE_DAYS} 日OHLCV（{_MAX_WORKERS}线程）...", flush=True)
    klines_map: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(get_stock_kline, s["code"], _STOCK_KLINE_DAYS): s["code"]
            for s in cap_filtered
        }
        done = 0
        total = len(cap_filtered)
        for future in as_completed(futures):
            code = futures[future]
            try:
                klines_map[code] = future.result()
            except Exception:
                pass
            done += 1
            if done % 500 == 0:
                print(f"  OHLCV 已拉取 {done}/{total}...", flush=True)
    print(f"  OHLCV 拉取完成（{len(klines_map)} 只有数据）。", flush=True)

    # ---- Step 5: 抗跌条件判定 ----
    candidates = []
    for s in cap_filtered:
        bars = klines_map.get(s["code"], [])
        detail = is_anticorrection(bars, index_ret20, s["market_cap"])
        if detail:
            candidates.append({
                "code": s["code"],
                "name": s["name"],
                "close": s["close"],
                **detail,
                "q2": None,
            })
    print(f"  抗跌条件通过：{len(candidates)} 只。", flush=True)

    # ---- Step 6: Q2 过滤（默认开，--no-q2 可关）----
    if use_q2 and candidates:
        candidates = _q2_filter(candidates)
    elif candidates:
        for c in candidates:
            c["q2"] = "跳过"

    # ---- Step 6.5: 四大赛道标注（默认开，--no-sid 可关）----
    if use_sid and candidates:
        _sid_annotate(candidates)

    # ---- Step 7: 保存 ----
    save_results(date_str, candidates, output_dir, trigger=trigger)

    elapsed = time.time() - start_time
    print(
        f"完成！抗跌观察池 {len(candidates)} 只，耗时 {elapsed:.0f} 秒。"
        f"结果：{os.path.join(output_dir, f'kd_{date_str}.json')}",
        flush=True,
    )
    return True


def _q2_filter(candidates: list[dict]) -> list[dict]:
    """Q2 业绩展望过滤。verdict=="偏正" 通过；数据不足/失败兜底放行。"""
    try:
        from screener import bridges
        get_financial, q2_analyze = bridges.get_q2_funcs()
        print("  Q2 桥接成功，开始过滤...", flush=True)
    except Exception as e:
        print(f"  Q2 桥接失败({e})，降级为跳过（不阻断）。", flush=True)
        for c in candidates:
            c["q2"] = "跳过"
        return candidates

    passed = []
    for c in candidates:
        try:
            fin = get_financial(c["code"])
            result = q2_analyze(fin)
            verdict = result.get("q2_outlook", {}).get("verdict", "数据不足")
            c["q2"] = verdict
            # 偏正通过；数据不足兜底放行（只正向收紧，不误杀）
            if verdict == "偏正" or verdict == "数据不足":
                passed.append(c)
            else:
                pass  # 中性/偏负 → 过滤掉
        except Exception as e:
            c["q2"] = "数据不足"
            passed.append(c)  # 失败兜底放行

    filtered_out = len(candidates) - len(passed)
    print(
        f"  Q2 过滤：{len(candidates)} -> {len(passed)} 只"
        f"（过滤 {filtered_out} 只中性/偏负）。",
        flush=True,
    )
    return passed


def _sid_annotate(candidates: list[dict]) -> None:
    """给候选标注四大赛道（原地修改 c["tracks"]）。桥接失败降级为跳过，不阻断。"""
    try:
        from screener import bridges
        get_detail, match_tracks = bridges.get_sid_funcs()
        print("  四大赛道桥接成功，开始标注...", flush=True)
    except Exception as e:
        print(f"  四大赛道桥接失败({e})，降级为跳过（不阻断）。", flush=True)
        for c in candidates:
            c["tracks"] = "跳过"
        return

    sid_cnt = 0
    for c in candidates:
        try:
            det = get_detail(c["code"])
            matched = match_tracks(det.get("industry", ""), det.get("concepts", []))
            tracks = [t["track"] for t in matched]
            c["tracks"] = ",".join(tracks) if tracks else "无"
            if tracks:
                sid_cnt += 1
        except Exception:
            c["tracks"] = "数据不足"
    print(f"  四大赛道标注完成：{sid_cnt}/{len(candidates)} 只属四大赛道。", flush=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="抗跌观察池扫描")
    parser.add_argument(
        "--no-q2", action="store_true", help="跳过 Q2 业绩展望过滤"
    )
    parser.add_argument(
        "--drop", type=float, default=-1.5,
        help="大盘大跌触发阈值(%)，当日跌幅 ≤ 此值即触发（默认 -1.5）",
    )
    parser.add_argument(
        "--no-sid", action="store_true", help="跳过四大赛道标注"
    )
    args = parser.parse_args()
    run_screener(
        use_q2=not args.no_q2,
        drop_threshold=args.drop,
        use_sid=not args.no_sid,
    )
