import pandas as pd

def generate_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generates trading signals based on SMA crossover strategy.

    Args:
        df (pd.DataFrame): DataFrame containing 'close' prices.

    Returns:
        pd.DataFrame: Original DataFrame with an added 'signal' column (-1: sell, 0: hold, 1: buy).
    """
    df = df.copy()
    n1 = 5  # Short-term SMA period
    n2 = 10 # Long-term SMA period

    # Calculate SMAs
    df['sma_1'] = df['close'].rolling(window=n1).mean()
    df['sma_2'] = df['close'].rolling(window=n2).mean()

    # Generate signals
    df['signal'] = 0
    # Buy signal: short SMA crosses above long SMA
    cond_buy = (df['sma_1'] > df['sma_2']) & (df['sma_1'].shift(1) <= df['sma_2'].shift(1))
    # Sell signal: short SMA crosses below long SMA
    cond_sell = (df['sma_1'] < df['sma_2']) & (df['sma_1'].shift(1) >= df['sma_2'].shift(1))

    df.loc[cond_buy, 'signal'] = 1
    df.loc[cond_sell, 'signal'] = -1

    # Fill NaN values in signal column with 0 (no signal)
    df['signal'] = df['signal'].fillna(0).astype(int)

    return df
