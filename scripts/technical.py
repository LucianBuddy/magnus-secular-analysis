#!/usr/bin/env python3
"""
technical — 技术面多周期分析模块（P2-3）

在 Step 3 的基础上，增加：
- MACD 方向判断
- 量价背离检测
- 周线趋势确认
- 成交量加权支撑/阻力（筹码密集区近似）

全部纯 Python 实现，无 numpy/pandas 依赖。
"""

import math
from typing import List, Optional


# ── EMA 计算 ────────────────────────────────────────────────

def _ema(data: list, period: int) -> list:
    """计算指数移动平均。返回长度 = len(data)。"""
    if not data or period <= 0:
        return data[:]
    result = [data[0]] if data else []
    k = 2.0 / (period + 1)
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result


# ── MACD ─────────────────────────────────────────────────────

def compute_macd(closes: list, fast=12, slow=26, signal=9) -> dict:
    """
    MACD 计算。

    返回：
        {
            "macd_line": float,     # DIF
            "signal_line": float,   # DEA
            "histogram": float,     # MACD 柱 (DIF - DEA)
            "direction": str,       # "金叉" / "死叉" / "零轴上" / "零轴下" / ""
        }
    """
    if len(closes) < slow + signal:
        return {"macd_line": 0, "signal_line": 0, "histogram": 0, "direction": ""}

    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)

    dif = [e_f - e_s for e_f, e_s in zip(ema_fast, ema_slow)]
    dea = _ema(dif, signal)
    hist = dif[-1] - dea[-1]

    # 方向判断
    direction = ""
    if len(dif) >= 2 and len(dea) >= 2:
        if dif[-2] < dea[-2] and dif[-1] >= dea[-1]:
            direction = "金叉"
        elif dif[-2] > dea[-2] and dif[-1] <= dea[-1]:
            direction = "死叉"
        elif dif[-1] > 0:
            direction = "零轴上"
        elif dif[-1] < 0:
            direction = "零轴下"

    return {
        "macd_line": round(dif[-1], 4) if dif else 0,
        "signal_line": round(dea[-1], 4) if dea else 0,
        "histogram": round(hist, 4),
        "direction": direction,
    }


# ── 量价背离检测 ────────────────────────────────────────────

def detect_divergence(closes: list, volumes: list, lookback=20) -> list:
    """
    量价背离检测。

    - 价格新高但成交量递减 → "顶背离"（看跌信号）
    - 价格新低但成交量递增 → "底背离"（看涨信号）

    参数：
        closes  — 收盘价序列（最新在最后）
        volumes — 成交量序列
        lookback — 回溯周期

    返回：
        list[str] — 信号列表（可能为空）
    """
    if len(closes) < lookback or len(volumes) < lookback:
        return []

    signals = []

    # 取最近 lookback 周期的数据
    recent_close = closes[-lookback:]
    recent_vol = volumes[-lookback:]
    n = len(recent_close)

    # 价格区间高点/低点
    price_high = max(recent_close)
    price_low = min(recent_close)

    # 新高位置的成交量
    high_idx = recent_close.index(price_high)
    if high_idx >= 5:
        # 高点到当前可能还有更高，找全局新高
        pass

    # 顶背离：价格>=前高85%分位，成交量缩减
    high_threshold = sorted(recent_close)[int(n * 0.85)]
    high_indices = [i for i, c in enumerate(recent_close) if c >= high_threshold]
    if len(high_indices) >= 2:
        # 成交量是否递减
        vol_at_highs = [recent_vol[i] for i in high_indices]
        if len(vol_at_highs) >= 3 and all(vol_at_highs[i] > vol_at_highs[i+1] for i in range(len(vol_at_highs)-1)):
            signals.append("顶背离")

    # 底背离：价格<=前低15%分位，成交量递增
    low_threshold = sorted(recent_close)[int(n * 0.15)]
    low_indices = [i for i, c in enumerate(recent_close) if c <= low_threshold]
    if len(low_indices) >= 2:
        vol_at_lows = [recent_vol[i] for i in low_indices]
        if len(vol_at_lows) >= 3 and all(vol_at_lows[i] < vol_at_lows[i+1] for i in range(len(vol_at_lows)-1)):
            signals.append("底背离")

    # 简化检测：最近 N 天的高价/低价成交量趋势
    if len(recent_close) >= 10:
        # 前半段 vs 后半段
        mid = n // 2
        p1_high = max(recent_close[:mid])
        p2_high = max(recent_close[mid:])
        p1_vol_high = recent_vol[recent_close[:mid].index(p1_high)] if p1_high == max(recent_close[:mid]) else 0
        p2_vol_high = recent_vol[mid:][recent_close[mid:].index(p2_high)] if p2_high == max(recent_close[mid:]) else 0

        if p2_high > p1_high and p2_vol_high < p1_vol_high * 0.7:
            if "顶背离" not in signals:
                signals.append("顶背离")

        p1_low = min(recent_close[:mid])
        p2_low = min(recent_close[mid:])
        p1_vol_low = recent_vol[recent_close[:mid].index(p1_low)] if p1_low == min(recent_close[:mid]) else 0
        p2_vol_low = recent_vol[mid:][recent_close[mid:].index(p2_low)] if p2_low == min(recent_close[mid:]) else 0

        if p2_low < p1_low and p2_vol_low > p1_vol_low * 1.3:
            if "底背离" not in signals:
                signals.append("底背离")

    return list(set(signals))


