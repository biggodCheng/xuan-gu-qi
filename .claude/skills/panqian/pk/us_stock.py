# -*- coding: utf-8 -*-
"""维度1:美股三大指数 + VIX。新浪为主,Yahoo fallback。

校准依据(probe 2026-07-23 真实返回):
- 新浪返回的 var 名带 hq_str_ 前缀(hq_str_gb_ixic ...),剥掉后查 NAME_MAP。
- 字段顺序:[0]名称 [1]当前价 [2]涨跌幅% [3]时间戳 [4]涨跌额 ...
  (骨架初猜 IDX_PCT=3,实测 [3] 是时间戳,真正 pct 在 [2],已校正)
- VIX(gb_vix)新浪返回空 payload → 走 Yahoo ^VIX fallback。
"""
import re
from pk import base
from pk.config import US_INDICES, US_VIX, PROXY

# 字段索引 — 以 probe 真实输出为准
IDX_NAME = 0
IDX_PRICE = 1     # '25690.9029'
IDX_PCT = 2       # '-0.57'(骨架初猜 3,实测 [3]=时间戳,已校正为 2)
NAME_MAP = dict(US_INDICES + [US_VIX])
_YAHOO_SYMBOL = {"gb_ixic": "^IXIC", "gb_inx": "^GSPC", "gb_dji": "^DJI"}


def _norm_code(raw_code):
    """新浪 var 名可能带 hq_str_ 前缀,统一剥掉。"""
    return raw_code[7:] if raw_code.startswith("hq_str_") else raw_code


def parse_us(raw_text):
    """从新浪 hq 返回文本解析出 [{code,name,price,pct}]。

    - 兼容带/不带 hq_str_ 前缀的 var 名。
    - 空 payload、未知 code、字段不足/非数字 均跳过(不抛异常)。
    """
    out = []
    for m in re.finditer(r'var\s+(\w+)="([^"]*)"', raw_text):
        payload = m.group(2)
        if not payload:
            continue
        code = _norm_code(m.group(1))
        if code not in NAME_MAP:
            continue
        f = payload.split(",")
        try:
            price = float(f[IDX_PRICE])
            pct = float(f[IDX_PCT])
        except (IndexError, ValueError):
            continue
        out.append({"code": code, "name": NAME_MAP[code], "price": price, "pct": pct})
    return out


def _yahoo_meta(symbol):
    """Yahoo fallback:走代理取 chart meta dict。失败/不可达返回 None。

    Yahoo v8 chart API:chart.result[0].meta 含 regularMarketPrice 与
    regularMarketChangePercent。当前代理(7897)实测不可达 → 返回 None,
    上层据此降级。
    """
    r = base.proxy_get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        proxy=PROXY,
    )
    if not r:
        return None
    try:
        return r.json()["chart"]["result"][0]["meta"]
    except Exception:
        return None


def fetch_us():
    """返回 FetchResult(dim='us')。

    data = {'indices': [{code,name,price,pct}, ...], 'vix': float|None}
    新浪为主;缺失指数/VIX 走 Yahoo(代理 7897)。detail 诚实标注各源可达性。
    """
    codes = [c for c, _ in US_INDICES]
    raw = base.sina_quote(codes)  # key 形如 hq_str_gb_ixic
    # 用真实返回重建文本,parse_us 统一剥前缀;新浪无此 code 即空 payload
    text = "".join(
        f'var hq_str_{c}="{",".join(raw.get("hq_str_" + c, []))}";'
        for c in codes
    )
    items = parse_us(text)

    # Yahoo 补新浪缺失的指数
    yahoo_used = []
    have = {it["code"] for it in items}
    for c, _ in US_INDICES:
        if c in have:
            continue
        meta = _yahoo_meta(_YAHOO_SYMBOL.get(c, ""))
        if not meta:
            continue
        pct = meta.get("regularMarketChangePercent")
        price = meta.get("regularMarketPrice", 0.0)
        if pct is None:
            continue
        items.append({
            "code": c, "name": NAME_MAP[c],
            "price": float(price), "pct": float(pct),
        })
        yahoo_used.append(c)

    # VIX:新浪 gb_vix 实测返回空 → Yahoo ^VIX 取 absolute level(非 pct)
    vix = None
    vix_src = ""
    vraw = base.sina_quote([US_VIX[0]])
    vp = vraw.get("hq_str_" + US_VIX[0], vraw.get(US_VIX[0]))
    if vp and len(vp) > IDX_PRICE:
        try:
            vix = float(vp[IDX_PRICE])
            vix_src = "sina"
        except ValueError:
            vix = None
    if vix is None:
        meta = _yahoo_meta("^VIX")
        lvl = meta.get("regularMarketPrice") if meta else None
        if lvl is not None:
            vix = float(lvl)
            vix_src = "yahoo"

    ok = bool(items)
    # detail 诚实标注来源与缺口
    if ok:
        bits = [f"{len(items)}指数(sina)"]
        if yahoo_used:
            bits.append(f"Yahoo补{','.join(yahoo_used)}")
        if vix is not None:
            bits.append(f"VIX={vix:.2f}({vix_src})")
        else:
            bits.append("VIX缺(sina空+yahoo不可达)")
        detail = "✓ " + " | ".join(bits)
    else:
        detail = "✗ 美股取数失败(新浪+Yahoo 均不可达)"

    return base.FetchResult("us", ok=ok, data={"indices": items, "vix": vix}, detail=detail)
