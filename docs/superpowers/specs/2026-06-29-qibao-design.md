# qibao (起爆点筛选器) 设计文档

## Context

项目已有 "创新高 → 涨停 → 缩量回踩/市值 → Q2展望" 的选股流水线（qsht-agent 编排）。本 skill 基于用户提供的通达信"主力监测系统"公式，新增一个**起爆点信号筛选器**：从创新高股中筛出"放量起爆"的标的，作为创新高之后的派生信号步骤。

原公式包含两个信号：主力吸筹（绿色 K 线）和起爆点（黄色 K 线/买点）。其中"主力吸筹"核心依赖 `L2_AMOUNT`（L2 大单资金流），而项目数据源（腾讯/新浪日线）**只有日 OHLCV，拿不到 L2 数据**。因此本设计**忠实翻译原公式，仅删除 L2 资金流条件**：蓄势信号改为"横盘 + 放量阳线"判定（量价近似），起爆信号三条件完整保留。

设计取向（已与用户确认）：
- **方案 A — 忠实翻译**：布尔信号判定，不做置信度评分。
- **股票池**：创新高股（chuangxingao 输出）。
- **接入流水线**：作为 qsht-agent 新步骤。
- **输出范围**：只输出"起爆"股，兼具蓄势的标注出来（信号更强）；仅蓄势未起爆的不输出。

## 数据流

```
chuangxingao/data/{date}.json  (输入：创新高股列表)
  → 提取股票列表
  → 逐只获取日K线（含 open/high/low/close/volume）
  → 计算技术指标（MA / 布林 / MACD / HHV / LLV / CROSS）
  → 判定 蓄势 / 起爆（只看每只股票的最近一个交易日）
  → 筛出 起爆=True 的股票，标注是否兼蓄势
  → qb_{date}.json (输出，保存在 qibao/data/)
```

## 文件结构

```
.claude/skills/qibao/
├── SKILL.md              # 技能描述、使用方式、执行步骤、边界条件、反例
├── main.py               # 入口：参数解析、编排流程
├── screener/
│   ├── __init__.py
│   ├── fetcher.py        # 复用腾讯/新浪日K，返回 {date,open,high,low,close,volume}
│   ├── indicators.py     # MA / 布林 / MACD / HHV / LLV / CROSS（项目无统一指标库，自实现）
│   ├── analyzer.py       # 蓄势/起爆判定 + 筛选入口
│   └── storage.py        # 读取上游JSON + 保存结果JSON
├── tests/
│   ├── __init__.py
│   ├── test_indicators.py
│   └── test_analyzer.py
└── requirements.txt      # requests
```

> 与其他筛选器相比多一个 `indicators.py`：方案 A 需要多个技术指标，单列文件更清晰、便于独立单测。

## K线数据获取 (fetcher.py)

- 复用现有腾讯/新浪主从数据源（腾讯优先，腾讯条数过少或失败时回退新浪）。
- 现有 fetcher 只解析了 `close`/`volume`，本 skill 需**增强解析为完整 OHLCV**：`{date: str, open: float, high: float, low: float, close: float, volume: float}`，按日期正序。
- 获取天数：默认 100–120 个交易日（与 chuangxingao 一致），足以覆盖指标 warmup。
- `min_history`：历史不足 **40 日**的股票跳过并记日志（MACD 需 26+9≈35 日 warmup，留余量）。

## 技术指标 (indicators.py)

项目无统一指标库，本文件自实现以下函数（纯函数、可单测）：

- `ma(values, n)` — 简单移动平均
- `ema(values, n)` — 指数移动平均
- `boll_upper(closes, n=20, w=2)` — 布林上轨 = `MA(closes,n) + w * STD(closes,n)`
- `macd(closes, fast=12, slow=26, signal=9)` — 返回 `(dif, dea)` 序列
- `hhv(values, n)` / `llv(values, n)` — N 日最高/最低
- `cross(a, b)` — 上穿：昨日 `a<b` 且今日 `a>b`

## 信号判定 (analyzer.py)

对每只股票，**只检查其 K 线序列的最后一个交易日（最近一日）**是否满足下列条件。

### 蓄势信号（原"主力吸筹"）

- A1 横盘：`HHV(high,20) / LLV(low,20) - 1 < 0.15`（20日振幅 < 15%）
- A2 放量阳线：`volume > MA(volume,5) * 1.5  AND  close > open`
- ~~L2 资金流阶段新高~~ ← 删除（数据源无 L2）
- **蓄势 = A1 AND A2**

### 起爆信号（原"起爆点"/买点）

