# -*- coding: utf-8 -*-
"""赚钱组 vs 亏钱组共性挖掘 → 定位正期望画像。输出 _trade_pattern.md"""
import pandas as pd
import numpy as np
from collections import defaultdict, deque

SRC = 'docs/A股交易数据导出.xls'
OUT = 'docs/_trade_pattern.md'

df = pd.read_csv(SRC, sep='\t', encoding='gbk', dtype=str)
df.columns = ['code','name','flag','date','time','price','qty','amount','tid','oid','acct']
def sf(s):
    if pd.isna(s): return s
    s=str(s).strip()
    return s[2:-1] if s.startswith('="') else s
for c in ['code','name','tid','acct']: df[c]=df[c].map(sf)
for c in ['price','qty','amount']: df[c]=pd.to_numeric(df[c],errors='coerce')
df['dt']=pd.to_datetime(df['date']+' '+df['time'],format='%Y%m%d %H:%M:%S',errors='coerce')
df['donly']=pd.to_datetime(df['date'],format='%Y%m%d',errors='coerce')
df=df.sort_values('dt').reset_index(drop=True)
def side(x):
    x=str(x)
    if '买入' in x: return 'B'
    if '卖出' in x or '限价卖' in x: return 'S'
    return 'X'
df['side']=df['flag'].map(side)
tr=df[df['side'].isin(['B','S'])].copy()

# FIFO 配对，同时记录买入时间/时段/买入金额
lots=defaultdict(deque); rounds=[]
for _,r in tr.iterrows():
    c=r['code']; q=abs(r['qty']); p=r['price']; sd=r['side']; d=r['donly']; t=r['dt']
    if sd=='B':
        lots[c].append([q,p,d,t,r['name'],q*p])
    else:
        rem=q
        while rem>0:
            if not lots[c]: break
            lot=lots[c][0]; m=min(rem,lot[0])
            rounds.append(dict(code=c,name=lot[4],buy_date=lot[2],buy_dt=lot[3],sell_date=d,sell_dt=t,
                qty=m,buy_price=lot[1],sell_price=p,cost=m*lot[1],sell=m*p,pnl=m*(p-lot[1]),
                ret_pct=(p/lot[1]-1)*100,hold_days=(d-lot[2]).days))
            lot[0]-=m; rem-=m
            if lot[0]<=1e-9: lots[c].popleft()
rdf=pd.DataFrame(rounds)
rdf['hour_buy']=rdf['buy_dt'].dt.hour*60+rdf['buy_dt'].dt.minute

def market(c):
    c=str(c).zfill(6)
    if c[:3] in ('600','601','603','605','688','689'): return '沪市(主板+科创)'
    if c[:3] in ('000','001','002','003','300','301'): return '深市(主板+创业)'
    if c[0] in ('8','4','9'): return '北交所'
    return '其他'
rdf['market']=rdf['code'].map(market)
rdf['ym']=rdf['sell_date'].dt.to_period('M')

g=open(OUT,'w',encoding='utf-8'); w=lambda s='': g.write(s+'\n')
w('# 正期望画像挖掘：赚钱组 vs 亏钱组\n')
w(f'样本: {len(rdf)} 笔完整配对 | 赚钱 {len(rdf[rdf.pnl>0])} 笔 | 亏钱 {len(rdf[rdf.pnl<=0])} 笔\n')

def cmp_table(col, bins=None, labels=None, q=None):
    """按某特征分组, 输出 每组 笔数/胜率/平均盈亏/平均收益/总盈亏"""
    w(f'\n### 按【{col}】分组')
    s=rdf.copy()
    if bins is not None:
        s[col]=pd.cut(s[col],bins=bins,labels=labels)
    grp=s.groupby(col,observed=True)
    rows=[]
    for k,sub in grp:
        if len(sub)<5 and q is None: continue
        rows.append((k,len(sub),(sub.pnl>0).mean()*100,sub.pnl.mean(),sub.ret_pct.mean(),sub.pnl.sum()))
    rows.sort(key=lambda x:str(x[0]))
    w(f'  {"组":<16}{"笔数":>5}{"胜率":>7}{"平均盈亏":>10}{"平均收益%":>10}{"总盈亏":>11}')
    for k,n,wr,mp,mr,sp in rows:
        w(f'  {str(k):<16}{n:>5}{wr:>6.0f}%{mp:>10,.0f}{mr:>9.2f}%{sp:>11,.0f}')

