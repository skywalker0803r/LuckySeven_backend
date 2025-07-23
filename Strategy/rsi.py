import pandas as pd
import numpy as np

def generate_signal(df, period=14, buy_threshold=30, sell_threshold=70):
    df = df.copy()
    
    # 計算每日價格變化
    delta = df['close'].diff()
    
    # 分離上漲和下跌
    up_gains = delta.where(delta > 0, 0)
    down_losses = -delta.where(delta < 0, 0)
    
    # 計算平均上漲和平均下跌
    avg_gain = up_gains.ewm(span=period, adjust=False).mean()
    avg_loss = down_losses.ewm(span=period, adjust=False).mean()
    
    # 計算相對強度 (RS)
    rs = avg_gain / avg_loss
    
    # 計算 RSI
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 判斷買賣訊號
    df['signal'] = 0
    
    # 超賣買入訊號：RSI 從低於買入閾值轉為高於買入閾值
    cond_buy_oversold = (df['rsi'] > buy_threshold) & (df['rsi'].shift(1) <= buy_threshold)
    
    # 超買賣出訊號：RSI 從高於賣出閾值轉為低於賣出閾值
    cond_sell_overbought = (df['rsi'] < sell_threshold) & (df['rsi'].shift(1) >= sell_threshold)
    
    df.loc[cond_buy_oversold, 'signal'] = 1
    df.loc[cond_sell_overbought, 'signal'] = -1
    
    return df