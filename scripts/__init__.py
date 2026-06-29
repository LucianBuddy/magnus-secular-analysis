"""
scripts 包 — magnus-secular-analysis 数据预处理模块包
========================================================
子模块拆分：
  - peer_engine:    行业映射、同行识别、竞争矩阵
  - valuation:      估值计算、因子权重、安全边际、后验复盘、选股因子结构化
  - cash_quality:   现金转化率、Owner Earnings、ROE分解、价值陷阱、财务异常检测
  - risk:           卖出条件、再评估触发器、市场调节、行业景气轮动
  - position:       仓位建议、综合信号生成
  - cache:          缓存系统
  - valuation_ensemble: 多路径估值集成
  - backtest:       回测框架、Walk-forward 交叉验证
  - technical:      技术面9因子评分
  - portfolio:      组合层面检查、换仓成本模型
  - sentiment:      情绪信号（词典匹配法）
  - event_calendar: 公司行动日历
  - factor_analysis:因子归因分析（简化Barra模型）
  - batch:          批量并行分析
  - performance:    持仓绩效归因（简化Brinson模型）
  - data_layer:     数据接入统一层

向后兼容：from scripts.preprocess import build_summary 仍然可用。
"""

# ── 从子模块导入所有公共符号 ─────────────────────────────

from .peer_engine import *
from .valuation import *
from .cash_quality import *
from .risk import *
from .position import *
from .preprocess import *
from .cache import *
from .valuation_ensemble import *
from .technical import *
from .portfolio import *
from .backtest import *
from .sentiment import *
from .event_calendar import *
from .factor_analysis import *
from .batch import *
from .performance import *
from .data_layer import *

# 这些模块定义了 build_summary / SS_SCHEMA / new_ss
# preprocess.py 有完整的重新导出

# ── 可用功能总览 ──
# peer_engine:   INDUSTRY_PEER_MAP, STOCK_TO_INDUSTRY,
#                get_industry, get_industry_peers, filter_peers,
#                compute_industry_median_pe, build_competition_matrix
# valuation:     compute_pe_history, compute_pb_history, compute_forward_pe,
#                compute_dynamic_pe_limit, compute_normalized_cagr,
#                compute_valuation_verdict, get_rf_rate, get_inflation_rate,
#                get_cost_of_equity, get_oe_multiple, margin_of_safety_continuous,
#                scenario_analysis, estimate_percentile, review_accuracy,
#                review_accuracy_extended, get_factor_weights,
#                FACTOR_WEIGHT_MAP, FACTOR_WEIGHT_DEFAULT,
#                PE_LIMIT_CONFIG, INDUSTRY_BETA, ERP_CHINA,
#                FACTOR_DEF_REGISTRY, compute_factor_scores, factor_radar,
#                deduplicate_factor_signals, FACTOR_CORRELATION_GROUPS
# cash_quality:  CashConvResult, analyze_cash_conversion,
#                infer_moat_trend, roe_quality, value_trap_check,
#                auto_is_light_asset, LIGHT_ASSET_INDUSTRIES,
#                financial_anomaly_detection, ANOMALY_RULES
# risk:          market_regime_adjustment, macro_regime_adjustment,
#                sell_condition_check, compute_triggers, get_rf_trend,
#                estimate_economic_phase, sector_cycle_advice, CYCLE_MAP,
#                CROSS_ASSET_SENSITIVITY, ASSET_TICKER_MAP,
#                fetch_asset_trend, cross_asset_risk_premium
# position:      position_sizing, generate_signal, generate_signal_v2,
#                generate_signal_with_matrix, cross_validate_signals,
#                calibrate_conviction, record_verdict_outcome,
#                SIGNAL_MATRIX
# preprocess:    SS_SCHEMA, new_ss, build_summary
# portfolio:     portfolio_check, build_weight_plan, estimate_slippage,
#                add_slippage_to_build_plan, TRANSACTION_COST_PARAMS,
#                risk_budget_usage, worst_case_analysis, batch_worst_case
# sentiment:     compute_sentiment_score, fetch_news_sentiment, sentiment_signal
# event_calendar: next_events, fetch_historical_ex_dividend_dates
# factor_analysis: fetch_factor_returns, calculate_alpha_beta, factor_exposure_report
# batch:         batch_analyze, batch_build_summary
# backtest:      run_backtest, roll_forward, performance_metrics, regime_split,
#                bias_analysis, walk_forward_backtest, compute_sharpe_ratio,
#                deflated_sharpe_ratio, compute_dsr_from_returns
# performance:   attribution_analysis, summary_attribution, compare_periods
# data_layer:    get_quote, get_kline, get_index_quote, get_us_markets,
#                get_hk_market, get_finance_snapshot, get_multi_period_finance,
#                get_fund_flow, get_north_flow, get_concept_blocks,
#                get_industry_peers
