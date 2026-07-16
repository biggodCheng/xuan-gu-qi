"""新浪财经数据源 fetcher。

东方财富 push2 接口在当前网络环境被 IP 层封锁（直连 / 代理均失败），
改用新浪财经接口。新浪不提供「板块指数 K 线」，故采用**成分股聚合**：
取板块成分股的个股日 K，等权平均合成板块走势，供趋势分析。

接口（均直连可达，无需代理）：
- 板块列表：Market_Center.getHQNodes（节点树，提取概念板块 gn_xxx）
- 成分股：Market_Center.getHQNodeData?node=gn_xxx
- 个股K线：CN_MarketData.getKLineData?symbol=<code>&scale=240&datalen=N（scale=240 即日K）

注：新浪 getKLineData 返回不复权数据；成分股聚合（20 只大市值）会稀释
单只除权跳空的影响，对趋势判断（均线 / 高低点）可接受。
"""

import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

_session = requests.Session()
_session.trust_env = False  # 新浪直连可达；系统代理(Clash)对东方财富已失效，这里也避开
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
})

_HQNODES_URL = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodes"
_HQNODE_DATA_URL = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

# 每个板块取前 N 只大市值成分股做聚合（兼顾代表性与请求量）
_MAX_COMPONENTS = 20
# 成分股少于该数则跳过该板块（数据不具代表性）
_MIN_COMPONENTS = 5


def _get_json(url, params=None, retries=3, timeout=10):
    """带重试的 JSON 请求，失败返回 None。"""
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            return r.json()
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    return None


def _collect_concept_nodes(node, out):
    """递归遍历 getHQNodes 节点树，收集概念板块（node 以 gn_ 开头）。

    节点树叶子形如 [板块名, "", node代码]；分支形如 [分类名, [子节点...]]。
    """
    if isinstance(node, list):
        if (len(node) >= 3 and isinstance(node[2], str)
                and node[2].startswith("gn_") and node[0]):
            out.append((node[0], node[2]))
        for child in node:
            _collect_concept_nodes(child, out)


def get_concept_sectors(retries: int = 3) -> list[dict]:
    """获取新浪概念板块列表（数据源：getHQNodes）。

    新浪不提供板块当日行情，故仅返回 code/name；
    close/change_pct 由 main.py 从合成 K 线回填。

    Returns:
        板块列表，每项 {code, name}。code 即新浪板块 node（如 gn_hwqc）。
    """
    data = _get_json(_HQNODES_URL, retries=retries)
    if not isinstance(data, list):
        return []

    nodes = []
    _collect_concept_nodes(data, nodes)
    seen = set()
    sectors = []
    for name, node in nodes:
        if node in seen:
            continue
        seen.add(node)
        sectors.append({"code": node, "name": name})
    return sectors


def _get_components(node, retries=3):
    """获取板块成分股（按市值降序），返回原始 dict 列表。"""
    components = []
    page = 1
    while page <= 2:  # 至多 2 页（每页 100 只，足够选头部）
        params = {
            "page": page, "num": 100, "sort": "mktcap", "asc": 0,
            "node": node, "symbol": "", "_s_r_a": "init",
        }
        data = _get_json(_HQNODE_DATA_URL, params=params, retries=retries)
        if not isinstance(data, list) or not data:
            break
        components.extend(item for item in data if item.get("symbol"))
        if len(data) < 100:
            break
        page += 1
    return components


def _get_stock_kline(symbol, datalen=120, retries=3):
    """获取个股日 K（scale=240 即日K），返回 [{day,open,close,high,low,volume}]。"""
    params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": datalen}
    data = _get_json(_KLINE_URL, params=params, retries=retries)
    if not isinstance(data, list):
        return []
    result = []
    for k in data:
        try:
            result.append({
                "day": k["day"],
                "open": float(k["open"]),
                "close": float(k["close"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "volume": float(k.get("volume", 0) or 0),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return result


def _aggregate_klines(klines_by_stock, min_coverage=0.5):
    """将多只个股 K 线等权聚合为板块合成 K 线。

    按日期对齐，每日取各成分股当日数据的均值（volume 取和）；
    仅保留至少 min_coverage 比例成分股有数据的日期。
    """
    if not klines_by_stock:
        return []
    n_stocks = len(klines_by_stock)
    threshold = max(2, int(n_stocks * min_coverage))

    day_data = defaultdict(lambda: {"open": [], "close": [], "high": [], "low": [], "volume": []})
    for klines in klines_by_stock.values():
        for k in klines:
            d = k["day"]
            day_data[d]["open"].append(k["open"])
            day_data[d]["close"].append(k["close"])
            day_data[d]["high"].append(k["high"])
            day_data[d]["low"].append(k["low"])
            day_data[d]["volume"].append(k["volume"])

    result = []
    for d in sorted(day_data.keys()):
        dd = day_data[d]
        if len(dd["close"]) < threshold:
            continue
        result.append({
            "date": d,
            "open": round(sum(dd["open"]) / len(dd["open"]), 4),
            "close": round(sum(dd["close"]) / len(dd["close"]), 4),
            "high": round(sum(dd["high"]) / len(dd["high"]), 4),
            "low": round(sum(dd["low"]) / len(dd["low"]), 4),
            "volume": round(sum(dd["volume"]), 0),
        })
    return result


def get_sector_kline(node: str, days: int = 120, retries: int = 3) -> list[dict]:
    """获取概念板块的合成日 K 线（成分股等权聚合）。

    Args:
        node: 板块 node 代码（如 gn_hwqc）。
        days: 获取最近多少个交易日。
        retries: 单次请求失败重试次数。

    Returns:
        K 线列表，每项 {date, open, close, high, low, volume}。
        成分股不足或聚合失败返回空列表。
    """
    try:
        components = _get_components(node, retries=retries)
        if len(components) < _MIN_COMPONENTS:
            return []
        components = components[:_MAX_COMPONENTS]

        klines_by_stock = {}
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(_get_stock_kline, c["symbol"], days, retries): c["symbol"]
                for c in components
            }
            for f in as_completed(futures):
                sym = futures[f]
                try:
                    kl = f.result()
                    if kl:
                        klines_by_stock[sym] = kl
                except Exception:
                    continue

        if len(klines_by_stock) < _MIN_COMPONENTS:
            return []

        result = _aggregate_klines(klines_by_stock)
        return result[-days:] if result else []
    except Exception:
        return []
