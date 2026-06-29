"""
position — 仓位管理与信号生成
==============================
仓位建议、综合信号生成（基本面+技术面融合）。
"""

import json
import os
from typing import Optional


# ── 仓位建议 ─────────────────────────────────────────────

def position_sizing(margin_premium: float, conviction_high: bool = False) -> dict:
    """
    根据安全边际/溢价输出推荐仓位。

    参数：
        margin_premium — 溢价（正=溢价, 负=折价）
        conviction_high — 高置信度
    返回：{pct, label, detail}
    """
    if margin_premium <= -0.30 and conviction_high:
        return {"pct": 0.80, "label": "重仓", "detail": "边际>30%+高置信度"}
    if margin_premium <= -0.20:
        return {"pct": 0.50, "label": "半仓", "detail": "边际>20%"}
    if margin_premium <= -0.10:
        return {"pct": 0.30, "label": "轻仓", "detail": "边际>10%"}
    if margin_premium >= 0.30:
        return {"pct": 0.0, "label": "清仓", "detail": "溢价>30%"}
    if margin_premium >= 0.10:
        return {"pct": 0.0, "label": "不持有", "detail": "溢价>10%"}
    return {"pct": 0.0, "label": "观望", "detail": "边际不足10%"}


# ── 综合信号生成 ──────────────────────────────────────────

def generate_signal(step2_verdict: str, step3_score: float, time_horizon: str) -> dict:
    """
    综合基本面(Step2)与技术面(Step3)信号。

    参数：
        step2_verdict — "买入"/"持有"/"观望"/"卖出"
        step3_score   — -1~1 技术面总分
        time_horizon  — "长线"/"中线"/"短线"

    返回：
        {verdict, conviction, conflict, fund_score, tech_score, explanation, position}
    """
    if time_horizon == "短线":
        return {"verdict": "短线独立", "conviction": 0, "explanation": ""}

    verdict_score = {"卖出": -1.0, "观望": -0.3, "持有": 0.0, "买入": 0.7, "强烈买入": 1.0}
    fund_score = verdict_score.get(step2_verdict, 0.0)

    w_fund = 0.8 if time_horizon == "长线" else 0.6
    w_tech = 1.0 - w_fund
    total = fund_score * w_fund + step3_score * w_tech

    conflict = (fund_score >= 0.5 and step3_score <= -0.5) or \
               (fund_score <= -0.5 and step3_score >= 0.5)

    if total >= 0.5:
        verdict = "买入"; conv = round(abs(total), 2)
    elif total >= 0.0:
        verdict = "持有"; conv = round(abs(total), 2)
    elif total >= -0.3:
        verdict = "观望"; conv = round(abs(total), 2)
    else:
        verdict = "卖出"; conv = round(abs(total), 2)

    parts = []
    if conflict:
        parts.append("⚠️ 基本面与技术面信号冲突")
    parts.append("基本面=%.1f(权重%.1f) 技术面=%.1f(权重%.1f)" % (fund_score, w_fund, step3_score, w_tech))

    return {
        "verdict": verdict, "conviction": conv, "conflict": conflict,
        "fund_score": fund_score, "tech_score": step3_score,
        "explanation": " | ".join(parts),
        "position": position_sizing(-total),
    }


# ── 置信度校准（P2-6）────────────────────────────────────

CALIBRATION_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cache", "calibration.json")


def load_calibration() -> dict:
    """
    从 cache 加载置信度校准记录。

    返回 {
        "buckets": {"0-0.2": {"correct": 0, "total": 0}, ...},
        "version": 1,
    }
    """
    default = {
        "buckets": {
            "0-0.2": {"correct": 0, "total": 0},
            "0.2-0.4": {"correct": 0, "total": 0},
            "0.4-0.6": {"correct": 0, "total": 0},
            "0.6-0.8": {"correct": 0, "total": 0},
            "0.8-1.0": {"correct": 0, "total": 0},
        },
        "version": 1,
    }

    try:
        if os.path.exists(CALIBRATION_FILE):
            with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "buckets" in data:
                    return data
    except (json.JSONDecodeError, IOError):
        pass

    return default


