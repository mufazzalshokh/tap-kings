# 👑 Tap Kings — Real-time Telegram Mini App Clicker Game

A production-ready Telegram Mini App where players tap as fast as they can
in 30 seconds and compete on a live global leaderboard. Built with FastAPI,
aiogram v3, Redis Sorted Sets, WebSockets, and PostgreSQL — deployed on Railway.

## Architecture

```
Telegram User
     │  opens Mini App
     ▼
Frontend (HTML/JS)  ──── WebSocket ────► FastAPI (live leaderboard updates)
     │
     │  REST API calls (X-Init-Data header)
     ▼
FastAPI Backend
     ├── Auth: Telegram initData HMAC-SHA256 validation
     ├── Game: start → tap (anti-cheat) → finish
     ├── Redis: leaderboard + session counters + rate limiter
     └── PostgreSQL: persistent user records + session history
          │
          ▼
aiogram v3 Bot (webhook mode, same FastAPI process)
     └── /start, /leaderboard, /help commands
     └── Channel notifications on new high scores
```

## Features

### 🎮 Game Flow
1. `POST /game/start` — creates a `GameSession` in PostgreSQL, initialises a
   Redis counter with 35-second TTL
2. `POST /game/tap` — anti-cheat check → atomic Redis `INCR` → returns current score
3. `POST /game/finish` — reads final score from Redis → persists to PostgreSQL →
   updates Redis leaderboard → broadcasts updated top 10 to all WebSocket clients

### 🔒 Authentication
Telegram Mini Apps send a signed `initData` string with every request.
The backend validates it using **HMAC-SHA256** per the official Telegram spec:

```python
# Secret key = HMAC-SHA256("WebAppData", bot_token)
# Then verify: HMAC-SHA256(secret_key, data_check_string) == received_hash
```

No sessions, no JWTs — every request is stateless and cryptographically verified.
`DEV_MODE=true` bypasses validation for local development.

### 🛡️ Anti-Cheat — Redis Sliding Window Rate Limiter
Blocks impossible tap speeds (> 20 taps/second) using a **sliding window**
(more accurate than fixed window — no boundary burst exploitation):

```python
pipe.zremrangebyscore(key, 0, now - 1.0)  # remove events outside window
pipe.zcard(key)                            # count events in window
pipe.zadd(key, {str(now): now})            # record this event
pipe.expire(key, 2)                        # auto-cleanup
# All 4 ops in a single pipeline round-trip
```

`cheating_detected` is flagged on the `GameSession` record in PostgreSQL.

### 🏆 Leaderboard — Redis Sorted Sets
O(log N) insert and lookup using Redis Sorted Sets:

| Operation | Redis Command | Complexity |
|---|---|---|
| Update score | `ZADD` | O(log N) |
| Get top N | `ZREVRANGE ... WITHSCORES` | O(log N + M) |
| Get user rank | `ZREVRANK` | O(log N) |

The leaderboard is always in Redis — PostgreSQL stores the authoritative record.

### 📡 Real-time Leaderboard via WebSocket
On `POST /game/finish`, the backend broadcasts the updated top 10 to every
connected WebSocket client instantly — no polling required:

```
Client connects → receives current top 10
Any player finishes → all connected clients receive leaderboard_update event
```

### 🤖 Telegram Bot (aiogram v3, webhook mode)
- `/start` — opens the Mini App via `WebAppInfo` inline button
- `/leaderboard` — shows top 5 from Redis directly in chat
- `/help` — command reference
- Channel notifications on new high scores via `CHANNEL_ID` env var
- Runs as a **webhook inside the same FastAPI process** (no separate service)
- `MenuButtonWebApp` set on startup for persistent Play button in chat header

### 🚀 Deployment (Railway)
Railway-aware database connection: auto-detects internal (`railway.internal`)
vs external URLs and sets `ssl: disable` vs `ssl: require` accordingly —
no manual config change needed between environments.

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI (async), Python 3.11 |
| Bot | aiogram v3 (webhook mode) |
| Cache / Leaderboard | Redis (aioredis) — Sorted Sets, INCR, sliding window |
| Database | PostgreSQL + SQLAlchemy 2.0 async (asyncpg) |
| Auth | Telegram initData HMAC-SHA256 |
| Real-time | WebSocket (FastAPI native) |
| Deployment | Railway |

## Project Structure

```
tap-kings/
├── backend/
│   ├── main.py              # FastAPI app, lifespan, middleware
│   ├── auth.py              # Telegram initData HMAC-SHA256 validation
│   ├── bot.py               # aiogram v3 bot + webhook handler
│   ├── database.py          # SQLAlchemy async engine (Railway SSL-aware)
│   ├── models.py            # User + GameSession ORM models
│   ├── redis_client.py      # Leaderboard, session counters, rate limiter
│   └── routes/
│       ├── game.py          # /game/start, /tap, /finish + WebSocket
│       └── leaderboard.py   # /leaderboard/top, /me
└── frontend/                # Static Mini App (served by FastAPI)
```

## Getting Started

```bash
git clone https://github.com/mufazzalshokh/tap-kings.git
cd tap-kings/backend
pip install -r requirements.txt

# .env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tapkings
REDIS_URL=redis://localhost:6379
APP_URL=https://your-app.railway.app
DEV_MODE=true   # skip initData validation locally

python main.py
```

## Key Design Decisions

- **Redis INCR for tap counting** — atomic increment with no race conditions
  under concurrent requests from the same user.
- **Sliding window over fixed window rate limiting** — fixed windows allow a
  burst of 40 taps at a window boundary (20 at end + 20 at start). Sliding
  window prevents this.
- **Pipeline for rate limiter** — 4 Redis commands execute in a single round
  trip, keeping tap latency minimal.
- **Redis TTL on session keys** — sessions expire automatically 35 seconds
  after creation (30s game + 5s buffer), no cleanup job needed.
- **Webhook in same process** — aiogram v3 webhook handler mounted on the
  same FastAPI app eliminates a second service to manage and deploy.
- **WebSocket broadcast on finish** — event-driven; no client polling. All
  spectators see the updated leaderboard the moment any player finishes.
- **Railway internal SSL detection** — avoids SSL handshake on private network
  while enforcing it on public connections automatically.
