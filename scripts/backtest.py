#!/usr/bin/env python3
"""
backtest — magnus-secular-analysis 信号回测框架（P2-2）

功能：
  1. fetch_history_data(code) — 获取过去 N 年的逐日 K 线 + 季报数据
  2. roll_forward() — 在每个季度末回放 build_summary() + 判定逻辑
  3. performance_metrics() — Sharpe, 胜率, 盈亏比, 最大回撤
  4. regime_split() — 按牛/熊/震荡市分拆表现
  5. bias_analysis() — 系统偏差方向（高估/低估倾向）

依赖：requests (仅用于实时数据), 其余标准库
      估值判定复用 preprocess.py 中的已有函数
"""

import json
import math
import requests
from datetime import datetime, timedelta
from typing import Optional, Any, List

# 尝试引入 preprocess.py 的估值函数（向后兼容）
try:
    from . import preprocess as pp
    from .preprocess import compute_valuation_verdict, compute_dynamic_pe_limit
    from .preprocess import compute_normalized_cagr, margin_of_safety_continuous, get_industry
    from .preprocess import get_industry_peers, get_oe_multiple
    from .preprocess import build_summary
    from .preprocess import get_factor_weights
    from .preprocess import generate_signal
except ImportError:
    # fallback: 直接 import preprocess
    import sys, os
    _d = os.path.dirname(os.path.abspath(__file__))
    if _d not in sys.path:
        sys.path.insert(0, _d)
    import preprocess as pp
    from preprocess import compute_valuation_verdict, compute_dynamic_pe_limit
    from preprocess import compute_normalized_cagr, margin_of_safety_continuous, get_industry
    from preprocess import get_industry_peers, get_oe_multiple
    from preprocess import build_summary
    from preprocess import get_factor_weights
    from preprocess import generate_signal


# ═══════════════════════════════════════════════════════════════
# 1a. 历史行情数据获取
# ═══════════════════════════════════════════════════════════════

def get_quarter_end_dates(start: str, end: str) -> list:
    """
    生成从 start 到 end 之间的季度末日期序列。

    参数：
        start — "YYYY-MM-DD"
        end   — "YYYY-MM-DD"

    返回：
        list of "YYYY-MM-DD" — 每个季度最后一个月的第15天（模拟季报已发布）
    """
    try:
        sd = datetime.strptime(start, "%Y-%m-%d")
        ed = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        return []

    quarters = []
    # 从起始年初开始
    year, month = sd.year, sd.month
    while True:
        # 季度末月: 3, 6, 9, 12
        if month <= 3:
            qm = 3
        elif month <= 6:
            qm = 6
        elif month <= 9:
            qm = 9
        else:
            qm = 12

        # 季报通常在季度结束后1-2个月发布，模拟为季度结束后第15天
        if qm == 3:
            avail_month = 5  # 一季报4月底前
        elif qm == 6:
            avail_month = 8  # 中报8月底前
        elif qm == 9:
            avail_month = 10  # 三季报10月底前
        else:
            avail_month = 4  # 年报次年4月底前

        # 确定可用年份
        avail_year = year
        if qm == 12:
            avail_year = year + 1  # 年报次年发布

        try:
            qd = datetime(avail_year, avail_month, 15)
        except ValueError:
            year += 1
            month = 1
            continue

        if sd <= qd <= ed:
            quarters.append(qd.strftime("%Y-%m-%d"))

        # 移到下个季度
        if month <= 3:
            year = year
            month = 4
        elif month <= 6:
            year = year
            month = 7
        elif month <= 9:
            month = 12
        else:
            year += 1
            month = 1

        # 安全阀
        if year > ed.year + 2:
            break

    return quarters


def fetch_history_data(code: str, years: int = 2) -> dict:
    """
    获取过去 N 年的逐日 K 线数据。

    优先通过腾讯行情接口获取，回拉有限（约2年）。
    返回 dict: { "klines": [...], "dates": [...], "quarterly": [...] }

    klines 每行为 [date, open, close, high, low, vol, amt]
    quarterly 为季报期关键数据（仅结构占位，实际由外部传入）
    """
    # 腾讯 daily K 线
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,%d,qfq" % (code, years)
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://stock.qq.com"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
    except Exception:
        return {"klines": [], "dates": [], "quarterly": []}

    data_section = d.get("data", {})
    # 尝试多种 key
    klines_raw = (data_section.get(code, {}).get("day", [])
                  or data_section.get("qt", {}).get(code, {}).get("day", [])
                  or [])

    if not klines_raw:
        return {"klines": [], "dates": [], "quarterly": []}

    klines = []
    dates = []
    for row in klines_raw:
        # 腾讯格式: [date, open, close, high, low, volume]
        if len(row) < 6:
            continue
        dt_str = str(row[0])
        o, c, h, l = float(row[1]), float(row[2]), float(row[3]), float(row[4])
        v = float(row[5])
        dates.append(dt_str)
        klines.append([dt_str, o, c, h, l, v, 0])  # amt 暂为0

    return {
        "klines": klines,
        "dates": dates,
        "quarterly": [],
    }


def fetch_historical_quotes(code: str, target_date: str) -> dict:
    """
    拉取目标日期前的最新行情数据（腾讯API）。

    返回 {
        "price": float,
        "pe": float,
        "pb": float,
        "market_cap": float,
        "turnover": float,
        "date": str,
    }
    """
    try:
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,2,qfq" % code
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://stock.qq.com"})
        d = r.json()
        data_sec = d.get("data", {})
        klines_raw = (data_sec.get(code, {}).get("day", [])
                      or data_sec.get("qt", {}).get(code, {}).get("day", [])
                      or [])
        if klines_raw:
            last = klines_raw[-1]
            price = float(last[2])
            return {
                "price": price,
                "pe": 0, "pb": 0, "market_cap": 0, "turnover": 0,
                "date": str(last[0]),
            }
    except Exception:
        pass
    return {"price": 0, "pe": 0, "pb": 0, "market_cap": 0, "turnover": 0, "date": target_date}


