import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

    def _parse_date(self, date_str: str) -> datetime:
        """Attempts to parse a date string from various formats."""
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Date string '{date_str}' does not match any expected format.")

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
            start_dt = self._parse_date(start_date_str)
            end_dt = self._parse_date(end_date_str)

            df = self.data_service.get_crypto_prices(symbol, currency, start_dt, end_dt, interval)
            if df.empty:
                raise DataNotFoundException("No crypto data found for the given parameters.")

            if strategy_name == "commit_sma" and github_owner and github_repo:
                github_commits_df = self.data_service.get_github_commits(github_owner, github_repo, start_dt, end_dt, {})
                if github_commits_df.empty:
                    logger.warning("No GitHub commit data found for commit_sma strategy.")
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
            logger.error(f"An unexpected error occurred during backtest: {e}", exc_info=True)
            raise BacktestFailedException(detail=f"Backtest failed: {e}")

misc_service = MiscService()