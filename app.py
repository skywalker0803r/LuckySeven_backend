from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import pandas as pd
import importlib.util
import sys
import os

# Import custom modules
from Datafetcher.binance_data_fetcher import get_crypto_prices, get_binance_trading_pairs
from Datafetcher.github_data_fetcher import get_github_commits # Import github_data_fetcher
from Backtest.backtest import run_backtest

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

app = FastAPI()

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_root():
    return {"message": "Welcome to LuckySeven Backend API"}

@app.get("/crypto_prices")
async def get_prices(
    symbol: str = "BTC",
    currency: str = "USDT",
    interval: str = "1h",
    start_date: str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
    end_date: str = datetime.now().strftime("%Y-%m-%d")
):
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        df = get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found for the given parameters.")
        
        # Convert DataFrame to a list of dictionaries for JSON response
        # Ensure datetime objects are converted to string
        df.reset_index(inplace=True)
        df['open_time'] = df['open_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        return df.to_dict(orient="records")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}. Please use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/trading_pairs")
async def get_pairs(top_n: int = 1000):
    try:
        pairs = get_binance_trading_pairs(top_n)
        return {"pairs": pairs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/strategy_list")
async def get_strategy_list():
    strategy_dir = "Strategy"
    strategies = []
    for filename in os.listdir(strategy_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            strategies.append(filename[:-3]) # Remove .py extension
    return {"strategies": strategies}

@app.get("/strategy_code/{strategy_name}")
async def get_strategy_code(strategy_name: str):
    strategy_path = os.path.join("Strategy", f"{strategy_name}.py")
    if not os.path.exists(strategy_path):
        raise HTTPException(status_code=404, detail="Strategy not found.")
    with open(strategy_path, "r", encoding="utf-8") as f:
        code = f.read()
    return {"code": code}

@app.post("/run_backtest")
async def run_strategy_backtest(
    request: dict,
):
    symbol = request.get("symbol")
    currency = request.get("currency")
    interval = request.get("interval")
    start_date = request.get("start_date")
    end_date = request.get("end_date")
    strategy_code = request.get("strategy_code")
    initial_capital = request.get("initial_capital", 10000)
    commission_rate = request.get("commission_rate", 0.001)
    slippage = request.get("slippage", 0.0005)
    risk_free_rate = request.get("risk_free_rate", 0.02)
    github_owner = request.get("github_owner")
    github_repo = request.get("github_repo")
    strategy_name = request.get("strategy_name")
    try:
        # Fetch data
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        df = get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
        if df.empty:
            raise HTTPException(status_code=404, detail="No crypto data found for the given parameters.")

        # Handle GitHub commit data for commit_sma strategy
        if strategy_name == "commit_sma" and github_owner and github_repo: # Check if strategy is commit_sma and owner/repo are provided
            github_commits_df = get_github_commits(github_owner, github_repo, start_dt, end_dt, GITHUB_HEADERS)

            if github_commits_df.empty:
                raise HTTPException(status_code=404, detail="No GitHub commit data found for the given parameters. Please check owner/repo or date range.")
            
            # Aggregate commit count by day
            github_commits_count = github_commits_df.groupby(github_commits_df['date'].dt.floor('D')).size().reset_index(name='commit_count')
            github_commits_count.rename(columns={'date': 'open_time'}, inplace=True)
            github_commits_count.set_index('open_time', inplace=True)

            # Merge crypto data with commit data
            df = pd.merge(df, github_commits_count, left_index=True, right_index=True, how='left')
            df['commit_count'] = df['commit_count'].fillna(0) # Fill NaN with 0 if no commits on a day
            print("DEBUG: DataFrame columns after merging GitHub data:", df.columns)
            print("DEBUG: DataFrame head after merging GitHub data:\n", df.head())

        # Dynamically load and execute strategy code
        # Create a temporary module to execute the strategy code
        spec = importlib.util.spec_from_loader("temp_strategy_module", loader=None)
        temp_strategy_module = importlib.util.module_from_spec(spec)
        exec(strategy_code, temp_strategy_module.__dict__)

        if not hasattr(temp_strategy_module, 'generate_signal'):
            raise HTTPException(status_code=400, detail="Strategy code must contain a 'generate_signal' function.")
        
        df_with_signal = temp_strategy_module.generate_signal(df.copy())

        # Run backtest
        results = run_backtest(
            df_with_signal,
            initial_capital,
            commission_rate,
            slippage,
            risk_free_rate
        )
        
        # Convert pandas Series in 'fig' to lists for JSON serialization
        for key, value in results['fig'].items():
            if isinstance(value, pd.Series):
                # Convert index to string and values to list
                results['fig'][key] = {'index': value.index.strftime('%Y-%m-%d %H:%M:%S').tolist(), 'values': value.tolist()}

        return results

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format or strategy parameter: {e}")
    except HTTPException as e:
        raise e # Re-raise HTTP exceptions
    except Exception as e:
        # Log the full traceback for debugging
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An error occurred during backtest: {e}")
