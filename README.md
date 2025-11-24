-----------------------
STRATEGY IMPLEMENTATION
-----------------------

-----------------------------
Core Idea: Dynamic Alpha-QUBO
-----------------------------

The core of this trading bot is a quantum computing-inspired optimization engine designed to solve the NP-hard problem of portfolio selection under strict risk constraints. 

--------------------------------------------------------------------------------------------------------------
Avantage of Dynamic Alpha-QUBO: the optimum between reward and risk with instrinsic structural diversification
--------------------------------------------------------------------------------------------------------------
* The optimum is the minimized Hamiltonian of the system

Unlike traditional bots that greedily chase high returns, our system explicitly models the trade-off between Alpha (Reward) and Correlation (Risk) as an energy minimization problem.The system operates as a closed-loop control system involving four key modules working in tandem:

----------------------------------------------------
MODULE 1: Market Regime Detection (The "Controller")
----------------------------------------------------

Before any assets are selected, the bot analyzes the current market state using qubo_optimizer.py.
* Input: Historical k-line data fetched via data_fetcher.py.
* Logic: The MarketRegimeDetector calculates market-wide volatility.
* Output: It dynamically determines two critical hyperparameters:
    1. n (Portfolio Size): In high volatility, n increases to force diversification. In low volatility, n decreases to concentrate on high-alpha plays.
    2. lambda (Risk Penalty): In high volatility, the risk penalty is amplified to strictly punish asset correlation.

------------------------------------------------------
MODULE 2: Multi-Factor Alpha Generation (The "Signal")
------------------------------------------------------

Simultaneously, the system generates a composite "Alpha Score" for every eligible asset.
* Input: Price/Volume data (data_fetcher.py) and Sentiment/Trend signals (dashboard.py).
* Process: The calculate_alpha_score method in qubo_optimizer.py aggregates three distinct signals:
    1. Momentum: Short-term vs. long-term return differentials.
    2. Mean Reversion: Deviation from moving averages.
    3. Sentiment/Trend: External predictive analytics derived from the Horus API.
* Output: A normalized score alpha_i for each asset i, representing its potential for short-term appreciation.

------------------------------------------------------------
MODULE 3: The Quantum-Inspired Hamiltonian (The "Optimizer")
------------------------------------------------------------

This is the core innovation. We map the portfolio selection problem to a Quadratic Unconstrained Binary Optimization (QUBO) problem. The AdaptiveQUBOOptimizer class in qubo_optimizer.py constructs a Hamiltonian energy function H:

H = -sum(alpha_i x_i) + lambda*sum(rho_ij x_i x_j) + P(sum(x_i) - n)^2 (for i<j)

H = -Alpha Reward + Risk Penalty + Dynamic Constraint

* Alpha Reward: Minimizing negative energy maximizes the selection of high-alpha assets.
* Risk Penalty: Minimizing positive energy actively avoids selecting assets that are highly correlated rho_ij, preventing the "bull market trap" where a portfolio unwittingly becomes a single directional bet.
* Dynamic Constraint: A penalty term that forces the Simulated Annealer to converge on a portfolio of exactly size n (determined by the regime detector).

The solver (simulated annealing via neal) explores this energy landscape to find the global minimum, representing the mathematically optimal balance of return and structural diversification.

----------------------------------------------
MODULE 4: Execution & Allocation (The "Actor")
----------------------------------------------

Once the optimal basket of assets is identified:
* Weighting: allocator.py takes the binary selection from the QUBO solver and assigns precise portfolio weights (CVaR portfolio optimization optimized for Sortino/Sharpe/Calmar ratios).
* Trading: bot_executor.py calculates the delta between the current portfolio and the target state, executing the necessary BUY and SELL orders via the Roostoo API.
* Logging: Every decision (from the detected regime to the final energy state of the QUBO solver) is recorded in performance_logger.py for post-trade analysis and strategy tuning.

---------------------------------------------------------
MODULE 5: Smart Order Execution Pipeline (The "Executor")
---------------------------------------------------------

The **`bot_executor.py`** module handles the precise mechanics of trade execution, transforming quantum-optimized portfolio allocations into real market orders.
* Input: Target portfolio weights from allocator.py and current portfolio state from Roostoo API.
* Logic: Implements precision order execution with asset-specific quantity rounding and rate limiting.
* Output: Executed market orders with real-time portfolio synchronization.