- B1 突破：`CROSS(close, boll_upper)`（收盘上穿布林上轨）
- B2 倍量：`volume > REF(HHV(volume,5), 1) * 2`（今日量 > 截至昨日的 5 日最高量 × 2）
- B3 MACD 水上金叉状态：`dif > dea  AND  dif > 0`（dif 处于 dea 上方且在零轴上方，是"状态"而非金叉当天；对应原公式用 `>` 而非 `CROSS`）
- **起爆 = B1 AND B2 AND B3**

### 输出筛选

- 仅当 **起爆=True** 的股票进入输出。
- `xushi`（兼蓄势）：该起爆日同时满足蓄势（A1 AND A2）。由于起爆日本身是倍量大阳线，A2 通常自动满足，因此兼蓄势主要由 A1（前期横盘）决定 —— 横盘后的突破视为蓄势充分的真起爆，信号更强。

## 筛选入口函数

```python
def analyze_qibao(
    kline_data: list[dict],   # [{date,open,high,low,close,volume}, ...] 按日期正序
) -> dict | None
```

检查最近一个交易日是否起爆。命中起爆则返回结果 dict（含各项数值与 `xushi` 标志），否则返回 None。

## 输出格式

```json
{
  "date": "2026-06-29",
  "source": "chuangxingao/data/2026-06-29.json",
  "description": "起爆=突破布林上轨+倍量+MACD水上金叉；蓄势=横盘+放量阳线(无L2资金流)",
  "count": 2,
  "stocks": [
    {
      "code": "600563",
      "name": "法拉电子",
      "close": 174.2,
      "pct_chg": 8.5,
      "vol_ratio": 2.3,
      "boll_breakout": true,
      "macd_above_zero": true,
      "xushi": true,
      "signals": ["起爆", "兼蓄势"]
    }
  ]
}
```

字段说明：
- `pct_chg` — 当日涨幅 `(close - ref(close,1)) / ref(close,1)`
- `vol_ratio` — 当日量 / `MA(volume,5)`
- `boll_breakout` — B1 是否满足
- `macd_above_zero` — `dif > 0`
- `xushi` — 是否兼具蓄势
- `signals` — `["起爆"]`，兼蓄势时追加 `"兼蓄势"`

## SKILL.md 交互设计

1. 触发词："起爆"、"起爆点"、"放量突破"、"主力起爆"、"突破布林"。
2. 用户输入 `/qibao <chuangxingao_json路径>`（缺省时默认读最新的 `chuangxingao/data/{date}.json`）。
3. 执行：`python main.py <json路径>`（可选 `--min-history`、`--boll-n` 等调参）。
4. 输出结果摘要：起爆股数量、其中兼蓄势的数量、逐只关键数值。
5. 正文包含 🔴 CHECKPOINT（数据拉取失败/上游缺失时的处理）、边界条件表、❌ 反例（如历史不足、非起爆形态）、流程链（上游=chuangxingao，下游=qsht-agent）。

## 接入 qsht-agent

- 在 `qsht-agent/main.py` 增加 `qibao` 路径常量与步骤调用：从 `chuangxingao/data/{date}.json` 读取，作为创新高之后的派生分支步骤。
- 结果写入 qsht-agent 的 markdown 报告，与现有每步一致。

## 依赖

- requests（HTTP 请求）
- 复用腾讯/新浪数据源，无新增外部依赖

## 扩展性

- `indicators.py` 为纯函数模块，未来其他 skill 需要 MACD/布林/CROSS 可直接复用（可作为项目统一指标库的起点）。
- 信号阈值（振幅 0.15、倍量 ×2、放量 ×1.5、布林 N=20 等）集中为常量/参数，便于实盘验证后调参。
- `analyze_qibao` 当前只看最近一日；未来可扩展为扫描窗口内任意起爆日。

## 已知限制

- 无 L2 资金流，蓄势判定纯靠量价，弱于原公式的主力资金视角。
- 布林突破与创新高股池语义重叠（创新高股多已贴近/突破布林上轨），需实盘验证 B1 的区分度。
- 倍量条件（×2）较严，信号可能偏少；如过少可在调参中放宽。

## 验证

1. 单测：`test_indicators.py` 用已知序列验证 MA/EMA/布林/MACD/HHV/LLV/CROSS 计算正确；`test_analyzer.py` 构造满足/不满足各条件的 K 线验证起爆与蓄势判定，覆盖边界（历史不足、空输入、非起爆形态）。
2. 集成：用真实 `chuangxingao/data/{date}.json` 跑 `python main.py`，检查输出 JSON 格式与字段。
3. 人工抽查 2–3 只起爆股的 K 线，确认突破/倍量/MACD 状态与判定一致。
4. 检查历史不足 40 日的股票是否被正确跳过。
5. 接入 qsht-agent 后，确认 markdown 报告中出现 qibao 步骤与结果。
