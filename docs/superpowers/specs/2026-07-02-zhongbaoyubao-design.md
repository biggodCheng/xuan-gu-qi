# 中报预报跟踪器（zhongbaoyubao）设计文档

- **日期**：2026-07-02
- **状态**：待实现
- **作者**：brainstorming 产出
- **skill name**：`zhongbaoyubao`

## 1. 背景与目标

A 股中报预告季（7 月）会密集披露"业绩预告"。其中"大幅预增"是典型的业绩事件。本 skill 要回答一个问题：

> **那些中报预告大幅预增的公司，预告披露后股价到底是涨是跌？**

这是一个**事件跟踪器**（event study 视角）：每次执行扫描最新大幅预增的预告纳入跟踪池，每天增量更新池内股票"自披露后"的累计涨跌，持续到跟踪窗口结束。

### 它不是什么
- **不是选股器**：不做"该不该买"的判断，只跟踪已发生事件的股价反应。
- **不是精确预测**：只产出涨跌幅读数与分布，不给目标价。
- **不是一次性筛选**：和现有 chuangxingao/zhangting 等"一次性筛选"skill 不同，它有**跨天持久化状态**。

## 2. 范围

### 本期做
- 扫描全 A 股 2026 中报业绩预告，筛"预增且同比下限 ≥ 50%"入跟踪池。
- 每只入池股以"公告次日开盘价"为基准，跟踪 30 个交易日的累计涨跌。
- 每次执行：增量发现新股入池 + 刷新池内活跃股当前价 + 追加每日系列 + 淘汰到期股 + 生成每日 markdown 报告。
- 持久化跟踪池 `data/watchlist.json`（active + expired 分区，含每日系列）。

### 本期不做（YAGNI / 未来扩展）
- 接入 qsht-agent 流水线、在报告里交叉标注"是否在创新高/涨停池"。
- 用每日系列画涨跌曲线（数据已存，画图留给未来）。
- 沪深 300 超额收益口径（本期只算绝对累计涨跌）。
- 扣非净利润口径（业绩预告接口以归母预测为主）。
- 三季报/年报预告（本期仅中报，报告期锁定 2026-06-30）。

## 3. 核心参数（已与用户确认）

| 决策项 | 取值 |
|---|---|
| 筛选标准 | 预告类型=预增，且净利润同比变动幅度**下限 ≥ 50%** |
| 跟踪周期 | **30 个交易日**（从基准日起算） |
| 涨跌基准 | **公告次日开盘价** |
| 涨跌口径 | **累计涨跌** = (今日收盘 − 基准价) / 基准价；另算当日涨跌 |
| 扫描范围 | 全 A 扫描东方财富业绩预告（独立于其他 skill） |
| 每日系列 | 记录（watchlist 中每只股存每日 {close, 累计涨跌, 当日涨跌}） |

## 4. 架构：持久化跟踪池（方案 A）

跨天状态由 `data/watchlist.json` 承载。每次执行是一个**幂等的增量更新**：

```
扫描全A预告 → 新达标股去重入池(取基准价)
                ↓
        刷新池内 active 股行情(前复权日K段)
                ↓
        算累计/当日涨跌 + 追加每日系列
                ↓
        淘汰 held_days≥30 → expired
                ↓
        生成 output/<date>.md + 写回 watchlist.json
```

### 为什么用前复权日K段统一口径（重要）
涨跌计算的基准价（次日开盘）与当前价（今日收盘）必须**同一复权口径**，否则中间发生分红除权会让涨跌读数失真。因此：

- 对每只 active 股，统一用**腾讯前复权日K**拉取"从公告日到今天"的完整序列。
- 一次请求同时得到：基准日开盘价、每日收盘价、今日收盘价、交易日序列。
- **不使用新浪全A批量刷新当前价**（那是为全市场新高筛选设计的，且不复权，口径会与基准价冲突）。跟踪池规模远小于全市场（几十~上百只），逐只拉前复权日K + 并发控制，性能完全可接受。

## 5. 目录结构（沿用项目惯例）

```
.claude/skills/zhongbaoyubao/
├── SKILL.md
├── main.py                 # 编排：扫描→入池→刷新→涨跌→淘汰→报告
├── requirements.txt        # requests, pandas（无新依赖）
├── screener/
│   ├── __init__.py
│   ├── fetcher.py          # 业绩预告接口 + 前复权日K段 + 名称解析
│   ├── analyzer.py         # 筛选/涨跌计算/到期判定/基准日推算
│   └── storage.py          # watchlist.json 读写(去重/覆盖每日系列/迁移)
├── data/
│   ├── watchlist.json      # 持久化跟踪池(active + expired)
│   └── .gitkeep
├── output/
│   └── <date>.md           # 每日报告
└── tests/
    ├── test_analyzer.py
    └── test_storage.py
```

