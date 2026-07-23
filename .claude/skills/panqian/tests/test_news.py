# -*- coding: utf-8 -*-
"""维度4(国际重大事件)parser/merge/fetch 测试。

主源东财 7x24 快讯(2026-07-23 probe 实测确认直连稳定):
- getFastNewsList 返回 data.fastNewsList,字段 showTime/titleColor/pinglun_Num。
- parse_eastmoney_724:showTime strptime 定时间窗,titleColor 映射 star。

财联社/金十/新华 parser 保留作备份(不被 fetch_news 调用),其字段映射逻辑仍由
合成 payload test 覆盖,fixture 存空/真实结构 + _comment 说明。
"""
import os, json, time
from datetime import datetime, timedelta
from pk import news

FX = os.path.dirname(__file__)


def _load(p):
    with open(os.path.join(FX, "fixtures", p), encoding="utf-8") as f:
        return json.load(f)


# --- fixture-based:parser 对真实(空)fixture 必须稳返 list ---
def test_parse_cls_on_empty_fixture_returns_list():
    items = news.parse_cls(_load("cls_news.json"))
    assert isinstance(items, list)
    assert items == []


def test_parse_jin10_on_empty_fixture_returns_list():
    items = news.parse_jin10(_load("jin10_calendar.json"))
    assert items == []


def test_parse_xinhua_on_empty_fixture_returns_list():
    items = news.parse_xinhua(_load("xinhua_news.json"))
    assert items == []


# --- 时间窗过滤 ---
def test_parse_cls_filters_by_time_window():
    now = datetime.now()
    recent_ts = int(now.timestamp()) - 60                    # 1 分钟前
    old_ts = int((now - timedelta(days=2)).timestamp())      # 2 天前
    data = {"data": {"roll_data": [
        {"title": "美联储加息75基点", "ctime": recent_ts, "content": "", "level": "B"},
        {"title": "美联储旧闻", "ctime": old_ts, "content": "", "level": "B"},
    ]}}
    items = news.parse_cls(data, now=now)
    titles = [it["title"] for it in items]
    assert "美联储加息75基点" in titles
    assert "美联储旧闻" not in titles


def test_time_window_filters_old_news():
    old = {"data": {"roll_data": [{"title": "旧闻无关", "ctime": 1000000000, "content": ""}]}}
    assert news.parse_cls(old) == []


# --- 关键词过滤 ---
def test_parse_cls_filters_by_keyword():
    now = datetime.now()
    recent_ts = int(now.timestamp())
    data = {"data": {"roll_data": [
        {"title": "美联储宣布加息", "ctime": recent_ts, "content": ""},
        {"title": "今日天气晴朗", "ctime": recent_ts, "content": ""},
        {"title": "某公司发布财报", "ctime": recent_ts, "content": ""},
    ]}}
    items = news.parse_cls(data, now=now)
    titles = sorted(it["title"] for it in items)
    assert titles == ["某公司发布财报", "美联储宣布加息"]


# --- 字段映射:ctime/title/content/level → ts/title/star ---
def test_parse_cls_level_mapping():
    now = datetime.now()
    ts = int(now.timestamp())
    data = {"data": {"roll_data": [
        {"title": "美联储加息", "ctime": ts, "content": "", "level": "B"},   # 重要 → star=3
        {"title": "美联储降息", "ctime": ts, "content": "", "level": 1},     # star=2
        {"title": "央行发声", "ctime": ts, "content": "", "level": None},    # star=1
    ]}}
    items = news.parse_cls(data, now=now)
    by_title = {it["title"]: it["star"] for it in items}
    assert by_title["美联储加息"] == 3
    assert by_title["美联储降息"] == 2
    assert by_title["央行发声"] == 1


def test_parse_cls_item_shape():
    now = datetime.now()
    ts = int(now.timestamp())
    data = {"data": {"roll_data": [
        {"title": "美联储加息", "ctime": ts, "content": "", "level": "B"},
    ]}}
    items = news.parse_cls(data, now=now)
    assert len(items) == 1
    it = items[0]
    assert set(it.keys()) >= {"title", "ts", "source", "star"}
    assert it["ts"] == ts
    assert it["source"] == "财联社"


# --- merge_top:排序 + 去重 + topn ---
def test_merge_dedup_topn():
    a = [{"title": "美联储加息75基点", "ts": 2, "source": "财联社", "star": 3}]
    b = [{"title": "美联储宣布加息75个基点", "ts": 2, "source": "金十", "star": 3}]
    merged = news.merge_top([a, b], topn=5)
    assert len(merged) == 1   # 标题相似→去重