def save_calibration(records: dict):
    """
    保存校准记录到 cache。

    参数：
        records — load_calibration() 返回的 dict
    """
    try:
        os.makedirs(os.path.dirname(CALIBRATION_FILE), exist_ok=True)
        with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except (IOError, OSError):
        pass


def _conviction_bucket(conviction: float) -> str:
    """根据置信度返回桶名。"""
    if conviction < 0.2:
        return "0-0.2"
    elif conviction < 0.4:
        return "0.2-0.4"
    elif conviction < 0.6:
        return "0.4-0.6"
    elif conviction < 0.8:
        return "0.6-0.8"
    else:
        return "0.8-1.0"


def record_verdict_outcome(verdict: str, conviction: float, actual_chg: float):
    """
    记录一次预测结果（由后验复盘或回测调用）。

    conviction 按 0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0 分5桶，
    记录每个桶的预测方向和实际方向是否一致。

    参数：
        verdict     — "买入" / "持有" / "观望" / "卖出"
        conviction  — 0~1 置信度
        actual_chg  — 实际涨跌幅（小数，如 0.05 = +5%）
    """
    bucket = _conviction_bucket(conviction)
    cal = load_calibration()

    # 判断预测方向
    pred_direction = 0  # 0=中性, 1=看多, -1=看空
    if verdict in ("买入", "强烈建议买入"):
        pred_direction = 1
    elif verdict in ("卖出", "减仓"):
        pred_direction = -1

    # 判断实际方向
    actual_direction = 0
    if actual_chg > 0.02:
        actual_direction = 1
    elif actual_chg < -0.02:
        actual_direction = -1

    # 是否一致
    is_correct = pred_direction == actual_direction

    cal["buckets"][bucket]["total"] += 1
    if is_correct:
        cal["buckets"][bucket]["correct"] += 1

    save_calibration(cal)


def calibrate_conviction(conviction: float, verdict: str) -> dict:
    """
    根据历史校准数据修正 conviction。

    查询最终桶的历史正确率：
    - 如果桶内有 >= 5 个样本 → conviction = 该桶正确率
    - 如果桶内不足 5 个样本 → 返回原始值

    参数：
        conviction  — 原始置信度（0~1）
        verdict     — 判定结果

    返回：
        {"original": float, "calibrated": float, "samples": int,
         "bucket": str, "bucket_accuracy": float}
    """
    cal = load_calibration()
    bucket = _conviction_bucket(conviction)

    buck = cal["buckets"][bucket]
    samples = buck["total"]
    accuracy = buck["correct"] / max(buck["total"], 1)

    if samples >= 5:
        calibrated = round(accuracy, 4)
    else:
        calibrated = conviction

    return {
        "original": round(conviction, 4),
        "calibrated": round(calibrated, 4),
        "samples": samples,
        "bucket": bucket,
        "bucket_accuracy": round(accuracy, 4),
    }


# ── 综合信号生成 v2 ─────────────────────────────────────────

