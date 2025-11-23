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
