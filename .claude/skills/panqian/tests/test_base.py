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
