#!/usr/bin/env python3
"""
portfolio — 组合层面风险和仓位管理模块（P2-4）

支持对同时分析的多个标的做组合优化检查。
"""

from typing import Optional, List, Dict


# ── 常量 ─────────────────────────────────────────────────────

MAX_SINGLE_INDUSTRY_WEIGHT = 0.30   # 单行业最大权重
MAX_DAILY_TRADE_RATIO = 0.05        # 单日成交不超过日成交额的比例
MIN_DAILY_AMOUNT = 50000000         # 最低日成交额 5000万（可投性检查）


# ── 行业集中度检查 ──────────────────────────────────────────

def check_industry_concentration(signals: list) -> dict:
    """
    行业集中度检查：同一行业累计权重不超过 MAX_SINGLE_INDUSTRY_WEIGHT。

    参数 signals: [
        {"code": "002475", "name": "立讯精密", "verdict": "买入", "weight": 0.3,
         "industry": "消费电子代工", "amount_wan": 1875739, "pe": 31.6},
        ...
    ]

    返回 dict: { "industry_name": {"total_weight": float, "count": int, "flagged": bool}, ... }
    """
    industry_weights = {}
    industry_counts = {}

    for s in signals:
        ind = s.get("industry", "未知")
        w = s.get("weight", 0)
        industry_weights[ind] = industry_weights.get(ind, 0) + w
        industry_counts[ind] = industry_counts.get(ind, 0) + 1

    result = {}
    for ind, total_w in industry_weights.items():
        flagged = total_w > MAX_SINGLE_INDUSTRY_WEIGHT
        result[ind] = {
            "total_weight": round(total_w, 4),
            "count": industry_counts[ind],
            "flagged": flagged,
        }

    return result


# ── 流动性检查 ──────────────────────────────────────────────

def check_liquidity(signals: list) -> dict:
    """
    流动性检查：推荐仓位不超过日成交额的 MAX_DAILY_TRADE_RATIO。

    参数 signals 每项应包含 amount_wan（日成交额，万元）。

    返回 {
        "total_recommended_amount": float,  # 推荐总投入(估算)
        "flagged_stocks": list,             # 日成交额不足的标的
        "details": [...],                   # 逐标的详情
    }
    """
    details = []
    flagged = []
    total_recommended = 0.0

    for s in signals:
        amount_wan = s.get("amount_wan", 0)
        weight = s.get("weight", 0)
        code = s.get("code", "")
        name = s.get("name", "")

        # 估算推荐金额：假设基准 1 亿组合
        rec_amount = 100000000 * weight
        total_recommended += rec_amount

        # 可投性检查
        if amount_wan < MIN_DAILY_AMOUNT / 10000:  # 5000万 = 5000万元
            flagged.append({
                "code": code,
                "name": name,
                "daily_amount_wan": amount_wan,
                "reason": "日成交额<5000万，流动性不足",
            })

        # 仓位冲击
        max_safe_amount = amount_wan * 10000 * MAX_DAILY_TRADE_RATIO  # 万元 * 万 = 元
        days_needed = rec_amount / max_safe_amount if max_safe_amount > 0 else 99
        details.append({
            "code": code,
            "name": name,
            "rec_amount": rec_amount,
            "daily_amount_wan": amount_wan,
            "max_safe_per_day": round(max_safe_amount, 2),
            "estimated_days": round(days_needed, 1),
        })

    return {
        "total_recommended_amount": round(total_recommended, 2),
        "flagged_stocks": flagged,
        "details": details,
    }


# ── 相关性检查 ──────────────────────────────────────────────

_HIGH_CORRELATION_GROUPS = [
    {"消费电子代工", "消费电子"},
    {"半导体设计", "半导体设备", "半导体封测"},
    {"银行", "保险", "证券"},
    {"白酒", "食品饮料"},
    {"煤炭", "公用事业"},
    {"新能源汽车", "汽车零部件", "电力设备"},
    {"光伏", "电力设备"},
    {"AI算力", "云计算软件", "通信"},
    {"机械", "机器人"},
]


def _are_highly_correlated(ind1: str, ind2: str) -> bool:
    """判断两个行业是否高相关。"""
    if ind1 == ind2:
        return True
    for group in _HIGH_CORRELATION_GROUPS:
        if ind1 in group and ind2 in group:
            return True
    return False


