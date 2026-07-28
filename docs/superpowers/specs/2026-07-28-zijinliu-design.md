# zijinliu (行业资金流排行榜) 设计文档

## Context

项目已有一整套 A 股选股/观察 skill（zhuxian 主线、renqibang 人气榜、kangdie 抗跌、fupan 复盘等）。本 skill 新增一个**行业资金流排行榜**：盘后抓取东方财富行业板块当日主力资金净流入，按"额 + 占比"双口径排序，作为**复盘观察快照**。

定位（已与用户确认）：
- **复盘观察快照**：看今日主力资金流向哪些行业，作为 fupan 第 2 步（主线）之后的"资金流印证"输入。
- **只看不动，不出买点**：与 renqibang/panqian 同属"市场温度计"类，符合用户"少交易 + 严纪律"的纪律（资金流入 ≠ 买点，利好出尽时常兑现）。
- **对象**：仅行业板块（不做个股/概念板块）。
- **指标**：双口径——主力净流入额（绝对）+ 净流入占比（相对，排除体量偏差）。借鉴用户"量能判定双口径"偏好，单一绝对额会让大行业（银行/非银）长期靠体量霸榜。
- **时间窗口**：仅"今日"（盘后快照）。
- **架构**：复用 renqibang 分层模式（main.py + screener/{fetcher,storage}.py + SKILL.md + probe + tests）。

## 数据流

```
东方财富 push2delay clist (行业板块资金流)
  → 两端各取 Top100: po=1 降序拿流入端 + po=0 升序拿流出端
       (单页上限 100, total≈496, 复盘只需两端, 无需翻全)
  → 各端去重 (消除同行业多层级 BK 的重复; 同端内相邻)
  → 解析字段 (代码/名/涨跌幅/主力净流入额/占比/超大单/大单)
  → 双口径展示 (按主力净流入额排序, 占比列并列)
  → zijin_<date>.json (输出, 保存在 zijinliu/data/)
  → 终端打印 markdown 摘要 (流入 Top20 + 流出 Top10)
```

## 数据源（2026-07-28 实测确认）

- 接口：`http://push2delay.eastmoney.com/api/qt/clist/get`（**push2delay 比 push2 稳**，见 memory 可用性矩阵；走系统代理 `trust_env=True`，http 非 https，带浏览器 UA + `Referer: https://data.eastmoney.com/`，同 renqibang fetcher 模式）。
- 参数：`fs=m:90+t:2+f:!50`，`fid=f62`（按主力净流入降序），`po=1`，`pn`/`pz` 翻页，`fltt=2`，`po=1` 为降序。
- 字段映射（实测）：

| 东财字段 | 含义 | 单位/示例 |
|---|---|---|
| f12 | 板块代码 | BK1283 |
| f14 | 行业名 | 银行 |
| f3 | 涨跌幅 | %（如 1.04） |
| f62 | 主力净流入额 | 元（如 1527127040 ≈ 15.27 亿） |
| f184 | 主力净流入占比 | %（如 4.3） |
| f66 | 超大单净流入额 | 元 |
| f72 | 大单净流入额 | 元 |

- 单页 pz 上限 100，`total≈496`。复盘只需两端（流入 Top + 流出 Top），故 **降序 `po=1` 取一页（流入端）+ 升序 `po=0` 取一页（流出端）**，各 100 条即覆盖；同行业多层级 BK 在同端内相邻，端内去重即可，无需翻全。`--full` 可选翻全 5 页用于排查。
- 实测样本合理：流入 Top 为银行/食品饮料/电力（防御+消费），流出 Top 为电子(-559 亿)/半导体(-317 亿)/通信(-212 亿)（科技），符合正常交易日特征。

## 去重（关键实现点）

