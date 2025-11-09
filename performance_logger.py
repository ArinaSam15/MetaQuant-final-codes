# performance_logger.py
import pandas as pd
import numpy as np
import logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class PerformanceLogger:
    def __init__(self):
        self.portfolio_history = []
        self.trade_log = []
        self.regime_history = []

    def calculate_metrics(self, returns_series, risk_free_rate=0.02, trading_days=252):
        """Calculate comprehensive performance metrics"""
        if len(returns_series) == 0:
            return {}

        metrics = {}

        # Basic metrics
        metrics["total_return"] = returns_series.sum()
        metrics["annual_return"] = returns_series.mean() * trading_days
        metrics["annual_volatility"] = returns_series.std() * np.sqrt(trading_days)

        # Sharpe Ratio
        if metrics["annual_volatility"] > 0:
            metrics["sharpe_ratio"] = (
                metrics["annual_return"] - risk_free_rate
            ) / metrics["annual_volatility"]
        else:
            metrics["sharpe_ratio"] = 0

        # Sortino Ratio (downside risk only)
        downside_returns = returns_series[returns_series < 0]
        downside_dev = (
            downside_returns.std() * np.sqrt(trading_days)
            if len(downside_returns) > 0
            else 0
        )
        metrics["sortino_ratio"] = (
            (metrics["annual_return"] - risk_free_rate) / downside_dev
            if downside_dev > 0
            else 0
        )

        # Drawdown analysis
        wealth_index = (1 + returns_series).cumprod()
        previous_peaks = wealth_index.cummax()
        drawdowns = (wealth_index - previous_peaks) / previous_peaks
        metrics["max_drawdown"] = drawdowns.min()
        metrics["calmar_ratio"] = (
            metrics["annual_return"] / abs(metrics["max_drawdown"])
            if metrics["max_drawdown"] != 0
            else 0
        )

        # Risk metrics
        metrics["var_95"] = returns_series.quantile(0.05)
        metrics["cvar_95"] = returns_series[returns_series <= metrics["var_95"]].mean()

        return metrics

    def log_rebalance(
        self, timestamp, selected_assets, weights, regime, n_assets, lambda_risk
    ):
        """Log rebalance decision"""
        log_entry = {
            "timestamp": timestamp,
            "regime": regime,
            "n_assets": n_assets,
            "lambda_risk": lambda_risk,
            "selected_assets": selected_assets,
            "weights": weights,
            "portfolio_size": len(selected_assets),
        }

        self.regime_history.append(log_entry)
        logger.info(f"📊 Rebalance logged: {regime}, n={n_assets}, λ={lambda_risk}")

    def log_trade(self, asset, action, quantity, price, success, error_msg=None):
        """Log individual trade"""
        trade_entry = {
            "timestamp": datetime.now(),
            "asset": asset,
            "action": action,
            "quantity": quantity,
            "price": price,
            "success": success,
            "error_msg": error_msg,
        }

        self.trade_log.append(trade_entry)

    def get_performance_report(self):
        """Generate performance report for Week 1 analysis"""
        if not self.regime_history:
            return "No performance data available"

        df = pd.DataFrame(self.regime_history)

        report = {
            "total_rebalances": len(df),
            "regime_distribution": df["regime"].value_counts().to_dict(),
            "avg_portfolio_size": df["portfolio_size"].mean(),
            "unique_assets_traded": len(
                set([asset for sublist in df["selected_assets"] for asset in sublist])
            ),
            "latest_lambda": df["lambda_risk"].iloc[-1] if len(df) > 0 else 0,
        }

        return report

    def save_logs(self):
        """Save logs to files"""
        try:
            # Save regime history
            regime_df = pd.DataFrame(self.regime_history)
            regime_df.to_csv("regime_history.csv", index=False)

            # Save trade log
            trade_df = pd.DataFrame(self.trade_log)
            trade_df.to_csv("trade_log.csv", index=False)

            logger.info("📁 Performance logs saved to files")
        except Exception as e:
            logger.error(f"Error saving logs: {e}")
