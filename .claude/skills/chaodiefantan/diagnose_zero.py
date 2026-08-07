# -*- coding: utf-8 -*-
"""诊断 08-04(反弹第1天) 超跌反弹为何 0 信号。
拆解4条件漏斗 + 验证"条件1含T日反弹、抵消跌幅"假设。
拉全A 70日OHLCV(到最新08-07), 截取到 08-04 模拟当日判定。
"""
import os, sys, collections
_SKILL = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SKILL)))
sys.path.insert(0, os.path.join(_ROOT, ".claude", "skills", "kangdie"))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

from screener.fetcher import get_all_stocks_today, get_stock_kline
from concurrent.futures import ThreadPoolExecutor, as_completed

T_DATE = "2026-08-04"
DROP = -15.0

def day_of(bar): return bar.get("day") or bar.get("date") or ""
def vol_of(bar): return bar.get("volume", bar.get("vol", 0))

def analyze(bars, idx):
    if idx < 6: return None
    tail = bars[idx-6:idx+1]  # 末7根, tail[-1]=T日(08-04)
    closes = [b["close"] for b in tail]
    vols = [vol_of(b) for b in tail]
    if closes[-6] <= 0: return None
    drop_with = (closes[-1]-closes[-6])/closes[-6]*100     # 含T日(代码当前)
    drop_without = (closes[-2]-closes[-6])/closes[-6]*100  # 不含T日(用T-1)
    # 条件2 T-1长下影
    t2=tail[-2]; o2,c2=t2["open"],t2["close"]; low2=t2.get("low",0); body2=abs(o2-c2); lower2=min(o2,c2)-low2
    c2_ok = body2>0 and lower2>=2*body2 and c2>0 and lower2/c2>=0.03
    # 条件3 T-1缩量(相对前4日均量)
    prev4=vols[-6:-2]; vol_prev=sum(prev4)/4 if len(prev4)==4 else 0
    c3_ok = vol_prev>0 and vols[-2] < vol_prev*0.8
    # 条件4 T日放量阳包阴
    t1=tail[-1]; o1,c1=t1["open"],t1["close"]; high1=t1.get("high",0); high2=t2.get("high",0); v1,v2=vols[-1],vols[-2]
    c4_ok = c1>o1 and v2>0 and v1>=v2*1.5 and c1>o2 and high1>high2
    return dict(drop_with=drop_with, drop_without=drop_without,
                c1_with=drop_with<=DROP, c1_without=drop_without<=DROP,
                c2=c2_ok, c3=c3_ok, c4=c4_ok)

def main():
    recs = get_all_stocks_today().to_dict("records")
    print(f"全A {len(recs)} 只, 拉OHLCV...", flush=True)
    kmap={}
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs={ex.submit(get_stock_kline, s["code"], 70): s["code"] for s in recs}
        done=0
        for f in as_completed(futs):
            c=futs[f]
            try: kmap[c]=f.result()
            except Exception: pass
            done+=1
            if done%1000==0: print(f"  OHLCV {done}/{len(recs)}", flush=True)
    print(f"OHLCV完成 {len(kmap)} 只, 拆解条件...", flush=True)

    stat=collections.Counter()
    samp_with=[]; samp_killed=[]
    for s in recs:
        bars=kmap.get(s["code"])
        if not bars: continue
        idx=next((i for i,b in enumerate(bars) if day_of(b).startswith(T_DATE)), None)
        if idx is None or idx<6: continue
        r=analyze(bars, idx)
        if not r: continue
        stat["total"]+=1
        if r["c1_with"]: stat["c1_with"]+=1
        if r["c1_without"]: stat["c1_without"]+=1
        if r["c1_with"] and r["c2"]: stat["c1_c2"]+=1
        if r["c1_with"] and r["c2"] and r["c3"]: stat["c1_c2_c3"]+=1
        if r["c1_with"] and r["c2"] and r["c3"] and r["c4"]: stat["sig_with"]+=1
        if r["c1_without"] and r["c2"] and r["c3"] and r["c4"]: stat["sig_without"]+=1
        # 单看c1含T通过的前10只, 看它们卡在哪个条件
        if r["c1_with"] and len(samp_with)<12:
            kill=[]
            if not r["c2"]: kill.append("长下影")
            if not r["c3"]: kill.append("缩量")
            if not r["c4"]: kill.append("阳包阴")
            samp_with.append((s["name"], s["code"], round(r["drop_with"],1), "+".join(kill) if kill else "全过"))
        # 被T日抵消的样本(T-1口径急跌但含T口径不急跌)
        if r["c1_without"] and not r["c1_with"] and len(samp_killed)<12:
            samp_killed.append((s["name"], s["code"], round(r["drop_without"],1), round(r["drop_with"],1)))

    print(f"\n===== T日={T_DATE}(反弹第1天) 4条件漏斗 =====")
    print(f"有效样本 total          = {stat['total']}")
    print(f"条件1 含T日(代码当前)   = {stat['c1_with']}")
    print(f"  +条件2 T-1长下影      = {stat['c1_c2']}")
    print(f"  +条件3 T-1缩量        = {stat['c1_c2_c3']}")
    print(f"  +条件4 阳包阴 → 信号  = {stat['sig_with']}")
    print(f"\n条件1 不含T日(用T-1算)  = {stat['c1_without']}")
    print(f"改T-1口径后 → 信号      = {stat['sig_without']}")
    print(f"\n===== 条件1(含T)通过的前12只, 卡在哪 =====")
    for n,c,d,k in samp_with: print(f"  {n}({c}) drop5={d}%  卡:{k}")
    print(f"\n===== 被T日反弹抵消的样本(T-1口径<=-15但含T>-15) =====")
    for n,c,dw,dt in samp_killed: print(f"  {n}({c}) T-1口径={dw}% → 含T口径={dt}%")

main()
