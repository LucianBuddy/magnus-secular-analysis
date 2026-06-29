# 变更记录

格式：`v主版本.次版本.修订号`，规则：
- **主版本**（x.0.0）：架构优化或重构
- **次版本**（0.x.0）：功能模块增减
- **修订号**（0.0.x）：Bug修复或模块内部优化

---

## v2.4.0 (2026-06-26)

### 新增

**持仓绩效归因**（#3）：scripts/performance.py 新增 `attribution_analysis()`（简化 Brinson 模型，分解选股贡献/行业配置贡献/择时贡献），`summary_attribution()`（一句话摘要），`compare_periods()`（多期对比 + Alpha波动率 + 信息比率）。纯参数驱动，零外部数据依赖。

**数据接入统一层**（#5）：scripts/data_layer.py 新增统一数据获取入口。包含：
  - `get_quote(codes)` — 腾讯通道（优先）→ 新浪通道（回退），解析 name/price/change_pct/pe_ttm/mcap_yi/pb 等
  - `get_kline(code, count)` — 百度 K线（优先，带MA5/10/20）→ 腾讯 K线（回退）
  - `get_index_quote()` / `get_us_markets()` / `get_hk_market()` — 指数/美股/港股行情
  - `get_finance_snapshot()` / `get_multi_period_finance()` — 财务快照（备用入口）
  - `get_fund_flow()` / `get_north_flow()` — 资金流向（东财接口）
  - `get_concept_blocks()` / `get_industry_peers()` — 行业/概念/同行
  - 内置限流器（≥1s），统一 timeout=10，失败返回 {"error": True} 不抛异常
  - `_cache_wrap()` — 集成 scripts.cache 缓存

### 变更
- scripts/__init__.py：新增 performance 和 data_layer 两个模块导入，功能总览增加对应行
- SKILL.md：新增 v2.4.0 模块引用，数据采集部分增加 data_layer 可选入口说明

### 兼容性
- 纯 Python 实现，urllib.request 零外部依赖
- Python 3.6+ 兼容
- `from scripts import *` 不报错
- `from scripts.preprocess import build_summary` 仍可用

## v2.3.0 (2026-06-26)

### 新增
- **Deflated Sharpe Ratio（多重测试校正）**（#1）：backtest.py 新增 `deflated_sharpe_ratio()`（Mertens 2002 近似, 含 E[max(Z)] 多重测试校正项 + 偏度峰度方差调整）和 `compute_dsr_from_returns()`（从收益序列直接计算），DSR>2.0 标记 95% 置信非随机
- **Monte Carlo 估值分布**（#2）：valuation_ensemble.py 新增 `monte_carlo_valuation()`（10000次正态/均匀分布模拟, DCF+终值, 输出均值/中位数/众数/标准差/偏度/百分位数/直方图）和 `mc_compare_to_market()`（估值分布与市价对比，含分位和低估概率）
- **因子暴露回环**（#4）：portfolio.py 新增 `risk_budget_usage()`（检查高β/高R²/独特α/信号一致性/因子分组去重，输出仓位调整系数）
- **大类资产联动信号**（#6）：risk.py 新增 `CROSS_ASSET_SENSITIVITY`（15行业×外部资产敏感性矩阵）、`ASSET_TICKER_MAP`（6类资产API映射）、`fetch_asset_trend()`（腾讯/新浪API + 1h缓存）、`cross_asset_risk_premium()`（外生风险溢价 -1~1）
- **最坏情景分析**（#7）：portfolio.py 新增 `worst_case_analysis()`（止损金额/VaR/恢复所需收益率/风险评级/行动建议）和 `batch_worst_case()`（批量 + 合并风险标记）

### 变更
- scripts/__init__.py：新增 deflated_sharpe_ratio, compute_dsr_from_returns, monte_carlo_valuation, mc_compare_to_market, risk_budget_usage, worst_case_analysis, batch_worst_case, CROSS_ASSET_SENSITIVITY, ASSET_TICKER_MAP, fetch_asset_trend, cross_asset_risk_premium 导出
- SKILL.md：新增 v2.3.0 模块引用

### 兼容性
- 纯 Python 实现，无 numpy/pandas 依赖
- Python 3.6+ 兼容（type hint 避坑）
- API 调用失败不抛出异常，标注"数据不可用"后正常返回

## v2.2.1 (2026-06-26)

