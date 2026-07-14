# 人气榜（renqibang）设计文档

- **日期**：2026-07-14
- **状态**：待实现
- **作者**：brainstorming 产出
- **skill name**：`renqibang`

## 1. 背景与目标

用户要一个"拉取同花顺或东方财富前 100 人气榜"的 skill，且每只股票必须保存 **上榜原因、所属行业、人气排名**。

经数据源实测（见第 6 节），最终落地为：抓取**东方财富股吧个股人气榜 Top100** 快照，每只股票保存 **人气排名 + 所属行业 + 题材（作为"上榜原因"）+ 热度 + 排名变动**，结果存为本地 JSON。

它回答一个问题：
> **此刻 A 股市场最受股吧用户关注的 100 只股票是谁、属于什么行业、沾了什么题材？**

### 它不是什么
- **不是选股器、不是买入信号**：人气榜反映"市场关注度/热度"，高人气 ≠ 值得买入，利好出尽时高人气股往往兑现下跌。本 skill 只采集读数，供观察市场情绪与热门方向。
- **不是实时盯盘工具**：每次触发抓一份**快照**存盘，不做盘中持续推送。
- **不预测涨跌**：只记录排名/行业/题材，不给目标价或买卖建议。

> ⚠️ 对齐用户体系：用户是历史负期望的过度交易者（见 memory）。人气榜天然诱导"追热点"。本 skill 的定位是**市场情绪观察参考**，SKILL.md 须明示"高人气不等于买点，需结合 qsht 体系的趋势/回踩/市值等纪律使用"。

## 2. 范围

### 本期做
- 抓取东方财富股吧个股人气榜**热度榜 Top100**（`guba.eastmoney.com/rank`）。
- 每只股票保存：人气排名、代码、名称、热度、排名变动、所属行业、题材（概念板块，作为"上榜原因"）。
- 结果存为 `data/popularity_<date>.json`，终端打印 markdown 摘要（Top10 + 行业分布 + 热门题材）。

### 本期不做（YAGNI / 未来扩展）
- 同花顺人气榜（实测不可行，见 6.1）。
- 抓股吧热门帖 + LLM 抽取事件（实测题材可用 push2 概念字段轻量获取，无需 LLM）。
- 接入 qsht-agent / eval-stock 流水线（本期存结构化 JSON + 查询函数，留待日后按需引用）。
- 人气排名历史趋势曲线（榜单自带 `rankchange`/`strHistory`，本期只存当前值，画图留未来）。
- 同时抓"人气升幅榜（飙升榜）"（本期仅热度榜，排序选项见第 12 节 CHECKPOINT）。

## 3. 核心参数（已与用户确认）

| 决策项 | 取值 |
|---|---|
| 数据源 | **东方财富股吧个股人气榜**（同花顺实测不可行，已排除） |
| 榜单排序 | **热度榜**（`sort=1`，综合人气）；飙升榜 `sort=0` 留作可选 |
| 取数数量 | **Top 100** |
| "上榜原因"落地 | **题材 = push2 概念板块字段 `f129`**（榜单无原生原因字段，实测确认） |
| 所属行业 | push2 行业字段 `f127` |
| 绕过加密方式 | **Playwright 渲染页面读解密后 DOM**（纯 Python 解密不可行，见 6.2） |
| 触发即抓当前快照 | 是（人气榜基于股吧行为，盘中/盘后均有数据） |

## 4. 架构：渲染抓榜单 + 明文接口补字段

```
Playwright 渲染 guba.eastmoney.com/rank（JS 自动解密人气榜密文）
        ↓ 读解密后 DOM，翻页收集 Top100
   [{rank, code, name, popularity, rank_change}, ...]  ×100
        ↓ 对 100 只并发请求 push2 stock/get（明文）
   补 f127(行业) + f129(题材)
        ↓ 合并
   保存 data/popularity_<date>.json + 终端 markdown 摘要
```