# 1. 板块
cmp_table('market')
# 2. 买入价位
cmp_table('buy_price',bins=[0,5,10,20,30,50,100,1e5],labels=['<5','5-10','10-20','20-30','30-50','50-100','>100'])
# 3. 单笔仓位
cmp_table('cost',bins=[0,5000,10000,20000,50000,100000,1e9],labels=['<5k','5-10k','10-20k','20-50k','50-100k','>100k'])
# 4. 持仓周期
cmp_table('hold_days',bins=[-1,0,1,3,5,10,20,1000],labels=['日内','1天','2-3天','4-5天','6-10天','11-20天','>20天'])
# 5. 买入时段
def sess(m):
    if m<9*60+35: return 'A.集合竞价-开盘'
    if m<10*60: return 'B.09:35-10:00'
    if m<11*60+30: return 'C.10:00-11:30'
    if m<13*60+10: return 'D.13:00-13:10'
    if m<14*60+45: return 'E.13:10-14:45'
    return 'F.14:45-15:00'
rdf['sess_buy']=rdf['hour_buy'].map(sess)
cmp_table('sess_buy')
# 6. 卖出月份(市场环境)
cmp_table('ym')

# 7. 止盈止损习惯
w('\n### 止盈止损习惯(卖出时收益率)')
win=rdf[rdf.pnl>0]; loss=rdf[rdf.pnl<=0]
w(f'盈利单收益率: 中位 {win.ret_pct.median():.2f}%  均 {win.ret_pct.mean():.2f}%  75分位 {win.ret_pct.quantile(0.75):.2f}%  P90 {win.ret_pct.quantile(0.9):.2f}%  最大 {win.ret_pct.max():.1f}%')
w(f'亏损单收益率: 中位 {loss.ret_pct.median():.2f}%  均 {loss.ret_pct.mean():.2f}%  25分位 {loss.ret_pct.quantile(0.25):.2f}%  P10 {loss.ret_pct.quantile(0.1):.2f}%  最小 {loss.ret_pct.min():.1f}%')
w(f'→ 典型止盈位 ≈ +{win.ret_pct.median():.1f}%  典型止损位 ≈ {loss.ret_pct.median():.1f}%')
# 止盈过窄 vs 止损过宽 的样本量
w(f'盈利<{win.ret_pct.median():.0f}%就跑: {(win.ret_pct<win.ret_pct.median()).sum()} 笔 (利润没让跑)')
w(f'亏损>{abs(loss.ret_pct.median()):.0f}%才砍: {(loss.ret_pct<loss.ret_pct.median()).sum()} 笔 (亏损拖到中位以下才砍)')

# 8. 单笔仓位 vs 收益相关性
w('\n### 仓位大小与收益相关性(大单是不是更亏?)')
w(f'成本(仓位)与收益率相关系数: {rdf["cost"].corr(rdf["ret_pct"]):.3f}')
w(f'成本(仓位)与盈亏金额相关系数: {rdf["cost"].corr(rdf["pnl"]):.3f}')
big=rdf[rdf.cost>=50000]; sml=rdf[rdf.cost<20000]
w(f'大单(≥5万){len(big)}笔: 胜率{(big.pnl>0).mean()*100:.0f}% 平均收益{big.ret_pct.mean():.2f}% 平均盈亏¥{big.pnl.mean():,.0f}')
w(f'小单(<2万){len(sml)}笔: 胜率{(sml.pnl>0).mean()*100:.0f}% 平均收益{sml.ret_pct.mean():.2f}% 平均盈亏¥{sml.pnl.mean():,.0f}')

