# -*- coding: utf-8 -*-
"""A股账户交易复盘：FIFO配对 + 短线交易诊断。输出 UTF-8 markdown。"""
import pandas as pd
from collections import defaultdict, deque
from datetime import datetime

SRC = 'docs/A股交易数据导出.xls'
OUT = 'docs/_trade_analysis.md'

# ---------- 1. 读取与清洗 ----------
df = pd.read_csv(SRC, sep='\t', encoding='gbk', dtype=str)
df.columns = ['code', 'name', 'flag', 'date', 'time', 'price', 'qty', 'amount', 'tid', 'oid', 'acct']

def strip_formula(s):
    if pd.isna(s): return s
    s = str(s).strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1]
    return s

df['code'] = df['code'].map(strip_formula)
df['name'] = df['name'].map(strip_formula)
df['tid'] = df['tid'].map(strip_formula)
df['acct'] = df['acct'].map(strip_formula)
df['price'] = pd.to_numeric(df['price'], errors='coerce')
df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
df['dt'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str), format='%Y%m%d %H:%M:%S', errors='coerce')
df['donly'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d', errors='coerce')
df = df.sort_values('dt').reset_index(drop=True)

# 标准化方向
def side(x):
    x = str(x)
    if '买入' in x: return 'B'
    if '卖出' in x or '限价卖' in x: return 'S'
    return 'X'  # 非买卖：股息/配号/红股等
df['side'] = df['flag'].map(side)

trade_rows = df[df['side'].isin(['B','S'])].copy()
nontrade = df[df['side']=='X'].copy()

# ---------- 2. FIFO 配对 ----------
lots = defaultdict(deque)   # code -> deque[(qty_remaining, price, date)]
rounds = []                 # 每一笔匹配出的"完整交易"
short_warn = []             # 卖出超过持仓（数据不连续）

for _, r in trade_rows.iterrows():
    code = r['code']; qty = abs(r['qty']); price = r['price']; sd = r['side']
    d = r['donly']
    if sd == 'B':
        lots[code].append([qty, price, d, r['name']])
    else:  # S
        remaining = qty
        while remaining > 0:
            if not lots[code]:
                short_warn.append((code, r['name'], remaining, price, d))
                break
            lot = lots[code][0]
            matched = min(remaining, lot[0])
            pnl = matched * (price - lot[1])
            cost = matched * lot[1]
            sell = matched * price
            hold_days = (d - lot[2]).days if pd.notna(lot[2]) and pd.notna(d) else None
            rounds.append({
                'code': code, 'name': lot[3], 'buy_date': lot[2], 'sell_date': d,
                'qty': matched, 'buy_price': lot[1], 'sell_price': price,
                'cost': cost, 'sell': sell, 'pnl': pnl,
                'ret_pct': (price/lot[1]-1)*100 if lot[1] else None,
                'hold_days': hold_days
            })
            lot[0] -= matched
            remaining -= matched
            if lot[0] <= 1e-9:
                lots[code].popleft()

rdf = pd.DataFrame(rounds)
# 未平仓持仓
open_lots = [(c, l[3], l[0], l[1], l[2]) for c, dq in lots.items() for l in dq]

# ---------- 3. 汇总统计 ----------
g = open(OUT, 'w', encoding='utf-8')
def w(s=''): g.write(s + '\n')

w('# 交易账户复盘分析（自动生成）\n')
w(f'数据范围: {df["donly"].min().date()} ~ {df["donly"].max().date()}')
w(f'成交流水: {len(df)} 条 | 买卖成交: {len(trade_rows)} 条 | 非买卖(股息/配号等): {len(nontrade)} 条')
w(f'完整配对(已平仓交易): {len(rdf)} 笔 | 数据末未平仓持仓: {len(open_lots)} 个股票')
if short_warn:
    w(f'⚠ 卖出超过持仓记录(可能数据不全或转股): {len(short_warn)} 笔')

total_pnl = rdf['pnl'].sum()
total_cost = rdf['cost'].sum()
w(f'\n## 一、核心盈亏')
w(f'已实现盈亏合计: ¥{total_pnl:,.2f}')
w(f'已平仓买入总成本(投入本金合计): ¥{total_cost:,.2f}')
w(f'已平仓总收益率: {total_pnl/total_cost*100:.2f}%')

# 胜率
wins = rdf[rdf['pnl']>0]; losses = rdf[rdf['pnl']<=0]
win_rate = len(wins)/len(rdf)*100 if len(rdf) else 0
w(f'\n## 二、胜率与盈亏比')
w(f'胜率: {len(wins)}/{len(rdf)} = {win_rate:.1f}%')
w(f'平均盈利: ¥{wins["pnl"].mean():,.2f} / 笔  平均收益率 {wins["ret_pct"].mean():.2f}%')
w(f'平均亏损: ¥{losses["pnl"].mean():,.2f} / 笔  平均收益率 {losses["ret_pct"].mean():.2f}%')
w(f'盈亏比(平均盈利/平均亏损): {abs(wins["pnl"].mean()/losses["pnl"].mean()):.2f}')
exp = win_rate/100*wins["pnl"].mean() - (1-win_rate/100)*abs(losses["pnl"].mean())
w(f'每笔期望值(¥): {exp:,.2f}')
w(f'最大单笔盈利: ¥{rdf["pnl"].max():,.2f}  最大单笔亏损: ¥{rdf["pnl"].min():,.2f}')

# 持仓周期
w(f'\n## 三、持仓周期(短线核心指标)')
hd = rdf['hold_days'].dropna()
w(f'平均持仓天数: {hd.mean():.1f} 天  中位数: {hd.median():.0f} 天')
bins = pd.cut(hd, [-1,0,1,3,5,10,20,1000], labels=['日内(T+0违规?)','1天(T+1)','2-3天','4-5天','6-10天','11-20天','>20天'])
vc = bins.value_counts().sort_index()
for k,v in vc.items():
    w(f'  {k}: {v} 笔 ({v/len(hd)*100:.1f}%)')

# 交易频率
w(f'\n## 四、交易频率与换手')
trade_days = trade_rows['donly'].nunique()
span_days = (df['donly'].max()-df['donly'].min()).days
w(f'交易自然日跨度: {span_days} 天 ({span_days/30.4:.1f} 月)  实际交易天数: {trade_days} 天')
w(f'平均每个交易日下单项数: {len(trade_rows)/trade_days:.1f}')
w(f'平均每月完整配对笔数: {len(rdf)/(span_days/30.4):.1f}')
w(f'交易的不同股票数: {trade_rows["code"].nunique()} 只')

# 单笔金额分布
w(f'\n## 五、仓位管理(单笔买入金额)')
buy_amt = trade_rows[trade_rows['side']=='B']['amount']
w(f'单笔买入金额 平均: ¥{buy_amt.mean():,.0f}  中位数: ¥{buy_amt.median():,.0f}')
w(f'最小: ¥{buy_amt.min():,.0f}  最大: ¥{buy_amt.max():,.0f}  总和: ¥{buy_amt.sum():,.0f}')
ab = pd.cut(buy_amt, [0,3000,5000,10000,30000,100000,1e9], labels=['<3k','3-5k','5-10k','10-30k','30-100k','>100k'])
for k,v in ab.value_counts().sort_index().items():
    w(f'  {k}: {v} 笔 ({v/len(buy_amt)*100:.1f}%)')

# 买卖时点偏好
w(f'\n## 六、买卖时点偏好(下单时间)')
trade_rows2 = trade_rows.copy()
trade_rows2['hour'] = trade_rows2['dt'].dt.hour
trade_rows2['quarter'] = (trade_rows2['dt'].dt.hour*60+trade_rows2['dt'].dt.minute)
def session(m):
    if m < 9*60+35: return '09:25-09:35 集合竞价/开盘急'
    if m < 10*60: return '09:35-10:00 早盘'
    if m < 11*60+30: return '10:00-11:30 上午盘中'
    if m < 13*60+10: return '13:00-13:10 午后开盘'
    if m < 14*60+45: return '13:10-14:45 下午盘中'
    return '14:45-15:00 尾盘'
trade_rows2['sess'] = trade_rows2['quarter'].map(session)
for k,v in trade_rows2['sess'].value_counts().reindex(['09:25-09:35 集合竞价/开盘急','09:35-10:00 早盘','10:00-11:30 上午盘中','13:00-13:10 午后开盘','13:10-14:45 下午盘中','14:45-15:00 尾盘']).fillna(0).items():
    w(f'  {k}: {int(v)} 笔 ({v/len(trade_rows2)*100:.1f}%)')

# 个股盈亏排行
w(f'\n## 七、个股盈亏(按已平仓)')
stk = rdf.groupby(['code','name']).agg(pnl=('pnl','sum'), trades=('pnl','size'),
    winrate=('pnl', lambda s: (s>0).mean()*100), buy_cost=('cost','sum')).reset_index()
stk = stk.sort_values('pnl')
w('\n亏钱最多的10只:')
for _,r in stk.head(10).iterrows():
    w(f'  {r["code"]} {r["name"]:<6} 盈亏¥{r["pnl"]:>10,.0f}  交易{r["trades"]:>2}笔 胜率{r["winrate"]:.0f}%')
w('\n赚钱最多的10只:')
for _,r in stk.sort_values('pnl',ascending=False).head(10).iterrows():
    w(f'  {r["code"]} {r["name"]:<6} 盈亏¥{r["pnl"]:>10,.0f}  交易{r["trades"]:>2}笔 胜率{r["winrate"]:.0f}%')

# 同一只票反复交易(补仓摊平特征)
w(f'\n## 八、行为特征')
repeat = stk[stk['trades']>=5].sort_values('trades',ascending=False).head(10)
w('反复交易最多的股票(可能存在"补仓摊平/反复抄底"特征):')
for _,r in repeat.iterrows():
    w(f'  {r["code"]} {r["name"]:<6} 交易{r["trades"]:>2}笔 累计盈亏¥{r["pnl"]:>9,.0f}')

# 止盈止损特征：盈利单 vs 亏损单 持仓天数
w('\n止盈速度 vs 止损速度:')
w(f'  盈利单平均持仓 {wins["hold_days"].mean():.1f} 天 / 亏损单平均持仓 {losses["hold_days"].mean():.1f} 天')
w(f'  盈利单平均收益率 {wins["ret_pct"].mean():.2f}% / 亏损单平均收益率 {losses["ret_pct"].mean():.2f}%')

# 月度盈亏曲线
w(f'\n## 九、月度盈亏曲线')
rdf['ym'] = rdf['sell_date'].dt.to_period('M')
mp = rdf.groupby('ym')['pnl'].sum()
cum = 0
for k,v in mp.items():
    cum += v
    bar = '█'*max(1,int(abs(v)/max(1,abs(mp).max())*30))
    sign = '+' if v>=0 else '-'
    w(f'  {k}  {sign}¥{abs(v):>9,.0f} {bar}  累计¥{cum:>,.0f}')

# 交易成本吞噬
w(f'\n## 十、交易成本吞噬(过度交易的代价)')
buy_amt = trade_rows[trade_rows['side']=='B']['amount'].sum()
sell_amt = trade_rows[trade_rows['side']=='S']['amount'].sum()
turnover = buy_amt + sell_amt
stamp = sell_amt*0.0005
comm = turnover*0.00025
transfer = turnover*0.00001
tc = stamp+comm+transfer
w(f'累计买入 ¥{buy_amt:,.0f} + 累计卖出 ¥{sell_amt:,.0f} = 双边周转 ¥{turnover:,.0f}')
w(f'估算: 印花税(卖0.05%)¥{stamp:,.0f} + 佣金(双边万2.5)¥{comm:,.0f} + 过户费¥{transfer:,.0f}')
w(f'交易成本合计 ¥{tc:,.0f}  → 占已实现亏损({total_pnl:,.0f})的 {abs(tc/total_pnl)*100:.0f}%')
w(f'每笔完整交易平均被成本吃掉 ¥{tc/len(rdf):,.0f} (平均盈利才 ¥{wins["pnl"].mean():,.0f})')

# 真实资金占用估算: 每日净持仓成本峰值
w(f'\n## 十一、真实资金占用(估算本金)')
daily_pos = []
hold_map = defaultdict(float)  # code -> 持仓成本
peak = 0; peak_date=None
for _,r in trade_rows.iterrows():
    c=r['code']; q=r['qty']; p=r['price']
    if r['side']=='B':
        hold_map[c]+=abs(q)*p
    else:
        # FIFO扣减成本(近似: 按比例)
        cur_cost = hold_map[c]
        cur_qty = max(abs(q),1e-9)
        # 用当前持仓成本近似
        hold_map[c] = max(0, cur_cost - abs(q)*p) if cur_cost>0 else 0
    tot=sum(hold_map.values())
    if tot>peak: peak=tot; peak_date=r['donly']
w(f'估算日内持仓峰值成本 ¥{peak:,.0f} (峰值日 {peak_date.date() if pd.notna(peak_date) else "?"})')
w(f'→ 真实本金可能仅 ¥{peak:,.0f} 量级; 18.4万亏损相对本金的实际损失比例可能高达 {abs(total_pnl)/peak*100:.0f}%+')
w(f'→ 累计周转¥{turnover:,.0f}/本金≈{turnover/peak:.0f}倍换手, 典型高频消耗')

# 持仓周期分桶 vs 收益率(越拿越亏吗)
w(f'\n## 十二、持仓周期 vs 收益率(是否越拿越亏)')
rdf['hbin']=pd.cut(rdf['hold_days'].fillna(-1),[-2,0,1,3,5,10,20,1000],labels=['日内','1天','2-3天','4-5天','6-10天','11-20天','>20天'])
for k,sub in rdf.groupby('hbin',observed=True):
    if len(sub)==0: continue
    w(f'  {k}: {len(sub):>4}笔 平均收益{sub["ret_pct"].mean():>6.2f}% 胜率{(sub["pnl"]>0).mean()*100:>4.0f}% 平均盈亏¥{sub["pnl"].mean():>7,.0f}')

# 按收益率分桶
w(f'\n## 十三、单笔收益率分布')
rb = pd.cut(rdf['ret_pct'], [-100,-10,-5,-2,0,2,5,10,1000], labels=['<-10%','-10~-5%','-5~-2%','-2~0%','0~2%','2~5%','5~10%','>10%'])
for k,v in rb.value_counts().sort_index().items():
    w(f'  {k}: {v} 笔 ({v/len(rdf)*100:.1f}%)')

g.close()
print('analysis written to', OUT)
print('RDF rows:', len(rdf), 'total pnl:', round(total_pnl,2))