# ── 周线趋势确认 ────────────────────────────────────────────

def _aggregate_weekly(closes: List[float]) -> List[List[float]]:
    """从日K聚合为周K线（每5个交易日为一周），返回每周收盘价列表。"""
    weeks = []
    for i in range(0, len(closes), 5):
        week = closes[i:i+5]
        if week:
            weeks.append(week)
    return weeks


def check_weekly_trend(closes: list) -> dict:
    """
    周线趋势确认。

    从日K线聚合周K线（每5个交易日为一周），判断周线 MA5/MA10/MA20 排列。

    返回：
        {"trend": "多头" / "空头" / "震荡", "score": float, "weekly_closes": list}
    """
    if len(closes) < 60:
        return {"trend": "震荡", "score": 0.0, "weekly_closes": []}

    weeks = _aggregate_weekly(closes)

    # 至少需要 20 根周K线来算周MA20
    if len(weeks) < 12:
        return {"trend": "震荡", "score": 0.0, "weekly_closes": weeks}

    weekly_closes = [w[-1] for w in weeks]  # 每周收盘价

    # 计算周MA5, MA10, MA20
    def _sma(data, period):
        if len(data) < period:
            return data[-1] if data else 0
        return sum(data[-period:]) / period

    wma5 = _sma(weekly_closes, 5)
    wma10 = _sma(weekly_closes, 10)
    wma20 = _sma(weekly_closes, 20)
    current_w = weekly_closes[-1]

    # 多头排列: MA5 > MA10 > MA20
    bull = wma5 > wma10 > wma20 and current_w > wma5
    # 空头排列: MA5 < MA10 < MA20
    bear = wma5 < wma10 < wma20 and current_w < wma5

    if bull:
        return {"trend": "多头", "score": 0.8, "weekly_closes": weekly_closes}
    elif bear:
        return {"trend": "空头", "score": -0.8, "weekly_closes": weekly_closes}
    else:
        # 部分多头
        score = 0.0
        if current_w > wma20:
            score += 0.3
        if current_w > wma10:
            score += 0.2
        if current_w > wma5:
            score += 0.1
        if wma5 > wma10:
            score += 0.1
        if wma10 > wma20:
            score += 0.1
        return {"trend": "震荡", "score": round(score - 0.3, 2), "weekly_closes": weekly_closes}


# ── 成交量加权支撑/阻力（筹码密集区近似） ─────────────────

