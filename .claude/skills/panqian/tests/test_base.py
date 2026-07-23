from unittest.mock import patch, MagicMock
from pk import base


def test_sina_quote_parses_lines():
    fake = MagicMock()
    fake.text = 'var gb_ixic="纳斯达克,18000.00,17900,18100,17950";\nvar gb_inx="标普500,5588,5560,5600";'
    with patch("pk.base.sess.get", return_value=fake):
        out = base.sina_quote(["gb_ixic", "gb_inx"])
    assert out["gb_ixic"][0] == "纳斯达克"
    assert out["gb_inx"][0] == "标普500"


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
