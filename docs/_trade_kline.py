# -*- coding: utf-8 -*-
"""对热门票(trades>=5)拉K线，还原买入时形态。对比赚钱组 vs 亏钱组。输出 _trade_kline.md"""
import os, time
import pandas as pd
import numpy as np
from collections import defaultdict, deque
import requests

for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"): os.environ.pop(k,None)
os.environ["NO_PROXY"]="*"
S=requests.Session(); S.trust_env=False

SRC='docs/A股交易数据导出.xls'; OUT='docs/_trade_kline.md'

# ---- 读取+FIFO配对(复用) ----
df=pd.read_csv(SRC,sep='\t',encoding='gbk',dtype=str)
df.columns=['code','name','flag','date','time','price','qty','amount','tid','oid','acct']
sf=lambda s: s[2:-1] if (pd.notna(s) and str(s).startswith('="')) else s
for c in ['code','name','tid','acct']: df[c]=df[c].map(sf)
for c in ['price','qty','amount']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['dt']=pd.to_datetime(df['date']+' '+df['time'],format='%Y%m%d %H:%M:%S',errors='coerce')
df['donly']=pd.to_datetime(df['date'],format='%Y%m%d',errors='coerce')
df=df.sort_values('dt').reset_index(drop=True)
df['side']=df['flag'].map(lambda x:'B' if '买入' in str(x) else ('S' if ('卖出' in str(x) or '限价卖' in str(x)) else 'X'))
tr=df[df.side.isin(['B','S'])]
lots=defaultdict(deque); rounds=[]
for _,r in tr.iterrows():
    c=r.code;q=abs(r.qty);p=r.price;sd=r.side;d=r.donly;t=r['dt']
    if sd=='B': lots[c].append([q,p,d,t,r.name])
    else:
        rem=q
        while rem>0:
            if not lots[c]: break
            lot=lots[c][0];m=min(rem,lot[0])
            rounds.append(dict(code=c,name=lot[4],buy_date=lot[2],buy_dt=lot[3],sell_date=d,
                buy_price=lot[1],sell_price=p,pnl=m*(p-lot[1]),ret_pct=(p/lot[1]-1)*100,hold_days=(d-lot[2]).days))
            lot[0]-=m;rem-=m
            if lot[0]<=1e-9: lots[c].popleft()
rdf=pd.DataFrame(rounds)

# 选取热门票
stk=rdf.groupby('code').size()
hot=stk[stk>=5].index.tolist()
print(f'热门票(trades>=5): {len(hot)} 只')

# ---- 拉K线 ----
def sym(code):
    c=str(code).zfill(6)
    return f'sh{c}' if c.startswith('6') else (f'bj{c}' if c.startswith(('4','8','9')) else f'sz{c}')
def kline(code,start='2024-03-01',count=800):
    s=sym(code)
    try:
        r=S.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
                params={'param':f'{s},day,{start},,{count},qfq'},timeout=15)
        d=r.json()
        if d.get('code')!=0: return []
        sd=d.get('data',{}).get(s,{})
        rows=sd.get('qfqday',[]) or sd.get('day',[])
        out=[]
        for it in rows:
            out.append(dict(date=it[0],open=float(it[1]),close=float(it[2]),high=float(it[3]),low=float(it[4]),vol=float(it[5]) if len(it)>5 else 0))
        return out
    except Exception:
        return []

def zt_thr(code):
    c=str(code).zfill(6)
    if c.startswith(('300','301','688','689')): return 19.5
    if c.startswith(('8','4','9')): return 29.5
    return 9.5

KL={}
for i,code in enumerate(hot):
    rows=kline(code)
    KL[code]=rows
    if i%5==0: time.sleep(0.3)
print(f'拉到K线: {sum(1 for v in KL.values() if v)}/{len(hot)} 只成功')

# ---- 形态指标 ----
def feats(code, buy_date, buy_price):
    rows=KL.get(code,[])
    if not rows: return None
    dates=[r['date'] for r in rows]
    # 找买入日K (YYYYMMDD -> YYYY-MM-DD)
    bd=pd.Timestamp(buy_date).strftime('%Y-%m-%d')
    if bd not in dates:
        # 找最近一天
        idx=min(range(len(dates)),key=lambda i:abs(pd.Timestamp(dates[i])-pd.Timestamp(bd)))
        if abs(pd.Timestamp(dates[idx])-pd.Timestamp(bd)).days>3: return None
    else:
        idx=dates.index(bd)
    if idx<25: return None
    closes=[r['close'] for r in rows]
    vols=[r['vol'] for r in rows]
    cur=rows[idx]
    prev_close=closes[idx-1]
    day_pct=(cur['close']-prev_close)/prev_close*100
    thr=zt_thr(code)
    # 近5日涨停次数(含当日)
    zt5=sum(1 for j in range(max(1,idx-4),idx+1) if (closes[j]-closes[j-1])/closes[j-1]*100>=thr-0.3)
    # 相对120日高点位置
    hi120=max(closes[max(0,idx-120):idx]) if idx>0 else cur['close']
    pos=buy_price/hi120*100  # 距高点的%
    # 日内位置(买入价在当日low-high的位置) 0=最低 1=最高
    ih=(buy_price-cur['low'])/(cur['high']-cur['low']) if cur['high']>cur['low'] else 0.5
    # 量比 vs 前20日均量
    mv=np.mean(vols[max(0,idx-20):idx]) if idx>=20 else cur['vol']
    vr=cur['vol']/mv if mv>0 else 1
    return dict(day_pct=day_pct,is_zt=int(day_pct>=thr-0.3),zt5=zt5,
                pos_vs_high=pos, intraday_high=ih*100, vol_ratio=vr)

