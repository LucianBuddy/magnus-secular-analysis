#!/usr/bin/env python3
"""
持仓绩效归因分析模块（轻量版）。

支持三类归因：
- 选股贡献：因选对/选错股票获得的超额收益
- 行业配置贡献：因超配/低配行业获得的超额收益
- 择时贡献：因加减仓时机获得的超额收益

归因方法：简化 Brinson 模型
  组合超额收益 = 配置效应 + 选股效应 + 交叉效应（择时）
  
  配置效应 = Σ(组合行业权重 - 基准行业权重) × 基准行业收益
  选股效应 = Σ 组合行业权重 × (个股收益 - 行业基准收益)
  交叉效应 = Σ(组合行业权重 - 基准行业权重) × (个股收益 - 行业基准收益)
  择时 = 交叉效应（正=正确的加减仓时机）
"""

from typing import Optional, List

# ── 行业基准收益（默认值，在 analyze 时可通过参数覆盖） ────
# 结构：{行业名: 期间的收益率（小数）}
DEFAULT_INDUSTRY_RETURNS = {
    "消费电子代工": 0.05,
    "消费电子": 0.04,
    "半导体设计": 0.08,
    "半导体设备": 0.07,
    "AI算力": 0.10,
    "电力设备": 0.03,
    "电网自动化": 0.02,
    "新能源汽车": 0.06,
    "白酒": 0.01,
    "银行": 0.02,
    "公用事业": 0.01,
    # 未列出的行业默认用大盘
}

# 大盘默认收益
DEFAULT_MARKET_RETURN = 0.03


def _pct_str(value: float) -> str:
    """将小数转为带正负号的百分比字符串。"""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.2f}%"


def _safe_div(a: float, b: float) -> float:
    """安全除法，除零返回 0。"""
    if b is None or b == 0:
        return 0.0
    return a / b


def attribution_analysis(
    holdings_snapshot: List[dict],
    industry_returns: Optional[dict] = None,
    market_return: Optional[float] = None,
    risk_free_rate: float = 0.02,
) -> dict:
    """
    逐笔归因分析。

    参数 holdings_snapshot:
    [
        {
            "code": "002475",
            "name": "立讯精密",
            "industry": "消费电子代工",
            "weight_at_entry": 0.30,    # 建仓时占组合权重
            "current_weight": 0.28,      # 当前权重（因价格变动/加减仓）
            "entry_price": 68.0,         # 买入均价
            "current_price": 75.0,       # 当前价
            "stock_return": 0.103,       # 该标的期间收益（可替代 entry/current 自动计算）
        },
        ...
    ]

    参数：
        holdings_snapshot — 持仓快照列表
        industry_returns — 行业期间收益率 dict {行业名: 收益率小数}
        market_return — 大盘期间收益率，默认 3%
        risk_free_rate — 无风险利率（年化），默认 2%

    返回：
    {
        "total_return": float,
        "excess_return": float,
        "attribution": {
            "stock_picking": float,
            "sector_allocation": float,
            "timing": float,
            "residual": float,
        },
        "attribution_pct": {
            "stock_picking": str,
            "sector_allocation": str,
            "timing": str,
            "residual": str,
        },
        "details": [...],
        "managers_alpha": float,
        "summary": str,
    }
    """
    # ── 参数默认值 ──
    if industry_returns is None:
        industry_returns = {}
    if market_return is None:
        market_return = DEFAULT_MARKET_RETURN

    # 合并行业收益：用户提供 > 默认字典 > 大盘
    _ind_returns = dict(DEFAULT_INDUSTRY_RETURNS)
    _ind_returns.update(industry_returns)

    # ── Step 1: 计算每只股票收益 ──
    computed = []
    for h in holdings_snapshot:
        stock_return = h.get("stock_return")
        if stock_return is None:
            entry = h.get("entry_price")
            current = h.get("current_price")
            if entry and current and entry > 0:
                stock_return = (current - entry) / entry
            else:
                stock_return = 0.0

        entry_weight = h.get("weight_at_entry", 0.0) or 0.0
        current_weight = h.get("current_weight", 0.0) or 0.0
        industry = h.get("industry", "未知")
        code = h.get("code", "")
        name = h.get("name", "")

        # 查行业基准收益
        ind_ret = _ind_returns.get(industry, market_return)

        computed.append({
            "code": code,
            "name": name,
            "industry": industry,
            "stock_return": stock_return,
            "industry_return": ind_ret,
            "entry_weight": entry_weight,
            "current_weight": current_weight,
            "excess": stock_return - ind_ret,
            "contribution": current_weight * stock_return,
        })

    # ── 行业权重聚合 ──
    # 当前组合行业权重
    ind_current_weight = {}
    for c in computed:
        ind = c["industry"]
        ind_current_weight[ind] = ind_current_weight.get(ind, 0.0) + c["current_weight"]

    # 基准行业权重（假设等权重或按实际组合初始权重）
    # 简化：使用 entry_weight 聚合作为"基准"行业权重
    ind_bench_weight = {}
    for c in computed:
        ind = c["industry"]
        ind_bench_weight[ind] = ind_bench_weight.get(ind, 0.0) + c["entry_weight"]

    # 归一化
    total_current = sum(ind_current_weight.values())
    total_bench = sum(ind_bench_weight.values())

    if total_current > 0:
        for k in ind_current_weight:
            ind_current_weight[k] /= total_current
    if total_bench > 0:
        for k in ind_bench_weight:
            ind_bench_weight[k] /= total_bench

    # 所有涉及的行业
    all_industries = set(list(ind_current_weight.keys()) + list(ind_bench_weight.keys()))

    # ── Step 3/4/5: 计算三项效应 ──
    allocation_effect = 0.0
    selection_effect = 0.0
    cross_effect = 0.0

    details = []
    for c in computed:
        ind = c["industry"]
        cw = ind_current_weight.get(ind, 0.0)
        bw = ind_bench_weight.get(ind, 0.0)
        ir = c["industry_return"]
        sr = c["stock_return"]

        # 配置效应 = (组合行业权重 - 基准行业权重) × 行业收益
        ae = (cw - bw) * ir

        # 选股效应 = 组合行业权重 × (个股收益 - 行业收益)
        se = cw * (sr - ir)

        # 交叉效应 = (组合行业权重 - 基准行业权重) × (个股收益 - 行业收益)
        ce = (cw - bw) * (sr - ir)

        allocation_effect += ae
        selection_effect += se
        cross_effect += ce

        details.append({
            "code": c["code"],
            "name": c["name"],
            "industry": ind,
            "stock_return": round(sr, 6),
            "industry_return": round(ir, 6),
            "excess": round(sr - ir, 6),
            "contribution": round(cw * sr, 6),
            "allocation_effect": round(ae, 6),
            "selection_effect": round(se, 6),
        })

    # ── Step 6: 计算组合总收益 / 超额收益 / Alpha ──
    total_return = sum(d["contribution"] for d in details)
    excess_return = total_return - market_return
    managers_alpha = excess_return - (allocation_effect + cross_effect)  # Alpha ≈ 选股收益
    residual = excess_return - (allocation_effect + selection_effect + cross_effect)

    attribution = {
        "stock_picking": round(selection_effect, 6),
        "sector_allocation": round(allocation_effect, 6),
        "timing": round(cross_effect, 6),
        "residual": round(residual, 6),
    }

    result = {
        "total_return": round(total_return, 6),
        "excess_return": round(excess_return, 6),
        "attribution": attribution,
        "attribution_pct": {k: _pct_str(v) for k, v in attribution.items()},
        "details": details,
        "managers_alpha": round(managers_alpha, 6),
        "summary": summary_attribution({
            "total_return": total_return,
            "excess_return": excess_return,
            "attribution": attribution,
        }),
    }

    return result


