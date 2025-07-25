from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.strategy_service import StrategyService

router = APIRouter()

strategy_service = StrategyService()

@router.post("/strategies")
async def save_strategy(request: dict, db: Session = Depends(get_db)):
    return strategy_service.save_strategy(request, db)

@router.get("/strategies")
async def get_strategies(db: Session = Depends(get_db)):
    return strategy_service.get_strategies(db)

@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    return strategy_service.delete_strategy(strategy_id, db)

@router.post("/strategies/{strategy_id}/start")
async def start_strategy(strategy_id: int, db: Session = Depends(get_db)):
    return strategy_service.start_strategy(strategy_id, db)

@router.post("/strategies/{strategy_id}/stop")
async def stop_strategy(strategy_id: int, db: Session = Depends(get_db)):
    return strategy_service.stop_strategy(strategy_id, db)

@router.get("/strategies/{strategy_id}/status")
async def get_strategy_status(strategy_id: int, db: Session = Depends(get_db)):
    return strategy_service.get_strategy_status(strategy_id, db)

@router.get("/strategies/{strategy_id}/trade_logs")
async def get_strategy_trade_logs(strategy_id: int, db: Session = Depends(get_db)):
    return strategy_service.get_strategy_trade_logs(strategy_id, db)

@router.get("/strategies/{strategy_id}/equity_curve")
async def get_strategy_equity_curve(strategy_id: int, db: Session = Depends(get_db)):
    return strategy_service.get_strategy_equity_curve(strategy_id, db)
