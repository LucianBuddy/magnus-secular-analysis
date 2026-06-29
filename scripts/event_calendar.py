#!/usr/bin/env python3
"""
公司行动日历模块。
基于确定日期和简单规则预测未来30天关键事件。
"""

import datetime

# 固定的关键日期（已知规则）
FIXED_EVENTS = {
    "annual_report_deadline": {"rule": "每年4月底前发布年报", "month": 4, "day": 30},
    "q1_report_deadline": {"rule": "每年4月底前发布一季报", "month": 4, "day": 30},
    "semi_annual_deadline": {"rule": "每年8月底前发布中报", "month": 8, "day": 31},
    "q3_report_deadline": {"rule": "每年10月底前发布三季报", "month": 10, "day": 31},
}


def fetch_historical_ex_dividend_dates(code: str) -> list:
    """
    尝试通过新浪历史分红数据获取除权除息日期。
    如果失败（网络不可用或API变化），返回空列表。

    新浪分红数据API大致格式：
    http://vip.stock.finance.sina.com.cn/corp/go.php/vISSUE_ShareBonus/stockid/... .phtml
    但这个API已知不稳定，所以此函数不保证有效。
    """
    import requests

    try:
        # 尝试新浪分红数据
        url = "https://vip.stock.finance.sina.com.cn/corp/go.php/vISSUE_ShareBonus/stockid/%s.phtml" % code
        r = requests.get(url, timeout=5, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://vip.stock.finance.sina.com.cn",
        })
        # 大致提取日期行
        lines = r.text.split("\n")
        dates = []
        for line in lines:
            # 寻找类似 "2025-06-20" 的日期
            import re
            matches = re.findall(r'\d{4}-\d{2}-\d{2}', line)
            for m in matches:
                try:
                    dt = datetime.datetime.strptime(m, "%Y-%m-%d")
                    if dt < datetime.datetime.now():
                        dates.append(m)
                except ValueError:
                    pass
        return sorted(set(dates))
    except Exception:
        return []


def next_events(code, name):
    """
    获取某标的未来30天的关键事件。

    当前自动可推断的（无额外API依赖）：
    1. 季报截止日期（固定规则：4/30, 8/31, 10/31, 次年4/30）
    2. 年报 - 可以通过已发布年报日期推断下一年（如去年4月25日发，大概率今年类似日期）
    3. 除权除息日 - 可通过历史分红记录推断（如过去3年都是6月，今年大概率也在6-7月）

    参数：
        code — 股票代码
        name — 股票名称

    返回 [{date: "2026-07-15", type: "除权除息", description: "预计...", confidence: "高/中/低"}, ...]

    注意：没有外部API时，主要输出基于规则的季报截止日。

    所有事件标注置信度：
    - 高：固定截止日期（如4月30日年报截止）
    - 中：基于历史规律的推断（如过去3年同一月分红）
    - 低：基于行业惯例的猜测
    """
    today = datetime.date.today()
    future_limit = today + datetime.timedelta(days=30)
    events = []

    this_year = today.year

    # 1. 固定季报截止日
    deadlines = [
        ("annual_report", 4, 30, "年报"),
        ("q1_report", 4, 30, "一季报"),
        ("semi_annual", 8, 31, "中报"),
        ("q3_report", 10, 31, "三季报"),
    ]

    for key, m, d, label in deadlines:
        # 确定年份
        yr = this_year
        if key == "annual_report":
            # 年报是次年发布，当前日期在4月底之前，看上年年报
            if (today.month < 4) or (today.month == 4 and today.day <= 30):
                yr = this_year - 1
            else:
                yr = this_year
        elif key == "q1_report":
            yr = this_year
        elif key == "semi_annual":
            yr = this_year
        elif key == "q3_report":
            yr = this_year

        try:
            deadline_date = datetime.date(yr, m, d)
        except ValueError:
            if m == 9 and d == 31:
                deadline_date = datetime.date(yr, m, 30)
            else:
                continue

        if today <= deadline_date <= future_limit:
            # 截止日期提前1-2周给出提醒
            reminder_date = deadline_date - datetime.timedelta(days=14)
            if today <= reminder_date <= future_limit:
                events.append({
                    "date": reminder_date.strftime("%Y-%m-%d"),
                    "type": "报告期提醒",
                    "description": "距%s截止日(%.2d/%.2d)还有约2周" % (label, m, d),
                    "confidence": "高",
                })

            events.append({
                "date": deadline_date.strftime("%Y-%m-%d"),
                "type": "%s截止" % label,
                "description": "%s发布截止日期" % label,
                "confidence": "高",
            })

    # 2. 除权除息 — 通过历史分红推断
    hist_dividends = fetch_historical_ex_dividend_dates(code)
    if hist_dividends:
        # 如果有历史数据，看看最近3年的月份模式
        months = []
        for ds in hist_dividends[-5:]:  # 最近5次
            try:
                months.append(int(ds.split("-")[1]))
            except (ValueError, IndexError):
                pass
        if months:
            # 取最常见的月份
            from collections import Counter
            counter = Counter(months)
            most_common_month = counter.most_common(1)[0][0]
            # 推断今年同样月份
            ex_div_year = this_year
            ex_div_date = datetime.date(ex_div_year, most_common_month, 15)
            if today <= ex_div_date <= future_limit:
                events.append({
                    "date": ex_div_date.strftime("%Y-%m-%d"),
                    "type": "除权除息",
                    "description": "预计除权除息（历史%3d年数据推断，通常在%2d月前后）" % (
                        len(hist_dividends), most_common_month),
                    "confidence": "中",
                })
    else:
        # 无历史数据，给一个通用规则
        # 很多A股公司在5-7月除权除息
        for est_month in (6, 7):
            try:
                est_date = datetime.date(this_year, est_month, 15)
            except ValueError:
                continue
            if today <= est_date <= future_limit:
                events.append({
                    "date": est_date.strftime("%Y-%m-%d"),
                    "type": "除权除息",
                    "description": "大多数A股公司在6-7月除权除息，届时需查询公告确认",
                    "confidence": "低",
                })
                break  # 只推荐一个

    return sorted(events, key=lambda e: e["date"])


__all__ = [
    "next_events",
    "fetch_historical_ex_dividend_dates",
    "FIXED_EVENTS",
]
