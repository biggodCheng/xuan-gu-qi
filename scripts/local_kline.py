# -*- coding: utf-8 -*-
"""招商证券 vipdoc 本地日K读取 (通达信内核 .day 二进制)。

本地直读, 零网络, 永不被 WAF 封。沪深北全覆盖, 含指数(sh000001 等)。

格式: 每记录 32 字节, struct '<IIIIIfII'
  date(int YYYYMMDD) open/high/low/close(int, 实际价÷100)
  amount(float32, 成交额元) vol(int, 成交量手) reserve(int)

⚠️ 局限: lday 存的是不复权原始价 (除权除息会让K线跳空, 破坏均线/新高/回测连续性)。
  - 指数 / 短期形态 / 当日涨跌 / 量能比 → 不复权即可用 (除权对短期窗口影响极小)
  - 跨季新高 / 长期趋势 / 回测 → 需前复权, 走新浪 (akshare adjust='qfq'), 本库不提供
"""
import os
import re
import struct
from collections import Counter

# vipdoc 根目录; 可用环境变量 VIPDOC_DIR 覆盖 (换机器/换人)
VIPDOC = os.environ.get("VIPDOC_DIR", r"D:\APP\招商证券\vipdoc")

_REC = 32           # 每条记录 32 字节
_FMT = "<IIIIIfII"  # date open high low close amount vol reserve


def _day_path(sym):
    """sym='sh000001' → vipdoc/sh/lday/sh000001.day。sym 前缀即市场(sh/sz/bj)。"""
    sym = sym.lower()
    return os.path.join(VIPDOC, sym[:2], "lday", f"{sym}.day")


def _parse_day_bytes(data):
    """解析 .day 字节流 → [{date,open,high,low,close,volume,amount}, ...] 正序(早→晚)。
    date='YYYY-MM-DD'; 价格=原值(已÷100); volume=成交量(手); amount=成交额(元,float32)。
    尾部不足 32 字节的残缺记录忽略。"""
    out = []
    for i in range(len(data) // _REC):
        b = data[i * _REC:(i + 1) * _REC]
        date, o, h, l, c, amount, vol, _res = struct.unpack(_FMT, b)
        d = str(date)
        out.append({
            "date": f"{d[0:4]}-{d[4:6]}-{d[6:8]}",
            "open": o / 100.0,
            "high": h / 100.0,
            "low": l / 100.0,
            "close": c / 100.0,
            "volume": vol,      # 成交量(手)
            "amount": amount,   # 成交额(元)
        })
    return out


def read_day(sym):
    """读本地 .day → 完整字段 list。文件不存在返回 []。"""
    path = _day_path(sym)
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        return _parse_day_bytes(f.read())


def fetch_index_kline(sym, days=70):
    """对齐 fupan/market_regime 的 fetch_index_kline 接口:
    返回 [{date, close, volume}, ...] 正序, 取末尾 days 条。
    volume 用成交额(元), 与新浪 getKLineData 语义一致 (供 fupan 量能比判定, 单位无关)。
    纯本地读取, 不触网; 调用方需自行 fallback 网络 (见 fupan.main.fetch_index_kline)。"""
    rows = read_day(sym)
    if days and len(rows) > days:
        rows = rows[-days:]
    return [{"date": r["date"], "close": r["close"], "volume": r["amount"]} for r in rows]


# ---------- 全市场宽度 (供 market_regime.fetch_market_breadth 本地首选源) ----------
def _classify_a_share(sym):
    """按 vipdoc 文件名前缀判定 A股板块, 非A股(指数/B股/基金/债券/转债)返回 None。
    sym 如 'sh600519'/'sz000001'/'bj430047'。
    返回 'main'/'cyb'/'kcb'/'bj' 或 None。"""
    s = sym.lower()
    if not s.startswith(("sh", "sz", "bj")):
        return None
    num = s[2:]
    if s.startswith("sh"):
        if num.startswith(("000", "880", "9", "5", "10", "11", "13")):  # 指数(上证000/通达信板块880)/沪B/基金/转债
            return None
        if num.startswith(("688", "689")):
            return "kcb"
        return "main"                                             # 600/601/603/605 沪主板
    if s.startswith("sz"):
        if num.startswith(("399", "2", "15", "16", "18", "11", "12", "13")):  # 指数/深B/基金/转债
            return None
        if num.startswith(("300", "301")):
            return "cyb"
        return "main"                                             # 000/001/002/003 深主板
    return "bj"                                                   # 北交所 8/4/920


def fetch_local_breadth():
    """本地招商证券 vipdoc 全市场当日宽度 (零网络, 永不被封, 最快最全)。
    遍历 sh/sz/bj 的 lday/*.day, 取每只 A股尾两根 close 算当日涨跌幅。

    返回 (pairs, latest_date, coverage):
      pairs       = [(code6, chg_percent), ...] 已过滤指数/B股/基金 + 涨跌幅超限(除权异常)
      latest_date = 'YYYY-MM-DD' 全市场众数最新交易日
      coverage    = 最新日期==latest_date 的 A股数量(当天数据覆盖率)
    性能: ~6700只仅需 1-2s(每文件只读尾部 64 字节, 不读全文件)。
    局限: lday 不复权, 除权日 close 下跳会造成单日假跌停 → 用涨跌幅超限过滤排除。"""
    _REC, _FMT = 32, "<IIIIIfII"
    pairs = []
    date_cnt = Counter()
    for market in ("sh", "sz", "bj"):
        d = os.path.join(VIPDOC, market, "lday")
        if not os.path.isdir(d):
            continue
        try:
            files = os.listdir(d)
        except Exception:
            continue
        for fname in files:
            if not fname.endswith(".day"):
                continue
            sym = fname[:-4]
            bd = _classify_a_share(sym)
            if bd is None:
                continue
            try:
                size = os.path.getsize(os.path.join(d, fname))
                n = size // _REC
                if n < 2:
                    continue
                with open(os.path.join(d, fname), "rb") as f:
                    f.seek((n - 2) * _REC)
                    b = f.read(2 * _REC)
                _d1, _o1, _h1, _l1, c1, _a1, _v1, _ = struct.unpack(_FMT, b[:_REC])
                _d2, _o2, _h2, _l2, c2, _a2, _v2, _ = struct.unpack(_FMT, b[_REC:])
            except Exception:
                continue
            ds = str(_d2)
            date_cnt[f"{ds[0:4]}-{ds[4:6]}-{ds[6:8]}"] += 1
            if c1 <= 0:
                continue
            chg = (c2 - c1) / c1 * 100.0
            # 涨跌幅超真实涨跌停极限 → 除权/数据异常, 排除
            limit = 30.5 if bd == "bj" else (20.3 if bd in ("cyb", "kcb") else 10.2)
            if abs(chg) > limit:
                continue
            pairs.append((re.sub(r"\D", "", sym)[-6:], chg))
    if not date_cnt:
        return [], "", 0
    latest_date = date_cnt.most_common(1)[0][0]
    return pairs, latest_date, date_cnt.get(latest_date, 0)
