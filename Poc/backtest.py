import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def backtest_signals(df: pd.DataFrame,
                     initial_capital=100_000,
                     fee_rate=0.001,
                     leverage=1,
                     allow_short=True,
                     risk_free_rate=0.0,
                     annualization_factor=252,
                     plot=False):
    """
    Performs a backtest of trading signals.

    Args:
        df (pd.DataFrame): DataFrame containing 'close', 'signal', and 'timestamp' columns.
                           'timestamp' column is required for annual return and trade holding days calculation.
        initial_capital (int, optional): Initial capital for backtesting. Defaults to 100_000.
        fee_rate (float, optional): Transaction fee rate. Defaults to 0.001.
        leverage (int, optional): Leverage to apply. Defaults to 1.
        allow_short (bool, optional): Whether to allow short selling. Defaults to True.
        risk_free_rate (float, optional): Risk-free rate for Sharpe Ratio calculation. Defaults to 0.0.
        annualization_factor (int, optional): Factor to annualize Sharpe Ratio.
                                              Should match the number of data points in a year based on your data frequency.
                                              Defaults to 252 (for daily data).
        plot (bool, optional): Whether to plot the equity curve. Defaults to False.

    Returns:
        dict: A dictionary containing backtesting results.
    """
    
    df = df.copy().reset_index(drop=True)
    df["position"] = 0

    # === 建立部位 (向量化) ===
    # 初始化 position 欄位
    df["position"] = 0

    # 根據 signal 設定部位，對於不改變的部位，暫時設定為 NaN
    df.loc[df["signal"] == 1, "position"] = leverage  # 做多 + 槓桿
    if allow_short:
        df.loc[df["signal"] == -1, "position"] = -leverage  # 做空
    else:
        # 如果不允許做空，且 signal 為 -1，則出場 (position = 0)
        df.loc[df["signal"] == -1, "position"] = 0

    # 使用 forward fill 處理持續持倉的情況
    # 這裡需要特別處理，因為 signal=0 或其他值時，position 應該保持前一個狀態
    # 我們可以先將 signal=0 的地方設為 NaN，然後再 ffill
    # 但更直接的方式是，先處理 signal != 0 的情況，然後再 ffill
    # 為了確保 signal=0 時保持前一個部位，我們需要一個中間步驟
    
    # 創建一個臨時的部位欄位，只處理 signal != 0 的情況
    temp_position = pd.Series(np.nan, index=df.index)
    temp_position.loc[df["signal"] == 1] = leverage
    if allow_short:
        temp_position.loc[df["signal"] == -1] = -leverage
    else:
        temp_position.loc[df["signal"] == -1] = 0
    
    # 將初始部位設定為 0，然後向前填充
    df["position"] = temp_position.ffill().fillna(0)
    
    # 確保第一天的部位是 0 (如果沒有交易信號)
    df.loc[0, "position"] = 0
    
    # 處理 signal = 0 的情況，保持前一個部位
    # 由於 ffill 已經處理了，這裡可以簡化為：
    # 如果 signal 為 0，則 position 保持前一個值
    # 由於我們已經用 ffill 處理了，這裡不需要額外的邏輯
    # 只需要確保 signal=0 的地方沒有被 signal=1 或 -1 覆蓋
    # 實際上，ffill 已經會將 signal=0 的地方填充為前一個非 NaN 的值
    # 所以，如果 signal=0，且之前有部位，則會保持該部位
    # 如果 signal=0，且之前沒有部位 (NaN)，則會被 fillna(0) 填充為 0
    # 這樣就實現了 "持續持倉" 的邏輯。
    
    # 最終的 position 欄位已經包含了所有邏輯
    # df["position"] = df["position"].fillna(method='ffill').fillna(0) # 確保開頭沒有信號時為0
    # 上面的 ffill().fillna(0) 已經包含了這個邏輯
    
    # 舊的迴圈邏輯已移除，替換為向量化操作
    # for i in range(1, len(df)):
    #     signal = df.loc[i, "signal"]
    #     prev_pos = df.loc[i - 1, "position"]
    #     if signal == 1:
    #         df.loc[i, "position"] = leverage  # 做多 + 槓桿
    #     elif signal == -1 and allow_short:
    #         df.loc[i, "position"] = -leverage  # 做空
    #     elif signal == -1 and not allow_short:
    #         df.loc[i, "position"] = 0  # 出場
    #     else:
    #         df.loc[i, "position"] = prev_pos  # 持續持倉

    # === 報酬計算 ===
    df["return"] = df["close"].pct_change()
    df["strategy_return"] = df["return"] * df["position"].shift(1).fillna(0)

    # === 手續費 ===
    # 目前手續費計算是簡化模型，每次交易直接從報酬中扣除 fee_rate * abs(position)。
    # 如果 fee_rate 是基於交易金額的百分比，更精確的計算應考慮交易金額：
    # df.loc[df["trade"], "strategy_return_with_fee"] -= fee_rate * abs(df["position"] - df["position"].shift(1)) * df["close"] / df["close"].shift(1)
    df["trade"] = df["position"] != df["position"].shift(1)
    df["strategy_return_with_fee"] = df["strategy_return"]
    df.loc[df["trade"], "strategy_return_with_fee"] -= fee_rate * abs(df["position"])

    # === 資產曲線 ===
    df["equity"] = initial_capital * (1 + df["strategy_return_with_fee"]).cumprod()
    df["buy_and_hold"] = initial_capital * (1 + df["return"].fillna(0)).cumprod()

    # === 最大回撤 ===
    df["peak"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] / df["peak"] - 1
    max_drawdown = df["drawdown"].min()

    # === Sharpe Ratio ===
    daily_return = df["strategy_return_with_fee"].mean()
    daily_std = df["strategy_return_with_fee"].std()
    sharpe_ratio = (daily_return - risk_free_rate) / daily_std * np.sqrt(annualization_factor) if daily_std > 0 else 0

    # === 報酬統計 ===
    total_return = df["equity"].iloc[-1] / initial_capital - 1
    days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).days
    annual_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0

    # === 單筆交易統計 ===
    # 此部分由於需要追蹤每筆交易的進出場狀態，邏輯較為複雜，
    # 難以直接進行完全的向量化。如果此處成為效能瓶頸，
    # 可以考慮使用 Numba 等工具來加速 Python 迴圈。
    trade_returns = []
    hold_days = []
    entry_price = None
    entry_time = None
    entry_position = 0

    for i in range(len(df)):
        row = df.iloc[i]
        if row["trade"]:
            if entry_price is not None and entry_position != 0:
                # 注意：這裡的 exit_price 和 entry_price 的手續費計算方式
                # 與整體策略報酬的手續費計算方式 (df["strategy_return_with_fee"]) 可能不一致。
                # 整體策略報酬是直接從報酬中扣除 fee_rate * abs(position)，
                # 而這裡則是直接影響進出場價格。
                exit_price = row["close"] * (1 - fee_rate)
                if entry_position > 0:
                    rtn = (exit_price / entry_price) - 1
                else:
                    rtn = (entry_price / exit_price) - 1
                rtn *= leverage
                days_held = (row["timestamp"] - entry_time).days
                trade_returns.append(rtn)
                hold_days.append(days_held)

            # 新進場
            entry_price = row["close"] * (1 + fee_rate)
            entry_time = row["timestamp"]
            entry_position = row["position"]

    num_trades = len(trade_returns)
    win_rate = np.mean([1 if r > 0 else 0 for r in trade_returns]) if num_trades > 0 else 0
    avg_profit = np.mean(trade_returns) if num_trades > 0 else 0
    avg_days = np.mean(hold_days) if hold_days else 0


    return {
        "總報酬率": round(total_return * 100, 2),
        "年化報酬率": round(annual_return * 100, 2),
        "最大回撤": round(max_drawdown * 100, 2),
        "Sharpe Ratio": round(sharpe_ratio, 2),
        "交易次數": num_trades,
        "勝率": round(win_rate * 100, 2),
        "平均持有天數": round(avg_days, 2),
        "平均每筆報酬率": round(avg_profit * 100, 2),
        "timestamp": df["timestamp"].values,
        "equity": df["equity"].values,
        "buy_and_hold": df["buy_and_hold"].values.tolist(),
        "trade_returns": np.array(trade_returns) * 100,
        "close": df["close"].values,
        "signal": df["signal"].values,
        "position":df["position"].values,
    }

# 使用範例
if __name__ == '__main__':
    from Technicalindicatorstrategy.sma import get_signals
    from datetime import datetime
    # 範例使用：請確保 df_signals 包含 'timestamp' 欄位，且為 datetime 類型。
    # annualization_factor 應根據數據頻率設定，例如 15m 數據可能需要不同的因子。
    df_signals = get_signals("BTCUSDT", "15m", datetime.now())
    result = backtest_signals(df_signals, annualization_factor=365 * 24 * 4) # 假設 15m 數據，一年有 365*24*4 個週期
    print(result)