# bot_executor.py
# QF2 Trader Module - Portfolio Management and Rebalancing

import requests
import time
import hmac
import hashlib
import logging
from typing import Dict, Tuple, List, Optional

# Configuration
BASE_URL = "https://mock-api.roostoo.com"
API_KEY = "SIQ3xG7yGWC9RmmOJ5f9zsAUAGTee69qrI0CkkPro35XG0XKxmXbhpCeOPN6tqy7"
SECRET_KEY = "GKV86o7ISR6DBGHGqMakQN84N9hEeNbnWmYhWsRI5h5KGhx8G6sbLbGSViVKbqgj"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def _get_timestamp():
    """Returns a 13-digit millisecond timestamp as a string."""
    return str(int(time.time() * 1000))

def _generate_signature(payload: Dict) -> Tuple[Dict, Dict, str]:
    """Generate authentication signature and headers"""
    # Add timestamp to payload
    payload['timestamp'] = _get_timestamp()
    
    # Sort keys and create parameter string
    sorted_keys = sorted(payload.keys())
    total_params = "&".join(f"{key}={payload[key]}" for key in sorted_keys)
    
    # Create HMAC-SHA256 signature
    signature = hmac.new(
        SECRET_KEY.encode('utf-8'),
        total_params.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Create headers
    headers = {
        'RST-API-KEY': API_KEY,
        'MSG-SIGNATURE': signature
    }
    
    return headers, payload, total_params

def get_current_portfolio() -> Tuple[Dict[str, float], float]:
    """
    Get current portfolio holdings and cash balance
    
    Returns:
        Tuple[portfolio_dict, cash_balance]
        - portfolio_dict: {asset: quantity} e.g., {'BTC': 0.5, 'ETH': 2.0}
        - cash_balance: USD available for trading
    """
    try:
        logger.info("Fetching current portfolio...")
        
        # Get authenticated headers
        headers, payload, _ = _generate_signature({})
        
        # Make API call
        response = requests.get(
            f"{BASE_URL}/v3/balance",
            headers=headers,
            params=payload,
            timeout=10
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to get portfolio: {response.status_code}")
            return {}, 0.0
        
        data = response.json()
        
        if not data.get('Success'):
            error_msg = data.get('ErrMsg', 'Unknown error')
            logger.error(f"API Error: {error_msg}")
            return {}, 0.0
        
        # Parse the portfolio data
        wallet = data.get('Wallet', {})
        portfolio_dict = {}
        cash_balance = 0.0
        
        # Extract cash (USD) balance
        usd_data = wallet.get('USD', {})
        cash_balance = float(usd_data.get('Free', 0)) + float(usd_data.get('Lock', 0))
        
        # Extract crypto holdings (excluding USD)
        for asset, balance_info in wallet.items():
            if asset != 'USD':
                free = float(balance_info.get('Free', 0))
                locked = float(balance_info.get('Lock', 0))
                total = free + locked
                
                # Only include assets with significant holdings
                if total > 0.000001:  # Avoid dust amounts
                    portfolio_dict[asset] = total
        
        logger.info(f"Portfolio parsed: {len(portfolio_dict)} assets, Cash: ${cash_balance:.2f}")
        return portfolio_dict, cash_balance
        
    except requests.exceptions.Timeout:
        logger.error("Timeout while fetching portfolio")
        return {}, 0.0
    except requests.exceptions.ConnectionError:
        logger.error("Connection error while fetching portfolio")
        return {}, 0.0
    except Exception as e:
        logger.error(f"Unexpected error in get_current_portfolio: {str(e)}")
        return {}, 0.0

def _place_order(pair_or_coin: str, side: str, quantity: float, order_type: str = "MARKET") -> Optional[Dict]:
    """Place an order - internal function for rebalancing"""
    # Determine the full pair name
    pair = f"{pair_or_coin}/USD" if "/" not in pair_or_coin else pair_or_coin
    
    # Create payload
    payload = {
        'pair': pair,
        'side': side.upper(),
        'type': order_type.upper(),
        'quantity': str(quantity)
    }
    
    headers, final_payload, total_params_string = _generate_signature(payload)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    
    try:
        logger.info(f"Placing {side} order for {quantity} {pair}...")
        response = requests.post(
            f"{BASE_URL}/v3/place_order",
            headers=headers,
            data=total_params_string,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result and result.get('Success'):
                order_id = result.get('OrderDetail', {}).get('OrderID')
                logger.info(f"✅ {side} order placed successfully! Order ID: {order_id}")
            else:
                error_msg = result.get('ErrMsg', 'Unknown error') if result else 'No response'
                logger.error(f"❌ {side} order failed: {error_msg}")
            return result
        else:
            logger.error(f"Order API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Order placement error: {e}")
        return None

def _get_current_prices(assets: list) -> Dict[str, float]:
    """Get current prices for portfolio assets"""
    prices = {}
    for asset in assets:
        if asset == 'USD':
            prices[asset] = 1.0  # USD is always 1
            continue
            
        try:
            # Use the ticker endpoint
            pair = f"{asset}/USD"
            response = requests.get(
                f"{BASE_URL}/v3/ticker",
                params={'timestamp': _get_timestamp(), 'pair': pair},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('Success'):
                    last_price = data['Data'][pair]['LastPrice']
                    prices[asset] = float(last_price)
            
            time.sleep(0.1)  # Rate limiting
            
        except Exception as e:
            logger.warning(f"Could not get price for {asset}: {e}")
            prices[asset] = 0.0
    
    return prices

def execute_rebalance(target_weights: Dict[str, float], 
                     current_portfolio: Dict[str, float], 
                     cash_balance: float, 
                     threshold: float = 0.03) -> Dict:
    """
    Execute portfolio rebalancing according to target weights
    
    Args:
        target_weights: {asset: target_weight} e.g., {'BTC': 0.6, 'ETH': 0.4}
        current_portfolio: {asset: current_quantity}
        cash_balance: Current USD cash available
        threshold: Rebalancing threshold (default 3%)
        
    Returns:
        Dict with rebalancing results and order details
    """
    logger.info("🚀 STARTING PORTFOLIO REBALANCE")
    logger.info(f"Target weights: {target_weights}")
    logger.info(f"Current portfolio: {current_portfolio}")
    logger.info(f"Cash balance: ${cash_balance:.2f}")
    logger.info(f"Rebalance threshold: {threshold*100}%")
    
    rebalance_result = {
        'success': False,
        'total_orders_placed': 0,
        'sell_orders': [],
        'buy_orders': [],
        'errors': [],
        'final_cash_balance': cash_balance
    }
    
    try:
        # Step 1: Get current prices for all assets
        all_assets = set(list(target_weights.keys()) + list(current_portfolio.keys()))
        if 'USD' in all_assets:
            all_assets.remove('USD')
            
        prices = _get_current_prices(list(all_assets))
        logger.info(f"Retrieved prices for {len(prices)} assets")
        
        # Step 2: Calculate current portfolio value and weights
        portfolio_value = 0.0
        for asset, quantity in current_portfolio.items():
            if asset in prices and prices[asset] > 0:
                portfolio_value += quantity * prices[asset]
        
        total_value = portfolio_value + cash_balance
        
        if total_value <= 0:
            logger.error("Total portfolio value is zero or negative - cannot rebalance")
            rebalance_result['errors'].append("Total portfolio value is zero")
            return rebalance_result
        
        logger.info(f"📊 Total Portfolio Value: ${total_value:.2f}")
        
        # Calculate current weights
        current_weights = {}
        for asset in all_assets:
            if asset in current_portfolio and asset in prices and prices[asset] > 0:
                asset_value = current_portfolio[asset] * prices[asset]
                current_weights[asset] = asset_value / total_value
            else:
                current_weights[asset] = 0.0
        
        # Add cash as 'USD' in weights
        current_weights['USD'] = cash_balance / total_value
        
        logger.info("📈 CURRENT WEIGHTS:")
        for asset, weight in current_weights.items():
            logger.info(f"   {asset}: {weight:.1%}")
        
        logger.info("🎯 TARGET WEIGHTS:")
        for asset, weight in target_weights.items():
            logger.info(f"   {asset}: {weight:.1%}")
        
        # Step 3: Calculate rebalancing needs
        rebalance_actions = []
        
        logger.info("🧮 Calculating rebalancing actions...")
        
        for asset, target_weight in target_weights.items():
            if asset == 'USD':
                continue  # Skip USD for trading actions
                
            current_weight = current_weights.get(asset, 0.0)
            weight_diff = current_weight - target_weight
            abs_diff = abs(weight_diff)
            
            # Check if outside threshold
            if abs_diff > threshold:
                action_type = 'SELL' if weight_diff > 0 else 'BUY'
                
                # Calculate USD value to rebalance
                usd_value_to_rebalance = abs(weight_diff) * total_value
                
                # Calculate quantity to trade
                if asset in prices and prices[asset] > 0:
                    quantity = usd_value_to_rebalance / prices[asset]
                    
                    # Apply minimum quantity checks
                    if quantity > 0.000001:  # Avoid dust amounts
                        action = {
                            'asset': asset,
                            'action': action_type,
                            'current_weight': current_weight,
                            'target_weight': target_weight,
                            'weight_diff': weight_diff,
                            'usd_value': usd_value_to_rebalance,
                            'quantity': quantity,
                            'price': prices[asset]
                        }
                        rebalance_actions.append(action)
                        
                        logger.info(f"   {asset}: {current_weight:.1%} → {target_weight:.1%} "
                                   f"({action_type} {quantity:.6f})")
        
        # Also handle assets that need to be completely sold (not in target weights)
        for asset, current_weight in current_weights.items():
            if (asset not in target_weights and asset != 'USD' and 
                current_weight > threshold and asset in prices and prices[asset] > 0):
                
                usd_value = current_weight * total_value
                quantity = usd_value / prices[asset]
                
                action = {
                    'asset': asset,
                    'action': 'SELL',
                    'current_weight': current_weight,
                    'target_weight': 0.0,
                    'weight_diff': current_weight,
                    'usd_value': usd_value,
                    'quantity': quantity,
                    'price': prices[asset]
                }
                rebalance_actions.append(action)
                
                logger.info(f"   {asset}: {current_weight:.1%} → 0.0% "
                           f"(SELL {quantity:.6f} - not in target)")
        
        logger.info(f"📋 Total rebalance actions: {len(rebalance_actions)}")
        
        if not rebalance_actions:
            logger.info("✅ No rebalancing needed - portfolio within thresholds")
            rebalance_result['success'] = True
            return rebalance_result
        
        # Step 4: Execute SELL orders first
        sell_orders = [action for action in rebalance_actions if action['action'] == 'SELL']
        if sell_orders:
            logger.info(f"📤 Executing {len(sell_orders)} SELL orders")
            
            for order in sell_orders:
                result = _place_order(
                    order['asset'], 'SELL', order['quantity']
                )
                
                order_result = {
                    'asset': order['asset'],
                    'action': 'SELL',
                    'quantity': order['quantity'],
                    'success': result is not None and result.get('Success', False),
                    'api_response': result,
                    'timestamp': time.time()
                }
                
                if order_result['success']:
                    order_id = result.get('OrderDetail', {}).get('OrderID')
                    order_result['order_id'] = order_id
                else:
                    error_msg = result.get('ErrMsg', 'Unknown error') if result else 'No response'
                    order_result['error'] = error_msg
                
                rebalance_result['sell_orders'].append(order_result)
                time.sleep(1)  # Rate limiting
            
            # Wait for orders to potentially fill
            logger.info("⏳ Waiting 5 seconds for SELL orders...")
            time.sleep(5)
        
        # Step 5: Get updated cash balance
        logger.info("🔄 Getting updated cash balance...")
        updated_portfolio, updated_cash = get_current_portfolio()
        rebalance_result['final_cash_balance'] = updated_cash
        logger.info(f"💰 Updated cash balance: ${updated_cash:.2f}")
        
        # Step 6: Execute BUY orders
        buy_orders = [action for action in rebalance_actions if action['action'] == 'BUY']
        if buy_orders:
            # Recalculate buy quantities based on actual available cash
            total_buy_value = sum(order['usd_value'] for order in buy_orders)
            
            if total_buy_value > updated_cash:
                # Scale down buy orders proportionally
                scale_factor = updated_cash / total_buy_value
                logger.warning(f"⚠️ Insufficient cash. Scaling buy orders by {scale_factor:.1%}")
                
                adjusted_buy_orders = []
                for order in buy_orders:
                    adjusted_usd = order['usd_value'] * scale_factor
                    adjusted_quantity = adjusted_usd / prices[order['asset']]
                    
                    adjusted_order = order.copy()
                    adjusted_order['usd_value'] = adjusted_usd
                    adjusted_order['quantity'] = adjusted_quantity
                    
                    adjusted_buy_orders.append(adjusted_order)
                    
                    logger.info(f"   {order['asset']}: {order['quantity']:.6f} → {adjusted_quantity:.6f}")
                
                buy_orders = adjusted_buy_orders
            
            logger.info(f"📥 Executing {len(buy_orders)} BUY orders")
            
            for order in buy_orders:
                result = _place_order(
                    order['asset'], 'BUY', order['quantity']
                )
                
                order_result = {
                    'asset': order['asset'],
                    'action': 'BUY',
                    'quantity': order['quantity'],
                    'success': result is not None and result.get('Success', False),
                    'api_response': result,
                    'timestamp': time.time()
                }
                
                if order_result['success']:
                    order_id = result.get('OrderDetail', {}).get('OrderID')
                    order_result['order_id'] = order_id
                else:
                    error_msg = result.get('ErrMsg', 'Unknown error') if result else 'No response'
                    order_result['error'] = error_msg
                
                rebalance_result['buy_orders'].append(order_result)
                time.sleep(1)  # Rate limiting
        
        # Update total orders count
        rebalance_result['total_orders_placed'] = len(rebalance_result['sell_orders']) + len(rebalance_result['buy_orders'])
        
        # Final validation
        success_orders = len([o for o in rebalance_result['sell_orders'] + rebalance_result['buy_orders'] 
                            if o.get('success', False)])
        
        if success_orders > 0:
            rebalance_result['success'] = True
            logger.info(f"✅ REBALANCE COMPLETED: {success_orders} orders executed successfully")
        else:
            logger.warning("⚠️ Rebalance completed but no orders were filled")
        
        return rebalance_result
        
    except Exception as e:
        logger.error(f"💥 CRITICAL ERROR during rebalance: {str(e)}")
        rebalance_result['errors'].append(f"Critical error: {str(e)}")
        return rebalance_result

# Test functions
def test_functions():
    """Test both functions"""
    print("🧪 Testing Trader Functions")
    print("=" * 50)
    
    # Test get_current_portfolio
    print("1. Testing get_current_portfolio()...")
    portfolio, cash = get_current_portfolio()
    print(f"   ✅ Portfolio: {len(portfolio)} assets")
    print(f"   ✅ Cash: ${cash:.2f}")
    
    # Test execute_rebalance with example data
    print("\n2. Testing execute_rebalance()...")
    target_weights = {'BTC': 0.5, 'ETH': 0.3}
    
    result = execute_rebalance(
        target_weights=target_weights,
        current_portfolio=portfolio,
        cash_balance=cash,
        threshold=0.50  # High threshold for testing
    )
    
    print(f"   ✅ Success: {result['success']}")
    print(f"   ✅ Orders placed: {result['total_orders_placed']}")
    print(f"   ✅ Final cash: ${result['final_cash_balance']:.2f}")
    
    return result

if __name__ == "__main__":
    # Run tests
    test_result = test_functions()
