"""数据获取层 — push2 明文接口补行业(f127) + 题材/概念(f129) + 名称(f58)。

榜单本体(加密)由 browser.py 用 Playwright 渲染;本模块只负责明文字段补全。

网络要点(2026-07-14 联调确认,同 zhuxian/screener/fetcher.py):
  push2 域名直连(trust_env=False/NO_PROXY)必被服务端 RemoteDisconnected;
  必须跟随系统代理(trust_env=True),且用 http 而非 https(代理下 https 成功率
  仅 ~13%,http ~90%+)。push2 偶发空响应,带重试(RETRIES)。
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

_session = requests.Session()
_session.trust_env = True   # 跟随系统代理(push2 直连会被关闭连接)
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
})

PUSH2_URL = "http://push2.eastmoney.com/api/qt/stock/get"   # http 非 https
FIELDS = "f57,f58,f127,f129"   # 代码 / 名称 / 行业 / 概念
RETRIES = 3                    # push2 偶发空响应,重试次数


def build_secid(code: str) -> str:
    """东方财富 secid:6 开头(沪)→'1'，其余(深/创业板/北交所)→'0'。"""
    prefix = "1" if code.startswith("6") else "0"
    return f"{prefix}.{code}"


def _request_push2(secid: str) -> dict:
    """请求 push2 stock/get，返回 json(失败/重试耗尽返回 {})。可被测试 mock。"""
    params = {"secid": secid, "fields": FIELDS, "fltt": "2"}
    for attempt in range(RETRIES):
        try:
            r = _session.get(PUSH2_URL, params=params, timeout=10)
            return r.json() or {}
        except Exception as e:
            if attempt < RETRIES - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            print(f"push2 请求失败(secid={secid}): {e}", flush=True)
            return {}


def fetch_industry_concepts(code: str) -> dict:
    """取一只股票的行业 + 概念 + 名称。失败/缺字段返回空(不抛)。"""
    data = (_request_push2(build_secid(code)) or {}).get("data") or {}
    industry = (data.get("f127") or "").strip()
    raw = (data.get("f129") or "").strip()
    concepts = [c.strip() for c in raw.split(",") if c.strip()]
    name = (data.get("f58") or "").strip()
    return {"industry": industry, "concepts": concepts, "name": name}


def fetch_industry_for_stocks(stocks: list, max_workers: int = 5,
                              sweeps: int = 3) -> None:
    """并发为 stocks 每条就地补 industry / concepts / reason / name。

    push2 经系统代理(Clash)访问,上游节点偶发空响应(突发式失效),单次并发跑会有
    部分股票拿不到数据。故做多轮 sweep:每轮只重试上一轮仍缺 name 的 code;
    各 sweep 之间天然有时间间隔,可骑过突发窗口,显著提升补全率。
    """
    result = {}
    pending = [s.get("code") for s in stocks if s.get("code")]

    def _one(code):
        return code, fetch_industry_concepts(code)

    for sweep in range(sweeps if sweeps > 0 else 1):
        if not pending:
            break
        got_this_sweep = 0
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = [ex.submit(_one, c) for c in pending]
            for fut in as_completed(futs):
                try:
                    code, info = fut.result()
                except Exception:
                    continue
                if info.get("name") or info.get("industry") or info.get("concepts"):
                    result[code] = info
                    got_this_sweep += 1
        # 下一轮只重试仍未取到的
        pending = [c for c in pending if c not in result]
        if pending:
            print(f"[sweep {sweep + 1}/{sweeps}] 已补 {got_this_sweep} 只,"
                  f"仍缺 {len(pending)} 只,将重试...", flush=True)

    for s in stocks:
        info = result.get(s.get("code"), {"industry": "", "concepts": [], "name": ""})
        s["industry"] = info["industry"]
        s["concepts"] = info["concepts"]
        s["reason"] = ",".join(info["concepts"])
        if not s.get("name"):               # DOM name 空 → 用 push2 f58 补
            s["name"] = info.get("name", "")
        s["rank_change"] = s.get("rank_change", "")
