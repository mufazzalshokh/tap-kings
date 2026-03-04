"""
Redis client.
- Leaderboard using Redis Sorted Sets (ZADD, ZREVRANGE, ZRANK)
- Anti-cheat rate limiting using Redis sliding window
- Session tap counters
"""

import os
import time
import redis.asyncio as aioredis
from typing import Optional

redis_client: Optional[aioredis.Redis] = None

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Anti-cheat: max taps allowed per window
MAX_TAPS_PER_WINDOW = 20       # max 20 taps
RATE_WINDOW_SECONDS = 1        # per 1 second
LEADERBOARD_KEY = "tap_kings:leaderboard"
SESSION_KEY_PREFIX = "tap_kings:session:"
RATE_KEY_PREFIX = "tap_kings:rate:"


async def init_redis():
    global redis_client
    redis_client = aioredis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True
    )
    await redis_client.ping()
    print("✅ Redis connected")


async def close_redis():
    if redis_client:
        await redis_client.close()


# ─── Leaderboard ────────────────────────────────────────────────

async def update_leaderboard(user_id: int, username: str, score: int):
    """Add/update user score in Redis sorted set."""
    await redis_client.zadd(LEADERBOARD_KEY, {f"{user_id}:{username}": score})


async def get_top_players(limit: int = 10) -> list[dict]:
    """Get top N players with scores."""
    results = await redis_client.zrevrange(
        LEADERBOARD_KEY, 0, limit - 1, withscores=True
    )
    players = []
    for i, (member, score) in enumerate(results):
        user_id, *name_parts = member.split(":")
        players.append({
            "rank": i + 1,
            "user_id": int(user_id),
            "username": ":".join(name_parts),
            "score": int(score)
        })
    return players


async def get_user_rank(user_id: int, username: str) -> dict:
    """Get a specific user's rank and score."""
    member = f"{user_id}:{username}"
    rank = await redis_client.zrevrank(LEADERBOARD_KEY, member)
    score = await redis_client.zscore(LEADERBOARD_KEY, member)
    return {
        "rank": (rank + 1) if rank is not None else None,
        "score": int(score) if score else 0
    }


# ─── Session Management ─────────────────────────────────────────

async def start_session(session_id: str, duration: int = 30):
    """Initialize tap counter for a game session."""
    key = f"{SESSION_KEY_PREFIX}{session_id}"
    await redis_client.setex(key, duration + 5, 0)


async def increment_tap(session_id: str) -> int:
    """Increment tap count for a session. Returns new count."""
    key = f"{SESSION_KEY_PREFIX}{session_id}"
    count = await redis_client.incr(key)
    return count


async def get_session_score(session_id: str) -> int:
    """Get current tap count for a session."""
    key = f"{SESSION_KEY_PREFIX}{session_id}"
    val = await redis_client.get(key)
    return int(val) if val else 0


# ─── Anti-Cheat Rate Limiting ────────────────────────────────────

async def check_rate_limit(user_id: int) -> bool:
    """
    Sliding window rate limiter.
    Returns True if tap is allowed, False if rate limit exceeded (cheating).
    Max 20 taps per second per user.
    """
    key = f"{RATE_KEY_PREFIX}{user_id}"
    now = time.time()
    window_start = now - RATE_WINDOW_SECONDS

    pipe = redis_client.pipeline()
    # Remove old entries outside window
    pipe.zremrangebyscore(key, 0, window_start)
    # Count current window
    pipe.zcard(key)
    # Add current timestamp
    pipe.zadd(key, {str(now): now})
    # Expire key after window
    pipe.expire(key, RATE_WINDOW_SECONDS + 1)

    results = await pipe.execute()
    current_count = results[1]

    return current_count < MAX_TAPS_PER_WINDOW
