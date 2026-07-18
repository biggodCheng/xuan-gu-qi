"""数据加载层 — akshare 东财前复权/不复权日K + parquet 缓存 + WAF 退避。

WAF 缓解: 并发≤4、指数退避(1/2/4/8s)、断点续拉、每100只sleep。
详见 spec §4.2。
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd

_COL_MAP = {
    "日期": "date", "开盘": "open", "收盘": "close",
    "最高": "high", "最低": "low", "成交量": "volume",
}


def standardize_kline(df: pd.DataFrame) -> pd.DataFrame:
    """akshare 中文列名 → 标准 {date,open,high,low,close,volume}，按日期升序。"""
    out = df.rename(columns=_COL_MAP)[["date", "open", "high", "low", "close", "volume"]]
    out = out.sort_values("date").reset_index(drop=True)
    return out


def fetch_kline(code: str, start: str, end: str, adjust: str = "qfq",
                retries: int = 3) -> pd.DataFrame | None:
    """拉单只日K。start/end 为 'YYYYMMDD'。adjust: 'qfq'前复权 / ''不复权。

    Returns:
        标准化 DataFrame，或失败返回 None。
    """
    for attempt in range(retries):
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date=start, end_date=end, adjust=adjust)
            if df is None or len(df) == 0:
                return None
            return standardize_kline(df)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)        # 1/2/4s 退避
            else:
                print(f"[data_loader] {code} adjust={adjust} 拉取失败: {e}")
                return None


def save_cache(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)


def load_cache(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


def _fmt(date_str: str) -> str:
    """'2024-01-02' → '20240102'。"""
    return date_str.replace("-", "")


def fetch_all(pool: list[dict], start: str, end: str, adjust: str,
              cache_dir: str, tag: str, max_workers: int = 4,
              sleep_every: int = 100) -> dict[str, pd.DataFrame]:
    """批量拉取全池日K并缓存。断点续拉: 已有缓存则跳过。

    Args:
        pool: [{code, name, ...}] 股票池。
        start/end: 'YYYY-MM-DD'。
        adjust: 'qfq' / ''。
        cache_dir: 缓存目录。
        tag: 缓存子目录名(如 'qfq' / 'unadj')。
    Returns:
        {code: DataFrame}。
    """
    sub_dir = os.path.join(cache_dir, tag)
    os.makedirs(sub_dir, exist_ok=True)
    start_fmt, end_fmt = _fmt(start), _fmt(end)
    result: dict[str, pd.DataFrame] = {}
    todo = []
    for s in pool:
        cache_path = os.path.join(sub_dir, f"{s['code']}.parquet")
        if os.path.exists(cache_path):
            try:
                result[s["code"]] = load_cache(cache_path)
                continue
            except Exception:
                pass
        todo.append((s["code"], cache_path))

    def _task(item):
        code, cache_path = item
        df = fetch_kline(code, start_fmt, end_fmt, adjust=adjust)
        if df is not None:
            save_cache(df, cache_path)
        return code, df

    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_task, it): it[0] for it in todo}
        for fut in as_completed(futs):
            code, df = fut.result()
            if df is not None:
                result[code] = df
            done += 1
            if done % sleep_every == 0:
                time.sleep(0.3)
                print(f"[data_loader] {tag}: {done}/{len(todo)}", flush=True)
    return result


def prefetch_waf_check(pool: list[dict], start: str, end: str,
                       sample: int = 50) -> float:
    """正式拉取前 WAF 预测试: 连拉 sample 只,返回成功率。<0.8 则中止。"""
    import random
    sample_pool = pool if len(pool) <= sample else random.sample(pool, sample)
    ok = 0
    start_fmt, end_fmt = _fmt(start), _fmt(end)
    for s in sample_pool:
        df = fetch_kline(s["code"], start_fmt, end_fmt, adjust="qfq")
        if df is not None and len(df) > 0:
            ok += 1
    rate = ok / len(sample_pool) if sample_pool else 0
    print(f"[data_loader] WAF 预测试成功率: {ok}/{len(sample_pool)} = {rate:.0%}",
          flush=True)
    return rate
