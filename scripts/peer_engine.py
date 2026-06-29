"""
peer_engine — 行业映射与同行识别
===================================
覆盖常见A股行业，每行业精选5-10家可比公司。
映射规则：100%硬编码，零外部依赖。
"""

from typing import Optional, List


# ── 行业映射 ─────────────────────────────────────────────────

INDUSTRY_PEER_MAP = {
    # 消费电子
    "消费电子": ["002475", "002241", "601138", "300433", "600745", "002600", "603160"],
    # 半导体设计
    "半导体设计": ["603986", "603893", "688008", "300782", "688012", "002049", "300661", "688981"],
    # 半导体设备/材料
    "半导体设备": ["002371", "688012", "300604", "688120", "688072", "002409", "300567"],
    # 半导体制造/封测
    "半导体封测": ["600584", "002156", "603005", "688981", "688396"],
    # 电力设备
    "电力设备": ["600406", "601567", "600885", "300124", "002028", "002074", "300274", "601877"],
    # 光伏
    "光伏": ["601012", "600438", "688599", "002459", "688390", "300274", "603806"],
    # 新能源车/锂电
    "新能源汽车": ["002594", "300750", "002074", "300014", "300457", "002850", "601689", "600104"],
    # 白酒
    "白酒": ["600519", "000858", "000568", "600809", "002304", "603369", "000596"],
    # 银行
    "银行": ["601398", "601939", "601288", "600036", "600016", "000001", "002142", "601166"],
    # 保险
    "保险": ["601318", "601628", "601601", "601336", "000627"],
    # 证券
    "证券": ["600030", "601211", "601688", "000776", "600837", "601066", "002736"],
    # AI/算力
    "AI算力": ["601138", "000977", "688041", "300308", "688256", "002230", "300502"],
    # 通信/5G
    "通信": ["600941", "601728", "000063", "300502", "002583", "600522", "603236"],
    # 医药/创新药
    "创新药": ["600276", "300760", "002007", "300122", "688180", "300347", "300529", "000538"],
    # 医疗器械
    "医疗器械": ["300760", "002901", "300529", "300206", "603387", "688029", "300003"],
    # 家电
    "家电": ["000333", "000651", "600690", "002242", "002032", "603486", "002508"],
    # 互联网/平台
    "互联网": ["300059", "603444", "002602", "300418", "002624", "300033", "300226"],
    # 军工
    "军工": ["600760", "600893", "600862", "002179", "600118", "600185", "600391"],
    # 消费电子零部件（代工/ODM）
    "消费电子代工": ["002475", "002241", "601138", "603160", "002600", "300433", "300115"],
    # 电网自动化
    "电网自动化": ["600406", "601567", "600885", "002028", "300124", "002747", "300360"],
    # 食品饮料
    "食品饮料": ["600887", "600519", "000858", "603288", "000568", "002714", "300146"],
    # 煤炭/能源
    "煤炭": ["601225", "600188", "601088", "600985", "600348", "002128", "601001"],
    # 水电/公用事业
    "公用事业": ["600900", "600886", "600025", "601985", "600011", "600023", "003816"],
    # 机械/自动化
    "机械": ["300124", "002444", "600031", "000988", "002008", "300747", "603338"],
    # 云计算/软件
    "云计算软件": ["002230", "300033", "000977", "300454", "688111", "688568", "300496"],
    # 汽车零部件
    "汽车零部件": ["601689", "002048", "002126", "300750", "002850", "600741", "000887"],
    # 化工/新材料
    "化工新材料": ["600309", "000830", "002601", "600585", "002709", "002460", "300568"],
    # 机器人
    "机器人": ["300124", "688017", "300024", "002747", "688160", "002008", "300607"],
}

# 反向映射
STOCK_TO_INDUSTRY = {}
for ind, codes in INDUSTRY_PEER_MAP.items():
    for c in codes:
        if c not in STOCK_TO_INDUSTRY:
            STOCK_TO_INDUSTRY[c] = ind

STOCK_TO_INDUSTRY.update({
    "002463": "消费电子",
    "300782": "半导体设计",
    "002916": "消费电子",
    "002938": "消费电子代工",
    "601012": "光伏",
    "600438": "光伏",
    "688599": "光伏",
    "600584": "半导体封测",
    "688256": "AI算力",
    "300274": "电力设备",
    "300124": "机械",
    "002594": "新能源汽车",
    "600519": "白酒",
    "600900": "公用事业",
    "688017": "机器人",
})


