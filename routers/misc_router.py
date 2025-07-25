from fastapi import APIRouter, HTTPException
import logging

from services.misc_service import MiscService

router = APIRouter()

misc_service = MiscService()

logger = logging.getLogger(__name__)

@router.get("/strategy_list")
async def get_strategy_list():
    try:
        return misc_service.get_strategy_list()
    except Exception as e:
        logger.error(f"An error occurred in get_strategy_list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.get("/strategy_code/{strategy_name}")
async def get_strategy_code(strategy_name: str):
    try:
        return misc_service.get_strategy_code(strategy_name)
    except Exception as e:
        logger.error(f"An error occurred in get_strategy_code: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.post("/run_backtest")
async def run_backtest(
    request: dict,
):
    symbol = request.get("symbol")
    currency = request.get("currency")
    interval = request.get("interval")
    start_date_str = request.get("start_date")
    end_date_str = request.get("end_date")
    strategy_code = request.get("strategy_code")
    strategy_name = request.get("strategy_name")
    initial_capital = request.get("initial_capital", 10000)
    commission_rate = request.get("commission_rate", 0.001)
    slippage = request.get("slippage", 0.0005)
    risk_free_rate = request.get("risk_free_rate", 0.02)
    github_owner = request.get("github_owner")
    github_repo = request.get("github_repo")

    try:
        return misc_service.run_backtest(
            symbol, currency, interval, start_date_str, end_date_str, strategy_code, strategy_name,
            initial_capital, commission_rate, slippage, risk_free_rate, github_owner, github_repo
        )
    except Exception as e:
        logger.error(f"An error occurred in run_backtest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