def compute_volume_profile(closes: list, highs: list, lows: list,
                           volumes: list, bins=10) -> dict:
    """
    成交量加权支撑/阻力计算（近似筹码密集区）。

    将近期价格区间分为 bins 等份，统计每份的成交量占比。
    最高成交占比的价格区间 = 筹码密集区 → 强支撑/阻力。

    参数：
        closes  — 收盘价序列
        highs   — 最高价序列
        lows    — 最低价序列
        volumes — 成交量序列
        bins    — 价格区间份数

    返回：
        {
            "support_zones": [(price_low, price_high), ...],
            "resistance_zones": [(price_low, price_high), ...],
            "volume_distribution": [(price_low, price_high, vol_pct), ...],
            "current_price_zone": (price_low, price_high),
        }
    """
    if not closes or not volumes:
        return {"support_zones": [], "resistance_zones": [],
                "volume_distribution": [], "current_price_zone": (0, 0)}

    # 使用最近 60 根 K 线
    n = min(len(closes), 60)
    recent_c = closes[-n:]
    recent_h = highs[-n:]
    recent_l = lows[-n:]
    recent_v = volumes[-n:]

    price_min = min(recent_l)
    price_max = max(recent_h)
    current = recent_c[-1]

    if price_max <= price_min:
        return {"support_zones": [], "resistance_zones": [],
                "volume_distribution": [], "current_price_zone": (0, 0)}

    bin_size = (price_max - price_min) / bins
    bin_volumes = [0.0] * bins
    total_vol = sum(recent_v) or 1

    # 将每根K线的成交量按收盘价分配到对应区间
    for c, h, l, v in zip(recent_c, recent_h, recent_l, recent_v):
        # 用 (c+l+h)/3 作为该K线的典型价格
        typical = (c + h + l) / 3.0
        idx = min(bins - 1, int((typical - price_min) / bin_size))
        bin_volumes[idx] += v

    # 计算每个区间的成交量占比
    vol_dist = []
    for i in range(bins):
        low = price_min + i * bin_size
        high = low + bin_size
        pct = bin_volumes[i] / total_vol * 100
        vol_dist.append((round(low, 2), round(high, 2), round(pct, 1)))

    # 当前价所在区间
    ci = min(bins - 1, int((current - price_min) / bin_size))

    # 筹码密集区：成交量占比 > 平均值
    mean_pct = 100.0 / bins
    dense_zones = [(l, h, p) for l, h, p in vol_dist if p > mean_pct * 1.2]

    # 低于当前价的密集区 → 支撑
    support = [(l, h) for l, h, p in dense_zones if h < current]
    # 高于当前价的密集区 → 阻力
    resistance = [(l, h) for l, h, p in dense_zones if l > current]
    # 当前价所在密集区：既是支撑也是阻力
    for l, h, p in vol_dist:
        if l <= current <= h and p > mean_pct:
            support.append((l, h))
            resistance.append((l, h))

    return {
        "support_zones": sorted(set(support)),
        "resistance_zones": sorted(set(resistance)),
        "volume_distribution": vol_dist,
        "current_price_zone": (round(current, 2), round(current, 2)),
    }


# ── 综合技术面评分 ──────────────────────────────────────────

