# qsht-agent 设计文档

**日期:** 2026-05-26
**状态:** 已批准

## 概述

qsht-agent 是一个选股流水线 Agent，编排 4 个现有 skill，按顺序筛选股票，最终输出 markdown 报告。

## 管道流程

```
chuangxingao → shizhi → zhangting → suolianghuicai → markdown
   (创新高)     (市值)     (涨停)      (缩量回踩)
```

**用户指定的顺序：** 先创新高，再按市值过滤（去掉大盘股），再找涨停，再找缩量回踩。市值过滤前置可以减少后续步骤需要获取 K 线的股票数量，提高效率。

## 参数

所有参数使用默认值，不写死可配置入口：
- shizhi 市值阈值: 200 亿
- suolianghuicai 策略: 1（连续缩量+价格回落）
- suolianghuicai shrink_ratio: 0.8
- suolianghuicai min_days: 2

## 文件结构

```
.claude/skills/qsht-agent/
├── SKILL.md       # 技能描述、触发词、运行指令
└── main.py        # 管道编排脚本
```

## 技术方案

### subprocess 隔离调用

通过 subprocess 调用各 skill 的 `main.py`，而非直接 import。原因：
- 各 skill 有独立的 `screener/` 子包，直接 import 会产生命名冲突
- 无需修改任何现有 skill
- 每个 skill 作为独立进程运行，故障隔离

### 数据流与文件路径

| 步骤 | 命令 | 输出文件 |
|------|------|---------|
| 1 | `python chuangxingao/main.py` | `chuangxingao/data/{date}.json` |
| 2 | `python shizhi/main.py {step1_output}` | `shizhi/data/sz_{date}.json` |
| 3 | `python zhangting/main.py {step2_output}` | `shizhi/data/zt_{date}.json` |
| 4 | `python suolianghuicai/main.py {step3_output} --strategy 1` | `shizhi/data/slhc_{date}.json` |
| 5 | 读取最终 JSON → 生成 markdown | `qsht-agent/output/{date}.md` |

说明：
- shizhi 的 output_dir 硬编码为 `shizhi/data/`
- zhangting 和 suolianghuicai 的 output_dir = `os.path.dirname(json_path)`
- 因此步骤 3、4 的输出都在 `shizhi/data/` 目录下
- 管道脚本通过日期字符串预测所有中间文件路径

### 错误处理

- subprocess 返回非零退出码 → 打印 stderr 并终止管道
- 步骤间检查输出文件是否存在
- 非交易日（chuangxingao 无数据）→ 打印提示并退出

## 输出格式

Markdown 报告保存到 `qsht-agent/output/{date}.md`：

```markdown
# 选股报告 - 2026-05-26

## 筛选流水线
1. 创新高：245 只
2. 市值<200亿：120 只
3. 近期涨停：35 只
4. 缩量回踩：12 只

## 筛选结果
| 股票名称 | 股票代码 | 当前价格 |
|---------|---------|---------|
| 法拉电子 | 600563 | 174.20 |
```

表格字段：股票名称、股票代码、当前价格。不含所属板块。

## SKILL.md 设计

- **触发词：** "选股"、"筛选股票"、"qsht"、"缩量回踩选股"、"完整选股"
- **运行指令：** `python main.py`
- **输出：** 告知 Claude 读取生成的 markdown 文件并展示给用户

## 关键文件

需要创建：
- `.claude/skills/qsht-agent/SKILL.md`
- `.claude/skills/qsht-agent/main.py`

依赖的现有文件（只读）：
- `.claude/skills/chuangxingao/main.py`
- `.claude/skills/shizhi/main.py`
- `.claude/skills/zhangting/main.py`
- `.claude/skills/suolianghuicai/main.py`

## 验证方案

1. 运行 `python .claude/skills/qsht-agent/main.py`
2. 检查每步输出文件是否生成
3. 检查最终 `qsht-agent/output/{date}.md` 内容是否正确
4. 非交易日运行应提示无数据
