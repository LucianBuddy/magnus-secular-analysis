"""
magnus-secular-analysis 数据预处理模块
======================================
在 Step 1 数据采集完成后、Step 2 分析前调用。
所有输入通过参数传递，不进 LLM 上下文。输出结构化的数据摘要 dict `ss`。
"""

from typing import Any, Optional


# ── ss 数据摘要结构 ──────────────────────────────────────────

SS_SCHEMA = {
    # meta
    "ts": "", "td": "", "src": "", "em_ok": False,
    # K线/技术
    "p": 0.0, "ma5": 0.0, "ma10": 0.0, "ma20": 0.0,
    "v5": 0.0, "v20": 0.0,
    "pe": 0.0, "pb": 0.0, "mc": 0.0, "turn": 0.0,
    "pe_h": [], "pb_h": [],
    "kl10": [],
    # 财务
    "roe": [], "dr": 0.0, "idr": 0.0, "gm": [],
    "rg": [], "pg": [],
    "ocf": 0.0, "np": 0.0, "bvps": 0.0,
    "oe_avg": 0.0, "oe_pr": [0.0, 0.0],
    # 资金
    "f_yd": 0.0, "f_20d": 0.0, "f_ok": False,
    # 市场
    "ix_sh": 0.0, "ix_sz": 0.0, "ix_cyb": 0.0,
    "cblk": [], "ind": "",
    # 预期
    "eps": 0.0, "eps_src": "",
}


def new_ss() -> dict:
    """返回一个空的 ss 字典副本。"""
    return dict(SS_SCHEMA)


# ── K线列索引 ────────────────────────────────────────────────
# 百度18字段K线索引：
# [0]=ts [1]=date [2]=open [3]=close [4]=vol
# [5]=high [6]=low [7]=amt [12]=ma5 [14]=ma10 [16]=ma20

def compute_pe_history(closes: list[float], ttm_eps: float) -> list[float]:
    """计算 PE 历史序列。不足60根取实际根数。"""
    if not ttm_eps or ttm_eps <= 0:
        return []
    return [c / ttm_eps for c in closes]


def compute_pb_history(closes: list[float], bvps: float) -> list[float]:
    """计算 PB 历史序列。"""
    if not bvps or bvps <= 0:
        return []
    return [c / bvps for c in closes]


# ── 同行数据处理 ────────────────────────────────────────────

def filter_peers(peers: list[dict]) -> list[dict]:
    """
    剔除 PE>100 的 outlier。
    若剔除后不足2家，返回空列表，caller 应 fallback 板块 PE 均值。
    """
    valid = [p for p in peers if abs(p.get("pe", 0) or 0) <= 100]
    return valid if len(valid) >= 2 else []


def compute_industry_median_pe(peers: list[dict],
                                block_pe: Optional[float] = None) -> float:
    """计算同行 PE 中位数，不可用时 fallback 板块 PE。"""
    filtered = filter_peers(peers)
    if filtered:
        pes = sorted([p["pe"] for p in filtered if p.get("pe")])
        n = len(pes)
        if n == 0:
            return block_pe or 0.0
        mid = n // 2
        return float(pes[mid]) if n % 2 else (pes[mid - 1] + pes[mid]) / 2.0
    return block_pe or 0.0


# ── 现金转化率 / 盈利质量分析 ──────────────────────────────

class CashConvResult:
    """现金转化率分析结果。"""
    __slots__ = (
        "ocf_data_mismatch",
        "earnings_quality_poor",
        "cash_gen_strong",
        "oe_available",
        "oe_approx",
        "warning",
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
    revenue_3y: Optional[list[float]] = None,
    net_profit_3y: Optional[list[float]] = None,
    depreciation_3y: Optional[list[float]] = None,
    capex_3y: Optional[list[float]] = None,
    is_light_asset: bool = False,
) -> CashConvResult:
    """
    完整现金转化率与 Owner Earnings 分析。

    参数说明：
        ocf, np            — 当年经营现金流、净利润
        cashflow_np        — 现金流量表中的净利润（可能与利润表不同期）
        depreciation       — 当年折旧摊销
        capex              — 购建固定资产支付的现金
        accounts_receivable_delta — 应收账款变动
        inventory_delta    — 存货变动
        prepaid_delta      — 预付账款变动
        revenue_3y         — 近3年营收
        net_profit_3y      — 近3年净利润
        depreciation_3y    — 近3年折旧
        capex_3y           — 近3年资本开支
        is_light_asset     — 是否为轻资产行业 (fabless/软件/设计等)
    """
    r = CashConvResult()

    # ── 两表数据一致性检查 ──
    if cashflow_np is not None:
        if cashflow_np == 0:
            r.ocf_data_mismatch = True
            # 用近似比率
            if np != 0:
                approx_conv = ocf / np
                if approx_conv < 0:
                    r.earnings_quality_poor = True
                    # 进一步区分：检查应收/存货
                    net_working_delta = (accounts_receivable_delta
                                         + inventory_delta)
                    if net_working_delta > 0:
                        r.warning = "现金转化率负: 应收+存货大幅增加"
                    else:
                        r.warning = "现金转化率负: 需进一步核实"
        elif abs(cashflow_np - np) / max(abs(np), 1) > 0.20:
            r.ocf_data_mismatch = True  # 差异>20%，两表不同期

    # ── 经营现金流为负但利润为正 ──
    if ocf < 0 and np > 0:
        r.earnings_quality_poor = True
        r.warning = "OCF为负但净利润为正，盈利质量差"

    # ── 现金转化率分类 ──
    if np != 0:
        cash_conv_ratio = ocf / np

        if cash_conv_ratio > 1.20:
            # 现金生成极强：不仅利润全部变现还额外产出现金
            r.cash_gen_strong = True
            r.warning = "现金利润超额覆盖——Q5增强证据"

        elif cash_conv_ratio > 0.80 and np != 0 and depreciation / abs(np) < 0.20:
            # 高现金转化率+低折旧，OE≈净利润
            r.oe_available = True
            r.oe_approx = np

        elif cash_conv_ratio < 0.60:
            # 低转化率，检查应收/存货
            if accounts_receivable_delta > 0:
                r.warning = "回款延迟"
            elif inventory_delta > 0:
                r.warning = "备货周期，销售后可转化"
            else:
                r.warning = "需进一步核实"

    # ── OE 可用性判断 ──
    if r.ocf_data_mismatch or r.earnings_quality_poor:
        r.oe_available = False
        return r

    # ── Owner Earnings 计算（3年均值） ──
    if net_profit_3y and depreciation_3y and capex_3y:
        oe_values = []
        for i in range(min(len(net_profit_3y), len(depreciation_3y),
                           len(capex_3y))):
            _np = net_profit_3y[i]
            _dep = depreciation_3y[i]
            _capex = capex_3y[i]

            # 维持性资本开支
            if is_light_asset:
                maint_capex = _dep * 0.3  # 无形资产摊销非现金支出
            else:
                maint_capex = min(_capex * 0.7, _dep)

            # 营运资本增量
            wc_delta = (accounts_receivable_delta
                        + inventory_delta
                        + prepaid_delta)

            oe = _np + _dep - maint_capex - wc_delta
            oe_values.append(oe)

        if oe_values:
            r.oe_approx = sum(oe_values) / len(oe_values)

    return r


