---
name: zhongbaoyubao
description: 中报预报跟踪器 — 扫描A股中报业绩预告(预增且同比下限≥50%),以公告次日开盘为基准,跟踪30交易日累计涨跌,每日生成markdown报告。当用户说"中报预报"、"中报预增"、"业绩预告大增"、"预报跟踪"、"预告大涨跟踪"、"zhongbaoyubao"时触发。
---

# 中报预报跟踪器

跟踪中报预告"大幅预增"公司的**披露后股价反应**(事件跟踪,非买卖建议)。

## 它解决什么问题

中报预告季(7月)密集披露"大幅预增"。本 skill 回答:**这些预增股,预告披露后股价到底是涨是跌?** 每次执行扫描最新预增入池,以公告次日开盘为基准,持续跟踪 30 个交易日的累计涨跌。

## 使用方式

输入 `/zhongbaoyubao` 触发。每日执行:扫描新预增预告入池 → 刷新跟踪池累计涨跌 → 生成报告。

## 执行步骤

1. 🔴 CHECKPOINT(运行前检查今日报告是否已存在):
   ```bash
   ls .claude/skills/zhongbaoyubao/output/$(date +%Y-%m-%d).md 2>/dev/null
   ```
   - 已存在 → 🛑 STOP,提示"今日报告已生成,重跑会重新刷新行情并覆盖",询问确认后再继续。
   - 不存在 → 继续。

2. 确认依赖:
   ```bash
   cd .claude/skills/zhongbaoyubao && pip install -r requirements.txt
   ```

3. 运行:
   ```bash
   cd .claude/skills/zhongbaoyubao && PYTHONUTF8=1 python main.py
   ```

4. 脚本会:扫描全A中报业绩预告(预增,同比下限≥50%) → 新股入池(取公告次日开盘为基准价) → 并发刷新池内活跃股前复权日K → 算累计/当日涨跌 → 满30交易日迁出 → skipped 重试 → 生成 `output/<date>.md` → 写回 `data/watchlist.json`。

5. 读取 `output/<date>.md` 向用户展示:今日新增、活跃跟踪(按累计涨跌排序)、今日到期、涨跌分布。

## 实测字段(经 probe_yjyg.py 确认,2026-07-02)

> 首次实现或接口变动时运行 `PYTHONUTF8=1 python probe_yjyg.py` 重新核对,改 `screener/fetcher.py` 顶部 `FLD_*` / `YJYG_REPORT_NAME` 常量。

- reportName = `RPT_PUBLIC_OP_PREDICT`(旧的 RPT_LICO_FN_CPD_GD 已不可用,success=False)
- 代码 `SECURITY_CODE` / 名称 `SECURITY_NAME_ABBR` / 行业 `PUBLISHNAME`
- 公告日 `NOTICE_DATE`(截 `[:10]`) / 报告期 `REPORTDATE`
- 预告类型 `FORECASTTYPE`(值"预增"/"预减"/"扭亏"/"续盈"…)
- 同比变动下限/上限 `INCREASEL` / `INCREASET`(%)
- 预测净利润下限/上限 `FORECASTL` / `FORECASTT`(元)
- filter 用 `(REPORTDATE='2026-06-30')` 有效,返回含所有类型,代码内按 FORECASTTYPE 过滤

## 关键参数

| 项 | 值 | 改动位置 |
|---|---|---|
| 预告类型 | 预增 | `analyzer.PREDICT_TYPE` |
| 同比下限阈值 | 50% | `analyzer.YOY_LOWER_MIN` |
| 跟踪交易日 | 30 | `analyzer.HOLD_DAYS` |
| 基准价 | 公告次日开盘(前复权) | `fetcher.get_kline_since` |
| 报告期 | 2026-06-30(中报) | `storage.REPORT_DATE` |

## 数据流

- `data/watchlist.json` 跨天持久化跟踪池:active(跟踪中) / expired(已到期) / skipped(入池失败待重试)。
- 基准价与当前价同取自一条腾讯前复权日K序列(避免除权失真)。
- daily 系列每次执行覆盖式刷新(前复权口径自洽),末条即今日。
- `output/<date>.md` 每日报告。

## 边界条件

| 触发 | 处理 |
|---|---|
| 非交易日执行 | 仍扫预告(公告非行情);当前价=最近交易日收盘,末条非今日 |
| 公告次日停牌 | 基准日顺延到复牌后首个有行情日 |
| K线拉取失败(腾讯偶发空响应) | 入 skipped,下次执行移回 active 重试 |
| 腾讯日K连接异常 | 必须直连禁代理(NO_PROXY=*、trust_env=False),走代理会被关连接 |
| 业绩预告接口异常 | 本次不新增,提示稍后重试 |
| watchlist.json 损坏 | 备份为 `*.bad` 后重建空池 |
| 跨报告期 | report_date 写死 2026-06-30,只扫中报 |

## ❌ 不要做

| 不要 | 原因 | 正确做法 |
|---|---|---|
| 把"预增"当买卖建议 | 预告≠兑现,利好出尽或下跌 | 只跟踪涨跌读数 |
| 用入池 1 天的单点涨跌下结论 | 噪声大 | 看 held_days≥5 的读数 |
| 用不复权价配前复权基准价 | 除权失真 | 基准与当前同取一条前复权序列 |
| 逐个串行刷新全池 | 慢 | 用 20 线程并发 |
| 忽略 CHECKPOINT 直接覆盖今日报告 | 重跑浪费时间 | 先询问 |

## 局限

- 预告是公司**指引**,非实际数;正式中报(8月底前)可能修订。
- 绝对涨跌,**未剔除大盘/行业 beta**(同期普涨/普跌会失真)。
- 仅归母口径,预增可能含一次性损益。
- 跟踪窗口 30 交易日是经验值,不保证覆盖完整"利好兑现/出尽"周期。
