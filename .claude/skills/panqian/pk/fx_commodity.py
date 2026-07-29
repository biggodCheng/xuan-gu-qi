# -*- coding: utf-8 -*-
"""维度3:离岸人民币 + 大宗(金/油/铜)。非关键维,失败不阻断。板块映射由 render 解读。

校准依据(probe 2026-07-23 真实返回):
- fx_susdcnh 实测可达,18 字段。字段顺序与校准:
    [0]time  [1]现价  [2]bid  [3]ask  [4]vol  [5]今开  [6]high  [7]low
    [8]?(实测=现价,跨 2 次 probe 与 [1] 同步移动 → 非稳定昨收)
    [9]name  [10]?(0.03,语义不明,与 price-prev_close 算不出,疑脏数据)
    [11]pct(decimal,×100)  [12]振幅(已数学验证)  [13]?  [14]年高  [15]年低  [16]?  [17]日期
  - [12] 振幅 验证:(high-low)/price=(6.7773-6.7670)/6.7771=0.001520 ✓
  - [11] 取作 pct(decimal):典型 sina fx 格式为 [10]change/[11]pct/[12]振幅,
    实测 0.0021 → ×100 → 0.21%。数学无法完全验证([1]=[8] 意味 net=0,与 [10]/[11] 矛盾,
    sina fx 字段含混),但不编造,直接采用 [11]×100。
- 大宗 hf_GC/hf_CL/hf_HG 实测可达(15 字段,同 A50 hf_CHA50CFD 布局):
    [0]最新价  [1]空  [2]?  [3]?  [4]高  [5]低  [6]时间  [7]昨收  [8]开盘 ... [13]中文名
  [2]/[3] 实测≈现价(语义待定,疑 bid/ask 镜像)非昨收;昨收真在 [7]、开盘在 [8]
  (2026-07-29 经 CNBC/WSJ 交叉验证:CL [7]=79.26=PrevClose、[8]=80.04=Open)。
  probe 2026-07-23 平开日 [3]≈[0]≈真昨收三者重合,曾误判 [3] 为昨收,已纠正。
  hf_ 无 pct 槽位 → 从 price[0]+prev[7] 自算 pct。原 config 小写 hf_gc/cl/cu 是错代码
  (新浪海外期货代码大小写敏感,铜应为 hf_HG 非 hf_cu),已修正。
"""
import math
import re
from pk import base
from pk.config import FX, COMMODITY

# fx_susdcnh 字段索引(probe 2026-07-23 实测)
IDX_PCT_FX = 11      # pct as decimal (e.g. 0.0021 → ×100 → 0.21%)

# hf_ 期货字段索引(probe 2026-07-23 实测;2026-07-29 复测纠正昨收在 [7] 非 [3])
IDX_PRICE_HF = 0     # 最新价
IDX_PREV_HF = 7      # 昨收(pct 自算基准)— [3] 是≈现价字段非昨收(平开日误判,已纠)


def _norm(raw_code):
    """新浪 var 名可能带 hq_str_ 前缀,统一剥掉。"""
    return raw_code[7:] if raw_code.startswith("hq_str_") else raw_code


def _build_map(raw_text):
    """从新浪 hq 文本构建 code -> fields list。兼容 hq_str_ 前缀。"""
    fmap = {}
    for m in re.finditer(r'var\s+(\w+)="([^"]*)"', raw_text):
        code = _norm(m.group(1))
        payload = m.group(2)
        fmap[code] = payload.split(",") if payload else []
    return fmap


def _parse_fx(fmap, pairs):
    """fx_ 组:从字段 [IDX_PCT_FX] 取 pct(decimal,×100)。

    空 payload / 字段不足 / 非数字 / NaN/inf 均跳过(不抛)。
    """
    out = []
    for code, name in pairs:
        f = fmap.get(code, [])
        if len(f) > IDX_PCT_FX:
            try:
                pct = float(f[IDX_PCT_FX]) * 100   # decimal → percent
            except ValueError:
                continue
            if math.isfinite(pct):
                out.append({"name": name, "pct": pct})
    return out


def _parse_comm(fmap, pairs):
    """hf_ 组:从 price[0] + prev[7] 自算 pct(hf_ 无 pct 字段)。

    空 payload / 字段不足 / 非数字 / prev<=0 / NaN/inf 均跳过(不抛)。
    """
    out = []
    for code, name in pairs:
        f = fmap.get(code, [])
        if len(f) <= max(IDX_PRICE_HF, IDX_PREV_HF):
            continue
        try:
            price = float(f[IDX_PRICE_HF])
            prev = float(f[IDX_PREV_HF])
        except (ValueError, IndexError):
            continue
        if prev > 0 and math.isfinite(price) and math.isfinite(prev):
            pct = (price - prev) / prev * 100
            if math.isfinite(pct):
                out.append({"name": name, "pct": pct})
    return out


def parse_fx_comm(raw_text):
    """解析 fx + comm。返回 {'fx': [{name,pct}, ...], 'comm': [{name,pct}, ...]}。

    兼容 var 名带/不带 hq_str_ 前缀。空 payload / 字段不足 / 非数字 均跳过(不抛)。
    """
    fmap = _build_map(raw_text)
    return {"fx": _parse_fx(fmap, FX), "comm": _parse_comm(fmap, COMMODITY)}


def fetch_fx_comm():
    """返回 FetchResult(dim='fx')。

    data = {'fx': [{name,pct}, ...], 'comm': [{name,pct}, ...]}
    汇率/大宗非关键维:任一项不可用 → 该项空,不阻断;ok = bool(fx or comm)。
    detail 诚实标注可达性(✓ / ⚠️)。
    """
    codes = [c for c, _ in FX + COMMODITY]
    raw = base.sina_quote(codes)   # base 已剥 hq_str_ 前缀
    # 重建文本喂给 parse_fx_comm(带 hq_str_,parse 内 _norm 兼容剥前缀)
    text = "".join(f'var hq_str_{c}="{",".join(raw.get(c, []))}";' for c in codes)
    d = parse_fx_comm(text)
    ok = bool(d["fx"] or d["comm"])
    if ok:
        bits = []
        if d["fx"]:
            bits.append(f"{len(d['fx'])}汇率(sina)")
        if d["comm"]:
            bits.append(f"{len(d['comm'])}大宗(sina)")
        else:
            bits.append("大宗缺(hf_全空)")
        detail = "✓ " + " | ".join(bits)
    else:
        detail = "⚠️ 汇率+大宗取数失败(新浪不可达)"
    return base.FetchResult("fx", ok=ok, data=d, detail=detail)