# ── 行业查询 ─────────────────────────────────────────────────

def get_industry(code):
    """返回股票所属行业名。"""
    if code in STOCK_TO_INDUSTRY:
        return STOCK_TO_INDUSTRY[code]
    if code.startswith("688"):
        return "半导体设计"
    if code.startswith("300"):
        return "消费电子"
    if code.startswith("002"):
        return "机械"
    if code.startswith("000"):
        return "消费电子"
    if code.startswith("601") or code.startswith("600"):
        return "电力设备"
    return "机械"


def get_industry_peers(code):
    """返回同行业可比公司代码列表（去自身，最多8家）。"""
    ind = get_industry(code)
    peers = INDUSTRY_PEER_MAP.get(ind, [])
    peers = [c for c in peers if c != code]
    return peers[:8]


# ── 同行数据处理 ──────────────────────────────────────────

def filter_peers(peers: List[dict]) -> List[dict]:
    """剔除 PE>100 的 outlier，不足2家返回空列表。"""
    valid = [p for p in peers if abs(p.get("pe", 0) or 0) <= 100]
    return valid if len(valid) >= 2 else []


def compute_industry_median_pe(peers: List[dict],
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


# ── 竞争格局对比矩阵 ─────────────────────────────────────

def build_competition_matrix(target_code, peer_codes, target_data=None, peers_data=None):
    """
    构建竞争格局对比矩阵（7维：PE/PB/ROE/毛利率/营收增速/负债率/市值）。

    参数：
        target_code — 分析标的代码
        peer_codes — 同行代码列表
        target_data — dict {pe, pb, roe, gm, rg, dr, mcap}
        peers_data  — list of dict [{code, name, pe, pb, roe, gm, rg, dr, mcap}, ...]

    返回：{"matrix": [...], "summary": str}
    """
    if not target_data or not peers_data:
        return {"matrix": [], "summary": "数据不足，无法构建竞争格局对比"}

    dims = [
        {"key": "pe", "label": "PE(TTM)", "higher_is_better": False},
        {"key": "pb", "label": "PB", "higher_is_better": False},
        {"key": "roe", "label": "ROE(%)", "higher_is_better": True},
        {"key": "gm", "label": "毛利率(%)", "higher_is_better": True},
        {"key": "rg", "label": "营收增速(%)", "higher_is_better": True},
        {"key": "dr", "label": "负债率(%)", "higher_is_better": False},
        {"key": "mcap", "label": "市值(亿)", "higher_is_better": None},
    ]

    matrix_rows = []
    for dim in dims:
        key = dim["key"]
        nv = target_data.get(key, 0) or 0
        row = {"维度": dim["label"], "标的": nv}
        all_vals = [(c.get(key, 0) or 0) for c in peers_data]
        if all_vals:
            sorted_vals = sorted(all_vals)
            n = len(sorted_vals)
            if n >= 3:
                q1 = sorted_vals[n // 4]
                q3 = sorted_vals[(3 * n) // 4]
                median = sorted_vals[n // 2]
                row["同行中位"] = median
                row["同行Q1"] = q1
                row["同行Q3"] = q3

                if dim["higher_is_better"] is True:
                    rank = sum(1 for v in all_vals if v > nv) + 1
                    row["排位"] = "%d/%d" % (rank, n + 1)
                    row["评级"] = "领先" if rank <= n // 3 else ("落后" if rank >= (2 * n) // 3 else "中游")
                elif dim["higher_is_better"] is False:
                    rank = sum(1 for v in all_vals if v < nv) + 1
                    row["排位"] = "%d/%d" % (rank, n + 1)
                    row["评级"] = "最低(优)" if key == "dr" else ("领先" if rank <= n // 3 else "中游")
                else:
                    row["同行均值"] = round(sum(all_vals) / n, 2)
        matrix_rows.append(row)

    return {
        "matrix": matrix_rows,
        "summary": "竞争格局对比表已生成，包含 %d 个维度 x %d 家同行" % (
            len(dims), len(peers_data) + 1),
    }


# ── __all__ ──────────────────────────────────────────────────

__all__ = [
    "INDUSTRY_PEER_MAP", "STOCK_TO_INDUSTRY",
    "get_industry", "get_industry_peers",
    "filter_peers", "compute_industry_median_pe",
    "build_competition_matrix",
]
