import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def plot_backtest_result(result):
    timestamp = pd.to_datetime(result["timestamp"])
    close = result["close"]
    equity = result["equity"]
    buy_and_hold = result["buy_and_hold"]
    trade_returns = result["trade_returns"]
    buy_sell = result.get("buy_sell_points", np.zeros_like(close))
    position = result.get("position", np.zeros_like(close))

    fig, axs = plt.subplots(3, 1, figsize=(14, 10), gridspec_kw={"height_ratios": [2, 2, 1]})

    # === 圖1：策略資產曲線 ===
    axs[0].plot(timestamp, equity, label="Strategy")
    axs[0].plot(timestamp, buy_and_hold, label="Buy and Hold", linestyle="--", alpha=0.6)
    axs[0].set_title("Equity Curve")
    axs[0].legend()
    axs[0].grid()

    # === 圖2：收盤價 + 買賣點 + 持倉顏色 ===
    # === 圖2：收盤價 + 買賣點 + 持倉顏色 ===
    # 根據持倉變化繪製不同顏色的收盤價曲線
    # 找到持倉變化的點
    position_changes = np.where(np.diff(position) != 0)[0] + 1
    # 在數據的開始和結束點也加入，以確保繪製完整
    split_points = np.concatenate(([0], position_changes, [len(timestamp)]))

    for i in range(len(split_points) - 1):
        start_idx = split_points[i]
        end_idx = split_points[i+1]
        
        # 確保索引範圍有效
        if start_idx >= len(timestamp) or end_idx > len(timestamp) or start_idx == end_idx:
            continue

        # 獲取該區間的持倉狀態
        # 使用 start_idx 處的 position 來決定顏色，因為這是該區間的起始持倉
        current_position = position[start_idx]
        
        color = "green" if current_position > 0 else "red" if current_position < 0 else "gray"
        
        # 繪製該區間的價格線
        # 為了確保線段連續，需要包含 end_idx 點
        axs[1].plot(timestamp[start_idx:end_idx+1], close[start_idx:end_idx+1], color=color, linewidth=1.5)

    # 畫出買賣點 (從 signal 欄位推斷)
    '''
    signal = result["signal"]
    buy_idx = np.where(signal == 1)[0]
    sell_idx = np.where(signal == -1)[0]

    axs[1].scatter(timestamp[buy_idx], close[buy_idx], marker="^", color="green", label="Buy Signal", zorder=5)
    axs[1].scatter(timestamp[sell_idx], close[sell_idx], marker="v", color="red", label="Sell Signal", zorder=5)

    axs[1].set_title("Price with Positions and Signals")
    axs[1].legend()
    axs[1].grid()
    '''

    # === 圖3：單筆報酬分布 ===
    axs[2].hist(np.array(trade_returns), bins=20, color="skyblue", edgecolor="k")
    axs[2].set_title("Trade Return Distribution (%)")
    axs[2].grid()

    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
    from Technicalindicatorstrategy.sma import get_signals
    from datetime import datetime
    from backtest import backtest_signals
    df_signals = get_signals("BTCUSDT", "1h", datetime.now())
    result = backtest_signals(df_signals,fee_rate=0.001,allow_short=True)
    plot_backtest_result(result)