### 为什么榜单用 Playwright、字段用 requests（混合而非全浏览器）
- **榜单 list 是加密的**：接口返回 AES-CBC-Pkcs7 密文，key 被前端自定义函数 `i.M("getUtilsFromFile")` 动态派生，纯 Python 静态解密实测失败（见 6.2）。让浏览器执行 JS 自动解密最稳。
- **行业/题材接口是明文的**：`push2.eastmoney.com/api/qt/stock/get` 直接返回 JSON，`f127`/`f129` 一次拿全，requests 直连即可，不必走浏览器（更快、更省资源）。
- 100 只股票的行业/题材用线程池并发请求 push2，单只毫秒级，整体几秒完成。

## 5. 目录结构（沿用项目惯例）

```
.claude/skills/renqibang/
├── SKILL.md
├── main.py                 # 编排：渲染榜单→补字段→保存→打印摘要
├── requirements.txt        # requests, playwright（新增依赖）
├── screener/
│   ├── __init__.py
│   ├── browser.py          # Playwright 渲染人气榜，翻页提取 Top100
│   ├── fetcher.py          # push2 stock/get 明文接口：行业 f127 + 题材 f129
│   └── storage.py          # popularity_<date>.json 读写
├── data/
│   └── .gitkeep            # popularity_*.json 运行时产物，不入库
└── tests/
    ├── test_browser.py     # DOM 解析逻辑（用录制的 HTML 片段，不真开浏览器）
    ├── test_fetcher.py     # secid 构造 / 字段解析（mock 接口返回）
    └── test_storage.py     # 读写一致性
```

**入库策略**：`data/popularity_*.json` 为运行时产物，沿用各 skill 惯例（`.gitignore` 忽略 `data/*.json`，保留 `.gitkeep`）。

## 6. 数据源与接口（均经实测）

### 6.1 同花顺（已排除）
- 固定人气榜页面 `10jqka.com.cn/hot-list` 实测 **404**。
- 问财（iwencai）查询需动态反爬 token `hexin-v`（JS 生成），requests 直连被拦，长期不稳。
- **结论**：同花顺路线不可行，本期只用东方财富。

### 6.2 东方财富股吧人气榜（榜单本体，加密 → 用 Playwright 渲染）
- **榜单页**：`https://guba.eastmoney.com/rank/`（基于股吧用户行为，非事件榜）。
- **数据接口**：`https://gbcdn.dfcfw.com/rank/popularityList.js?type=0&sort={0:人气升幅|1:热度榜}&page=n&m=<分钟>`，返回 `var popularityList='<AES密文>'`。
- **加密细节（实测）**：
  - 算法：**AES-CBC-Pkcs7**（前端 `window.d()`，`CryptoJS.AES.decrypt` 等价别名 `AlocalStorage`）。
  - iv = `enc.Utf8.parse("getClassFromFile")`（16 字节）。
  - key = `enc.Utf8.parse(o)`，其中 `o = i.M("getUtilsFromFile")`，`i.M` 为自定义派生方法，**静态分析拿不到 o 的值**；穷举 `d_key`/`d_iv`/`getUtilsFromFile`/`getClassFromFile` + EVP_BytesToKey 全部 padding error。
  - 即便动态调试破解，**前端改版加密即失效**，脆弱。
- **结论**：放弃纯 Python 解密，改用 Playwright 渲染页面，让浏览器 JS 自动 `window.d()` 解密 + `eval`，直接读渲染后 DOM 表格。
- **DOM 提取字段**（实现时以实际渲染结构为准）：排名 `rankNumber`、代码 `code`、名称、热度、排名变动 `rankchange`、历史趋势 `strHistory`。本期取 排名/代码/名称/热度/排名变动。

> 🔴 **实现 CHECKPOINT（DOM 结构核对）**：榜单页渲染后的表格 DOM 结构（class/selector）需在实现首步用 Playwright 打印实际 HTML 确认，再写提取规则，并把实测 selector 写进 SKILL.md。前端改版会导致 selector 失效，属可接受的维护点。

### 6.3 push2 个股接口（行业 + 题材，明文 → requests）
- **接口**：`https://push2.eastmoney.com/api/qt/stock/get?secid=<前缀>.<code>&fields=f57,f58,f127,f129`，带 `User-Agent` + `Referer: https://quote.eastmoney.com/`。
- **secid 前缀**：代码 `6` 开头 → `1.`（沪），其余（`0/3` 深，`8/4/920` 北交所）→ `0.`。
- **实测字段**（2026-07-14，以 600000 为例）：
  - `f57` = 代码（600000）
  - `f58` = 名称（浦发银行）
  - `f127` = **行业板块名**（银行）→ 所属行业 ✅
  - `f129` = **概念板块列表**（"沪股通,融资融券,标准券"）→ 题材，作为"上榜原因" ✅