def summary_attribution(result: dict) -> str:
    """
    将归因结果转化为一句话摘要。

    例：
    "当期组合收益+8.5%，超额大盘+5.5%。归因：选股贡献+3.2%，行业配置+1.5%，择时+0.8%"
    """
    tr = result.get("total_return", 0.0)
    er = result.get("excess_return", 0.0)
    attr = result.get("attribution", {})

    sp = attr.get("stock_picking", 0.0)
    sa = attr.get("sector_allocation", 0.0)
    ti = attr.get("timing", 0.0)

    parts = [
        f"当期组合收益{_pct_str(tr)}",
        f"超额大盘{_pct_str(er)}",
    ]
    items = [
        f"选股贡献{_pct_str(sp)}",
        f"行业配置{_pct_str(sa)}",
        f"择时{_pct_str(ti)}",
    ]
    parts.append("归因：" + "，".join(items))
    return "。".join(parts)


def compare_periods(period_results: List[dict]) -> dict:
    """
    多期归因对比。

    参数 period_results: [attribution_analysis() 的结果, ...]
    每期可以是不同月份/季度。

    返回：
    {
        "periods": [{"period_label": str, ...}, ...],
        "cumulative_picking": float,
        "cumulative_allocation": float,
        "cumulative_timing": float,
        "cumulative_excess": float,
        "alpha_volatility": float,
        "info_ratio": float,
    }
    """
    if not period_results:
        return {
            "periods": [],
            "cumulative_picking": 0.0,
            "cumulative_allocation": 0.0,
            "cumulative_timing": 0.0,
            "cumulative_excess": 0.0,
            "alpha_volatility": 0.0,
            "info_ratio": 0.0,
        }

    periods = []
    total_picking = 0.0
    total_allocation = 0.0
    total_timing = 0.0
    total_excess = 0.0
    alpha_list = []

    for i, r in enumerate(period_results):
        label = r.get("period_label", f"第{i+1}期")
        attr = r.get("attribution", {})
        alphas = r.get("managers_alpha", 0.0)
        excess = r.get("excess_return", 0.0)

        periods.append({
            "period_label": label,
            "total_return": r.get("total_return", 0.0),
            "excess_return": excess,
            "stock_picking": attr.get("stock_picking", 0.0),
            "sector_allocation": attr.get("sector_allocation", 0.0),
            "timing": attr.get("timing", 0.0),
            "managers_alpha": alphas,
        })

        total_picking += attr.get("stock_picking", 0.0)
        total_allocation += attr.get("sector_allocation", 0.0)
        total_timing += attr.get("timing", 0.0)
        total_excess += excess
        alpha_list.append(alphas)

    # Alpha 波动率（标准差）
    n = len(alpha_list)
    if n > 1:
        mean_alpha = sum(alpha_list) / n
        variance = sum((a - mean_alpha) ** 2 for a in alpha_list) / n
        alpha_vol = variance ** 0.5
    else:
        alpha_vol = 0.0

    # 信息比率 = 平均超额收益 / Alpha波动率
    info_ratio = _safe_div(total_excess / n, alpha_vol) if n > 0 else 0.0

    return {
        "periods": periods,
        "cumulative_picking": round(total_picking, 6),
        "cumulative_allocation": round(total_allocation, 6),
        "cumulative_timing": round(total_timing, 6),
        "cumulative_excess": round(total_excess, 6),
        "alpha_volatility": round(alpha_vol, 6),
        "info_ratio": round(info_ratio, 6),
    }


__all__ = [
    "attribution_analysis",
    "summary_attribution",
    "compare_periods",
    "DEFAULT_INDUSTRY_RETURNS",
    "DEFAULT_MARKET_RETURN",
]