**入库策略**：`data/watchlist.json` 与 `output/*.md` 为运行时产物，沿用各 skill 运行时数据不强制入库的惯例（`.gitignore` 忽略 `data/*.json`、`output/*.md`，保留 `.gitkeep` 占位）。

## 6. 数据源与接口

### 6.1 中报业绩预告（核心新增接口）
- **来源**：东方财富 datacenter-web，`https://datacenter-web.eastmoney.com/api/data/v1/get`
- **reportName**：`RPT_LICO_FN_CPD_GD`（个股业绩预告；实现首步必须实测确认，候选备选 `RPT_PUBLIC_OP_PREDICT`）
- **请求模式**：与 q2zhanwang 的 `get_financial` 完全一致（同 session、同 headers、`columns=ALL`、分页）。
- **筛选过滤**：
  - 报告期 `REPORTDATE = '2026-06-30'`（中报预告对应的报告期）
  - 预告类型字段 = "预增"（候选字段名 `PREDICTTYPE` / `NOTICE_TYPE`，实测确认）
- **取用字段**（字段名以实测为准，下列为东方财富常见命名候选）：
  - 代码 `SECURITY_CODE`、名称 `SECURITY_NAME_ABBR`、行业 `PUBLISHNAME`
  - 公告日 `NOTICE_DATE`（预告发布日，作事件日）
  - 净利润同比变动幅度下限 `YYSJLL` / 上限 `YYSJHL`（候选；下限 ≥ 50 入池）

> 🔴 **实现 CHECKPOINT（接口字段核对）**：东方财富业绩预告接口的字段命名与 reportName 在不同专题页略有差异。实现第一步必须先抓一条样本（如已知某只已披露中报预增的股票），打印全部字段，确认 reportName、类型字段、上下限字段、公告日字段的准确命名后，再写筛选逻辑。SKILL.md 须记录实测后的字段名。

### 6.2 前复权日K（跟踪涨跌，复用并扩展 chuangxingao）
- **来源**：腾讯财经 fqkline，`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get`，`param=<symbol>,day,<start>,,<len>,qfq`
- chuangxingao 现有 `_fetch_tencent_closes` 只取 `item[2]`(close)。本 skill 新增 `get_kline_since(code, since_date)`，返回 `[{date, open, close}, ...]`（取 `item[0]` 日期、`item[1]` 开盘、`item[2]` 收盘），前复权，按日期正序，自动跳过非交易日与停牌日。
- **回退**：腾讯失败/残缺时回退新浪 K 线（新浪只有 close 无 open）；回退时基准价缺失则该股标注 `base_note="基准价缺失(数据源回退)"` 并暂不入 active（留 skipped 待次日重试）。

### 6.3 股票名称解析
- 复用 q2zhanwang/chuangxingao 的 `resolve_stock_code`（东方财富 searchapi + 新浪行情）。本 skill 主要按 code 操作，名称来自预告接口返回。

## 7. 核心流程（main.py 编排）

```
1. 🔴 CHECKPOINT：output/<today>.md 已存在
   → 提示"今日报告已生成，重跑会重新刷新行情并覆盖"，询问确认后才继续
   （沿用 chuangxingao 的防覆盖惯例）

2. 加载 data/watchlist.json（不存在则初始化空池）

3. 扫描发现新股：
   a. 拉全A 2026中报业绩预告(预增)，筛 yoy_lower ≥ 50
   b. 去重：排除已在 active/expired/skipped 的 code
   c. 新股入 active 占位（base_price/daily 待第 4 步填）；skipped 中的旧股一并重新尝试

4. 刷新前复权日K + 算涨跌（对 active 全部，含新股；线程池并发）：
   每只拉 get_kline_since(code, notice_date)：
   - 失败/无数据 → 新股转 skipped(reason="K线拉取失败")；存量股保留旧 daily、标 last_note
   - 成功得前复权序列 [{date,open,close},...]：
     * 基准价 base_price = 序列[0].open（公告后首个交易日开盘）
     * 覆盖式重算 daily = 每条 {date, close, chg_total, chg_today}（算法见 10.2）
     * held_days = len(daily) − 1；remain_days = 30 − held_days

5. 到期处理：held_days ≥ 30 → 从 active 移入 expired（保留最终 daily，停止每日刷新）

6. 生成 output/<today>.md（见第 9 节）

7. 写回 data/watchlist.json（updated_at = today）

并发：第 3、4 步网络请求用线程池（参考 qibao/main.py），单请求超时 15s、重试 3 次。
```

