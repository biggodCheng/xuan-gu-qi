# Q2展望 skill 设计文档

- **日期**:2026-06-26
- **skill 名称**:Q2展望(目录 slug:`q2zhanwang`)
- **状态**:设计已确认,进入实现

## 一、目标

给定一只 A 股股票,基于其 **2026 年一季度(2026Q1)已披露业绩**,推断 **2026Q2 业绩走向**,产出**定性展望(偏正/中性/偏负)+ 信号面板 + 置信度**,而非伪精确的预测数字。

> 克制原则:公开季报不足以支撑精确预测。本 skill 给方向 + 摊开依据,把判断权留给用户。对齐 `sidasaidao` 的"confidence + 正确解读"哲学。

## 二、数据源(已验证可用)

东方财富 datacenter 业绩报表接口:

```
GET https://datacenter-web.eastmoney.com/api/data/v1/get
    reportName  = RPT_LICO_FN_CPD
    filter      = (SECURITY_CODE="<code>")
    sortColumns = REPORTDATE  sortTypes=-1
    pageSize    = 9            # 取近 9 期,覆盖 2024Q1~2026Q1
```

字段(均累计口径):
- `PARENT_NETPROFIT` 归母净利润(元)
- `TOTAL_OPERATE_INCOME` 营业收入(元)
- `XSMLL` 毛利率(%)
- `QDATE` 报告期标识(如 `2026Q1`、`2025Q4`)
- `REPORTDATE` 报告日期(如 `2026-03-31`)
- `SECURITY_NAME_ABBR` 名称、`PUBLISHNAME` 行业

股票代码解析复用 `sidasaidao` 同款 `resolve_stock_code`(东方财富 searchapi + 新浪行情)。

## 三、架构与文件职责

```
.claude/skills/q2zhanwang/
├── SKILL.md              # 文档(使用方式/执行步骤/边界/输出/⚠️局限)
├── main.py               # 单只入口:python main.py "<代码或名称>"
├── batch_query.py        # 批量入口:python batch_query.py <stocks.json>
├── requirements.txt      # requests>=2.28.0
└── screener/
    ├── __init__.py
    ├── fetcher.py        # resolve_stock_code + get_financial(取近9期累计数据)
    └── analyzer.py       # 单季化 + Q1定位 + verdict判定 + 格式化(纯逻辑,可测)
```

职责隔离:`fetcher` 只管取数 + 解析代码;`analyzer` 只管单季化、信号计算、判定、格式化。

## 四、核心技术点:单季化(已验证必要)

接口每期返回的是**累计**口径。**接口自带的 `SJLTZ`/`YSTZ` 同比随报告期变口径**(一季报=单季、年报=全年、中报=H1),**不能跨期比较**。

→ analyzer **统一自算单季同比**,不直接用接口同比字段:

- 单季值:`Q单季 = 本期累计 − 上一期累计`(相邻相减)
  - `Q1单季 = Q1累计`(年初至3月末,天然单季)
  - `Q2单季 = 中报 − 一季报`
  - `Q3单季 = 三季报 − 中报`
  - `Q4单季 = 年报 − 三季报`
- 单季同比:`(本期单季 − 去年同期单季) / |去年同期单季|`

**验证(比亚迪 002594)**:
- 2026Q1单季归母 = 40.85亿,2025Q1单季 = 91.55亿 → Q1单季同比 = -55.38%
- 2025Q4单季 = 326.19(年报)−233.33(三季报)= 92.86亿;2024Q4单季 = 402.54−252.38=150.16亿 → 2025Q4单季同比 = **-38.17%**(接口给全年口径 -18.97%,完全不同,证明自算必要)

## 五、信号体系(用户已选定 A + B)

### 信号 A:同比势头(加速度)
对比 `2026Q1单季同比` 与 `2025Q4单季同比`:
- Q1 > Q4 → **加速**(偏正)
- Q1 ≈ Q4 → **持平**
- Q1 < Q4 → **减速**(偏负)

### 信号 B:营收-净利背离
对比 `2026Q1营收同比` 与 `2026Q1净利同比`,辅以毛利率同比变化(`2026Q1毛利率 − 2025Q1毛利率`):
- 营收涨 & 净利跌(或净利远弱于营收)+ 毛利率压缩 → **利润承压**(偏负)
- 营收跌 & 净利涨 / 毛利率回升 → **利润改善**(偏正)
- 同向、幅度接近 → **同步**(中性)

(季节性 D、现金流 E 经讨论不纳入,见 YAGNI)

## 六、verdict 判定逻辑

