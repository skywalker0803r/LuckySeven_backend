from dotenv import load_dotenv
import os
load_dotenv()

# github 設定
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
github_headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}


# 預設組件
PREDEFINED_CRYPTOS = {
    "ethereum": {"binance_symbol": "ETHUSDT", "github_owner": "ethereum", "github_repo": "go-ethereum"},
    "bitcoin": {"binance_symbol": "BTCUSDT", "github_owner": "bitcoin", "github_repo": "bitcoin"},
    "solana": {"binance_symbol": "SOLUSDT", "github_owner": "solana-labs", "github_repo": "solana"},
    "polkadot": {"binance_symbol": "DOTUSDT", "github_owner": "paritytech", "github_repo": "polkadot-sdk"},
    "cardano": {"binance_symbol": "ADAUSDT", "github_owner": "input-output-hk", "github_repo": "cardano-node"},
}
