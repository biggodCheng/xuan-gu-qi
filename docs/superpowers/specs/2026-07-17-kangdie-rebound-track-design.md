# 抗跌反弹跟踪系统设计（kangdie track）

## 背景与目标

`kangdie` skill 在大盘（创业板指）暴跌日扫描"不破前低 + 跑赢大盘 + 缩量 + 市值50-500亿 + Q2偏正"的抗跌种子（只看不动）。本设计为其增加**反弹跟踪复盘**能力：长期累积跟踪每次暴跌入选的种子，在后续行情中回看它们的表现，验证"暴跌日抗跌的股，大盘反弹时是否第一时间领涨、反弹高度如何"。

对标 `qsht-agent/backtest_pullback.py`（回踩策略复盘）——那个验证"缩量回踩策略"，本系统验证"抗跌→反弹"假设，结构同构。

## 验证假设

- **H1（第一时间反弹）**：暴跌日抗跌的种子，在创业板企稳反弹的头几天（D+1~D+3），是否跑赢大盘。
- **H2（反弹高度）**：这些种子在反弹中的最大涨幅（MFE）与各窗口累计涨幅，是否显著为正且跑赢创业板。

累积多批样本后，用平均 MFE / 末值胜率 / 第一时间反弹占比等统计量回答上述假设。结论为**小样本探索性**，非统计显著。

## 架构

**独立脚本 `kangdie/track.py`**，import 复用 kangdie 现有模块：

- `screener.fetcher`：`get_stock_kline(code, days)` 拉个股 OHLCV、`get_index_kline(sym, days)` 拉创业板指
- `screener.storage`：`load_results(date, dir)` 读 `kd_<date>.json`
- `screener.analyzer` 的纯函数风格（`compute_ret20` 可借鉴）

新增纯函数模块 `screener/track_analyzer.py`（无网络、可单测）：窗口涨幅、MFE/MAE、第一时间反弹判定。

**职责分离**：`main.py` = 暴跌日找种子；`track.py` = 后续看反弹。两者通过 `kd_*.json` 解耦。

## 数据流

```
track.py 运行:
  1. 扫描 kangdie/data/kd_*.json → 每个文件 = 一次暴跌批次(date=D, stocks=种子)
  2. 对每个种子:
     a. D 收盘价 = kd 文件里该股的 close
     b. 拉 D→今 个股日K (get_stock_kline, days=D至今交易日数+缓冲)
     c. 拉创业板指 D→今 (get_index_kline)
     d. 调 track_analyzer 算各窗口指标
  3. 汇总 → 写 track_history.json + track_review_<date>.md
```

## 衡量指标

以**暴跌日 D 的收盘价**为基准（D 当天种子已定格在 kd 文件）。D+N = D 之后第 N 个交易日。

| 维度 | 指标 | 计算 |
|------|------|------|
| 第一时间反弹 | `d1`/`d2`/`d3` 累计涨幅 | `(close[D+N] - close[D]) / close[D] × 100` |
| 反弹高度 | `d5`/`d10`/`d20` 累计涨幅 | 同上 |
| 区间极值 | `mfe`（最大涨幅）/ `mae`（最大跌幅） | 基于 `high[D+1..今]` / `low[D+1..今]` 相对 close[D] |
| 末值 | `end_ret` | `(close[今] - close[D]) / close[D] × 100` |
| 对照 | event 级存 `idx_end`（创业板末值）+ `first_rebound`（D+1~3 跑赢创业板的布尔）；创业板各窗口均值进汇总 `stats.by_window` | 判定相对强度 |

**第一时间反弹判定**（布尔）：D+1~D+3 区间，个股累计涨幅 > 0 **且** > 创业板同期累计涨幅 → True。

**成熟度**：`mature` = 已过 D+20 个交易日（数据成熟，不再更新）；未到 D+20 的窗口值可能为 None（数据不足）。

## 汇总面板（track_review_<date>.md）