**问题**：`fs=m:90+t:2+f:!50` 返回约 496 条，含同一行业的多级分类（东财一级 / 申万二级 Ⅱ / 三级 Ⅲ），底层是同一批股票、f62 完全相同。例如实测中：
- BK1283「银行」与 BK0475「银行Ⅱ」，f62 均为 1527127040（完全相同）
- BK1575「白酒Ⅲ」与 BK1277「白酒Ⅱ」，f62 均为 769635056

若不去重，榜单会出现"银行 / 银行Ⅱ / 国有大型银行Ⅲ / 股份制银行Ⅲ"占据多个位置。

**策略（两段式，TDD 用真实数据定）**：

1. **主策略——探精确一级 fs**：用 `probe_fs.py` 探测只返回东财一级行业（约 86 条、无层级重叠）的 fs 参数。若探到，则无需步骤 2。
2. **降级——数据驱动去重**：按 `(f62, f184)` 元组精确去重（同行业不同层级 BK 的这两个值完全相同；用元组而非单字段降低巧合碰撞）；同值多条中，**优先保留行业名不含罗马后缀 `[ⅡⅢⅣⅤⅥ]` 者**（即一级名），其次保留 f62 绝对值最大者。

> 注：实测中"通信"(-212 亿) 与"通信设备"(-209 亿) f62 不同，是不同成分（通信含运营商+设备，通信设备只含设备），降级算法会正确保留两者，不误并。

`probe_fs.py` 同时承担开发期探字段 + 维护期诊断接口改版（同 renqibang probe_rank.py 先例）。

## 文件结构（镜像 renqibang）

```
.claude/skills/zijinliu/
├── SKILL.md              # 技能描述、使用方式、执行步骤、边界、反例
├── main.py               # 编排：CHECKPOINT → fetch → dedup → sort → store → print
├── screener/
│   ├── __init__.py
│   ├── fetcher.py        # push2delay clist 翻页 + 走代理 + 重试 + 去重
│   └── storage.py        # zijin_<date>.json 读写
├── probe_fs.py           # 探精确一级 fs / 字段（开发 & 维护用）
├── data/                 # zijin_<date>.json
├── tests/
│   ├── __init__.py
│   ├── test_fetcher.py   # mock requests 测翻页/去重/字段解析
│   ├── test_storage.py
│   └── test_main.py      # 注入 mock fetcher 测编排
├── requirements.txt      # requests（无 Playwright，比 renqibang 轻）
└── test-prompts.json
```

## fetcher.py

- 复用 renqibang 的会话配置：`Session().trust_env=True`、浏览器 UA、Referer、http 非 https、`RETRIES=3`（push2delay 偶发空响应，带退避重试）。
- `fetch_top_flows(per_end=100) -> dict`：发两次请求——`po=1` 降序 pz=per_end 拿流入端、`po=0` 升序 pz=per_end 拿流出端；`diff` 接口返回 dict，按 `.values()` 取；返回 `{"inflow": [...], "outflow": [...]}`（原始 dict 列表）。
- `parse(raw_row) -> dict`：单条原始 dict → 统一结构（含 `main_net_yi` 换算）。
- `dedup(industries) -> list[dict]`：实现上述"降级去重"算法（端内按 `(f62,f184)` 去重，保留无罗马后缀名；主策略探到一级 fs 时此函数退化为近似 no-op，仍保留以兜底）。
- 可选 `fetch_full() -> list[dict]`：pn=1..5 翻全 5 页（`--full` 排查用）。
- 解析后每条结构：
  ```python
  {"code": "BK1283", "name": "银行", "change_pct": 1.04,
   "main_net": 1527127040,        # 元
   "main_net_yi": 15.27,          # 亿（展示用，÷1e8 保留两位）
   "main_pct": 4.3,
   "super_large_net": 1108062464, # 超大单净流入额(元)
   "large_net": 419064576}        # 大单净流入额(元)
  ```

## storage.py

