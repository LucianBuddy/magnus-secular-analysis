# magnus-secular-analysis
magnus-secular-analysis is a long-term value investing analysis skill for A-shares, grounded in the Warren Buffett investment framework. It is triggered when users request fundamental analysis, investment recommendations, or company valuation.

Key features:


Buffett 8-question quick filter — a two-stage screening process. Stage A (pre-screening, before data collection): evaluates circle of competence, 10-year durability, moat existence, and management integrity using existing knowledge. Stage B (validation, after data collection): verifies pricing power (gross margin vs peers + 3-year trend), earnings quality (cash conversion rate), debt safety (coverage ratio + interest-bearing debt), and price reasonableness (PE/PB historical percentile + intrinsic value range). Rules: 2 "No" answers require strong justification to proceed; 4 "No" answers trigger an automatic pass/skip.


Three-tier data sourcing — primary: a-stock-data SDK (Tencent quotes, Baidu candlesticks, Sina financial statements, East Money fund flows, MooTDX financial snapshots); secondary: wiki knowledge base for past analysis records and prediction reviews (mandatory); tertiary: web search triggered by specific conditions (ROE decline >5%, gross margin decline >3%, sudden policy changes).


Dual framework routing — Branch A (Buffett framework) for companies with ≥5 years of auditable financials, understandable business, and non-cyclical industry. Branch B (relative valuation) for companies failing any criterion. Branch A includes moat assessment (5 types + market structure scoring), intrinsic value estimation via PE/PB/DDM three-method convergence, and margin of safety calculation.


Pre-computed data summary — raw API data is processed in Python before entering the LLM context. Only a compact 35-field stock_summary structure is passed through, containing: candlestick data (60-day MA5/10/20), PE/PB history sequences, financial metrics (ROE 3yr/gross margin 3yr/debt ratio/OCF/cash conversion), owner earnings estimates, and EPS consensus. Reduces token consumption by ~70% compared to passing raw data.


Multi-method intrinsic value estimation — E1: Owner Earnings (with Fabless/light-asset adjustment); E2: PE valuation (with growth vs value PE regime classification and forward PE for rapidly growing companies); E3: PB valuation (mandatory for heavy-asset/financial companies); E4: convergence interval of all three methods with discrepancy detection (>20% divergence flagged). DDM alternative for high-dividend stocks with interest rate sensitivity analysis (±50bp).


Comprehensive margin of safety tiers — >30% premium → severely overvalued (automatic sell); 10-30% premium → overvalued (watch); 10-20% discount → reasonably undervalued (consider buy); >20% discount with Q5 passed → significantly undervalued (strong buy).


Sell discipline with item-by-item checks — 5 conditions: price severely overvalued, moat destruction, management integrity issue (automatic veto), better opportunity available, earnings quality deterioration. Uses 3-state evaluation (yes/watch/no) for intermediate scenarios.


Framework extensibility — the /frameworks/ directory houses Buffett's complete 8-file reference library (moat classification, management evaluation, financial metrics, valuation, risk behavior, industry playbooks). Designed for future expansion with Munger, Druckenmiller, or other investor frameworks as independent subdirectories.


Prediction review mechanism — quarterly heartbeat checks compare past analysis outcomes against actual price movements, recording systematic bias into the wiki knowledge base for continuous skill improvement.



Skill size: ~375 lines, includes frameworks/buffett/ (8 reference files). 
