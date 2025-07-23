def add_commit_sma_signals(df,n1,n2):
    df = df.copy()
    df['sma_1'] = df['commit_count'].rolling(window=n1).mean()
    df['sma_2'] = df['commit_count'].rolling(window=n2).mean()

    # 判斷買賣訊號：sma_5 上穿 sma_10 為買，反之為賣
    df['signal'] = 0
    # 用 shift 搭配判斷均線交叉
    cond_buy = (df['sma_1'] > df['sma_2']) & (df['sma_1'].shift(1) <= df['sma_2'].shift(1))
    cond_sell = (df['sma_1'] < df['sma_2']) & (df['sma_1'].shift(1) >= df['sma_2'].shift(1))

    df.loc[cond_buy, 'signal'] = 1
    df.loc[cond_sell, 'signal'] = -1
    return df