def check_correlation(signals: list) -> list:
    """
    相关性检查：同行业标的、同概念标的视为高相关。

    返回:
        list of dict: [
            {
                "pair": ("002475", "601138"),
                "name1": "立讯精密",
                "name2": "工业富联",
                "reason": "同行业 消费电子代工",
            },
            ...
        ]
    """
    warnings = []
    for i in range(len(signals)):
        for j in range(i + 1, len(signals)):
            s1 = signals[i]
            s2 = signals[j]
            ind1 = s1.get("industry", "未知")
            ind2 = s2.get("industry", "未知")
            if _are_highly_correlated(ind1, ind2):
                warnings.append({
                    "pair": (s1.get("code", ""), s2.get("code", "")),
                    "name1": s1.get("name", ""),
                    "name2": s2.get("name", ""),
                    "reason": "同行业 %s" % (ind1 if ind1 == ind2 else "%s/%s" % (ind1, ind2)),
                })

    return warnings


# ── 权重调整建议 ────────────────────────────────────────────

def build_weight_plan(signals: list) -> dict:
    """
    根据行业集中度约束调整权重。

    规则：
    1. 同一行业累计权重不超过 MAX_SINGLE_INDUSTRY_WEIGHT
    2. 超额行业按原比例缩减
    3. 释放的权重按原有比例分配到未超额标的

    返回 {
        "adjusted_weights": {"code": float, ...},
        "adjustments": [str],  # 调整说明
    }
    """
    # 原始权重
    raw_weights = {}
    for s in signals:
        code = s.get("code", "")
        w = s.get("weight", 0)
        raw_weights[code] = w

    # 行业集中度
    concentration = check_industry_concentration(signals)
    adjustments = []
    adjusted = dict(raw_weights)

    # 找出超额行业
    overflow_industries = {}
    for ind, info in concentration.items():
        if info["flagged"]:
            overflow_industries[ind] = info["total_weight"]
            ratio = MAX_SINGLE_INDUSTRY_WEIGHT / info["total_weight"]
            # 缩减该行业所有标的
            for s in signals:
                if s.get("industry") == ind:
                    code = s.get("code", "")
                    adjusted[code] = round(adjusted.get(code, 0) * ratio, 4)
            adjustments.append("行业 %s 权重从 %.0f%% 缩减至 %.0f%%" % (
                ind, info["total_weight"] * 100, MAX_SINGLE_INDUSTRY_WEIGHT * 100))

    # 释放的权重重新分配
    if overflow_industries:
        freed = sum(raw_weights.get(c, 0) - adjusted.get(c, 0) for s in signals
                     for c in [s.get("code", "")]
                     if s.get("industry") in overflow_industries)
        if freed > 0 and len(signals) > len(overflow_industries):
            # 分配到未调整的标的
            non_adjusted_sum = sum(
                raw_weights.get(s.get("code", ""), 0)
                for s in signals
                if s.get("industry") not in overflow_industries
            )
            if non_adjusted_sum > 0:
                for s in signals:
                    code = s.get("code", "")
                    ind = s.get("industry", "")
                    if ind not in overflow_industries and code in raw_weights:
                        add_w = raw_weights[code] / non_adjusted_sum * freed
                        adjusted[code] = round(adjusted.get(code, 0) + add_w, 4)
                adjustments.append("释放的 %.1f%% 权重按比例分配至其他标的" % (freed * 100))

    return {
        "adjusted_weights": adjusted,
        "adjustments": adjustments,
    }


# ── 综合组合检查 ────────────────────────────────────────────