### 新增
- **信号聚合去重**（#2）：valuation.py 新增 `FACTOR_CORRELATION_GROUPS`（5组）和 `deduplicate_factor_signals()`，高相关性因子同组取均值消除重复计分，输出去重后总分+分组明细+归一化得分
- **信号交叉验证矩阵**（#3/#5）：position.py 新增 `SIGNAL_MATRIX`（16条规则），涵盖买入/持有/观望/卖出/减仓/清仓 × 偏多/中性/偏空的二维决策表
- **`cross_validate_signals()`**：底层矩阵查询函数，未命中时回退加权求和
- **`generate_signal_with_matrix()`**：基于信号矩阵的综合信号生成，替代线性加权方式

### 变更
- `SIGNAL_MATRIX` 使基本面+技术面的融合方式从

### 新增
- **NLP情绪信号**（P4-1）：新增 scripts/sentiment.py，词典匹配法（850+积极/消极词条），支持 `compute_sentiment_score()`（头条/摘要去重计数）、`fetch_news_sentiment()`（新浪个股新闻API）、`sentiment_signal()`（情绪分转因子方向信号）
- **因子归因分析**（P4-2）：新增 scripts/factor_analysis.py，简化 Barra 模型，包含 `fetch_factor_returns()`（腾讯API获取沪深300市场因子）、`calculate_alpha_beta()`（最小二乘法手动计算α/β/R²，无外部依赖）、`factor_exposure_report()`（因子暴露报告+可读解释）
- **换仓成本模型**（P4-3）：portfolio.py 新增 `TRANSACTION_COST_PARAMS`（5档市值分档）、`estimate_slippage()`（冲击成本 ∝ participation_rate^0.6 × impact_coeff）、`add_slippage_to_build_plan()`（融入建仓计划）
- **Walk-forward 交叉验证**（P4-4）：backtest.py 新增 `walk_forward_backtest()`（多段交叉验证+OOS/IS Sharpe比率+稳定性评级）、`compute_sharpe_ratio()`（纯Python夏普比率计算）
- **行业景气轮动**（P4-5）：risk.py 新增 `CYCLE_MAP`（5情景×4象限经济周期）、`estimate_economic_phase()`（沪深300近3月涨跌→增长方向 + 10Y国债趋势→通胀方向）、`sector_cycle_advice()`（行业配置建议+安全边际修正）
- **财务异常检测**（P4-6）：cash_quality.py 新增 `ANOMALY_RULES`（6类规则）、`financial_anomaly_detection()`（参数可选，只检测有数据的维度，含应收/营收匹配、OCF/净利润背离、异常毛利率、资产减值突增、商誉风险、营收质量）
- **公司行动日历**（P4-7）：新增 scripts/event_calendar.py，包含 `next_events()`（固定季报截止日+历史分红推断除权除息）、`fetch_historical_ex_dividend_dates()`（新浪API历史分红）、`FIXED_EVENTS`（4固定截止日期），所有事件标注置信度（高/中/低）
- **批量并行执行**（P4-8）：新增 scripts/batch.py，包含 `batch_build_summary()`（批量多股票数据预计算，ThreadPoolExecutor 4线程）、`batch_analyze()`（并行分析+技术面评分+组合检查）
- **选股因子结构化**（P4-9）：valuation.py 新增 `FACTOR_DEF_REGISTRY`（7因子注册中心）、`compute_factor_scores()`（多因子评分归一化到-1~1）、`factor_radar()`（多股票雷达数据）

### 变更
- `scripts/__init__.py`：新增 sentiment / event_calendar / factor_analysis / batch 四个模块导入
- SKILL.md：新增 Step 2-E 中集成选股因子结构化引用、Step 4-B 换仓成本说明

---

## v2.1.0 (2026-06-26)

