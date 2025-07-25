from datetime import datetime, timedelta
import pandas as pd
import requests
import time
import json
import os

class DataService:
    def get_crypto_prices(self, symbol, currency, start_date, end_date=None, interval="1d", data_limit=None):
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

    def get_binance_trading_pairs(self, top_n):
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

    def get_github_commits(self, owner, repo, start_date, end_date, headers):
        print(f"\n--- Starting to fetch GitHub Commit data for {owner}/{repo} ---")

        all_commits_for_range = []
                
        # Expand search range slightly for API to ensure all commits are caught
        api_start_date = (start_date - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        api_end_date = (end_date + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)

        since_date_str = api_start_date.isoformat(timespec='seconds') + 'Z'
        until_date_str = api_end_date.isoformat(timespec='seconds') + 'Z'

        page = 1
        per_page = 100
        
        try:
            while True:
                url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page={per_page}&page={page}&since={since_date_str}&until={until_date_str}"
                print(f"DEBUG(GitHub API): Request URL: {url}")
                response = requests.get(url, headers=headers)
                response.raise_for_status()

                commits = response.json()
                print(f"DEBUG(GitHub API): Received {len(commits)} commits for page {page}.")

                if not commits:
                    print(f"DEBUG(GitHub API): No more commits found for page {page}, breaking loop.")
                    break

                for commit in commits:
                    commit_date_str = commit['commit']['author']['date']
                    commit_date_obj = datetime.strptime(commit_date_str, '%Y-%m-%dT%H:%M:%SZ')
                    commit_day_str = commit_date_obj.strftime('%Y-%m-%d')
                    
                    # Only store commits within the requested block's date range
                    if start_date.replace(hour=0, minute=0, second=0, microsecond=0) <= commit_date_obj.replace(hour=0, minute=0, second=0, microsecond=0) <= end_date.replace(hour=0, minute=0, second=0, microsecond=0):
                        all_commits_for_range.append({
                            'date': commit_date_str, # Store as string for JSON
                            'message': commit['commit']['message']
                        })

                if len(commits) < per_page:
                    break

                page += 1
                time.sleep(0.1) # Be kind to the API

        except requests.exceptions.HTTPError as e:
            print(f"Error: HTTP error occurred while fetching GitHub Commits: {e} (Status code: {response.status_code if 'response' in locals() else 'N/A'})")
            if 'response' in locals() and response.status_code == 404:
                print("Please check if GitHub Owner and Repository names are correct.")
            elif 'response' in locals() and response.status_code == 403:
                print(f"GitHub API rate limit might have been reached (Status code: {response.status_code}). Consider setting GITHUB_TOKEN.")
            # For now, return empty DataFrame on error for missing data
            return pd.DataFrame(columns=['date', 'message'])
        except requests.exceptions.RequestException as e:
            print(f"Error: Failed to connect to GitHub API: {e}")
            return pd.DataFrame(columns=['date', 'message'])
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to decode JSON response from GitHub API: {e}")
            if 'response' in locals():
                print(f"ERROR: Raw response content: {response.text}")
            return pd.DataFrame(columns=['date', 'message'])
        except Exception as e:
            print(f"ERROR: An unknown error occurred while fetching GitHub Commits: {e}")
            return pd.DataFrame(columns=['date', 'message'])

        if not all_commits_for_range:
            print(f"Warning: No Commit data found for {owner}/{repo} within the specified date range ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}).")
            df = pd.DataFrame(columns=['date', 'message'])
        else:
            df = pd.DataFrame(all_commits_for_range)
            df['date'] = pd.to_datetime(df['date']).dt.floor('D') # Ensure date is floored to day
            # Filter to ensure strict adherence to requested start_date and end_date
            df = df[(df['date'] >= start_date.replace(hour=0, minute=0, second=0, microsecond=0)) &
                    (df['date'] <= end_date.replace(hour=0, minute=0, second=0, microsecond=0))]
            print(f"Successfully consolidated {len(df)} GitHub Commit data points for the requested range.")

        return df

data_service = DataService()