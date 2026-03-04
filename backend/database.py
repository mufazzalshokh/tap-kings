import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tapkings")

# Fix URL format
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://").replace("postgres://", "postgresql+asyncpg://")

# Remove ssl=require from URL if present - we handle it in connect_args
DATABASE_URL = DATABASE_URL.replace("?ssl=require", "").replace("&ssl=require", "")

# Use SSL only for public endpoints, not private Railway internal ones
is_internal = "railway.internal" in DATABASE_URL
connect_args = {"ssl": "disable"} if is_internal else {"ssl": "require"}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    from models import User, GameSession  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()