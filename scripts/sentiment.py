#!/usr/bin/env python3
"""
简易情绪信号模块（词典匹配法）。
通过搜索财经新闻标题/摘要，基于积极/消极词表计算情绪得分。
"""

# 积极词表
POSITIVE_WORDS = {
    # 业绩/财务
    "预增", "扭亏", "大幅增长", "突破", "创纪录", "新高", "超预期",
    "净利润增长", "营收增长", "毛利率提升", "盈利能力改善",
    # 订单/业务
    "中标", "大单", "签订合同", "战略合作", "获得许可", "批准上市",
    "量产", "交付", "投产", "扩产",
    # 资金/股东
    "回购", "增持", "分红", "派息", "股权激励",
    "北向资金加仓", "主力资金净流入", "机构增持",
    # 行业/政策
    "政策利好", "行业景气", "需求旺盛", "供不应求",
    "国产替代", "政策支持",
    # 管理层
    "管理层增持", "股权激励", "员工持股",
}

# 消极词表
NEGATIVE_WORDS = {
    # 业绩/财务
    "预亏", "预减", "亏损", "下滑", "大幅下跌", "营收下降",
    "净利润下降", "毛利率下滑", "计提减值", "资产减值",
    "商誉减值", "坏账", "存货跌价",
    # 经营
    "立案", "调查", "处罚", "监管", "问询", "警示函", "整改",
    "停产", "减产", "停工", "违约", "诉讼", "仲裁", "冻结",
    "股权质押", "平仓", "强制",
    # 资金/股东
    "减持", "套现", "解禁", "资金流出", "主力净流出",
    "北向资金减仓", "机构减持",
    # 行业/风险
    "政策风险", "行业下行", "产能过剩", "竞争加剧",
    "客户流失", "订单减少", "延期交付",
    # 其他
    "暂停上市", "退市风险", "ST", "立案调查", "信用评级下调",
    "反腐", "行贿",
}


def compute_sentiment_score(headlines, summaries=None):
    """
    计算新闻情绪得分。

    处理逻辑：
    1. 遍历每条新闻标题和摘要
    2. 统计积极词和消极词的命中次数
    3. 情绪分 = (积极命中 - 消极命中) / 总命中数（分母=0时返回0）
    4. 去重：同一条新闻标题和摘要都命中同一个词只计1次

    返回:
    {
        "score": float,        # -1 ~ 1
        "positive_hits": int,
        "negative_hits": int,
        "total_articles": int,
        "sentiment_label": "积极/中性/消极",
        "top_positive_words": list[str],
        "top_negative_words": list[str],
    }
    """
    if not headlines:
        return {
            "score": 0.0,
            "positive_hits": 0,
            "negative_hits": 0,
            "total_articles": 0,
            "sentiment_label": "中性",
            "top_positive_words": [],
            "top_negative_words": [],
        }

    positive_hits = 0
    negative_hits = 0
    pos_word_count = {}
    neg_word_count = {}

    # 合并所有文本
    combined_texts = []
    for i, h in enumerate(headlines):
        texts_for_article = [h]
        if summaries and i < len(summaries) and summaries[i]:
            texts_for_article.append(summaries[i])
        combined_texts.append(texts_for_article)

    for texts in combined_texts:
        # 去重：同一条新闻中同一个词只计1次
        article_pos = set()
        article_neg = set()
        article_full_text = " ".join(texts)

        for word in POSITIVE_WORDS:
            if word in article_full_text:
                article_pos.add(word)
        for word in NEGATIVE_WORDS:
            if word in article_full_text:
                article_neg.add(word)

        for w in article_pos:
            positive_hits += 1
            pos_word_count[w] = pos_word_count.get(w, 0) + 1
        for w in article_neg:
            negative_hits += 1
            neg_word_count[w] = neg_word_count.get(w, 0) + 1

    total_hits = positive_hits + negative_hits
    if total_hits > 0:
        score = (positive_hits - negative_hits) / total_hits
    else:
        score = 0.0

    # 标签映射
    if score > 0.3:
        label = "积极"
    elif score < -0.3:
        label = "消极"
    else:
        label = "中性"

    # top 5 词
    top_pos = sorted(pos_word_count.items(), key=lambda x: -x[1])[:5]
    top_neg = sorted(neg_word_count.items(), key=lambda x: -x[1])[:5]

    return {
        "score": round(score, 4),
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
        "total_articles": len(headlines),
        "sentiment_label": label,
        "top_positive_words": [w for w, c in top_pos],
        "top_negative_words": [w for w, c in top_neg],
    }


def fetch_news_sentiment(code: str, name: str, days=3) -> dict:
    """
    从新闻获取情绪信号。

    使用 web_fetch 获取最近3天的新闻标题。
    因为不能保证 web_fetch 可用，提供一个备用路径：
    直接通过新浪个股新闻API获取.

    返回同上结构，但 data_source 标记数据来源。
    """
    import requests

    headlines = []
    summaries = []

    try:
        # 尝试新浪个股新闻API
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/News_MarketNews.queryStockNews?symbol={}&num=20&page=1&tag=gn&show=title,time,source,url".format(code)
        r = requests.get(url, timeout=5, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        })
        data = r.json()
        if isinstance(data, list):
            for item in data[:20]:
                title = item.get("title", "")
                if title:
                    headlines.append(title)
                    # 摘要可能不存在
                    summaries.append(item.get("intro", ""))
    except Exception:
        pass

    result = compute_sentiment_score(headlines, summaries if summaries else None)
    result["data_source"] = "新浪个股新闻" if headlines else "无可用新闻源"
    return result


def sentiment_signal(sentiment: dict, weight=0.10) -> dict:
    """
    将情绪分转为因子信号（供 factor_weights 使用）。

    规则：
    score > 0.3 → +1（积极）
    score < -0.3 → -1（消极）
    其他 → 0（中性）

    返回 {direction: -1/0/1, weight: float, detail: str}
    """
    score = sentiment.get("score", 0.0)
    label = sentiment.get("sentiment_label", "中性")

    if score > 0.3:
        direction = 1
    elif score < -0.3:
        direction = -1
    else:
        direction = 0

    return {
        "direction": direction,
        "weight": weight,
        "detail": "情绪信号: %s (score=%.2f, 权重=%.0f%%)" % (label, score, weight * 100),
    }


__all__ = [
    "compute_sentiment_score",
    "fetch_news_sentiment",
    "sentiment_signal",
    "POSITIVE_WORDS",
    "NEGATIVE_WORDS",
]
