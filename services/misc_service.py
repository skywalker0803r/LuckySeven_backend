from fastapi import HTTPException
import os
import importlib.util
from datetime import datetime
import pandas as pd
import traceback

from Backtest.backtest import run_backtest
from services.data_service import DataService
from exceptions import DataNotFoundException, InvalidDateFormatException, MissingSignalFunctionException, BacktestFailedException

class MiscService:
    def __init__(self):
        self.data_service = DataService()

    def get_strategy_list(self):
        strategy_dir = "Strategy"
        strategies = []
        for filename in os.listdir(strategy_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                strategies.append(filename[:-3]) # Remove .py extension
        return {"strategies": strategies}

    def get_strategy_code(self, strategy_name: str):
        strategy_path = os.path.join("Strategy", f"{strategy_name}.py")
        if not os.path.exists(strategy_path):
            raise HTTPException(status_code=404, detail="Strategy not found.")
        with open(strategy_path, "r", encoding="utf-8") as f:
            code = f.read()
        return {"code": code}

    def run_backtest(
        self,
        symbol: str,
        currency: str,
        interval: str,
        start_date_str: str,
        end_date_str: str,
        strategy_code: str,
        strategy_name: str,
        initial_capital: float,
        commission_rate: float,
        slippage: float,
        risk_free_rate: float,
        github_owner: str | None,
        github_repo: str | None
    ):
        try:
            try:
                start_dt = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise InvalidDateFormatException(detail=f"Invalid start_date format: {start_date_str}. Please use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.")

            try:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise InvalidDateFormatException(detail=f"Invalid end_date format: {end_date_str}. Please use YYYY-MM-DD or YYYY-MM-DD HH:MM:S.")

            df = self.data_service.get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
            if df.empty:
                raise DataNotFoundException("No crypto data found for the given parameters.")

            if strategy_name == "commit_sma" and github_owner and github_repo:
                github_commits_df = self.data_service.get_github_commits(github_owner, github_repo, start_dt, end_dt, {})
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
                raise MissingSignalFunctionException()

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
        except HTTPException as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise BacktestFailedException(detail=f"Backtest failed: {e}")

misc_service = MiscService()