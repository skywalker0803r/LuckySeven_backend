from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB # For storing JSON data
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set. Please create a .env file with DATABASE_URL.")

# SQLAlchemy Setup
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Database Model for Saved Strategies
class SavedStrategy(Base):
    __tablename__ = "saved_strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    code = Column(Text, nullable=False)
    symbol = Column(String)
    currency = Column(String)
    interval = Column(String)
    initial_capital = Column(Float)
    commission_rate = Column(Float)
    slippage = Column(Float)
    risk_free_rate = Column(Float)
    github_owner = Column(String, nullable=True)
    github_repo = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

# Database Model for Running Strategies
class RunningStrategy(Base):
    __tablename__ = "running_strategies"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("saved_strategies.id"), unique=True)
    pid = Column(Integer, nullable=True) # Process ID
    status = Column(String, default="stopped") # running, paused, stopped
    started_at = Column(DateTime, default=datetime.now)
    last_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# Database Model for Trade Logs
class TradeLog(Base):
    __tablename__ = "trade_logs"

    id = Column(Integer, primary_key=True, index=True)
    running_strategy_id = Column(Integer, ForeignKey("running_strategies.id"))
    timestamp = Column(DateTime, default=datetime.now)
    trade_type = Column(String) # "buy" or "sell"
    price = Column(Float)
    quantity = Column(Float)
    commission = Column(Float)
    profit_loss = Column(Float, nullable=True) # For sell trades

# Database Model for Equity Curve
class EquityCurve(Base):
    __tablename__ = "equity_curves"

    id = Column(Integer, primary_key=True, index=True)
    running_strategy_id = Column(Integer, ForeignKey("running_strategies.id"))
    timestamp = Column(DateTime, default=datetime.now)
    equity = Column(Float)

# Database Model for GitHub Commit Cache
class GithubCommitCache(Base):
    __tablename__ = 'github_commit_cache'
    id = Column(String, primary_key=True) # owner/repo
    repo_data = Column(JSONB, nullable=False) # 存放該 repo 的所有 commit cache

    def __repr__(self):
        return f"<GithubCommitCache(id='{self.id}')>"

# Create tables if they don't exist
Base.metadata.create_all(engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
