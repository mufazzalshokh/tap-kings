"""
Game routes:
- POST /game/start     → start new session
- POST /game/tap       → register a tap (with anti-cheat)
- POST /game/finish    → end session, save score
- WS   /game/ws        → real-time leaderboard broadcast
"""

import uuid
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from models import User, GameSession
from redis_client import (
    start_session, increment_tap, get_session_score,
    update_leaderboard, get_top_players, check_rate_limit
)

router = APIRouter()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


# ─── Schemas ─────────────────────────────────────────────────────

class StartSessionResponse(BaseModel):
    session_key: str
    duration: int = 30
    message: str


class TapRequest(BaseModel):
    session_key: str


class TapResponse(BaseModel):
    score: int
    allowed: bool
    message: str


class FinishRequest(BaseModel):
    session_key: str


class FinishResponse(BaseModel):
    final_score: int
    is_best: bool
    rank: Optional[int]


# ─── Routes ──────────────────────────────────────────────────────

@router.post("/start", response_model=StartSessionResponse)
async def start_game(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a new game session for the authenticated user."""
    user_id = user["id"]

    # Upsert user in PostgreSQL
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one_or_none()

    if not db_user:
        db_user = User(
            id=user_id,
            username=user.get("username", ""),
            first_name=user.get("first_name", ""),
            last_name=user.get("last_name", ""),
        )
        db.add(db_user)
    else:
        db_user.last_seen = datetime.utcnow()

    # Create game session
    session_key = str(uuid.uuid4())
    session = GameSession(
        user_id=user_id,
        session_key=session_key,
        started_at=datetime.utcnow()
    )
    db.add(session)
    await db.commit()

    # Init Redis session counter (30 second TTL)
    await start_session(session_key, duration=30)

    return StartSessionResponse(
        session_key=session_key,
        duration=30,
        message="Game started! Tap as fast as you can!"
    )


@router.post("/tap", response_model=TapResponse)
async def register_tap(
    body: TapRequest,
    user: dict = Depends(get_current_user),
):
    """
    Register a single tap.
    Anti-cheat: Redis rate limiter blocks > 20 taps/second.
    """
    user_id = user["id"]

    # Anti-cheat check
    allowed = await check_rate_limit(user_id)
    if not allowed:
        return TapResponse(
            score=await get_session_score(body.session_key),
            allowed=False,
            message="Slow down! Tap limit exceeded."
        )

    score = await increment_tap(body.session_key)

    return TapResponse(
        score=score,
        allowed=True,
        message="Tap registered!"
    )


@router.post("/finish", response_model=FinishResponse)
async def finish_game(
    body: FinishRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """End game session — save to PostgreSQL + update Redis leaderboard."""
    user_id = user["id"]
    username = user.get("username") or user.get("first_name", "Player")

    # Get final score from Redis
    final_score = await get_session_score(body.session_key)

    # Update session in DB
    result = await db.execute(
        select(GameSession).where(GameSession.session_key == body.session_key)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.score = final_score
    session.finished_at = datetime.utcnow()

    # Update user best score
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one_or_none()

    is_best = False
    if db_user and final_score > db_user.best_score:
        db_user.best_score = final_score
        db_user.total_games += 1
        is_best = True
    elif db_user:
        db_user.total_games += 1

    await db.commit()

    # Update Redis leaderboard
    await update_leaderboard(user_id, username, final_score)

    # Broadcast updated leaderboard to all WebSocket clients
    top = await get_top_players(10)
    await manager.broadcast({"type": "leaderboard_update", "data": top})

    # Get user rank
    from redis_client import get_user_rank
    rank_data = await get_user_rank(user_id, username)

    return FinishResponse(
        final_score=final_score,
        is_best=is_best,
        rank=rank_data.get("rank")
    )


# ─── WebSocket ────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_leaderboard(websocket: WebSocket):
    """
    Real-time leaderboard WebSocket.
    Sends current top 10 on connect, then receives live updates.
    """
    await manager.connect(websocket)
    try:
        # Send current leaderboard on connect
        top = await get_top_players(10)
        await websocket.send_json({"type": "leaderboard_init", "data": top})

        # Keep connection alive, listen for pings
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
