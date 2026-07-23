# -*- coding: utf-8 -*-
"""维度4:国际重大事件。主源东财 7x24 快讯;财联社/金十/新华 parser 作备份。

主源(2026-07-23 probe 实测确认):东方财富 getFastNewsList JSON 直连稳定,
无签名、无需代理。showTime 字符串定时间窗,titleColor 映射重要性,sortEnd
游标翻页覆盖昨夜 18:00~今晨。parse_cls/jin10/xinhua 仍按各源公开 schema
实现字段映射(不被 fetch_news 调用),留作未来某源恢复时的备份 parser,
其逻辑由 fixture + 合成 payload test 覆盖。
"""
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pk import base
from pk.config import NEWS_KEYWORDS, POLICY_KEYWORDS

# 东财 7x24 快讯:np-listapi 直连,JSON,无签名。sortEnd 为空串取首页(最新),
# 之后取上一页最早一条的 realSort 作下一页 sortEnd,倒序翻页。
EM_URL = "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
# 东财反爬:必须带浏览器 User-Agent + 东财 Referer,否则返回 HTML 错误页(HTTP 567, 非 JSON)
EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://kuaixun.eastmoney.com/",
}
EM_PARAMS = {
    "client": "web",
    "biz": "web_724_content",
    "fastColumn": "102",
    "pageSize": "100",
    "req_trace": "panqian",
}


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


def parse_eastmoney_724(data, now=None):
    """东财 7x24 快讯:取 data.fastNewsList,时间窗(昨夜18:00~今晨)+关键词过滤。

    probe(2026-07-23)实测字段:
      showTime     — "YYYY-MM-DD HH:MM:SS" 字符串,strptime 解析为时间戳
      titleColor   — 0=普通,3=红字重要(美股三大指数/布油/菲尔兹奖等均为3),
                     2 未见但保留映射
      pinglun_Num  — 评论数(高互动也算重要)
      title/summary
    重要性映射: titleColor==3 → star=3; titleColor==2 或 pinglun_Num>50 → star=2;
              其余 star=1。
    """
    cutoff = _window_start_ts(now)
    items = (data.get("data") or {}).get("fastNewsList", []) or []
    out = []
    for it in items:
        show = it.get("showTime") or ""
        try:
            ts = datetime.strptime(show, "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        if ts < cutoff:
            continue
        title = (it.get("title") or "").strip()[:80]
        summary = it.get("summary") or ""
        if not _hit_keyword(title + " " + summary):
            continue
        color = it.get("titleColor")
        pl = it.get("pinglun_Num") or 0
        try:
            pl = int(pl)
        except (TypeError, ValueError):
            pl = 0
        if color == 3:
            star = 3
        elif color == 2 or pl > 50:
            star = 2
        else:
            star = 1
        out.append({"title": title or "(无标题)", "ts": ts,
                    "source": "东财", "star": star})
    return out


def _fetch_eastmoney_pages(now, max_pages=12):
    """东财 7x24:sortEnd 游标倒序翻页,直到最早一条 showTime < 昨夜18:00 或 max_pages。

    返回原始 fastNewsList 列表(未过滤),交 parse_eastmoney_724 二次过滤。
    首页 sortEnd="" 取最新;之后用上一页最早一条的 realSort 作游标。
    max_pages=12 × pageSize=100 = 1200 条,活跃夜间(约45条/h × 28h ≈ 1260)能
    覆盖到昨夜18:00 窗口起点;实际更早 break(earliest showTime < cutoff 即停)。
    """
    cutoff = _window_start_ts(now)
    all_items = []
    sort_end = ""
    for _ in range(max_pages):
        try:
            params = dict(EM_PARAMS)
            params["sortEnd"] = sort_end
            r = base.sess.get(EM_URL, params=params, timeout=15, headers=EM_HEADERS)
            data = r.json()
        except Exception:
            break
        page = (data.get("data") or {}).get("fastNewsList", []) or []
        if not page:
            break
        all_items.extend(page)
        # 最早一条 showTime < cutoff → 已覆盖到窗口起点,停
        earliest = page[-1].get("showTime") or ""
        try:
            if datetime.strptime(earliest, "%Y-%m-%d %H:%M:%S").timestamp() < cutoff:
                break
        except ValueError:
            break
        sort_end = page[-1].get("realSort") or ""
        if not sort_end:
            break
    return all_items


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


def fetch_news():
    """返回 FetchResult(dim='news')。data={'items':[...], 'sources_ok':[...]}。

    主源东财 7x24 快讯:sortEnd 翻页拉昨夜18:00~今晨窗口内条目,关键词过滤,
    titleColor 映射重要性,merge_top 排序去重截 topn。
    东财不可达 → ok=False,detail 提示"请手动补充",由 render 层报告底部留兜口。
    """
    now = datetime.now()
    sources_ok, all_items = [], []
    # 主源:东财 7x24 快讯
    try:
        pages = _fetch_eastmoney_pages(now)
        em_items = parse_eastmoney_724({"data": {"fastNewsList": pages}}, now)
        all_items.append(em_items)
        if em_items:
            sources_ok.append("东财")
    except Exception:
        all_items.append([])
    items = merge_top(all_items)
    ok = bool(items)
    detail = "✓" if ok else "⚠️ 新闻自动抓取失败(东财不可达),请手动补充"
    return base.FetchResult("news", ok=ok,
                            data={"items": items, "sources_ok": sources_ok},
                            detail=detail)