def test_merge_top_sorts_by_star_then_ts():
    # 标题须足够不同,否则会被 >0.6 相似度去重
    pool_a = [{"title": "欧央行维持利率不变", "ts": 1, "source": "财联社", "star": 1}]
    pool_b = [{"title": "美联储宣布加息75基点", "ts": 9, "source": "金十", "star": 3},
              {"title": "日本央行利率决议公布", "ts": 1, "source": "金十", "star": 3}]
    merged = news.merge_top([pool_a, pool_b], topn=5)
    assert merged[0]["title"] == "美联储宣布加息75基点"
    assert merged[1]["title"] == "日本央行利率决议公布"
    assert merged[2]["title"] == "欧央行维持利率不变"


def test_merge_top_respects_topn_limit():
    # 标题需互不相似,否则被去重;用截然不同的事件
    titles = [
        "美联储加息75基点", "欧央行维持利率不变", "日本央行决议公布",
        "英国央行跟进加息", "澳洲央行按兵不动", "加拿大央行降息",
        "新西兰央行缩表", "瑞士央行干预汇率", "中国央行开展逆回购",
        "印度央行调整政策",
    ]
    pool = [{"title": t, "ts": i, "source": "财联社", "star": 3} for i, t in enumerate(titles)]
    merged = news.merge_top([pool], topn=3)
    assert len(merged) == 3


def test_merge_top_handles_empty_sources():
    assert news.merge_top([[], [], []]) == []
    assert news.merge_top([]) == []


# --- 金十/新华 parser 合成字段 ---
def test_parse_jin10_filters_by_star_and_keyword():
    now = datetime.now()
    ts = int(now.timestamp())
    data = {"items": [
        {"title": "美联储利率决议", "star": 3, "time": ts},
        {"title": "美联储小事件", "star": 1, "time": ts},          # star<2 过滤
        {"title": "某地今日天气晴朗", "star": 3, "time": ts},      # 无关键词
    ]}
    items = news.parse_jin10(data, now=now)
    titles = [it["title"] for it in items]
    assert "美联储利率决议" in titles
    assert "美联储小事件" not in titles
    assert "某地今日天气晴朗" not in titles


def test_parse_xinhua_filters_by_policy_keyword():
    now = datetime.now()
    ts = int(now.timestamp())
    data = {"items": [
        {"title": "国务院发布新一轮政策", "time": ts},
        {"title": "某地天气持续晴好", "time": ts},
        {"title": "央行开展逆回购操作", "time": ts},
    ]}
    items = news.parse_xinhua(data, now=now)
    titles = sorted(it["title"] for it in items)
    assert titles == ["国务院发布新一轮政策", "央行开展逆回购操作"]


# --- 东财 7x24 parse_eastmoney_724 ---
def test_parse_eastmoney_on_real_fixture_with_fresh_window():
    """真实 fixture:用最早 showTime 推导 now 使窗口覆盖全部条目,
    验证 showTime strptime 解析、titleColor→star 映射、字段 shape 永久成立。"""
    fx = _load("eastmoney_724.json")
    items_raw = fx["data"]["fastNewsList"]
    # now 取最早 showTime + 1h,使昨夜18:00 窗口起点早于全部条目
    earliest = min(it["showTime"] for it in items_raw)
    now = datetime.strptime(earliest, "%Y-%m-%d %H:%M:%S") + timedelta(hours=1)
    parsed = news.parse_eastmoney_724(fx, now=now)
    # fixture 含 5 条 color=3 + 10 条 color=0;关键词过滤后保留命中 NEWS/POLICY 的
    assert isinstance(parsed, list)
    assert len(parsed) >= 3
    # 美股/布油/黄金等隔夜市场信号(关键词已补齐)应保留且 color=3 → star=3
    by_title = {it["title"]: it for it in parsed}
    assert "美股三大指数集体低开 特斯拉跌超8%、谷歌跌超6%" in by_title
    assert by_title["美股三大指数集体低开 特斯拉跌超8%、谷歌跌超6%"]["star"] == 3
    # 每条 shape + source + showTime 已解析为 float 时间戳
    for it in parsed:
        assert set(it.keys()) >= {"title", "ts", "source", "star"}
        assert it["source"] == "东财"
        assert isinstance(it["ts"], float)


