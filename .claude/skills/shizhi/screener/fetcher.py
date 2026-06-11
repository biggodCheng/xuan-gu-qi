import os
import time

import requests

for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False


def _code_to_tencent_prefix(code: str) -> str:
    """根据股票代码判断市场前缀（sh/sz/bj）。"""
    if code.startswith("6"):
        return "sh"
    elif code.startswith("0") or code.startswith("3"):
        return "sz"
    elif code.startswith("9") or code.startswith("8") or code.startswith("4"):
        return "bj"
    return "sh"


def get_market_cap_map(codes: list[str] | None = None) -> dict[str, float]:
    """获取 A 股市值映射（腾讯财经数据源）。

    Args:
        codes: 需要查询的股票代码列表。如果提供，只查这些股票；
               否则获取全部 A 股（逐字母段扫描）。

    Returns:
        dict: code → 总市值（万元）
    """
    if codes:
        return _fetch_by_codes(codes)
    return _fetch_all()


def _fetch_by_codes(codes: list[str]) -> dict[str, float]:
    """按指定代码列表批量查询市值（腾讯接口）。"""
    cap_map: dict[str, float] = {}
    batch_size = 50

    for i in range(0, len(codes), batch_size):
        batch = codes[i : i + batch_size]
        tickers = [_code_to_tencent_prefix(c) + c for c in batch]
        try:
            url = "https://qt.gtimg.cn/q=" + ",".join(tickers)
            r = _session.get(url, timeout=15)
            lines = r.text.strip().split(";")

            for line in lines:
                line = line.strip()
                if not line or '="' not in line:
                    continue
                try:
                    data_str = line.split('="', 1)[1].rstrip('";')
                    parts = data_str.split("~")
                    if len(parts) > 45:
                        code = parts[2]
                        total_cap_yi = parts[44]  # 总市值（亿元）
                        if code and total_cap_yi:
                            cap_map[code] = float(total_cap_yi) * 1_0000
                            # 亿元 → 万元
                except (ValueError, TypeError, IndexError):
                    continue
        except Exception as e:
            print(f"批量获取市值失败 (batch {i // batch_size + 1}): {e}", flush=True)

        if i + batch_size < len(codes):
            time.sleep(0.3)

    return cap_map


def _fetch_all() -> dict[str, float]:
    """扫描全市场市值（腾讯接口，按代码前缀分批）。

    腾讯接口单次最多返回约 800 只，按代码首位数字分段查询。
    """
    cap_map: dict[str, float] = {}
    prefixes = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]

    for prefix in prefixes:
        # 用前缀 + 市场筛选出该段所有股票
        tickers = []
        for second in "0123456789":
            code_pat = prefix + second
            if code_pat.startswith("6"):
                tickers.append(f"sh{code_pat}")
            elif code_pat.startswith("0") or code_pat.startswith("3"):
                tickers.append(f"sz{code_pat}")
            elif code_pat[0] in "894":
                tickers.append(f"bj{code_pat}")

        # 这种方式不太好，改用新浪分页方式但带重试
        pass

    # 实际全量获取还是走新浪接口，但加上失败重试和降级
    return _fetch_all_sina_with_retry()


def _fetch_all_sina_with_retry(max_retries: int = 3) -> dict[str, float]:
    """通过新浪财经 API 分页获取全市场市值，带重试机制。"""
    cap_map: dict[str, float] = {}

    for attempt in range(1, max_retries + 1):
        cap_map.clear()
        page = 1
        per_page = 80
        failed = False

        while True:
            try:
                url = (
                    "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
                    "json_v2.php/Market_Center.getHQNodeData"
                )
                params = {
                    "page": page,
                    "num": per_page,
                    "sort": "symbol",
                    "asc": 1,
                    "node": "hs_a",
                    "_s_r_a": "auto",
                }
                r = _session.get(url, params=params, timeout=15)

                if r.status_code != 200:
                    print(
                        f"新浪API返回非200状态: {r.status_code} (第{attempt}次重试)",
                        flush=True,
                    )
                    failed = True
                    break

                data = r.json()

                if not data:
                    break

                for item in data:
                    try:
                        code = item.get("code", "")
                        mktcap = item.get("mktcap", "")
                        if code and mktcap:
                            cap_map[code] = float(mktcap)
                    except (ValueError, TypeError):
                        continue

                page += 1
                time.sleep(0.5)

            except Exception as e:
                print(
                    f"获取市值第 {page} 页失败: {e} (第{attempt}次重试)",
                    flush=True,
                )
                failed = True
                break

        if not failed and cap_map:
            return cap_map

        if attempt < max_retries:
            wait = attempt * 30
            print(f"等待 {wait} 秒后重试...", flush=True)
            time.sleep(wait)

    print("新浪API全部重试失败，尝试腾讯接口按需查询", flush=True)
    return cap_map
