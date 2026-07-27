from unittest.mock import patch, MagicMock
from pk import base


def test_sina_quote_parses_lines():
    fake = MagicMock()
    fake.text = 'var gb_ixic="纳斯达克,18000.00,17900,18100,17950";\nvar gb_inx="标普500,5588,5560,5600";'
    with patch("pk.base.sess.get", return_value=fake):
        out = base.sina_quote(["gb_ixic", "gb_inx"])
    assert out["gb_ixic"][0] == "纳斯达克"
    assert out["gb_inx"][0] == "标普500"


def test_sina_quote_strips_hq_str_prefix():
    # 新浪真实返回的 var 名带 hq_str_ 前缀;base 应剥掉后以 bare code 为 key,
    # 否则 fetcher 用 raw.get(bare_code) 会取空(参 config 代码常量)。
    fake = MagicMock()
    fake.text = 'var hq_str_gb_ixic="纳斯达克,18000.00,-0.5";'
    with patch("pk.base.sess.get", return_value=fake):
        out = base.sina_quote(["gb_ixic"])
    assert "gb_ixic" in out               # 剥前缀后是 bare code
    assert "hq_str_gb_ixic" not in out    # 带前缀的 key 不应残留
    assert out["gb_ixic"][0] == "纳斯达克"


def test_sina_quote_empty_payload():
    fake = MagicMock()
    fake.text = 'var gb_zzz="";'
    with patch("pk.base.sess.get", return_value=fake):
        out = base.sina_quote(["gb_zzz"])
    assert out["gb_zzz"] == []


def test_sina_quote_network_error_returns_empty():
    with patch("pk.base.sess.get", side_effect=Exception("timeout")):
        assert base.sina_quote(["gb_ixic"]) == {}


def test_fetch_result_defaults():
    r = base.FetchResult("us")
    assert r.ok is False and r.data is None and r.detail == ""


def test_proxy_get_sends_browser_user_agent():
    # Yahoo v8 chart API 拒绝 requests 默认 python-requests UA(返回 401/meta=None)。
    # 根因(2026-07-27 实测:加浏览器 UA 后 ^VIX 立即返回 regularMarketPrice):
    # proxy_get 必须默认带浏览器 UA,否则 VIX 永久缺。
    fake = MagicMock()
    fake.status_code = 200
    fake.raise_for_status = lambda: None
    with patch("pk.base.requests.get", return_value=fake) as g:
        base.proxy_get("https://x", proxy={"http": "p"})
    ua = g.call_args.kwargs["headers"]["User-Agent"]
    assert "python-requests" not in ua
    assert "Mozilla" in ua


def test_proxy_get_caller_headers_override_default():
    fake = MagicMock()
    fake.status_code = 200
    fake.raise_for_status = lambda: None
    with patch("pk.base.requests.get", return_value=fake) as g:
        base.proxy_get("https://x", proxy={"http": "p"}, headers={"User-Agent": "custom"})
    assert g.call_args.kwargs["headers"]["User-Agent"] == "custom"


def test_proxy_get_failure_returns_none():
    with patch("pk.base.requests.get", side_effect=Exception("boom")):
        assert base.proxy_get("https://x", proxy={"http": "p"}) is None
