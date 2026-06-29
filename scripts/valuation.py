"""
valuation — 估值计算模块
=========================
PE/PB 历史序列、前向PE、PEG、安全边际、DDM、OE 倍数、情景分析、
行业因子权重、后验复盘等。
"""

from typing import Optional

from .peer_engine import get_industry


# ── PE/PB 历史 ──────────────────────────────────────────────

def compute_pe_history(closes, ttm_eps=None, eps_history=None):
    """
    计算 PE 历史序列。

    双模式：
      - eps_history（长度匹配 closes）→ 逐期精确
      - 仅 ttm_eps → 用当前 TTM EPS 反代（有偏）
    """
    if eps_history and len(eps_history) == len(closes):
        result = []
        for c, e in zip(closes, eps_history):
            if e and e > 0:
                result.append(c / e)
        return result
    if not ttm_eps or ttm_eps <= 0:
        return []
    return [c / ttm_eps for c in closes]


def compute_pb_history(closes, bvps):
    """计算 PB 历史序列。"""
    if not bvps or bvps <= 0:
        return []
    return [c / bvps for c in closes]


def estimate_percentile(data, current):
    """估算当前值在历史数据中的分位（0~1），不足5样本返回0.5。"""
    if len(data) < 5:
        return 0.5
    below = sum(1 for v in data if v < current)
    return below / len(data)


# ── 前向PE（基数效应防护）──────────────────────────────────

def compute_forward_pe(market_cap, quarterly_net_profits):
    """
    计算前向PE，要求所有季度净利润为正（基数效应防护）。
    返回: {"pe": float, "valid": bool, "reason": str}
    """
    if len(quarterly_net_profits) < 4:
        return {"pe": 0, "valid": False, "reason": "季度数据不足4期"}
    for i, np_val in enumerate(quarterly_net_profits):
        if np_val <= 0:
            return {"pe": 0, "valid": False,
                    "reason": "Q%d净利润为负或零，前向PE受基数效应干扰，不计算" % (i+1)}
    annualized = sum(quarterly_net_profits)
    if annualized <= 0:
        return {"pe": 0, "valid": False, "reason": "年化净利润为负"}
    fpe = market_cap / annualized
    return {"pe": round(fpe, 2), "valid": True, "reason": ""}


# ── PE容忍上限配置 ─────────────────────────────────────────

PE_LIMIT_CONFIG = {
    "半导体设备":      {"multiplier": 1.8, "base_label": "板块中位PE×1.8"},
    "半导体设计":      {"multiplier": 2.0, "base_label": "板块中位PE×2.0"},
    "半导体封测":      {"multiplier": 1.5, "base_label": "板块中位PE×1.5"},
    "AI算力":         {"multiplier": 1.8, "base_label": "板块中位PE×1.8"},
    "消费电子":       {"multiplier": 1.5, "base_label": "板块中位PE×1.5"},
    "消费电子代工":    {"multiplier": 1.3, "base_label": "板块中位PE×1.3"},
    "创新药":         {"multiplier": 3.0, "base_label": "亏损可接受，参照PS"},
    "新能源汽车":      {"multiplier": 1.5, "base_label": "板块中位PE×1.5"},
    "光伏":           {"multiplier": 1.5, "base_label": "板块中位PE×1.5"},
    "电力设备":       {"multiplier": 1.5, "base_label": "板块中位PE×1.5"},
    "电网自动化":     {"multiplier": 1.5, "base_label": "板块中位PE×1.5"},
    "白酒":           {"multiplier": 1.5, "base_label": "板块中位PE×1.5"},
    "银行":           {"multiplier": 1.2, "base_label": "板块中位PE×1.2"},
    "保险":           {"multiplier": 1.3, "base_label": "板块中位PE×1.3"},
    "机器":           {"multiplier": 1.5, "base_label": "板块中位PE×1.5"},
    "公用事业":       {"multiplier": 1.3, "base_label": "板块中位PE×1.3"},
}
DEFAULT_PE_MULTIPLIER = 1.5


# ── 行业因子加权矩阵（P1-1）─────────────────────────────────

