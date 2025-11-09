# data_fetcher.py
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import yfinance as yf
import logging
import time

logger = logging.getLogger(__name__)

# Pre-filtered universe of 20 high-quality, liquid assets
HIGH_QUALITY_ASSETS = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "ADA-USD",
    "AVAX-USD",
    "DOT-USD",
    "LINK-USD",
    "LTC-USD",
    "MATIC-USD",
    "ATOM-USD",
    "ETC-USD",
    "XLM-USD",
    "ALGO-USD",
    "UNI-USD",
    "AAVE-USD",
    "FIL-USD",
    "EOS-USD",
    "XTZ-USD",
]

HORUS_KEY = "c2ee3103d6057c2932b984b488c19db0df1d79d00775e5c88816d5e88d994afb"


def get_history_market_data(ticker, interval="1h", duration=100):
    """Get historical market data for a single ticker"""
    clean_ticker = ticker.replace("-USD", "")

    # Horus API call
    url = "https://api-horus.com/market/price"
    extend = {"1h": 3600, "15min": 60 * 15}
    duration_seconds = duration * extend[interval]
    start = int(time.time()) - duration_seconds
    end = int(time.time())

    try:
        response = requests.get(
            url,
            headers={"X-API-Key": HORUS_KEY},
            params={
                "asset": clean_ticker,
                "interval": interval,
                "start": start,
                "end": end,
            },
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                prices = [item["price"] for item in data if "price" in item]
                logger.info(f"✓ {ticker}: {len(prices)} points from Horus")
                return prices
    except Exception as e:
        logger.warning(f"Horus API failed for {ticker}: {e}")

    # Yahoo Finance fallback
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=duration)

        df = yf.download(
            tickers=ticker, interval="1h", start=start, end=end, progress=False
        )

        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                close_prices = df[("Close", ticker)].tolist()
            else:
                close_prices = df["Close"].tolist()

            close_prices = [x for x in close_prices if not np.isnan(x)]
            logger.info(f"✓ {ticker}: {len(close_prices)} points from Yahoo")
            return close_prices
    except Exception as e:
        logger.error(f"Yahoo Finance failed for {ticker}: {e}")

    return []


def get_all_market_data(interval="1h", duration=100):
    """Get market data for all high-quality assets"""
    logger.info(f"🔄 Fetching data for {len(HIGH_QUALITY_ASSETS)} high-quality assets")

    df = {}
    successful_assets = []

    for asset in HIGH_QUALITY_ASSETS:
        prices = get_history_market_data(asset, interval=interval, duration=duration)
        if prices and len(prices) >= 50:
            df[asset] = prices
            successful_assets.append(asset)

    if len(successful_assets) < 10:
        logger.error(
            f"CRITICAL: Only {len(successful_assets)} assets have sufficient data"
        )
        return None, None

    # Ensure equal length
    min_length = min(len(df[asset]) for asset in successful_assets)
    for asset in successful_assets:
        df[asset] = df[asset][-min_length:]

    price_df = pd.DataFrame(df)
    logger.info(
        f"✅ Data fetched: {price_df.shape[1]} assets, {price_df.shape[0]} periods"
    )
    return price_df, successful_assets

#data can only be on a daily basis
def get_horus_sentiment(sentiments=['whale_supply_share','whale_net_flow','whale_inflow_count'],interval='1d',duration=50):
    """Get sentiment scores for tickers"""
    sentiment_scores = {}
    duration+=1
    duration = duration * 24*60*60
    start=int(time.time())-duration
    end=int(time.time())

    for sentiment in sentiments:
        url = f"https://api-horus.com/addresses/{sentiment}"
        response = requests.get(
            url,
            headers={"X-API-Key": HORUS_KEY},
            params={
                "chain": "bitcoin",
                'interval':interval,
                'start' : start,
                'end' : end
                },
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            sentiment_scores[sentiment] = [item[sentiment] for item in data]         
        else:
            logger.warning(f"Sentiment failed for {sentiment}: {response.text}")
    #length-set:
    min_length = min(len(sentiment_scores[asset]) for asset in sentiment_scores.keys())
    for asset in sentiment_scores.keys():
        sentiment_scores[asset] = sentiment_scores[asset][-min_length:]
    #data-clean:
    for index in range(len(sentiment_scores['whale_supply_share'])):
        if(sentiment_scores['whale_supply_share'][index]>1 and index):
            sentiment_scores['whale_supply_share'][index]=sentiment_scores['whale_supply_share'][index-1]
    return pd.DataFrame(sentiment_scores)

    """
        # Realistic sentiment biases for demo
        if not any(abs(score) > 0.2 for score in sentiment_scores.values()):
            logger.info("Using realistic sentiment biases")
            sentiment_biases = {
                "BTC-USD": 0.3,
                "ETH-USD": 0.2,
                "SOL-USD": 0.4,
                "BNB-USD": 0.1,
                "XRP-USD": -0.1,
                "ADA-USD": 0.0,
                "AVAX-USD": 0.3,
                "DOT-USD": 0.1,
                "LINK-USD": 0.2,
                "LTC-USD": 0.0,
            }
            for ticker in tickers:
                sentiment_scores[ticker] = sentiment_biases.get(ticker, 0.0)
    """