### 新增
- **回测数据自动回填**（P2-2）：backtest.py 新增 `fetch_finance_at_date()`、`fetch_historical_finance()`、`fetch_historical_quotes()`、`get_quarter_end_dates()`、`run_backtest()` 和 `print_backtest_report()`，支持在每个季度末自动获取财务数据并运行完整判定流程
- **因子权重滚动优化**（P2-5）：valuation.py 新增 `optimize_factor_weights()` 和 `evaluate_single_factor()`，根据回测历史记录按单因子准确率动态优化权重
- **组合层面检查**（P2-4）：新增 scripts/portfolio.py，支持行业集中度检查（单行≤30%）、流动性检查（日成交≥5000万）、相关性警告、权重调整建议和建仓计划
- **宏观过滤器**：risk.py 新增 `get_rf_trend()` 和 `macro_regime_adjustment()`（双参数版本），基于 10Y 国债收益率趋势叠加宏观层安全边际修正；新增 `MACRO_FILTERS` 常量配置
- **技术面多周期增强**（P2-3）：新增 scripts/technical.py，包含 `compute_macd()`（金叉/死叉/零轴上/零轴下）、`detect_divergence()`（顶底背离）、`check_weekly_trend()`（周线多头/空头/震荡）、`compute_volume_profile()`（筹码密集区近似支撑阻力）、`compute_enhanced_tech_score()`（综合 9 因子评分替代原 5 因子）
- **置信度校准**（P2-6）：position.py 新增 `load_calibration()`、`save_calibration()`、`record_verdict_outcome()`、`calibrate_conviction()` 和 `generate_signal_v2()`，按 5 桶分桶记录预测准确率并校准 conviction

### 变更
- `generate_signal()` 内部调用 `generate_signal_v2()` 后取子集，保持向后兼容
- `market_regime_adjustment()` 拆分为内部 `_impl` + 包装函数，保持单参数接口不变

---

## v2.0.0 (2026-06-26)

### 架构变更（P3-1: 模块拆分）
- **模块拆分**：scripts/preprocess.py 拆分为 peer_engine.py / valuation.py / cash_quality.py / risk.py / position.py / cache.py + preprocess.py（向后兼容 shim）+ __init__.py
- `scripts/__init__.py` 重新导出所有公共符号，`from scripts.preprocess import build_summary` 仍可用

### 新增
- **缓存系统**（P3-2）：scripts/cache.py，按分类缓存（K线2h/财务24h/同行7d/新闻1h/市场1h），md5 key，JSON 文件存储，自动创建 cache/ 目录
- **多路径估值集成**（P2-1）：scripts/valuation_ensemble.py，加权聚合 PE/PB/DDM/OE 四路径估值，输出均值+90%CI+分歧度
- **回测框架**（P2-2）：scripts/backtest.py，季度末滚窗回放，绩效指标（夏普/胜率/盈亏比/最大回撤），市场分拆，偏差分析
- **行业因子加权矩阵**（P1-1）：FACTOR_WEIGHT_MAP 覆盖 28 个行业，每个行业配置 4-5 个关键因子+权重
- **动态 maint_capex**（P1-2）：analyze_cash_conversion() 新增 asset_age_years 参数，资产年限驱动维护开支
- **真实三年 OCF**（P1-3）：build_summary() 新增 ocf_3y 参数，真实三年 OCF 计算 cash_conv_3y

### 修复
- **baidu_kline_with_ma 解析回退**（P0-1）：a-stock-data SKILL.md 中新增兼容模式，先尝试 quotation_kline_ab，失败回退 newMarketData
- **Eastmoney 失败时概念板块 fallback**（P0-2）：build_summary() 新增 web_fetcher 参数，fund_flow_ok=False 时自动 web_fetch 获取板块归属，SS_SCHEMA 新增 fallback_cblk_attempted 标记
- **美股数据腾讯备用通道**（P0-3）：SKILL.md 数据采集表新增美股三大指数行（gb_dji/gb_ixic/gb_inx）

### SKILL.md 更新
- 所有 scripts/preprocess.py 引用改为指向拆分后模块
- Step 2-D 新增因子加权矩阵调用说明
- 相关段落新增 cache.py 引用说明

---

## v1.8.0 (2026-06-25)

### 新增
- **市场环境调节**（#1）：market_regime_adjustment() 根据市场情绪[亢奋/正常/恐慌/震荡]修正安全边际±5%（preprocess.py + SKILL.md）
- **4个No跳转分支B**（#2）：预筛4No不再跳过，改为走分支B（相对估值），保留分析产出
- **分析时效性标记**（#3）：报告头部强制输出分析日期/数据截止/有效期限
- **假设风险评级**（#4）：关键假设清单每条标注[风险:低/中/高]，标记影响最大的前2条
- **分支AB输出统一**（#5）：分支B强制输出标准化估值区间和置信度，与分支A可比

### 变更
- SKILL.md 8问过滤器：4个No跳过→走分支B
- SKILL.md 分支B：新增强制输出格式（估值区间+置信度）
- SKILL.md 报告结构：C时效性/D市场环境/E报告声明/F假设清单（含风险评级）
- preprocess.py：新增market_regime_adjustment()

