from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta
import multiprocessing
import time
import importlib.util
import os
import pandas as pd
import traceback

from database import SessionLocal, SavedStrategy, RunningStrategy, TradeLog, EquityCurve
from services.data_service import DataService
from exceptions import (
    StrategyNotFoundException,
    StrategyAlreadyRunningException,
    StrategyCodeMissingException,
    StrategyNameExistsException,
    MissingSignalFunctionException
)

class StrategyService:
    def __init__(self):
        self.running_strategy_processes = {}
        self.data_service = DataService()

    def _run_live_strategy_process(self, running_strategy_id: int, saved_strategy_id: int):
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
                raise MissingSignalFunctionException()

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

                df = self.data_service.get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
                print(f"STRATEGY_RUNNER DEBUG: Received {len(df)} klines for strategy calculation.")
                if df.empty:
                    print(f"STRATEGY_RUNNER WARNING: No crypto data fetched for {symbol}{currency}. Retrying in 60 seconds.")
                    time.sleep(60)
                    continue

                if saved_strategy_record.name == "commit_sma" and github_owner and github_repo:
                    github_commits_df = self.data_service.get_github_commits(github_owner, github_repo, start_dt, end_dt, {})
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

                current_equity = current_capital + current_holding_shares * latest_close_price
                equity_record = EquityCurve(
                    running_strategy_id=running_strategy_id,
                    timestamp=latest_open_time,
                    equity=current_equity
                )
                db.add(equity_record)
                db.commit()

                last_processed_time = latest_open_time

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

    def start_strategy(self, strategy_id: int, db: Session):
        saved_strategy = db.query(SavedStrategy).filter(SavedStrategy.id == strategy_id).first()
        if not saved_strategy:
            raise StrategyNotFoundException(strategy_id=strategy_id)

        running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
        if running_strategy and running_strategy.status != "stopped":
            raise StrategyAlreadyRunningException(strategy_id=strategy_id, status=running_strategy.status)

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
                target=self._run_live_strategy_process,
                args=(running_strategy.id, saved_strategy.id)
            )
            process.start()
            self.running_strategy_processes[running_strategy.id] = process
            # The PID will be updated by the _run_live_strategy_process itself
            return {"message": "Strategy started successfully!", "running_strategy_id": running_strategy.id, "pid": process.pid}
        except Exception as e:
            db.rollback()
            # Only attempt to set status to error if the record still exists and is not already stopped
            record_for_error_update = db.query(RunningStrategy).filter(RunningStrategy.id == running_strategy.id).first()
            if record_for_error_update and record_for_error_update.status != "stopped":
                try:
                    record_for_error_update.status = "error"
                    db.commit()
                    print(f"STRATEGY_RUNNER: Strategy {saved_strategy.name} (ID: {saved_strategy.id}) set to 'error' due to exception during start.")
                except Exception as db_e:
                    print(f"STRATEGY_RUNNER ERROR: Failed to update strategy status to 'error' in DB: {db_e}")
            raise HTTPException(status_code=500, detail=f"Failed to start strategy process: {e}")

    def stop_strategy(self, strategy_id: int, db: Session):
        running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
        if not running_strategy:
            return {"message": "Strategy is already stopped or was not running."}

        if running_strategy.status != "stopped":
            running_strategy.status = "stopped"
            db.commit()
            print(f"DEBUG: Set running strategy {running_strategy.id} status to 'stopped'.")

            # Terminate the process if it's still running
            if running_strategy.id in self.running_strategy_processes:
                process = self.running_strategy_processes[running_strategy.id]
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5) # Give it some time to terminate
                    if process.is_alive():
                        print(f"WARNING: Process {process.pid} for strategy {running_strategy.id} did not terminate gracefully.")
                    del self.running_strategy_processes[running_strategy.id]
                else:
                    print(f"DEBUG: Process for strategy {running_strategy.id} was already dead.")
                    del self.running_strategy_processes[running_strategy.id]

            # Delete associated trade logs and equity curves first
            db.query(TradeLog).filter(TradeLog.running_strategy_id == running_strategy.id).delete()
            db.query(EquityCurve).filter(EquityCurve.running_strategy_id == running_strategy.id).delete()
            db.commit() # Commit deletions of related records

            return {"message": "Strategy stopped successfully!"}
        else:
            return {"message": "Strategy is already stopped."}

    def delete_strategy(self, strategy_id: int, db: Session):
        strategy = db.query(SavedStrategy).filter(SavedStrategy.id == strategy_id).first()
        if not strategy:
            raise StrategyNotFoundException(strategy_id=strategy_id)
        # Check if there's a running strategy associated with this saved strategy
        running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
        if running_strategy:
            # If a running strategy exists, set its status to stopped so the process can exit gracefully
            if running_strategy.status != "stopped":
                running_strategy.status = "stopped"
                db.commit()
                print(f"DEBUG: Set running strategy {running_strategy.id} status to 'stopped' for deletion.")

            # Terminate the process if it's still running
            if running_strategy.id in self.running_strategy_processes:
                process = self.running_strategy_processes[running_strategy.id]
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
                    del self.running_strategy_processes[running_strategy.id]
                else:
                    print(f"DEBUG: Process for strategy {running_strategy.id} was already dead.")
                    del self.running_strategy_processes[running_strategy.id]

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

    def get_strategy_status(self, strategy_id: int, db: Session):
        running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
        if not running_strategy:
            return {"status": "stopped"}
        return {"status": running_strategy.status, "pid": running_strategy.pid, "started_at": running_strategy.started_at, "last_updated_at": running_strategy.last_updated_at}

    def get_strategy_trade_logs(self, strategy_id: int, db: Session):
        running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
        if not running_strategy:
            raise StrategyNotFoundException(strategy_id=strategy_id)
        
        trade_logs = db.query(TradeLog).filter(TradeLog.running_strategy_id == running_strategy.id).order_by(TradeLog.timestamp).all()
        return trade_logs

    def get_strategy_equity_curve(self, strategy_id: int, db: Session):
        running_strategy = db.query(RunningStrategy).filter(RunningStrategy.strategy_id == strategy_id).first()
        if not running_strategy:
            raise StrategyNotFoundException(strategy_id=strategy_id)

        equity_curve = db.query(EquityCurve).filter(EquityCurve.running_strategy_id == running_strategy.id).order_by(EquityCurve.timestamp).all()
        return equity_curve

    def save_strategy(self, request: dict, db: Session):
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
            raise StrategyCodeMissingException()

        # Check if strategy name already exists
        existing_strategy = db.query(SavedStrategy).filter(SavedStrategy.name == strategy_name).first()
        if existing_strategy:
            raise StrategyNameExistsException(strategy_name=strategy_name)

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

    def get_strategies(self, db: Session):
        strategies = []
        # Eager load running_strategy to avoid N+1 queries for status
        saved_strategies = db.query(SavedStrategy).options(joinedload(SavedStrategy.running_strategy)).all()

        for saved_strategy in saved_strategies:
            strategy_data = saved_strategy.__dict__.copy()
            strategy_data.pop('_sa_instance_state', None) # Remove SQLAlchemy internal state

            running_strategy = saved_strategy.running_strategy # Access the eagerly loaded running_strategy
            
            trade_count = 0
            total_profit_loss = 0.0
            equity_curve_data = []
            current_status = "stopped" # Default status

            if running_strategy:
                current_status = running_strategy.status # Get status from eagerly loaded object
                
                # Fetch trade logs and equity curve data for the specific running_strategy
                trade_logs = db.query(TradeLog).filter(TradeLog.running_strategy_id == running_strategy.id).all()
                trade_count = len(trade_logs)
                total_profit_loss = sum(log.profit_loss for log in trade_logs if log.trade_type == 'sell' and log.profit_loss is not None)

                equity_records = db.query(EquityCurve).filter(EquityCurve.running_strategy_id == running_strategy.id).order_by(EquityCurve.timestamp.desc()).limit(100).all()
                equity_curve_data = [[record.timestamp.isoformat(), record.equity] for record in reversed(equity_records)]
            
            strategy_data['trade_count'] = trade_count
            strategy_data['total_profit_loss'] = round(total_profit_loss, 2)
            strategy_data['equity_curve_data'] = equity_curve_data
            strategy_data['status'] = current_status # Add status to the returned data
            
            strategies.append(strategy_data)
        return strategies

strategy_service = StrategyService()
