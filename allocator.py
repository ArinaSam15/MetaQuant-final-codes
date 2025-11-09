# allocator.py
import numpy as np
import pandas as pd
import cvxpy as cp
import logging

logger = logging.getLogger(__name__)


def get_target_weights(asset_list, price_data, alpha=0.95, risk_aversion=1.0):
    """CVaR portfolio optimization with input validation"""
    # Input validation
    if not asset_list:
        raise ValueError("asset_list cannot be empty")

    if len(asset_list) == 1:
        return {asset_list[0]: 1.0}

    # Filter to available assets
    available_assets = [asset for asset in asset_list if asset in price_data.columns]
    if len(available_assets) != len(asset_list):
        missing = set(asset_list) - set(available_assets)
        logger.warning(f"Missing data for assets: {missing}")

    if len(available_assets) == 0:
        raise ValueError("No assets with price data available")

    prices = price_data[available_assets].dropna()

    if len(prices) < 10:
        logger.warning("Insufficient data points, using equal weights")
        return {asset: 1.0 / len(available_assets) for asset in available_assets}

    # Compute returns
    returns = prices.pct_change().dropna()
    n = len(available_assets)
    T = returns.shape[0]

    # Expected returns
    mu = returns.mean().values

    # CVaR optimization
    w = cp.Variable(n)
    z = cp.Variable(T)
    VaR = cp.Variable()

    portfolio_returns = returns.values @ w
    losses = -portfolio_returns

    constraints = [
        cp.sum(w) == 1,
        w >= 0.02,  # Minimum 2% allocation
        w <= 0.4,  # Maximum 40% allocation
        z >= 0,
        z >= losses - VaR,
    ]

    CVaR = VaR + (1 / (1 - alpha)) * cp.sum(z) / T
    objective = cp.Maximize(mu @ w - risk_aversion * CVaR)

    try:
        prob = cp.Problem(objective, constraints)
        prob.solve(solver=cp.ECOS, verbose=False)

        if w.value is None:
            logger.warning("CVaR optimization failed - using equal weights")
            weights = np.ones(n) / n
        else:
            weights = w.value

        # Normalize and create output
        weights = np.clip(weights, 0, 1)
        weights /= np.sum(weights)

        result = dict(zip(available_assets, weights))
        logger.info(f"✅ Portfolio weights calculated for {len(result)} assets")
        return result

    except Exception as e:
        logger.error(f"Optimization error: {e} - using equal weights")
        weights = np.ones(n) / n
        return dict(zip(available_assets, weights))
