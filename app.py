from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import pandas as pd
import importlib.util
import sys
import os
import multiprocessing
import subprocess # For running external scripts
import psutil # For process management

# Import custom modules
from Datafetcher.binance_data_fetcher import get_crypto_prices, get_binance_trading_pairs
from Datafetcher.github_data_fetcher import get_github_commits # Import github_data_fetcher
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB # For storing JSON data

from Backtest.backtest import run_backtest

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DatabaseURL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set. Please create a .env file with DATABASE_URL.")

# SQLAlchemy Setup
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Database Model for Saved Strategies
class SavedStrategy(Base):
    __tablename__ = "saved_strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    code = Column(Text, nullable=False)
    symbol = Column(String)
    currency = Column(String)
    interval = Column(String)
    initial_capital = Column(Float)
    commission_rate = Column(Float)
    slippage = Column(Float)
    risk_free_rate = Column(Float)
    github_owner = Column(String, nullable=True)
    github_repo = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

# Database Model for Running Strategies
class RunningStrategy(Base):
    __tablename__ = "running_strategies"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("saved_strategies.id"), unique=True)
    pid = Column(Integer, nullable=True) # Process ID
    status = Column(String, default="stopped") # running, paused, stopped
    started_at = Column(DateTime, default=datetime.now)
    last_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# Database Model for Trade Logs
class TradeLog(Base):
    __tablename__ = "trade_logs"

    id = Column(Integer, primary_key=True, index=True)
    running_strategy_id = Column(Integer, ForeignKey("running_strategies.id"))
    timestamp = Column(DateTime, default=datetime.now)
    trade_type = Column(String) # "buy" or "sell"
    price = Column(Float)
    quantity = Column(Float)
    commission = Column(Float)
    profit_loss = Column(Float, nullable=True) # For sell trades

# Database Model for Equity Curve
class EquityCurve(Base):
    __tablename__ = "equity_curves"

    id = Column(Integer, primary_key=True, index=True)
    running_strategy_id = Column(Integer, ForeignKey("running_strategies.id"))
    timestamp = Column(DateTime, default=datetime.now)
    equity = Column(Float)

# Create tables if they don't exist
Base.metadata.create_all(engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

app = FastAPI()

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://luckyseven-frontend.onrender.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

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

    # Start the strategy in a new process
    # We use subprocess.Popen to detach the process from the main FastAPI process
    # This is a simplified approach. For production, consider a proper task queue (e.g., Celery)
    try:
        # Get the path to the Python executable in the current environment
        python_executable = sys.executable
        
        # Construct the command to run strategy_runner.py
        command = [
            python_executable,
            os.path.join(os.path.dirname(__file__), "strategy_runner.py"),
            str(running_strategy.id),
            str(saved_strategy.id)
        ]
        
        # Start the subprocess
        # Use creationflags for Windows to create a new console window (DETACHED_PROCESS)
        # For Linux/macOS, it will run in the background by default
        if sys.platform == "win32":
            process = subprocess.Popen(command, creationflags=subprocess.DETACHED_PROCESS)
        else:
            process = subprocess.Popen(command, preexec_fn=os.setsid) # Detach for Unix-like systems

        running_strategy.pid = process.pid
        running_strategy.status = "running"
        db.commit()
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
        # If the running_strategy record is not found, it means the strategy is already stopped or was never running.
        # In this case, we can consider the stop request successful.
        return {"message": "Strategy is already stopped or was not running."}

    if running_strategy.status != "stopped":
        running_strategy.status = "stopped"
        db.commit()

        if running_strategy.pid:
            try:
                process = psutil.Process(running_strategy.pid)
                # Terminate the process and its children
                for proc in process.children(recursive=True):
                    proc.terminate()
                process.terminate() # Terminate the parent process
                gone, alive = psutil.wait_procs(process.children() + [process], timeout=3)
                if alive:
                    for p in alive:
                        p.kill() # Force kill if not terminated
                print(f"Process {running_strategy.pid} and its children terminated.")
            except psutil.NoSuchProcess:
                print(f"Process {running_strategy.pid} not found, likely already terminated.")
            except Exception as e:
                print(f"Error terminating process {running_strategy.pid}: {e}")
        
        db.delete(running_strategy)
        try:
            db.commit()
            print(f"DEBUG: Running strategy record {running_strategy.id} deleted successfully.")
        except Exception as e:
            db.rollback()
            print(f"ERROR: Failed to commit deletion of running strategy record {running_strategy.id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete running strategy record: {e}")
        return {"message": "Strategy stopped and removed successfully!"}
    else:
        # If status is already "stopped", return success.
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
