# -*- coding: utf-8 -*-
"""维度4:国际重大事件。财联社+金十+新华财经,时间窗(昨夜18:00~今晨)+关键词过滤+去重。

probe 实测(2026-07-23):三源运行时均不可直连取数 → fetch_news 自动降级空,
detail 提示"请手动补充",由 render 层在报告底部留兜口。parser 字段映射仍按
各源公开 schema 实现,fixture + 合成 payload test 保证逻辑正确,日后某源恢复
或换可靠镜像时只需改 URL/headers 即可复用。
"""
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pk import base
from pk.config import NEWS_KEYWORDS, POLICY_KEYWORDS

# 财联社:task 给的 nodeapi URL 已下线,保留作为 documented attempt;
# 替代 endpoint(v1/v3/v5)实测均需 sign 返回 errno=10012/50101。
CLS_URL = ("https://www.cls.cn/nodeapi/updateTelegraphList?"
           "app=CailianpressWeb&category=&lastTime=&os=web&sv=7.7.5&rn=80")
CLS_HEADERS = {"Referer": "https://www.cls.cn/telegraph",
               "User-Agent": "Mozilla/5.0"}


def _window_start_ts(now=None):
    """时间窗起点:昨日 18:00(覆盖昨夜盘后 + 今晨盘前)。返回 Unix 秒时间戳。"""
    now = now or datetime.now()
    start = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    return start.timestamp()


def _hit_keyword(text):
    kw = NEWS_KEYWORDS + POLICY_KEYWORDS
    t = text or ""
    return any(k in t for k in kw)


def _extract_items(data, roll_key):
    """从各源 JSON 提取新闻条目 list,兼容三种结构:
      - {"data": {"roll_data": [...]}}  (财联社;roll_key='roll_data')
      - {"data": [...]}                  (扁平 list)
      - {"items": [...]}                 (金十/新华)
    防御非预期类型(如 data 是 dict 而非 list)→ 返回 []。
    """
    if not isinstance(data, dict):
        return []
    inner = data.get("data")
    if isinstance(inner, dict):
        if roll_key:
            got = inner.get(roll_key)
            return got if isinstance(got, list) else []
        return inner.get("items") if isinstance(inner.get("items"), list) else []
    if isinstance(inner, list):
        return inner
    items = data.get("items")
    return items if isinstance(items, list) else []


def parse_cls(data, now=None):
    """财联社电报:取 data.roll_data,过滤时间窗 + 关键词。

    字段(以公开 schema 为准;fixture 因反爬为空,逻辑由合成 payload test 覆盖):
      ctime    — Unix 秒级时间戳
      title    — 标题(纯文本)
      content  — 正文(可能含 HTML)
      level    — 重要性:"B"/2=重要 → star=3;1/"1"=较重要 → star=2;其他 → star=1
    """
    items = _extract_items(data, "roll_data")
    cutoff = _window_start_ts(now)
    out = []
    for it in items:
        ts = it.get("ctime") or it.get("time")
        if not ts:
            continue
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            continue
        if ts < cutoff:
            continue
        title = (it.get("title") or "").strip()
        content = it.get("content") or ""
        if not _hit_keyword(title + " " + content):
            continue
        level = it.get("level")
        star = 3 if level in (2, "2", "B") else (2 if level in (1, "1") else 1)
        out.append({"title": title[:80] or "(无标题)",
                    "ts": ts, "source": "财联社", "star": star})
    return out


def parse_jin10(data, now=None):
    """金十财经日历:取星级>=2 且命中关键词的事件。

    字段(公开 schema):
      star/importance — 0~3 级
      title/event     — 事件名
      time/date       — 时间(数值则按 Unix 秒过滤,字符串则放过由人工研判)
    """
    cutoff = _window_start_ts(now)
    out = []
    for it in _extract_items(data, None):
        star = it.get("star") or it.get("importance") or 0
        try:
            star = int(star)
        except (TypeError, ValueError):
            star = 0
        if star < 2:
            continue
        title = (it.get("title") or it.get("event") or "").strip()
        if not _hit_keyword(title):
            continue
        ts = it.get("time") or it.get("date") or 0
        if isinstance(ts, (int, float)) and ts < cutoff:
            continue
        out.append({"title": title[:80] or "(无标题)",
                    "ts": ts if isinstance(ts, (int, float)) else 0,
                    "source": "金十", "star": star})
    return out


def parse_xinhua(data, now=None):
    """新华财经:政策/宏观类,按 POLICY_KEYWORDS 过滤标题。

    字段(公开 schema):title / time / ctime。新华 RSS 实测无 pubDate,
    运行时数据不可用 → fixture 空该路径仅做 schema 兜底。
    """
    cutoff = _window_start_ts(now)
    out = []
    for it in _extract_items(data, None):
        title = (it.get("title") or "").strip()
        if not any(k in title for k in POLICY_KEYWORDS):
            continue
        ts = it.get("time") or it.get("ctime") or 0
        if isinstance(ts, (int, float)) and ts < cutoff:
            continue
        out.append({"title": title[:80] or "(无标题)",
                    "ts": ts if isinstance(ts, (int, float)) else 0,
                    "source": "新华", "star": 2})
    return out


def _similar(a, b):
    """标题相似度去重:SequenceMatcher > 0.6 视为同一事件。"""
    return SequenceMatcher(None, a, b).ratio() > 0.6


def merge_top(sources, topn=6):
    """多源合并:按 (star desc, ts desc) 排序后相似去重,截 topn。"""
    pool = [it for src in sources for it in src]
    pool.sort(key=lambda x: (-x.get("star", 0), -x.get("ts", 0)))
    merged = []
    for it in pool:
        if any(_similar(it["title"], m["title"]) for m in merged):
            continue
        merged.append(it)
        if len(merged) >= topn:
            break
    return merged


def _safe_fetch(name):
    """金十/新华运行时抓取:据 probe 结果填具体请求;无可靠 API 则返回 {}。

    probe(2026-07-23):两源均不可达(金十 sign / 新华 RSS 无 pubDate),返回 {}
    触发 parser 空列表降级。若日后发现可靠镜像,在此填 name → (url, headers, parser)。
    """
    return {}


def fetch_news():
    """返回 FetchResult(dim='news')。data={'items':[...], 'sources_ok':[...]}。

    三源全失败 → ok=False,detail "⚠️ 新闻自动抓取失败(三源均无),请手动补充"。
    部分源成功 → 合并可用项,ok=bool(items)。
    """
    now = datetime.now()
    sources_ok, all_items = [], []
    # 财联社:直连尝试
    try:
        r = base.sess.get(CLS_URL, timeout=15, headers=CLS_HEADERS)
        cls_items = parse_cls(r.json(), now)
        all_items.append(cls_items)
        if cls_items:
            sources_ok.append("财联社")
    except Exception:
        all_items.append([])
    # 金十/新华:经 _safe_fetch(目前返回 {})
    for parser, name in [(parse_jin10, "金十"), (parse_xinhua, "新华")]:
        try:
            data = _safe_fetch(name)
            items = parser(data, now)
            all_items.append(items)
            if data and items:
                sources_ok.append(name)
        except Exception:
            all_items.append([])
    items = merge_top(all_items)
    ok = bool(items)
    detail = "✓" if ok else "⚠️ 新闻自动抓取失败(三源均无),请手动补充"
    return base.FetchResult("news", ok=ok,
                            data={"items": items, "sources_ok": sources_ok},
                            detail=detail)
