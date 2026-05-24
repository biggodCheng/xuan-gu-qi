import os
import time

import requests

for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

_session = requests.Session()
_session.trust_env = False


def get_market_cap_map() -> dict[str, float]:
    """获取全 A 股市值映射（新浪财经数据源）。

    Returns:
        dict: code → 总市值（万元）
    """
    cap_map: dict[str, float] = {}
    page = 1
    per_page = 80

    while True:
        try:
            url = (
                "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
                "json_v2.php/Market_Center.getHQNodeData"
            )
            params = {
                "page": page,
                "num": per_page,
                "sort": "symbol",
                "asc": 1,
                "node": "hs_a",
                "_s_r_a": "auto",
            }
            r = _session.get(url, params=params, timeout=15)
            data = r.json()

            if not data:
                break

            for item in data:
                try:
                    code = item.get("code", "")
                    mktcap = item.get("mktcap", "")
                    if code and mktcap:
                        cap_map[code] = float(mktcap)
                except (ValueError, TypeError):
                    continue

            page += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"获取市值第 {page} 页失败: {e}", flush=True)
            break

    return cap_map
