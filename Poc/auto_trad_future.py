import ccxt
from datetime import datetime
import time
import pandas as pd  # 假設 get_sma_signals 回傳 DataFrame
import sma

# 初始化 Binance USDT 永續合約客戶端
def create_binance_futures_client():
    api_key = '074bfe01cf7533fff407a680cdd32df3cd912378a9cbcd55787b2d136140ae48'
    secret = '3747cfeb3b75c7790a1f9c2d29eb11d45dd5b0626086dfb3cc2895d2051fc9db'
    client = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',  # 永續合約
        }
    })
    client.set_sandbox_mode(True)  # 測試用沙盒
    return client

# 設定槓桿 (數字，ex: 5)
def set_leverage(client, symbol, leverage=5):
    try:
        client.set_leverage(leverage, symbol)
        print(f"✅ 槓桿設為 {leverage}x")
    except Exception as e:
        print(f"設定槓桿失敗: {e}")

# 取得持倉資訊
def get_position(client, symbol):
    try:
        positions = client.fetch_positions([symbol])
        for pos in positions:
            if pos['symbol'] == symbol:
                return float(pos['contracts'])  # 多為正，空為負
    except Exception as e:
        print(f"查持倉錯誤: {e}")
    return 0

# 取得可用餘額（USDT）
def get_usdt_balance(client):
    try:
        balance = client.fetch_balance()
        return balance['USDT']['free']
    except Exception as e:
        print(f"查餘額錯誤: {e}")
        return 0

def get_min_order_amount(client, symbol):
    try:
        markets = client.load_markets()
        min_amt = markets[symbol]['limits']['amount']['min']
        print(f"✅ {symbol} 的最小下單量為 {min_amt}")
        return float(min_amt)
    except Exception as e:
        print(f"❌ 無法取得最小下單量: {e}")
        return 0.01  # 預設保底

def auto_trade_futures(symbol="ETH/USDT", interval="1m", usdt_per_order=50, leverage=5,strategy=None):
    client = create_binance_futures_client()
    set_leverage(client, symbol, leverage)
    min_amount = get_min_order_amount(client, symbol)  # 新增：抓最小下單量

    interval_sec = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400
    }[interval]

    while True:
        try:
            now = datetime.utcnow()
            df = strategy.get_signals(symbol.replace("/", ""), interval, now)
            latest = df.iloc[-1]
            close_price = latest['close']
            signal = latest['signal']

            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Close: {close_price:.2f}, Signal: {signal}")

            position_amt = get_position(client, symbol)
            print(f"當前持倉數量：{position_amt}")

            usdt_balance = get_usdt_balance(client)
            print(f"可用 USDT：{usdt_balance}")

            # 計算下單合約數量 (依槓桿調整)
            min_amount = get_min_order_amount(client, symbol)
            # ...
            amount = (usdt_per_order * leverage) / close_price
            amount = max(amount, min_amount)  # 確保達最小下單量
            amount = round(amount, 3)

            # 黃金交叉，且無多單 → 開多單
            if signal == 1 and position_amt <= 0:
                # 若有空單，先平空單
                if position_amt < 0:
                    print("平空單中...")
                    order = client.create_market_buy_order(symbol, abs(position_amt))
                    print(f"平空單成功：{order['info'].get('cumQty', 'N/A')} 張")

                print("開多單中...")
                order = client.create_market_buy_order(symbol, amount)
                print(f"開多單成功：{order['info'].get('cumQty', 'N/A')} 張")

            # 死亡交叉，且無空單 → 開空單
            elif signal == -1 and position_amt >= 0:
                # 若有多單，先平多單
                if position_amt > 0:
                    print("平多單中...")
                    order = client.create_market_sell_order(symbol, abs(position_amt))
                    print(f"平多單成功：{order['info'].get('cumQty', 'N/A')} 張")
                
                print("開空單中...")
                order = client.create_market_sell_order(symbol, amount)
                print(f"開空單成功：{order['info'].get('cumQty', 'N/A')} 張")

            else:
                print("無操作，持倉不變")

        except Exception as e:
            print(f"❌ 執行錯誤: {e}")

        time.sleep(int(interval_sec/3))

# 啟動交易機器人
if __name__ == "__main__":
    auto_trade_futures(symbol="ETH/USDT", interval="1m", usdt_per_order=50, leverage=5,strategy=sma)