# 9. 热门票操作序列: 反复交易的票
w('\n### 热门票操作序列(交易≥5笔)')
stk=rdf.groupby(['code','name']).agg(trades=('pnl','size'),winrate=('pnl',lambda s:(s>0).mean()*100),
    pnl=('pnl','sum'),hold=('hold_days','mean'),pos=('cost','mean'),
    ym0=('ym','min'),ym1=('ym','max')).reset_index()
stk=stk[stk.trades>=5].sort_values('pnl')
w(f'\n反复交易【赚钱】TOP8 (胜率排序):')
for _,r in stk[stk.pnl>0].sort_values('winrate',ascending=False).head(8).iterrows():
    w(f'  {r.code} {r.name:<7} {r.trades:>3}笔 胜率{r.winrate:>3.0f}% 累计¥{r.pnl:>8,.0f} 均仓¥{r.pos:>7,.0f} 均持{r.hold:>4.1f}天 {r.ym0}~{r.ym1}')
w(f'\n反复交易【亏钱】TOP8 (胜率排序):')
for _,r in stk[stk.pnl<=0].sort_values('winrate').head(8).iterrows():
    w(f'  {r.code} {r.name:<7} {r.trades:>3}笔 胜率{r.winrate:>3.0f}% 累计¥{r.pnl:>8,.0f} 均仓¥{r.pos:>7,.0f} 均持{r.hold:>4.1f}天 {r.ym0}~{r.ym1}')

# 10. 情绪化: 连续亏损后的行为
w('\n### 情绪化信号: 连续亏损后的下一笔')
s=rdf.sort_values('sell_dt').reset_index(drop=True)
streak=0; after_loss=[]; after_win=[]
for i in range(len(s)):
    if i>0:
        if s.loc[i-1,'pnl']<=0: after_loss.append(s.loc[i])
        else: after_win.append(s.loc[i])
al=pd.DataFrame(after_loss); aw=pd.DataFrame(after_win)
if len(al): w(f'上一笔亏损后,本笔: {len(al)}笔 胜率{(al.pnl>0).mean()*100:.0f}% 平均仓位¥{al.cost.mean():,.0f} 平均盈亏¥{al.pnl.mean():,.0f}')
if len(aw): w(f'上一笔盈利后,本笔: {len(aw)}笔 胜率{(aw.pnl>0).mean()*100:.0f}% 平均仓位¥{aw.cost.mean():,.0f} 平均盈亏¥{aw.pnl.mean():,.0f}')
# 连续亏损≥3次后
streak=0; heavy=[]
for i in range(len(s)):
    if i>=3 and all(s.loc[j,'pnl']<=0 for j in range(i-3,i)):
        heavy.append(s.loc[i])
h=pd.DataFrame(heavy)
if len(h): w(f'连续3笔亏损后,本笔: {len(h)}笔 胜率{(h.pnl>0).mean()*100:.0f}% 平均仓位¥{h.cost.mean():,.0f} (是否加码: {">>>加码" if h.cost.mean()>s.cost.mean() else "减仓"})')

# 11. 关键洞察: 把赚钱的票汇总成画像
w('\n### === 赚钱组画像(初步) ===')
w赚=rdf[rdf.pnl>0]
w(f'赚钱单的 板块分布: {w赚.market.value_counts().to_dict()}')
w(f'赚钱单 价位中位: ¥{w赚.buy_price.median():.1f}  仓位中位: ¥{w赚.cost.median():,.0f}  持仓中位: {w赚.hold_days.median():.0f}天')
w(f'赚钱单 买入时段TOP: {w赚.sess_buy.value_counts().head(2).to_dict()}')
w(f'赚钱单 卖出月份分布: {w赚.ym.value_counts().sort_index().astype(str).to_dict()}')

g.close(); print('written',OUT,'|赚钱',len(rdf[rdf.pnl>0]),'亏',len(rdf[rdf.pnl<=0]))
