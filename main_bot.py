# main_bot.py
import time
import logging
from datetime import datetime
import pandas as pd

# Import your modules
import data_fetcher
import qubo_optimizer
import allocator
import bot_executor
import performance_logger

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class DynamicQUBOBot:
    def __init__(self, lambda_risk=0.5):
        self.lambda_risk = lambda_risk
        self.performance_logger = performance_logger.PerformanceLogger()
        self.iteration_count = 0

        # Week 1 parameters (will be tuned for Week 2)
        self.hyperparameters = {
            "lambda_risk": lambda_risk,
            "rebalance_interval": 4 * 3600,  # 4 hours
            "last_rebalance": None,
        }

    def run_trading_cycle(self):
        """Run one complete trading cycle"""
        logger.info(f"🔄 Trading Cycle {self.iteration_count}")

        try:
            # 1. Fetch market data
            price_data, successful_assets = data_fetcher.get_all_market_data(
                duration=100
            )
            if price_data is None:
                logger.error("❌ Failed to fetch market data")
                return False

            # 2. Fetch sentiment data
            sentiment_scores = data_fetcher.get_horus_sentiment(successful_assets)

            # 3. QUBO Asset Selection
            selected_assets, regime, n_assets = qubo_optimizer.get_target_assets(
                price_data, sentiment_scores, self.lambda_risk
            )

            if not selected_assets:
                logger.error("❌ QUBO failed to select assets")
                return False

            # 4. Portfolio Allocation
            portfolio_weights = allocator.get_target_weights(
                selected_assets, price_data
            )

            # 5. Get current portfolio and execute rebalance
            current_holdings, cash_balance = bot_executor.get_current_portfolio()

            # 6. Execute trades
            rebalance_result = bot_executor.execute_rebalance(
                portfolio_weights, current_holdings, cash_balance, threshold=0.03
            )

            # 7. Log performance
            self.performance_logger.log_rebalance(
                timestamp=datetime.now(),
                selected_assets=selected_assets,
                weights=portfolio_weights,
                regime=regime,
                n_assets=n_assets,
                lambda_risk=self.lambda_risk,
            )

            # Log trades
            for order in rebalance_result.get("sell_orders", []) + rebalance_result.get(
                "buy_orders", []
            ):
                self.performance_logger.log_trade(
                    asset=order["asset"],
                    action=order["action"],
                    quantity=order["quantity"],
                    price=order.get("price", 0),
                    success=order.get("success", False),
                    error_msg=order.get("error", None),
                )

            self.iteration_count += 1
            logger.info(
                f"✅ Trading cycle {self.iteration_count} completed successfully"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Trading cycle failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False

    def analyze_and_tune(self):
        """Analyze Week 1 performance and tune hyperparameters"""
        report = self.performance_logger.get_performance_report()
        logger.info(f"📈 Performance Report: {report}")

        # Simple tuning logic based on regime distribution
        if report["total_rebalances"] > 10:
            regime_dist = report["regime_distribution"]
            high_vol_count = regime_dist.get("HIGH_VOLATILITY", 0)

            # If we encountered lots of high volatility, increase risk aversion
            if high_vol_count > report["total_rebalances"] * 0.3:
                new_lambda = min(1.5, self.lambda_risk * 1.5)
                logger.info(
                    f"🔄 Tuning: Increasing lambda_risk from {self.lambda_risk} to {new_lambda}"
                )
                self.lambda_risk = new_lambda

        self.performance_logger.save_logs()

    def run_continuously(self):
        """Main bot loop"""
        logger.info("🤖 Starting Dynamic QUBO Trading Bot")

        while True:
            try:
                success = self.run_trading_cycle()

                if success:
                    # Weekly analysis and tuning
                    if self.iteration_count % 42 == 0:  # ~weekly for 4-hour cycles
                        self.analyze_and_tune()

                    logger.info(
                        f"💤 Sleeping for {self.hyperparameters['rebalance_interval']} seconds"
                    )
                    time.sleep(self.hyperparameters["rebalance_interval"])
                else:
                    logger.warning("🔄 Cycle failed, retrying in 5 minutes")
                    time.sleep(300)

            except KeyboardInterrupt:
                logger.info("🛑 Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"💥 Unexpected error in main loop: {e}")
                time.sleep(300)


# For testing
def test_bot():
    """Test the bot with one cycle"""
    bot = DynamicQUBOBot(lambda_risk=0.5)
    bot.run_trading_cycle()


if __name__ == "__main__":
    # Start the bot
    bot = DynamicQUBOBot(lambda_risk=0.5)
    bot.run_continuously()