---

## v1.7.1 (2026-06-25)

### 新增
- **ROE质量分解（杜邦拆分）**（#5）：roe_quality(dr, roe, npm) 区分高杠杆驱动的ROE与高利润率驱动的ROE，输出6级分类标签
- **ss字段引用表**（#6）：Step 1.5 新增结构化字段引用表，统一LLM在分析流中的字段名调用，消除别名歧义

### 变更
- SKILL.md 2-C 财务健康：新增ROE质量分解调用说明
- SKILL.md Step 1.5：新增ss字段引用表（22个字段）
- preprocess.py：新增roe_quality()函数

---

## v1.7.0 (2026-06-25)

### 新增
- **资本配置质量评估**（#1）：管理层评估新增4项量化指标（回购记录/分红质量/收购质量/商誉比），护城河趋势 infer_moat_trend()
- **关键假设清单**（#2）：每个结论附带5条前置假设说明
- **护城河趋势量化**（#3）：infer_moat_trend(gm_3y, roe_3y) 从毛利率和ROE趋势输出[增强/稳定/削弱]（preprocess.py）
- **持有期修正安全边际**（#4）：margin_of_safety_continuous 新增 holding_months 参数，长线/中线/短线不同要求（preprocess.py）
- **Reference 文件压缩**（#5）：8个.summary.md（共2.5K字），替代147KB全量文件。不满足时回退全量
- **通胀/实际收益覆盖**（#6）：get_inflation_rate() 实时获取CPI，DDM输出双版本（名义g=2%/实际g=rg-inflation）
- **情景分析**（#7）：scenario_analysis(oe_base, rg_3y, gm_3y) 输出三情景估值区间（悲观OE-20%×倍0.85 ~ 乐观OE+15%×倍1.10）
- **SS_SCHEMA 清理**（#8）：_clean_ss() 去除死字段，review_accuracy_extended() 增加盈亏比

### 变更
- SKILL.md 管理层评估：新增资本配置4项检查
- SKILL.md 2-E DDM：新增通胀调整和DDM双版本
- SKILL.md 2-E 估值：新增情景分析输出
- SKILL.md Step4：新增持有期修正、假设清单段落
- SKILL.md 所有reference引用：改为.summary.md + 回退机制
- preprocess.py 20个函数 → 28个函数（+8 new），1234行 → 1458行

---

## v1.6.0 (2026-06-25)

### 新增
- **非经常性损益检查**（#1）：Q5验证新增 Q5a，检查扣非净利润/净利润比值，<0.7标记⚠️盈利质量警告。数据源 mootdx finance() kcfjcxsy 或新浪三表
- **权益风险溢价(ERP)加入OE/DDM**（#2）：新增 `INDUSTRY_BETA` 映射（28个行业），`get_cost_of_equity(industry)` 计算 rf + β×ERP(6.5%)。OE 估值倍数从固定 15x/20x 改为 `1/cost_of_equity` 动态计算，DDM 折现率改为股权资本成本

### 变更
- SKILL.md Q5验证：新增 5a 非经常性损益检查
- SKILL.md 数据采集表：新增扣非净利润行
- SKILL.md 2-E OE估值：倍数从硬编码改为 `get_oe_multiple()` 动态
- SKILL.md 2-E DDM：折现率从 rf 改为 coe(rf+β×ERP)
- SKILL.md 行业β参考：银行0.7、白酒0.8、公用0.6、消费电子1.1、半导体1.4、AI算力1.5
- preprocess.py OE倍数：15x/20x → 基于资本成本的动态倍数

---

## v1.5.0 (2026-06-25)

### 新增
- **DDM无风险利率实时化**（#1）：`get_rf_rate()` 通过新浪/腾讯实时获取中债10Y收益率，fallback 2.0%，替代硬编码2.5%
- **估值裁决矩阵预计算**（#2）：`compute_valuation_verdict(pe, cagr, block_median_pe, pe_limit)` 一次性完成PEG+板块溢价+容忍上限三步裁决，LLM直接读取结构化结果，消除文本推理分歧
- **竞争格局对比表**（#3）：`build_competition_matrix(target_code, peer_codes, target_data, peers_data)` 输出7维结构化对比矩阵（PE/PB/ROE/毛利率/营收增速/负债率/市值），含四分位和排位评级
- **安全边际连续评分**（#4）：`margin_of_safety_continuous(price, intrinsic_median, conviction)` 输出0-100连续分数替代离散档次，联动position_sizing()输出仓位建议

