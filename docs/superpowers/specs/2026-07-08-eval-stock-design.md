# eval-stock 个股评估器 设计文档

- 日期：2026-07-08
- 状态：已设计，待实现

## 背景与动机

`qsht-agent` 是**全市场扫描**流水线（创新高 → 涨停 → 缩量回踩 → 市值 → Q2 展望），每日产出选股报告，单次运行 10–25 分钟。但用户经常需要对**指定的一两只股票**做定点体检——例如人气榜上的票、他人推荐的票——看它在 qsht 各维度的成色。为此跑全市场 qsht 既慢又产出冗长大报告，不合适。

需要一个轻量、快速、针对个股的评估工具：输入一只股票，跑 qsht 的 6 个维度，终端打印汇总与达标判定。

## 定位

独立 skill `.claude/skills/eval-stock/`，与 qsht-agent 互补：

- **qsht-agent**：广撒网，全市场筛选今日标的，落盘报告。
- **eval-stock**：定点体检，给定个股看各维度成色，终端输出。

## 非目标（YAGNI）

- 不做全市场筛选（qsht-agent 的职责）。
- 不落盘报告（纯终端输出，无文件副作用）。
- 不扩展到技术面（均线/量能）、资金面（主力净流入）等——聚焦 qsht 体系；通用体检是另一个工具的事。
- 不做策略回测（qsht-agent 第 6 步的职责）。

## 文件结构（遵循现有 skill 模式）

```
.claude/skills/eval-stock/
├── SKILL.md              # 触发说明
├── main.py               # CLI 入口：解析参数 → 编排各维度 → 打印报告
└── screener/
    ├── __init__.py
    ├── fetcher.py        # 日K(腾讯前复权,含量价) + 市值(腾讯qt) + 代码名称互查
    ├── analyzer.py       # 趋势新高 / 涨停 / 缩量回踩 / 市值门槛 判断（纯函数）
    ├── bridges.py        # importlib 按路径加载 q2zhanwang / sidasaidao 核心函数
    └── reporter.py       # 终端 markdown 格式化
```

## 数据流

```
输入(代码或名称, 可多只)
   │
   ├── bridges.resolve_stock_code()  →  统一解析成 code+name
   │
   ├── fetcher.fetch_kline(code)     →  日K(含量价)
   ├── fetcher.fetch_marketcap(code) →  总市值/流通市值
   │
   ├── analyzer: 趋势新高 / 涨停 / 缩量回踩 / 市值门槛   （自写, 用上面的K线/市值）
   ├── bridges: Q2 展望   （复用 q2zhanwang.get_financial + analyze）
   ├── bridges: 赛道      （复用 sidasaidao.get_stock_detail + match_tracks）
   │
   └── reporter.format()  →  终端打印 markdown
```

## 维度与阈值

> 涨停 / 缩量回踩 / 市值 / Q2 / 赛道 的阈值与 qsht 各子 skill 默认**完全一致**，保证两工具判定标准统一。**仅第①步趋势新高规则不同**（见下）。

### ① 趋势新高（eval-stock 专属放宽规则）

**判定**：最近 **20 个交易日**（约一个自然月）内，任一天的收盘价创过"该日前 100 个交易日新高"，即视为通过。

实现：对 `kline[-20:]` 的每一根 `i`，判断 `kline[i].close >= max(kline[i-100:i] 的 close)`；任一满足即通过。需 K 线长度 ≥ 120；不足则降级标注。

输出标注三种情况：
- 今日就创新高 → `✅ 今日新高`
- 今日没新高、近 20 日内某天创过 → `✅ 近一月新高（N 日前, MM/DD 创 100 日新高）`
- 近 20 日都没创过 → `❌ 距高点 −X%`

**与 qsht-agent 的有意差异**：qsht-agent 第①步是严格的"今日收盘创 100 日新高"（全市场选股语义）；eval-stock 用宽松的"近一月曾新高"（体检语义，看趋势是否还在）。同一只票可能 eval-stock"①通过"而 qsht 当日筛不中——这是设计意图，非 bug。

### ② 近 15 天涨停

单日涨幅（close vs prev_close）达到板块阈值：

| 板块 | 代码前缀 | 涨停阈值 |
|------|---------|---------|
| 主板 | 60 / 00 | ≥ 9.5% |
| 科创板 / 创业板 | 68 / 30 | ≥ 19.5% |
| 北交所 | 8 / 4 / 9 | ≥ 29.5% |

窗口：最近 15 个交易日内。输出命中次数与日期。

### ③ 缩量回踩（策略 1）

与 `suolianghuicai` 默认一致：最后一次涨停后，连续 `close < zt_close` 且 `volume < prev_volume × 0.8`，`min_days = 2`。命中输出回踩起始日、天数、量比。

### ④ 市值门槛

总市值 `< 200 亿`（腾讯 qt `parts[44]`）。输出总市值/流通市值。

### ⑤ Q2 业绩展望（复用 q2zhanwang）

调用 `q2zhanwang.screener.fetcher.get_financial(code)` + `q2zhanwang.screener.analyzer.analyze(fin)`，取 `q2_outlook.verdict`（偏正/中性/偏负）、`confidence`、`q1.netprofit_yoy`、`q1.revenue_yoy`、`summary`。

