import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm

def plot_result(result):
    price = result['fig']['價格序列']
    signal = result['fig']['買賣點序列'] # 現在這個signal會是實際交易點
    strategy_equity = result['fig']['策略資產曲線序列']
    buyhold_equity = result['fig']['買入持有資產曲線序列']
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    # 上圖：價格 + 買賣點
    axes[0].plot(price, label='Price', color='black')
    axes[0].scatter(signal[signal > 0].index, price[signal > 0], label='Buy', marker='^', color='green')
    axes[0].scatter(signal[signal < 0].index, price[signal < 0], label='v', color='red') # 修改了 marker 顯示為紅色倒三角
    axes[0].set_title('Price and Actual Trade Points') # 修改標題
    axes[0].legend()

    # 下圖：策略 vs Buy&Hold
    axes[1].plot(strategy_equity, label='Strategy', color='blue')
    axes[1].plot(buyhold_equity, label='Buy & Hold', color='gray')
    axes[1].set_title('Equity Curve')
    axes[1].legend()
    plt.tight_layout()
    plt.show()

def run_backtest(df: pd.DataFrame, initial_capital: float, commission_rate: float = 0.001, slippage: float = 0.0005, risk_free_rate: float = 0.02) -> dict:
    """
    根據給定的收盤價和交易訊號進行回測，並計算多項績效指標。
    並返回資產報酬曲線序列、價格序列和實際交易買賣點序列。

    Args:
        df (pd.DataFrame): 包含 'close' 和 'signal' 欄位的 DataFrame。
                          'close' 為收盤價序列，'signal' 為交易訊號 (-1: 賣出, 0: 不動作, 1: 買進)。
        initial_capital (float): 初始資金。
        commission_rate (float): 交易手續費率 (預設為 0.001，即 0.1%)。
        slippage (float): 交易滑點率 (預設為 0.0005，即 0.05%)。
        risk_free_rate (float): 無風險利率 (預設為 0.02，用於夏普率計算)。

    Returns:
        dict: 包含多項回測結果指標的字典，以及繪圖所需的序列數據。
    """

    # 確保必要的欄位存在
    if 'close' not in df.columns or 'signal' not in df.columns:
        raise ValueError("DataFrame 必須包含 'close' 和 'signal' 欄位。")

    capital = initial_capital
    
    # 策略資產曲線，初始值為初始資金，後續記錄每天結束時的資產淨值
    strategy_equity_curve = [initial_capital]
    
    total_commission = 0
    
    # 用於追蹤單筆交易盈虧的詳細記錄
    detailed_trades = []
    current_holding_cost = 0 # 當前持倉的總成本 (用於計算平均成本)
    current_holding_shares = 0 # 當前持倉的總股數
    current_holding_start_index = -1 # 紀錄目前持有部位的起始索引

    # 新增：用於記錄實際交易點的序列，初始化為0
    actual_trade_signal = pd.Series(0, index=df.index, dtype=int)


    # 迴圈遍歷每一天的數據
    for i in tqdm(range(len(df))):
        current_close = df['close'].iloc[i]
        signal = df['signal'].iloc[i]

        # 買入訊號
        if signal == 1:
            if current_holding_shares == 0:  # 只有在沒有持倉時才買入
                buy_price = current_close * (1 + slippage)
                # 買入所有可用資金，計算可買入的股數
                buyable_shares = (capital / (buy_price * (1 + commission_rate)))
                
                if buyable_shares > 0:
                    shares_to_buy = buyable_shares
                    commission = shares_to_buy * buy_price * commission_rate
                    capital -= (shares_to_buy * buy_price + commission)
                    
                    current_holding_cost = shares_to_buy * buy_price # 記錄買入成本
                    current_holding_shares = shares_to_buy
                    total_commission += commission
                    current_holding_start_index = i # 更新持有開始索引
                    actual_trade_signal.iloc[i] = 1 # 記錄實際買入點


        # 賣出訊號
        elif signal == -1:
            if current_holding_shares > 0:  # 只有在有持倉時才賣出
                sell_price = current_close * (1 - slippage)
                commission = current_holding_shares * sell_price * commission_rate
                
                capital_gain = (current_holding_shares * sell_price - current_holding_cost) - commission # 計算實現利潤
                
                detailed_trades.append({
                    'entry_price': current_holding_cost / current_holding_shares if current_holding_shares > 0 else np.nan, # 平均買入成本
                    'exit_price': sell_price,
                    'profit_loss': capital_gain,
                    'holding_period': i - current_holding_start_index
                })
                total_commission += commission
                capital += (current_holding_shares * sell_price - commission) # 更新資金
                current_holding_shares = 0 # 清空持倉
                current_holding_cost = 0 # 清空成本
                current_holding_start_index = -1 # 重置持有開始索引
                actual_trade_signal.iloc[i] = -1 # 記錄實際賣出點
        
        # 紀錄每日結束時的資產淨值
        current_total_asset = capital + current_holding_shares * current_close
        strategy_equity_curve.append(current_total_asset)


    # 最後一天的資產結算 (如果還有持倉，需要清算)
    if current_holding_shares > 0:
        final_sell_price = df['close'].iloc[-1] * (1 - slippage)
        final_commission = current_holding_shares * final_sell_price * commission_rate
        capital_gain = (current_holding_shares * final_sell_price - current_holding_cost) - final_commission
        
        detailed_trades.append({
            'entry_price': current_holding_cost / current_holding_shares if current_holding_shares > 0 else np.nan,
            'exit_price': final_sell_price,
            'profit_loss': capital_gain,
            'holding_period': len(df) - 1 - current_holding_start_index
        })
        total_commission += final_commission
        capital += (current_holding_shares * final_sell_price - final_commission)
        actual_trade_signal.iloc[-1] = -1 # 記錄最後一次清倉的賣出點
    
    # 更新最後的總資產
    final_asset = capital + current_holding_shares * df['close'].iloc[-1]
    # 因為 strategy_equity_curve 在迴圈中已經多append了一次，最後清倉時應該更新最後一個值
    # 如果最後有清倉，則strategy_equity_curve的最後一個值可能需要調整為最終資產
    if len(strategy_equity_curve) == len(df) + 1: # 如果在迴圈中已經append了 len(df) + 1 次
        strategy_equity_curve[-1] = final_asset # 更新為最終實際資產

    # --- 回測結果計算 ---

    # 1. 策略總報酬率
    strategy_total_return = (final_asset / initial_capital) - 1

    # 2. 單純買進持有策略的總報酬率
    # 買入持有資產曲線
    buy_and_hold_equity_curve = [initial_capital * (df['close'].iloc[i] / df['close'].iloc[0]) for i in range(len(df))]
    buy_and_hold_return = (buy_and_hold_equity_curve[-1] / initial_capital) - 1
    
    # 3. 淨值曲線 (用於最大回撤和夏普率)
    equity_curve_series = pd.Series(strategy_equity_curve, index=[df.index[0]] + list(df.index)) # 加上初始資金的時間點
    
    # 4. 最大回撤 (Maximum Drawdown)
    peak = equity_curve_series.expanding(min_periods=1).max()
    drawdown = (equity_curve_series / peak) - 1
    max_drawdown = drawdown.min()

    # 5. 夏普率 (Sharpe Ratio)
    returns = equity_curve_series.pct_change().dropna()
    if len(returns) > 0:
        annualization_factor = np.sqrt(252) # 假設交易日為 252 天
        excess_returns = returns - (risk_free_rate / annualization_factor**2) # 將無風險利率日化
        sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * annualization_factor
    else:
        sharpe_ratio = np.nan 

    # 重新計算相關指標 (基於 detailed_trades)
    total_trades = len(detailed_trades)
    winning_trades = [t for t in detailed_trades if t['profit_loss'] > 0]
    losing_trades = [t for t in detailed_trades if t['profit_loss'] < 0]

    win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0

    total_profit = sum(t['profit_loss'] for t in winning_trades)
    total_loss = sum(abs(t['profit_loss']) for t in losing_trades)

    profit_factor = total_profit / total_loss if total_loss > 0 else (np.inf if total_profit > 0 else 0)

    average_trade_profit = sum(t['profit_loss'] for t in detailed_trades) / total_trades if total_trades > 0 else 0

    max_single_profit = max([t['profit_loss'] for t in detailed_trades]) if detailed_trades else 0
    max_single_loss = min([t['profit_loss'] for t in detailed_trades]) if detailed_trades else 0

    average_holding_period = np.mean([t['holding_period'] for t in detailed_trades]) if detailed_trades else 0


    results = {
        
        # 指標
        "metrics":{
        "策略總報酬率": f"{strategy_total_return:.2%}",
        "最終資產": f"${final_asset:,.2f}",
        "最大回撤": f"{max_drawdown:.2%}",
        "夏普率": f"{sharpe_ratio:.2f}",
        "總交易次數": total_trades,
        "勝率": f"{win_rate:.2%}",
        "Profit Factor": f"{profit_factor:.2f}",
        "總手續費": f"${total_commission:,.2f}",
        "平均持有週期 (K棒數)": f"{average_holding_period:.2f}",
        "平均交易獲利": f"${average_trade_profit:,.2f}",
        "最大單筆獲利": f"${max_single_profit:,.2f}",
        "最大單筆虧損": f"${max_single_loss:,.2f}",
        "單純買進持有策略的總報酬率": f"{buy_and_hold_return:.2%}",
        },
        
        # 圖表
        "fig":{
        "策略資產曲線序列": pd.Series(strategy_equity_curve, index=[df.index[0]] + list(df.index)), # 加上起始日的初始資金
        "買入持有資產曲線序列": pd.Series(buy_and_hold_equity_curve, index=df.index),
        "價格序列": df['close'],
        "買賣點序列": actual_trade_signal # 將這裡替換為實際交易點序列
        }
    }

    return results