| | A 加速 | A 持平 | A 减速 |
|---|---|---|---|
| **B 改善** | 偏正 | 偏正/中性 | 中性 |
| **B 同步** | 偏正 | 中性 | 偏负 |
| **B 承压** | 中性 | 偏负 | **偏负** |

- **confidence**:两信号同向→高;矛盾→中;数据缺期或单季化异常→降级为低。
- 只输出方向(偏正/中性/偏负),绝不输出伪精确的 Q2 预测数值。

## 七、输出格式

### 单只(`main.py`)
```json
{
  "code": "002594", "name": "比亚迪", "industry": "乘用车",
  "report_period": "2026Q1",
  "q1": {
    "netprofit_yoy": -55.38,
    "revenue_yoy": -11.82,
    "gross_margin": 18.81,
    "gross_margin_prev": 20.07,
    "parent_netprofit_yi": 40.85,
    "parent_netprofit_prev_yi": 91.55
  },
  "q2_outlook": {
    "verdict": "偏负",
    "confidence": "中",
    "signals": {
      "momentum": {
        "q1_single_yoy": -55.38,
        "q4_single_yoy": -38.17,
        "direction": "减速",
        "note": "Q1单季-55% 较 Q4单季-38% 进一步恶化"
      },
      "divergence": {
        "revenue_yoy": -11.82,
        "netprofit_yoy": -55.38,
        "gross_margin_chg": -1.26,
        "direction": "利润承压",
        "note": "营收-12%但净利-55%,毛利率压缩1.3pct,Q2净利仍承压"
      }
    },
    "summary": "Q1净利加速恶化+营收净利严重背离+毛利率压缩,Q2大概率延续承压。"
  },
  "data_date": "2026-04-29",
  "source": "东方财富 datacenter RPT_LICO_FN_CPD"
}
```

### 批量(`batch_query.py`)
读 `zhangting`/`chuangxingao` 等 skill 输出的 JSON(`stocks[].code`),逐只查询,输出按 `verdict`(偏正→中性→偏负)再按 `netprofit_yoy` 降序排列,存 `data/batch_<date>.json`:
```json
{
  "report_period": "2026Q1",
  "total": 120, "count": 116, "failed": 4,
  "stocks": [
    {"code":"...","name":"...","verdict":"偏正","confidence":"高",
     "netprofit_yoy":85.2,"revenue_yoy":23.1,"q2_note":"..."}
  ]
}
```

## 八、边界条件(三段式,对齐项目风格)

| 触发条件 | 一线处理 | 仍失败兜底 |
|---|---|---|
| 股票代码/名称不存在 | resolve 返回 None → "未找到该股票" | — |
| 2026Q1 尚未披露 | 多期无 2026Q1 → "该股 2026Q1 未披露",给最近一期 | — |
| 缺 2025 年报(算不出 Q4单季) | 信号A降级"数据不足",只给B,confidence→低 | — |
| 新股(无 2025Q1,算不出 Q1同比) | verdict="数据不足",列出已有数据 | — |
| 单季化异常(单季为负/单季>累计,疑似数据重述) | 标注"数据可能修订",降 confidence | — |
| 去年同期单季 \|值\|<ε | 标"基数过小,增速失真",confidence→低 | — |
| 接口请求失败 | 重试 1 次 | "数据获取失败,稍后重试" |
| 批量输入文件格式错 | 提示格式异常 + 示例 | — |

## 九、⚠️ 局限(SKILL.md 必备)

- **不预测精确数值**:只给方向(偏正/中性/偏负)+ 依据,不甩伪精确的 Q2 数字。
- **基数陷阱**:看 `parent_netprofit_prev_yi`,基数极低→增速虚高,需结合势头信号判断持续性。
- **归母未扣非**:一次性损益(补贴/资产处置)会扭曲,高增速应再看扣非(本 skill 数据源不含扣非,作提示)。
- **单季化依赖数据未重述**:若公司重述前期数据,单季化可能出现异常值,已做合理性校验并降 confidence,但仍需人工留意。
- **两信号不足时降级**:缺 Q4 基数/新股等情况,verdict 退化为"数据不足",诚实告知而非硬判。

## 十、实现与验证

- analyzer 核心纯函数(单季化、势头方向、背离方向、verdict 合成)用 TDD:先写测试再实现。
- 端到端验证:比亚迪 002594(偏负)、贵州茅台 600519;边界:不存在代码、新股(无 2025Q1)、缺 2025 年报。
- 批量验证:用一份 `zhangting` JSON 跑一批。