def portfolio_check(signals: list) -> dict:
    """
    对多个标的的分析信号做组合层面检查。

    参数 signals: [
        {"code": "002475", "name": "立讯精密", "verdict": "买入", "weight": 0.3,
         "industry": "消费电子代工", "amount_wan": 1875739, "pe": 31.6},
        ...
    ]

    返回 dict:
        {
            "warnings": [...],
            "industry_concentration": {...},
            "liquidity_check": {...},
            "correlation_warning": [...],
            "adjusted_weights": {...},
            "build_plan": str,
            "summary": str,
        }
    """
    if not signals:
        return {
            "warnings": [],
            "industry_concentration": {},
            "liquidity_check": {},
            "correlation_warning": [],
            "adjusted_weights": {},
            "build_plan": "",
            "summary": "无标的，跳过组合检查",
        }

    warnings = []

    # 行业集中度
    concentration = check_industry_concentration(signals)
    flagged_inds = [ind for ind, info in concentration.items() if info["flagged"]]
    if flagged_inds:
        warnings.append("行业集中度预警: %s" % ", ".join(
            "%s=%.0f%%(限额30%%)" % (ind, concentration[ind]["total_weight"] * 100)
            for ind in flagged_inds))

    # 流动性
    liquidity = check_liquidity(signals)
    if liquidity["flagged_stocks"]:
        for item in liquidity["flagged_stocks"]:
            warnings.append("流动性不足: %s(%s) 日成交仅 %.0f万元" % (
                item["name"], item["code"], item["daily_amount_wan"]))

    # 相关性
    corr_warnings = check_correlation(signals)
    if corr_warnings:
        for cw in corr_warnings:
            warnings.append("高相关: %s(%s) 与 %s(%s) — %s" % (
                cw["name1"], cw["pair"][0], cw["name2"], cw["pair"][1], cw["reason"]))

    # 权重调整
    weight_plan = build_weight_plan(signals)
    if weight_plan["adjustments"]:
        warnings.extend(weight_plan["adjustments"])

    # 建仓计划
    total_amount = sum(
        s.get("amount_wan", 0) * 10000 for s in signals
    ) or 1
    max_per_day = total_amount * MAX_DAILY_TRADE_RATIO
    recommended_total = 100000000  # 假设 1 亿组合
    build_days = max(1, int(recommended_total / max_per_day)) if max_per_day > 0 else 1
    build_plan = "建议分 %d 天建仓，每次成交不超过日成交额的 %d%%" % (
        min(build_days, 5), int(MAX_DAILY_TRADE_RATIO * 100))

    # 汇总
    total_weight = sum(s.get("weight", 0) for s in signals)
    buy_count = sum(1 for s in signals if s.get("verdict") in ("买入", "强烈建议买入"))
    total_stocks = len(signals)

    summary_parts = ["共 %d 个标的" % total_stocks]
    summary_parts.append("建议买入: %d" % buy_count)
    summary_parts.append("总权重: %.0f%%" % (total_weight * 100))
    if warnings:
        summary_parts.append("风险项: %d 项" % len(warnings))
    else:
        summary_parts.append("无组合层面风险")

    return {
        "warnings": warnings,
        "industry_concentration": concentration,
        "liquidity_check": liquidity,
        "correlation_warning": corr_warnings,
        "adjusted_weights": weight_plan["adjusted_weights"],
        "build_plan": build_plan,
        "summary": " | ".join(summary_parts),
    }


# ── 换仓成本模型 ──────────────────────────────────────

# 市值分档参数（日成交额，万元）
TRANSACTION_COST_PARAMS = {
    "mega_cap": {"daily_volume_threshold": 500000, "spread_bps": 5, "impact_coeff": 0.001},
    "large_cap": {"daily_volume_threshold": 100000, "spread_bps": 8, "impact_coeff": 0.003},
    "mid_cap": {"daily_volume_threshold": 20000, "spread_bps": 15, "impact_coeff": 0.005},
    "small_cap": {"daily_volume_threshold": 5000, "spread_bps": 25, "impact_coeff": 0.010},
    "micro_cap": {"daily_volume_threshold": 0, "spread_bps": 40, "impact_coeff": 0.020},
}


def _determine_tier(amount_wan: float) -> str:
    """根据日成交额（万元）确定市值分档。"""
    for tier, params in sorted(
        TRANSACTION_COST_PARAMS.items(),
        key=lambda x: -x[1]["daily_volume_threshold"]
    ):
        if amount_wan >= params["daily_volume_threshold"]:
            return tier
    return "micro_cap"


