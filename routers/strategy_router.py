from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import logging

from database import get_db
from services.strategy_service import StrategyService
from exceptions import (
    StrategyNotFoundException,
    StrategyAlreadyRunningException,
    StrategyCodeMissingException,
    StrategyNameExistsException
)

router = APIRouter()

strategy_service = StrategyService()

logger = logging.getLogger(__name__)

@router.post("/strategies")
async def save_strategy(request: dict, db: Session = Depends(get_db)):
    try:
        return strategy_service.save_strategy(request, db)
    except StrategyNameExistsException as e:
        logger.warning(f"Attempted to save strategy with existing name: {e.strategy_name}")
        raise HTTPException(status_code=409, detail=str(e))
    except StrategyCodeMissingException as e:
        logger.warning(f"Attempted to save strategy with missing code or name: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred while saving strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.get("/strategies")
async def get_strategies(db: Session = Depends(get_db)):
    try:
        return strategy_service.get_strategies(db)
    except Exception as e:
        logger.error(f"An error occurred while getting strategies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    try:
        return strategy_service.delete_strategy(strategy_id, db)
    except StrategyNotFoundException as e:
        logger.warning(f"Attempted to delete non-existent strategy: {e.strategy_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred while deleting strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.post("/strategies/{strategy_id}/start")
async def start_strategy(strategy_id: int, db: Session = Depends(get_db)):
    try:
        return strategy_service.start_strategy(strategy_id, db)
    except StrategyNotFoundException as e:
        logger.warning(f"Attempted to start non-existent strategy: {e.strategy_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except StrategyAlreadyRunningException as e:
        logger.warning(f"Attempted to start already running strategy: {e.strategy_id} (status: {e.status})")
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred while starting strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.post("/strategies/{strategy_id}/stop")
async def stop_strategy(strategy_id: int, db: Session = Depends(get_db)):
    try:
        return strategy_service.stop_strategy(strategy_id, db)
    except Exception as e:
        logger.error(f"An error occurred while stopping strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.get("/strategies/{strategy_id}/status")
async def get_strategy_status(strategy_id: int, db: Session = Depends(get_db)):
    try:
        return strategy_service.get_strategy_status(strategy_id, db)
    except Exception as e:
        logger.error(f"An error occurred while getting strategy status for {strategy_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.get("/strategies/{strategy_id}/trade_logs")
async def get_strategy_trade_logs(strategy_id: int, db: Session = Depends(get_db)):
    try:
        return strategy_service.get_strategy_trade_logs(strategy_id, db)
    except StrategyNotFoundException as e:
        logger.warning(f"Attempted to get trade logs for non-existent strategy: {e.strategy_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred while getting trade logs for strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.get("/strategies/{strategy_id}/equity_curve")
async def get_strategy_equity_curve(strategy_id: int, db: Session = Depends(get_db)):
    try:
        return strategy_service.get_strategy_equity_curve(strategy_id, db)
    except StrategyNotFoundException as e:
        logger.warning(f"Attempted to get equity curve for non-existent strategy: {e.strategy_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred while getting equity curve for strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
