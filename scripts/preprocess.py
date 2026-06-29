"""
magnus-secular-analysis 数据预处理模块（重构 shim）
===================================================
从子模块导入 + 本地保留 SS_SCHEMA/new_ss/build_summary。
向后兼容：from scripts.preprocess import build_summary 仍然可用。
"""

from typing import Optional, Any

# ── 从子模块导入所有公共符号（向后兼容） ────────────────

from .peer_engine import *
from .valuation import *
from .cash_quality import *
from .risk import *
from .position import *


# ── ss 数据摘要结构 ──────────────────────────────────────────

SS_SCHEMA = {
    # meta
    "ts": "", "td": "",
    # K线/技术
    "p": 0.0, "ma5": 0.0, "ma10": 0.0, "ma20": 0.0, "ma60": 0.0,
    "v5": 0.0, "v20": 0.0,
    "volatility_60d": 0.0,
    "pe": 0.0, "pb": 0.0, "mc": 0.0, "turn": 0.0,
    "pe_h": [], "pb_h": [],
    "kl10": [],
    # 财务
    "roe": [], "dr": 0.0, "idr": 0.0, "gm": [],
    "rg": [], "pg": [],
    "ocf": 0.0, "np": 0.0, "bvps": 0.0,
    "cash_conv_3y": [],
    "oe_avg": 0.0, "oe_pr": [0.0, 0.0],
    # 价值陷阱
    "value_trap_score": 0, "value_trap_warnings": [],
    # 再评估触发器
    "re_eval_triggers": [],
    # 资金
    "f_yd": 0.0, "f_20d": 0.0, "f_ok": False,
    "fallback_cblk_attempted": False,
    # 市场
    "ix_sh": 0.0, "ix_sz": 0.0, "ix_cyb": 0.0,
    "cblk": [], "ind": "",
    # 预期
    "eps": 0.0,
}


def new_ss() -> dict:
    """返回一个空的 ss 字典副本。"""
    return dict(SS_SCHEMA)


# ── K线列索引 ────────────────────────────────────────────────
# 百度18字段K线索引：
# [0]=ts [1]=date [2]=open [3]=close [4]=vol
# [5]=high [6]=low [7]=amt [12]=ma5 [14]=ma10 [16]=ma20


# ── 整体预处理函数 ──────────────────────────────────────────