def estimate_slippage(trade_amount: float, daily_volume: float, amount_wan: float = 0) -> dict:
    """
    估算交易滑点成本。

    参数：
        trade_amount — 计划买入金额（万元）
        daily_volume — 标的日均成交额（万元）
        amount_wan — 标的昨日成交额（万元，用于市值分档判断）

    返回：
    {
        "participation_rate": float,     # 参与率（成交占比）
        "spread_cost_bps": float,        # 买卖价差成本（基点）
        "impact_cost_bps": float,        # 冲击成本（基点）
        "total_cost_bps": float,         # 总成本（基点）
        "total_cost_pct": float,         # 总成本（百分比）
        "recommended_days": int,         # 建议分N天执行
        "cost_label": str,               # 可读描述
    }

    冲击成本估算：impact ∝ participation_rate^0.6 × impact_coeff
    """
    dv = max(daily_volume, amount_wan, 1)
    participation_rate = trade_amount / dv

    amount_for_tier = amount_wan if amount_wan > 0 else dv
    tier = _determine_tier(amount_for_tier)
    params = TRANSACTION_COST_PARAMS[tier]

    spread_cost_bps = params["spread_bps"]

    # 冲击成本 ∝ participation_rate^0.6 × impact_coeff
    import math
    impact_cost_bps = (participation_rate ** 0.6) * params["impact_coeff"] * 10000  # 转为基点
    impact_cost_bps = min(impact_cost_bps, 200)  # 上限200bps

    total_cost_bps = spread_cost_bps + impact_cost_bps
    total_cost_pct = total_cost_bps / 100.0

    # 建议分拆天数：参与率>10%时建议分拆
    recommended_days = 1
    if participation_rate > 0.10:
        # 使单日参与率降至5%以下
        target_rate = 0.05
        recommended_days = max(1, int(participation_rate / target_rate))
    recommended_days = min(recommended_days, 10)

    # 成本标签
    if total_cost_bps > 80:
        cost_label = "高滑点成本(%.0fbps)，建议分批建仓，分约%d天执行" % (total_cost_bps, recommended_days)
    elif total_cost_bps > 30:
        cost_label = "中等滑点成本(%.0fbps)，可分%d天降低冲击" % (total_cost_bps, recommended_days)
    else:
        cost_label = "低滑点成本(%.0fbps)，可一次性建仓" % total_cost_bps

    return {
        "participation_rate": round(participation_rate, 4),
        "spread_cost_bps": round(spread_cost_bps, 1),
        "impact_cost_bps": round(impact_cost_bps, 1),
        "total_cost_bps": round(total_cost_bps, 1),
        "total_cost_pct": round(total_cost_pct, 2),
        "recommended_days": recommended_days,
        "cost_label": cost_label,
        "_tier": tier,
    }


def add_slippage_to_build_plan(build_plan, signals):
    """
    在建仓计划中加入滑点成本分析。
    修改 build_weight_plan 的输出，增加 estimated_cost 和 adjusted_plan。
    """
    adjusted_weights = build_plan.get("adjusted_weights", {})
    slippage_details = []
    total_days = 1

    for s in signals:
        code = s.get("code", "")
        name = s.get("name", "")
        weight = adjusted_weights.get(code, 0)
        amount_wan = s.get("amount_wan", 0)
        daily_volume = amount_wan  # 日均成交近似
        trade_amount = weight * 10000  # 假设1亿基准，万元级

        cost = estimate_slippage(trade_amount, daily_volume, amount_wan)
        slippage_details.append({
            "code": code,
            "name": name,
            "weight": weight,
            "estimated_cost_bps": cost["total_cost_bps"],
            "recommended_days": cost["recommended_days"],
            "cost_label": cost["cost_label"],
        })
        if cost["recommended_days"] > total_days:
            total_days = cost["recommended_days"]

    # 总体平均成本
    avg_cost_bps = 0
    if slippage_details:
        avg_cost_bps = sum(d["estimated_cost_bps"] for d in slippage_details) / len(slippage_details)

    result = dict(build_plan)
    result["slippage_analysis"] = {
        "estimated_avg_cost_bps": round(avg_cost_bps, 1),
        "recommended_total_days": total_days,
        "details": slippage_details,
    }
    return result


# ── 因子暴露回环：打通因子分析与仓位决策 ─────────────────


