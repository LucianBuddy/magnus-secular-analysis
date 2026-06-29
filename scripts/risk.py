"""
risk — 风险模块
================
量化卖出条件、再评估触发器、市场环境调节。
"""

from typing import Optional


# ── 宏观因子配置 ────────────────────────────────────────────

MACRO_FILTERS = {
    "信用收缩": {
        "factor": 0.8,
        "desc": "社融/M2增速连续2月下降，降低权益仓位",
    },
    "经济复苏": {
        "factor": 1.2,
        "desc": "宏观环境支持加大权益暴露",
    },
    "流动性收紧": {
        "factor": 0.7,
        "desc": "利率上行期，高估值标的压力大",
    },
}

DEFAULT_CORRECTION = 0.00  # 正常环境


# ── 市场环境调节因子 ──────────────────────────────────────

def get_rf_trend(period_days=90) -> str:
    """
    通过缓存获取最近 N 天 10Y 国债收益率变化趋势。

    调用 get_rf_rate() 获取近期收益率数据（由 side-effect 缓存）。
    简单判断：最近 N 天内的收益率趋势。

    返回 "上升" / "下降" / "震荡"
    """
    try:
        # 尝试获取短期和长期利率
        from .valuation import get_rf_rate
        # get_rf_rate 不直接缓存历史，这里用多个请求探测趋势
        import requests

        # 腾讯债券 K 线
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=zy101466,day,,,%d,qfq" % (
            max(1, period_days // 120))
        r = requests.get(url, timeout=5, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://stock.qq.com"})
        d = r.json()
        data_sec = d.get("data", {})
        klines = (data_sec.get("zy101466", {}).get("day", [])
                  or data_sec.get("qt", {}).get("zy101466", {}).get("day", [])
                  or [])

        if len(klines) >= 10:
            closes = [float(k[2]) for k in klines if len(k) >= 3 and float(k[2]) > 0.5]
            if len(closes) >= 10:
                # 前半段 vs 后半段
                mid = len(closes) // 2
                first_half_avg = sum(closes[:mid]) / mid
                second_half_avg = sum(closes[mid:]) / (len(closes) - mid)
                diff = second_half_avg - first_half_avg
                if diff > 0.1:
                    return "上升"
                elif diff < -0.1:
                    return "下降"
                else:
                    return "震荡"
    except Exception:
        pass

    return "震荡"


# ── 宏观层安全边际修正（带 rf_trend 的重载版本） ───────────

def macro_regime_adjustment(rf_trend: str = None,
                            market_sentiment: str = "正常") -> dict:
    """
    宏观层安全边际修正（在 market_regime_adjustment 基础上叠加）。

    参数：
        rf_trend         — "上升" / "下降" / "震荡"（由 get_rf_trend 获取）
        market_sentiment — "亢奋" / "正常" / "恐慌" / "震荡"

    返回：
        {"correction": float, "applied_filters": list[str], "description": str}

    修正规则：
        - rf_trend="上升" 且 market_sentiment="亢奋" → correction = 0.10（非常严格）
        - rf_trend="上升" 且 market_sentiment="正常" → correction = 0.05
        - rf_trend="下降" 且 (恐慌/震荡) → correction = -0.05（放宽）
        - 其他情况：correction = market_regime_adjustment(sentiment).correction
    """
    # 自动获取 rf_trend 如果未提供
    if rf_trend is None:
        rf_trend = get_rf_trend()

    applied_filters = []

    # 基础市场情绪修正
    base = market_regime_adjustment_impl(market_sentiment)
    correction = base["correction"]
    description_parts = [base["desc"]]

    # 宏观叠加
    if rf_trend == "上升":
        if market_sentiment == "亢奋":
            correction = 0.10
            applied_filters.append("流动性收紧")
            description_parts.append("利率上行+市场亢奋，安全边际收紧+10%%")
        elif market_sentiment == "正常":
            correction = 0.05
            applied_filters.append("流动性收紧")
            description_parts.append("利率上行，安全边际收紧+5%%")
    elif rf_trend == "下降":
        if market_sentiment in ("恐慌", "震荡"):
            correction = -0.05
            applied_filters.append("经济复苏")
            description_parts.append("利率下行+市场悲观，安全边际放宽-5%%")

    return {
        "correction": correction,
        "applied_filters": applied_filters,
        "description": "；".join(description_parts),
        "rf_trend": rf_trend,
        "market_sentiment": market_sentiment,
    }


def market_regime_adjustment_impl(market_sentiment: str) -> dict:
    """原始版本的 market_regime_adjustment 逻辑。"""
    corrections = {
        "亢奋": {"correction": 0.05, "desc": "市场亢奋期，安全边际收紧+5%"},
        "正常": {"correction": 0.00, "desc": "市场正常，标准安全边际"},
        "恐慌": {"correction": -0.05, "desc": "市场恐慌期，安全边际放宽-5%"},
        "震荡": {"correction": 0.00, "desc": "震荡市，标准安全边际"},
    }
    return corrections.get(market_sentiment, corrections["正常"])


def market_regime_adjustment(market_sentiment: str) -> dict:
    """
    根据市场情绪返回安全边际修正系数。

    参数：market_sentiment — "亢奋" / "正常" / "恐慌" / "震荡"
    返回：{correction: float, desc: str}
    """
    return market_regime_adjustment_impl(market_sentiment)


# ── 量化卖出条件 ─────────────────────────────────────────

def sell_condition_check(code, pe_current, pe_limit, peg, roe, gm_trend, ocf_vs_np, dr):
    """量化卖出条件逐项检查，返回结构化结果。"""
    results = []

    # 条件1：价格严重高估？
    cond1 = pe_current > pe_limit * 1.2 and (peg > 3.0 if peg else False)
    results.append({"num": 1, "label": "价格严重高估", "triggered": cond1,
                    "detail": "PE=%.1f 上限=%.1f PEG=%.1f" % (pe_current, pe_limit, peg or 0)})

    # 条件2：护城河被破坏？
    gm_declining = (len(gm_trend) >= 3 and gm_trend[-1] < gm_trend[-3] * 0.95)
    roe_low = roe[-1] < 8.0 if roe else False
    cond2 = gm_declining or (roe_low and gm_declining)
    results.append({"num": 2, "label": "护城河被破坏", "triggered": cond2,
                    "detail": "毛利趋势=%s ROE=%.1f" % ("↓" if gm_declining else "→", roe[-1] if roe else 0)})

    # 条件3：管理层诚信（LLM判断）
    results.append({"num": 3, "label": "管理层诚信问题", "triggered": False, "detail": "LLM判断: 一票否决"})

    # 条件4：OCF持续为负
    ocf_bad = ocf_vs_np < 0
    results.append({"num": 4, "label": "盈利质量恶化(OCF为负)", "triggered": ocf_bad,
                    "detail": "OCF/NP=%.2f" % ocf_vs_np})

    return {"checks": results, "any_sell": any(r["triggered"] for r in results)}


# ── 再评估触发器 ─────────────────────────────────────────

def compute_triggers(gm_3y, dr, pe, pe_h):
    """从当前数据自动推导再评估触发阈值。"""
    triggers = []

    if gm_3y and len(gm_3y) >= 1:
        current_gm = gm_3y[-1]
        trigger_gm = round(current_gm * 0.85, 1)
        triggers.append({"metric": "毛利率", "current": current_gm,
                         "trigger": "跌破 %.1f%%" % trigger_gm,
                         "reason": "护城河关键指标，毛利率快速下降通常意味着竞争加剧"})

    if dr:
        triggers.append({"metric": "资产负债率", "current": dr * 100,
                         "trigger": "超过 %.0f%%" % (dr * 100 * 1.2),
                         "reason": "负债率上升20%可能触发流动性风险"})

    if pe:
        pe_high = round(pe * 1.5, 1)
        triggers.append({"metric": "PE", "current": pe,
                         "trigger": "高于 %.1f x" % pe_high,
                         "reason": "PE膨胀50%说明价格已远超价值"})
        pe_low = round(pe * 0.5, 1) if pe > 5 else round(pe * 0.7, 1)
        triggers.append({"metric": "PE", "current": pe,
                         "trigger": "低于 %.1f x" % pe_low,
                         "reason": "PE大幅收缩可能意味着基本面恶化"})

    if pe_h and len(pe_h) >= 20:
        median_pe_h = sorted(pe_h)[len(pe_h) // 2]
        triggers.append({"metric": "PE历史新高", "current": round(median_pe_h, 1),
                         "trigger": "历史中位 PE=%.1f" % median_pe_h,
                         "reason": "PE回到历史中位时重新评估估值"})

    return triggers


# ── 行业景气轮动 ──────────────────────────────────────

# 情景定义为 (经济增长, 通胀) 的四象限
CYCLE_MAP = {
    ("复苏", "低"): {
        "label": "复苏+低通胀",
        "prefer": ["消费电子", "半导体设计", "新能源", "AI算力"],
        "avoid": ["公用事业", "食品饮料"],
        "desc": "经济增长加速，通胀温和，对成长型行业最有利",
    },
    ("过热", "高"): {
        "label": "过热+高通胀",
        "prefer": ["煤炭", "有色", "银行", "保险"],
        "avoid": ["消费电子", "创新药"],
        "desc": "通胀上行，货币政策收紧前夕，应转向价值/资源股",
    },
    ("衰退", "低"): {
        "label": "衰退+低通胀",
        "prefer": ["公用事业", "医疗", "食品饮料", "白酒"],
        "avoid": ["周期制造", "资源"],
        "desc": "经济下行，防御性资产优先",
    },
    ("衰退", "高"): {
        "label": "衰退+高通胀（滞胀）",
        "prefer": ["现金", "短债"],
        "avoid": ["全部", "股票"],
        "desc": "滞胀期，规避股票",
    },
    ("复苏", "高"): {
        "label": "复苏+高通胀",
        "prefer": ["银行", "保险"],
        "avoid": ["科技成长"],
        "desc": "经济复苏但通胀偏高，货币政策可能收紧",
    },
}


def estimate_economic_phase(rf_trend: str, cpi: float = None) -> tuple:
    """
    估算当前经济所处阶段。

    使用代理变量（不需要PMI/CPI官方数据）：
    - 经济增长方向 ≈ 沪深300近3个月涨跌（正=增长/负=衰退）
    - 通胀方向 ≈ 10Y国债收益率趋势（上升=高通胀/下降=低通胀）

    参数：
        rf_trend — get_rf_trend() 返回值
        cpi — 可选，若提供额外确认

    返回 (growth_direction, inflation_level) 元组
    growth_direction: "复苏" / "衰退"
    inflation_level: "高" / "低"
    """
    import requests

    # 经济增长方向 ≈ 沪深300近3个月涨跌
    growth_direction = "复苏"
    inflation_level = "低"

    try:
        # 沪深300近3个月
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=000300,day,,,1,qfq"
        r = requests.get(url, timeout=5, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://stock.qq.com",
        })
        d = r.json()
        data_sec = d.get("data", {})
        klines = (data_sec.get("000300", {}).get("day", [])
                  or data_sec.get("qt", {}).get("000300", {}).get("day", [])
                  or [])
        if len(klines) >= 2:
            # 取最新60个交易日（约3个月）
            relevant = klines[-60:]
            start_close = float(relevant[0][2])
            end_close = float(relevant[-1][2])
            chg = (end_close - start_close) / start_close
            if chg > 0:
                growth_direction = "复苏"
            else:
                growth_direction = "衰退"
    except Exception:
        pass

    # 通胀方向 ≈ 10Y国债收益率趋势
    if rf_trend == "上升":
        inflation_level = "高"
    elif rf_trend == "下降":
        inflation_level = "低"
    else:
        # 震荡，再看CPI
        if cpi is not None:
            if cpi > 2.5:
                inflation_level = "高"
            else:
                inflation_level = "低"

    return (growth_direction, inflation_level)


def sector_cycle_advice(industry: str, rf_trend: str = None) -> dict:
    """
    根据当前经济阶段给出行业的配置建议。

    参数：
        industry — 待分析的行业名
        rf_trend — get_rf_trend() 返回值，None则自动获取

    返回：
    {
        "cycle_phase": str,              # 当前所处阶段
        "cycle_description": str,
        "industry_in_prefer": bool,       # 该行业是否在当前偏好中
        "industry_in_avoid": bool,        # 该行业是否在当前规避中
        "sector_adjustment": float,       # 安全边际修正系数（prefer=-0.03, avoid=+0.03, 其他=0）
    }
    """
    if rf_trend is None:
        rf_trend = get_rf_trend()

    growth_dir, infl_level = estimate_economic_phase(rf_trend)
    phase_key = (growth_dir, infl_level)
    phase_info = CYCLE_MAP.get(phase_key, {
        "label": "未知",
        "prefer": [],
        "avoid": [],
        "desc": "数据不足，无法判断经济阶段",
    })

    prefer_list = phase_info.get("prefer", [])
    avoid_list = phase_info.get("avoid", [])

    # 检查行业是否在偏好/规避列表中
    # 支持模糊匹配：部分匹配（如"消费电子"包含"消费电子代工"）
    in_prefer = False
    in_avoid = False
    for p in prefer_list:
        if p in industry or industry in p:
            in_prefer = True
            break
    for a in avoid_list:
        if a in industry or industry in a or a == "全部":
            in_avoid = True
            break

    # 安全边际修正：prefer=-3%, avoid=+3%
    if in_prefer:
        sector_adjustment = -0.03
    elif in_avoid:
        sector_adjustment = 0.03
    else:
        sector_adjustment = 0.0

    return {
        "cycle_phase": phase_info.get("label", "未知"),
        "cycle_description": phase_info.get("desc", ""),
        "industry_in_prefer": in_prefer,
        "industry_in_avoid": in_avoid,
        "sector_adjustment": sector_adjustment,
        "_growth_direction": growth_dir,
        "_inflation_level": infl_level,
    }


# ── 大类资产联动信号 ──────────────────────────────────────

# 行业 × 外部资产敏感性矩阵
# 值域 0~1，表示敏感度
CROSS_ASSET_SENSITIVITY = {
    "消费电子代工": {"usd_cny": 0.30, "费城半导体指数": 0.40, "原油": 0.05},
    "消费电子":     {"usd_cny": 0.20, "费城半导体指数": 0.30, "原油": 0.05},
    "半导体设计":   {"usd_cny": 0.10, "费城半导体指数": 0.50, "原油": 0.00},
    "半导体设备":   {"usd_cny": 0.10, "费城半导体指数": 0.40, "原油": 0.00},
    "AI算力":       {"usd_cny": 0.10, "费城半导体指数": 0.35, "原油": 0.00},
    "电力设备":     {"usd_cny": 0.05, "费城半导体指数": 0.00, "铜": 0.20},
    "电网自动化":   {"usd_cny": 0.05, "费城半导体指数": 0.00, "铜": 0.15},
    "新能源汽车":   {"usd_cny": 0.05, "费城半导体指数": 0.10, "铜": 0.25, "碳酸锂": 0.20},
    "光伏":         {"usd_cny": 0.15, "费城半导体指数": 0.00, "多晶硅": 0.30},
    "白酒":         {"usd_cny": 0.00, "费城半导体指数": 0.00, "CPI": 0.10},
    "银行":         {"usd_cny": 0.10, "沪深300": 0.50, "10Y国债": 0.30},
    "保险":         {"usd_cny": 0.05, "沪深300": 0.40, "10Y国债": 0.25},
    "家电":         {"usd_cny": 0.15, "费城半导体指数": 0.00, "房地产": 0.10},
    "公用事业":     {"usd_cny": 0.00, "10Y国债": 0.30, "煤炭": 0.10},
    "军工":         {"usd_cny": 0.00, "国防指数": 0.30, "原油": 0.05},
}

# 外部资产参考代码映射（腾讯API或新浪API）
ASSET_TICKER_MAP = {
    "usd_cny": {"name": "美元/人民币", "api": "tencent", "code": "USDCNY"},
    "10Y国债": {"name": "10Y国债收益率", "api": "sina", "code": "zy101466"},
    "费城半导体指数": {"name": "费城半导体指数", "api": "sina", "code": "gb_semiconductor"},
    "铜": {"name": "LME铜", "api": "sina", "code": "nf_CU"},
    "原油": {"name": "WTI原油", "api": "sina", "code": "nf_CL"},
    "沪深300": {"name": "沪深300", "api": "tencent", "code": "sh000300"},
}

# 近期方向缓存（字典，过期时间1小时）
_cross_asset_cache = {"data": {}, "ts": 0}
_CACHE_TTL = 3600


def fetch_asset_trend(asset_key: str) -> dict:
    """
    获取某外部资产的近期涨跌方向。

    使用腾讯/新浪API获取最新数据，缓存1小时。

    参数：
        asset_key — ASSET_TICKER_MAP 中的键

    返回：
        {"name": str, "trend": "上涨"/"下跌"/"震荡",
         "change_pct": float, "price": float, "asset_key": str}

    如果API调用失败，返回 {"trend": "数据不可用", "change_pct": 0}
    """
    import time as _time
    import requests as _requests

    now = _time.time()
    # 检查缓存
    if now - _cross_asset_cache["ts"] < _CACHE_TTL:
        if asset_key in _cross_asset_cache["data"]:
            return _cross_asset_cache["data"][asset_key]

    asset_info = ASSET_TICKER_MAP.get(asset_key)
    if not asset_info:
        return {"trend": "数据不可用", "change_pct": 0, "asset_key": asset_key,
                "name": asset_key, "price": 0}

    name = asset_info["name"]
    api = asset_info["api"]
    code = asset_info["code"]

    try:
        if api == "tencent":
            url = "https://qt.gtimg.cn/q=%s" % code
            resp = _requests.get(url, timeout=5, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://stock.qq.com",
            })
            text = resp.text
            # 腾讯格式：v_USDCNY="..."... 字段以~分隔
            if "~" in text:
                parts = text.split("~")
                # 索引3=最新价, 索引32=涨跌幅
                if len(parts) > 32:
                    price_str = parts[3].strip()
                    chg_str = parts[32].strip()
                    try:
                        price = float(price_str) if price_str else 0.0
                    except (ValueError, IndexError):
                        price = 0.0
                    try:
                        change_pct = float(chg_str) if chg_str else 0.0
                    except (ValueError, IndexError):
                        change_pct = 0.0

                    if change_pct > 0.5:
                        trend = "上涨"
                    elif change_pct < -0.5:
                        trend = "下跌"
                    else:
                        trend = "震荡"

                    result = {
                        "name": name,
                        "trend": trend,
                        "change_pct": change_pct,
                        "price": price,
                        "asset_key": asset_key,
                    }
                    _cross_asset_cache["data"][asset_key] = result
                    _cross_asset_cache["ts"] = now
                    return result
        elif api == "sina":
            # 新浪API：用于债券/商品指数
            url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData?symbol=%s&scale=240&datalen=2" % code
            resp = _requests.get(url, timeout=5, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://vip.stock.finance.sina.com.cn",
            })
            data = resp.json()
            if isinstance(data, list) and len(data) >= 2:
                prev = float(data[0].get("close", 0))
                curr = float(data[-1].get("close", 0))
                if prev > 0:
                    change_pct = (curr - prev) / prev * 100.0
                else:
                    change_pct = 0.0

                if change_pct > 0.5:
                    trend = "上涨"
                elif change_pct < -0.5:
                    trend = "下跌"
                else:
                    trend = "震荡"

                result = {
                    "name": name,
                    "trend": trend,
                    "change_pct": round(change_pct, 2),
                    "price": curr,
                    "asset_key": asset_key,
                }
                _cross_asset_cache["data"][asset_key] = result
                _cross_asset_cache["ts"] = now
                return result
    except Exception:
        pass

    return {"trend": "数据不可用", "change_pct": 0, "asset_key": asset_key,
            "name": name, "price": 0}


