# boduan(波段)skill 设计 — 阶段 2:skill 落地

> 2026-08-08 · 基于阶段 1 spec(`2026-08-08-band-oversold-rebound-design.md`)的回测验证结果,落地为独立 skill。
> 阶段 1 已验证:`is_band_rebound` 全量 2018-2026 回测 31/36 达标,最优 X=30 R=2.5 → +5.06%/胜率 59%/熊市全正。

## 1. skill 定位

- **命名**:boduan(波段)
- **触发词**:"波段超跌" / "波段反弹" / "超跌波段"
- **定位**:与 chaodiefantan(短线超跌反抽,5日急跌+长下影)**并行**的独立选股 skill。捕捉**月度级超跌后的反弹启动**(20日跌>30% + 放量阳包阴)。
- **区别 chaodiefantan**:窗口 5日→20日;去 T-1 长下影(阶段1诊断的瓶颈);保留阳包阴放量。

## 2. 信号参数(回测最优,固定常量)

| 参数 | 值 | 依据 |
|------|-----|------|
| DROP_WINDOW | 20 | 月度级(≈一个月) |
| drop_pct | 30 | 回测最优(近20日跌>30%) |
| vol_ratio | 2.5 | 回测最优(T日放量2.5倍) |
| use_shrink | False | 回测显示缩量降收益 |
| 大盘开关 | 不加 | 回测证明无开关熊市全正 + 用户意愿 |
| 市值 | 不卡 | 全A扫,market_cap 仅展示 |

**复用** `chaodiefantan/backtest/band_signal.py` 的 `is_band_rebound`(阶段1已建成+测试)。

## 3. 文件结构

```
.claude/skills/boduan/
├── SKILL.md              # 触发文档(用户看的)
├── main.py               # 脚本(薄:复用 is_band_rebound + fetcher)
└── data/
    └── bd_YYYY-MM-DD.json  # 输出
```

**复用(不重写)**:
- `chaodiefantan/backtest/band_signal.py` → `is_band_rebound`(判定)
- `kangdie/screener/fetcher.py` → `get_all_stocks_today`/`get_stock_kline`/`get_market_cap_map`(数据,chaodiefantan 也用此)

main.py 通过 `sys.path.insert` import 上述模块(仿 chaodiefantan main.py 的 bridges 模式)。

## 4. main.py 流程(复用 chaodiefantan main.py 结构)

1. 🔴 CHECKPOINT:`bd_<今日>.json` 存在则 STOP 询问
2. `trading_day.latest_trading_day()` 定日期 + 收盘后跑(日K类)
3. 拉全A(`get_all_stocks_today`,过滤 ST/*ST/新股)+ 市值(`get_market_cap_map`,展示用)
4. 并发拉个股 21+ 日 OHLCV(`get_stock_kline`,本地 vipdoc 优先,fallback 新浪)
5. 判定 `is_band_rebound(window, cap, drop_pct=30, vol_ratio=2.5)`(不缩量、不加开关)
6. 保存 `data/bd_<日期>.json` + 终端展示 + 纪律提醒

## 5. 输出格式

```json
{
  "date": "2026-08-07",
  "trigger": {"signal": "band_oversold_rebound"},
  "count": 5,
  "stocks": [
    {"code":"...", "name":"...", "close":9.5, "drop20":-32.1,
     "stop_loss":8.3, "vol_ratio":2.8, "market_cap":80.0}
  ]
}
```

## 6. SKILL.md 大纲(核心文档)

- **标题 + 理念**:月度超跌后反弹启动信号(20日跌>30%+放量阳包阴),左侧短线严止损
- **使用方式**:`/boduan`,收盘后跑,约 2-8 分钟
- **执行步骤**:CHECKPOINT → main.py → 展示
- **筛选条件表**:近20日跌>30% / T日阳包阴 / 放量2.5倍(全满足;不卡市值;不加开关)
- **回测依据**(引用阶段1):最优 X=30 R=2.5 → 190信号/胜率59%/盈亏比2.98/+5.06%,2018/2022熊市全正;对比 chaodiefantan(30信号/+3.27%)信号6倍+收益高
- **纪律铁律**:止损破T-1最低不补仓 / 止盈纪律退出(跟踪+10日强平) / 仓位≤10% / 收盘后跑
- **反例黑名单**:抄底阴跌股(无阳包阴确认)/ 放宽阈值凑数 / 补仓摊平 / 当中线持有
- **边界条件**:无信号 count=0 诚实退出 / 大盘任何状态都扫(无开关) / 新浪失败重试
- **数据源**:复用 kangdie fetcher(money host),本地 vipdoc 优先

## 7. 纪律对齐(spec §8,对齐用户实盘教训)

用户实盘核心病灶:负期望+不止损+补仓摊平(15月亏18.4万)。boduan 纪律反向:
- 🛑 止损:破 T-1 最低硬止损,**禁止补仓摊平**
- 💰 止盈:纪律退出(收盘破前低跟踪 + 10日强平,复用回测 simulator 逻辑);不恋战
- 📊 仓位:单只 ≤10%
- ⚠️ 反弹是兑现窗口,不当中线持有

## 8. 非目标(YAGNI)

- ❌ 不修改 chaodiefantan(保持独立并行)
- ❌ 不接入 qsht-agent(波段左侧反弹 vs qsht 右侧趋势,逻辑不搭)
- ❌ 不加大盘开关(回测证明无开关正期望)
- ❌ 不做 fupan 引用(留作后续可选增强,阶段2不做)
- ❌ 不预测涨跌/不给买卖建议(信号参考,纪律由人执行)