def generate_signal_v2(step2_verdict: str, step3_result: dict,
                       time_horizon: str) -> dict:
    """
    generate_signal 的增强版。

    在原有基础上增加：
    1. 校准后的 conviction
    2. 冲突检测时给出更详细的解释
    3. 输出校准前后对比

    参数：
        step2_verdict — "买入"/"持有"/"观望"/"卖出"
        step3_result — dict（至少包含 "score" 字段，也可包含 details/signals/macd 等）
        time_horizon — "长线"/"中线"/"短线"

    向后兼容：generate_signal 仍可用，内部调用 generate_signal_v2 后取子集。
    """
    # 提取 step3_score
    if isinstance(step3_result, dict):
        step3_score = step3_result.get("score", 0.0)
    else:
        step3_score = float(step3_result)

    # 调用原始生成逻辑
    raw = _generate_signal_inner(step2_verdict, step3_score, time_horizon)

    # 校准 conviction
    cal = calibrate_conviction(raw["conviction"], raw["verdict"])
    calibrated_conviction = cal["calibrated"]

    # 冲突检测详细化
    fund_score = raw["fund_score"]
    tech_score = raw["tech_score"]
    conflict = raw["conflict"]
    conflict_detail = ""

    if conflict:
        if fund_score >= 0.5 and tech_score <= -0.5:
            conflict_detail = "基本面看多(%.1f) vs 技术面看空(%.1f)：估值偏低但短期走势弱，建议等待技术面企稳" % (
                fund_score, tech_score)
        elif fund_score <= -0.5 and tech_score >= 0.5:
            conflict_detail = "基本面看空(%.1f) vs 技术面看多(%.1f)：估值偏高但短期走势强，建议利用反弹减仓" % (
                fund_score, tech_score)
        else:
            conflict_detail = "基本面(%.1f)与技术面(%.1f)信号分歧" % (fund_score, tech_score)

    result = {
        "verdict": raw["verdict"],
        "conviction": calibrated_conviction,
        "conviction_original": raw["conviction"],
        "calibration": cal,
        "conflict": conflict,
        "conflict_detail": conflict_detail,
        "fund_score": fund_score,
        "tech_score": tech_score,
        "explanation": raw["explanation"],
        "position": raw["position"],
        "time_horizon": time_horizon,
        **({} if not isinstance(step3_result, dict) else {
            "tech_detail": step3_result.get("details", {}),
            "tech_signals": step3_result.get("signals", []),
        }),
    }

    return result


def _generate_signal_inner(step2_verdict: str, step3_score: float,
                           time_horizon: str) -> dict:
    """
    generate_signal 的内部实现（无校准）。
    """
    if time_horizon == "短线":
        return {"verdict": "短线独立", "conviction": 0, "explanation": ""}

    verdict_score = {"卖出": -1.0, "观望": -0.3, "持有": 0.0, "买入": 0.7, "强烈买入": 1.0}
    fund_score = verdict_score.get(step2_verdict, 0.0)

    w_fund = 0.8 if time_horizon == "长线" else 0.6
    w_tech = 1.0 - w_fund
    total = fund_score * w_fund + step3_score * w_tech

    conflict = (fund_score >= 0.5 and step3_score <= -0.5) or \
               (fund_score <= -0.5 and step3_score >= 0.5)

    if total >= 0.5:
        verdict = "买入"
        conv = round(abs(total), 2)
    elif total >= 0.0:
        verdict = "持有"
        conv = round(abs(total), 2)
    elif total >= -0.3:
        verdict = "观望"
        conv = round(abs(total), 2)
    else:
        verdict = "卖出"
        conv = round(abs(total), 2)

    parts = []
    if conflict:
        parts.append("⚠️ 基本面与技术面信号冲突")
    parts.append("基本面=%.1f(权重%.1f) 技术面=%.1f(权重%.1f)" % (fund_score, w_fund, step3_score, w_tech))

    return {
        "verdict": verdict,
        "conviction": conv,
        "conflict": conflict,
        "fund_score": fund_score,
        "tech_score": step3_score,
        "explanation": " | ".join(parts),
        "position": position_sizing(-total),
    }


# ── generate_signal 保持向后兼容 ──────────────────────────
# generate_signal 现在调用 v2 后取子集（保持旧接口返回值一致）

def generate_signal(step2_verdict: str, step3_score: float,
                    time_horizon: str) -> dict:
    """
    综合基本面(Step2)与技术面(Step3)信号。

    向后兼容接口，内部调用 generate_signal_v2 后取子集。

    参数：
        step2_verdict — "买入"/"持有"/"观望"/"卖出"
        step3_score   — -1~1 技术面总分（也接受 dict 含 score 字段）
        time_horizon  — "长线"/"中线"/"短线"

    返回：
        {verdict, conviction, conflict, fund_score, tech_score, explanation, position}
    """
    v2 = generate_signal_v2(step2_verdict, step3_score, time_horizon)
    return {
        "verdict": v2["verdict"],
        "conviction": v2["conviction"],
        "conflict": v2["conflict"],
        "fund_score": v2["fund_score"],
        "tech_score": v2["tech_score"],
        "explanation": v2["explanation"],
        "position": v2["position"],
    }