- **降级**：若某只 `f127`/`f129` 为空（如部分北交所/新股），该字段填空字符串/空数组，不阻断整批。

### 6.4 关于"上榜原因"的说明（重要）
榜单本身**没有**"上榜原因"字段（同花顺、东方财富均无）。用户要的"上榜原因"经实测确认落地为 **push2 `f129` 概念板块**（如"AI算力""机器人""业绩预增"），即该股所沾的题材。这是"上榜原因"最贴近、且轻量可靠的语义——高人气股通常因某题材被关注。无需抓股吧热门帖或调用 LLM。

## 7. 核心流程（main.py 编排）

```
1. 🔴 CHECKPOINT：data/popularity_<today>.json 是否存在
   → 存在则提示"今日人气榜快照已抓取，重跑会覆盖"，询问确认后才继续
   （沿用 chuangxingao/zhongbaoyubao 防覆盖惯例）

2. Playwright headless 打开 guba.eastmoney.com/rank，切换"热度榜"：
   - wait_for_selector 等榜单表格渲染（JS 解密完成）
   - 提取当前页 Top20；操作分页（点"下一页"或改 page 参数）至累计 100 条
   - 每条取 {rank, code, name, popularity, rank_change}
   - 不足 100 时取实际条数并提示

3. 对 100 只股票并发请求 push2 stock/get（线程池，~10 并发）：
   - 补 industry(f127)、concepts(f129 split 逗号)
   - 失败的字段留空，不阻断

4. 合并 → save_results 存 data/popularity_<today>.json

5. 终端打印 markdown 摘要（见第 9 节）

并发：第 3 步用线程池（参考 chuangxingao/main.py）；第 2 步浏览器为单实例顺序翻页。
单只 push2 请求超时 10s、重试 2 次。
```

## 8. 数据结构：popularity_<date>.json

```json
{
  "date": "2026-07-14",
  "fetched_at": "2026-07-14T15:02:30",
  "source": "东方财富股吧个股人气榜",
  "sort": "热度榜",
  "count": 100,
  "stocks": [
    {
      "rank": 1,
      "code": "600000",
      "name": "浦发银行",
      "popularity": 426283,
      "rank_change": "+5",
      "industry": "银行",
      "concepts": ["沪股通", "融资融券", "标准券"],
      "reason": "沪股通,融资融券,标准券"
    }
  ]
}
```

说明：
- `rank`：人气排名（1=最热）。
- `popularity`：热度数值（榜单原生）。
- `rank_change`：排名变动（榜单原生 `rankchange`，如 "+5"/"新进"/"-"）。
- `industry`：所属行业（push2 `f127`）。
- `concepts`：题材数组（push2 `f129` 按逗号切分）。
- `reason`：上榜原因 = `concepts` 原样拼接字符串（便于终端展示与日后检索）。

## 9. 输出：终端 markdown 摘要

```markdown
# 人气榜快照 · 2026-07-14（东方财富·热度榜）
共 100 只 | 来源：guba.eastmoney.com/rank

## Top 10
| 排名 | 代码 | 名称 | 行业 | 热度 | 变动 | 题材 |
| 1 | 600000 | 浦发银行 | 银行 | 426283 | +5 | 沪股通,融资融券 |

## 行业分布（Top 5）
| 行业 | 数量 |
| 电子 | 18 |
| ...

## 热门题材（Top 8，按出现频次）
| 题材 | 出现次数 |
| AI算力 | 12 |
| ...
```

## 10. 边界条件与失败处理

