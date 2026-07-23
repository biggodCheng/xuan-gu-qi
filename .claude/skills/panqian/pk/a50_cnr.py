# -*- coding: utf-8 -*-
"""维度2:A50 期货(关键维)+ 中概股。仅新浪(无可靠替代),A50 失败需明示。

校准依据(probe 2026-07-23 真实返回):
- A50 期货 hf_CHA50CFD 实测可达(15 字段,夜盘实时)。字段布局:
    [0]最新价  [1]空  [2]开盘  [3]昨收  [4]高  [5]低  [6]时间 ... [13]中文名
  hf_ 接口无 pct 字段 → pct 自算 (price-prev)/prev*100。
  原 config hf_CN 是错代码(新浪无此标的),已改 hf_CHA50CFD。
  备份 hf_HSI(恒指期货,同字段布局),主代码失效时 fetch 内降级尝试。
- 中概 gb_hxc / gb_baba 等字段同美股格式:[0]名称 [1]当前价 [2]涨跌幅% [3]时间戳
  → IDX_PRICE_GB=1 / IDX_PCT_GB=2(数学验证:gb_hxc/gb_baba pct 字段直接可用)。
"""
import re
from pk import base
from pk.config import A50_CODE, CNR_DRAGON, CNR_STOCKS

# hf_ 期货字段索引(probe 2026-07-23 实测 hf_CHA50CFD 15 字段)
IDX_PRICE_HF = 0     # 最新价
IDX_PREV_HF = 3      # 昨收(pct 自算基准)
IDX_NAME_HF = 13     # 中文名(仅展示参考,parser 当前未读)
# 中概 gb_ 字段索引(美股式,[2]直接是 pct%)
IDX_PRICE_GB = 1
IDX_PCT_GB = 2


def _norm(raw_code):
    """新浪 var 名可能带 hq_str_ 前缀,统一剥掉。"""
    return raw_code[7:] if raw_code.startswith("hq_str_") else raw_code


def _pick_hf(fields):
    """hf_ 期货:price([0]) + prev([3]) 自算 pct(hf_ 无 pct 字段)。

    prev<=0 / 字段不足 / 非数字 均返回 None(不抛)。
    """
    try:
        price = float(fields[IDX_PRICE_HF])
        prev = float(fields[IDX_PREV_HF])
    except (IndexError, ValueError):
        return None
    if prev <= 0:
        return None
    return {"price": price, "pct": (price - prev) / prev * 100}


def _pick_gb(fields):
    """中概 gb_:直接取 [1]价 / [2]pct%(美股式,sina 已算好)。"""
    try:
        return {"price": float(fields[IDX_PRICE_GB]), "pct": float(fields[IDX_PCT_GB])}
    except (IndexError, ValueError):
        return None


def parse_a50_cnr(raw_text):
    """从新浪 hq 返回文本解析 A50 + 中概。

    兼容 var 名带/不带 hq_str_ 前缀。空 payload、字段不足/非数字均跳过(不抛)。
    返回 {'a50': {price,pct}|None, 'cnr': [{name,pct}, ...]}。
    A50 空/缺失时 a50=None,由上层 fetch 据此降级。
    """
    fields_map = {}
    for m in re.finditer(r'var\s+(\w+)="([^"]*)"', raw_text):
        code = _norm(m.group(1))
        payload = m.group(2)
        fields_map[code] = payload.split(",") if payload else []

    a50 = None
    af = fields_map.get(A50_CODE[0], [])
    if af:
        a50 = _pick_hf(af)

    cnr = []
    for code, name in [CNR_DRAGON] + CNR_STOCKS:
        f = fields_map.get(code, [])
        if not f:
            continue
        p = _pick_gb(f)
        if p:
            cnr.append({"name": name, "pct": p["pct"]})
    return {"a50": a50, "cnr": cnr}


def fetch_a50_cnr():
    """返回 FetchResult(dim='a50')。

    data = {'a50': {price,pct}|None, 'cnr': [{name,pct}, ...]}
    A50 是关键维:主代码 hf_CHA50CFD 失败即 ok=False 并在 detail 明示盲区(不编造,不静默降级)。
    注:恒指 hf_HSI 是港股弱代理,不作 A50 静默替代(违背"客观陈列"卖点);A50_BACKUP 常量
    留在 config 备将来"明确标注的参考行"用,本 fetcher 不自动替换。中概在 A50 失败时仍解析。
    """
    cnr_codes = [CNR_DRAGON[0]] + [c for c, _ in CNR_STOCKS]
    a50_main = A50_CODE[0]

    raw = base.sina_quote([a50_main] + cnr_codes)

    # A50:主代码 hf_CHA50CFD;失败即关键维缺失(不用恒指 HSI 静默替代)
    a50 = _pick_hf(raw.get(a50_main, []))

    # 中概走 parse_a50_cnr;A50 以 _pick_hf 结果为准
    text = "".join(f'var hq_str_{c}="{",".join(raw.get(c, []))}";' for c in [a50_main] + cnr_codes)
    d = parse_a50_cnr(text)
    d["a50"] = a50

    ok = d["a50"] is not None
    if ok:
        bits = [f"A50={d['a50']['price']:.0f}({d['a50']['pct']:+.2f}%)"]
        if d["cnr"]:
            bits.append(f"{len(d['cnr'])}中概")
        detail = "✓ " + " | ".join(bits)
    else:
        # A50 关键维缺失:中概若在仍列出,但顶部明示 A50 盲区
        extra = f" | 中概{len(d['cnr'])}只(sina)" if d["cnr"] else ""
        detail = "⚠️ A50 取数失败(关键维缺失,开盘预判可靠性下降)" + extra
    return base.FetchResult("a50", ok=ok, data=d, detail=detail)