def cross_asset_risk_premium(code: str, industry: str) -> dict:
    """
    计算该标的外生风险溢价。

    逻辑：
    1. 从 CROSS_ASSET_SENSITIVITY 中查找行业×外部资产敏感度
    2. 对敏感度非零的每项资产，获取近期涨跌
    3. 加权汇总外部风险分

    返回：
        {
            "external_risk_score": float,  # -1~1（负=系统性压力, 正=有利环境）
            "risk_label": str,             # "有利" / "中性" / "承压"
            "asset_signals": [
                {"asset": "usd_cny", "trend": "上涨", "sensitivity": 0.30, "contribution": 0.15},
                ...
            ],
            "detail": str,
        }
    """
    # 查找行业敏感度
    sensitivities = CROSS_ASSET_SENSITIVITY.get(industry, {})

    if not sensitivities:
        return {
            "external_risk_score": 0.0,
            "risk_label": "中性",
            "asset_signals": [],
            "detail": "行业 \"%s\" 无外部资产敏感性配置" % industry,
        }

    asset_signals = []
    total_contribution = 0.0
    total_sensitivity = 0.0

    is_data_unavailable = False

    for asset_key, sensitivity in sensitivities.items():
        if sensitivity <= 0:
            continue

        trend_data = fetch_asset_trend(asset_key)
        trend = trend_data.get("trend", "数据不可用")

        if trend == "数据不可用":
            is_data_unavailable = True
            continue

        # 上涨=+1, 下跌=-1, 震荡=0
        if trend == "上涨":
            direction = 1.0
        elif trend == "下跌":
            direction = -1.0
        else:
            direction = 0.0

        contribution = sensitivity * direction
        total_contribution += contribution
        total_sensitivity += sensitivity

        asset_signals.append({
            "asset": asset_key,
            "trend": trend,
            "sensitivity": sensitivity,
            "contribution": round(contribution, 4),
        })

    # 归一化到 -1~1（除以3作为缩放因子）
    if total_sensitivity > 0:
        external_risk_score = total_contribution / 3.0
        external_risk_score = max(-1.0, min(1.0, external_risk_score))
    else:
        external_risk_score = 0.0

    # 风险标签
    if external_risk_score > 0.2:
        risk_label = "有利"
    elif external_risk_score < -0.2:
        risk_label = "承压"
    else:
        risk_label = "中性"

    detail_parts = []
    if is_data_unavailable:
        detail_parts.append("部分外部资产数据不可用")
    if asset_signals:
        signals_desc = "; ".join(
            "%s(%s,敏感=%.0f%%%%,贡献=%.2f)" % (
                s["asset"], s["trend"], s["sensitivity"] * 100, s["contribution"])
            for s in asset_signals
        )
        detail_parts.append(signals_desc)
    detail_parts.append("外部风险分=%.2f(%s)" % (external_risk_score, risk_label))

    return {
        "external_risk_score": round(external_risk_score, 4),
        "risk_label": risk_label,
        "asset_signals": asset_signals,
        "detail": " | ".join(detail_parts) if detail_parts else "无有效信号",
    }


# ── __all__ ──────────────────────────────────────────────────

__all__ = [
    "market_regime_adjustment",
    "macro_regime_adjustment",
    "get_rf_trend",
    "sell_condition_check",
    "compute_triggers",
    "MACRO_FILTERS",
    "DEFAULT_CORRECTION",
    "CROSS_ASSET_SENSITIVITY",
    "ASSET_TICKER_MAP",
    "fetch_asset_trend",
    "cross_asset_risk_premium",
]
