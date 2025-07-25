from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta

from services.data_service import DataService

router = APIRouter()

data_service = DataService()

@router.get("/crypto_prices")
async def get_prices(
    symbol: str = "BTC",
    currency: str = "USDT",
    interval: str = "1h",
    start_date: str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
    end_date: str | None = None,
    limit: int | None = None
):
    try:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")

        if end_date is None:
            end_dt = datetime.now()
        else:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        df = data_service.get_crypto_prices(symbol, currency, start_dt, end_dt, interval, data_limit=limit)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found for the given parameters.")
        
        df.reset_index(names=['open_time'], inplace=True)
        df['open_time'] = df['open_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        return df.to_dict(orient="records")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}. Please use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.get("/trading_pairs")
async def get_pairs(top_n: int = 1000):
    try:
        pairs = data_service.get_binance_trading_pairs(top_n)
        return {"pairs": pairs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