### ⑥ 赛道（复用 sidasaidao）

调用 `sidasaidao.screener.fetcher.resolve_stock_code / get_stock_detail` + `sidasaidao.screener.analyzer.match_tracks`，取四大赛道归属与主赛道（含 confidence）。

## 输入

CLI：

```
python .claude/skills/eval-stock/main.py <代码或名称>[,代码或名称,...]
```

示例：`python main.py 深科技,有研新材`、`python main.py 000021`、`python main.py 600206`。

代码与名称都能传；名称经 `resolve_stock_code` 解析为代码。

SKILL.md 触发词：用户给一只（或几只）股票，并说"评估 / 体检 / 看成色 / 过一遍流水线 / 能不能买 / 帮我分析一下"等时触发。

## 输出（终端 markdown，不落盘）

```
深科技(000021) · 消费电子 · 数据截至 2026-07-07 · 最新 54.07
─────────────────────────────────────────────
① 趋势新高    ✅  近一月新高（7 日前 6/30 创 100 日新高）
② 近15天涨停   ✅  2 次（6/24, 6/29）
③ 缩量回踩S1   ✅  7/3 起 2 天，量比 0.70
④ 市值<200亿   ❌  851 亿
⑤ Q2展望      ➖  中性（净利 +35% / 营收 +11%）
⑥ 赛道        ✅  四大赛道全覆盖，主 AI硬件(中)
─────────────────────────────────────────────
qsht 漏斗判定：①②③通过，④市值淘汰 → 不达标
一句话：高位回落的反弹型大票，非体系标的，不建议追。
```

- 灯标：`✅` 通过 / `❌` 不通过 / `➖` 中性（仅 Q2 用）。
- 末尾给**qsht 漏斗达标判定**：按 ①→②→③→④ 串联，任一步淘汰即整体"不达标"，并指出在哪步淘汰。⑤⑥ 为参考维度不参与漏斗淘汰。
- 末尾**一句话总评**：基于各维度综合给一句克制结论（对齐用户"少交易+严纪律"，不诱导追高）。

## 实现方式：importlib 复用

`bridges.py` 用 `importlib.util.spec_from_file_location` 按绝对路径加载其他 skill 的核心函数，绕开多个 `screener` 包名冲突：

```python
import importlib.util

def _load(module_path, name):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

加载：

| 来源 skill | 加载函数 | 用途 |
|-----------|---------|------|
| q2zhanwang/screener/fetcher.py | `get_financial(code)` | 拉财报 |
| q2zhanwang/screener/analyzer.py | `analyze(fin)` | Q2 展望推断 |
| sidasaidao/screener/fetcher.py | `resolve_stock_code(name)`, `get_stock_detail(code)` | 代码名称互查 / 行业概念 |
| sidasaidao/screener/analyzer.py | `match_tracks(industry, concepts)` | 赛道匹配 |

好处：复用复杂逻辑不重写、不写文件（无副作用，不污染其他 skill 的 data 目录）、无 subprocess 开销。

`fetcher.py` 自写新高/涨停/回踩/市值所需的数据获取（腾讯日K `web.ifzq.gtimg.cn` + 腾讯市值 `qt.gtimg.cn`），逻辑简单、内聚。

## 数据源

- 日K（前复权，含量价）：腾讯 `web.ifzq.gtimg.cn/appstock/app/fqkline/get`，格式 `[日期,开,收,高,低,量]`。
- 市值：腾讯 `qt.gtimg.cn/q=<symbol>`，`parts[44]`=总市值(亿)、`parts[45]`=流通市值(亿)。
- 财报、行业、概念：经 bridges 调 q2zhanwang / sidasaidao（其内部走东方财富/腾讯）。

## 错误处理

- **单股失败不阻断**：多只股票时，某只取数失败则该股标注错误原因，继续评估其他。
- **K 线不足**（新股、退市）：第①②③步降级标注"数据不足"，不参与判定。
- **盘中提示**：若最新 K 线为当日且当前处于交易时段（9:30–15:00），报告头标注"盘中未收盘"。
- **bridges 加载失败 / 被调 skill 接口异常**：对应维度标"数据不可用"，不崩溃，其余维度照常。

## 测试

- `analyzer.py` 的纯函数（趋势新高 / 涨停 / 缩量回踩判定）写单元测试：喂构造的 K 线序列，覆盖命中、不命中、边界（数据不足、今日新高 vs 近一月新高）。
- `bridges.py` 集成测试：用真实代码（如 000021）跑通 Q2 与赛道加载。
- `reporter.py` 格式快照测试：固定输入 → 固定 markdown。

## 验收标准

1. `python main.py 深科技,有研新材` 能在 < 30 秒内输出两只股票的完整 6 维度报告。
2. 第①步采用"近一月新高"规则，深科技（高点在近一月内）应判①通过。
3. 输出含 qsht 漏斗达标判定与一句话总评。
4. 单只取数失败不影响其他股票输出。
5. 不向任何 skill 的 data/ 目录写文件。
6. 涨停 / 缩量回踩 / 市值 / Q2 / 赛道 阈值与 qsht 各子 skill 一致。