rows_out=[]
for _,r in rdf.iterrows():
    if r.code not in hot: continue
    f=feats(r.code,r.buy_date,r.buy_price)
    if f:
        rows_out.append({**f,'pnl':r.pnl,'win':int(r.pnl>0),'ret':r.ret_pct,'code':r.code,'name':r.name})
F=pd.DataFrame(rows_out)
F=F.dropna(subset=['day_pct'])

g=open(OUT,'w',encoding='utf-8'); w=lambda s='': g.write(s+'\n')
w('# 买入形态还原：赚钱组 vs 亏钱组（热门票 trades≥5）\n')
w(f'样本: {len(F)} 笔 (赚钱{(F.pnl>0).sum()} / 亏钱{(F.pnl<=0).sum()})\n')
winF=F[F.pnl>0]; lossF=F[F.pnl<=0]

w(f'\n## 形态指标对比')
w(f'{"指标":<22}{"赚钱组":>14}{"亏钱组":>14}{"差异":>10}')
def line(name, a, b, fmt='{:.2f}', pct=False):
    da=fmt.format(a); db=fmt.format(b)
    diff=(a-b)
    w(f'  {name:<20}{da:>14}{db:>14}{(fmt.format(diff)):>10}')

line('买入日涨幅%', winF.day_pct.mean(), lossF.day_pct.mean())
line('近5日涨停次数', winF.zt5.mean(), lossF.zt5.mean())
line('买入日是涨停%', winF.is_zt.mean()*100, lossF.is_zt.mean()*100)
line('距120日高点%(低=深)', winF.pos_vs_high.mean(), lossF.pos_vs_high.mean())
line('日内追高%(高=追)', winF.intraday_high.mean(), lossF.intraday_high.mean())
line('量比(vs20均量)', winF.vol_ratio.mean(), lossF.vol_ratio.mean())

w(f'\n## 买入日是否涨停 / 近5日是否含涨停')
w(f'赚钱组: 买入日涨停 {winF.is_zt.sum()}/{len(winF)} = {winF.is_zt.mean()*100:.0f}%  | 近5日有涨停 {(winF.zt5>0).mean()*100:.0f}%')
w(f'亏钱组: 买入日涨停 {lossF.is_zt.sum()}/{len(lossF)} = {lossF.is_zt.mean()*100:.0f}%  | 近5日有涨停 {(lossF.zt5>0).mean()*100:.0f}%')

w(f'\n## 买入位置分布(距120日高点)')
for lo,hi,lab in [(0,70,'深跌低位<70%'),(70,90,'中位70-90%'),(90,98,'贴沿90-98%'),(98,200,'几乎最高位≥98%')]:
    a=((winF.pos_vs_high>=lo)&(winF.pos_vs_high<hi)).mean()*100
    b=((lossF.pos_vs_high>=lo)&(lossF.pos_vs_high<hi)).mean()*100
    w(f'  {lab:<16} 赚钱组 {a:>5.0f}%   亏钱组 {b:>5.0f}%')

w(f'\n## 追涨停(近5日含涨停)的盈亏')
chase=F[F.zt5>0]; nochase=F[F.zt5==0]
w(f'追涨停/近端含涨停: {len(chase)}笔 胜率{(chase.pnl>0).mean()*100:.0f}% 平均收益{chase.ret.mean():.2f}% 平均盈亏¥{chase.pnl.mean():,.0f}')
w(f'非涨停低位/冷门:    {len(nochase)}笔 胜率{(nochase.pnl>0).mean()*100:.0f}% 平均收益{nochase.ret.mean():.2f}% 平均盈亏¥{nochase.pnl.mean():,.0f}')

w(f'\n## 量能对比: 放量追 vs 缩量买')
vol_hi=F[F.vol_ratio>=1.5]; vol_lo=F[F.vol_ratio<1.0]
w(f'放量(量比≥1.5): {len(vol_hi)}笔 胜率{(vol_hi.pnl>0).mean()*100:.0f}% 平均收益{vol_hi.ret.mean():.2f}%')
w(f'缩量(量比<1.0): {len(vol_lo)}笔 胜率{(vol_lo.pnl>0).mean()*100:.0f}% 平均收益{vol_lo.ret.mean():.2f}%')

g.close(); print('written',OUT,'| 样本',len(F))
