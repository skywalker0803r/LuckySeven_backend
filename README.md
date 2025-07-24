# LuckySeven_backend

This directory contains the backend services for the LuckySeven project. It is responsible for:
- **Data Fetching:** Retrieving data from sources like Binance and GitHub.
- **Strategy Management:** Implementing and managing various trading strategies (e.g., SMA, MACD, RSI).
- **Strategy Execution:** Running trading strategies.
- **Backtesting:** Providing functionality to backtest trading strategies against historical data.
- **Configuration:** Managing application settings.

Key components include:
- `app.py`: Main application entry point.
- `config.py`: Application configuration.
- `strategy_runner.py`: Executes trading strategies.
- `Datafetcher/`: Modules for fetching data.
- `Strategy/`: Contains different trading strategy implementations.
- `Backtest/`: Contains backtesting logic.