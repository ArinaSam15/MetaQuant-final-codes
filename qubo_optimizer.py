# qubo_optimizer.py
import pandas as pd
import numpy as np
import logging
from pyqubo import Array, Constraint
import neal

logger = logging.getLogger(__name__)


class MarketRegimeDetector:
    def __init__(self):
        self.volatility_thresholds = {"low": 0.02, "high": 0.05}

    def get_optimal_n(self, returns_data):
        """Dynamic portfolio size based on market regime"""
        avg_volatility = returns_data.std().mean()

        if avg_volatility > self.volatility_thresholds["high"]:
            regime = "HIGH_VOLATILITY"
            n_assets = 20  # Max diversification
        elif avg_volatility < self.volatility_thresholds["low"]:
            regime = "LOW_VOLATILITY"
            n_assets = 5  # Concentrated alpha
        else:
            regime = "NORMAL"
            n_assets = 10  # Balanced

        logger.info(
            f"Market Regime: {regime} (vol: {avg_volatility:.3f}) → n={n_assets}"
        )
        return n_assets, regime


class DynamicQUBOOptimizer:
    def __init__(self, lambda_risk=0.5):
        self.regime_detector = MarketRegimeDetector()
        self.LAMBDA_RISK = lambda_risk

    def calculate_alpha_score(self, asset, price_data, sentiment_scores):
        """Composite alpha score combining multiple signals"""
        try:
            # Momentum Alpha (short-term)
            returns_24h = price_data[asset].pct_change(24).iloc[-1]
            returns_72h = price_data[asset].pct_change(72).iloc[-1]
            momentum_alpha = 0.7 * returns_24h + 0.3 * returns_72h

            # Sentiment Alpha
            sentiment_alpha = sentiment_scores.get(asset, 0.0)

            # Mean Reversion Alpha
            current_price = price_data[asset].iloc[-1]
            ma_24h = price_data[asset].rolling(24).mean().iloc[-1]
            mean_reversion_alpha = (
                (ma_24h - current_price) / current_price if current_price > 0 else 0
            )

            # Composite Alpha Score
            composite_alpha = (
                0.5 * momentum_alpha
                + 0.3 * sentiment_alpha
                + 0.2 * mean_reversion_alpha
            )

            return composite_alpha

        except Exception as e:
            logger.error(f"Error calculating alpha for {asset}: {e}")
            return 0.0

    def build_qubo_hamiltonian(
        self, assets, alpha_scores, correlation_matrix, n_target
    ):
        """Build QUBO Hamiltonian for dynamic portfolio selection"""
        x = Array.create("x", shape=len(assets), vartype="BINARY")

        # 1. Alpha Term (Reward)
        alpha_term = sum(-alpha_scores[i] * x[i] for i in range(len(assets)))

        # 2. Risk Term (Correlation Penalty)
        risk_term = 0
        for i in range(len(assets)):
            for j in range(i + 1, len(assets)):
                risk_term += correlation_matrix.iloc[i, j] * x[i] * x[j]

        # 3. Dynamic Constraint Term
        P = 2.0 * max(abs(alpha) for alpha in alpha_scores) if alpha_scores else 2.0
        constraint_term = P * (sum(x) - n_target) ** 2

        # Complete Hamiltonian
        H = alpha_term + self.LAMBDA_RISK * risk_term + constraint_term

        return H, x

    def select_optimal_portfolio(self, price_data, sentiment_scores):
        """Complete dynamic portfolio selection pipeline"""
        # Calculate returns
        returns_data = price_data.pct_change().dropna()

        # 1. Dynamic n selection
        n_assets, regime = self.regime_detector.get_optimal_n(returns_data)

        # 2. Calculate alpha scores
        alpha_scores = {}
        for asset in price_data.columns:
            alpha_scores[asset] = self.calculate_alpha_score(
                asset, price_data, sentiment_scores
            )

        # 3. Short-term correlation matrix (48-hour)
        short_term_returns = (
            returns_data.tail(48) if len(returns_data) >= 48 else returns_data
        )
        correlation_matrix = short_term_returns.corr()

        # 4. Build and solve QUBO
        assets = price_data.columns.tolist()
        alpha_values = [alpha_scores[asset] for asset in assets]

        H, x = self.build_qubo_hamiltonian(
            assets, alpha_values, correlation_matrix, n_assets
        )

        # 5. Solve QUBO
        try:
            model = H.compile()
            qubo, offset = model.to_qubo()
            sampler = neal.SimulatedAnnealingSampler()
            sampleset = sampler.sample_qubo(qubo, num_reads=100)

            # Extract solution
            solution = sampleset.first.sample
            selected_assets = [
                assets[i] for i in range(len(assets)) if solution.get(f"x[{i}]", 0) == 1
            ]

            logger.info(f"✅ QUBO selected {len(selected_assets)} assets")
            return selected_assets, regime, n_assets

        except Exception as e:
            logger.error(f"QUBO optimization failed: {e}")
            # Fallback: select top n assets by alpha score
            sorted_assets = sorted(
                alpha_scores.items(), key=lambda x: x[1], reverse=True
            )
            selected_assets = [asset for asset, score in sorted_assets[:n_assets]]
            return selected_assets, regime, n_assets


# Simple function for easy integration
def get_target_assets(price_data, sentiment_scores, lambda_risk=0.5):
    """Main function for other modules to call"""
    optimizer = DynamicQUBOOptimizer(lambda_risk=lambda_risk)
    return optimizer.select_optimal_portfolio(price_data, sentiment_scores)