并发：第 3、4 步对多只股票的网络请求用线程池并发（参考 qibao/main.py 的并发编排），单次请求超时 15s、重试 3 次。

## 8. 数据结构：watchlist.json

```json
{
  "report_period": "2026H1",
  "report_date": "2026-06-30",
  "updated_at": "2026-07-02",
  "threshold": {"predict_type": "预增", "yoy_lower_min": 50, "hold_days": 30, "base": "次日开盘"},
  "active": [
    {
      "code": "600160", "name": "巨化股份", "industry": "化学制品",
      "predict_type": "预增", "yoy_lower": 80.0, "yoy_upper": 120.0,
      "notice_date": "2026-07-10",
      "base_date": "2026-07-11", "base_price": 12.34,
      "held_days": 15, "remain_days": 15,
      "last_close": 13.10, "chg_total": 6.16, "chg_today": 1.2,
      "base_note": "",
      "daily": [
        {"date": "2026-07-11", "close": 12.40, "chg_total": 0.49, "chg_today": 0.49},
        {"date": "2026-07-14", "close": 12.55, "chg_total": 1.70, "chg_today": 1.21}
      ]
    }
  ],
  "expired": [
    { "同 active 结构，不再每日刷新，daily 为完整 30 日序列" }
  ],
  "skipped": [
    { "code": "xxx", "name": "...", "notice_date": "...", "reason": "基准价缺失(数据源回退)" }
  ]
}
```

说明：
- `active`/`expired`/`skipped` 三区。`skipped` 是入池失败待重试的，下次执行会重新尝试拉基准价，成功则转 active。
- `daily` 为**覆盖式刷新**：每次执行用最新拉取的完整前复权序列覆盖（因前复权基准随时间微调，覆盖比追加更自洽）。末条即今日。
- `remain_days = 30 − held_days`。

## 9. 输出报告：output/<date>.md

```markdown
# 中报预报跟踪 · 2026-07-02

## 概览
- 报告期：2026中报（预告对应 2026-06-30）
- 阈值：预增 且同比下限≥50%｜跟踪30交易日｜基准=次日开盘｜口径=前复权累计涨跌
- 跟踪池：活跃 N 只 / 已到期 M 只 / 待重试 K 只
- 今日新增：X 只

## 今日新增（X 只）
| 代码 | 名称 | 预增下限 | 预增上限 | 公告日 | 基准日 | 基准价 |

## 活跃跟踪（按累计涨跌降序）
| 代码 | 名称 | 预增下限 | 公告日 | 基准价 | 今收 | 累计涨跌% | 当日涨跌% | 持有天数 | 剩余天数 |

## 今日到期（移出活跃）
| 代码 | 名称 | 基准价 | 期末收 | 累计涨跌% | 持有天数 |

## 涨跌分布（活跃股）
- 累计为正 X 只 / 为负 Y 只 / 平均累计涨跌 Z%
- Top3 涨幅 / Top3 跌幅
```

## 10. 关键算法

### 10.1 基准日与基准价
`get_kline_since(code, notice_date)` 返回 notice_date 之后的首个交易日序列。首条即基准日，其 `open` 即基准价。无需独立交易日历——该股自身的有行情日序列即为其有效交易日序列，天然处理周末/节假日/停牌。

### 10.2 涨跌计算
- 累计涨跌% = (daily[-1].close − daily[0].open) / daily[0].open × 100
- 当日涨跌% = (daily[-1].close − daily[-2].close) / daily[-2].close × 100（仅 1 条时 = 累计涨跌）
- held_days = len(daily) − 1

### 10.3 到期判定
held_days ≥ 30 → 移入 expired。到期股保留完整 daily 与最终累计涨跌，不再刷新。

### 10.4 去重
按 `code` 去重：已在 active/expired/skipped 的不再重复入池。skipped 的下次执行重新尝试拉基准价。

## 11. 边界条件与失败处理