def risk_budget_usage(
    code: str,
    signal: dict,
    factor_exposure: dict = None,
    group_signals: dict = None
) -> dict:
    """
    在最终决策前，检查该标的的因子暴露是否超出组合的风险预算。

    目标：将 factor_analysis.py 输出的 α/β/R² 与仓位决策打通。

    参数：
        code             — 股票代码
        signal           — generate_signal 或 generate_signal_with_matrix 的输出
                           必须包含 verdict, tech_score, conviction 等字段
        factor_exposure  — factor_analysis.factor_exposure_report() 的输出
                           或包含 alpha, beta, r_squared 的 dict
        group_signals    — deduplicate_factor_signals() 的输出（可选）

    返回：
        {
            "adjustment_factor": float,  # 仓位调整系数（1.0=不变, 0.8=降20%%, 1.2=加20%%）
            "reason": str,               # 调整原因
            "checks": [
                {"check": "高β", "triggered": bool, "action": str, "detail": str},
                {"check": "高R²", ...},
                {"check": "独特α", ...},
                {"check": "信号一致性", ...},
                {"check": "因子分组去重", ...},
            ],
            "adjusted_verdict": str,     # 调整后的裁决
        }

    检查规则：
    1. 高β（β > 1.3）：降低仓位15%%
    2. 高R²（R² > 0.8）：与指数高度同步，降低α置信度
    3. 独特α（R² < 0.3 且 α > 0.01）：优质选股信号，可增加仓位
    4. 信号一致性：如果 signal_matrix 的裁决结果与加权求和不同，标记分歧
    5. 因子分组去重：如果 group_signals.normalized_score < 0.3，整体信号弱，降低仓位
    """
    checks = []
    adjustment = 1.0
    reasons = []

    # 从signal中读取原始裁决和置信度
    verdict = signal.get("verdict", "持有")
    conviction = signal.get("conviction", 0.3)
    tech_score = signal.get("tech_score", 0)

    # 1. 高β检查
    beta = 1.0
    if factor_exposure:
        beta = factor_exposure.get("beta", 1.0)
    beta_high = beta > 1.3
    checks.append({
        "check": "高β",
        "triggered": beta_high,
        "action": "降15%%" if beta_high else "无调整",
        "detail": "β=%.2f %s" % (beta, ">1.3, 单向敞口偏高" if beta_high else "<1.3, 正常范围"),
    })
    if beta_high:
        adjustment *= 0.85
        reasons.append("高β(%.2f>1.3), 降15%%仓位" % beta)

    # 2. 高R²检查
    r_squared = 0.0
    if factor_exposure:
        r_squared = factor_exposure.get("r_squared", 0.0)
    r2_high = r_squared > 0.8
    checks.append({
        "check": "高R²",
        "triggered": r2_high,
        "action": "降低α置信度" if r2_high else "无调整",
        "detail": "R²=%.2f %s" % (r_squared, ">0.8, 与指数高度同步" if r2_high else "<0.8, 独立选股α空间充足"),
    })
    if r2_high:
        # 高R²降低置信度但不降低仓位
        reasons.append("高R²(%.2f>0.8), α置信度降低" % r_squared)

    # 3. 独特α检查
    alpha = 0.0
    if factor_exposure:
        alpha = factor_exposure.get("alpha", 0.0)
    has_unique_alpha = r_squared < 0.3 and alpha > 0.01
    checks.append({
        "check": "独特α",
        "triggered": has_unique_alpha,
        "action": "加20%%" if has_unique_alpha else "无调整",
        "detail": "R²=%.2f, α=%.4f %s" % (r_squared, alpha,
            "<0.3且α>0.01, 优质选股信号" if has_unique_alpha else "不满足独特α条件"),
    })
    if has_unique_alpha:
        adjustment *= 1.2
        reasons.append("独特α(R²=%.2f<0.3, α=%.4f>0.01), 加20%%仓位" % (r_squared, alpha))

    # 4. 信号一致性检查
    verdict_from_matrix = signal.get("matrix_verdict", verdict)
    has_divergence = verdict != verdict_from_matrix
    checks.append({
        "check": "信号一致性",
        "triggered": has_divergence,
        "action": "标记分歧" if has_divergence else "一致",
        "detail": "裁决=%s, 矩阵裁决=%s %s" % (
            verdict, verdict_from_matrix,
            "分歧" if has_divergence else "一致"),
    })
    if has_divergence:
        reasons.append("信号分歧: 裁决=%s 矩阵=%s" % (verdict, verdict_from_matrix))

    # 5. 因子分组去重检查
    group_score = 1.0
    if group_signals:
        group_score = group_signals.get("normalized_score", 1.0)
    score_weak = group_score < 0.3
    checks.append({
        "check": "因子分组去重",
        "triggered": score_weak,
        "action": "降15%%" if score_weak else "无调整",
        "detail": "分组归一化得分=%.2f %s" % (group_score,
            "<0.3, 整体信号弱" if score_weak else ">=0.3, 信号充足"),
    })
    if score_weak:
        adjustment *= 0.85
        reasons.append("因子分组得分(%.2f<0.3), 降15%%仓位" % group_score)

    # 综合调整
    if adjustment < 0.5:
        adjusted_verdict = "减仓"
    elif adjustment < 0.8:
        if verdict in ("买入", "强烈建议买入"):
            adjusted_verdict = "买入(谨慎)"
        else:
            adjusted_verdict = verdict
    elif adjustment > 1.15:
        if verdict in ("买入", "强烈建议买入"):
            adjusted_verdict = "强烈建议买入"
        else:
            adjusted_verdict = verdict
    else:
        adjusted_verdict = verdict

    reason_str = " | ".join(reasons) if reasons else "无调整"

    return {
        "adjustment_factor": round(adjustment, 4),
        "reason": reason_str,
        "checks": checks,
        "adjusted_verdict": adjusted_verdict,
    }


