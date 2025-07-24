import requests
import pandas as pd
import time
from datetime import datetime

# 取得幣種價格資料
def get_crypto_prices(symbol, currency, start_date, end_date, interval="1d"):
    full_symbol = f"{symbol.upper()}{currency.upper()}"
    start_timestamp_ms = int(start_date.timestamp() * 1000)
    end_timestamp_ms = int(end_date.timestamp() * 1000)
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": full_symbol,
        "interval": interval,  # 使用傳入的 interval 參數
        "startTime": start_timestamp_ms,
        "endTime": end_timestamp_ms,
        "limit": 1000  # Max 1000 data points per request
    }
    all_klines = []
    while True:
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # 檢查 HTTP 請求是否成功
            klines = response.json()
            if not klines:
                break  # 沒有更多數據
            all_klines.extend(klines)
            if len(klines) < params["limit"]:
                break
            params["startTime"] = klines[-1][0] + 1
            time.sleep(0.1)  # Be kind to the API
        except requests.exceptions.HTTPError as e:
            print(f"Error: HTTP error occurred while fetching {full_symbol} price: {e} (Status code: {response.status_code if 'response' in locals() else 'N/A'})")
            return pd.Series(dtype='float64')
        except requests.exceptions.RequestException as e:
            print(f"Error: Failed to connect to Binance API: {e}")
            return pd.Series(dtype='float64')
        except Exception as e:
            print(f"Error: An unknown error occurred while fetching {full_symbol} price: {e}")
            return pd.Series(dtype='float64')
    if not all_klines:
        print(f"Warning: No price data fetched for {full_symbol} from Binance. Check symbol, interval or date range.")
        return pd.Series(dtype='float64')
    df = pd.DataFrame(all_klines, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col])
    df.set_index('open_time', inplace=True)
    return df[['open','high','low','close','volume']]

# 取得熱門幣種
def get_binance_trading_pairs(top_n):
    try:
        # 把幣種跟交易量抓出來
        ticker_url = "https://api.binance.com/api/v3/ticker/24hr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        ticker_response = requests.get(ticker_url,headers=headers)
        ticker_response.raise_for_status()
        ticker_data = ticker_response.json()
        volume_data = {item['symbol']: float(item['quoteVolume']) for item in ticker_data}

        # 整理成交易量在前 幣種在後    
        volumed_pairs = []
        for symbol in volume_data.keys():
            volumed_pairs.append((volume_data[symbol], symbol))
        
        # 按照交易量排序
        volumed_pairs.sort(key=lambda x: x[0], reverse=True)
        
        # 過濾top_n
        filtered_symbols = []
        for volume, symbol in volumed_pairs:
            if str(symbol)[-4:] == 'USDT':
                filtered_symbols.append(symbol[:-4])
            if len(filtered_symbols) >= top_n:
                break
        return filtered_symbols
    
    except requests.exceptions.RequestException as e:
        error_message = f"Error: Failed to fetch Binance trading pairs: {e}"
        print(error_message)
        return []