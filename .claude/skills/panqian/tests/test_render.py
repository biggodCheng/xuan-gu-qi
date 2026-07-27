from pk import render


def _sample_data():
    return {
        "date_str": "2026-07-23",
        "tone": "偏冷",
        "strength": "中",
        "us": {"indices": [{"name": "纳指", "price": 18123, "pct": -1.8}], "vix": 22.0},
        "a50": {"a50": {"price": 13210, "pct": -0.6}, "cnr": [{"name": "阿里", "pct": -2.5}]},
        "fx": {"fx": [{"name": "离岸人民币", "pct": 0.2}], "comm": [{"name": "WTI原油", "pct": -2.0}]},
        "news": {"items": [{"title": "美联储FOMC偏鹰", "ts": 2, "source": "东财", "star": 3}], "sources_ok": ["东财"]},
        "quality": {"us": "✓", "a50": "✓", "cnr": "✓", "fx": "✓", "comm": "✓", "news": "✓"},
        "critical_missing": False,
        "note": "",
    }


def test_render_has_sections():
    md = render.render(_sample_data())
    assert "# 盘前外部温度计 · 2026-07-23" in md
    assert "## 0. 隔夜定调" in md
    assert "## 1. 美股隔夜" in md
    assert "## 6. 你的盘前研判" in md


def test_render_warns_not_prediction():
    md = render.render(_sample_data())
    assert "不是" in md and "涨跌" in md and "预测" in md   # 第0步护栏文案


def test_render_critical_missing_banner():
    d = _sample_data()
    d["critical_missing"] = True
    md = render.render(d)
    assert "外部信号缺失" in md


def test_render_quality_row():
    md = render.render(_sample_data())
    assert "美股✓" in md and "A50✓" in md


def test_render_a50_missing_warns():
    d = _sample_data()
    d["a50"] = {"a50": None, "cnr": []}
    md = render.render(d)
    assert "A50期货:⚠️" in md


def test_render_news_items_with_star():
    md = render.render(_sample_data())
    assert "★★★" in md            # star=3 → 三星
    assert "美联储FOMC偏鹰" in md


def test_render_vix_level_in_price_column():
    # VIX 是绝对水平(非涨跌幅);第5步历史映射用 VIX>20/>30 阈值 → level 才是关键值。
    # 故 level 应落在"收盘"列,涨跌列留 -(修前 render 误把 level 塞进涨跌列)。
    md = render.render(_sample_data())   # sample vix=22.0
    assert "| VIX | 22.0 | - |" in md
