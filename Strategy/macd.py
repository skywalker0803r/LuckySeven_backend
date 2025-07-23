import pandas as pd

def add_macd_signals(df, fast_period=12, slow_period=26, signal_period=9):
    df = df.copy()
    
    # 計算 EMA 12 和 EMA 26
    df['ema_fast'] = df['close'].ewm(span=fast_period, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_period, adjust=False).mean()
    
    # 計算 MACD 線
    df['macd_line'] = df['ema_fast'] - df['ema_slow']
    
    # 計算訊號線 (MACD 線的 EMA)
    df['signal_line'] = df['macd_line'].ewm(span=signal_period, adjust=False).mean()
    
    # 判斷買賣訊號
    df['signal'] = 0
    cond_buy = (df['macd_line'] > df['signal_line']) & (df['macd_line'].shift(1) <= df['signal_line'].shift(1))
    cond_sell = (df['macd_line'] < df['signal_line']) & (df['macd_line'].shift(1) >= df['signal_line'].shift(1))
    
    df.loc[cond_buy, 'signal'] = 1
    df.loc[cond_sell, 'signal'] = -1
    
    return df