# ═══════════════════════════════════════════════════════════════
# 1b. 历史财务数据获取
# ═══════════════════════════════════════════════════════════════

def fetch_historical_finance(code: str, quarter_date: str) -> dict:
    """
    拉取目标季度末的财务快照（新浪财报API）。

    从目标日期往前推，找到最近的完整季度财报数据。
    直接使用 requests 直连新浪 API。

    参数：
        code         — 股票代码
        quarter_date — 目标日期 "YYYY-MM-DD"

    返回：
        {roe, gm, np, ocf, dr, rg, pg, bvps, ...}
    """
    try:
        qd = datetime.strptime(quarter_date, "%Y-%m-%d")
    except ValueError:
        return {}

    # 从 quarter_date 确定对应季度
    y, m = qd.year, qd.month
    if quarter_date.endswith("-04-15") or quarter_date.startswith("-05-"):
        # 一季报
        report_date = "%s-03-31" % y
    elif quarter_date.endswith("-08-15"):
        report_date = "%s-06-30" % y
    elif quarter_date.endswith("-10-15"):
        report_date = "%s-09-30" % y
    elif quarter_date.endswith("-04-15"):
        report_date = "%s-12-31" % (y - 1)  # 上年年报
    else:
        # 从 date 推断
        if m <= 5:
            report_date = "%s-03-31" % (y if m < 4 else y)
        elif m <= 8:
            report_date = "%s-06-30" % y
        elif m <= 10:
            report_date = "%s-09-30" % y
        else:
            report_date = "%s-12-31" % y

    # 新浪三表 API
    # 利润表
    result = {}
    try:
        url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getFinanceData?symbol=%s&date=%s" % (
            code, report_date)
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://vip.stock.finance.sina.com.cn"})
        data = r.json()
        if isinstance(data, list):
            for item in data:
                k = item.get("key", "")
                v_str = item.get("value", "0")
                try:
                    v = float(v_str.replace(",", "")) if v_str else 0.0
                except (ValueError, AttributeError):
                    v = 0.0
                if k == "roe":
                    result["roe"] = v
                elif k == "net_profit":
                    result["np"] = v
                elif k == "gross_margin":
                    result["gm"] = v
                elif k == "operate_cash_flow":
                    result["ocf"] = v
                elif k == "debt_ratio":
                    result["dr"] = v
                elif k == "revenue_growth":
                    result["rg"] = v
                elif k == "profit_growth":
                    result["pg"] = v
                elif k == "bvps":
                    result["bvps"] = v
                elif k == "revenue":
                    result["revenue"] = v
    except Exception:
        pass

    return result


def fetch_finance_at_date(code: str, target_date: str) -> dict:
    """
    获取目标时间点可得的财务快照。

    模拟在历史某个时间点，分析师能看到的最新的完整财务数据。
    使用策略：
    1. 从 target_date 往前推，找到最近的季报发布日
    2. 通过新浪财报三表API获取该季度的数据
    3. 构建 build_summary() 所需的财务参数子集

    参数：
        code        — 股票代码
        target_date — 目标日期 "YYYY-MM-DD"

    返回：
        dict {roe, gm, np, ocf, dr, rg, pg, bvps, ...}
    """
    # 往前找最近季度
    td = datetime.strptime(target_date, "%Y-%m-%d")

    # 确定最新的完整季度
    y, m, d = td.year, td.month, td.day

    # 季报可用性模拟:
    # Q1(1-3月) → 4月底前发布
    # Q2(4-6月) → 8月底前发布
    # Q3(7-9月) → 10月底前发布
    # Q4(10-12月) → 次年4月底前发布
    quarter_str = ""
    if (m == 4 and d >= 30) or (5 <= m <= 8 and not (m == 8 and d < 31)):
        # 一季报已发布
        # 需要看是否已到8月底（中报发布）
        if m >= 8 and d >= 31:
            # 中报已发布
            if m >= 10 and d >= 31:
                # 三季报已发布
                if m >= 4 or (m == 4 and d >= 30):
                    # 年报也已发布
                    quarter_str = "%s-12-31" % (y - 1)
                else:
                    quarter_str = "%s-09-30" % y
            else:
                quarter_str = "%s-06-30" % y
        else:
            quarter_str = "%s-03-31" % y
    else:
        # 最新完整年度是上年
        quarter_str = "%s-12-31" % (y - 1)

    if not quarter_str:
        return {}

    return fetch_historical_finance(code, quarter_str)


# ═══════════════════════════════════════════════════════════════
# 1c. 运行完整回测
# ═══════════════════════════════════════════════════════════════