FACTOR_WEIGHT_MAP = {
    "消费电子": {"客户集中度": 0.25, "资金流": 0.20, "均线系统": 0.25, "美股传导": 0.15, "事件驱动": 0.15},
    "消费电子代工": {"客户集中度": 0.30, "资金流": 0.25, "均线系统": 0.20, "美股传导": 0.15, "事件驱动": 0.10},
    "白酒": {"毛利率趋势": 0.35, "库存周期": 0.25, "资金流": 0.20, "均线系统": 0.20},
    "半导体设计": {"技术迭代": 0.25, "资金流": 0.20, "均线系统": 0.20, "美股传导": 0.20, "事件驱动": 0.15},
    "半导体设备": {"国产替代": 0.30, "资金流": 0.20, "均线系统": 0.20, "事件驱动": 0.15, "美股传导": 0.15},
    "半导体封测": {"产能利用率": 0.25, "资金流": 0.25, "均线系统": 0.20, "美股传导": 0.15, "事件驱动": 0.15},
    "AI算力": {"技术路线": 0.25, "资本开支": 0.20, "资金流": 0.20, "均线系统": 0.20, "美股传导": 0.15},
    "创新药": {"管线进展": 0.30, "资金流": 0.20, "均线系统": 0.20, "集采风险": 0.15, "事件驱动": 0.15},
    "医疗器械": {"集采风险": 0.25, "资金流": 0.20, "毛利率趋势": 0.20, "均线系统": 0.20, "事件驱动": 0.15},
    "新能源汽车": {"产能过剩": 0.25, "资金流": 0.20, "均线系统": 0.20, "美股传导": 0.18, "事件驱动": 0.17},
    "光伏": {"产能过剩": 0.30, "资金流": 0.20, "均线系统": 0.20, "政策环境": 0.15, "事件驱动": 0.15},
    "电力设备": {"电网投资": 0.25, "资金流": 0.20, "均线系统": 0.20, "事件驱动": 0.18, "毛利率趋势": 0.17},
    "电网自动化": {"政策环境": 0.25, "资金流": 0.20, "均线系统": 0.25, "事件驱动": 0.15, "毛利率趋势": 0.15},
    "银行": {"净息差": 0.30, "不良率": 0.25, "资金流": 0.20, "政策环境": 0.15, "均线系统": 0.10},
    "保险": {"新业务价值": 0.25, "资金流": 0.20, "均线系统": 0.20, "利率环境": 0.20, "事件驱动": 0.15},
    "证券": {"市场成交额": 0.25, "资金流": 0.25, "均线系统": 0.20, "政策环境": 0.15, "事件驱动": 0.15},
    "互联网": {"用户增长": 0.25, "资金流": 0.20, "均线系统": 0.20, "美股传导": 0.20, "事件驱动": 0.15},
    "云计算软件": {"客户粘性": 0.25, "资金流": 0.20, "均线系统": 0.20, "美股传导": 0.20, "事件驱动": 0.15},
    "军工": {"政策环境": 0.25, "资金流": 0.20, "均线系统": 0.20, "事件驱动": 0.20, "毛利率趋势": 0.15},
    "家电": {"毛利率趋势": 0.25, "库存周期": 0.20, "资金流": 0.20, "均线系统": 0.20, "事件驱动": 0.15},
    "食品饮料": {"毛利率趋势": 0.30, "库存周期": 0.20, "资金流": 0.20, "均线系统": 0.15, "事件驱动": 0.15},
    "煤炭": {"大宗商品": 0.30, "资金流": 0.20, "均线系统": 0.20, "政策环境": 0.15, "事件驱动": 0.15},
    "公用事业": {"政策环境": 0.25, "资金流": 0.20, "均线系统": 0.20, "资本开支": 0.20, "利率环境": 0.15},
    "机械": {"资金流": 0.25, "均线系统": 0.25, "事件驱动": 0.20, "美股传导": 0.15, "毛利率趋势": 0.15},
    "化工新材料": {"大宗商品": 0.25, "资金流": 0.20, "均线系统": 0.20, "产能周期": 0.20, "事件驱动": 0.15},
    "通信": {"资本开支": 0.25, "资金流": 0.20, "均线系统": 0.20, "政策环境": 0.18, "事件驱动": 0.17},
    "汽车零部件": {"客户集中度": 0.25, "资金流": 0.20, "均线系统": 0.20, "毛利率趋势": 0.20, "事件驱动": 0.15},
    "机器人": {"技术迭代": 0.25, "资金流": 0.20, "均线系统": 0.20, "事件驱动": 0.18, "美股传导": 0.17},
}

FACTOR_WEIGHT_DEFAULT = {
    "均线系统": 0.25, "资金流": 0.20, "量价关系": 0.20,
    "事件驱动": 0.20, "美股传导": 0.15,
}


def get_factor_weights(industry: str) -> dict:
    """返回行业因子权重配置，未配置的行业返回通用兜底。"""
    return FACTOR_WEIGHT_MAP.get(industry, FACTOR_WEIGHT_DEFAULT).copy()


# ── 归一化CAGR ──────────────────────────────────────────────