# ── 信号交叉验证矩阵（#3/#5：技术面+基本面交叉验证）───────

# 信号矩阵：(基本面方向, 技术面方向) → (最终裁决, 策略说明)
# 技术面方向："偏多"(score>0.3) / "中性"(-0.3≤score≤0.3) / "偏空"(score<-0.3)
SIGNAL_MATRIX = {
    ("买入", "偏多"):      ("买入", "正常建仓"),
    ("买入", "中性"):      ("买入", "等回调"),
    ("买入", "偏空"):      ("观望", "技术面不支持"),
    ("持有", "偏多"):      ("持有", "继续"),
    ("持有", "中性"):      ("持有", "观望"),
    ("持有", "偏空"):      ("减仓", "技术面恶化"),
    ("观望", "偏多"):      ("买入", "技术面确认"),
    ("观望", "中性"):      ("观望", "等待"),
    ("观望", "偏空"):      ("卖出", "双重确认"),
    ("卖出", "偏多"):      ("减仓", "技术面有支撑，减仓替代清仓"),
    ("卖出", "中性"):      ("卖出", "正常"),
    ("卖出", "偏空"):      ("清仓", "双重确认"),
    # 强烈买入视为买入
    ("强烈买入", "偏多"):  ("买入", "强信号建仓"),
    ("强烈买入", "中性"):  ("买入", "等回调"),
    ("强烈买入", "偏空"):  ("观望", "矛盾信号，等待确认"),
    # 减仓/清仓视为卖出
    ("减仓", "偏多"):      ("减仓", "减仓执行"),
    ("减仓", "中性"):      ("减仓", "减仓执行"),
    ("减仓", "偏空"):      ("卖出", "确认减仓"),
    ("清仓", "偏多"):      ("减仓", "技术面反弹，减仓替代清仓"),
    ("清仓", "中性"):      ("清仓", ""),
    ("清仓", "偏空"):      ("清仓", "双重确认"),
}


def _tech_direction(tech_score: float) -> str:
    """将技术面分数转化为方向标签。"""
    if tech_score > 0.3:
        return "偏多"
    elif tech_score < -0.3:
        return "偏空"
    else:
        return "中性"


def cross_validate_signals(fundamental_verdict: str, tech_score: float) -> dict:
    """
    使用信号矩阵做基本面+技术面交叉验证。

    取代原有的简单加权求和，使用规则矩阵来融合信号。
    当矩阵查询不到对应组合时，回退到加权求和模式。

    参数：
        fundamental_verdict — "买入"/"持有"/"观望"/"卖出"/"强烈买入"/"减仓"/"清仓"
        tech_score — -1~1 技术面总分

    返回：
        {
            "verdict": str,         # 最终裁决
            "reason": str,          # 策略说明
            "fundamental": str,     # 基本面方向
            "technical": str,       # 技术面方向
            "matrix_used": bool,    # 是否使用了信号矩阵
            "conflict": bool,       # 是否存在冲突
        }
    """
    tech_dir = _tech_direction(tech_score)
    key = (fundamental_verdict, tech_dir)

    if key in SIGNAL_MATRIX:
        verdict, reason = SIGNAL_MATRIX[key]
        # 检查是否存在冲突
        base_dir_map = {"买入": 1, "强烈买入": 1, "持有": 0, "观望": 0, "减仓": -1, "卖出": -1, "清仓": -1}
        final_dir_map = {"买入": 1, "持有": 0, "观望": 0, "减仓": -1, "卖出": -1, "清仓": -1}
        fund_dir = base_dir_map.get(fundamental_verdict, 0)
        final_dir = final_dir_map.get(verdict, 0)
        conflict = abs(fund_dir - final_dir) >= 2

        return {
            "verdict": verdict,
            "reason": reason,
            "fundamental": fundamental_verdict,
            "technical": tech_dir,
            "matrix_used": True,
            "conflict": conflict,
        }

    # 矩阵未命中，回退加权求和的标签
    score_map = {"卖出": -1.0, "清仓": -1.0, "减仓": -0.7, "观望": -0.3, "持有": 0.0, "买入": 0.7, "强烈买入": 1.0}
    fund_score = score_map.get(fundamental_verdict, 0.0)
    total = fund_score * 0.6 + tech_score * 0.4

    if total >= 0.5:
        verdict = "买入"
    elif total >= 0.0:
        verdict = "持有"
    elif total >= -0.3:
        verdict = "观望"
    else:
        verdict = "卖出"

    fund_dir_map = {"买入": 1, "强烈买入": 1, "持有": 0, "观望": 0, "减仓": -1, "卖出": -1, "清仓": -1}
    final_dir_map2 = {"买入": 1, "持有": 0, "观望": 0, "减仓": -1, "卖出": -1, "清仓": -1}
    fund_dir2 = fund_dir_map.get(fundamental_verdict, 0)
    final_dir2 = final_dir_map2.get(verdict, 0)
    conflict2 = abs(fund_dir2 - final_dir2) >= 2

    return {
        "verdict": verdict,
        "reason": "回退加权求和",
        "fundamental": fundamental_verdict,
        "technical": tech_dir,
        "matrix_used": False,
        "conflict": conflict2,
    }