```
## 抗跌反弹跟踪（截至 as_of · 样本 span · N 事件/M 股）
- 平均末值收益: x% ｜ 平均 MFE y% / MAE z%
- 末值正收益(胜率): w/N
- 第一时间反弹(D+1~3 跑赢创业板): k/N
- 各窗口平均涨幅序列: D+1 / D+3 / D+5 / D+10 / D+20  ← 看反弹节奏
- 同窗口创业板平均涨幅: ...  ← 标注大盘反弹了没
```

附：每只种子的明细表（代码/名称/D收盘/各窗口/MFE/末值/是否第一时间反弹/成熟度）。

## 存储格式

- **累积数据** `kangdie/data/track_history.json`：所有种子的跟踪记录 + 汇总 stats，每次跑覆盖更新。
  ```json
  {
    "as_of": "2026-07-17",
    "span": "2026-07-16–2026-07-17",
    "events": [
      {"drop_date":"2026-07-17","code":"920438","name":"戈碧迦","d_close":99.0,
       "d1":null,"d3":null,"d5":null,"d10":null,"d20":null,
       "mfe":null,"mae":null,"end_ret":null,
       "idx_end":null,"first_rebound":null,"mature":false}
    ],
    "stats": {"n":0,"stocks_total":0,"avg_end_ret":0,"avg_mfe":0,"avg_mae":0,
              "win":0,"first_rebound_cnt":0,"by_window":{}}
  }
  ```
  （暴跌当天 D+1 尚未发生，各窗口为 null，属正常。）
- **人读报告** `kangdie/output/track_review_<date>.md`（新建 output 目录，与 qsht 对齐）。

## 运行方式

```bash
python .claude/skills/kangdie/track.py            # 扫所有历史 kd_*.json
python .claude/skills/kangdie/track.py --date 2026-07-17  # 只跟踪指定批次
```

独立于"今天是否暴跌"——任何一天都能跑，更新所有未成熟种子的最新数据。

`kangdie/SKILL.md` 新增"## 反弹跟踪（反弹复盘）"章节，说明 `track.py` 用法与"暴跌日存种子、反弹后跑 track 复盘"的工作流。

## 生命周期

- 种子从其 D 起跟踪，到 **D+20 个交易日**后 `mature=true`，停止更新。
- D+20 内的种子每次跑都刷新（拉最新K线重算各窗口）。
- 同一只股票若在多个暴跌日都被选为种子，按 (drop_date, code) 作为独立事件分别跟踪。

## 边界条件

| 场景 | 处理 |
|------|------|
| 无历史 kd_*.json | 提示"尚无暴跌批次可跟踪"，写空 stats 退出 |
| 种子退市/长期停牌 | D 后 K 线不足，各窗口标 null，event 保留但 mature=false |
| D+20 未到 | 能算的窗口算（d1/d3...），算不出的 null |
| 创业板指拉取失败 | 跳过对照字段（idx_*/first_rebound 标 null），不阻断个股指标 |
| 个股 K 线拉取失败 | 该 event 指标全 null，继续其他 |

## 测试策略

`track_analyzer.py` 的核心计算为纯函数（无网络），单测覆盖（对标 `tests/test_analyzer.py` 风格）：

- 窗口涨幅：构造 D+N 收盘序列，验证 d1/d3/d5/d10/d20 计算
- MFE/MAE：构造含区间最高/最低的序列，验证极值
- 第一时间反弹：构造"涨且跑赢创业板" / "跌" / "涨但跑输" 三例，验证布尔判定
- 成熟度：K 线长度 ≥21 → mature=true

IO 层（拉 K 线、读写文件）不做单测，靠端到端跑 `track.py` + 人读报告验证。

## 非目标（YAGNI）

- **不**做精确"反弹段识别"（找低点→高点段）——固定窗口已能回答两个核心问题，低点判定主观且复杂。
- **不**自动判定大盘企稳信号触发（不依赖 qsht 的 `_is_stabilized`）——用创业板同期涨幅客观标注，由人判断。
- **不**做买卖建议——纯跟踪复盘，验证假设。
- **不**接入 qsht-agent 主漏斗——独立脚本，按需手动跑。