| 触发条件 | 一线处理 | 仍失败兜底 |
|---|---|---|
| 非交易日（周末/节假日）执行 | 仍扫描预告(公告非行情)；get_kline_since 末条为最近交易日，当前价=最近收盘，报告标注"非交易日，价格为最近收盘" | — |
| 公告次日停牌 | 序列首条自动顺延到复牌后首个交易日，基准价=该日 open，base_note 标注"顺延至复牌首日" | — |
| 新股/次新股 K 线不足（公告日后无足够交易日） | 入 skipped，reason="K线不足"，下次重试 | 连续 3 次失败移出 skipped 并记入 failed |
| 腾讯日K失败/残缺 | 回退新浪(仅 close) | 新浪也失败→入 skipped，基准价缺失 |
| 业绩预告接口字段变动/为空 | 打印原始返回，降级提示"预告接口异常"，本次不新增 | 提示稍后重试 |
| 预告类型非"预增"（扭亏/续盈/略增） | 本期一律不纳入（仅预增+下限≥50%） | — |
| 预告同比下限为空（仅给区间或文字描述） | 跳过该条，不纳入 | — |
| 跨报告期 | report_date 写死 2026-06-30，天然只扫中报预告、不会混入三季报；中报预告披露季（约至 8 月中）结束后新池自然停止增长，存量继续跟踪到期 | — |
| watchlist.json 损坏/不可解析 | 备份为 watchlist.json.bad.<date>，重建空池并提示 | — |
| output/<today>.md 已存在 | CHECKPOINT 询问是否覆盖（防重跑） | — |

## 12. 反例黑名单（❌ 不要做）

| 不要 | 原因 | 正确做法 |
|---|---|---|
| 把"大幅预增"当买卖建议 | 预告≠兑现，且利好出尽可能下跌 | 只跟踪涨跌读数，不下买卖结论 |
| 用入池 1 天的单点涨跌下结论 | 样本太短，噪声大 | 至少看 held_days≥5 的读数 |
| 用新浪不复权价做当前价、腾讯前复权做基准价 | 除权会让涨跌失真 | 基准与当前同取自一条前复权日K序列 |
| 逐个请求且不并发刷新全池 | 池大时慢 | 线程池并发拉日K |
| 忽略 CHECKPOINT 直接覆盖今日报告 | 重跑浪费时间且可能混淆 | 先询问 |
| 把扭亏/续盈当预增纳入 | 本期口径仅预增 | 严格按类型过滤 |
| 跨报告期继续入新池 | 中报逻辑结束 | report_date 校验后停止入新 |

## 13. CHECKPOINT 规范

1. **运行前**：`output/<today>.md` 是否存在 → 存在则提示"今日报告已生成，重跑会重新刷新行情并覆盖"，询问确认。
2. **接口字段核对（实现期）**：首次对接业绩预告接口时，先抓样本打印全部字段，确认 reportName/类型/上下限/公告日字段名后再写筛选逻辑，并把实测字段名写进 SKILL.md。

## 14. 测试计划（pytest，沿用 TDD 惯例）

### test_analyzer.py（纯函数，不触网）
- 筛选边界：yoy_lower = 49.9 → 不入池；50.0 → 入池；类型≠预增 → 不入池。
- 累计涨跌：(close 11, open 10) → +10.0%；跨 0 基准价保护。
- 当日涨跌：首条=累计；两条时正确算环比。
- held_days：daily 长度 N → held_days = N−1。
- 到期判定：held_days=29 留 active；=30 移 expired。
- 基准日推算：给定 notice_date 与日K序列，基准日=序列首条 date。

### test_storage.py（临时 watchlist）
- 去重：已存在 code 不重复入池。
- 覆盖式刷新 daily：新序列覆盖旧序列，末条为今日。
- active→expired 迁移：到期股移区，daily 保留。
- skipped 重试：下次执行重新尝试，成功转 active。
- 读写一致性：写后读回字段完整。
- 损坏兜底：传入非法 JSON → 备份 + 重建空池。

网络层（fetcher）用 mock/录制的接口返回测试，不在单测里真实联网。

## 15. 依赖

`requirements.txt`：`requests`、`pandas`（与现有 skill 一致，无新依赖）。并发用标准库 `concurrent.futures`。

## 16. 局限（写进 SKILL.md）

- 业绩预告是公司**指引**，非实际数；正式中报（8 月底前）可能修订。
- 涨跌为绝对收益，未剔除大盘/行业 beta（同期普涨/普跌会失真）。
- 仅归母口径，预增可能含一次性损益。
- 跟踪窗口 30 交易日是经验值，不保证覆盖完整"利好兑现/出尽"周期。

## 17. SKILL.md 触发词

`中报预报` / `中报预增` / `业绩预告大增` / `预报跟踪` / `预告大涨跟踪` / `zhongbaoyubao`。
