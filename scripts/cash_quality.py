"""
cash_quality — 盈利质量分析模块
=================================
现金转化率、Owner Earnings、价值陷阱检查、ROE杜邦拆分、护城河趋势推断。
"""

from typing import Optional


# ── 轻资产行业集合 ──────────────────────────────────────────

LIGHT_ASSET_INDUSTRIES = {
    "半导体设计", "云计算软件", "创新药", "互联网", "白酒", "AI算力",
}


def auto_is_light_asset(industry):
    """根据行业自动判断是否轻资产。"""
    return industry in LIGHT_ASSET_INDUSTRIES


# ── 现金转化率分析 ──────────────────────────────────────────

class CashConvResult:
    """现金转化率分析结果。"""
    __slots__ = (
        "ocf_data_mismatch", "earnings_quality_poor", "cash_gen_strong",
        "oe_available", "oe_approx", "warning",
    )

    def __init__(self):
        self.ocf_data_mismatch = False
        self.earnings_quality_poor = False
        self.cash_gen_strong = False
        self.oe_available = True
        self.oe_approx = 0.0
        self.warning = ""


def analyze_cash_conversion(
    ocf: float,
    np: float,
    cashflow_np: Optional[float] = None,
    depreciation: float = 0,
    capex: float = 0,
    accounts_receivable_delta: float = 0,
    inventory_delta: float = 0,
    prepaid_delta: float = 0,
    revenue_3y: Optional[list] = None,
    net_profit_3y: Optional[list] = None,
    depreciation_3y: Optional[list] = None,
    capex_3y: Optional[list] = None,
    is_light_asset: bool = False,
    ppe_turnover: Optional[float] = None,
    asset_age_years: Optional[float] = None,
) -> CashConvResult:
    """
    完整现金转化率与 Owner Earnings 分析。

    P1-2: 支持 asset_age_years 动态 maint_capex。
    """
    r = CashConvResult()

    # 两表数据一致性检查
    if cashflow_np is not None:
        if cashflow_np == 0:
            r.ocf_data_mismatch = True
            if np != 0:
                approx_conv = ocf / np
                if approx_conv < 0:
                    r.earnings_quality_poor = True
                    net_working_delta = accounts_receivable_delta + inventory_delta
                    if net_working_delta > 0:
                        r.warning = "现金转化率负: 应收+存货大幅增加"
                    else:
                        r.warning = "现金转化率负: 需进一步核实"
        elif abs(cashflow_np - np) / max(abs(np), 1) > 0.20:
            r.ocf_data_mismatch = True

    # OCF为负但利润为正
    if ocf < 0 and np > 0:
        r.earnings_quality_poor = True
        r.warning = "OCF为负但净利润为正，盈利质量差"

    # 现金转化率分类
    if np != 0:
        cash_conv_ratio = ocf / np
        if cash_conv_ratio > 1.20:
            r.cash_gen_strong = True
            r.warning = "现金利润超额覆盖——Q5增强证据"
        elif cash_conv_ratio > 0.80 and np != 0 and depreciation / abs(np) < 0.20:
            r.oe_available = True
            r.oe_approx = np
        elif cash_conv_ratio < 0.60:
            if accounts_receivable_delta > 0:
                r.warning = "回款延迟"
            elif inventory_delta > 0:
                r.warning = "备货周期，销售后可转化"
            else:
                r.warning = "需进一步核实"

    # OE可用性判断
    if r.ocf_data_mismatch or r.earnings_quality_poor:
        r.oe_available = False
        return r

    # Owner Earnings 计算（3年均值）
    if net_profit_3y and depreciation_3y and capex_3y:
        oe_values = []
        for i in range(min(len(net_profit_3y), len(depreciation_3y), len(capex_3y))):
            _np = net_profit_3y[i]
            _dep = depreciation_3y[i]
            _capex = capex_3y[i]

            if asset_age_years is not None and asset_age_years > 1:
                maint_capex = _dep * (1 - min(1.0, 1.0 / asset_age_years))
            elif is_light_asset:
                maint_capex = _dep * 0.3
            else:
                maint_capex = min(_capex * 0.7, _dep)

            wc_delta = accounts_receivable_delta + inventory_delta + prepaid_delta
            oe = _np + _dep - maint_capex - wc_delta
            oe_values.append(oe)

        if oe_values:
            r.oe_approx = sum(oe_values) / len(oe_values)

    return r