def build_summary(
    code: str,
    name: str,
    closes: list,
    highs: list,
    lows: list,
    volumes: list,
    amounts: list,
    ma5_list: list,
    ma10_list: list,
    ma20_list: list,
    current_price: float,
    pe: float,
    pb: float,
    market_cap: float,
    turnover: float,
    bvps: float,
    ttm_eps: float,
    roe_3y: list,
    gross_margin_3y: list,
    debt_ratio: float,
    interest_debt_ratio: float,
    revenue_growth: list,
    profit_growth: list,
    ocf: float,
    np: float,
    # P1-3: ocf_3y（向前兼容，保留 ocf）
    ocf_3y: Optional[list] = None,
    cashflow_np: Optional[float] = None,
    depreciation_3y: Optional[list] = None,
    capex_3y: Optional[list] = None,
    net_profit_3y: Optional[list] = None,
    fund_flow_today: float = 0.0,
    fund_flow_20d: float = 0.0,
    fund_flow_ok: bool = False,
    ix_sh: float = 0.0,
    ix_sz: float = 0.0,
    ix_cyb: float = 0.0,
    concept_blocks: Optional[list] = None,
    industry: str = "",
    eps_forecast: float = 0.0,
    eps_source: str = "",
    peers: Optional[list] = None,
    is_light_asset: bool = False,
    accounts_receivable_delta: float = 0,
    inventory_delta: float = 0,
    prepaid_delta: float = 0,
    # P0-2: Eastmoney 失败时自动触发 web_fetch fallback
    web_fetcher: Optional = None,
    ppe_turnover: Optional[float] = None,
    asset_age_years: Optional[float] = None,
) -> dict:
    """
    构建完整的 ss 数据摘要字典。

    该函数封装了从原始数据到 ss 结构的全部转换逻辑：
    - PE/PB 历史序列
    - 现金转化率 & Owner Earnings 预计算
    - 同行过滤
    - 近10根K线摘要
    - 均线/均量

    返回 ss dict，直接供 Step 2 分析使用。
    """
    ss = new_ss()
    ss["ts"] = code
    ss["td"] = name

    # ── 技术指标 ──
    n = min(len(closes), 60) if closes else 0
    if n > 0:
        ss["p"] = closes[-1]
        ss["ma5"] = ma5_list[-1] if ma5_list and len(ma5_list) >= n else 0.0
        ss["ma10"] = ma10_list[-1] if ma10_list and len(ma10_list) >= n else 0.0
        ss["ma20"] = ma20_list[-1] if ma20_list and len(ma20_list) >= n else 0.0

        if len(closes) >= 60:
            ss["ma60"] = sum(closes[-60:]) / 60.0
        elif len(closes) >= 20:
            ss["ma60"] = sum(closes[-20:]) / 20.0

        if len(closes) >= 20:
            import math
            log_returns = []
            for i in range(1, min(len(closes), 60)):
                if closes[i-1] > 0:
                    log_returns.append(math.log(closes[i] / closes[i-1]))
            if log_returns:
                mean_r = sum(log_returns) / len(log_returns)
                variance = sum((r - mean_r) ** 2 for r in log_returns) / len(log_returns)
                ss["volatility_60d"] = round(math.sqrt(variance * 252) * 100, 2)

        recent = closes[-n:]
        recent_v = volumes[-n:] if len(volumes) >= n else volumes
        ss["v5"] = sum(recent_v[-5:]) / 5 if len(recent_v) >= 5 else 0.0
        ss["v20"] = sum(recent_v[-20:]) / 20 if len(recent_v) >= 20 else 0.0

        k10 = closes[-10:] if n >= 10 else closes
        h10 = highs[-10:] if len(highs) >= 10 else highs
        l10 = lows[-10:] if len(lows) >= 10 else lows
        ss["kl10"] = list(zip(k10, h10, l10))

        ss["pe_h"] = compute_pe_history(closes, ttm_eps)
        ss["pb_h"] = compute_pb_history(closes, bvps)

    # ── 估值/市值 ──
    ss["pe"] = pe
    ss["pb"] = pb
    ss["mc"] = market_cap
    ss["turn"] = turnover
    ss["bvps"] = bvps

    # ── 财务 ──
    ss["roe"] = roe_3y
    ss["dr"] = debt_ratio
    ss["idr"] = interest_debt_ratio
    ss["gm"] = gross_margin_3y
    ss["rg"] = revenue_growth
    ss["pg"] = profit_growth
    ss["ocf"] = ocf
    ss["np"] = np

    # ── 资金 ──
    ss["f_yd"] = fund_flow_today
    ss["f_20d"] = fund_flow_20d
    ss["f_ok"] = fund_flow_ok

    # ── 市场 ──
    ss["ix_sh"] = ix_sh
    ss["ix_sz"] = ix_sz
    ss["ix_cyb"] = ix_cyb
    ss["cblk"] = concept_blocks or []
    ss["fallback_cblk_attempted"] = False

    if not fund_flow_ok and (not concept_blocks) and web_fetcher is not None:
        try:
            result_text = web_fetcher("同花顺 " + name + " 概念板块")
            import re
            candidates = re.findall(r'[\u4e00-\u9fa5]{2,8}板块', str(result_text))
            if candidates:
                ss["cblk"] = list(set(candidates))[:10]
                ss["fallback_cblk_attempted"] = True
        except Exception:
            pass

    ss["ind"] = industry

    # ── 预期 ──
    ss["eps"] = eps_forecast
    ss["eps_src"] = eps_source

    # ── 多期现金转化率（P1-3: 支持真实三年 OCF） ──
    if ocf != 0 and np != 0:
        cash_conv_3y = []
        if ocf_3y is not None and len(ocf_3y) >= 3:
            np_list = net_profit_3y or []
            for i in range(min(len(ocf_3y), len(np_list))):
                ocf_i = ocf_3y[i]
                np_i = np_list[i]
                if np_i != 0:
                    cash_conv_3y.append(round(ocf_i / np_i, 2))
        elif len(net_profit_3y or []) >= 3:
            for i in range(len(net_profit_3y)):
                np_i = net_profit_3y[i]
                if np_i != 0:
                    cash_conv_3y.append(round(ocf / np_i, 2))
        ss["cash_conv_3y"] = cash_conv_3y

    # ── 价值陷阱检查 ──
    vt = value_trap_check(
        ss["rg"] if len(ss["rg"]) >= 3 else None,
        ss["gm"], ss["dr"], ss["pe"], ocf / np if np != 0 else 0)
    ss["value_trap_score"] = vt["score"]
    ss["value_trap_warnings"] = vt["warnings"]

    # ── 再评估触发器 ──
    triggers = compute_triggers(ss["gm"], ss["dr"], ss["pe"], ss["pe_h"])
    ss["re_eval_triggers"] = triggers

    # ── OE 预计算 ──
    cash = analyze_cash_conversion(
        ocf=ocf, np=np, cashflow_np=cashflow_np,
        depreciation=depreciation_3y[-1] if depreciation_3y else 0,
        capex=capex_3y[-1] if capex_3y else 0,
        accounts_receivable_delta=accounts_receivable_delta,
        inventory_delta=inventory_delta, prepaid_delta=prepaid_delta,
        revenue_3y=None, net_profit_3y=net_profit_3y,
        depreciation_3y=depreciation_3y, capex_3y=capex_3y,
        is_light_asset=is_light_asset,
        ppe_turnover=ppe_turnover, asset_age_years=asset_age_years,
    )

    if cash.oe_available and cash.oe_approx != 0:
        ss["oe_avg"] = cash.oe_approx
        oe_mult = get_oe_multiple(industry)
        ss["oe_pr"] = [
            round(cash.oe_approx * oe_mult["conservative"], 2),
            round(cash.oe_approx * oe_mult["optimistic"], 2),
        ]
        ss["oe_cost_of_equity"] = oe_mult["cost_of_equity"]

    return ss


