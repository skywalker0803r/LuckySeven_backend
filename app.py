from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import pandas as pd
import importlib.util
import sys
import os
import multiprocessing # Added for process management
import time

# Import custom modules
from Datafetcher.binance_data_fetcher import get_crypto_prices, get_binance_trading_pairs
from Datafetcher.github_data_fetcher import get_github_commits # Import github_data_fetcher
from Backtest.backtest import run_backtest

# Import database components
from database import SessionLocal, SavedStrategy, RunningStrategy, TradeLog, EquityCurve, get_db

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

app = FastAPI()

# CORS settings
app.add_middleware(
    CORSMiddleware,
    #allow_origins=["https://luckyseven-frontend.onrender.com"],
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Dictionary to store running strategy processes
running_strategy_processes = {}

# Helper function to run live strategy in a separate process
def _run_live_strategy_process(running_strategy_id: int, saved_strategy_id: int):
    db = SessionLocal()
    try:
        running_strategy_record = db.query(RunningStrategy).filter(RunningStrategy.id == running_strategy_id).first()
        if not running_strategy_record:
            print(f"STRATEGY_RUNNER ERROR: Running strategy record {running_strategy_id} not found.")
            return

        saved_strategy_record = db.query(SavedStrategy).filter(SavedStrategy.id == saved_strategy_id).first()
        if not saved_strategy_record:
            print(f"STRATEGY_RUNNER ERROR: Saved strategy record {saved_strategy_id} not found.")
            return

        running_strategy_record.pid = os.getpid()
        running_strategy_record.status = "running"
        db.commit()
        print(f"STRATEGY_RUNNER: Updated running_strategy {running_strategy_id} status to 'running' with PID {os.getpid()}")

        strategy_code = saved_strategy_record.code
        symbol = saved_strategy_record.symbol
        currency = saved_strategy_record.currency
        interval = saved_strategy_record.interval
        initial_capital = saved_strategy_record.initial_capital
        commission_rate = saved_strategy_record.commission_rate
        slippage = saved_strategy_record.slippage
        risk_free_rate = saved_strategy_record.risk_free_rate
        github_owner = saved_strategy_record.github_owner
        github_repo = saved_strategy_record.github_repo

        spec = importlib.util.spec_from_loader("live_strategy_module", loader=None)
        live_strategy_module = importlib.util.module_from_spec(spec)
        exec(strategy_code, live_strategy_module.__dict__)

        if not hasattr(live_strategy_module, 'generate_signal'):
            print("STRATEGY_RUNNER ERROR: Strategy code must contain a 'generate_signal' function.")
            running_strategy_record.status = "error"
            db.commit()
            return

        lookback_periods = getattr(live_strategy_module, 'REQUIRED_LOOKBACK_PERIODS', 100)

        current_capital = initial_capital
        current_holding_shares = 0
        last_processed_time = None

        def calculate_start_dt(end_dt, interval, lookback_periods=200):
            if interval == '1m':
                return end_dt - timedelta(minutes=lookback_periods)
            elif interval == '3m':
                return end_dt - timedelta(minutes=lookback_periods * 3)
            elif interval == '5m':
                return end_dt - timedelta(minutes=lookback_periods * 5)
            elif interval == '15m':
                return end_dt - timedelta(minutes=lookback_periods * 15)
            elif interval == '30m':
                return end_dt - timedelta(minutes=lookback_periods * 30)
            elif interval == '1h':
                return end_dt - timedelta(hours=lookback_periods)
            elif interval == '4h':
                return end_dt - timedelta(hours=lookback_periods * 4)
            elif interval == '1d':
                return end_dt - timedelta(days=lookback_periods)
            else:
                print(f"Warning: Unknown interval '{interval}'. Defaulting to 365 days lookback.")
                return end_dt - timedelta(days=365)

        while True:
            # Re-fetch the running strategy record in each iteration to get the latest status
            current_running_strategy = db.query(RunningStrategy).filter(RunningStrategy.id == running_strategy_id).first()

            if not current_running_strategy or current_running_strategy.status == "stopped":
                print(f"STRATEGY_RUNNER: Strategy {saved_strategy_record.name} (ID: {saved_strategy_id}) stopped or deleted. Exiting loop.")
                break

            # Update the local running_strategy_record reference
            running_strategy_record = current_running_strategy

            print(f"STRATEGY_RUNNER: Fetching data for {symbol}{currency} at {datetime.now()} for strategy {saved_strategy_record.name} (ID: {saved_strategy_id})...")
            end_dt = datetime.now()
            start_dt = calculate_start_dt(end_dt, interval, lookback_periods)
            print(f"STRATEGY_RUNNER DEBUG: Strategy calculation data range: start_dt={start_dt}, end_dt={end_dt}, lookback_periods={lookback_periods}")

            df = get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
            print(f"STRATEGY_RUNNER DEBUG: Received {len(df)} klines for strategy calculation.")
            if df.empty:
                print(f"STRATEGY_RUNNER WARNING: No crypto data fetched for {symbol}{currency}. Retrying in 60 seconds.")
                time.sleep(60)
                continue

            if saved_strategy_record.name == "commit_sma" and github_owner and github_repo:
                github_commits_df = get_github_commits(github_owner, github_repo, start_dt, end_dt, {})
                if github_commits_df.empty:
                    print("STRATEGY_RUNNER WARNING: No GitHub commit data fetched. Strategy might not work as expected.")
                else:
                    github_commits_count = github_commits_df.groupby(github_commits_df['date'].dt.floor('D')).size().reset_index(name='commit_count')
                    github_commits_count.rename(columns={'date': 'open_time'}, inplace=True)
                    github_commits_count.set_index('open_time', inplace=True)
                    df = pd.merge(df, github_commits_count, left_index=True, right_index=True, how='left')
                    df['commit_count'] = df['commit_count'].fillna(0)

            df_with_signal = live_strategy_module.generate_signal(df.copy())
            latest_signal_row = df_with_signal.iloc[-1]
            latest_signal = latest_signal_row['signal']
            print(f"STRATEGY_RUNNER DEBUG: Latest generated signal: {latest_signal}")
            latest_close_price = latest_signal_row['close']
            latest_open_time = df_with_signal.index[-1]

            if last_processed_time is None or latest_open_time > last_processed_time:
                print(f"STRATEGY_RUNNER: New signal generated at {latest_open_time}: {latest_signal}")
                if latest_signal == 1:
                    if current_holding_shares == 0:
                        buy_price = latest_close_price * (1 + slippage)
                        shares_to_buy = (current_capital / (buy_price * (1 + commission_rate)))
                        if shares_to_buy > 0:
                            commission = shares_to_buy * buy_price * commission_rate
                            current_capital -= (shares_to_buy * buy_price + commission)
                            current_holding_shares += shares_to_buy
                            trade_log = TradeLog(
                                running_strategy_id=running_strategy_id,
                                timestamp=latest_open_time,
                                trade_type="buy",
                                price=buy_price,
                                quantity=shares_to_buy,
                                commission=commission
                            )
                            db.add(trade_log)
                            db.commit()

                elif latest_signal == -1:
                    if current_holding_shares > 0:
                        sell_price = latest_close_price * (1 - slippage)
                        commission = current_holding_shares * sell_price * commission_rate
                        profit_loss = (current_holding_shares * sell_price - (initial_capital - current_capital)) - commission
                        current_capital += (current_holding_shares * sell_price - commission)
                        trade_log = TradeLog(
                            running_strategy_id=running_strategy_id,
                            timestamp=latest_open_time,
                            trade_type="sell",
                            price=sell_price,
                            quantity=current_holding_shares,
                            commission=commission,
                            profit_loss=profit_loss
                        )
                        db.add(trade_log)
                        db.commit()
                        current_holding_shares = 0

                last_processed_time = latest_open_time

            current_equity = current_capital + current_holding_shares * latest_close_price
            equity_record = EquityCurve(
                running_strategy_id=running_strategy_id,
                timestamp=latest_open_time,
                equity=current_equity
            )
            db.add(equity_record)
            db.commit()

            time.sleep(5)

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Only attempt to set status to error if the record still exists and is not already stopped
        record_for_error_update = db.query(RunningStrategy).filter(RunningStrategy.id == running_strategy_id).first()
        if record_for_error_update and record_for_error_update.status != "stopped":
            try:
                record_for_error_update.status = "error"
                db.commit()
                print(f"STRATEGY_RUNNER: Strategy {saved_strategy_record.name} (ID: {saved_strategy_id}) set to 'error' due to exception.")
            except Exception as db_e:
                print(f"STRATEGY_RUNNER ERROR: Failed to update strategy status to 'error' in DB: {db_e}")
    finally:
        db.close()


@app.post("/strategies")
async def save_strategy(request: dict, db: Session = Depends(get_db)):
    strategy_name = request.get("name")
    strategy_code = request.get("code")
    symbol = request.get("symbol")
    currency = request.get("currency")
    interval = request.get("interval")
    initial_capital = request.get("initial_capital")
    commission_rate = request.get("commission_rate")
    slippage = request.get("slippage")
    risk_free_rate = request.get("risk_free_rate")
    github_owner = request.get("github_owner")
    github_repo = request.get("github_repo")

    if not strategy_name or not strategy_code:
        raise HTTPException(status_code=400, detail="Strategy name and code are required.")

    # Check if strategy name already exists
    existing_strategy = db.query(SavedStrategy).filter(SavedStrategy.name == strategy_name).first()
    if existing_strategy:
        raise HTTPException(status_code=409, detail="Strategy name already exists. Please choose a different name.")

    new_strategy = SavedStrategy(
        name=strategy_name,
        code=strategy_code,
        symbol=symbol,
        currency=currency,
        interval=interval,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage=slippage,
        risk_free_rate=risk_free_rate,
        github_owner=github_owner,
        github_repo=github_repo
    )
    db.add(new_strategy)
    db.commit()
    db.refresh(new_strategy)
    return {"message": "Strategy saved successfully!", "strategy_id": new_strategy.id}

@app.get("/strategies")
async def get_strategies(db: Session = Depends(get_db)):
    strategies = db.query(SavedStrategy).all()
    return strategies

@app.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    strategy = db.query(SavedStrategy).filter(SavedStrategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    # Check if there's a running strategy associated with this saved strategy
    running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
    if running_strategy:
        # If a running strategy exists, set its status to stopped so the process can exit gracefully
        if running_strategy.status != "stopped":
            running_strategy.status = "stopped"
            db.commit()
            print(f"DEBUG: Set running strategy {running_strategy.id} status to 'stopped' for deletion.")

        # Terminate the process if it's still running
        if running_strategy.id in running_strategy_processes:
            process = running_strategy_processes[running_strategy.id]
            if process.is_alive():
                process.terminate()
                # Wait for the process to actually terminate
                process.join(timeout=1) # Reduced timeout
                if process.is_alive():
                    print(f"WARNING: Process {process.pid} for strategy {running_strategy.id} did not terminate gracefully, attempting kill.")
                    os.kill(process.pid, 9) # Force kill
                    process.join(timeout=1) # Wait again after kill
                if process.is_alive():
                    print(f"ERROR: Process {process.pid} for strategy {running_strategy.id} is still alive after force kill.")
                del running_strategy_processes[running_strategy.id]
            else:
                print(f"DEBUG: Process for strategy {running_strategy.id} was already dead.")
                del running_strategy_processes[running_strategy.id]

        # Delete its associated trade logs and equity curves
        db.query(TradeLog).filter(TradeLog.running_strategy_id == running_strategy.id).delete()
        db.query(EquityCurve).filter(EquityCurve.running_strategy_id == running_strategy.id).delete()
        db.commit() # Commit deletions of related records
        # Then delete the running strategy itself
        db.delete(running_strategy)
        db.commit() # Commit the deletion of running_strategy before deleting saved_strategy
        print(f"DEBUG: Associated running strategy {running_strategy.id} and its logs/curves deleted.")

    db.delete(strategy)
    db.commit()
    return {"message": "Strategy deleted successfully!"}

@app.post("/strategies/{strategy_id}/start")
async def start_strategy(strategy_id: int, db: Session = Depends(get_db)):
    saved_strategy = db.query(SavedStrategy).filter(SavedStrategy.id == strategy_id).first()
    if not saved_strategy:
        raise HTTPException(status_code=404, detail="Saved strategy not found.")

    running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
    if running_strategy and running_strategy.status != "stopped":
        raise HTTPException(status_code=400, detail=f"Strategy is already {running_strategy.status}.")

    if not running_strategy:
        running_strategy = RunningStrategy(strategy_id=strategy_id, status="starting")
        db.add(running_strategy)
        db.commit()
        db.refresh(running_strategy)
    else:
        running_strategy.status = "starting"
        running_strategy.started_at = datetime.now()
        running_strategy.last_updated_at = datetime.now()
        db.commit()

    try:
        # Start the strategy in a separate process
        process = multiprocessing.Process(
            target=_run_live_strategy_process,
            args=(running_strategy.id, saved_strategy.id)
        )
        process.start()
        running_strategy_processes[running_strategy.id] = process
        # The PID will be updated by the _run_live_strategy_process itself
        return {"message": "Strategy started successfully!", "running_strategy_id": running_strategy.id, "pid": process.pid}
    except Exception as e:
        db.rollback()
        running_strategy.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to start strategy process: {e}")

@app.post("/strategies/{strategy_id}/stop")
async def stop_strategy(strategy_id: int, db: Session = Depends(get_db)):
    running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
    if not running_strategy:
        return {"message": "Strategy is already stopped or was not running."}

    if running_strategy.status != "stopped":
        running_strategy.status = "stopped"
        db.commit()
        print(f"DEBUG: Set running strategy {running_strategy.id} status to 'stopped'.")

        # Terminate the process if it's still running
        if running_strategy.id in running_strategy_processes:
            process = running_strategy_processes[running_strategy.id]
            if process.is_alive():
                process.terminate()
                process.join(timeout=5) # Give it some time to terminate
                if process.is_alive():
                    print(f"WARNING: Process {process.pid} for strategy {running_strategy.id} did not terminate gracefully.")
                del running_strategy_processes[running_strategy.id]
            else:
                print(f"DEBUG: Process for strategy {running_strategy.id} was already dead.")
                del running_strategy_processes[running_strategy.id]

        # Delete associated trade logs and equity curves first
        db.query(TradeLog).filter(TradeLog.running_strategy_id == running_strategy.id).delete()
        db.query(EquityCurve).filter(EquityCurve.running_strategy_id == running_strategy.id).delete()
        db.commit() # Commit deletions of related records

        return {"message": "Strategy stopped successfully!"}
    else:
        return {"message": "Strategy is already stopped."}

@app.get("/strategies/{strategy_id}/status")
async def get_strategy_status(strategy_id: int, db: Session = Depends(get_db)):
    running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
    if not running_strategy:
        return {"status": "stopped"}
    return {"status": running_strategy.status, "pid": running_strategy.pid, "started_at": running_strategy.started_at, "last_updated_at": running_strategy.last_updated_at}

@app.get("/strategies/{strategy_id}/trade_logs")
async def get_strategy_trade_logs(strategy_id: int, db: Session = Depends(get_db)):
    running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
    if not running_strategy:
        raise HTTPException(status_code=404, detail="Running strategy not found.")
    
    trade_logs = db.query(TradeLog).filter(TradeLog.running_strategy_id == running_strategy.id).order_by(TradeLog.timestamp).all()
    return trade_logs

@app.get("/strategies/{strategy_id}/equity_curve")
async def get_strategy_equity_curve(strategy_id: int, db: Session = Depends(get_db)):
    running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
    if not running_strategy:
        raise HTTPException(status_code=404, detail="Running strategy not found.")

    equity_curve = db.query(EquityCurve).filter(EquityCurve.running_strategy_id == running_strategy.id).order_by(EquityCurve.timestamp).all()
    return equity_curve

@app.get("/crypto_prices")
async def get_prices(
    symbol: str = "BTC",
    currency: str = "USDT",
    interval: str = "1h",
    start_date: str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
    end_date: str | None = None, # Modified: end_date can be None
    limit: int | None = None # New: limit the number of data points
):
    try:
        # Try parsing with datetime first, then date only
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")

        # If end_date is not provided, use current datetime
        if end_date is None:
            end_dt = datetime.now()
        else:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        df = get_crypto_prices(symbol, currency, start_dt, end_dt, interval, data_limit=limit)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found for the given parameters.")

        # Convert DataFrame to a list of dictionaries for JSON response
        # Ensure datetime objects are converted to string
        df.reset_index(names=['open_time'], inplace=True)
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
    # Directly run backtest
    symbol = request.get("symbol")
    currency = request.get("currency")
    interval = request.get("interval")
    start_date_str = request.get("start_date")
    end_date_str = request.get("end_date")
    strategy_code = request.get("strategy_code")
    strategy_name = request.get("strategy_name")
    initial_capital = request.get("initial_capital", 10000)
    commission_rate = request.get("commission_rate", 0.001)
    slippage = request.get("slippage", 0.0005)
    risk_free_rate = request.get("risk_free_rate", 0.02)
    github_owner = request.get("github_owner")
    github_repo = request.get("github_repo")

    try:
        # Try parsing with datetime first, then date only
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")

        try:
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")

        df = get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
        if df.empty:
            raise ValueError("No crypto data found for the given parameters.")

        if strategy_name == "commit_sma" and github_owner and github_repo:
            github_commits_df = get_github_commits(github_owner, github_repo, start_dt, end_dt, {})
            if github_commits_df.empty:
                print("WARNING: No GitHub commit data found for commit_sma strategy.")
            else:
                github_commits_count = github_commits_df.groupby(github_commits_df['date'].dt.floor('D')).size().reset_index(name='commit_count')
                github_commits_count.rename(columns={'date': 'open_time'}, inplace=True)
                github_commits_count.set_index('open_time', inplace=True)
                df = pd.merge(df, github_commits_count, left_index=True, right_index=True, how='left')
                df['commit_count'] = df['commit_count'].fillna(0)

        spec = importlib.util.spec_from_loader("temp_strategy_module", loader=None)
        temp_strategy_module = importlib.util.module_from_spec(spec)
        exec(strategy_code, temp_strategy_module.__dict__)

        if not hasattr(temp_strategy_module, 'generate_signal'):
            raise ValueError("Strategy code must contain a 'generate_signal' function.")

        df_with_signal = temp_strategy_module.generate_signal(df.copy())

        results = run_backtest(
            df_with_signal,
            initial_capital,
            commission_rate,
            slippage,
            risk_free_rate
        )

        for key, value in results['fig'].items():
            if isinstance(value, pd.Series):
                results['fig'][key] = {'index': value.index.strftime('%Y-%m-%d %H:%M:%S').tolist(), 'values': value.tolist()}

        return {"message": "Backtest completed successfully!", "status": "SUCCESS", "result": results}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")

# Removed /backtest_status/{task_id} as it's no longer needed without Celery