# ── ROE 质量分解（杜邦拆分）─────────────────────────────────

def roe_quality(debt_ratio: float, roe: float, net_profit_margin: float) -> dict:
    """
    从杜邦拆分角度判断 ROE 的质量来源（小数格式）。

    返回: {label, risk(low/medium/high), detail}
    """
    if debt_ratio > 0.6 and roe > 0.12:
        return {"label": "高杠杆驱动", "risk": "高",
                "detail": "负债率>60%，ROE靠杠杆放大，盈利质量打折扣"}
    elif debt_ratio > 0.6 and roe <= 0.12:
        return {"label": "高杠杆+低回报", "risk": "极高",
                "detail": "杠杆高但ROE低，资产回报效率不足"}
    elif debt_ratio < 0.3 and roe > 0.15:
        return {"label": "高质量盈利", "risk": "低",
                "detail": "低杠杆+高ROE，真本事"}
    elif net_profit_margin > 0.15 and roe > 0.12 and debt_ratio < 0.5:
        return {"label": "高利润率驱动", "risk": "低",
                "detail": "高利润率+低杠杆，ROE质量高且可持续"}
    elif net_profit_margin > 0.15 and roe > 0.08:
        return {"label": "利润率驱动", "risk": "中低",
                "detail": "靠利润率驱动但ROE绝对值一般"}
    else:
        return {"label": "正常", "risk": "中",
                "detail": "杠杆和利润率均在正常范围"}


# ── 价值陷阱检查 ────────────────────────────────────────────

def value_trap_check(rg_3y, gm_3y, dr, pe, ocf_ratio):
    """
    识别价值陷阱（score 0-10, >=6高风险, >=4需警惕）。

    评分维度（每项+2）：营收萎缩+低PE, 毛利率连降+低PE, 高负债+低PE, 现金转化率差, 双重恶化。
    """
    score = 0
    warnings = []

    if rg_3y and len(rg_3y) >= 3:
        if all(r <= 0 for r in rg_3y[-3:]):
            if pe and pe < 20:
                score += 2
                warnings.append("营收连续3年萎缩但PE<20: 挣死钱陷阱")
        if rg_3y[-1] < rg_3y[-3] * 0.8:
            score += 1
            if "营收加速下滑" not in str(warnings):
                warnings.append("营收加速下滑")

    if gm_3y and len(gm_3y) >= 3:
        if gm_3y[-1] < gm_3y[-3] * 0.9:
            if pe and pe < 20:
                score += 2
                warnings.append("毛利率连续下降+低PE: 护城河腐蚀")

    if dr and dr > 0.6:
        if pe and pe < 15:
            score += 2
            warnings.append("高负债率(%d%%)+低PE: 杠杆陷阱" % (dr * 100))

    if ocf_ratio is not None and ocf_ratio < 0.5:
        score += 2
        warnings.append("现金转化率(%.1f)<0.5: 盈利质量差" % ocf_ratio)

    if score >= 3:
        extra = 0
        if rg_3y and all(r <= 0 for r in rg_3y[-3:]):
            extra += 1
        if gm_3y and gm_3y[-1] < gm_3y[-3] * 0.9:
            extra += 1
        if extra >= 2:
            score += 1
            warnings.append("营收和毛利率双重恶化: 结构性衰退风险")

    return {"score": min(score, 10), "warnings": warnings[:5], "is_trap": score >= 6}


# ── 护城河趋势量化推断 ──────────────────────────────────────

