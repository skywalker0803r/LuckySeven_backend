import requests
import pandas as pd
import time
from datetime import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()

# 取得幣種價格資料
def get_crypto_prices(symbol, currency, start_date, end_date=None, interval="1d", data_limit=None):
    full_symbol = f"{symbol.upper()}{currency.upper()}"
    url = "https://api.binance.com/api/v3/klines"
    all_klines = []

    if data_limit is not None:
        # If data_limit is provided, fetch the latest 'data_limit' candles directly
        params = {
            "symbol": full_symbol,
            "interval": interval,
            "limit": data_limit  # Use the provided data_limit for Binance API
        }
        print(f"DEBUG: Fetching latest {data_limit} {full_symbol} klines from Binance API. URL: {url}, Params: {params}")
        try:
            response = requests.get(url, params=params)
            print(f"DEBUG: Binance API Response Status Code: {response.status_code}")
            if 'x-mbx-used-weight' in response.headers:
                print(f"DEBUG: Binance API Used Weight: {response.headers['x-mbx-used-weight']}")
            if 'x-mbx-used-weight-1m' in response.headers:
                print(f"DEBUG: Binance API Used Weight (1m): {response.headers['x-mbx-used-weight-1m']}")
            response.raise_for_status()
            klines = response.json()
            all_klines.extend(klines)
            print(f"DEBUG: Received {len(klines)} klines from Binance API for data_limit request.")
        except requests.exceptions.HTTPError as e:
            print(f"ERROR: HTTP error occurred while fetching {full_symbol} price with data_limit: {e}")
            if 'response' in locals():
                print(f"ERROR: Binance API Response Status Code: {response.status_code}")
                print(f"ERROR: Binance API Response Content: {response.text}")
            return pd.Series(dtype='float64')
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Failed to connect to Binance API with data_limit: {e}")
            return pd.Series(dtype='float64')
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to decode JSON response from Binance API with data_limit: {e}")
            if 'response' in locals():
                print(f"ERROR: Raw response content: {response.text}")
            return pd.Series(dtype='float64')
        except Exception as e:
            print(f"ERROR: An unknown error occurred while fetching {full_symbol} price with data_limit: {e}")
            return pd.Series(dtype='float64')
    else:
        # Original logic for fetching data between start_date and end_date
        start_timestamp_ms = int(start_date.timestamp() * 1000)
        if end_date is None:
            end_timestamp_ms = int(datetime.now().timestamp() * 1000)
        else:
            end_timestamp_ms = int(end_date.timestamp() * 1000)

        params = {
            "symbol": full_symbol,
            "interval": interval,
            "startTime": start_timestamp_ms,
            "endTime": end_timestamp_ms,
            "limit": 1000  # Max 1000 data points per request
        }

        print(f"DEBUG: Fetching {full_symbol} from Binance API. URL: {url}, Params: {params}")

        while True:
            try:
                print(f"DEBUG: Requesting data from {datetime.fromtimestamp(params['startTime']/1000)} to {datetime.fromtimestamp(params['endTime']/1000)}")
                response = requests.get(url, params=params)
                print(f"DEBUG: Binance API Response Status Code: {response.status_code}")
                
                # Check for rate limit headers
                if 'x-mbx-used-weight' in response.headers:
                    print(f"DEBUG: Binance API Used Weight: {response.headers['x-mbx-used-weight']}")
                if 'x-mbx-used-weight-1m' in response.headers:
                    print(f"DEBUG: Binance API Used Weight (1m): {response.headers['x-mbx-used-weight-1m']}")

                response.raise_for_status()  # 檢查 HTTP 請求是否成功
                klines = response.json()
                print(f"DEBUG: Received {len(klines)} klines from Binance API.")

                if not klines:
                    print("DEBUG: No more data from Binance API.")
                    break  # 沒有更多數據
                
                all_klines.extend(klines)

                if len(klines) < params["limit"]:
                    print("DEBUG: Reached end of data for this request.")
                    break
                params["startTime"] = klines[-1][6] + 1 # Modified: Use close_time + 1
                time.sleep(0.1)  # Be kind to the API
            except requests.exceptions.HTTPError as e:
                print(f"ERROR: HTTP error occurred while fetching {full_symbol} price: {e}")
                if 'response' in locals():
                    print(f"ERROR: Binance API Response Status Code: {response.status_code}")
                    print(f"ERROR: Binance API Response Content: {response.text}")
                return pd.Series(dtype='float64')
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Failed to connect to Binance API: {e}")
                return pd.Series(dtype='float64')
            except json.JSONDecodeError as e:
                print(f"ERROR: Failed to decode JSON response from Binance API: {e}")
                if 'response' in locals():
                    print(f"ERROR: Raw response content: {response.text}")
                return pd.Series(dtype='float64')
            except Exception as e:
                print(f"ERROR: An unknown error occurred while fetching {full_symbol} price: {e}")
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
    
    # Ensure we return only the requested number of data points from the end
    if data_limit is not None and len(df) > data_limit:
        df = df.tail(data_limit)

    return df[['open','high','low','close','volume']]

# 取得熱門幣種
def get_binance_trading_pairs(top_n):
    try:
        # 把幣種跟交易量抓出來
        ticker_url = "https://api.binance.com/api/v3/ticker/24hr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        print(f"DEBUG: Fetching trading pairs from Binance API. URL: {ticker_url}")
        ticker_response = requests.get(ticker_url,headers=headers)
        print(f"DEBUG: Binance API Trading Pairs Response Status Code: {ticker_response.status_code}")
        
        if 'x-mbx-used-weight' in ticker_response.headers:
            print(f"DEBUG: Binance API Used Weight (Trading Pairs): {ticker_response.headers['x-mbx-used-weight']}")

        ticker_response.raise_for_status()
        ticker_data = ticker_response.json()
        print(f"DEBUG: Received {len(ticker_data)} trading pairs from Binance API.")

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
        if 'ticker_response' in locals():
            print(f"ERROR: Binance API Trading Pairs Response Status Code: {ticker_response.status_code}")
            print(f"ERROR: Binance API Trading Pairs Response Content: {ticker_response.text}")
        return []
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to decode JSON response from Binance API (Trading Pairs): {e}")
        if 'ticker_response' in locals():
            print(f"ERROR: Raw response content (Trading Pairs): {ticker_response.text}")
        return []
    except Exception as e:
        print(f"ERROR: An unknown error occurred while fetching trading pairs: {e}")
        return []