| 触发条件 | 一线处理 | 仍失败兜底 |
|---|---|---|
| 非交易日（周末/节假日）执行 | 人气榜基于股吧行为仍有数据，正常抓取，摘要标注"非交易日，数据为最近股吧活跃快照" | — |
| Playwright/chromium 未安装 | SKILL.md 提示 `pip install playwright && playwright install chromium`，脚本启动检测失败时给出明确安装指引并退出 | — |
| 榜单渲染超时（JS 未解密完成） | 增大 wait_for_selector 超时 + 重试 1 次 | 仍失败提示"页面渲染异常，稍后重试" |
| 榜单不足 100 条 | 取实际条数，摘要如实显示 count | — |
| push2 某只 f127/f129 为空 | 该字段留空，继续 | — |
| push2 接口字段变更（f127/f129 失效） | 打印原始返回，降级提示"行业/题材接口异常"，榜单字段仍保存 | 提示稍后重试 |
| DOM selector 失效（前端改版） | 报错并提示"榜单页面结构变更，需更新 selector" | — |
| popularity_<today>.json 已存在 | CHECKPOINT 询问是否覆盖 | — |

## 11. 反例黑名单（❌ 不要做）

| 不要 | 原因 | 正确做法 |
|---|---|---|
| 把高人气当买入信号 | 高人气≠会涨，常是兑现下跌窗口 | 只作市场情绪观察，结合 qsht 纪律使用 |
| 为了"上榜原因"抓股吧帖子 + LLM | 题材可用 push2 f129 轻量拿到 | 直接用 f129 概念板块 |
| 纯 Python 逆向解密人气榜接口 | key 动态派生 + 前端改版即失效，脆弱 | Playwright 渲染让浏览器解密 |
| 逐个请求 push2 不并发 | 100 只慢 | 线程池并发补字段 |
| 忽略 CHECKPOINT 直接覆盖今日快照 | 重跑无意义 | 先询问 |
| 用同花顺人气榜 | hot-list 404、问财需 token，不稳 | 固定东方财富 |

## 12. CHECKPOINT 规范

1. **运行前**：`data/popularity_<today>.json` 是否存在 → 存在则询问是否覆盖。
2. **DOM 结构核对（实现期）**：首次对接榜单页时，用 Playwright 打印渲染后表格 HTML，确认 selector 后再写提取规则，实测 selector 写进 SKILL.md。
3. **排序选项（可选交互）**：默认热度榜；若用户显式要"飙升榜/人气升幅榜"，传 `sort=0`。

## 13. 测试计划（pytest，沿用 TDD 惯例）

### test_browser.py（DOM 解析，不真开浏览器）
- 用录制的榜单表格 HTML 片段，测提取函数：正确解析 rank/code/name/popularity/rank_change。
- 缺字段、异常结构 → 留空不崩。
- 不足 100 → 取实际条数。

### test_fetcher.py（mock 接口返回）
- secid 构造：600000→`1.600000`；000001→`0.000001`；920001→`0.920001`。
- 字段解析：`f129="沪股通,融资融券"` → `["沪股通","融资融券"]`。
- 空 f127/f129 → 留空。

### test_storage.py（临时 data 目录）
- 写后读回字段完整。
- 覆盖写：同 date 重写正确替换。

网络层（browser/fetcher）用 mock/录制的返回测试，不在单测里真实联网或开浏览器。

## 14. 依赖

`requirements.txt`：`requests`、`playwright`（**新增**，现有 skill 无）。并发用标准库 `concurrent.futures`。
- 首次使用需 `pip install playwright` 且 `playwright install chromium`（下载 chromium，Windows 一次性成本）。
- 已在 SKILL.md 与边界处理中给出安装指引。

## 15. 局限（写进 SKILL.md）

- 人气榜是**股吧用户行为**衍生的热度，不代表基本面，高人气股利好出尽可能下跌。
- "上榜原因"= 题材概念（push2 f129），是该股**所沾概念**，不一定是当日催化的具体事件。
- 仅抓热度榜 Top100 快照，不反映盘中动态变化。
- Playwright 依赖 chromium，环境需支持；前端改版可能导致 DOM selector 或加密逻辑变化，需维护。

## 16. SKILL.md 触发词与定位

**触发词**：`人气榜` / `股吧人气` / `热门股人气` / `东方财富人气榜` / `人气排名` / `renqibang`。

**定位提示（写入 SKILL.md 头部）**：本 skill 采集东方财富股吧人气榜 Top100 作为**市场情绪观察参考**，高人气不等于买点，须结合 qsht 选股体系的趋势/回踩/市值/业绩纪律使用，避免追涨。