# ── PE/PB 估值分位 ──────────────────────────────────────────

def estimate_percentile(data: list[float], current: float) -> float:
    """
    估算当前值在历史数据中的分位（0~1）。
    数据不足时返回 0.5（中位），避免极端判断。
    """
    if len(data) < 5:
        return 0.5
    below = sum(1 for v in data if v < current)
    return below / len(data)


# ── 整体预处理函数 ──────────────────────────────────────────

def build_summary(
    code: str,
    name: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    amounts: list[float],
    ma5_list: list[float],
    ma10_list: list[float],
    ma20_list: list[float],
    current_price: float,
    pe: float,
    pb: float,
    market_cap: float,
    turnover: float,
    bvps: float,
    ttm_eps: float,
    roe_3y: list[float],
    gross_margin_3y: list[float],
    debt_ratio: float,
    interest_debt_ratio: float,
    revenue_growth: list[float],
    profit_growth: list[float],
    ocf: float,
    np: float,
    cashflow_np: Optional[float] = None,
    depreciation_3y: Optional[list[float]] = None,
    capex_3y: Optional[list[float]] = None,
    net_profit_3y: Optional[list[float]] = None,
    fund_flow_today: float = 0.0,
    fund_flow_20d: float = 0.0,
    fund_flow_ok: bool = False,
    ix_sh: float = 0.0,
    ix_sz: float = 0.0,
    ix_cyb: float = 0.0,
    concept_blocks: Optional[list[str]] = None,
    industry: str = "",
    eps_forecast: float = 0.0,
    eps_source: str = "",
    peers: Optional[list[dict]] = None,
    is_light_asset: bool = False,
    accounts_receivable_delta: float = 0,
    inventory_delta: float = 0,
    prepaid_delta: float = 0,
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

        recent = closes[-n:]
        recent_v = volumes[-n:] if len(volumes) >= n else volumes
        ss["v5"] = sum(recent_v[-5:]) / 5 if len(recent_v) >= 5 else 0.0
        ss["v20"] = sum(recent_v[-20:]) / 20 if len(recent_v) >= 20 else 0.0

        # 最近10根K线摘要
        k10 = closes[-10:] if n >= 10 else closes
        h10 = highs[-10:] if len(highs) >= 10 else highs
        l10 = lows[-10:] if len(lows) >= 10 else lows
        ss["kl10"] = list(zip(k10, h10, l10))

        # PE/PB 历史
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
    ss["ind"] = industry

    # ── 预期 ──
    ss["eps"] = eps_forecast
    ss["eps_src"] = eps_source

    # ── OE 预计算 ──
    cash = analyze_cash_conversion(
        ocf=ocf,
        np=np,
        cashflow_np=cashflow_np,
        depreciation=depreciation_3y[-1] if depreciation_3y else 0,
        capex=capex_3y[-1] if capex_3y else 0,
        accounts_receivable_delta=accounts_receivable_delta,
        inventory_delta=inventory_delta,
        prepaid_delta=prepaid_delta,
        revenue_3y=None,
        net_profit_3y=net_profit_3y,
        depreciation_3y=depreciation_3y,
        capex_3y=capex_3y,
        is_light_asset=is_light_asset,
    )

    if cash.oe_available and cash.oe_approx != 0:
        ss["oe_avg"] = cash.oe_approx
        # 价格区间: [保守价(15x), 乐观价(20x)]
        ss["oe_pr"] = [
            round(cash.oe_approx * 15, 2),
            round(cash.oe_approx * 20, 2),
        ]

    return ss
