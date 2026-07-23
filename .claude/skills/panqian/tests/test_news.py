# -*- coding: utf-8 -*-
"""维度4(国际重大事件)parser/merge/fetch 测试。

probe 实测(2026-07-23):
- 财联社:nodeapi/updateTelegraphList 已下线(404);替代 endpoint v1/v3/v5 全部
  返回 errno=10012(签名错误)或 50101。反爬升级后需 sign,不可硬冲。
- 金十:反爬强,数据 API 需 sign,直连不可达。
- 新华:RSS 可达但 item 无 pubDate,时间窗无法过滤,视同不可用。
三源运行时均降级空,fetch_news ok=False。fixture 存空结构 + _comment 说明,
parser 必须正确处理空 fixture 返回 []。字段映射逻辑由 inline 合成 payload 覆盖。
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
        {"title": "美国初请失业金", "star": 3, "time": ts},        # 无关键词
    ]}
    items = news.parse_jin10(data, now=now)
    titles = [it["title"] for it in items]
    assert "美联储利率决议" in titles
    assert "美联储小事件" not in titles
    assert "美国初请失业金" not in titles


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


# --- fetch_news 端到端:三源全降级时返回 ok=False + 兜口文案 ---
def test_fetch_news_degrades_when_all_sources_empty(monkeypatch):
    # 强制 _safe_fetch 返回空(已经是默认),且 CLS_URL 也失败
    def fake_get(*a, **kw):
        raise RuntimeError("simulated cls unreachable")
    monkeypatch.setattr(news.base.sess, "get", fake_get)
    result = news.fetch_news()
    assert result.dim == "news"
    assert result.ok is False
    assert "请手动补充" in result.detail
    assert result.data["items"] == []
    assert result.data["sources_ok"] == []


def test_fetch_news_ok_when_cls_returns(monkeypatch):
    now = datetime.now()
    ts = int(now.timestamp())

    class FakeResp:
        def json(self):
            return {"data": {"roll_data": [
                {"title": "美联储加息", "ctime": ts, "content": "", "level": "B"},
            ]}}

    monkeypatch.setattr(news.base.sess, "get", lambda *a, **kw: FakeResp())
    result = news.fetch_news()
    assert result.ok is True
    assert result.data["sources_ok"] == ["财联社"]
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["title"] == "美联储加息"


def test_sources_ok_only_when_items_parsed(monkeypatch):
    """回归测试: sources_ok 仅计入真正解析出条目的源。

    即使 _safe_fetch 返回非空 dict(data 为真),若 parser 返回 [],
    该源也不应计入 sources_ok。此 bug 原先的条件为 if data and items:
    导致 data 非空但 parsed 为空时仍将源加入 sources_ok。
    """
    # 模拟 _safe_fetch 返回非空 dict,但 parser 返回 [] (无有效条目)
    monkeypatch.setattr(news, "_safe_fetch", lambda name: {"items": []})

    # 模拟 CLS_URL 也失败
    def fake_get(*a, **kw):
        raise RuntimeError("simulated cls unreachable")
    monkeypatch.setattr(news.base.sess, "get", fake_get)

    result = news.fetch_news()

    # 金十/新华 虽 _safe_fetch 返回非空,但 parser 返回 [] → 不应在 sources_ok
    assert "金十" not in result.data["sources_ok"]
    assert "新华" not in result.data["sources_ok"]
    assert result.data["sources_ok"] == []