```python
step_sizes = {
    "BTC": 0.00001,    # 5 decimal places
    "ETH": 0.0001,     # 4 decimal places  
    "SOL": 0.01,       # 2 decimal places
    "XRP": 0.1,        # 1 decimal place
    "ADA": 1.0,        # 0 decimal places
    # ... 17+ assets with precise step sizes
}
```

---------------------------------------------------------
MODULE 6: Anti-Wash Trading Controller (The "Compliance")
---------------------------------------------------------

The **`CompetitionWashController`** class implements a comprehensive rule-based system to prevent wash trading and ensure competition compliance.
* **Input:** Trade requests from rebalancing engine and historical trade data.
* **Logic:** Validates each trade against competition wash trading rules including hold times, profitability, and frequency limits.
* **Output:** Approved/blocked trade decisions with detailed compliance reasoning.

```python
COMPETITION_CONFIG = {
    "MIN_HOLD_HOURS": 1,           # Competition-optimized from 8 hours
    "MIN_NET_PROFIT": 0.001,       # 0.1% minimum profit threshold
    "MAX_DAILY_TRADES_PER_ASSET": 2, # Prevents excessive asset flipping
    "MAX_DAILY_TOTAL_TRADES": 99,   # Overall safety limit
    "MIN_TRADE_VALUE": 50.0,       # $50 minimum trade size
    "COMMISSION_RATE": 0.0001,     # 0.01% commission awareness
    "COOLDOWN_HOURS_AFTER_SELL": 2, # Strategic cooling periods
}
```
-----------------------------------------------------------
MODULE 7: Portfolio Rebalancing Engine (The "Orchestrator")
-----------------------------------------------------------

The **`execute_rebalance`** function implements a sophisticated seven-stage process that transforms quantum-optimized allocations into executable trades.
* **Input:** Target weights from optimizer, current portfolio holdings, and cash balance.
* **Logic:** Seven-stage rebalancing pipeline with anti-wash filtering and cash-aware execution.
* **Output:** Executed trades with comprehensive performance logging and validation.

```python
def execute_rebalance(target_weights, current_portfolio, cash_balance, threshold=0.05):
    # 1. Price Discovery & Portfolio Valuation
    # 2. Weight Delta Calculation  
    # 3. Anti-Wash Filtering
    # 4. SELL Orders Execution (First)
    # 5. Cash Balance Update
    # 6. BUY Orders Execution (Scaled to available cash)
    # 7. Performance Logging & Validation
```

-------------------------------------------------------
MODULE 8: Production Reliability (The "Infrastructure")
-------------------------------------------------------

The execution infrastructure ensures enterprise-grade reliability and competition compliance.
* **Input:** API requests, portfolio data, and market conditions.
* **Logic:** Secure authentication, error handling, and real-time monitoring systems.
* **Output:** Robust trading operations with comprehensive audit trails and fail-safe mechanisms.

**Key Infrastructure Components:**
- **Secure Authentication:** **HMAC-SHA256** signature generation for all API requests
- **Robust Error Handling:** Intelligent retry logic for network failures and rate limits
- **Portfolio Synchronization:** Ensures consistent state between optimization and execution
- **Circuit Breaker Patterns:** Emergency stops for excessive losses or trading anomalies
- **Comprehensive Logging:** Detailed trade execution records for debugging and compliance
- **Competition Timeline Adaptation:** Integrated with main trading loop for time-based strategy adjustments

--------------------------------------------------------
MODULE 9: Trade Execution & Settlement (The "Finalizer")
--------------------------------------------------------

This module handles the final stage of the trading pipeline, ensuring all trades are properly executed and settled.
* **Input:** Approved trade orders from the rebalancing engine and real-time market data.
* **Logic:** Manages order placement, confirmation, and portfolio state synchronization.
* **Output:** Successfully executed trades with updated portfolio positions and cash balances.

**Execution Features:**
- **Order Confirmation:** Validates successful order execution via API responses
- **Portfolio State Management:** Updates holdings and cash balances post-trade
- **Trade Reconciliation:** Ensures executed trades match intended allocations
- **Settlement Monitoring:** Tracks trade completion and fund availability
- **Error Recovery:** Handles partial fills and failed transactions gracefully

This multi-module execution engine ensures **quantum-inspired portfolio optimizations** translate into **compliant, high-performance trades** while maintaining strict adherence to competition regulations and the strategic integrity of the **Dynamic Alpha-QUBO** approach.