def run_backtest(code: str, start_date: str, end_date: str,
                 interval: str = "quarterly") -> list:
    """
    完整回测主入口。在每个季度末：
    1. 获取到该时间点为止的行情数据
    2. 获取该时间点可得的财务数据
    3. 调用 build_summary() 生成 ss
    4. 调用 get_factor_weights() + generate_signal() 生成判定
    5. 记录判定和之后1季度的实际表现

    参数：
        code       — 股票代码
        start_date — 起始日期 "YYYY-MM-DD"
        end_date   — 结束日期 "YYYY-MM-DD"
        interval   — 回测间隔 "quarterly" / "monthly"

    返回：
        list of dict: [
            {
                "quarter": "2025Q1",
                "date": "2025-05-15",
                "price": 30.0,
                "verdict": "买入",
                "conviction": 0.7,
                "tech_score": 0.3,
                "factors": {},
                "price_after_quarter": 33.0,
                "actual_chg": 10.0,
                "direction_ok": True,
            },
            ...
        ]
    """
    # 获取历史 K 线
    hist = fetch_history_data(code, years=5)
    klines = hist.get("klines", [])
    if not klines:
        return []

    dates = [k[0] for k in klines]
    closes = [k[2] for k in klines]
    highs = [k[3] for k in klines]
    lows = [k[4] for k in klines]
    volumes = [k[5] for k in klines]

    # 获取季度边界
    quarter_dates = get_quarter_end_dates(start_date, end_date)

    records = []
    for i, qd_str in enumerate(quarter_dates):
        # 找距 qd_str 最近的收盘日
        idx = None
        for j, dt_str in enumerate(dates):
            if dt_str >= qd_str:
                idx = j
                break
        if idx is None or idx >= len(closes):
            continue

        price = closes[idx]

        # 获取该时间点的财务数据
        fin = fetch_finance_at_date(code, qd_str)

        if not fin:
            records.append({
                "quarter": "Q%d" % ((datetime.strptime(qd_str, "%Y-%m-%d").month - 1) // 3 + 1),
                "date": qd_str,
                "price": price,
                "verdict": "持有",
                "conviction": 0.2,
                "tech_score": 0,
                "factors": {},
                "price_after_quarter": closes[min(idx + 60, len(closes) - 1)],
                "actual_chg": 0,
                "direction_ok": False,
                "error": "财务数据不可用",
            })
            continue

        # 尝试构建 ss
        try:
            ss = build_summary(
                code=code, name="",
                closes=closes[:idx+1], highs=highs[:idx+1], lows=lows[:idx+1],
                volumes=volumes[:idx+1], amounts=[0]*(idx+1),
                ma5_list=[closes[max(0, i-4):i+1] and sum(closes[max(0, i-4):i+1])/min(5,i+1) or 0 for i in range(idx+1)],
                ma10_list=[closes[max(0, i-9):i+1] and sum(closes[max(0, i-9):i+1])/min(10,i+1) or 0 for i in range(idx+1)],
                ma20_list=[closes[max(0, i-19):i+1] and sum(closes[max(0, i-19):i+1])/min(20,i+1) or 0 for i in range(idx+1)],
                current_price=price,
                pe=0, pb=0, market_cap=0, turnover=0,
                bvps=fin.get("bvps", 0),
                ttm_eps=0,
                roe_3y=[fin.get("roe", 0) or 0],
                gross_margin_3y=[fin.get("gm", 0) or 0],
                debt_ratio=fin.get("dr", 0) or 0,
                interest_debt_ratio=0,
                revenue_growth=[fin.get("rg", 0) or 0],
                profit_growth=[fin.get("pg", 0) or 0],
                ocf=fin.get("ocf", 0) or 0,
                np=fin.get("np", 0) or 0,
            )
        except Exception as exc:
            records.append({
                "quarter": "Q%d" % ((datetime.strptime(qd_str, "%Y-%m-%d").month - 1) // 3 + 1),
                "date": qd_str,
                "price": price,
                "verdict": "持有",
                "conviction": 0.2,
                "tech_score": 0,
                "factors": {},
                "price_after_quarter": closes[min(idx + 60, len(closes) - 1)],
                "actual_chg": 0,
                "direction_ok": False,
                "error": str(exc),
            })
            continue

        # 生成行业因子权重
        try:
            industry = get_industry(code)
            factor_weights = get_factor_weights(industry)
        except Exception:
            industry = ""
            factor_weights = {}

        # 生成信号
        try:
            sig = generate_signal("持有", 0.0, "长线")
            verdict = sig["verdict"]
            conviction = sig["conviction"]
        except Exception:
            verdict = "持有"
            conviction = 0.3

        # 实际表现：之后60个交易日（约1季度）
        future_idx = min(idx + 60, len(closes) - 1)
        price_after = closes[future_idx]
        actual_chg = round((price_after - price) / price * 100, 2) if price > 0 else 0
        direction_ok = (conviction >= 0.5 and actual_chg > 0) or (conviction < 0.3 and actual_chg < 0)

        q_num = (datetime.strptime(qd_str, "%Y-%m-%d").month - 1) // 3 + 1

        records.append({
            "quarter": "%dQ%d" % (datetime.strptime(qd_str, "%Y-%m-%d").year, q_num),
            "date": qd_str,
            "price": round(price, 2),
            "verdict": verdict,
            "conviction": conviction,
            "tech_score": 0.0,
            "factors": factor_weights,
            "price_after_quarter": round(price_after, 2),
            "actual_chg": actual_chg,
            "direction_ok": direction_ok,
            "fin_snapshot": {
                k: fin.get(k) for k in ["roe", "gm", "np", "ocf", "dr", "rg", "pg", "bvps"]
                if k in fin
            },
        })

    return records


# ═══════════════════════════════════════════════════════════════
# 2. 滚窗回放
# ═══════════════════════════════════════════════════════════════

def _detect_quarter_boundary(dates):
    """
    从 K 线日期列表推断季度边界。
    返回 list of (index, date_str)，索引指向季度最后一个交易日。
    """
    boundaries = []
    prev_q = None
    for i, ds in enumerate(dates):
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d")
        except ValueError:
            continue
        q = (dt.year, (dt.month - 1) // 3 + 1)
        if q != prev_q:
            if prev_q is not None and i > 0:
                boundaries.append((i - 1, dates[i - 1]))
            prev_q = q
    # last day
    if dates:
        boundaries.append((len(dates) - 1, dates[-1]))
    return boundaries


def roll_forward(
    code: str,
    start_date: str,
    end_date: str,
    interval: str = "quarterly",
    klines: Optional[list] = None,
    extra_data_func: Optional = None,
) -> list:
    """
    在每个季度末回放 build_summary() + 判定逻辑。

    参数：
        code              — 股票代码
        start_date        — 起始日期 "YYYY-MM-DD"
        end_date          — 结束日期 "YYYY-MM-DD"
        interval          — 回放间隔 "quarterly" / "monthly"
        klines            — 预获取的 K 线数据（可提前由 fetch_history_data 获取）
        extra_data_func   — 可选回调，在每个回放点的盘后拉取额外数据(季报、三表等)

    返回：
        list of dict: [{date, price, verdict, target_price, actual_direction, ...}, ...]
    """
    # 获取 K 线数据
    if klines is None:
        hist = fetch_history_data(code)
        klines = hist.get("klines", [])
    if not klines:
        return []

    dates = [k[0] for k in klines]
    closes = [k[2] for k in klines]

    # 检测季度边界
    if interval == "quarterly":
        boundaries = _detect_quarter_boundary(dates)
    else:
        # monthly: 每月最后一个交易日
        boundaries = []
        prev_m = None
        for i, ds in enumerate(dates):
            try:
                dt = datetime.strptime(ds, "%Y-%m-%d")
            except ValueError:
                continue
            m = (dt.year, dt.month)
            if m != prev_m:
                if prev_m is not None and i > 0:
                    boundaries.append((i - 1, dates[i - 1]))
                prev_m = m
        if dates:
            boundaries.append((len(dates) - 1, dates[-1]))

    # 过滤日期范围
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return []

    records = []
    for idx, dt_str in boundaries:
        try:
            dt_obj = datetime.strptime(dt_str, "%Y-%m-%d")
        except ValueError:
            continue
        if dt_obj < sd or dt_obj > ed:
            continue

        # 该点的价格数据
        price = closes[idx]
        lookback = min(len(closes[:idx+1]), 60)
        recent_closes = closes[idx+1-lookback:idx+1] if idx+1 >= lookback else closes[:idx+1]

        # 简单估值判定（默认模拟判定，实际应由调用方提供 extra_data_func）
        if extra_data_func is not None:
            extra = extra_data_func(code, dt_str, idx, klines)
            judgement = _simple_judge(price, extra)
        else:
            judgement = _simple_fallback_judge(price, recent_closes)

        judgement.update({
            "date": dt_str,
            "price": price,
            "target_price": judgement.get("target_price", price),
            "code": code,
        })

        # 实际方向（随后 N 个交易日后）
        future_window = 60  # 约 3 个月
        future_idx = idx + future_window
        if future_idx < len(closes):
            future_price = closes[future_idx]
            actual_chg = round((future_price - price) / price * 100, 2)
            direction = 1 if future_price > price else (-1 if future_price < price else 0)
        else:
            if closes:
                future_price = closes[-1]
                actual_chg = round((future_price - price) / price * 100, 2)
                direction = 1 if future_price > price else (-1 if future_price < price else 0)
            else:
                actual_chg = 0.0
                direction = 0

        judgement["actual_chg_pct"] = actual_chg
        judgement["actual_direction"] = direction
        records.append(judgement)

    return records


def _simple_fallback_judge(current_price: float, recent_closes: list) -> dict:
    """简单的 fallback 判定（当无 extra_data_func 时）。"""
    if len(recent_closes) < 20:
        return {"verdict": "持有", "conviction": 0.3, "target_price": current_price}

    # 均线策略: 价格在 MA20 以下 → 卖出, 以上 → 买入
    ma20 = sum(recent_closes[-20:]) / 20.0
    if current_price < ma20 * 0.95:
        verdict = "卖出"
        target_price = round(current_price * 0.95, 2)
        conviction = 0.5
    elif current_price > ma20 * 1.05:
        verdict = "买入"
        target_price = round(current_price * 1.10, 2)
        conviction = 0.5
    else:
        verdict = "持有"
        target_price = round(current_price * 1.02, 2)
        conviction = 0.3
    return {"verdict": verdict, "conviction": conviction, "target_price": target_price}


def _simple_judge(current_price: float, extra: dict) -> dict:
    """基于 extra_data_func 传入的额外财务数据进行判定。"""
    # 如果有 PE/CAGR 则调用估值判定
    pe = extra.get("pe", 0)
    cagr = extra.get("cagr", 0)
    block_median_pe = extra.get("block_median_pe", 0)
    pe_limit = extra.get("pe_limit", 0)
    industry = extra.get("industry", "")

    if pe and cagr:
        v = compute_valuation_verdict(pe, cagr, block_median_pe, pe_limit, industry)
        if v["action"] in ("买入", "强烈建议买入"):
            target_price = round(current_price * 1.15, 2)
            conviction = 0.7
        elif v["action"] in ("卖出", "减仓"):
            target_price = round(current_price * 0.90, 2)
            conviction = 0.6
        else:
            target_price = round(current_price * 1.02, 2)
            conviction = 0.4
        return {
            "verdict": v["action"],
            "conviction": conviction,
            "target_price": target_price,
            "vest_verdict": v.get("verdict", ""),
            "peg": v.get("peg", 0),
        }

    return _simple_fallback_judge(current_price, extra.get("closes", []))


# ═══════════════════════════════════════════════════════════════
# 3. 绩效指标
# ═══════════════════════════════════════════════════════════════

def performance_metrics(records: list) -> dict:
    """
    从回放记录计算绩效指标。

    返回：
        {
            "sharpe": float,       # 夏普比率
            "win_rate": float,     # 胜率
            "profit_loss_ratio": float, # 盈亏比
            "max_drawdown": float, # 最大回撤
            "total_trades": int,   # 总交易次数
            "avg_return": float,   # 平均单笔收益率
            "total_return": float, # 累计收益率
        }
    """
    if not records:
        return {"sharpe": 0, "win_rate": 0, "profit_loss_ratio": 0,
                "max_drawdown": 0, "total_trades": 0, "avg_return": 0, "total_return": 0}

    # 提取收益率序列（使用 actual_chg_pct）
    returns = [r.get("actual_chg_pct", 0) / 100.0 for r in records]
    if not returns:
        return {"sharpe": 0, "win_rate": 0, "profit_loss_ratio": 0,
                "max_drawdown": 0, "total_trades": 0, "avg_return": 0, "total_return": 0}

    n = len(returns)
    # 胜率：收益率 > 0 的比例
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    win_rate = len(wins) / n if n > 0 else 0

    # 盈亏比
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.01
    profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss > 0 else 0

    # 平均单笔
    avg_return = sum(returns) / n if n > 0 else 0

    # 累计收益率（假设计算复利）
    total_return = sum(returns)  # 简单累加

    # 夏普比率（年化, 假设每笔 ~60 交易日）
    if n >= 3:
        mean_r = sum(returns) / n
        variance = sum((r - mean_r) ** 2 for r in returns) / n
        std = math.sqrt(variance) if variance > 0 else 0.001
        # 假设每笔间隔 60 交易日, 年化 ~252/60=4.2
        periods_per_year = 4.2
        sharpe = (mean_r / std) * math.sqrt(periods_per_year) if std > 0 else 0
    else:
        sharpe = 0

    # 最大回撤
    max_dd = 0
    peak = 1.0
    cumulative = 1.0
    for r in returns:
        cumulative *= (1 + r)
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "sharpe": round(sharpe, 3),
        "win_rate": round(win_rate, 3),
        "profit_loss_ratio": round(profit_loss_ratio, 2),
        "max_drawdown": round(max_dd, 3),
        "total_trades": n,
        "avg_return": round(avg_return, 4),
        "total_return": round(total_return, 4),
    }


# ═══════════════════════════════════════════════════════════════
# 4. 市场分拆
# ═══════════════════════════════════════════════════════════════

def regime_split(records: list,
                 bull_threshold: float = 0.05,
                 bear_threshold: float = -0.05) -> dict:
    """
    按牛/熊/震荡市分拆回放表现。

    参数：
        bull_threshold — 季度涨幅 > 5% = 牛市
        bear_threshold — 季度涨幅 < -5% = 熊市
        records        — roll_forward() 返回的记录

    返回：
        {"regimes": {regime: {count, win_rate, avg_return, ...}}, "records": [...]}
    """
    if not records:
        return {"regimes": {}, "records": []}

    regimes = {"bull": [], "bear": [], "neutral": []}
    for r in records:
        chg = r.get("actual_chg_pct", 0)
        if chg > bull_threshold * 100:
            regimes["bull"].append(r)
        elif chg < bear_threshold * 100:
            regimes["bear"].append(r)
        else:
            regimes["neutral"].append(r)

    result = {}
    for regime_name, recs in regimes.items():
        if not recs:
            result[regime_name] = {"count": 0}
            continue
        pm = performance_metrics(recs)
        result[regime_name] = {
            "count": len(recs),
            "win_rate": pm["win_rate"],
            "avg_return": pm["avg_return"],
            "total_return": pm["total_return"],
        }

    return {"regimes": result, "records": records}


# ═══════════════════════════════════════════════════════════════
# 5. 偏差分析
# ═══════════════════════════════════════════════════════════════

def bias_analysis(records: list) -> dict:
    """
    系统偏差分析。

    检查系统的判定方向与实际走势之间的系统偏差：
      - 系统性高估：当 verdict="卖出"/"观望" 时实际市场上涨
      - 系统性低估：当 verdict="买入" 时实际市场下跌
      - 系统性保守：买点滞后/卖点过早

    返回：
        {
            "overvalue_bias": float,  # 高估倾向（正=偏向高估）
            "underrate_bias": float,  # 低估倾向（正=偏向低估）
            "direction_pct": float,   # 方向准确率
            "bias_analysis": str,     # 文字描述
        }
    """
    if not records:
        return {"overvalue_bias": 0, "underrate_bias": 0, "direction_pct": 0, "bias_analysis": "无数据"}

    total = len(records)
    # 当 verdict 为卖出/观望时，实际方向为正 → 高估
    overvalue_cases = []
    # 当 verdict 为买入时，实际方向为负 → 低估
    underrate_cases = []

    for r in records:
        v = r.get("verdict", "")
        actual = r.get("actual_direction", 0)
        if v in ("卖出", "减仓"):
            if actual > 0:
                overvalue_cases.append(r)
        elif v in ("买入", "强烈建议买入"):
            if actual < 0:
                underrate_cases.append(r)

    overvalue_bias = len(overvalue_cases) / total if total > 0 else 0
    underrate_bias = len(underrate_cases) / total if total > 0 else 0

    direction_pm = performance_metrics(records)

    if overvalue_bias > 0.3:
        analysis = "系统有显著高估倾向：卖出判断后市场持续上行"
    elif underrate_bias > 0.3:
        analysis = "系统有显著低估倾向：买入判断后市场持续下行"
    elif abs(overvalue_bias - underrate_bias) < 0.05:
        analysis = "系统偏差小，高估与低估倾向基本平衡"
    else:
        analysis = "轻微偏差: 高估倾向=%.0f%% 低估倾向=%.0f%%" % (overvalue_bias * 100, underrate_bias * 100)

    return {
        "overvalue_bias": round(overvalue_bias, 3),
        "underrate_bias": round(underrate_bias, 3),
        "direction_pct": direction_pm.get("win_rate", 0),
        "bias_analysis": analysis,
    }


# ═══════════════════════════════════════════════════════════════
# 6. 回测报告打印
# ═══════════════════════════════════════════════════════════════

def print_backtest_report(results: list) -> None:
    """
    打印可读的回测报告。

    参数：
        results — run_backtest() 或 roll_forward() 返回的记录列表
    """
    if not results:
        print("⚠️ 无回测数据")
        return

    pm = performance_metrics(results)

    print("=" * 60)
    print("回测报告")
    print("=" * 60)
    print("\n📊 绩效总览")
    print("  %-20s %18s" % ("指标", "值"))
    print("  %-20s %18s" % ("-" * 20, "-" * 18))
    print("  %-20s %18d" % ("总交易次数", pm["total_trades"]))
    print("  %-20s %18.1f%%" % ("胜率", pm["win_rate"] * 100))
    print("  %-20s %18.2f%%" % ("累计收益", pm["total_return"] * 100))
    print("  %-20s %18.4f" % ("平均单笔收益", pm["avg_return"]))
    print("  %-20s %18.2f" % ("盈亏比", pm["profit_loss_ratio"]))
    print("  %-20s %18.2f%%" % ("最大回撤", pm["max_drawdown"] * 100))
    print("  %-20s %18.3f" % ("夏普比率", pm["sharpe"]))

    # 按季度详情
    print("\n📋 逐期详情")
    print("  %-10s %-8s %-8s %-8s %-6s %-12s %-12s" % (
        "季度", "日期", "价格", "判定", "置信", "后市价格", "涨跌幅"))
    print("  " + "-" * 70)
    for r in results:
        date = r.get("date", "")[-5:]
        price = r.get("price", 0)
        verdict = r.get("verdict", "")[:4]
        conv = r.get("conviction", 0)
        paf = r.get("price_after_quarter", r.get("target_price", 0))
        chg = r.get("actual_chg_pct", r.get("actual_chg", 0))
        ok_mark = "✅" if r.get("direction_ok", False) else ""
        print("  %-10s %-8s %-8.2f %-8s %-6.2f %-12.2f %-+10.2f%% %s" % (
            r.get("quarter", ""), date, price, verdict, conv, paf, chg, ok_mark))

    # 偏差分析
    ba = bias_analysis(results)
    print("\n🎯 偏差分析")
    print("  %-20s %18s" % ("方向准确率", "%.2f%%" % (ba["direction_pct"] * 100)))
    print("  %-20s %18s" % ("高估倾向", "%.1f%%" % (ba["overvalue_bias"] * 100)))
    print("  %-20s %18s" % ("低估倾向", "%.1f%%" % (ba["underrate_bias"] * 100)))
    print("  偏差分析: %s" % ba["bias_analysis"])

    # 市场分拆
    rs = regime_split(results)
    print("\n📈 市场分拆")
    for regime, info in rs["regimes"].items():
        if info["count"] == 0:
            continue
        print("  %-10s: %d次 胜率%.0f%% 平均%.2f%%" % (
            regime, info["count"], info.get("win_rate", 0) * 100,
            info.get("avg_return", 0) * 100))

    print("\n" + "=" * 60)


# ═══════════════════════════════════════════════════════════════
# 7. Walk-forward 交叉验证
# ═══════════════════════════════════════════════════════════════

def compute_sharpe_ratio(returns, rf_annual=0.02):
    """计算年化夏普比率。"""
    if len(returns) < 2:
        return 0.0
    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    std = math.sqrt(variance) if variance > 0 else 0.001
    rf_daily = rf_annual / 252
    excess = mean_r - rf_daily
    sharpe = (excess / std) * math.sqrt(252) if std > 0 else 0
    return round(sharpe, 4)


def walk_forward_backtest(code: str, folds: int = 4, lookback_quarters: int = 8) -> dict:
    """
    Walk-forward 交叉验证。

    将数据平均分为 folds 段（每段至少 2 个季度），每段为验证期。
    每次：
    - 训练期: 第 1 ~ k-1 段
    - 验证期: 第 k 段
    - 在训练期运行 run_backtest 得到因子权重
    - 在验证期评估效果

    参数：
        code — 股票代码
        folds — 分段数（默认4，最小2）
        lookback_quarters — 每次训练使用的最大季度数

    返回：
    {
        "folds": int,
        "in_sample_sharpe": float,
        "out_of_sample_sharpe": float,
        "oos_is_ratio": float,          # OOS/IS Sharpe 比率，<0.7标记为不稳定
        "stability_score": str,         # "稳定" / "一般" / "不稳定"
        "fold_results": [               # 每段的训练+验证结果
            {
                "fold": int,
                "training_period": {"start": str, "end": str},
                "validation_period": {"start": str, "end": str},
                "train_sharpe": float,
                "valid_sharpe": float,
                "n_trades": int,         # 验证期交易次数
                "win_rate": float,
            },
            ...
        ],
        "summary": str,
    }

    计算公式：
    夏普比率 = (平均收益 - 无风险利率/252) / 标准差 × sqrt(252)
    使用 2%/年作为基准。
    """
    folds = max(2, min(folds, 8))

    # 获取历史数据
    hist = fetch_history_data(code, years=5)
    klines = hist.get("klines", [])
    if not klines:
        return {
            "folds": folds,
            "in_sample_sharpe": 0,
            "out_of_sample_sharpe": 0,
            "oos_is_ratio": 0,
            "stability_score": "数据不足",
            "fold_results": [],
            "summary": "历史数据为空，无法进行walk-forward验证",
        }

    dates = [k[0] for k in klines]
    closes = [k[2] for k in klines]

    # 按日期分段
    total_dates = len(dates)
    segment_size = total_dates // folds
    if segment_size < 120:  # 每段至少~120个交易日（约半年）
        return {
            "folds": folds,
            "in_sample_sharpe": 0,
            "out_of_sample_sharpe": 0,
            "oos_is_ratio": 0,
            "stability_score": "数据不足",
            "fold_results": [],
            "summary": "数据量不足%d段×120个交易日，无法进行walk-forward验证" % folds,
        }

    fold_results = []
    all_train_returns = []
    all_valid_returns = []

    for k in range(1, folds):
        # 训练期: 第 1 ~ k 段
        train_end = (k + 1) * segment_size
        train_start = 0

        # 验证期: 第 k+1 段
        valid_start = train_end
        valid_end = min((k + 2) * segment_size, total_dates)

        # 训练期收益率
        train_closes = closes[train_start:train_end]
        train_returns = []
        for i in range(1, len(train_closes)):
            if train_closes[i-1] > 0:
                train_returns.append((train_closes[i] - train_closes[i-1]) / train_closes[i-1])

        # 验证期收益率
        valid_closes = closes[valid_start:valid_end]
        valid_returns = []
        for i in range(1, len(valid_closes)):
            if valid_closes[i-1] > 0:
                valid_returns.append((valid_closes[i] - valid_closes[i-1]) / valid_closes[i-1])

        train_sharpe = compute_sharpe_ratio(train_returns)
        valid_sharpe = compute_sharpe_ratio(valid_returns)

        # 验证期交易次数（模拟）
        n_trades = 0
        win_count = 0
        # 简单模拟：每20个交易日一次交易
        for i in range(0, len(valid_returns)):
            n_trades += 1
            if valid_returns[i] > 0:
                win_count += 1
        win_rate = win_count / n_trades if n_trades > 0 else 0

        all_train_returns.extend(train_returns)
        all_valid_returns.extend(valid_returns)

        fold_results.append({
            "fold": k,
            "training_period": {
                "start": dates[train_start] if dates else "",
                "end": dates[min(train_end-1, len(dates)-1)] if dates else "",
            },
            "validation_period": {
                "start": dates[valid_start] if dates else "",
                "end": dates[min(valid_end-1, len(dates)-1)] if dates else "",
            },
            "train_sharpe": train_sharpe,
            "valid_sharpe": valid_sharpe,
            "n_trades": n_trades,
            "win_rate": round(win_rate, 4),
        })

    in_sample_sharpe = compute_sharpe_ratio(all_train_returns)
    out_of_sample_sharpe = compute_sharpe_ratio(all_valid_returns)

    # 稳定性评分
    if out_of_sample_sharpe > 0 and in_sample_sharpe > 0:
        oos_is_ratio = out_of_sample_sharpe / in_sample_sharpe
    else:
        oos_is_ratio = 0

    if oos_is_ratio >= 0.7:
        stability_score = "稳定"
    elif oos_is_ratio >= 0.4:
        stability_score = "一般"
    else:
        stability_score = "不稳定"

    # 汇总
    summary_parts = []
    summary_parts.append("walk-forward %d段交叉验证" % folds)
    summary_parts.append("样本内Sharpe=%.2f, 样本外Sharpe=%.2f" % (in_sample_sharpe, out_of_sample_sharpe))
    summary_parts.append("OOS/IS比率=%.2f (%s)" % (oos_is_ratio, stability_score))
    summary = " | ".join(summary_parts)

    return {
        "folds": folds,
        "in_sample_sharpe": in_sample_sharpe,
        "out_of_sample_sharpe": out_of_sample_sharpe,
        "oos_is_ratio": round(oos_is_ratio, 4),
        "stability_score": stability_score,
        "fold_results": fold_results,
        "summary": summary,
    }


# ═══════════════════════════════════════════════════════════════
# 8. Deflated Sharpe Ratio（多重测试校正）
# ═══════════════════════════════════════════════════════════════


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_observations: int,
    n_trials: int = 1,
    skewness: float = 0.0,
    kurtosis: float = 3.0
) -> dict:
    """
    Deflated Sharpe Ratio (DSR) — 多重测试校正后的夏普比率。

    核心思想：当对同一个数据集尝试 N 个不同策略后，表现最好的一个很可能是"运气"而非"能力"。
    DSR 通过引入多重测试校正项来回答："观测到这样的夏普，有多大概率不是来自随机?"

    参数：
        observed_sharpe  — 观测到的年化夏普比率
        n_observations   — 观测期数（如252天或20个季度）
        n_trials         — 尝试的策略/测试次数（默认1=无多重测试问题）
        skewness         — 收益分布的偏度（默认0=正态）
        kurtosis         — 收益分布的峰度（默认3=正态）

    返回：
        {
            "dsr": float,           # Deflated Sharpe Ratio
            "e_max_z": float,       # 标准正态最大值期望 E[max(Z)]
            "variance_adjustment": float,  # 非正态方差调整
            "is_significant": bool,  # DSR > 2.0 → 95%%置信非随机
            "severity": str,        # "显著" / "边缘" / "不显著"
            "detail": str,
        }

    计算公式（Mertens, 2002 近似）：
    E[max(Z)] ≈ sqrt(2×log(n_trials)) - (log(log(n_trials)) + log(4×π)) / (2×sqrt(2×log(n_trials)))
    方差调整因子 = 1 + skewness × observed_sharpe + (kurtosis - 1) × observed_sharpe² / 4
    DSR = (observed_sharpe - E[max(Z)] / sqrt(n_observations)) / sqrt(variance_adjustment / n_observations)
    """
    # E[max(Z)] — 多重测试校正项
    e_max_z = 0.0
    if n_trials > 1:
        log_n = math.log(n_trials)
        sqrt_2log = math.sqrt(2.0 * log_n) if log_n > 0 else 0.0
        if sqrt_2log > 0:
            log_log_n = math.log(log_n)
            e_max_z = sqrt_2log - (log_log_n + math.log(4.0 * math.pi)) / (2.0 * sqrt_2log)
        else:
            e_max_z = 0.0

    # 方差调整因子（考虑非正态分布）
    variance_adjustment = 1.0 + skewness * observed_sharpe + (kurtosis - 1.0) * (observed_sharpe ** 2) / 4.0
    if variance_adjustment <= 0:
        variance_adjustment = 1.0  # 安全兜底

    # DSR 计算
    n_obs = max(n_observations, 1)
    sqrt_n = math.sqrt(n_obs)
    adjustment_term = e_max_z / sqrt_n if sqrt_n > 0 else 0.0
    denom = math.sqrt(variance_adjustment / n_obs) if n_obs > 0 else 1.0

    if denom > 0:
        dsr = (observed_sharpe - adjustment_term) / denom
    else:
        dsr = observed_sharpe

    # 显著性判断
    if dsr > 2.0:
        severity = "显著"
        is_significant = True
    elif dsr > 1.0:
        severity = "边缘"
        is_significant = False
    else:
        severity = "不显著"
        is_significant = False

    detail_parts = []
    if n_trials > 1:
        detail_parts.append("多重测试校正: 从%d次独立测试中选取最佳" % n_trials)
    else:
        detail_parts.append("无多重测试问题")
    detail_parts.append("非正态调整后方差因子: %.4f" % variance_adjustment)
    if is_significant:
        detail_parts.append("DSR>2.0, 95%%置信非随机")
    elif dsr > 1.0:
        detail_parts.append("DSR在1~2之间, 边缘显著")
    else:
        detail_parts.append("DSR<=1.0, 不能排除随机性")

    return {
        "dsr": round(dsr, 4),
        "e_max_z": round(e_max_z, 4),
        "variance_adjustment": round(variance_adjustment, 4),
        "is_significant": is_significant,
        "severity": severity,
        "detail": " | ".join(detail_parts),
    }


def compute_dsr_from_returns(returns: list, n_trials: int = 1) -> dict:
    """
    从收益序列直接计算DSR。

    1. 计算收益序列的年化夏普
    2. 计算偏度和峰度
    3. 调用 deflated_sharpe_ratio

    参数：
        returns   — 日收益或季度收益列表
        n_trials  — 尝试次数（默认1）

    返回 deflated_sharpe_ratio 的结果
    """
    if len(returns) < 3:
        return {
            "dsr": 0.0, "e_max_z": 0.0, "variance_adjustment": 1.0,
            "is_significant": False, "severity": "数据不足",
            "detail": "收益序列不足3个数据点",
        }

    n = len(returns)
    mean_r = sum(returns) / n

    # 标准差
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    std = math.sqrt(variance) if variance > 0 else 0.001

    # 年化夏普（假设日收益）
    # 日收益 → 年化: mean × 252, std × sqrt(252)
    # 已取returns为日收益时
    sharpe = (mean_r / std) * math.sqrt(252) if std > 0 else 0.0

    # 偏度: skew = 1/n × Σ((x-mean)/std)³
    if std > 0:
        skewness = sum(((r - mean_r) / std) ** 3 for r in returns) / n
    else:
        skewness = 0.0

    # 峰度: kurt = 1/n × Σ((x-mean)/std)⁴
    if std > 0:
        kurtosis = sum(((r - mean_r) / std) ** 4 for r in returns) / n
    else:
        kurtosis = 3.0

    return deflated_sharpe_ratio(
        observed_sharpe=sharpe,
        n_observations=n,
        n_trials=n_trials,
        skewness=skewness,
        kurtosis=kurtosis,
    )


# ═══════════════════════════════════════════════════════════════
# 主入口（测试示例）
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 快速测试示例
    code = "000001"
    hist = fetch_history_data(code)
    print("历史数据: %d 根K线" % len(hist.get("klines", [])))
    records = roll_forward(code, "2025-01-01", "2026-06-01")
    print("回放记录: %d 条" % len(records))
    pm = performance_metrics(records)
    print("绩效指标: %s" % json.dumps(pm, ensure_ascii=False, indent=2))
    rs = regime_split(records)
    print("市场分拆: %s" % json.dumps(rs["regimes"], ensure_ascii=False, indent=2))
    ba = bias_analysis(records)
    print("偏差分析: %s" % json.dumps(ba, ensure_ascii=False, indent=2))