# ── 最坏情景分析 ──────────────────────────────────────────


def _z_score(confidence: float) -> float:
    """
    手动计算正态分布Z分数（近似）。
    使用 Abramowitz & Stegun 近似。
    """
    import math as _m
    # 常见置信度映射
    conf_map = {
        0.90: 1.645,
        0.95: 1.96,
        0.99: 2.576,
        0.85: 1.036,
        0.80: 0.842,
        0.75: 0.674,
        0.999: 3.291,
    }
    # 找最接近的
    if confidence in conf_map:
        return conf_map[confidence]
    # 近似计算
    # 使用简单线性映射
    if confidence >= 0.99:
        return 2.576 + (confidence - 0.99) / 0.009 * 0.715
    elif confidence >= 0.95:
        return 1.96 + (confidence - 0.95) / 0.04 * 0.616
    elif confidence >= 0.90:
        return 1.645 + (confidence - 0.90) / 0.05 * 0.315
    elif confidence >= 0.85:
        return 1.036 + (confidence - 0.85) / 0.05 * 0.609
    elif confidence >= 0.80:
        return 0.842 + (confidence - 0.80) / 0.05 * 0.194
    else:
        return 0.674 + (confidence - 0.75) / 0.05 * 0.168


def worst_case_analysis(
    current_price: float,
    stop_loss: float,
    position_size_pct: float,
    portfolio_value: float = 1000000,
    num_shares: int = 0,
    daily_volatility: float = 0.03,
    var_confidence: float = 0.95
) -> dict:
    """
    最坏情景分析（风控报表核心输出）。

    回答：如果这笔交易按最坏情况发展，会亏多少？

    参数：
        current_price       — 当前股价（元）
        stop_loss            — 止损价（元），等于 current_price 则表示无明确止损
        position_size_pct   — 仓位占比（小数，如0.3=30%%）
        portfolio_value     — 总组合价值（元，默认100万）
        num_shares          — 持仓股数（可选，如果提供则覆盖position计算）
        daily_volatility    — 日波动率估计（默认3%%）
        var_confidence      — VaR置信度（默认95%%）

    返回：
        {
            "stop_loss_price": float,
            "stop_loss_amount": float,
            "stop_loss_pct": float,
            "position_amount": float,
            "position_pct": float,
            "loss_as_pct_of_portfolio": float,
            "recovery_return_needed": float,
            "var_daily": float,
            "var_daily_pct": float,
            "risk_rating": str,
            "suggested_action": str,
            "detail": str,
        }
    """
    if current_price <= 0:
        return {
            "stop_loss_price": 0, "stop_loss_amount": 0, "stop_loss_pct": 0,
            "position_amount": 0, "position_pct": 0,
            "loss_as_pct_of_portfolio": 0, "recovery_return_needed": 0,
            "var_daily": 0, "var_daily_pct": 0,
            "risk_rating": "无效", "suggested_action": "检查输入",
            "detail": "current_price<=0",
        }

    # 持仓金额
    if num_shares > 0:
        position_amount = num_shares * current_price
    else:
        position_amount = portfolio_value * position_size_pct

    position_pct = position_amount / portfolio_value if portfolio_value > 0 else 0.0

    # 止损计算
    if stop_loss >= current_price:
        # 无明确止损
        stop_loss_price = current_price
        stop_loss_amount = 0.0
        stop_loss_pct = 0.0
    else:
        stop_loss_price = stop_loss
        if num_shares > 0:
            stop_loss_amount = (current_price - stop_loss) * num_shares
        else:
            stop_loss_amount = (1.0 - stop_loss / current_price) * position_amount
        stop_loss_pct = (current_price - stop_loss) / current_price * 100.0

    # 最大亏损占组合比例
    loss_as_pct_of_portfolio = stop_loss_amount / portfolio_value if portfolio_value > 0 else 0.0

    # 恢复所需收益率
    if portfolio_value - stop_loss_amount > 0:
        recovery_return_needed = stop_loss_amount / (portfolio_value - stop_loss_amount)
    else:
        recovery_return_needed = 1.0

    # VaR计算
    z = _z_score(var_confidence)
    var_daily = position_amount * daily_volatility * z
    var_daily_pct = daily_volatility * z * 100.0

    # 风险评级
    max_single_loss_pct = max(stop_loss_pct / 100.0, var_daily_pct / 100.0)
    if max_single_loss_pct < 0.05:
        risk_rating = "安全"
        suggested_action = "正常持有"
    elif max_single_loss_pct < 0.15:
        risk_rating = "可控"
        suggested_action = "设好止损, 关注波动"
    else:
        risk_rating = "高风险"
        suggested_action = "建议降低仓位或加强止损保护"

    detail_parts = [
        "持仓金额=%.2f (占组合%.1f%%%%) " % (position_amount, position_pct * 100),
        "止损幅度=%.1f%%%%, 最大亏损=%.2f (占组合%.1f%%%%) " % (
            stop_loss_pct, stop_loss_amount, loss_as_pct_of_portfolio * 100),
        "日VaR(%.0f%%%%)=%.2f (%.1f%%%%) " % (var_confidence * 100, var_daily, var_daily_pct),
        "恢复需涨=%.1f%%%%, 风险评级=%s" % (recovery_return_needed * 100, risk_rating),
    ]

    return {
        "stop_loss_price": round(stop_loss_price, 2),
        "stop_loss_amount": round(stop_loss_amount, 2),
        "stop_loss_pct": round(stop_loss_pct, 2),
        "position_amount": round(position_amount, 2),
        "position_pct": round(position_pct, 4),
        "loss_as_pct_of_portfolio": round(loss_as_pct_of_portfolio, 4),
        "recovery_return_needed": round(recovery_return_needed, 4),
        "var_daily": round(var_daily, 2),
        "var_daily_pct": round(var_daily_pct, 2),
        "risk_rating": risk_rating,
        "suggested_action": suggested_action,
        "detail": "".join(detail_parts),
    }