def generate_signal_with_matrix(step2_verdict: str, step3_result: dict,
                                 time_horizon: str) -> dict:
    """
    使用信号矩阵的综合信号生成（替代 generate_signal_v2 的线性加权）。

    在 generate_signal_v2 基础上，将信号融合方式从加权求和替换为信号矩阵查询。

    参数：
        step2_verdict — "买入"/"持有"/"观望"/"卖出"/"强烈买入"/"减仓"/"清仓"
        step3_result — dict（至少含 "score" 字段）
        time_horizon — "长线"/"中线"/"短线"

    返回：
        {verdict, conviction, matrix_result, calibration, ...}
    """
    if time_horizon == "短线":
        return {"verdict": "短线独立", "conviction": 0, "explanation": ""}

    if isinstance(step3_result, dict):
        tech_score = step3_result.get("score", 0.0)
    else:
        tech_score = float(step3_result)

    # 使用信号矩阵
    matrix = cross_validate_signals(step2_verdict, tech_score)

    # 确定 conviction
    verdict_score = {"买入": 0.7, "持有": 0.5, "观望": 0.3, "减仓": 0.6, "卖出": 0.7, "清仓": 0.8}
    conv = verdict_score.get(matrix["verdict"], 0.3)

    # 校准
    cal = calibrate_conviction(conv, matrix["verdict"])
    calibrated_conviction = cal["calibrated"]

    # 仓位
    if matrix["verdict"] in ("买入", "清仓"):
        pos = position_sizing(-0.2)  # 模拟买入/清仓
    elif matrix["verdict"] in ("卖出", "减仓"):
        pos = position_sizing(0.2)
    else:
        pos = {"pct": 0.0, "label": "观望", "detail": "信号矩阵裁决"}

    explanation_parts = []
    if matrix["conflict"]:
        explanation_parts.append("⚠️ 信号冲突")
    explanation_parts.append("基本面=%s 技术面=%s(%.2f)" % (
        step2_verdict, matrix["technical"], tech_score))
    explanation_parts.append("矩阵裁决:%s" % matrix["reason"])

    result = {
        "verdict": matrix["verdict"],
        "conviction": calibrated_conviction,
        "conviction_original": conv,
        "calibration": cal,
        "matrix_result": matrix,
        "conflict": matrix["conflict"],
        "fund_score": 0.0,
        "tech_score": tech_score,
        "explanation": " | ".join(explanation_parts),
        "position": pos,
        "time_horizon": time_horizon,
        "method": "signal_matrix",
    }

    if isinstance(step3_result, dict):
        result["tech_detail"] = step3_result.get("details", {})
        result["tech_signals"] = step3_result.get("signals", [])

    return result


# ── __all__ ──────────────────────────────────────────────────

__all__ = [
    "position_sizing",
    "generate_signal",
    "generate_signal_v2",
    "generate_signal_with_matrix",
    "cross_validate_signals",
    "calibrate_conviction",
    "record_verdict_outcome",
    "load_calibration",
    "save_calibration",
    "SIGNAL_MATRIX",
]
