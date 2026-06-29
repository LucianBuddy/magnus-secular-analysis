---
name: magnus-secular-analysis
description: A股长线价值投资分析（巴菲特框架）。当用户请求个股基本面分析、投资建议、公司估值、全面分析、系统分析时触发。
version: 2.2.0
changelog: CHANGELOG.md
---

# magnus-secular-analysis — A股长线价值投资分析

当用户请求**个股分析、投资建议、公司估值、全面分析、系统分析**时按此 SKILL 执行。数据采集按需调用 a-stock-data 的函数。

---

## 前置检查：风控中止

**P0（必须询问用户）：** ST/*ST/退市 / 财报非标意见 / 实控人被调查。
**P1（标记高风险）：** 重大未决诉讼/资产冻结 / 业绩预告亏损>50%。

---

## 前置判断 1：时间维度

**长线(>6月)：** 重 Step 2，Step 3 仅输出 A+C。**中线(1-6月)：** Step 2+3 并重（默认）。
**短线(<1月)：** 只走 Step 1→Step 3，跳过 Step 2。**不确定：** 按中线。

## 前置判断 2：框架判断

```
条件1：≥5年可查财报
条件2：业务可理解/有护城河（含定价权评估）
条件3：非强周期
→ 全满足 = 分支A（巴菲特框架）
→ 任一不满足 = 分支B（相对估值）

条件2细化：
  - 定价权强 → 直接通过
  - 定价权弱但有低成本优势/转换成本/客户锁定 → 仍通过，报告中标注补偿项
  - ODM/代工：普遍定价权弱，若具备规模优势/良率壁垒/垂直整合/长期绑定 → 仍视为有条件2
  - 护城河全无 → 条件2不满足，走分支B

板块类型识别：688开头→科创板，PE容忍度上调30%（上限70x）；8开头→北交所，需说明流动性风险。
板块相对估值：科创板/创业板公司，对比板块中位数PE。

适用性提示：半导体/软件/AI/生物科技等高速迭代行业，巴菲特框架适用性有限。
```

### 路线定义

| 时间 | 分支A | 分支B |
|------|-------|-------|
| 长线 | 完整路径+持有结论 | 行业估值水位替代持有锚 |
| 中线 | 完整路径 | 完整路径 |
| 短线 | 跳过 Step 2 | 跳过 Step 2 |

---

## ⏱ 巴菲特 8 问快速过滤器（预筛+验证）

### 步骤 A — 预筛（Step 1 之前，用已知知识回答）

Read: `references/buffett/01-thinking-frameworks.summary.md`
AND: `references/buffett/02-investment-philosophy.summary.md`
（若 summary 不足以支撑判断，回退全量文件）

```
1. 能力圈：能一句话说清怎么赚钱？
2. 持久性：10年后还在且更强？
3. 护城河：有复制门槛？
7. 管理层诚信：直面问题还是隐藏？（一票否决）
```

**Q7为No则一票否决跳过**。其他按以下规则判定路径：
- **0-1个No** → 自动通过，走分支A（巴菲特框架）
- **2-3个No** → 需强理由才能通过，仍需强理由则走分支B
- **4个No** → 走分支B（相对估值模式），不放弃分析但声明低置信度

通过（分支A）→ 进入 Step 1。

### 步骤 B — 验证（Step 1 数据采集完成后，数据摘要之前）

**短线路径下跳过此步骤。**

```
4. 定价权：毛利率 vs 同行（>同行+10%=强 / ±10%=中 / <同行-10%=弱）
   同时检查毛利率3年趋势（上升/稳定/下降）
5. 盈利质量：经营现金流 vs 净利润（现金转化率）
5a. 非经常性损益检查：扣非净利润 / 净利润 < 0.7 → "非经常性损益占比过高"
   数据源：mootdx finance() 的 kcfjcxsy 字段，或新浪财报
   若 < 0.7 → Q5即使通过也标记 ⚠️ 盈利质量警告
5b. 价值陷阱检查：#1，调用 `value_trap_check(rg_3y, gm_3y, dr, pe, ocf_ratio)`
   输出 score(0-10)，score>=6 → 高风险价值陷阱，报告顶部 ⚠️
6. 债务安全：资产负债率/有息负债率
8. 合理价格：PE/PB历史分位 + 内在价值区间
```

若验证与预筛矛盾，标记"预筛矛盾"。最终No计数决定是否继续。
⚠️ 若≥2个No通过：所有结论前标注"低置信度"，持有结论增加"不确定性高"前缀。

---

## Step 1：数据采集（三级通道，串行）

**调用顺序**：通道A（a-stock-data，强制）→ 通道W（wiki，强制）→ 通道S（联网搜索，条件触发）

### 通道 A — a-stock-data 实时数据

| 数据项 | 关键性 | a-stock-data 函数 | fallback |
|-------|-------|------------------|---------|
| 近60根K线+MA5/10/20 | 致命 | `baidu_kline_with_ma(code)` | mootdx bars() + 自算MA |
| PE/PB/市值/换手率 | 致命 | `tencent_quote([code])` | 无 |
| BVPS | 重要 | `mootdx finance()[meigujingzichan]` | 市值/总股本 |
| ROE/毛利率/营收/OCF/负债率 | 重要 | mootdx finance() + 新浪三表 | web_fetch 200字摘要 |
| 扣非净利润 | Q5a需要 | mootdx finance() 的 kcfjcxsy 字段 / 新浪三表 | 标注不可用 |
| 资金流向(分钟+120日日级) | 重要 | `eastmoney_fund_flow_minute()` + `stock_fund_flow_120d()` | 跳过 |
| 大盘指数5日走势 | 重要 | `tencent_quote([000001,399001,399006])` | 无 |
| 美股三大指数 | 重要 | `tencent_quote(["gb_dji","gb_ixic","gb_inx"])` 通过 `qt.gtimg.cn/q=gb_dji,gb_ixic,gb_inx` 获取, 字段索引与A股相同（如索引3=最新价, 索引30=PE等）。当A股指数不可用时也可用港股ETF替代。 | 无 |
| 概念板块归属 | 重要 | `eastmoney_concept_blocks(code)` | 东财不可用时→fallback A: `web_fetch("同花顺 " + name + " 概念板块")` 取摘要
东财+web均不可用→fallback B: `memory_search(code + " 板块概念")` wiki已有 |
| 个股新闻 | 补充 | 东财 search-api | `web_fetch(name + " 最新消息 日期")` 取摘要200字 |
| 研报列表+EPS预测 | 补充 | `eastmoney_reports(code)` / `ths_eps_forecast()` | 标注不可用 |
| 同行PE/PB/市值 | Step2需要时 | `tencent_quote([同行])` | `scripts.peer_engine` 中 `get_industry_peers(code)` 自动返回同行列表 |

**Owner Earnings 预计算**：调用 `scripts` 包的 `build_summary()` 完成（位于 `scripts/preprocess.py`），不进 LLM 上下文。

### 通道 W — Wiki 知识库（强制）

`memory_search("公司名 基本面 估值")` + `memory_search("股票代码 分析")` → **必须执行不得跳过**。无匹配也须在报告中标记。

### 通道 S — 联网搜索（条件触发，满足任一即可）

- ROE 连续3年下降 >5% / 毛利率连续3年下降 >3%
- 突发政策/监管变动（A通道新闻不可用时）
- 用户明确要求"搜一下最近的..."

**执行**：`web_fetch("公司名 + 关键词")` 取标题+摘要前200字。

### 东财不可用时的数据降级规则

当东财接口（push2/slist/clist/search-api）因IP限流/风控返回空数据或连接断开时，不中断分析流程，按以下降级：

| 数据项 | 降级操作 |
|--------|---------|
| 资金流向(分钟+120日) | 跳过，标注"东财受限，资金面无数据" |
| 涨跌家数 | 跳过 |
| 行业排行(TOP/BOTTOM5) | 跳过 |
| 概念板块归属 | → fallback A: `web_fetch("同花顺 " + name + " 概念板块")` 200字摘要
→ fallback B: `memory_search(code + " 板块概念")` |
| 全球快讯 | 跳过 |
| 个股新闻 | → `web_fetch(name + " 最新公告 消息")` 200字摘要 |

**报告要求**：所有跳过的项必须在「数据来源」段落列出缺失项清单。

**联网搜索 fallback 执行模板**：
```
概念板块: web_fetch("同花顺 " + name + " 概念板块", maxChars=1500)
          提取页面中的板块标签（通常为逗号分隔的关键词列表）
个股新闻: web_fetch(name + " 最新动态 消息", maxChars=1500)
          取标题+摘要前200字
```

### 数据整合评估

```
致命项完整 + 重要项不过半缺失 → OK
致命项缺失 → 中止
重要项过半缺失 → 置信度降级
```

---

## 📐 数据摘要（Step 1.5）

调用 `scripts` 包的 `build_summary()` 函数（位于 `scripts/preprocess.py`），传入 Step 1 采集的原始数据，获取结构化 ss 字典直接供 Step 2 使用。

预处理包括：PE/PB 历史序列计算、同行PE outlier过滤、现金转化率分析、Owner Earnings 均值估算。

**PE历史序列计算**：`compute_pe_history(closes, ttm_eps, eps_history=None)`
- 默认用当前 TTM EPS 反代全部历史（有偏倚），估值分位偏低
- **若通过财报数据获取了过去 3 年的 EPS 序列**，传入 `eps_history` 参数即可得到逐期精确 PE 历史，消除偏倚
- 数据源：mootdx finance() 每季度 EPS 或新浪三表每股收益

ss 结构定义见 `scripts` 包的 `SS_SCHEMA` / `new_ss()`。

### ss 字段引用表（LLM 分析流中统一使用）

```
ss.p      → 当前价
ss.ma5/10/20/60 → 均线价（MA60新增，中长期趋势参考）
ss.pe/pb  → PE TTM / PB
ss.pe_h/pb_h → PE/PB 历史序列
ss.mc     → 总市值(亿)
ss.turn   → 换手率(%)
ss.bvps   → 每股净资产
ss.roe    → 近3年ROE列表
ss.gm     → 近3年毛利率列表
ss.dr     → 资产负债率
ss.idr    → 有息负债率
ss.rg/pg  → 营收/利润增速列表
ss.ocf/np → 经营现金流 / 净利润
ss.cash_conv_3y → 多期现金转化率趋势（#2新增强制使用）
ss.oe_avg/oe_pr → Owner Earnings均值/[保守,乐观]价
ss.kl10   → 近10根K线 [(cl,hi,lo), ...]
ss.volatility_60d → 60日年化波动率(%)
ss.cblk   → 概念板块列表
ss.ind    → 行业名
ss.ix_sh/sz/cyb → 三大指数
ss.f_yd/f_20d → 资金流向(当日/20日累计)
```

所有分析步骤均引用以上字段名，不得自创别名。

---

## Step 2：基本面分析

### 2-A 业务画像（≤3句）

### 2-B 行业对标

大盘从 `ss.ix_*` 读取。同行调用 `scripts.peer_engine` 的 `get_industry_peers(code)` 自动获取同行代码列表，再调用 `tencent_quote(peer_codes)` 获取 PE/PB/市值。
使用 `scripts.peer_engine` 的 `compute_industry_median_pe()` 计算中位数。

**调用流程**：
```
1. peer_codes = get_industry_peers(code)  # 本地映射，零外部依赖
2. peer_quotes = tencent_quote(peer_codes)  # 腾讯API，不封IP
3. 同行PE中位数 = compute_industry_median_pe(peer_quotes.values())
```

**同行存在 PE>100 outlier**：自动剔除，取剩余中位数。均不可比时 fallback 行业板块 PE 均值。

**同行对比扩展**：毛利率、现金转化率、有息负债率（从 Step1 已取数据中提取）。

### 2-C 财务健康

从 ss 字段引用表直接读取：
```
ss.roe → 近3年ROE，趋势判断 [+]稳定[-]下降
ss.dr  → 资产负债率（> 50% 需注意杠杆质量）
ss.idr → 有息负债率（> 30% 财务杠杆风险）
ss.ocf / ss.np → 现金转化率（> 0.8 合格）
ss.cash_conv_3y → 多期现金转化率趋势（#2，优先于单期）
ss.rg / ss.pg → 营收/利润增速趋势
ss.gm  → 毛利率趋势，判断护城河稳定性
```

**多期盈利质量**（#2）：使用 `ss.cash_conv_3y` 看 3 年趋势，而非单期：
- 3 年均在 0.8-1.2 → 稳定
- 逐年下降 → 恶化（即使最近一期仍>0.8）
- 逐年上升 → 改善

**价值陷阱检查**（#1）：读取 `ss.value_trap_score` 和 `ss.value_trap_warnings`，score>=6 时报告顶部标注 ⚠️

**ROE 质量分解（杜邦拆分）**：调用 `roe_quality(ss.dr, ss.roe[-1], net_profit_margin)`
- 区分"高杠杆驱动"的 ROE 与"高利润率驱动"的 ROE
- 结果在报告中标注：`ROE质量: [标签]（[风险等级]）— [详情]`
- 若风险为"高"或"极高"，在 Q6 债务安全检查中额外标记

---

### 分支 A — 巴菲特框架

**2-D 前读**：`references/buffett/03-business-moat.summary.md` → 5种护城河分类 + 趋势判断
（若 summary 不足，回退 `03-business-moat.md` 全量）
**市场格局评分**：全球份额>60%或竞争对手<3家=主导(护城河上调一级) / 30-60%=领先 / <10%=碎片化
**2-D 后读**：`references/buffett/04-management-governance.summary.md` → 三维管理评估
（若 summary 不足，回退全量文件）

**竞争格局对比**：调用 `build_competition_matrix(target_code, peer_codes, target_data, peers_data)` 输出 7 维对比表（PE/PB/ROE/毛利率/营收增速/负债率/市值），替代 LLM 模糊记忆的竞争格局评估。

**护城河趋势量化**：调用 `infer_moat_trend(gm_3y, roe_3y)` 从毛利率和 ROE 趋势自动推断护城河方向，
输出 [增强/稳定/削弱/数据不足]。LLM 在此基础上做定性调整。

**行业专有风险过滤器**（#3，必做）：
根据 `ss.ind` 行业自动检查 2 个特有风险（LLM 从已知知识检索）：
- 消费电子/代工：客户集中度（前3大客户占比？）、供应链转移风险
- 半导体：技术迭代风险（制程差距）、出口管制风险
- 银行/保险：不良率趋势、净息差变化
- 医药/器械：集采风险、专利悬崖
- 公用事业：电价政策、资本开支压力
- 白酒/食品：库存周期、消费趋势变化
- 新能源/汽车：产能过剩、补贴退坡
- AI/算力：技术路线不确定性、资本开支回报期

输出格式：`行业特有风险: [风险1, 风险2]`

**行业因子加权矩阵**：调用 `get_factor_weights(ss.ind)` 获取行业特有因子权重配置（P1-1）。
各行业配置 4-5 个关键因子（如毛利率趋势、库存周期、资金流等），合计权重=1.0。
未覆盖行业使用通用兜底权重（均线0.25 / 资金流0.2 / 量价0.2 / 事件0.2 / 美股0.15）。

对比表格式：
```
维度        标的    同行中位    Q1    Q3    排位     评级
PE(TTM)     31.9   25.0       20    35     1/5    领先
ROE(%)      18.5   15.0       12    20     3/5    中游
毛利率(%)   32.0   28.0       25    34     2/5    领先
...
```

**客户集中度与地缘风险**：前3大客户收入占比>50%→高度集中；主要客户在海外→地缘风险。

**知名投资机构持仓检查**（持有时间>5年则标记"信任何极高"）

**管理层/大股东评估**（必做）：
1. 管理层诚信 — [是/否]
2. 大股东信用风险 — [低/中/高]
3. 股权质押比例 > 50% → 标记风险
4. **资本配置质量**（新增）：
   - 回购记录：近3年总股本变化？[减少/不变/增加] — 低位回购为好信号
   - 分红质量：分红率趋势？[稳定增长/不稳定/不分红] — 可持续分红为好信号
   - 收购质量：商誉/净资产比 > 30% → 标记"收购溢价过高风险"
5. 护城河趋势（量化）：从 `infer_moat_trend(gm_3y, roe_3y)` 读取 → [增强/稳定/削弱/数据不足]

**杠杆质量分析**：
- 负债率>50%但有息负债率<10% → 供应链议价能力，非财务风险
- 负债率>50%且有息负债率>30% → 财务杠杆风险

**压力测试**（营收下降50%）：
- 有息负债率<20% 且 现金/短期债务>2 → 大概率能活
- 有息负债率>50% 且 现金/短期债务<1 → 风险高

### 行业估值修正模块（2-E前置）

**适用条件**：PE > 35 且行业属于半导体/芯片/AI/创新药/新能源等赛道。不满足则走下方传统估值。

**三步串行**：

① **PEG计算**：近3年净利润CAGR，PEG=PE/CAGR（CAGR以整数计，如50%则代入50）
  <1.0低估 / 1.0~2.0合理 / 2.0~3.0偏高 / >3.0高估

② **板块内部比较**：个股PE/板块中位PE = 相对溢价倍数
  <1.5合理 / 1.5~2.0偏贵 / >2.0严重溢价

③ **产业链容忍上限（动态版）**：
  调用 `compute_dynamic_pe_limit(code, block_median_pe)` 自动计算：
  ```
  容忍上限 = 板块同行PE中位数 × 行业系数
  ```
  | 位置 | 系数 |
  |------|------|
  | 上游设备/材料/EDA | 板块中位PE × 1.8 |
  | Fabless设计 | 板块中位PE × 2.0 |
  | IDM/代工制造 | 板块中位PE × 1.5 |
  | 消费电子代工 | 板块中位PE × 1.3 |
  | 消费电子/传统制造 | 板块中位PE × 1.5 |
  | 创新药/Biotech | 亏损可接受(参照PS) |

  **block_median_pe 不可用**（如板块中位数缺失）时回退绝对上限。
  PE > 动态上限 → 标记"超行业容忍上限"

**双轨制裁决（预计算）**：

调用 `compute_valuation_verdict(pe, cagr, block_median_pe, pe_limit, industry)` 一次完成三步计算：
1. PEG = PE / (CAGR×100)，<1.0=低估 / 1.0~2.0=合理 / 2.0~3.0=偏高 / >3.0=高估
2. 板块溢价 = 个股PE / 板块中位PE，<1.5=合理 / 1.5~2.0=偏贵 / >2.0=严重溢价
3. PE > 动态上限 → 超限

返回结构化 dict 包含裁决结果，LLM 直接读取：
```
{"verdict": str, "action": str, "detail": str, "peg": float, "peg_label": str, ...}
```

### 2-E 内在价值

*E1 — Owner Earnings*：
- 从 ss.oe_avg 和 ss.oe_pr 读取（已预计算）
- OE 倍数不再硬编码 15x/20x，改为 `get_oe_multiple(industry)` 基于股权资本成本动态计算
- 股权资本成本 = 无风险利率(rf) + 行业β × ERP(6.5%)
- 各行业 β 系数：银行 0.7、白酒 0.8、公用事业 0.6、消费电子 1.1、半导体 1.4、AI算力 1.5 等
- LLM 判断护城河强度后可在倍数基础上 ±2x 调整

**OE 不可用时** → DDM替代：
- 无风险利率：调用 `get_rf_rate()` 实时获取（fallback 2.0%）
- DDM保守(g=0%)：近3年平均股息 ÷ 股权资本成本(coe)
- DDM增长(g≈2%)：平均股息 ÷ (coe - 2%)
- coe = get_cost_of_equity(industry) 包含行业 β 风险溢价

**通胀调整**（#6，必做）：
- 调用 `get_inflation_rate()` 获取 CPI（fallback 2.0%）
- 输出 DDM 双版本：
  - DDM名义：g_nominal ≈ 2%（当前逻辑）
  - DDM实际：g_real = history_median(rg_3y) - inflation（更保守）
- 通胀 > 3% 时在报告顶部标注 ⚠️ 高通胀环境

**利率敏感性**（公用事业/高分红必做）：
DDM(rf) / DDM(rf+0.5%) = +50bp / DDM(rf-0.5%) = -50bp

**OE 参数 — 轻资产自动识别**：
`build_summary()` 中 `is_light_asset` 参数由 `auto_is_light_asset(industry)` 自动推断，
覆盖行业：半导体设计、云计算软件、创新药、互联网、白酒、AI算力等
无需手动传入，避免同一标的在不同分析中的 `maint_capex` 系数冲突

*E2 — PE估值*：中枢=median(ss.pe_h)，数据不足则行业均值±20%。

**前向PE**（带基数效应防护）：

调用 `compute_forward_pe(market_cap, quarterly_net_profits: [Q1, Q2, Q3, Q4])`，返回 dict 格式：
```python
{"pe": float, "valid": bool, "reason": str}
```
**触发条件**：
1. 最近 4 个季度净利润全部为正（防止亏损期→微利期的同比虚高基数效应）
2. 所有季度净利润数据可获得

若 `valid=False`，原因标注的具体季度号，不计算前向PE。
若 `valid=True`：
- 前向PE < TTM×0.7 → "盈利快速增长，TTM滞后"
- 前向PE > TTM PE → "季度走弱，以TTM为主"

*E3 — PB估值*（重资产必做）：median(ss.pb_h) vs 当前PB。

*E4 — 综合区间*：三条路径取交集。

**情景分析**（#7，补充输出）：
调用 `scenario_analysis(oe_base, rg_3y, gm_3y, industry)` 输出三情景估值区间：
```
悲观: OE×0.8 × 倍数×0.85 = xx元
基准: OE×1.0 × 倍数×1.0  = xx元
乐观: OE×1.15 × 倍数×1.10 = xx元
均值: xx ~ xx元（跨度: xx%）
```

**安全边际判定（连续评分）**：

调用 `margin_of_safety_continuous(current_price, intrinsic_median, conviction_high)` 输出连续分数：
```
{"score": 0-100, "margin_premium": float, "label": str, "action": str, "position": dict}
```

| score区间 | 标签 | 操作 |
|-----------|------|------|
| 0-20 | 严重高估 | 卖出 |
| 20-40 | 偏高 | 观望/减仓 |
| 40-60 | 合理 | 持有 |
| 60-80 | 偏低 | 可买入 |
| 80-90 | 低估 | 买入 |
| 90-100 | 显著低估 | 强烈买入 |

高置信度（Q5通过+管理层可信）时 score +10。

若MAX(PE,PB,DDM)/MIN(PE,PB,DDM) > 1.2 → 标记"估值方法分歧>20%"。

**2-F 前读**：`references/buffett/06-valuation-capital.summary.md` → 安全边际分级
（若 summary 不足，回退全量文件）

**2-F 持有结论**：买入/持有/卖出 + 推荐买入价 + EPS一致预期，含再评估触发器。

**盈利质量覆盖规则**：

**再评估触发器**（#4，必出）：
从 `ss.re_eval_triggers` 读取输出，格式：
```
再评估触发器（以下任一触及请重新分析）：
1. 毛利率跌破 {X}% — {理由}
2. 资产负债率超过 {X}% — {理由}
3. PE 高于 {X}x 或低于 {X}x — {理由}
4. PE 回到历史中位 — {理由}
```
- Q5=✅且Q8=❌ → "好公司不便宜"，上调安全边际至15%
- Q5=❌且Q8=✅ → "便宜没好货"，不建议买入
- Q5=No且Q8=Yes → 利润质量差覆盖估值优势

**卖出条件逐项检查**（参考 references/buffett/07-risk-behavior.summary.md，配合量化规则）：

调用 `sell_condition_check(code, pe_current, pe_limit, peg, roe, gm_trend, ocf_vs_np, dr)`
返回结构化检查结果，不再依靠 LLM 纯定性判断。

| # | 条件 | 量化规则 |
|---|------|---------|
| 1 | 价格严重高估 | PE > 动态上限×1.2 且 PEG > 3.0 |
| 2 | 护城河被破坏 | 毛利率连续3年下降>5% 且 ROE<8%（连续2年） |
| 3 | 管理层诚信 | 一票否决（LLM判断，保持） |
| 4 | 盈利质量恶化 | OCF/NP < 0（连续2年经营现金流为负） |

检查结果中 `any_sell=True` 时，报告顶部标注 ⚠️ 卖出信号。

---

### 分支 B — 相对估值模式

**2-B**: 同行对比（PE/PB）。**2-C**: PE/PB当前分位（`estimate_percentile()`）。催化剂清单（上涨+下行）。

**持有结论**：低分位<30%可买入 / 高分位>70%可卖出 / 中位→观望。

**输出统一**：即使走分支 B，也需包含标准化估值区间和置信度，与分支 A 可比：
```
估值区间：{PE分位对应区间} ~ {PB分位对应区间} 元
置信度：{高/中/低}（非巴菲特框架，数据驱动）
```

---

## Step 3：技术面分析（产出结构化信号）

Step 3 产出 `tech_signal` 值（-1~1），供 Step 4 与基本面信号融合。

调用 `scripts.technical` 的 `compute_enhanced_tech_score()` 综合评分，
替代原来的 5 因子手动计算。该函数包含 9 因子评分系统：

| 因子 | 权重 | 说明 |
|------|------|------|
| 均线系统 | ±0.30 | 多头/空头排列判断 |
| 量价关系 | ±0.20 | 放量上涨/下跌 |
| K线形态 | ±0.15 | 大阳/大阴线 |
| 趋势幅度 | ±0.15 | 近5日涨跌幅 |
| 资金面 | ±0.15 | 主力净流入/流出 |
| MACD方向 | ±0.15 | 金叉/死叉/零轴 |
| 量价背离 | ±0.15 | 顶背离/底背离 |
| 周线趋势 | ±0.15 | 周线MA排列确认 |
| 筹码支撑 | ±0.15 | 成交量密集区支撑/阻力 |

**调用方式**：
```
from scripts.technical import compute_enhanced_tech_score

result = compute_enhanced_tech_score(
    closes=ss.kl10_closes, highs=..., lows=..., volumes=...,
    ma5=ss.ma5, ma10=ss.ma10, ma20=ss.ma20, ma60=ss.ma60,
    current_price=ss.p, vol_ratio=...,
    fund_flow_ok=ss.f_ok, fund_flow_today=ss.f_yd,
)
tech_score = result["score"]
```

函数返回结构化 dict 包含 score、details（各因子分值）、signals（文本信号列表，
如"多头排列" "放量上涨" "MACD金叉"）、macd 细项、weekly_trend、
volume_profile 和 divergences。

输出：`"技术面分数: {tech_score:.2f} ({signals描述})"`

所有函数纯 Python 实现，无 numpy/pandas 依赖。


---

## Step 4：输出报告

### A. 报告结构

```
预筛结论：{#个No} — {自动通过/需强理由/跳过}
验证结论：{#个No}/{#个⚠️} — {一致/预筛矛盾}
{#个No}<2→自动通过 / ≥2→需强理由 / ≥4→跳过
安全边际：{有/无}

板块一：基本面（Step 2精华）
  分支A：护城河 + 安全边际 + 持有结论
  分支B：相对估值分位 + 催化剂清单
板块二：技术面
```

### B. 决策模块

默认按"未持仓"输出。分支A：低估→买入/合理→观望/高估→卖出（配≤3观察变量）。分支B：相对分位XX%→持有/减仓/观望。

**安全边际根据持有期调整**：`margin_of_safety_continuous(price, intrinsic, conviction, holding_months)`
- holding_months >= 12 → 系数1.0（标准）
- holding_months >= 6 → 系数1.2（中线更严格）
- holding_months >= 3 → 系数1.4
- < 3 → 系数1.5（短线最严格）

**综合信号**（非短线路径必出）：

调用 `generate_signal(step2_verdict, tech_score, time_horizon)` 输出：
```
综合判定: {verdict} (置信度: {conviction})
基本面=xx分(权重xx) + 技术面=xx分(权重xx)
{⚠️ 冲突标记}
推荐仓位: {position.label} ({position.pct*100}%)
```

**冲突处理规则**：
- 基本面买入(>=+0.5) 且 技术面偏空(<=-0.5) → 标记冲突，在结论前加 ⚠️，降低置信度输出
- 基本面卖出(<=-0.5) 且 技术面偏多(>=+0.5) → 同上
- 无冲突 → 正常输出

**仓位建议**：
调用 `position_sizing(margin_premium, conviction_high)` 输出：
| 安全边际 | 仓位 |
|---------|------|
| 折价>30%且高置信度 | 80%（重仓） |
| 折价>20% | 50%（半仓） |
| 折价>10% | 30%（轻仓） |
| 溢价>30% | 清仓 |
| 其他 | 观望/不持有 |

### B2. 监控指标（必出）

```
每季度检查：ROE趋势、毛利率变化、OCF方向、客户集中度变化
触发重新评估：OCF连续2季为负 / H股发行价低于60元 / 苹果供应链转移实质性落地
```

### C. 分析时效性（必出）

报告头部强制包含：
```
分析日期: {YYYY-MM-DD}
数据截止: {YYYY-MM-DD}（收盘）
有效期限: {结论在下一次财报发布前有效 / 需要关注政策变化 / 重大事件后需重评}
```

### D. 市场环境调节

Step 4-B 安全边际判定后，按以下规则修正：
- LLM 简要判断当前市场情绪：`亢奋/正常/恐慌/震荡`
- 调用 `macro_regime_adjustment(rf_trend, market_sentiment)` 获取宏观叠加修正系数
- 该函数自动获取 10Y 国债收益率趋势（`get_rf_trend()`），并叠加市场情绪做出综合判断
- 修正后安全边际 = 原始安全边际 + correction

**修正规则**：
| rf_trend | 市场情绪 | correction | 含义 |
|----------|---------|------------|------|
| 上升 | 亢奋 | +0.10 | 非常严格，利率上行+市场亢奋 |
| 上升 | 正常 | +0.05 | 利率上行，收紧安全边际 |
| 下降 | 恐慌/震荡 | -0.05 | 利率下行+市场悲观，放宽安全边际 |
| 其他 | — | base.correction | 跟随 market_regime_adjustment() |

向下兼容：`market_regime_adjustment(sentiment)` 单参数接口仍可用。

### E. 报告声明
联网数据注明"需核实"；P0风险且继续→顶部⚠️；统一声明。

### F. 关键假设清单（必出，含风险评级）

每条假设标注风险评级，标记对结论影响最大的前 2 条：
```
关键假设（结论成立的前置条件）：
1. [风险:低/中/高] 竞争格局不变 — {若被颠覆则结论失效，影响大但概率低}
2. [风险:低/中/高] 管理层稳定 — {管理层变动可能性及影响}
3. [风险:低/中/高] 政策/监管环境稳定 — {行业政策敏感性}
4. [风险:低/中/高] 利率环境稳定 — {对估值的敏感性}
5. [风险:低/中/高] 客户关系稳定 — {客户集中度风险}

⚠️ 最关键的假设：{前2条风险最高的假设}
```

---

## 后验复盘

### 月度检查（HEARTBEAT 自动触发）

HEARTBEAT.md 中注册每月复盘：
```
每月1日 09:00 执行复盘：读取 wiki/wiki/prediction-review.md 中的预测记录，
调用 preprocess.py 的 review_accuracy() 计算胜率，
结果追加到 wiki/wiki/prediction-review.md
```

### 手动触发

用户说"复盘"时：
1. 从 wiki 找分析记录 → memory_search(股票名) + wiki回顾
2. 调用 `review_accuracy(predictions, actuals)` 计算方向准确率
3. 偏差归因（按行业/市场风格/时间分类）
4. 记入 `wiki/wiki/prediction-review.md`

### 输出格式

```
后验复盘报告 ({时间范围})
总计: {N}次预测, 正确: {M}次, 胜率: {X}%

分类胜率:
  买入: {x}% ({a}/{b})
  持有/观望: {x}% ({a}/{b})
  卖出: {x}% ({a}/{b})

行业归因:
  消费电子: {x}% ({a}/{b})
  电力设备: {x}% ({a}/{b})
  ...

系统偏差: 如果有系统性高估/低估，输出偏差方向
```

---

## 相关

- [[a-stock-data]] — 数据源
- `scripts` 包（`preprocess.py` / `peer_engine.py` / `valuation.py` / `cash_quality.py` / `risk.py` / `position.py` / `cache.py` / `technical.py` / `portfolio.py` / `backtest.py` / `valuation_ensemble.py` / `sentiment.py` / `event_calendar.py` / `factor_analysis.py` / `batch.py` / `performance.py` / `data_layer.py`）— 数据预处理与缓存模块（PE/PB历史、OE预计算、同行过滤、因子权重、安全边际、仓位建议、缓存系统、技术面增强评分、组合检查、回测框架、多路径估值集成、情绪信号、公司行动日历、因子归因分析、批量并行分析、持仓绩效归因、统一数据接入层）
- [[references]] — 内置的巴菲特/芒格等投资大师思维框架
- [[karpathy-llm-wiki]] — 本地知识库（通道W+复盘存储）
- `scripts/cache.py` — 数据缓存系统（K线2h / 财务24h / 同行7d / 新闻1h / 市场1h，cache 目录自动创建）

### v2.4.0 新增功能

**持仓绩效归因**：`scripts.performance.attribution_analysis(holdings_snapshot)` — 简化 Brinson 模型，将组合超额收益拆分为选股贡献、行业配置贡献和择时贡献。`summary_attribution(result)` 输出一句话摘要。`compare_periods(period_results)` 多期对比 + Alpha波动率 + 信息比率。纯参数驱动，不依赖外部数据。

**数据接入统一层**：`scripts.data_layer` — 统一数据获取入口，替代散落在各处的 inline API 调用。
- `get_quote(codes)` — 双通道行情（腾讯优先→新浪回退），返回结构化行情数据
- `get_kline(code, count)` — K线查询（百度优先→腾讯回退），带MA5/10/20
- `get_index_quote()` / `get_us_markets()` / `get_hk_market()` — 市场指数
- `get_fund_flow()` / `get_north_flow()` — 资金流向
- `get_industry_peers()` — 复用 peer_engine 同行识别 + tencent_quote 获取同行行情
- `_cache_wrap()` — 集成 cache.py 缓存的装饰函数

数据采集时也可以使用 `scripts.data_layer` 的 `get_quote()`/`get_kline()` 等函数替代 inline 代码，尤其是简单的行情查询场景。

### v2.3.0 新增功能

**Deflated Sharpe Ratio（多重测试校正）**：`scripts.backtest.deflated_sharpe_ratio()` — 基于 Mertens 2002 近似的多重测试校正夏普比率，含 E[max(Z)] 校正项和偏度/峰度方差调整，`compute_dsr_from_returns()` 从收益序列直接计算。DSR>2.0 标记 95% 置信非随机。

**Monte Carlo 估值模拟**：`scripts.valuation_ensemble.monte_carlo_valuation()` — 10000次 DCF+终值模拟，对增长率/折现率/OE倍数做正态分布采样，输出均值/中位数/众数/偏度/百分位数/直方图。`mc_compare_to_market()` 与市价对比，输出分位和低估概率。

**因子暴露回环**：`scripts.portfolio.risk_budget_usage(code, signal, factor_exposure, group_signals)` — 检查高β(>1.3)/高R²(>0.8)/独特α(R²<0.3且α>0.01)/信号一致性/因子分组去重，输出仓位调整系数和调整后裁决。

**大类资产联动信号**：`scripts.risk.CROSS_ASSET_SENSITIVITY` — 15行业×外部资产敏感性矩阵。`scripts.risk.cross_asset_risk_premium(code, industry)` — 通过腾讯/新浪API获取外部资产趋势，加权计算外生风险溢价(-1~1)，含1h缓存。API失败不中断，标注"数据不可用"。

**最坏情景分析**：`scripts.portfolio.worst_case_analysis(current_price, stop_loss, position_size_pct)` — 风控报表核心，输出止损金额/VaR/恢复所需收益率/风险评级/行动建议。`batch_worst_case(holdings)` 批量分析+合并风险标记。

**因子归因分析**：`scripts.factor_analysis` — 简化 Barra 模型，手动最小二乘法计算 α/β/R²，支持 `calculate_alpha_beta(stock_returns, market_returns)` 和 `factor_exposure_report(code)`

**换仓成本模型**：`scripts.portfolio.estimate_slippage(trade_amount, daily_volume)` — 按市值分档估算买卖价差+冲击成本，建议分N天建仓

**Walk-forward 验证**：`scripts.backtest.walk_forward_backtest(code, folds=4)` — 多段交叉验证，输出 OOS/IS Sharpe 比率和稳定性评级

**行业景气轮动**：`scripts.risk.sector_cycle_advice(industry, rf_trend)` — 基于四象限经济周期（增长/通胀）给出行业配置建议和安全边际修正

**财务异常检测**：`scripts.cash_quality.financial_anomaly_detection()` — 6类财务异常规则（应收、OCF、毛利率、减值、商誉、营收质量），参数可选

**公司行动日历**：`scripts.event_calendar.next_events(code, name)` — 基于固定规则+历史分红推断未来30天事件（季报截止日、除权除息），置信度标注

**选股因子结构化**：`scripts.valuation.FACTOR_DEF_REGISTRY` — 7因子注册中心（价值/盈利/成长/质量/动量/情绪/安全），`compute_factor_scores(ss)` 返回归一化[-1,1]评分，`factor_radar(summaries)` 输出雷达图数据结构

**批量并行**：`scripts.batch.batch_analyze(codes, names)` — 多线程并行分析（默认4线程），返回合并的摘要+技术评分+组合检查