### 变更
- SKILL.md DDM无风险利率：写死2.5% → `get_rf_rate()` 实时获取
- SKILL.md 行业估值修正模块：双轨制裁决 → `compute_valuation_verdict()` 预计算
- SKILL.md 2-D 竞争格局：新增 `build_competition_matrix()` 调用说明
- SKILL.md 安全边际：离散5档 → 连续评分(0-100)

---

## v1.4.0 (2026-06-25)

### 新增
- **轻资产自动识别**：`auto_is_light_asset(industry)` 自动判断，覆盖半导体设计/云计算/创新药/互联网/白酒/AI算力，无需手动传参（#3）
- **综合信号系统**：`generate_signal(step2_verdict, tech_score, time_horizon)` 加权融合基本面+技术面，长线(8:2)/中线(6:4)权重分离，自动检测并标记冲突（#1）
- **仓位建议**：`position_sizing(margin_premium)` 连续输出0-80%仓位比例，替代离散三档（#1附属）
- **量化卖出条件**：`sell_condition_check()` 输出4项结构化检查，含PE/PEG超限、毛利率连续下降+ROE<8%、OCF为负等定量规则（#4）
- **后验复盘系统**：`review_accuracy(predictions, actuals)` 计算方向胜率、行业归因；HEARTBEAT.md 注册月度检查；创建 wiki/wiki/prediction-review.md 存储复盘记录（#6）

### 变更
- SKILL.md Step 2-D: `is_light_asset` 改为自动推断
- SKILL.md Step 3: 从10行均线描述改为结构化tech_score计算
- SKILL.md Step 4-B: 新增综合信号+仓位建议输出
- SKILL.md 卖出条件: 从4项纯定性改为量化规则+结构化输出
- SKILL.md 后验复盘: 从声明改为可执行流程
- HEARTBEAT.md: 激活月度复盘

---

## v1.3.1 (2026-06-25)

### 修改
- **PE历史分位偏倚修复**：`compute_pe_history()` 新增 `eps_history` 参数，支持逐期精确PE计算。有历史EPS序列时自动使用，消除用当前TTM反代历史导致的"系统性偏低"偏倚（算法bug）
- **前向PE基数效应防护**：新增 `compute_forward_pe()`，要求最近4个季度全部正利润才能计算，防止亏损→微利期的同比虚高导致前向PE低估（算法bug）
- **产业链容忍上限动态化**：新增 `compute_dynamic_pe_limit(code, block_median_pe)`，用板块同行PE中位数 × 行业系数替代静态绝对值（50x/60x/30x/25x）。block_median_pe不可用时回退绝对上限
- SKILL.md Step1.5 数据摘要：增加 eps_history 参数说明
- SKILL.md 产业链容忍上限：改为动态系数表
- SKILL.md 前向PE：改为 compute_forward_pe() 带基数防护
- SKILL.md 双轨制裁决：用"动态上限"替代"绝对估值"判断

---

## v1.3.0 (2026-06-25)

### 新增
- **数据降级系统**：东财接口受限时自动降级，不中断分析流程
  - 概念板块：东财→web_fetch("同花顺 "+股票名+" 概念板块")→memory_search wiki
  - 个股新闻：东财→web_fetch(股票名+" 最新公告 消息")
  - 所有降级项在报告中标注缺失
- **自动同行识别**（preprocess.py）
  - `INDUSTRY_PEER_MAP`：覆盖28个行业的硬编码同行代码映射表（190+标的）
  - `STOCK_TO_INDUSTRY`：个股→行业反向映射
  - `get_industry(code)`：查表识别行业，未命中按代码前缀分类
  - `get_industry_peers(code)`：返回同行代码列表（去自身，≤8家），零外部依赖
  - `compute_normalized_cagr()`：中位数法平滑CAGR，消除周期基数效应

### 变更
- SKILL.md Step1 数据采集表：所有东财依赖项增加 fallback 列
- SKILL.md Step2-B 行业对标：同行选择改为 `get_industry_peers()` + tencent_quote 自动拉取
- preprocess.py 新增 `from typing import List, Dict`

---

## v1.2.0 (初始版本)

初始发布版。
