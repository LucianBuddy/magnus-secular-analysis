"""
valuation_ensemble — 多路径估值集成（P2-1）

功能：
  - 将 PE/PB/DDM/OE 四种路径的估值区间加权聚合
  - 计算均值、90% 置信区间、方法分歧度
  - 输出结构化的{mean, ci_low, ci_high, divergence, method_count}

依赖：无外部依赖（仅标准库）
"""

import random
import math
from typing import Optional, Any


def valuation_ensemble(
    current_price: float,
    pe_band: tuple,
    pb_band: tuple,
    ddm_band: tuple,
    oe_band: tuple,
    conviction_weight: float = 0.5,
) -> dict:
    """
    多路径估值集成。

    参数：
        current_price     — 当前价
        pe_band           — PE 估值区间 (低, 高)
        pb_band           — PB 估值区间 (低, 高)
        ddm_band          — DDM 估值区间 (低, 高)
        oe_band           — OE 估值区间 (低, 高)
        conviction_weight — 置信度权重 (0~1), 决定各方法权重分布

    返回：
        {
            "mean": float,          # 加权平均估值
            "ci_low": float,        # 90% 置信区间下限
            "ci_high": float,       # 90% 置信区间上限
            "divergence": str,      # "低" / "中等" / "高"
            "divergence_pct": float,# 分歧度百分比
            "method_count": int,    # 有效方法数
            "weights": dict,        # 各方法权重
            "band_spans": dict,     # 各方法区间跨度
        }
    """
    # ── 收集有效方法（区间任一值>0） ──
    bands = {
        "PE": pe_band,
        "PB": pb_band,
        "DDM": ddm_band,
        "OE": oe_band,
    }
    valid = {}
    for name, (low, high) in bands.items():
        if low is not None and high is not None and low > 0 and high > 0:
            valid[name] = (low, high)

    if not valid:
        return {
            "mean": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "divergence": "N/A",
            "divergence_pct": 0,
            "method_count": 0,
            "weights": {},
            "band_spans": {},
        }

    # ── 动态权重 ──
    # 基准权重: PE=0.3, PB=0.15, DDM=0.25, OE=0.3
    # 根据 conviction_weight 调整: 置信度高则加重 OE, 低则加重 PE
    base_weights = {
        "PE": 0.30,
        "PB": 0.15,
        "DDM": 0.25,
        "OE": 0.30,
    }
    # 当 conviction 高(>0.7): OE 权重提升, PE 降低
    # 当 conviction 低(<0.3): PE 权重提升
    adj = (conviction_weight - 0.5) * 0.3  # -0.15 ~ +0.15
    weights = base_weights.copy()
    weights["OE"] = max(0.05, min(0.50, weights["OE"] + adj))
    weights["PE"] = max(0.05, min(0.50, weights["PE"] - adj))

    # 只保留有效方法的权重，重新归一化
    filtered_weights = {k: v for k, v in weights.items() if k in valid}
    total_w = sum(filtered_weights.values())
    if total_w <= 0:
        n = len(valid)
        filtered_weights = {k: 1.0 / n for k in valid}
    else:
        filtered_weights = {k: v / total_w for k, v in filtered_weights.items()}

    # ── 加权平均 ──
    weighted_mid = 0.0
    all_spans = []
    for name, w in filtered_weights.items():
        low, high = valid[name]
        mid = (low + high) / 2.0
        weighted_mid += mid * w
        all_spans.append(high - low)

    band_spans = {name: round(high - low, 2) for name, (low, high) in valid.items()}

    # ── 90% 置信区间 ──
    all_mids = [(valid[name][0] + valid[name][1]) / 2.0 for name in filtered_weights]
    if len(all_mids) >= 2:
        sorted_mids = sorted(all_mids)
        n = len(sorted_mids)
        ci_low = sorted_mids[n // 4] if n >= 4 else sorted_mids[0]
        ci_high = sorted_mids[(3 * n) // 4] if n >= 4 else sorted_mids[-1]
    else:
        ci_low = valid[list(valid.keys())[0]][0]
        ci_high = valid[list(valid.keys())[0]][1]

    # ── 分歧度 ──
    if len(all_mids) >= 2:
        min_v = min(all_mids)
        max_v = max(all_mids)
        mean_v = sum(all_mids) / len(all_mids)
        if mean_v > 0:
            diverg_pct = round((max_v - min_v) / mean_v * 100, 1)
        else:
            diverg_pct = 0
    else:
        diverg_pct = 0

    if diverg_pct < 20:
        divergence = "低"
    elif diverg_pct < 40:
        divergence = "中等"
    else:
        divergence = "高"

    return {
        "mean": round(weighted_mid, 2),
        "ci_low": round(ci_low, 2),
        "ci_high": round(ci_high, 2),
        "divergence": divergence,
        "divergence_pct": diverg_pct,
        "method_count": len(valid),
        "weights": filtered_weights,
        "band_spans": band_spans,
    }


# ═══════════════════════════════════════════════════════════════
# Monte Carlo 估值模拟
# ═══════════════════════════════════════════════════════════════


def _perc(data, p):
    """手动计算百分位数。"""
    if not data:
        return 0.0
    n = len(data)
    sorted_data = sorted(data)
    idx = max(0, min(n - 1, int(round(p * n / 100.0))))
    return sorted_data[idx]


def monte_carlo_valuation(
    base_earnings_per_share: float,
    growth_rate_annual: float = 0.05,
    growth_volatility: float = 0.15,
    discount_rate_base: float = 0.08,
    discount_rate_volatility: float = 0.02,
    oe_multiple_base: float = 15.0,
    oe_multiple_volatility: float = 3.0,
    n_simulations: int = 10000,
    projection_years: int = 10,
    terminal_growth: float = 0.02
) -> dict:
    """
    Monte Carlo 估值模拟。

    对关键估值参数的概率分布做随机采样，输出估值的完整分布。

    参数：
        base_earnings_per_share  — 基准每股收益（元）
        growth_rate_annual       — 年化增长率基准
        growth_volatility        — 增长率的标准差（年度波动）
        discount_rate_base       — 折现率基准
        discount_rate_volatility — 折现率的标准差
        oe_multiple_base         — Owner Earnings 倍数基准
        oe_multiple_volatility   — OE 倍数的标准差
        n_simulations            — 模拟次数（默认10000）
        projection_years         — 投影年限（默认10年）
        terminal_growth          — 终值增长率（默认2%%）

    返回：
        {
            "mean": float, "median": float, "mode": float,
            "std": float, "percentiles": {...},
            "skewness": float, "is_right_skewed": bool,
            "n_simulations": int, "histogram_bins": [...],
            "detail": str,
        }
    """
    if base_earnings_per_share <= 0:
        return {
            "mean": 0.0, "median": 0.0, "mode": 0.0, "std": 0.0,
            "percentiles": {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
            "skewness": 0, "is_right_skewed": False,
            "n_simulations": 0, "histogram_bins": [],
            "detail": "基准EPS<=0，无法估值",
        }

    n_simulations = max(100, min(n_simulations, 100000))
    values = []

    for _ in range(n_simulations):
        # 1. 从增长率分布采样
        g = random.gauss(growth_rate_annual, growth_volatility)
        # 确保g合理范围 (-0.3 ~ 0.5)
        g = max(-0.3, min(0.5, g))

        # 2. 从折现率分布采样
        r = random.gauss(discount_rate_base, discount_rate_volatility)
        r = max(0.02, min(0.20, r))  # 2%%~20%%

        # 3. 从OE倍数分布采样
        m = random.gauss(oe_multiple_base, oe_multiple_volatility)
        m = max(3.0, min(50.0, m))

        # 4. 计算内在价值：简化 DCF + 终值
        # 每股内在价值 = Σ(EPS_t / (1+r)^t) + 终值/(1+r)^n
        # 其中 EPS_t = base_EPS × (1+g)^t
        # 终值 = EPS_n × M (Owner Earnings 终值法)
        intrinsic = 0.0
        eps_t = float(base_earnings_per_share)
        for t in range(1, projection_years + 1):
            eps_t *= (1.0 + g)
            intrinsic += eps_t / ((1.0 + r) ** t)

        # 终值 = 最后一期EPS × OE倍数 / (1+r)^n
        terminal_value = eps_t * m / ((1.0 + r) ** projection_years)
        intrinsic += terminal_value

        values.append(intrinsic)

    if not values:
        return {"detail": "模拟未产生有效结果"}

    n = len(values)
    sorted_vals = sorted(values)

    # 均值
    mean = sum(values) / n

    # 中位数
    median = sorted_vals[n // 2] if n > 0 else 0.0

    # 众数：直方图10桶近似
    v_min, v_max = min(values), max(values)
    if v_max - v_min < 0.01:
        mode = mean
    else:
        bin_count = 10
        bin_width = (v_max - v_min) / bin_count
        bins = [0] * bin_count
        for v in values:
            idx = int((v - v_min) / bin_width)
            if idx >= bin_count:
                idx = bin_count - 1
            bins[idx] += 1
        mode_idx = bins.index(max(bins))
        mode = v_min + (mode_idx + 0.5) * bin_width

    # 标准差
    variance = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(variance) if variance > 0 else 0.0

    # 百分位数
    percentiles = {
        "p5": _perc(sorted_vals, 5),
        "p25": _perc(sorted_vals, 25),
        "p50": median,
        "p75": _perc(sorted_vals, 75),
        "p95": _perc(sorted_vals, 95),
    }

    # 偏度
    if std > 0:
        skewness = sum(((v - mean) / std) ** 3 for v in values) / n
    else:
        skewness = 0.0

    is_right_skewed = skewness > 0.5

    # 直方图
    if v_max - v_min < 0.01:
        histogram_bins = [
            {"bin_start": round(v_min, 2), "bin_end": round(v_min + 0.01, 2),
             "count": n}
        ]
    else:
        bin_count = 10
        bin_width = (v_max - v_min) / bin_count
        bin_counts = [0] * bin_count
        for v in values:
            idx = int((v - v_min) / bin_width)
            if idx >= bin_count:
                idx = bin_count - 1
            bin_counts[idx] += 1
        histogram_bins = [
            {
                "bin_start": round(v_min + i * bin_width, 2),
                "bin_end": round(v_min + (i + 1) * bin_width, 2),
                "count": bin_counts[i],
            }
            for i in range(bin_count)
        ]

    detail_parts = [
        "Monte Carlo %d次模拟" % n_simulations,
        "右偏=%.2f(中位数<均值=%.2f<%.2f)" % (skewness, median, mean) if skewness > 0.3 else "分布接近对称(偏度=%.2f)" % skewness,
        "均值=%.2f 中位=%.2f 标准差=%.2f" % (mean, median, std),
        "90%%置信区间: [%.2f, %.2f]" % (percentiles["p5"], percentiles["p95"]),
    ]

    return {
        "mean": round(mean, 2),
        "median": round(median, 2),
        "mode": round(mode, 2),
        "std": round(std, 2),
        "percentiles": {k: round(v, 2) for k, v in percentiles.items()},
        "skewness": round(skewness, 4),
        "is_right_skewed": is_right_skewed,
        "n_simulations": n_simulations,
        "histogram_bins": histogram_bins,
        "detail": " | ".join(detail_parts),
    }


def mc_compare_to_market(monte_carlo_result: dict, current_price: float) -> dict:
    """
    将 Monte Carlo 估值结果与当前市价对比。

    返回：
        {
            "current_price": float,
            "price_vs_mean": str,        # "低于均值" / "高于均值" / "接近均值"
            "price_percentile": float,   # 当前价在模拟分布中的分位
            "prob_undervalued": float,   # 当前价低于p50的概率
            "detail": str,
        }
    """
    if current_price <= 0:
        return {
            "current_price": current_price,
            "price_vs_mean": "无效价格",
            "price_percentile": 0,
            "prob_undervalued": 0,
            "detail": "当前价<=0，无法比较",
        }

    mean = monte_carlo_result.get("mean", 0)
    median = monte_carlo_result.get("median", 0)
    n_sim = monte_carlo_result.get("n_simulations", 0)

    if mean <= 0 or n_sim <= 0:
        return {
            "current_price": current_price,
            "price_vs_mean": "无有效估值",
            "price_percentile": 0,
            "prob_undervalued": 0,
            "detail": "Monte Carlo结果无效",
        }

    # 价格 vs 均值
    diff_pct = (current_price - mean) / mean * 100
    if diff_pct > 10:
        price_vs_mean = "高于均值"
    elif diff_pct < -10:
        price_vs_mean = "低于均值"
    else:
        price_vs_mean = "接近均值"

    # 分位估算：从直方图推算当前价在分布中的位置
    # 没直方图回退到均值比较
    histogram_bins = monte_carlo_result.get("histogram_bins", [])
    if histogram_bins and len(histogram_bins) > 0:
        total = sum(b.get("count", 0) for b in histogram_bins)
        below_count = 0
        for b in histogram_bins:
            if b.get("bin_end", 0) <= current_price:
                below_count += b.get("count", 0)
            elif b.get("bin_start", 0) <= current_price < b.get("bin_end", 0):
                # 当前价落在该桶内，按比例分配
                ratio = (current_price - b["bin_start"]) / (b["bin_end"] - b["bin_start"] + 0.001)
                below_count += int(b["count"] * ratio)
                break
            else:
                break
        price_percentile = below_count / total * 100 if total > 0 else 50.0
    else:
        # 回退到正态分布近似
        std = monte_carlo_result.get("std", 0)
        if std > 0:
            z = (current_price - mean) / std
            # 简单近似累积正态
            price_percentile = 50.0 * (1.0 + z / 3.0)
            price_percentile = max(0.0, min(100.0, price_percentile))
        else:
            price_percentile = 50.0

    # 低于p50的概率：如果当前价<中位数，概率=1-分位/100
    prob_undervalued = max(0.0, 1.0 - price_percentile / 100.0)

    detail = "当前价=%.2f, 估值均值=%.2f(%s), 位于MC分布P%.0f, 低估概率=%.0f%%%%" % (
        current_price, mean, price_vs_mean, price_percentile, prob_undervalued * 100)

    return {
        "current_price": current_price,
        "price_vs_mean": price_vs_mean,
        "price_percentile": round(price_percentile, 1),
        "prob_undervalued": round(prob_undervalued, 4),
        "detail": detail,
    }
