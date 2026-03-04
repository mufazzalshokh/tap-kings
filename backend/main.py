import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db
from redis_client import init_redis, close_redis
from routes.game import router as game_router
from routes.leaderboard import router as leaderboard_router
from bot import router as bot_router, setup_webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_redis()
    await setup_webhook()  # <- THIS WAS MISSING
    yield
    await close_redis()


app = FastAPI(
    title="Tap Kings API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(game_router, prefix="/game", tags=["game"])
app.include_router(leaderboard_router, prefix="/leaderboard", tags=["leaderboard"])
app.include_router(bot_router, prefix="/webhook", tags=["webhook"])

# Serve frontend static files
frontend_path = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")