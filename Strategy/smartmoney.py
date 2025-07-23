import pandas as pd
import numpy as np

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def hull_moving_average(series, period):
    half_length = int(period / 2)
    sqrt_length = int(np.sqrt(period))
    wma_half = series.rolling(window=half_length).mean()
    wma_full = series.rolling(window=period).mean()
    hull = 2 * wma_half - wma_full
    return hull.rolling(window=sqrt_length).mean()

def generate_signal(df):
    df = df.copy()

    # === Vegas Tunnels ===
    df['ema_144'] = ema(df['close'], 144)
    df['ema_169'] = ema(df['close'], 169)

    # === Long-Term EMA Ribbons ===
    df['ema_288'] = ema(df['close'], 288)
    df['ema_338'] = ema(df['close'], 338)
    df['ema_576'] = ema(df['close'], 576)
    df['ema_676'] = ema(df['close'], 676)

    # === Hull Moving Averages ===
    df['main_hull'] = hull_moving_average(df['close'], 55)
    df['second_hull'] = hull_moving_average(df['close'], 21)

    # === Trend Direction (簡單定義: 長期均線多頭排列視為上升)
    df['trend_up'] = (
        (df['ema_144'] > df['ema_169']) &
        (df['ema_288'] > df['ema_338']) &
        (df['main_hull'] > df['second_hull'])
    )

    df['trend_down'] = (
        (df['ema_144'] < df['ema_169']) &
        (df['ema_288'] < df['ema_338']) &
        (df['main_hull'] < df['second_hull'])
    )

    # === Buy/Sell Signals (用 Hull 交叉 + 趨勢過濾)
    df['signal'] = 0
    cond_buy = (
        (df['main_hull'] > df['second_hull']) &
        (df['main_hull'].shift(1) <= df['second_hull'].shift(1)) &
        df['trend_up']
    )
    cond_sell = (
        (df['main_hull'] < df['second_hull']) &
        (df['main_hull'].shift(1) >= df['second_hull'].shift(1)) &
        df['trend_down']
    )
    df.loc[cond_buy, 'signal'] = 1
    df.loc[cond_sell, 'signal'] = -1

    return df
