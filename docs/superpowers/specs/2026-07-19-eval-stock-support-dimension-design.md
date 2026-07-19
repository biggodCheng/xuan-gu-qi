# eval-stock 新增 ⑦ 承接维度 — 设计文档

> **日期**：2026-07-19
> **作者**：biggodCheng × Claude
> **状态**：设计已确认，待实现
> **关联**：源自 [docs/2026-07-19-高手选股复盘思路-整理版.md](../../2026-07-19-高手选股复盘思路-整理版.md) 的"看承接，决定买不买"一节

---

## 1. 背景与目标

### 1.1 来源
公众号文章《散户亏损根源》指出高手选股第 5 步是"看承接"——判断下跌时有无资金主动护盘，决定买点。承接有力的 3 个实战信号：
1. 下跌阶段成交量明显缩量（持股资金不愿割肉抛售）
2. 回调时不会跌破关键支撑价位
3. 分时图出现砸盘后，有资金快速拉升收回失地

### 1.2 目标
将"承接"作为 eval-stock 的**第 ⑦ 维度**，使个股体检覆盖"买点承接"这一最后一环，与现有趋势/涨停/回踩/市值/Q2/赛道构成完整的"选股 → 买点"成色评估。

### 1.3 非目标
- **不**参与 qsht 漏斗淘汰（承接是买点时机，非成色筛选）
- **不**引入分时数据源（保持 eval-stock"秒级、纯终端、无新依赖"哲学）
- **不**修改 ①②③④ 现有维度的任何阈值与逻辑

---

## 2. 关键设计决策（已与用户确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 信号3 数据源 | **日K长下影近似** | 无新依赖、保持秒级；长下影=盘中砸到 low 又收回，是分时砸盘收回的合理日K代理（chaodiefantan `is_oversold_rebound` 已有同类逻辑） |
| 漏斗角色 | **参考维度 ⑦**（同 ⑤⑥） | 承接是买点时机，趋势在但承接弱=等买点而非不买；硬淘汰会误杀好票并与 qsht 选股语义错位 |
| 口袋严苛度 | **标准**（≥2 信号命中=有力） | 单信号易误判，≥2 平衡稳健与敏感度 |
| 支撑位定义 | **回调前 20 日平台低点** | 普适、不依赖是否有涨停；"本次回调不破前平台"是清晰的承接证据 |

---

## 3. 三信号判定口径

### 3.0 观察窗口与参数常量（提取至 analyzer.py 顶部）

```python
SUPPORT_WINDOW       = 10   # 承接观察窗口（近 N 交易日）
SUPPORT_LOOKBACK     = 20   # 支撑基准回看（回调前平台）
SUPPORT_TOLERANCE    = 0.98 # 不破支撑容忍度（2% 防假跌破）
SHRINK_RATIO         = 0.8  # 下跌缩量阈值（复用现有常量）
LOWER_SHADOW_RATIO   = 0.5  # 长下影阈值（下影占振幅比）
SUPPORT_HIT_THRESHOLD = 2   # "承接有力"的命中信号门槛
```

### 3.1 信号 1 — 下跌缩量
- **定义**：在近 `SUPPORT_WINDOW`(10) 日窗口内存在下跌日 D（`close_D < close_{D-1}`），且该日 `volume_D < volume_{D-1} × SHRINK_RATIO(0.8)`。
- **命中**：窗口内至少存在 1 个"缩量下跌日"。
- **语义**：最近一次下跌伴随量能萎缩 = 持股资金不愿割肉抛售。

### 3.2 信号 2 — 不破支撑
- **定义**：
  - 支撑基准 `base_low = min(low for 第 -30 … -11 日)`（即近 10 日**之前**的 20 日最低价，回调前平台低点）
  - 回调低点 `recent_low = min(low for 近 10 日)`
- **命中**：`recent_low >= base_low × SUPPORT_TOLERANCE(0.98)`
- **语义**：本次回调没有跌破回调前的平台低点，关键支撑守住。
- **注**：早期方案曾用"近10日低点 vs 近20日低点"，因 10 日是 20 日子集恒成立，已废弃。

### 3.3 信号 3 — 砸盘收回（长下影代理）
- **定义**：近 10 日内存在 K 线 i 满足：
  - `high_i > low_i`（防除零）
  - `lower_shadow_ratio = (min(open_i, close_i) - low_i) / (high_i - low_i) >= LOWER_SHADOW_RATIO(0.5)`
- **命中**：存在至少 1 根这样的 K 线。
- **数学注**：`ratio >= 0.5` ⟺ `min(open,close) >= (high+low)/2`，即 open 与 close 均 ≥ 中点。这天然排除"大阴线留长上影"（大阴线 close 低 → min 低 → ratio < 0.5），故无需额外的"收盘中上部"条件（早期方案曾加，已证冗余移除）。
- **语义**：盘中砸到 low 又收回来 = 有资金承接拉升。

### 3.4 灯标合成

| hit_count | 灯标 | 含义 |
|-----------|------|------|
| ≥ 2 | ✅ | 承接有力 |
| = 1 | ➖ | 承接一般 |
| = 0 | ❌ | 承接弱 |
| None（数据不足） | ➖ | 标注原因（K线 < 30 根等） |