def test_parse_eastmoney_filters_by_time_window():
    """showTime < 昨夜18:00 的条目丢弃。"""
    now = datetime.now()
    recent = now.strftime("%Y-%m-%d %H:%M:%S")
    old = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    data = {"data": {"fastNewsList": [
        {"title": "美联储加息", "summary": "", "showTime": recent, "titleColor": 3, "pinglun_Num": 0},
        {"title": "美联储旧闻", "summary": "", "showTime": old, "titleColor": 3, "pinglun_Num": 0},
    ]}}
    items = news.parse_eastmoney_724(data, now=now)
    titles = [it["title"] for it in items]
    assert "美联储加息" in titles
    assert "美联储旧闻" not in titles


def test_parse_eastmoney_filters_by_keyword():
    """未命中 NEWS_KEYWORDS/POLICY_KEYWORDS 的条目丢弃。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")
    data = {"data": {"fastNewsList": [
        {"title": "美联储宣布加息", "summary": "", "showTime": show, "titleColor": 0, "pinglun_Num": 0},
        {"title": "今日天气晴朗", "summary": "", "showTime": show, "titleColor": 0, "pinglun_Num": 0},
        {"title": "某地举办运动会", "summary": "", "showTime": show, "titleColor": 0, "pinglun_Num": 0},
    ]}}
    items = news.parse_eastmoney_724(data, now=now)
    titles = [it["title"] for it in items]
    assert titles == ["美联储宣布加息"]


def test_parse_eastmoney_keyword_hits_summary():
    """标题无关键词但 summary 命中(如"央行")也保留。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")
    data = {"data": {"fastNewsList": [
        {"title": "某地公布经济数据", "summary": "央行开展逆回购操作", "showTime": show, "titleColor": 0, "pinglun_Num": 0},
    ]}}
    items = news.parse_eastmoney_724(data, now=now)
    assert len(items) == 1
    assert items[0]["title"] == "某地公布经济数据"


def test_parse_eastmoney_star_mapping():
    """titleColor=3→star3;color=2→star2;pinglun_Num>50→star2;其余→star1。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")
    data = {"data": {"fastNewsList": [
        {"title": "美联储加息A", "summary": "", "showTime": show, "titleColor": 3, "pinglun_Num": 0},
        {"title": "美联储加息B", "summary": "", "showTime": show, "titleColor": 2, "pinglun_Num": 0},
        {"title": "美联储加息C", "summary": "", "showTime": show, "titleColor": 0, "pinglun_Num": 80},
        {"title": "美联储加息D", "summary": "", "showTime": show, "titleColor": 0, "pinglun_Num": 5},
    ]}}
    by_title = {it["title"]: it["star"] for it in news.parse_eastmoney_724(data, now=now)}
    assert by_title["美联储加息A"] == 3
    assert by_title["美联储加息B"] == 2
    assert by_title["美联储加息C"] == 2
    assert by_title["美联储加息D"] == 1


def test_parse_eastmoney_skips_bad_showtime():
    """showTime 格式异常 → 跳过该条不抛。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")
    data = {"data": {"fastNewsList": [
        {"title": "美联储加息", "summary": "", "showTime": show, "titleColor": 3, "pinglun_Num": 0},
        {"title": "坏时间", "summary": "", "showTime": "not-a-date", "titleColor": 3, "pinglun_Num": 0},
        {"title": "空时间", "summary": "", "showTime": "", "titleColor": 3, "pinglun_Num": 0},
    ]}}
    items = news.parse_eastmoney_724(data, now=now)
    titles = [it["title"] for it in items]
    assert titles == ["美联储加息"]


def test_parse_eastmoney_handles_empty_and_malformed():
    """空/缺字段结构不抛,返回 []。"""
    assert news.parse_eastmoney_724({}) == []
    assert news.parse_eastmoney_724({"data": None}) == []
    assert news.parse_eastmoney_724({"data": {}}) == []
    assert news.parse_eastmoney_724({"data": {"fastNewsList": None}}) == []


# --- _fetch_eastmoney_pages 翻页控制 ---
def _em_resp(items):
    class FakeResp:
        def json(self):
            return {"data": {"fastNewsList": items}}
    return FakeResp()


def test_fetch_pages_stops_when_window_covered(monkeypatch):
    """最早一条 showTime < 昨夜18:00 → 已覆盖窗口,停(只拉 1 页)。"""
    now = datetime.now()
    recent = now.strftime("%Y-%m-%d %H:%M:%S")
    old = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    page = [
        {"title": "新", "showTime": recent, "realSort": "9"},
        {"title": "旧", "showTime": old, "realSort": "1"},   # < cutoff → 停
    ]
    calls = []
    def fake_get(*a, **kw):
        calls.append(kw.get("params", {}).get("sortEnd"))
        return _em_resp(page)
    monkeypatch.setattr(news.base.sess, "get", fake_get)
    out = news._fetch_eastmoney_pages(now)
    assert len(calls) == 1                    # 第 1 页就因 old < cutoff 停
    assert len(out) == 2


