from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import pandas as pd
import importlib.util
import sys
import os

# Import custom modules
from Datafetcher.binance_data_fetcher import get_crypto_prices, get_binance_trading_pairs
from Backtest.backtest import run_backtest

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
    try:
        # Fetch data
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        df = get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found for the given parameters.")

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