- `save_results(date_str, inflow, outflow, output_dir) -> path`：覆盖写 `zijin_<date>.json`（防覆盖由 main 的 CHECKPOINT 处理）。
- `load_results(date_str, output_dir) -> dict | None`。
- JSON schema：
  ```json
  {
    "date": "2026-07-28",
    "fetched_at": "2026-07-28T15:30:00",
    "source": "东方财富行业板块资金流(push2delay clist)",
    "sort": "流入端 po=1 降序 / 流出端 po=0 升序（各端已去重）",
    "inflow_count": 86,
    "outflow_count": 86,
    "count": 172,
    "inflow":  [ { ... fetcher 解析结构 ... } ],
    "outflow": [ { ... 同结构, main_net 为负 ... } ]
  }
  ```

## main.py

- 编排：CHECKPOINT（今日快照存在则提示，`--force` 覆盖）→ `fetcher.fetch_top_flows()`（返回 inflow/outflow 两端原始数据）→ 各端 `parse` + `dedup` → `storage.save_results(inflow, outflow)` → `_print_summary`。
- CLI：`python main.py [--top 20] [--outflow-top 10] [--per-end 100] [--date YYYY-MM-DD] [--force] [--full]`。
- 终端 markdown 摘要：
  ```
  # 行业资金流 · 2026-07-28（东方财富·今日）
  共 N 个行业 | 主力净流入额降序（占比为净流入/成交额，排除体量偏差）

  ## 主力净流入 Top 20
  | # | 行业 | 涨跌% | 主力净流入(亿) | 占比% | 超大单(亿) |
  |---|---|---|---|---|---|
  ...

  ## 主力净流出 Top 10
  ...（同结构，净流出为负值）
  ```
- 可注入 `fetcher`（测试用），默认用 `screener.fetcher`。

## SKILL.md 执行步骤

1. 🔴 CHECKPOINT：`ls data/zijin_<今日>.json`，存在则提示"今日资金流快照已抓取，重跑会覆盖"，未加 `--force` 时 STOP 询问。
2. 确认依赖：`pip install -r requirements.txt`（仅 requests）。
3. 运行：`python main.py`（约 2–5 秒，无 Playwright）。
4. 读取 JSON 或终端摘要向用户展示。
5. 提醒：高流入 ≠ 买点，须结合 fupan/qsht 纪律。

## 边界条件

| 触发 | 处理 |
|---|---|
| 非交易日 | 资金流接口仍返回上一交易日数据，正常抓取，JSON 的 date 标注实际数据日 |
| push2delay 偶发空响应 | 3 轮退避重试（同 renqibang） |
| 接口被封/改版 | 报错 + 提示重跑 probe_fs.py 诊断；**不做 fallback**（资金流无等价替代源，口径不一混用易乱） |
| 今日快照已存在 | CHECKPOINT 询问，`--force` 覆盖 |
| 盘中运行 | 资金流为盘中实时值（非昨日），与日 K 类 skill 不同，盘中可跑但值会随盘中变化；复盘建议收盘后跑 |

## 测试（TDD）

- `test_fetcher.py`：mock requests，测①`fetch_top_flows` 发降序 + 升序两次请求、返回 inflow/outflow ②diff 为 dict 的 `.values()` 解析 ③`dedup`（构造银行/银行Ⅱ同 `(f62,f184)` 的样本，断言端内去重为一个、保留无后缀名）④`parse` 字段单位换算（main_net_yi）。
- `test_storage.py`：save→load round-trip，覆盖写。
- `test_main.py`：注入 mock fetcher，测编排（CHECKPOINT 提示、排序、Top N 截取、摘要打印）。

## 不做（YAGNI）

- 个股资金流排行榜（用户未选）
- 概念板块资金流（用户未选）
- 多时间窗口（5 日 / 10 日，用户只选今日）
- 买点信号 / 接入 qsht 选股（只看不动）
- fallback 数据源（资金流无等价替代源）
- L2 大单细分（f66/f72 已含超大单/大单，够复盘用，不追更细粒度）
