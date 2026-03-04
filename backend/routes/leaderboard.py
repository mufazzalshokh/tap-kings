from fastapi import APIRouter, Depends
from auth import get_current_user
from redis_client import get_top_players, get_user_rank

router = APIRouter()


@router.get("/top")
async def leaderboard_top(limit: int = 10):
    """Get global top players from Redis sorted set."""
    players = await get_top_players(min(limit, 50))
    return {"leaderboard": players, "total": len(players)}


@router.get("/me")
async def my_rank(user: dict = Depends(get_current_user)):
    """Get the current user's rank and score."""
    user_id = user["id"]
    username = user.get("username") or user.get("first_name", "Player")
    rank_data = await get_user_rank(user_id, username)
    return {
        "user_id": user_id,
        "username": username,
        **rank_data
    }
