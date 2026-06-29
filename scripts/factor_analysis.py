#!/usr/bin/env python3
"""
因子归因分析模块（简化Barra模型）。
将组合收益分解为市场/规模/价值因子暴露。
"""

# 因子定义
MARKET_FACTOR_TICKER = "000300"   # 沪深300作为市场因子
SIZE_FACTOR_TICKER = "000905"     # 中证500作为规模代理
VALUE_FACTOR_PROXY = lambda pe: "低PE" if pe < 15 else "高PE"  # 简化


def fetch_factor_returns(start_date: str, end_date: str) -> dict:
    """
    获取因子收益率序列。

    通过腾讯API获取沪深300（市场因子）和创业板指（成长因子）的日收益。

    返回 {
        "market": [日收益列表],
        "dates": [日期列表],
        "avg_market_return": float,
    }
    """
    import requests
    from datetime import datetime, timedelta

    # 估算需要的年数
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")
        delta_days = (ed - sd).days
    except ValueError:
        return {"market": [], "dates": [], "avg_market_return": 0}

    years = max(1, delta_days // 365 + 1)

    try:
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,%d,qfq" % (
            MARKET_FACTOR_TICKER, years)
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://stock.qq.com",
        })
        d = r.json()
        data_sec = d.get("data", {})
        klines = (data_sec.get(MARKET_FACTOR_TICKER, {}).get("day", [])
                  or data_sec.get("qt", {}).get(MARKET_FACTOR_TICKER, {}).get("day", [])
                  or [])

        market_returns = []
        dates = []
        closes = [float(k[2]) for k in klines if len(k) >= 3]
        for i in range(1, len(closes)):
            ret = (closes[i] - closes[i-1]) / closes[i-1]
            market_returns.append(ret)
            dates.append(str(klines[i][0]))

        avg_market = sum(market_returns) / len(market_returns) if market_returns else 0

        return {
            "market": market_returns,
            "dates": dates,
            "avg_market_return": round(avg_market, 6),
        }
    except Exception:
        return {"market": [], "dates": [], "avg_market_return": 0}


def calculate_alpha_beta(
    stock_returns,
    market_returns,
    risk_free_rate=0.02
):
    """
    计算 α 和 β。

    使用最小二乘法公式（手动计算，无外部依赖）：
    beta = cov(stock, market) / var(market)
    alpha = avg(stock_return) - beta * avg(market_return) - rf/252

    返回 {alpha: float, beta: float, r_squared: float, annualized_alpha: float}
    """
    n = min(len(stock_returns), len(market_returns))
    if n < 5:
        return {"alpha": 0, "beta": 1, "r_squared": 0, "annualized_alpha": 0}

    sr = stock_returns[-n:]
    mr = market_returns[-n:]

    mean_s = sum(sr) / n
    mean_m = sum(mr) / n

    # 协方差
    cov = sum((s - mean_s) * (m - mean_m) for s, m in zip(sr, mr)) / n
    # 方差
    var_m = sum((m - mean_m) ** 2 for m in mr) / n

    beta = cov / var_m if var_m > 0 else 1.0
    alpha_daily = mean_s - beta * mean_m - risk_free_rate / 252

    # R²
    ss_res = sum((s - (alpha_daily + beta * m)) ** 2 for s, m in zip(sr, mr))
    ss_tot = sum((s - mean_s) ** 2 for s in sr)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return {
        "alpha": round(alpha_daily, 6),
        "beta": round(beta, 4),
        "r_squared": round(r2, 4),
        "annualized_alpha": round(alpha_daily * 252, 4),
    }


def factor_exposure_report(code, prices_or_returns=None):
    """
    生成因子暴露报告。

    如果提供了 prices_or_returns，据此计算。
    否则通过API获取数据计算。

    返回报告 dict 包含 alpha/beta/r² 和解释文字。
    """
    import requests

    if prices_or_returns and len(prices_or_returns) >= 5:
        # 使用传入的价格序列计算收益率
        if isinstance(prices_or_returns[0], float) and prices_or_returns[0] > 10:
            # 是价格而非收益率
            stock_returns = []
            for i in range(1, len(prices_or_returns)):
                if prices_or_returns[i-1] > 0:
                    stock_returns.append(
                        (prices_or_returns[i] - prices_or_returns[i-1]) / prices_or_returns[i-1])
        else:
            stock_returns = list(prices_or_returns)
    else:
        # 通过API获取
        from .backtest import fetch_history_data
        hist = fetch_history_data(code, years=2)
        closes = [k[2] for k in hist.get("klines", [])]
        stock_returns = []
        for i in range(1, len(closes)):
            stock_returns.append((closes[i] - closes[i-1]) / closes[i-1])

    if len(stock_returns) < 5:
        return {
            "alpha": 0, "beta": 1, "r_squared": 0,
            "annualized_alpha": 0,
            "explanation": "收益率数据不足5个样本",
            "n_observations": len(stock_returns),
        }

    # 获取同期市场收益率
    factor_data = fetch_factor_returns("2025-01-01", "2026-06-01")
    market_returns = factor_data.get("market", [])

    if len(market_returns) < 5:
        return {
            "alpha": 0, "beta": 1, "r_squared": 0,
            "annualized_alpha": 0,
            "explanation": "市场收益率数据不足",
            "n_observations": len(stock_returns),
        }

    result = calculate_alpha_beta(stock_returns, market_returns)

    # 解释文字
    beta = result["beta"]
    alpha = result["annualized_alpha"]
    r2 = result["r_squared"]

    if beta > 1.5:
        beta_desc = "高波动（β=%.2f>1.5），系统性风险敞口大" % beta
    elif beta > 1.0:
        beta_desc = "中高波动（β=%.2f），跟随市场但弹性更大" % beta
    elif beta > 0.7:
        beta_desc = "中等波动（β=%.2f），跟随市场波动" % beta
    else:
        beta_desc = "低波动（β=%.2f<0.7），防御性强" % beta

    if alpha > 5:
        alpha_desc = "显著超额收益（α=%.1f%%/年），选股能力突出" % alpha
    elif alpha > 0:
        alpha_desc = "轻度超额收益（α=%.1f%%/年）" % alpha
    elif alpha > -5:
        alpha_desc = "轻度负超额（α=%.1f%%/年），但统计上可能不显著" % alpha
    else:
        alpha_desc = "明显负超额（α=%.1f%%/年），选股有待改进" % alpha

    explanation = "%s | %s" % (beta_desc, alpha_desc)
    if r2 < 0.3:
        explanation += " | R²=%.2f，个股特质收益为主，市场因子解释力有限" % r2
    elif r2 > 0.7:
        explanation += " | R²=%.2f，收益高度跟随市场，个股alpha空间小" % r2

    result["explanation"] = explanation
    result["n_observations"] = len(stock_returns)
    return result


__all__ = [
    "fetch_factor_returns",
    "calculate_alpha_beta",
    "factor_exposure_report",
    "MARKET_FACTOR_TICKER",
    "SIZE_FACTOR_TICKER",
]
