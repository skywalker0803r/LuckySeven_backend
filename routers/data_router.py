from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
import logging

from services.data_service import DataService

router = APIRouter()

data_service = DataService()

# Configure logging for this router
logger = logging.getLogger(__name__)

def _parse_date(date_str: str) -> datetime:
    """Attempts to parse a date string from various formats."""
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Date string '{date_str}' does not match any expected format.")

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
        start_dt = _parse_date(start_date)

        if end_date is None:
            end_dt = datetime.now()
        else:
            end_dt = _parse_date(end_date)

        df = data_service.get_crypto_prices(symbol, currency, start_dt, end_dt, interval, data_limit=limit)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found for the given parameters.")
        
        df.reset_index(names=['open_time'], inplace=True)
        df['open_time'] = df['open_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        return df.to_dict(orient="records")
    except ValueError as e:
        logger.error(f"Invalid date format provided: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}. Please use YYYY-MM-DD, YYYY-MM-DD HH:MM:SS or YYYY-MM-DDTHH:MM:SS.")
    except Exception as e:
        logger.error(f"An error occurred in get_prices: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.get("/trading_pairs")
async def get_pairs(top_n: int = 1000):
    try:
        pairs = data_service.get_binance_trading_pairs(top_n)
        return {"pairs": pairs}
    except Exception as e:
        logger.error(f"An error occurred in get_pairs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