def compute_enhanced_tech_score(
    closes: list,
    highs: list,
    lows: list,
    volumes: list,
    ma5: float, ma10: float, ma20: float, ma60: float,
    current_price: float,
    vol_ratio: float,
    fund_flow_ok: bool = False,
    fund_flow_today: float = 0.0,
) -> dict:
    """
    综合技术面评分（替代原来 Step 3 的 5 因子）。

    在原有 5 因子基础上新增：
    - MACD方向  ±0.15
    - 量价背离  ±0.15
    - 周线趋势  ±0.15
    - 筹码密集区支撑/阻力  ±0.15

    总分范围 -1.0 ~ 1.0

    返回：
        {
            "score": float,
            "details": {
                "均线系统": float,
                "量价关系": float,
                "MACD方向": float,
                "量价背离": float,
                "周线趋势": float,
                "筹码支撑": float,
                "趋势幅度": float,
                "资金面": Optional[float],
            },
            "signals": [str],  # 纯文本信号列表
        }
    """
    score = 0.0
    signals = []
    details = {}

    # ── 均线系统 (±0.30) ──
    ma_score = 0.0
    if current_price > ma5 > ma10 > ma20:
        ma_score = 0.30
        signals.append("多头排列")
    elif current_price < ma5 < ma10 < ma20:
        ma_score = -0.30
        signals.append("空头排列")
    elif current_price > ma20:
        ma_score = 0.10
        signals.append("站上MA20")
    elif current_price < ma20:
        ma_score = -0.10
        signals.append("跌破MA20")
    details["均线系统"] = ma_score
    score += ma_score

    # ── 量价关系 (±0.20) ──
    vol_score = 0.0
    if len(closes) >= 2:
        today_chg = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] != 0 else 0
        if vol_ratio > 1.5 and today_chg > 0:
            vol_score = 0.20
            signals.append("放量上涨")
        elif vol_ratio > 1.5 and today_chg < 0:
            vol_score = -0.20
            signals.append("放量下跌")
    details["量价关系"] = vol_score
    score += vol_score

    # ── K线形态 (±0.15) ──
    kline_score = 0.0
    if len(closes) >= 2:
        today_chg = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] != 0 else 0
        if today_chg > 5 and vol_ratio > 1.5:
            kline_score = 0.15
            signals.append("大阳线放量")
        elif today_chg < -5 and vol_ratio > 1.5:
            kline_score = -0.15
            signals.append("大阴线放量")
    details["K线形态"] = kline_score
    score += kline_score

    # ── 趋势幅度 (±0.15) ──
    trend_score = 0.0
    if len(closes) >= 5:
        chg_5d = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] != 0 else 0
        if chg_5d > 10:
            trend_score = 0.15
            signals.append("近5日涨超10%%")
        elif chg_5d < -10:
            trend_score = -0.15
            signals.append("近5日跌超10%%")
    details["趋势幅度"] = trend_score
    score += trend_score

    # ── 资金面 (±0.15) ──
    fund_score = 0.0
    if fund_flow_ok:
        if fund_flow_today > 0:
            fund_score = 0.15
            signals.append("主力净流入")
        else:
            fund_score = -0.15
            signals.append("主力净流出")
    details["资金面"] = fund_score if fund_flow_ok else None
    score += fund_score

    # ── MACD方向 (±0.15) ──
    macd = compute_macd(closes)
    macd_score = 0.0
    if macd["direction"] == "金叉":
        macd_score = 0.15
        signals.append("MACD金叉")
    elif macd["direction"] == "死叉":
        macd_score = -0.15
        signals.append("MACD死叉")
    elif macd["direction"] == "零轴上":
        macd_score = 0.05
    elif macd["direction"] == "零轴下":
        macd_score = -0.05
    details["MACD方向"] = macd_score
    score += macd_score

    # ── 量价背离 (±0.15) ──
    divergences = detect_divergence(closes, volumes)
    div_score = 0.0
    if "顶背离" in divergences:
        div_score -= 0.15
        signals.append("顶背离")
    if "底背离" in divergences:
        div_score += 0.15
        signals.append("底背离")
    details["量价背离"] = div_score
    score += div_score

    # ── 周线趋势 (±0.15) ──
    weekly = check_weekly_trend(closes)
    weekly_score = weekly["score"] * 0.15  # 原分 ±0.8, 缩放至 ±0.12, 再额外 ±0.03
    weekly_score = min(0.15, max(-0.15, weekly_score))
    if weekly["trend"] == "多头":
        signals.append("周线多头")
    elif weekly["trend"] == "空头":
        signals.append("周线空头")
    details["周线趋势"] = round(weekly_score, 4)
    score += weekly_score

    # ── 筹码密集区支撑/阻力 (±0.15) ──
    vp = compute_volume_profile(closes, highs, lows, volumes)
    vp_score = 0.0
    # 当前价下方有强支撑
    if vp["support_zones"] and len(vp["support_zones"]) >= 2:
        # 有支撑 → 看多信号
        vp_score += 0.10
    # 当前价上方有强阻力
    if vp["resistance_zones"] and len(vp["resistance_zones"]) >= 2:
        vp_score -= 0.10
    # 综合：支撑>阻力则偏多，反之偏空
    support_vol = sum(p for _, _, p in vp["volume_distribution"][:len(vp["volume_distribution"])//2])
    resist_vol = sum(p for _, _, p in vp["volume_distribution"][len(vp["volume_distribution"])//2:])
    # 粗略判断：下面筹码多（支撑强）+0.05，上面筹码多（阻力强）-0.05
    if support_vol > resist_vol * 1.3:
        vp_score += 0.05
        if "筹码支撑强" not in signals:
            signals.append("下方筹码密集")
    elif resist_vol > support_vol * 1.3:
        vp_score -= 0.05
        if "上方抛压重" not in signals:
            signals.append("上方筹码密集")
    details["筹码支撑"] = round(vp_score, 4)
    score += vp_score

    # ── 限幅 ──
    score = max(-1.0, min(1.0, round(score, 4)))

    return {
        "score": score,
        "details": details,
        "signals": signals,
        "macd": macd,
        "weekly_trend": weekly["trend"],
        "volume_profile": vp,
        "divergences": divergences,
    }


# ── __all__ ──────────────────────────────────────────────────

__all__ = [
    "compute_macd",
    "detect_divergence",
    "check_weekly_trend",
    "compute_volume_profile",
    "compute_enhanced_tech_score",
]
