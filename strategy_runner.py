import time
import pandas as pd
from datetime import datetime, timedelta
import importlib.util
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey

# Import custom modules
from Datafetcher.binance_data_fetcher import get_crypto_prices
from Datafetcher.github_data_fetcher import get_github_commits

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

# SQLAlchemy Setup (re-use models from app.py for consistency)
Base = declarative_base()

class SavedStrategy(Base):
    __tablename__ = "saved_strategies"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    code = Column(Text)
    symbol = Column(String)
    currency = Column(String)
    interval = Column(String)
    initial_capital = Column(Float)
    commission_rate = Column(Float)
    slippage = Column(Float)
    risk_free_rate = Column(Float)
    github_owner = Column(String, nullable=True)
    github_repo = Column(String, nullable=True)

class RunningStrategy(Base):
    __tablename__ = "running_strategies"
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey("saved_strategies.id"))
    pid = Column(Integer)
    status = Column(String)
    started_at = Column(DateTime)
    last_updated_at = Column(DateTime)

class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True)
    running_strategy_id = Column(Integer, ForeignKey("running_strategies.id"))
    timestamp = Column(DateTime)
    trade_type = Column(String) # "buy" or "sell"
    price = Column(Float)
    quantity = Column(Float)
    commission = Column(Float)
    profit_loss = Column(Float, nullable=True)

class EquityCurve(Base):
    __tablename__ = "equity_curves"
    id = Column(Integer, primary_key=True)
    running_strategy_id = Column(Integer, ForeignKey("running_strategies.id"))
    timestamp = Column(DateTime)
    equity = Column(Float)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
        # Default to a safe large period if interval is unknown or very long
        print(f"Warning: Unknown interval '{interval}'. Defaulting to 365 days lookback.")
        return end_dt - timedelta(days=365) # 1 year of data