def batch_worst_case(holdings: list) -> list:
    """
    批量最坏情景分析。

    对持仓中的多只股票分别计算 + 合并风险标记。

    参数 holdings: [
        {"code": "002475", "price": 75, "stop_loss": 70,
         "position_pct": 0.3, "portfolio_value": 1000000},
        ...
    ]

    返回每只标的的 worst_case_analysis + 合并风险标记
    """
    if not holdings:
        return []

    results = []
    for h in holdings:
        result = worst_case_analysis(
            current_price=h.get("price", 0),
            stop_loss=h.get("stop_loss", h.get("price", 0)),
            position_size_pct=h.get("position_pct", 0),
            portfolio_value=h.get("portfolio_value", 1000000),
            num_shares=h.get("num_shares", 0),
            daily_volatility=h.get("daily_volatility", 0.03),
            var_confidence=h.get("var_confidence", 0.95),
        )
        result["code"] = h.get("code", "")
        results.append(result)

    # 合并风险标记
    has_high_risk = any(r.get("risk_rating") == "高风险" for r in results)
    has_controllable = any(r.get("risk_rating") == "可控" for r in results)

    combined_risk = "高风险" if has_high_risk else ("需关注" if has_controllable else "安全")

    # 总计潜在最大亏损
    total_max_loss = sum(r.get("stop_loss_amount", 0) for r in results)

    if results:
        results[0]["_combined_risk"] = combined_risk
        results[0]["_total_max_loss"] = round(total_max_loss, 2)

    return results


# ── __all__ ──────────────────────────────────────────────────

__all__ = [
    "MAX_SINGLE_INDUSTRY_WEIGHT",
    "MAX_DAILY_TRADE_RATIO",
    "MIN_DAILY_AMOUNT",
    "portfolio_check",
    "check_industry_concentration",
    "check_liquidity",
    "check_correlation",
    "build_weight_plan",
    "estimate_slippage",
    "add_slippage_to_build_plan",
    "TRANSACTION_COST_PARAMS",
    "risk_budget_usage",
    "worst_case_analysis",
    "batch_worst_case",
]
