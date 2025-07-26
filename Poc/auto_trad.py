import ccxt
import time
import datetime
import sma

# ✅ 幣安 API 下單模組 (現貨)
def create_binance_client():
    api_key = 'mWLGc0yuQVCj6LPmTiem9moqSpDM9vLi2KFVSqaoQJppQVBqEopGs0YihGUDqKxN'
    secret = 'fub6Hre7UAzEkEjF3sdV5Pa1BE85xM7ptFeNysMTOvq28ZkQXfDfDEyv2ptVqG9I'
    client = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    client.set_sandbox_mode(True)  # 關鍵！！
    return client

# ✅ 自動交易機制
def auto_trade(symbol="ETH/USDT", interval="1m", usdt_per_order=50,strategy=None):
    
    # 建立客戶端
    client = create_binance_client()
    last_position = 0  # -1: 空單, 0: 無單, 1: 多單

    # 根據幣安 interval 轉秒數
    interval_sec = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400
    }[interval]

    # 自動交易迴圈
    while True:
        try:
            # 取得最新訊號
            now = datetime.utcnow()
            df = strategy.get_signals(symbol.replace("/", ""), interval, now)
            latest = df.iloc[-1]
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Close: {latest['close']:.2f}, Signal: {latest['signal']}")

            # 只有在訊號發生時才處理
            if latest["signal"] == 1 and last_position <= 0:
                print("🟢 黃金交叉 → 買入")
                client.create_market_buy_order(symbol, amount=usdt_per_order / latest["close"])
                last_position = 1
            
            elif latest["signal"] == -1 and last_position >= 0:
                print("🔴 死亡交叉 → 賣出")
                balance = client.fetch_balance()
                coin = symbol.split("/")[0]
                amount = balance[coin]["free"]
                client.create_market_sell_order(symbol, amount=amount)
                last_position = -1
            
            else:
                print("⏸ 無操作")
            
            # 看一下幣種餘額USDT餘額
            balance = client.fetch_balance()
            print(f"{str(symbol[:-5])} 餘額：{balance['total'].get(str(symbol[:-5]), 0)}")
            print(f"USDT 餘額：{balance['total'].get('USDT', 0)}")
    
        except Exception as e:
            print(f"❌ 發生錯誤：{e}")

        # 等待下一輪
        time.sleep(interval_sec)

if __name__ == "__main__":
    auto_trade(symbol="ETH/USDT", interval="1m", usdt_per_order=50,strategy=sma)