def run_strategy_in_process(running_strategy_id: int, saved_strategy_id: int):
    db = SessionLocal()
    try:
        print(f"STRATEGY_RUNNER: Starting process for running_strategy_id={running_strategy_id}, saved_strategy_id={saved_strategy_id}")
        running_strategy_record = db.query(RunningStrategy).filter(RunningStrategy.id == running_strategy_id).first()
        if not running_strategy_record:
            print(f"STRATEGY_RUNNER ERROR: Running strategy record {running_strategy_id} not found.")
            return

        saved_strategy_record = db.query(SavedStrategy).filter(SavedStrategy.id == saved_strategy_id).first()
        if not saved_strategy_record:
            print(f"STRATEGY_RUNNER ERROR: Saved strategy record {saved_strategy_id} not found.")
            return

        # Update PID and status
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

        # Dynamically load strategy code
        spec = importlib.util.spec_from_loader("live_strategy_module", loader=None)
        live_strategy_module = importlib.util.module_from_spec(spec)
        exec(strategy_code, live_strategy_module.__dict__)

        if not hasattr(live_strategy_module, 'generate_signal'):
            print("STRATEGY_RUNNER ERROR: Strategy code must contain a 'generate_signal' function.")
            running_strategy_record.status = "error"
            db.commit()
            return

        # Determine lookback periods based on strategy definition or default
        lookback_periods = getattr(live_strategy_module, 'REQUIRED_LOOKBACK_PERIODS', 1000)

        # --- Live Trading Loop ---
        current_capital = initial_capital
        current_holding_shares = 0
        last_processed_time = None # To track last fetched data point

        while True:
            db.refresh(running_strategy_record) # Get latest status from DB
            if running_strategy_record.status == "stopped":
                print(f"STRATEGY_RUNNER: Strategy {saved_strategy_record.name} (ID: {saved_strategy_id}) stopped by user. Exiting loop.")
                break

            print(f"STRATEGY_RUNNER: Fetching data for {symbol}{currency} at {datetime.now()} for strategy {saved_strategy_record.name} (ID: {saved_strategy_id})...")
            end_dt = datetime.now()
            start_dt = calculate_start_dt(end_dt, interval, lookback_periods)

            df = get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
            if df.empty:
                print(f"STRATEGY_RUNNER WARNING: No crypto data fetched for {symbol}{currency}. Retrying in 60 seconds.")
                time.sleep(60)
                continue
            print(f"STRATEGY_RUNNER: Successfully fetched {len(df)} crypto data points.")

            # Handle GitHub commit data if applicable
            if saved_strategy_record.name == "commit_sma" and github_owner and github_repo:
                github_commits_df = get_github_commits(github_owner, github_repo, start_dt, end_dt, GITHUB_HEADERS)
                if github_commits_df.empty:
                    print("STRATEGY_RUNNER WARNING: No GitHub commit data fetched. Strategy might not work as expected.")
                else:
                    github_commits_count = github_commits_df.groupby(github_commits_df['date'].dt.floor('D')).size().reset_index(name='commit_count')
                    github_commits_count.rename(columns={'date': 'open_time'}, inplace=True)
                    github_commits_count.set_index('open_time', inplace=True)
                    df = pd.merge(df, github_commits_count, left_index=True, right_index=True, how='left')
                    df['commit_count'] = df['commit_count'].fillna(0)
                    print(f"STRATEGY_RUNNER: Merged {len(github_commits_df)} GitHub commit data points.")

            # Generate signal
            df_with_signal = live_strategy_module.generate_signal(df.copy())
            latest_signal_row = df_with_signal.iloc[-1]
            latest_signal = latest_signal_row['signal']
            latest_close_price = latest_signal_row['close']
            latest_open_time = df_with_signal.index[-1]

            # Only process new signals
            if last_processed_time is None or latest_open_time > last_processed_time:
                print(f"STRATEGY_RUNNER: New signal generated at {latest_open_time}: {latest_signal}")
                # --- Simulate Trading (Replace with actual Binance API calls) ---
                if latest_signal == 1: # Buy signal
                    if current_holding_shares == 0: # Only buy if not holding
                        buy_price = latest_close_price * (1 + slippage)
                        shares_to_buy = (current_capital / (buy_price * (1 + commission_rate)))
                        if shares_to_buy > 0:
                            commission = shares_to_buy * buy_price * commission_rate
                            current_capital -= (shares_to_buy * buy_price + commission)
                            current_holding_shares += shares_to_buy
                            print(f"STRATEGY_RUNNER BUY: {shares_to_buy:.4f} {symbol} at {buy_price:.2f}. Remaining capital: {current_capital:.2f}")
                            # Log trade
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
                            print(f"STRATEGY_RUNNER: Trade log (BUY) committed for running_strategy_id={running_strategy_id}.")

                elif latest_signal == -1: # Sell signal
                    if current_holding_shares > 0: # Only sell if holding
                        sell_price = latest_close_price * (1 - slippage)
                        commission = current_holding_shares * sell_price * commission_rate
                        profit_loss = (current_holding_shares * sell_price - (initial_capital - current_capital)) - commission # Simplified P/L
                        current_capital += (current_holding_shares * sell_price - commission)
                        print(f"STRATEGY_RUNNER SELL: {current_holding_shares:.4f} {symbol} at {sell_price:.2f}. Total capital: {current_capital:.2f}")
                        # Log trade
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
                        print(f"STRATEGY_RUNNER: Trade log (SELL) committed for running_strategy_id={running_strategy_id}.")
                        current_holding_shares = 0 # Clear holding

                # Update equity curve
                current_equity = current_capital + current_holding_shares * latest_close_price
                equity_record = EquityCurve(
                    running_strategy_id=running_strategy_id,
                    timestamp=latest_open_time,
                    equity=current_equity
                )
                db.add(equity_record)
                db.commit()
                print(f"STRATEGY_RUNNER: Equity curve committed for running_strategy_id={running_strategy_id}. Equity: {current_equity:.2f}")

                last_processed_time = latest_open_time

            time.sleep(60) # Check every 60 seconds (adjust based on interval)

    except Exception as e:
        print(f"STRATEGY_RUNNER CRITICAL ERROR for strategy {saved_strategy_record.name} (ID: {saved_strategy_id}): {e}")
        import traceback
        traceback.print_exc()
        if running_strategy_record:
            running_strategy_record.status = "error"
            db.commit()
    finally:
        db.close()
        print(f"STRATEGY_RUNNER: Strategy {saved_strategy_record.name} (ID: {saved_strategy_id}) process finished.")

if __name__ == "__main__":
    # This part is for testing the runner directly
    # In production, this will be called by multiprocessing.Process
    if len(sys.argv) > 2:
        running_strategy_id = int(sys.argv[1])
        saved_strategy_id = int(sys.argv[2])
        run_strategy_in_process(running_strategy_id, saved_strategy_id)
    else:
        print("Usage: python strategy_runner.py <running_strategy_id> <saved_strategy_id>")