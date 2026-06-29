#!/usr/bin/env python3
"""
批量并行分析模块。
同时分析多只股票，采用多线程拉取数据。
"""

import concurrent.futures
import threading

# 线程本地存储
_thread_local = threading.local()


def batch_build_summary(codes_and_params: list) -> dict:
    """
    批量生成多只股票的 ss 摘要。

    参数：
        codes_and_params — [(code, name, dict_of_params), ...]
        其中 dict_of_params 是传给 build_summary 的各参数

    返回 {code: ss_dict, ...}

    使用 ThreadPoolExecutor 并行拉取数据。
    默认最大线程 4（避免触发限流）。
    """
    from .preprocess import build_summary

    results = {}
    errors = []

    def _build_one(code, name, params):
        try:
            ss = build_summary(code=code, name=name, **params)
            return code, ss, None
        except Exception as e:
            return code, None, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for item in codes_and_params:
            if len(item) == 3:
                code, name, params = item
            elif len(item) == 2:
                code, name = item
                params = {}
            else:
                continue
            futures.append(executor.submit(_build_one, code, name, params))

        for future in concurrent.futures.as_completed(futures):
            code, ss, err = future.result()
            if ss is not None:
                results[code] = ss
            else:
                errors.append("%s: %s" % (code, err))

    # 将错误作为元数据附加
    result = dict(results)
    result["_errors"] = errors
    return result


def batch_analyze(codes, names=None, max_workers=4):
    """
    并行分析多只股票，返回合并的分析简报。

    参数：
        codes — 股票代码列表
        names — 股票名称列表（可选，None则自动获取）
        max_workers — 最大并行数（默认4）

    返回：
    {
        "codes": [...],
        "summaries": {code: ss_dict, ...},
        "tech_scores": {code: tech_dict, ...},
        "portfolio_check": dict,       # 当>=2只股票时自动调用
        "errors": [str],               # 失败的股票
    }
    """
    from .preprocess import build_summary
    from .technical import compute_enhanced_tech_score
    from .portfolio import portfolio_check

    if names is None:
        names = [""] * len(codes)

    results = {}
    errors = []

    def _analyze_one(code, name):
        try:
            ss = build_summary(code=code, name=name)
            tech = compute_enhanced_tech_score(
                closes=ss.get("kl10_closes", []),
                ma5=ss.get("ma5", 0),
                ma10=ss.get("ma10", 0),
                ma20=ss.get("ma20", 0),
                current_price=ss.get("p", 0),
            )
            return code, ss, tech, None
        except Exception as e:
            return code, None, None, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_analyze_one, c, n) for c, n in zip(codes, names)]

        for future in concurrent.futures.as_completed(futures):
            code, ss, tech, err = future.result()
            if ss is not None:
                results[code] = {"summary": ss, "tech": tech}
            else:
                errors.append("%s: %s" % (code, err))

    # 组织的返回
    summaries = {}
    tech_scores = {}
    for code, data in results.items():
        summaries[code] = data["summary"]
        tech_scores[code] = data["tech"]

    # 组合检查
    portfolio_result = {}
    if len(codes) >= 2:
        signals = []
        for code in codes:
            if code in summaries:
                ss = summaries[code]
                signals.append({
                    "code": code,
                    "name": codes[codes.index(code)] if len(codes) < 10 else "",
                    "verdict": "买入" if tech_scores.get(code, {}).get("score", 0) > 0.3 else "持有",
                    "weight": 1.0 / max(len(codes), 1),
                    "industry": ss.get("ind", "未知"),
                    "amount_wan": ss.get("amount_wan", 0),
                    "pe": ss.get("pe", 0),
                })
        portfolio_result = portfolio_check(signals)

    return {
        "codes": codes,
        "summaries": summaries,
        "tech_scores": tech_scores,
        "portfolio_check": portfolio_result,
        "errors": errors,
    }


__all__ = [
    "batch_build_summary",
    "batch_analyze",
]
