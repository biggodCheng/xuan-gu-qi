"""将股票的行业和概念板块与四大赛道进行匹配。

匹配逻辑：
1. 将股票的行业和所有概念板块与四大赛道的关键词库进行匹配
2. 记录每个赛道匹配到的关键词
3. 根据匹配到的子分类判断置信度
4. 如果涉及多个赛道，生成跨赛道关联说明
"""

from .tracks import TRACKS, CROSS_TRACK_NOTES


def match_tracks(industry: str, concepts: list[str]) -> list[dict]:
    """将股票的行业和概念与四大赛道进行匹配。

    Args:
        industry: 申万行业名称，如 "汽车整车"
        concepts: 概念板块列表，如 ["新能源车", "锂电池", "储能"]

    Returns:
        匹配到的赛道列表，按匹配度排序：
        [
            {
                "track": "大工业",
                "matched_keywords": ["汽车", "新能源车", "汽车零部件"],
                "matched_from": {"industry": ["汽车"], "concepts": ["新能源车"]},
                "sub_categories": ["汽车整车", "三电系统"],
                "confidence": "高",
                "score": 6,
            },
            ...
        ]
    """
    # 合并所有需要匹配的标签
    all_labels = []
    if industry:
        all_labels.append(("industry", industry))
    for c in concepts:
        all_labels.append(("concept", c))

    results = []

    for track_def in TRACKS:
        track_name = track_def["name"]
        keywords = track_def["keywords"]
        sub_categories = track_def["sub_categories"]

        matched_keywords = set()
        matched_from = {"industry": [], "concepts": []}
        matched_sub_cats = set()
        score = 0

        for source, label in all_labels:
            # 检查关键词是否出现在标签中（双向匹配）
            for kw in keywords:
                if kw in label or label in kw:
                    if kw not in matched_keywords:
                        matched_keywords.add(kw)
                        score += 1
                    if source == "industry":
                        if label not in matched_from["industry"]:
                            matched_from["industry"].append(label)
                    else:
                        if label not in matched_from["concepts"]:
                            matched_from["concepts"].append(label)

            # 检查子分类匹配
            for sub_cat_name, sub_cat_kws in sub_categories.items():
                for sub_kw in sub_cat_kws:
                    if sub_kw in label or label in sub_kw:
                        matched_sub_cats.add(sub_cat_name)

        if matched_keywords:
            # 计算置信度
            confidence = _calc_confidence(
                matched_keywords, matched_from, matched_sub_cats
            )
            results.append({
                "track": track_name,
                "matched_keywords": sorted(matched_keywords),
                "matched_from": matched_from,
                "sub_categories": sorted(matched_sub_cats),
                "confidence": confidence,
                "score": score,
            })

    # 按分数降序排序
    results.sort(key=lambda x: x["score"], reverse=True)

    return results


def _calc_confidence(
    matched_keywords: set,
    matched_from: dict,
    matched_sub_cats: set,
) -> str:
    """根据匹配情况计算置信度。

    规则：
    - 行业直接命中 + 概念命中 → 高
    - 匹配到 3+ 个概念关键词 → 高
    - 匹配到 2 个概念关键词 → 中
    - 匹配到 1 个概念关键词 → 低
    - 匹配到子分类 → 提升置信度
    """
    industry_hits = len(matched_from.get("industry", []))
    concept_hits = len(matched_from.get("concepts", []))
    sub_cat_hits = len(matched_sub_cats)
    total_kw = len(matched_keywords)

    # 行业直接命中 + 至少 1 个概念 → 高
    if industry_hits > 0 and concept_hits > 0:
        return "高"

    # 匹配到 3+ 个子分类 → 高
    if sub_cat_hits >= 3:
        return "高"

    # 匹配到 3+ 个关键词 → 高
    if total_kw >= 3:
        return "高"

    # 匹配到 2 个关键词 → 中
    if total_kw >= 2:
        return "中"

    # 行业直接命中但无概念匹配 → 中
    if industry_hits > 0:
        return "中"

    # 只匹配到 1 个概念 → 低
    return "低"


def generate_cross_track_note(matched_tracks: list[dict]) -> str:
    """如果股票涉及多个赛道，生成跨赛道关联说明。

    Args:
        matched_tracks: match_tracks() 的返回值

    Returns:
        跨赛道说明文字，如果只有一个赛道则返回空字符串
    """
    if len(matched_tracks) < 2:
        return ""

    track_names = [t["track"] for t in matched_tracks]
    notes = []

    # 遍历所有赛道对
    for i in range(len(track_names)):
        for j in range(i + 1, len(track_names)):
            pair = (track_names[i], track_names[j])
            # 正向和反向都查
            note = CROSS_TRACK_NOTES.get(pair) or CROSS_TRACK_NOTES.get((pair[1], pair[0]))
            if note:
                notes.append(note)

    if not notes:
        # 没有预定义的关联说明，生成通用说明
        return f"该股票横跨 {' 和 '.join(track_names)} 赛道，产业链关联较广"

    return "；".join(notes)


def format_result(
    code: str,
    name: str,
    industry: str,
    concepts: list[str],
    matched_tracks: list[dict],
) -> dict:
    """格式化最终输出结果。

    Returns:
        完整的结果字典，可直接 JSON 序列化
    """
    cross_note = generate_cross_track_note(matched_tracks)

    result = {
        "code": code,
        "name": name,
        "industry": industry,
        "concepts": concepts,
        "tracks": [
            {
                "track": t["track"],
                "matched_keywords": t["matched_keywords"],
                "sub_categories": t["sub_categories"],
                "confidence": t["confidence"],
            }
            for t in matched_tracks
        ],
    }

    if cross_note:
        result["cross_track_note"] = cross_note

    if not matched_tracks:
        result["tracks"] = []
        result["note"] = "该股票当前不属于四大赛道范畴"

    return result
