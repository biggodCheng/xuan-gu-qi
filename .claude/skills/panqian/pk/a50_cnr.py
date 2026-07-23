# -*- coding: utf-8 -*-
"""维度2:A50 期货(关键维)+ 中概股。仅新浪(无可靠替代),A50 失败需明示。

校准依据(probe 2026-07-23 真实返回):
- 中概 gb_hxc / gb_baba 等字段同美股格式:[0]名称 [1]当前价 [2]涨跌幅% [3]时间戳
  → IDX_PRICE_GB=1 / IDX_PCT_GB=2(数学验证:gb_hxc 6180.98/-1.80,gb_baba 116.56/-1.20)。
- A50 期货 hf_CN 新浪实测返回空 payload(同 VIX),且无可靠替代(Yahoo 代理 7897 已失效)。
  A50 属 CRITICAL_DIMS → fetch_a50_cnr 返回 ok=False,detail 顶部明示盲区。
- hf_ 期货字段布局与美股不同(同族 hf_GC 实测 [0]最新价 [1]空 [2..]价格区间 [6]时间 [13]名称,
  无固定 pct 槽位)。hf_CN 既空,IDX_PRICE_HF/IDX_PCT_HF 暂留骨架占位(0/1),A50 恢复后须重新
  probe 校准;当前 a50 取空 → None 路径,_pick 不会被触发,占位索引无副作用。
"""
import re
from pk import base
from pk.config import A50_CODE, CNR_DRAGON, CNR_STOCKS

# 字段索引 — 以 probe 真实输出为准
IDX_PRICE_HF = 0     # hf_ 期货最新价(hf_GC 实测 [0]);A50(hf_CN)实测空,占位待校准
IDX_PCT_HF = 1        # 同上占位(hf_GC [1]实测为空,A50 恢复后须重探)
IDX_PRICE_GB = 1      # 中概 gb_ 当前价(probe 实测 [1])
IDX_PCT_GB = 2        # 中概涨跌幅(probe 实测 [2],美股式)


def _norm(raw_code):
    """新浪 var 名可能带 hq_str_ 前缀,统一剥掉。"""
    return raw_code[7:] if raw_code.startswith("hq_str_") else raw_code


def _pick(fields, idx_price, idx_pct):
    try:
        return {"price": float(fields[idx_price]), "pct": float(fields[idx_pct])}
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
        a50 = _pick(af, IDX_PRICE_HF, IDX_PCT_HF)

    cnr = []
    for code, name in [CNR_DRAGON] + CNR_STOCKS:
        f = fields_map.get(code, [])
        if not f:
            continue
        p = _pick(f, IDX_PRICE_GB, IDX_PCT_GB)
        if p:
            cnr.append({"name": name, "pct": p["pct"]})
    return {"a50": a50, "cnr": cnr}


def fetch_a50_cnr():
    """返回 FetchResult(dim='a50')。

    data = {'a50': {price,pct}|None, 'cnr': [{name,pct}, ...]}
    A50 是关键维:新浪 hf_CN 不可用时 ok=False,detail 明示盲区(不编造数据)。
    中概在 A50 失败时仍尽量解析(不阻断),只要 A50 在即算本维 ok。
    """
    codes = [A50_CODE[0], CNR_DRAGON[0]] + [c for c, _ in CNR_STOCKS]
    raw = base.sina_quote(codes)  # base 已剥 hq_str_ 前缀,key 是 bare code
    # 重建文本喂给 parse_a50_cnr(带 hq_str_,parse 内 _norm 兼容剥前缀)
    text = "".join(f'var hq_str_{c}="{",".join(raw.get(c, []))}";' for c in codes)
    d = parse_a50_cnr(text)

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