def test_fetch_pages_respects_max_pages(monkeypatch):
    """全部在窗口内且 realSort 持续返回 → 受 max_pages 截断,不无限翻。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")
    page = [{"title": "x", "showTime": show, "realSort": "1"}]
    monkeypatch.setattr(news.base.sess, "get", lambda *a, **kw: _em_resp(page))
    out = news._fetch_eastmoney_pages(now, max_pages=3)
    assert len(out) == 3                      # 3 页 × 1 条


def test_fetch_pages_stops_on_empty_page(monkeypatch):
    """空页(无 fastNewsList)→ 停。"""
    monkeypatch.setattr(news.base.sess, "get", lambda *a, **kw: _em_resp([]))
    assert news._fetch_eastmoney_pages(datetime.now()) == []


def test_fetch_pages_stops_when_realsort_missing(monkeypatch):
    """窗口未覆盖但 realSort 缺失 → 无法翻页,停。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")
    page = [{"title": "x", "showTime": show, "realSort": ""}]   # realSort 空
    monkeypatch.setattr(news.base.sess, "get", lambda *a, **kw: _em_resp(page))
    out = news._fetch_eastmoney_pages(now)
    assert len(out) == 1


def test_fetch_pages_breaks_on_request_error(monkeypatch):
    """请求异常 → break,返回已拉到的条目。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")
    page = [{"title": "x", "showTime": show, "realSort": "1"}]
    calls = {"n": 0}
    def fake_get(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _em_resp(page)
        raise RuntimeError("net err")
    monkeypatch.setattr(news.base.sess, "get", fake_get)
    out = news._fetch_eastmoney_pages(now, max_pages=5)
    assert len(out) == 1                      # 第 1 页成功,第 2 页异常 → 停


# --- fetch_news 端到端:东财为主源 ---
def test_fetch_news_degrades_when_eastmoney_unreachable(monkeypatch):
    """东财不可达 → ok=False + "请手动补充" 兜口。"""
    def fake_get(*a, **kw):
        raise RuntimeError("simulated eastmoney unreachable")
    monkeypatch.setattr(news.base.sess, "get", fake_get)
    result = news.fetch_news()
    assert result.dim == "news"
    assert result.ok is False
    assert "请手动补充" in result.detail
    assert result.data["items"] == []
    assert result.data["sources_ok"] == []


def test_fetch_news_ok_when_eastmoney_returns(monkeypatch):
    """东财返回窗口内、命中关键词的条目 → ok=True,sources_ok=['东财']。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")   # 当下,必在窗口内

    class FakeResp:
        def json(self):
            return {"data": {"fastNewsList": [
                {"title": "美联储加息75基点", "summary": "", "showTime": show,
                 "titleColor": 3, "pinglun_Num": 10, "realSort": "1"},
                {"title": "今日天气晴朗", "summary": "", "showTime": show,   # 无关键词
                 "titleColor": 0, "pinglun_Num": 0, "realSort": "2"},
            ]}}

    monkeypatch.setattr(news.base.sess, "get", lambda *a, **kw: FakeResp())
    result = news.fetch_news()
    assert result.ok is True
    assert result.data["sources_ok"] == ["东财"]
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["title"] == "美联储加息75基点"
    assert result.data["items"][0]["star"] == 3


def test_fetch_news_sources_ok_empty_when_eastmoney_parses_none(monkeypatch):
    """东财返回数据但 parser 过滤后为空(无关键词命中) → sources_ok 不含东财。"""
    now = datetime.now()
    show = now.strftime("%Y-%m-%d %H:%M:%S")

    class FakeResp:
        def json(self):
            return {"data": {"fastNewsList": [
                {"title": "今日天气晴朗", "summary": "", "showTime": show,
                 "titleColor": 0, "pinglun_Num": 0, "realSort": "1"},
            ]}}

    monkeypatch.setattr(news.base.sess, "get", lambda *a, **kw: FakeResp())
    result = news.fetch_news()
    # 解析出空 → 不计 sources_ok,ok=False
    assert result.data["sources_ok"] == []
    assert result.ok is False