def compute_normalized_cagr(net_profits, years=3):
    """中位数法平滑 CAGR，消除周期基数效应。"""
    if len(net_profits) < years + 1:
        return 0.0
    recent = net_profits[-(years + 1):]
    sorted_profits = sorted(recent[1:])
    median = sorted_profits[len(sorted_profits) // 2]
    base = recent[0]
    if base <= 0:
        return 0.0
    ratio = median / base
    if ratio <= 0:
        return -0.5
    cagr = ratio ** (1.0 / years) - 1.0
    return max(min(cagr, 2.0), -0.99)


# ── 动态PE上限 ─────────────────────────────────────────────

def compute_dynamic_pe_limit(code, block_median_pe):
    """动态PE容忍上限：板块中位PE × 行业系数。"""
    try:
        ind = get_industry(code)
    except NameError:
        ind = "机械"

    cfg = PE_LIMIT_CONFIG.get(ind, {"multiplier": DEFAULT_PE_MULTIPLIER})
    multi = cfg.get("multiplier", DEFAULT_PE_MULTIPLIER)

    if block_median_pe and block_median_pe > 0 and block_median_pe < 500:
        limit_pe = round(block_median_pe * multi, 1)
        label = cfg.get("base_label", "板块中位PE×%.1f" % multi)
    else:
        abs_limits = {
            "半导体设备": 50, "半导体设计": 60, "半导体封测": 35,
            "AI算力": 60, "消费电子": 30, "消费电子代工": 25,
            "创新药": 999, "新能源汽车": 40, "光伏": 40,
            "电力设备": 35, "电网自动化": 35, "白酒": 40,
            "银行": 10, "保险": 15,
        }
        limit_pe = abs_limits.get(ind, 30)
        label = "绝对值(板块PE不可用)"

    return {"industry": ind, "limit_pe": limit_pe, "multiplier": multi,
            "label": label, "absolute_fallback": limit_pe}


# ── 估值裁决矩阵 ───────────────────────────────────────────

def compute_valuation_verdict(pe, cagr, block_median_pe, pe_limit, industry=""):
    """三步裁决预计算：PEG + 板块溢价 + 容忍上限。"""
    if cagr and cagr > 0:
        peg = pe / (cagr * 100)
    else:
        peg = 999

    if peg >= 3.0:
        peg_label = "高估"
    elif peg >= 2.0:
        peg_label = "偏高"
    elif peg >= 1.0:
        peg_label = "合理"
    else:
        peg_label = "低估"

    if block_median_pe and block_median_pe > 0:
        premium = round(pe / block_median_pe, 2)
        premium_label = "严重溢价" if premium >= 2.0 else ("偏贵" if premium >= 1.5 else "合理")
    else:
        premium = 0
        premium_label = "数据不足"

    over_limit = pe > pe_limit if pe_limit > 0 else False
    peg_overvalued = peg_label in ("高估", "偏高")
    pe_overvalued = over_limit

    if peg_overvalued and pe_overvalued:
        verdict, action = "双重确认偏高", "卖出/减仓"
    elif not peg_overvalued and pe_overvalued:
        verdict, action = "行业修正抵消，持有可接受", "持有"
    elif peg_overvalued and not pe_overvalued:
        verdict, action = "分歧大，保守操作", "观望/减仓"
    else:
        verdict, action = "双低估，强烈建议买入", "买入"

    return {
        "peg": round(peg, 2) if peg < 999 else None,
        "peg_label": peg_label,
        "premium": premium,
        "premium_label": premium_label,
        "pe_limit": pe_limit,
        "over_limit": over_limit,
        "verdict": verdict,
        "action": action,
        "detail": "PEG=%.1f(%s) 板块溢价=%.1fx(%s) 上限=%.0fx(%s)" % (
            peg if peg < 999 else 0, peg_label, premium, premium_label,
            pe_limit, "超限" if over_limit else "正常"),
    }


# ── 市场利率 ───────────────────────────────────────────────

def get_rf_rate():
    """实时获取中国10Y国债收益率，失败 fallback 2.0%。"""
    import requests
    try:
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_BOND.getBondInfo?code=zy101466"
        r = requests.get(url, timeout=5, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/bond/"})
        data = r.json()
        if data and isinstance(data, list) and len(data) > 0:
            rate = float(data[0].get("price", 0))
            if 0.5 < rate < 5.0:
                return round(rate, 2)
    except Exception:
        pass
    try:
        url2 = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=zy101466,day,,,1,qfq"
        r2 = requests.get(url2, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        d2 = r2.json()
        data2 = d2.get("data", {})
        if data2:
            for key in ["zy101466", "qt"]:
                if key in data2:
                    klines = data2[key].get("day", [])
                    if klines and len(klines) > 0:
                        rate = float(klines[-1][2])
                        if 0.5 < rate < 5.0:
                            return round(rate, 2)
    except Exception:
        pass
    return 2.0


def get_inflation_rate():
    """获取 CPI 通胀率，fallback 2.0%。"""
    import requests
    try:
        url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
               "?sortColumns=REPORT_DATE&sortTypes=-1&pageSize=1&pageNumber=1"
               "&reportName=RPT_MACRO_CPI&columns=CPI_MONTH_SA&source=WEB&client=WEB")
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        d = r.json()
        data_list = d.get("result", {}).get("data", [])
        if data_list and len(data_list) > 0:
            cpi = float(data_list[0].get("CPI_MONTH_SA", 2.0))
            if 0 < cpi < 10:
                return round(cpi, 1)
    except Exception:
        pass
    return 2.0


# ── 权益风险溢价与行业β ─────────────────────────────────

INDUSTRY_BETA = {
    "半导体设计": 1.4, "半导体设备": 1.3, "半导体封测": 1.2,
    "AI算力": 1.5, "消费电子": 1.1, "消费电子代工": 1.0,
    "互联网": 1.3, "云计算软件": 1.2, "创新药": 1.1,
    "医疗器械": 0.9, "新能源汽车": 1.2, "光伏": 1.3,
    "电力设备": 1.0, "电网自动化": 0.9, "机器人": 1.2,
    "机械": 1.0, "军工": 1.0, "白酒": 0.8,
    "食品饮料": 0.8, "家电": 0.8, "银行": 0.7,
    "保险": 0.9, "证券": 1.3, "煤炭": 1.1,
    "公用事业": 0.6, "化工新材料": 1.0, "汽车零部件": 1.0, "通信": 1.1,
}
DEFAULT_BETA = 1.0
ERP_CHINA = 0.065


def get_cost_of_equity(industry="", rf=None):
    """股权资本成本 = rf + β × ERP。返回 {cost_of_equity(%), beta, rf(%), erp(%)}"""
    if rf is None:
        rf_pct = get_rf_rate()
    else:
        rf_pct = rf
    rf_dec = rf_pct / 100.0
    coe_dec = rf_dec + INDUSTRY_BETA.get(industry, DEFAULT_BETA) * ERP_CHINA
    return {
        "cost_of_equity": round(coe_dec * 100, 2),
        "beta": INDUSTRY_BETA.get(industry, DEFAULT_BETA),
        "rf": rf_pct,
        "erp": round(ERP_CHINA * 100, 1),
    }


def get_oe_multiple(industry=""):
    """
    根据股权资本成本计算 OE 估值倍数。
    保守=1/coe, 乐观=1/(coe-0.5%)。
    """
    coe_data = get_cost_of_equity(industry)
    coe_pct = coe_data["cost_of_equity"]
    coe = coe_pct / 100.0
    if coe <= 0.04:
        coe = 0.06
    if coe >= 0.15:
        coe = 0.12
    conservative = round(1.0 / coe, 1)
    optimistic = round(1.0 / max(coe - 0.005, 0.04), 1)
    return {
        "conservative": conservative, "optimistic": optimistic,
        "cost_of_equity": coe_pct, "beta": coe_data["beta"],
    }


# ── 安全边际连续评分 ─────────────────────────────────────

def margin_of_safety_continuous(current_price, intrinsic_median, conviction_high=False):
    """连续安全边际评分（0-100）。"""
    if not intrinsic_median or intrinsic_median <= 0:
        return {"score": 50, "margin_premium": 0, "label": "数据不足", "action": "观望"}

    margin_premium = (current_price - intrinsic_median) / intrinsic_median

    if margin_premium >= 0.30:
        score = max(0, 20 - int((margin_premium - 0.30) * 100))
        label = "严重高估"; action = "卖出"
    elif margin_premium >= 0.10:
        score = 40 - int((margin_premium - 0.10) * 100)
        label = "偏高"; action = "观望/减仓"
    elif margin_premium >= -0.10:
        score = 50 - int(margin_premium * 50)
        label = "合理"; action = "持有"
    elif margin_premium >= -0.20:
        score = 65 - int((margin_premium + 0.10) * 150)
        label = "偏低"; action = "可买入"
    elif margin_premium >= -0.30:
        score = 80 - int((margin_premium + 0.20) * 100)
        label = "低估"; action = "买入"
    else:
        score = 90; label = "显著低估"; action = "强烈买入"

    if conviction_high and margin_premium < -0.10:
        score = min(100, score + 10)
        if score >= 85:
            label = "显著低估"; action = "强烈买入"

    score = max(0, min(100, score))

    # 避免循环引用：直接内联 position_sizing 逻辑
    if margin_premium <= -0.30 and conviction_high:
        pos = {"pct": 0.80, "label": "重仓", "detail": "边际>30%+高置信度"}
    elif margin_premium <= -0.20:
        pos = {"pct": 0.50, "label": "半仓", "detail": "边际>20%"}
    elif margin_premium <= -0.10:
        pos = {"pct": 0.30, "label": "轻仓", "detail": "边际>10%"}
    elif margin_premium >= 0.30:
        pos = {"pct": 0.0, "label": "清仓", "detail": "溢价>30%"}
    elif margin_premium >= 0.10:
        pos = {"pct": 0.0, "label": "不持有", "detail": "溢价>10%"}
    else:
        pos = {"pct": 0.0, "label": "观望", "detail": "边际不足10%"}

    return {
        "score": score, "margin_premium": round(margin_premium, 2),
        "label": label, "action": action, "position": pos,
    }


# ── 情景分析 ─────────────────────────────────────────────

def scenario_analysis(oe_base, rg_3y, gm_3y, industry=""):
    """三情景估值分析（悲观OE-20%×倍0.85 ~ 乐观OE+15%×倍1.10）。"""
    mult = get_oe_multiple(industry)
    base_mult = (mult["conservative"] + mult["optimistic"]) / 2.0

    scenarios = [
        {"name": "悲观", "oe_adjust": "-20%", "multiple_adjust": "-15%",
         "oe": round(oe_base * 0.80, 2), "multiple": round(base_mult * 0.85, 1),
         "value": round(oe_base * 0.80 * round(base_mult * 0.85, 1), 2)},
        {"name": "基准", "oe_adjust": "0%", "multiple_adjust": "0%",
         "oe": round(oe_base, 2), "multiple": round(base_mult, 1),
         "value": round(oe_base * base_mult, 2)},
        {"name": "乐观", "oe_adjust": "+15%", "multiple_adjust": "+10%",
         "oe": round(oe_base * 1.15, 2), "multiple": round(base_mult * 1.10, 1),
         "value": round(oe_base * 1.15 * round(base_mult * 1.10, 1), 2)},
    ]

    values = [s["value"] for s in scenarios]
    range_pct = round((values[2] - values[0]) / values[1] * 100, 1)

    return {"scenarios": scenarios, "range_pct": range_pct, "span": "%s ~ %s" % (values[0], values[2])}


# ── 持有期修正 ───────────────────────────────────────────

def _holding_adjustment(holding_months):
    """根据持有期调整安全边际系数。"""
    if holding_months >= 12:
        return 1.0
    elif holding_months >= 6:
        return 1.2
    elif holding_months >= 3:
        return 1.4
    else:
        return 1.5


# ── SS_SCHEMA 清理 ────────────────────────────────────────

def _clean_ss(ss):
    """清理 ss 中的无用字段。"""
    return {k: v for k, v in ss.items() if k not in ("src", "eps_src")}


# ── 单因子验证 ───────────────────────────────────────────────

def evaluate_single_factor(predictions: list, actuals: list) -> float:
    """
    评估单个因子的方向预测准确率。

    参数：
        predictions — [1, -1, 0, ...] 因子方向（+1看多, -1看空, 0中性）
        actuals     — [0.05, -0.02, ...] 实际涨跌幅

    返回：
        0-1 的准确率
    """
    if not predictions or not actuals:
        return 0.0

    n = min(len(predictions), len(actuals))
    if n == 0:
        return 0.0

    correct = 0
    for i in range(n):
        pred_dir = predictions[i]
        actual_dir = 1 if actuals[i] > 0 else (-1 if actuals[i] < 0 else 0)
        if pred_dir == 0:
            # 中性预测：实际波动小也算对
            if abs(actuals[i]) < 0.03:
                correct += 1
            continue
        if pred_dir == actual_dir:
            correct += 1

    return round(correct / n, 4)


# ── 因子权重滚动优化（P2-5）───────────────────────────────

def optimize_factor_weights(industry: str,
                            backtest_records: list = None) -> dict:
    """
    根据回测历史记录滚动优化因子权重。

    对过去 N 个季度的回测记录做单因子准确率回溯：
    - 逐个因子单独作为唯一信号的预测准确率
    - 以准确率为权重归一化

    参数：
        industry         — 行业名
        backtest_records — 可选的回测记录列表（每季度一条）
                           [{quarter: "2026Q1", factors: {factor1: +/-1, ...},
                             actual_chg: 0.05}, ...]

    返回：
        {因子名: 权重, ...}

    如果 backtest_records 为 None 或不足 4 个记录，返回静态
    FACTOR_WEIGHT_MAP 的值（不优化）。
    """
    base_weights = get_factor_weights(industry)

    if backtest_records is None or len(backtest_records) < 4:
        return base_weights

    # 提取所有因子名
    all_factors = set()
    for rec in backtest_records:
        all_factors.update(rec.get("factors", {}).keys())

    if not all_factors:
        return base_weights

    # 对每个因子计算准确率
    factor_accuracy = {}
    for factor in all_factors:
        predictions = []
        actuals = []
        for rec in backtest_records:
            factors = rec.get("factors", {})
            if factor in factors:
                pred_dir = factors[factor]
                # pred_dir should be +/-1 or 0
                if isinstance(pred_dir, (int, float)) and pred_dir != 0:
                    predictions.append(int(pred_dir))
                    actuals.append(rec.get("actual_chg", 0))

        if len(predictions) >= 4:
            factor_accuracy[factor] = evaluate_single_factor(predictions, actuals)

    if not factor_accuracy:
        return base_weights

    # 以准确率为权重归一化
    total_acc = sum(factor_accuracy.values())
    if total_acc <= 0:
        return base_weights

    optimized = {}
    for factor, acc in factor_accuracy.items():
        optimized[factor] = round(acc / total_acc, 4)

    # 补齐权重未覆盖的因子（用原有权重按比例缩放）
    remaining = 1.0 - sum(optimized.values())
    if remaining > 0 and len(base_weights) > len(optimized):
        base_missing = {k: v for k, v in base_weights.items() if k not in optimized}
        total_missing = sum(base_missing.values())
        if total_missing > 0:
            for k, v in base_missing.items():
                optimized[k] = round(v / total_missing * remaining + optimized.get(k, 0), 4)

    return optimized


# ── 后验复盘 ─────────────────────────────────────────────────

REVIEW_DIR = None


def review_accuracy(predictions, actuals):
    """后验复盘：对比预测 vs 实际，输出偏差统计。"""
    if not predictions or not actuals:
        return {"status": "no_data", "count": 0}
    correct = 0
    total = len(predictions)
    details = []
    for p in predictions:
        matches = [a for a in actuals if a.get("code") == p["code"]]
        if not matches:
            continue
        a = matches[-1]
        actual_chg = a.get("chg_pct", 0)
        verdict_direction = {"买入": 1, "持有": 0, "观望": 0, "卖出": -1}
        pred_dir = verdict_direction.get(p.get("verdict", ""), 0)
        if pred_dir > 0 and actual_chg > 0:
            correct += 1; direction_ok = True
        elif pred_dir < 0 and actual_chg < 0:
            correct += 1; direction_ok = True
        elif pred_dir == 0 and abs(actual_chg) < 5:
            correct += 1; direction_ok = True
        else:
            direction_ok = False
        details.append({"code": p["code"], "verdict": p.get("verdict", ""),
                        "actual_chg_pct": actual_chg, "direction_ok": direction_ok,
                        "target_price": p.get("target_price")})
    return {"status": "ok", "count": total, "correct": correct,
            "accuracy": round(correct / total, 2) if total > 0 else 0, "details": details}


def review_accuracy_extended(predictions, actuals):
    """扩展后验复盘：方向胜率 + 盈亏比 + 按信号分拆。"""
    base = review_accuracy(predictions, actuals)
    if base["status"] == "no_data":
        return base
    gains_buy, losses_buy, gains_sell, losses_sell = [], [], [], []
    by_type = {"买入": [], "卖出": [], "持有": []}
    for d in base.get("details", []):
        chg = d.get("actual_chg_pct", 0)
        v = d.get("verdict", "")
        if v == "买入":
            (gains_buy if chg > 0 else losses_buy).append(chg)
            by_type["买入"].append({"chg": chg, "ok": d["direction_ok"]})
        elif v == "卖出":
            (gains_sell if chg < 0 else losses_sell).append(chg)
            by_type["卖出"].append({"chg": chg, "ok": d["direction_ok"]})
    avg_gain_buy = round(sum(gains_buy) / len(gains_buy), 1) if gains_buy else 0
    avg_loss_buy = round(sum(losses_buy) / len(losses_buy), 1) if losses_buy else 0
    win_loss_ratio = round(abs(avg_gain_buy / avg_loss_buy), 2) if avg_loss_buy != 0 else 0
    base["extended"] = {"avg_gain_when_buy": avg_gain_buy, "avg_loss_when_buy": avg_loss_buy,
                        "win_loss_ratio": win_loss_ratio, "by_type": by_type}
    return base


# ── 选股因子结构化 ──────────────────────────────────────

# 所有因子定义（统一管理）
FACTOR_DEF_REGISTRY = {
    "valuation": {
        "因子": "价值因子",
        "计算": lambda ss: "低估" if ss.get("pe", 999) < 15 else ("合理" if ss.get("pe", 999) < 30 else "高估"),
        "分数": lambda ss: 1 if ss.get("pe", 999) < 15 else (0 if ss.get("pe", 999) < 30 else -1),
        "区间": (0, 999),
    },
    "profitability": {
        "因子": "盈利能力因子",
        "计算": lambda ss: "强" if ss.get("roe") and ss["roe"][-1] > 15 else ("中" if ss.get("roe") and ss["roe"][-1] > 8 else "弱"),
        "分数": lambda ss: 1 if ss.get("roe") and ss["roe"][-1] > 15 else (0 if ss.get("roe") and ss["roe"][-1] > 8 else -1),
    },
    "growth": {
        "因子": "成长因子",
        "计算": lambda ss: "高增长" if ss.get("rg") and len(ss["rg"]) > 0 and ss["rg"][-1] > 20 else ("稳定" if ss.get("rg") and len(ss["rg"]) > 0 and ss["rg"][-1] > 5 else "低速"),
        "分数": lambda ss: 1 if ss.get("rg") and len(ss["rg"]) > 0 and ss["rg"][-1] > 20 else (0 if ss.get("rg") and len(ss["rg"]) > 0 and ss["rg"][-1] > 5 else -1),
    },
    "quality": {
        "因子": "质量因子",
        "计算": lambda ss: "优" if ss.get("cash_conv_3y") and len(ss["cash_conv_3y"]) >= 2 and all(c > 0.8 for c in ss["cash_conv_3y"]) else "中",
        "分数": lambda ss: 1 if ss.get("cash_conv_3y") and len(ss["cash_conv_3y"]) >= 2 and all(c > 0.8 for c in ss["cash_conv_3y"]) else (0 if ss.get("cash_conv_3y") and len(ss["cash_conv_3y"]) >= 2 and any(c > 0.6 for c in ss["cash_conv_3y"]) else -1),
    },
    "momentum": {
        "因子": "动量因子",
        "计算": lambda ss: "强" if ss.get("p", 0) > ss.get("ma20", 1) * 1.1 else ("中" if ss.get("p", 0) > ss.get("ma20", 1) else "弱"),
        "分数": lambda ss: 1 if ss.get("p", 0) > ss.get("ma20", 1) * 1.1 else (0 if ss.get("p", 0) > ss.get("ma20", 1) else -1),
    },
    "sentiment": {
        "因子": "情绪因子",
        "计算": lambda ss: "积极" if ss.get("sentiment_score", 0) > 0.3 else ("消极" if ss.get("sentiment_score", 0) < -0.3 else "中性"),
        "分数": lambda ss: 1 if ss.get("sentiment_score", 0) > 0.3 else (-1 if ss.get("sentiment_score", 0) < -0.3 else 0),
    },
    "safety": {
        "因子": "安全性因子",
        "计算": lambda ss: "安全" if ss.get("dr", 100) < 50 else ("关注" if ss.get("dr", 100) < 70 else "高危"),
        "分数": lambda ss: 1 if ss.get("dr", 100) < 50 else (0 if ss.get("dr", 100) < 70 else -1),
    },
}


def compute_factor_scores(ss: dict) -> dict:
    """
    对某只股票的 ss 数据应用所有因子，返回结构化评分。

    返回：
    {
        "total_score": float,          # 总分（各因子分数×权重的和）
        "factors": {
            factor_key: {
                "name": str,
                "score": int,           # -1 ~ 1
                "label": str,           # 可读标签
                "weight": float,        # 来自 FACTOR_WEIGHT_MAP 的行业权重
                "detail": str,
            }
        }
        "n_factors": int,
        "max_score": float,
    }
    """
    industry = ss.get("ind", "")
    factor_weights = get_factor_weights(industry)

    factors = {}
    total_score = 0.0
    total_weight_used = 0.0
    max_possible = 0.0

    for key, defn in FACTOR_DEF_REGISTRY.items():
        try:
            label = defn["计算"](ss)
            score = defn["分数"](ss)
        except Exception:
            label = "数据不足"
            score = 0

        # 查找匹配的权重因子名
        weight = 0.1  # 默认权重
        for wkey, wval in factor_weights.items():
            # 尝试匹配因子名
            name_map = {
                "valuation": ["估值", "PE", "PEG", "价值"],
                "profitability": ["毛利率", "ROE", "盈利", "利润"],
                "growth": ["成长", "增长", "营收"],
                "quality": ["质量", "客户"],
                "momentum": ["均线", "动量"],
                "sentiment": ["资金", "情绪"],
                "safety": ["风险", "安全", "负债", "债务"],
            }
            matched_names = name_map.get(key, [key])
            if any(mn in wkey for mn in matched_names) or wkey in key:
                weight = max(weight, wval)

        total_weight_used += weight
        weighted_score = score * weight
        total_score += weighted_score
        max_possible += 1.0 * weight

        factors[key] = {
            "name": defn["因子"],
            "score": score,
            "label": label,
            "weight": round(weight, 4),
            "detail": "%s→%s (权重=%.0f%%)" % (defn["因子"], label, weight * 100),
        }

    # 归一化总分到 -1 ~ 1
    if max_possible > 0:
        total_score = total_score / max_possible
    else:
        total_score = 0.0

    return {
        "total_score": round(total_score, 4),
        "factors": factors,
        "n_factors": len(factors),
        "max_score": 1.0,
    }


# ── 信号聚合去重（因子相关性分组） ─────────────────────────

FACTOR_CORRELATION_GROUPS = {
    "动量组": ["momentum", "macd_direction", "weekly_trend"],
    "价值组": ["valuation", "pe_band", "pb_band"],
    "质量组": ["quality", "safety", "roe_quality"],
    "情绪组": ["sentiment", "news_density"],
    "成长组": ["growth", "revenue_momentum"],
}

# 因子名称映射（FACTOR_DEF_REGISTRY key → 组名）
_FACTOR_TO_GROUP = {}
for gname, keys in FACTOR_CORRELATION_GROUPS.items():
    for k in keys:
        _FACTOR_TO_GROUP[k] = gname


def deduplicate_factor_signals(factor_scores: dict) -> dict:
    """
    因子信号去重聚合。

    高相关性因子同组取均值（而非累加），避免同一信号被重复计分。
    无分组归属的因子单独计入。

    参数：
        factor_scores — compute_factor_scores() 的返回值

    返回：
        {
            "total_score": float,        # 去重后总分
            "n_groups": int,              # 有效分组数
            "n_ungrouped": int,           # 未分组因子数
            "group_scores": {             # 每组得分
                "动量组": {"mean": 0.0, "n": 2, "members": [...], "group_label": "..."},
                ...
            },
            "ungrouped_factors": {        # 未分组因子
                "safety": {"score": 1, "label": "安全", ...},
            },
            "max_possible": float,        # 理论最大总分（用于归一化）
            "normalized_score": float,    # -1~1 归一化
            "detail": str,
        }
    """
    factors = factor_scores.get("factors", {})
    raw_score = factor_scores.get("total_score", 0.0)
    n_factors = factor_scores.get("n_factors", 0)

    if n_factors == 0 or not factors:
        return {
            "total_score": 0.0, "n_groups": 0, "n_ungrouped": 0,
            "group_scores": {}, "ungrouped_factors": {},
            "max_possible": 0.0, "normalized_score": 0.0,
            "detail": "无因子数据",
        }

    # 按组分桶
    groups = {}
    ungrouped = {}

    for key, data in factors.items():
        grp = _FACTOR_TO_GROUP.get(key)
        if grp:
            if grp not in groups:
                groups[grp] = {"scores": [], "members": [], "names": []}
            groups[grp]["scores"].append(data["score"])
            groups[grp]["members"].append(key)
            groups[grp]["names"].append(data.get("name", key))
        else:
            ungrouped[key] = data

    # 计算各组均值和未分组总分
    group_results = {}
    group_total = 0.0
    n_groups = 0

    for gname, gdata in groups.items():
        mean_score = sum(gdata["scores"]) / len(gdata["scores"])
        group_results[gname] = {
            "mean": round(mean_score, 4),
            "n": len(gdata["scores"]),
            "members": gdata["members"],
            "names": gdata["names"],
            "group_label": FACTOR_CORRELATION_GROUPS[gname] if gname in FACTOR_CORRELATION_GROUPS else gname,
        }
        group_total += mean_score
        n_groups += 1

    # 未分组因子直接累加
    ung_total = 0.0
    ung_results = {}
    for key, data in ungrouped.items():
        ung_results[key] = data
        ung_total += data["score"]

    total = group_total + ung_total
    # 最大可能得分
    max_possible = n_groups * 1.0 + len(ungrouped) * 1.0
    normalized = total / max_possible if max_possible > 0 else 0.0
    normalized = max(-1.0, min(1.0, normalized))

    detail_parts = []
    for gname, gr in group_results.items():
        detail_parts.append("%s=%.2f(%s)" % (gname, gr["mean"], ",".join(gr["names"])))
    for key, data in ung_results.items():
        detail_parts.append("%s=%d(%s)" % (key, data["score"], data.get("name", key)))

    return {
        "total_score": round(total, 4),
        "n_groups": n_groups,
        "n_ungrouped": len(ungrouped),
        "group_scores": group_results,
        "ungrouped_factors": ung_results,
        "max_possible": max_possible,
        "normalized_score": round(normalized, 4),
        "detail": " | ".join(detail_parts),
    }


def factor_radar(summaries: dict) -> dict:
    """
    生成多只股票因子雷达对比。

    参数 summaries: {code: ss_dict, ...}

    返回 {codes: [str], factors: [str], scores: {code: {factor: score}}}
    结构适合直接画雷达图。
    """
    codes = list(summaries.keys())
    factor_names = [defn["因子"] for defn in FACTOR_DEF_REGISTRY.values()]
    factor_keys = list(FACTOR_DEF_REGISTRY.keys())

    scores = {}
    for code, ss in summaries.items():
        factor_scores = compute_factor_scores(ss)
        scores[code] = {}
        for fkey in factor_keys:
            if fkey in factor_scores.get("factors", {}):
                scores[code][fkey] = factor_scores["factors"][fkey]["score"]
            else:
                scores[code][fkey] = 0

    return {
        "codes": codes,
        "factors": factor_names,
        "factor_keys": factor_keys,
        "scores": scores,
    }


# ── __all__ ──────────────────────────────────────────────────

__all__ = [
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
    # v2.1.0
    "optimize_factor_weights",
    "evaluate_single_factor",
]