数据不足时返回 `hit_count=None` 且**不带 `pass` 键**，与"承接弱（hit=0, pass=False → ❌）"明确区分：前者是信息缺失（中性灰），后者是承接明确差（负面）。

---

## 4. 代码接入点

### 4.1 analyzer.py — 新增 `check_support`
```python
def check_support(kline: list[dict]) -> dict:
    """承接 3 信号：下跌缩量 / 不破支撑 / 砸盘收回(长下影代理)。

    返回 {hit_count, signals, label, detail}。pass 键按 hit_count 三态：
    >= SUPPORT_HIT_THRESHOLD → True（✅）；==0 → False（❌）；
    ==1 或数据不足(None) → 省略该键（_lamp 走 else → ➖）。
    """
```
- 输入：现有 `kline`（同 check_new_high 等的入参）
- 数据不足兜底：`len(kline) < SUPPORT_WINDOW + SUPPORT_LOOKBACK`（30）→ 返回 `{hit_count: None, label: "数据不足", detail: ...}`，不带 pass / signals
- 返回字段：
  - `hit_count`: 0–3，或 None（数据不足）
  - `signals`: `[s1_bool, s2_bool, s3_bool]`（数据不足时省略）
  - `pass`: hit_count >= SUPPORT_HIT_THRESHOLD → True（✅）；==0 → False（❌）；==1 或 None → **省略该键**（→ _lamp 走 else → ➖）
  - `label`: 如 `"有力（命中：缩量、不破支撑）"` / `"一般（命中：砸盘收回）"` / `"弱（0/3）"`
  - `detail`: 各信号的关键数值（量比、recent_low/base_low、下影比）

### 4.2 main.py — `evaluate_one` 调用
在 [main.py:124](../../../.claude/skills/eval-stock/main.py#L124) `mc = check_marketcap(...)` 之后插入：
```python
sp = check_support(kline)
```
并在返回 dict（[main.py:133-139](../../../.claude/skills/eval-stock/main.py#L133-L139)）增加 `"support": sp`。

### 4.3 reporter.py — 输出与警示
- `_FUNNEL_STEPS` **保持不变**（承接不进漏斗）。
- `_lamp` **无需改动**：依赖 4.1 的 pass 键约定即可正确映射三态（hit>=2→✅ / hit==0→❌ / hit==1→无pass无verdict→➖）。
- `format_report` 在 ⑥ 赛道输出之后（[reporter.py:80](../../../.claude/skills/eval-stock/screener/reporter.py#L80) 之后）新增：
  ```
  ⑦ 承接        {lamp}  {label}
  ```
- `_oneliner` 增加承接弱警示：当 `stock["support"]["hit_count"] == 0` 时 `parts.append("承接偏弱，等买点")`。

### 4.4 SKILL.md 更新
- description / 标题："6 维度"→"7 维度"，新增"承接"。
- 维度列表增加 ⑦ 承接条目（标注参考维度、3信号口径简述、数据源=日K）。
- "输出示例"代码块增加 ⑦ 行。
- "与 qsht-agent 的差异"补一句：⑦ 承接为 eval-stock 体检独有，qsht-agent 选股流程暂不接入。
- "反例黑名单"增加一行：承接弱 ≠ 不买，是"等买点"；承接是买点维度非成色筛选。

---

## 5. 测试计划

延续 [tests/test_analyzer.py](../../../.claude/skills/eval-stock/tests/test_analyzer.py) 纯函数测试风格，新增 `check_support` 用例：

| 用例 | 构造 | 期望 |
|------|------|------|
| 全命中 | 近10日内有缩量下跌日 + 低点不破前平台 + 含长下影收回K | hit=3, pass=True ✅ |
| 仅命中砸盘收回 | 放量下跌跌破前平台 + 但有1根长下影收回K | hit=1, 无pass键 ➖ |
| 全不命中 | 放量下跌 + 跌破前平台 ×0.9 + 无长下影 | hit=0, pass=False ❌ |
| 数据不足 | len(kline)=20 | hit_count=None, label="数据不足", 无pass键 ➖ |
| 边界：长下影但收在中下部 | 下影比≥0.5 但 close < (h+l)/2（大阴线） | 信号3 不命中（验证收回条件） |

reporter 层：可在 test_reporter.py 增 1 个用例验证 ⑦ 行出现 + 承接弱时"一句话"含"等买点"。

---

## 6. 边界条件与兼容

| 情况 | 处理 |
|------|------|
| K线 < 30 根 | ⑦ 标"数据不足"➖，不阻断其他维度 |
| 涨停一字板（high==low） | 信号3 该K线被 `high>low` 过滤，不参与 |
| 停牌/数据缺失 | 沿用 fetcher 现有返回空容错，⑦ 标"数据不足" |
| 现有 ①②③④⑤⑥ | 完全不受影响（纯新增维度） |

---

## 7. 实现顺序建议

1. analyzer.py：常量 + `check_support` 纯函数
2. tests/test_analyzer.py：5 个用例，先红后绿（TDD）
3. main.py：调用 + 打包
4. reporter.py：⑦ 行输出 + 警示
5. 端到端冒烟：`python main.py 深科技` 等实盘样本验证输出
6. SKILL.md：文档更新