# ── 重新导出确保 from scripts.preprocess import X 仍可用 ──
# (这些符号已通过 from .peer_engine import * 等导入，明确列出确保兼容)

__all__ = [
    "SS_SCHEMA", "new_ss", "build_summary",
    # 从 peer_engine
    "INDUSTRY_PEER_MAP", "STOCK_TO_INDUSTRY",
    "get_industry", "get_industry_peers",
    "filter_peers", "compute_industry_median_pe",
    "build_competition_matrix",
    # 从 valuation
    "compute_pe_history", "compute_pb_history", "estimate_percentile",
    "compute_forward_pe", "compute_normalized_cagr",
    "compute_dynamic_pe_limit", "compute_valuation_verdict",
    "PE_LIMIT_CONFIG", "DEFAULT_PE_MULTIPLIER",
    "FACTOR_WEIGHT_MAP", "FACTOR_WEIGHT_DEFAULT", "get_factor_weights",
    "get_rf_rate", "get_inflation_rate", "get_cost_of_equity",
    "get_oe_multiple", "margin_of_safety_continuous",
    "scenario_analysis", "_holding_adjustment", "_clean_ss",
    "INDUSTRY_BETA", "DEFAULT_BETA", "ERP_CHINA",
    "REVIEW_DIR", "review_accuracy", "review_accuracy_extended",
    # 从 cash_quality
    "CashConvResult", "analyze_cash_conversion",
    "infer_moat_trend", "roe_quality", "value_trap_check",
    "auto_is_light_asset", "LIGHT_ASSET_INDUSTRIES",
    # 从 risk
    "market_regime_adjustment", "sell_condition_check", "compute_triggers",
    # 从 position
    "position_sizing", "generate_signal",
]
