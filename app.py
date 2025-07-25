from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from routers.strategy_router import router as strategy_router
from routers.data_router import router as data_router
from routers.misc_router import router as misc_router

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://luckyseven-frontend.onrender.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Include routers
app.include_router(strategy_router)
app.include_router(data_router)
app.include_router(misc_router)