def infer_moat_trend(gm_3y, roe_3y):
    """从毛利率和 ROE 的三年趋势推断护城河方向。"""
    if len(gm_3y) < 3 or len(roe_3y) < 3:
        return "数据不足"
    gm_trend = gm_3y[-1] - gm_3y[0]
    roe_trend = roe_3y[-1] - roe_3y[0]
    strengthening = (1 if gm_trend > 2 else 0) + (1 if roe_trend > 2 else 0)
    weakening = (1 if gm_trend < -2 else 0) + (1 if roe_trend < -2 else 0)
    if strengthening >= 2:
        return "增强"
    if weakening >= 2:
        return "削弱"
    if strengthening == 1 and weakening == 0:
        return "偏增强"
    if weakening == 1 and strengthening == 0:
        return "偏削弱"
    return "稳定"


# ── 财务异常检测 ──────────────────────────────────────

ANOMALY_RULES = {
    "receivables_mismatch": {
        "label": "应收异常",
        "severity": "中",
        "rule": "应收增速 > 营收增速 × 1.5"
    },
    "ocf_divergence": {
        "label": "OCF/净利润背离",
        "severity": "高",
        "rule": "OCF增速 < 净利润增速 × 0.5 持续2年"
    },
    "gm_increase_with_decline": {
        "label": "异常毛利率",
        "severity": "中",
        "rule": "毛利率升高但营收下降"
    },
    "asset_impairment_surge": {
        "label": "资产减值突增",
        "severity": "中",
        "rule": "资产减值损失同比增>100%"
    },
    "goodwill_risk": {
        "label": "商誉风险",
        "severity": "高",
        "rule": "商誉/净资产>30%"
    },
    "revenue_quality": {
        "label": "营收质量",
        "severity": "中",
        "rule": "营收增长但经营现金流下降持续2年"
    },
}


