"""zhuxian 数据源 v3: 东财板块成分股 + 本地 vipdoc 全成分聚合。

演进:
- v1 新浪前 20 龙头聚合 → 龙头拉偏(创新药报 +2.37%, 真实板块 -0.93%)
- v2 东财 push2his 真实板块指数 → push2his 被 IP 限频, 不稳定
- v3(本版) 东财成分股(push2delay 稳定) + 本地 vipdoc 全成分聚合(零网络真实)

数据流:
- 板块列表 + 当日涨跌: 东财 clist push2delay(fs=m:90+t:3+f:!50) → 真实板块涨跌
- 板块成分股: 东财 clist push2delay(fs=b:BKxxxx) → 全成分代码
- 个股日K: 本地招商证券 vipdoc(scripts/local_kline.py, 不复权, 零网络)
- 板块趋势K线: 全成分等权聚合(非真实板块指数, 但全成分聚合≈真实板块感受)

局限: lday 不复权, 全成分聚合会稀释单只除权跳空(同 v1 新浪聚合);
      板块K线为聚合非东财真实板块指数(东财概念板块指数不在本地 vipdoc)。
"""
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# 接入本地 vipdoc 读取模块: fetcher.py→screener→zhuxian→skills→.claude→项目根
_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT / "scripts"))
import local_kline  # noqa: E402

_session = requests.Session()
_session.trust_env = False  # 东财直连; Clash 系统代理对 push2 会 reset
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/center/boardlist.html",
})

_CLIST_URL = "http://push2delay.eastmoney.com/api/qt/clist/get"
_UT = "bd1d9ddb04089700cf9c27f6f7426281"
_MIN_COMPONENTS = 5  # 成分股(或有本地数据)少于此数跳过该板块

# 东财"风格/元板块"黑名单(条件选股集合,趋势分自我实现虚高,非行业概念主线)。
# 2026-07-21 经识别从 495 个概念板块筛出; "参股XX"(参股券商/银行/期货/保险/新三板)
# 是真题材概念,已排除在外(保留)。东财若增删风格板块,重跑识别脚本更新此表。
_STYLE_BK_BLACKLIST = {
    "BK0498","BK0499","BK0501","BK0511","BK0552","BK0567","BK0636","BK0707",
    "BK0718","BK0803","BK0804","BK0815","BK0816","BK0817","BK1050","BK1051",
    "BK1053","BK1059","BK1108","BK1112","BK1158","BK1198","BK1199","BK1630",
    "BK1631","BK1632","BK1633","BK1635","BK1636","BK1637","BK1639","BK1640",
    "BK1641","BK1642","BK1643","BK1645","BK1661","BK1662","BK1663","BK1664",
    "BK1665","BK1666","BK1667","BK1668","BK1669","BK1670","BK1671","BK1672",
    "BK1673","BK1674","BK1675","BK1676","BK1680","BK1681","BK1710","BK1711",
    "BK1712","BK1713","BK1714","BK1715","BK1716","BK1717","BK1749","BK1752",
}


def _is_style_board(code: str) -> bool:
    """板块是否为风格/元板块(条件选股集合)。"""
    return code in _STYLE_BK_BLACKLIST


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


def get_concept_sectors(retries: int = 3) -> list[dict]:
    """东财概念板块列表(含真实板块代码、名称、当日涨跌)。push2delay 稳定源。

    Returns: 每项 {code(BKxxxx), name, close(板块点数), change_pct(当日%)}。
    """
    sectors = []
    pn = 1
    while pn <= 10:
        params = {
            "pn": pn, "pz": 100, "po": 1, "np": 1, "ut": _UT,
            "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:90+t:3+f:!50",
            "fields": "f12,f14,f2,f3",
        }
        data = _get_json(_CLIST_URL, params=params, retries=retries)
        if not isinstance(data, dict) or not data.get("data"):
            break
        diff = data["data"].get("diff") or []
        if not diff:
            break
        for it in diff:
            code = it.get("f12"); name = it.get("f14")
            if not code or not name:
                continue
            if _is_style_board(code):
                continue
            sectors.append({
                "code": code, "name": name,
                "close": it.get("f2"), "change_pct": it.get("f3"),
            })
        if len(diff) < 100:
            break
        pn += 1
        time.sleep(0.2)
    return sectors


def _prefix(code: str) -> str:
    """6 位个股代码 → 本地 vipdoc 市场前缀(sh/sz/bj)。"""
    if code.startswith("6"):
        return "sh"
    if code.startswith(("4", "8", "920")):
        return "bj"
    return "sz"


def _get_board_members(bk_code: str, retries: int = 3) -> list[str]:
    """东财 clist 拉板块成分股(fs=b:BKxxxx)，返回 6 位代码列表(剔除 ST)。"""
    codes = []
    for pn in range(1, 11):
        params = {
            "pn": pn, "pz": 100, "po": 1, "np": 1, "ut": _UT,
            "fltt": 2, "invt": 2, "fid": "f20", "fs": f"b:{bk_code}",
            "fields": "f12,f14",
        }
        data = _get_json(_CLIST_URL, params=params, retries=retries)
        if not isinstance(data, dict) or not data.get("data"):
            break
        diff = data["data"].get("diff") or []
        if not diff:
            break
        for it in diff:
            code = it.get("f12"); name = it.get("f14") or ""
            if code and not name.startswith(("ST", "*ST")):
                codes.append(code)
        if len(diff) < 100:
            break
        time.sleep(0.1)
    return codes


def _aggregate(klines_by_stock: dict, min_coverage: float = 0.5) -> list[dict]:
    """全成分等权聚合: 按日期对齐，每日 OHLC 取均值、volume 求和。
    仅保留至少 min_coverage 比例成分股有数据的日期。"""
    if not klines_by_stock:
        return []
    threshold = max(2, int(len(klines_by_stock) * min_coverage))
    day_data = defaultdict(lambda: {"open": [], "close": [], "high": [], "low": [], "volume": []})
    for kl in klines_by_stock.values():
        for k in kl:
            d = k["date"]
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


def get_sector_kline(bk_code: str, days: int = 120, retries: int = 3) -> list[dict]:
    """板块合成日K = 本地全成分个股等权聚合。

    Args:
        bk_code: 东财板块代码(BKxxxx)。
        days: 取最近多少个交易日。

    Returns:
        K线列表(日期升序)，每项 {date,open,close,high,low,volume}。失败返回空。
    """
    try:
        codes = _get_board_members(bk_code, retries)
    except Exception:
        return []
    if len(codes) < _MIN_COMPONENTS:
        return []
    klines_by_stock = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(local_kline.read_day, f"{_prefix(c)}{c}"): c for c in codes}
        for f in as_completed(futures):
            c = futures[f]
            try:
                kl = f.result()
                if kl:
                    klines_by_stock[c] = kl
            except Exception:
                continue
    if len(klines_by_stock) < _MIN_COMPONENTS:
        return []
    result = _aggregate(klines_by_stock)
    return result[-days:] if result else []