def financial_anomaly_detection(
    # 应收相关（需要逐期数据）
    accounts_receivable_3y=None,
    # 营收数据
    revenue_3y=None,
    # OCF/净利润
    ocf_3y=None,
    np_3y=None,
    # 毛利率
    gm_3y=None,
    # 商誉
    goodwill_to_equity=0.0,
    # 资产减值
    asset_impairment_latest=0.0,
    asset_impairment_prev=0.0,
):
    """
    检查 6 类财务异常。

    参数均为可选——只检测有数据提供的维度。

    返回列表，每项：
    {
        "type": str,          # 异常类型名
        "label": str,         # 显示标签
        "severity": str,      # "高" / "中" / "低"
        "detail": str,        # 详细说明
        "triggered": bool,
    }

    检测规则：
    1. 应收/营收匹配：如果应收增速 > 营收增速×1.5 → triggered
    2. OCF/净利润背离：如果 ocf_3y[-1]/np_3y[-1] < 0.6 且 连续下降 → triggered
       (但如果 ocf_3y[-1] < 0 且 np_3y[-1] > 0 直接标记高)
    3. 异常毛利率：gm_3y[-1] > gm_3y[-3] 且 revenue_3y[-1] < revenue_3y[-3] → triggered
    4. 资产减值突增：asset_impairment_latest > asset_impairment_prev × 2 → triggered
    5. 商誉风险：goodwill_to_equity > 0.30 → triggered
    6. 营收质量：revenue_3y[-1] > revenue_3y[-3] 且 ocf_3y[-1] < ocf_3y[-3] → triggered
    """
    results = []

    # 1. 应收/营收匹配
    if accounts_receivable_3y is not None and revenue_3y is not None:
        if len(accounts_receivable_3y) >= 2 and len(revenue_3y) >= 2:
            ar_growth = (accounts_receivable_3y[-1] - accounts_receivable_3y[-2]) / max(abs(accounts_receivable_3y[-2]), 1)
            rev_growth = (revenue_3y[-1] - revenue_3y[-2]) / max(abs(revenue_3y[-2]), 1)
            triggered = ar_growth > rev_growth * 1.5 and rev_growth > 0
            results.append({
                "type": "receivables_mismatch",
                "label": "应收异常",
                "severity": "中",
                "detail": "应收增速(%.1f%%) > 营收增速(%.1f%%) × 1.5" % (ar_growth * 100, rev_growth * 100),
                "triggered": triggered,
            })

    # 2. OCF/净利润背离
    if ocf_3y is not None and np_3y is not None:
        if len(ocf_3y) >= 1 and len(np_3y) >= 1:
            triggered = False
            severity = "中"
            detail = ""
            # 最新一期OCF为负且净利润为正 → 直接标记高
            if ocf_3y[-1] < 0 and np_3y[-1] > 0:
                triggered = True
                severity = "高"
                detail = "OCF为负(%.2f)但净利润为正(%.2f)，盈利质量极差" % (ocf_3y[-1], np_3y[-1])
            elif abs(np_3y[-1]) > 0:
                ratio = ocf_3y[-1] / np_3y[-1]
                if len(ocf_3y) >= 3 and len(np_3y) >= 3:
                    prev_ratio = ocf_3y[-2] / np_3y[-2] if abs(np_3y[-2]) > 0 else 0
                    declining = ratio < prev_ratio
                    if ratio < 0.6 and declining:
                        triggered = True
                        severity = "高"
                        detail = "OCF/NP=%.2f 连续下降（上期=%.2f）" % (ratio, prev_ratio)
                if not triggered and ratio < 0.6:
                    triggered = True
                    detail = "OCF/NP=%.2f < 0.6" % ratio
            if not detail and triggered:
                detail = "OCF/净利润背离"
            if np_3y[-1] == 0:
                triggered = False
                detail = "净利润为0，无法计算OCF/NP比率"
            results.append({
                "type": "ocf_divergence",
                "label": "OCF/净利润背离",
                "severity": severity,
                "detail": detail,
                "triggered": triggered,
            })

    # 3. 异常毛利率
    if gm_3y is not None and revenue_3y is not None:
        if len(gm_3y) >= 3 and len(revenue_3y) >= 3:
            triggered = gm_3y[-1] > gm_3y[-3] and revenue_3y[-1] < revenue_3y[-3]
            results.append({
                "type": "gm_increase_with_decline",
                "label": "异常毛利率",
                "severity": "中",
                "detail": "毛利率从 %.2f%% 升至 %.2f%%，但营收从 %.2f 降至 %.2f" % (
                    gm_3y[-3], gm_3y[-1], revenue_3y[-3], revenue_3y[-1]),
                "triggered": triggered,
            })

    # 4. 资产减值突增
    if asset_impairment_latest != 0.0 or asset_impairment_prev != 0.0:
        if asset_impairment_prev != 0:
            triggered = asset_impairment_latest > asset_impairment_prev * 2
            results.append({
                "type": "asset_impairment_surge",
                "label": "资产减值突增",
                "severity": "中",
                "detail": "本期减值 %.2f > 上期 %.2f × 2" % (asset_impairment_latest, asset_impairment_prev),
                "triggered": triggered,
            })

    # 5. 商誉风险
    if goodwill_to_equity > 0:
        triggered = goodwill_to_equity > 0.30
        results.append({
            "type": "goodwill_risk",
            "label": "商誉风险",
            "severity": "高",
            "detail": "商誉/净资产 = %.2f%%" % (goodwill_to_equity * 100),
            "triggered": triggered,
        })

    # 6. 营收质量
    if revenue_3y is not None and ocf_3y is not None:
        if len(revenue_3y) >= 3 and len(ocf_3y) >= 3:
            triggered = revenue_3y[-1] > revenue_3y[-3] and ocf_3y[-1] < ocf_3y[-3]
            results.append({
                "type": "revenue_quality",
                "label": "营收质量",
                "severity": "中",
                "detail": "营收从 %.2f 增至 %.2f，但经营现金流从 %.2f 降至 %.2f" % (
                    revenue_3y[-3], revenue_3y[-1], ocf_3y[-3], ocf_3y[-1]),
                "triggered": triggered,
            })

    return results


# ── __all__ ──────────────────────────────────────────────────

__all__ = [
    "CashConvResult", "analyze_cash_conversion",
    "infer_moat_trend", "roe_quality", "value_trap_check",
    "auto_is_light_asset", "LIGHT_ASSET_INDUSTRIES",
]
