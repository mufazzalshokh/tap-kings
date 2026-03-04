# -*- coding: utf-8 -*-
"""
Telegram Bot using aiogram v3 with webhook mode.
"""

import os
from aiogram import Bot, Dispatcher, Router
from aiogram.types import (
    Message, Update, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton,
    MenuButtonWebApp
)
from fastapi import APIRouter, Request, Response

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")
WEBHOOK_PATH = "/webhook/telegram"
WEBHOOK_URL = f"{APP_URL}{WEBHOOK_PATH}"

router = APIRouter()

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()
bot_router = Router()
dp.include_router(bot_router)


@bot_router.message(lambda m: m.text == "/start")
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Play Tap Kings!",
            web_app=WebAppInfo(url=APP_URL)
        )
    ]])
    await message.answer(
        "*Welcome to Tap Kings!*\n\n"
        "Tap as fast as you can in 30 seconds.\n"
        "Compete on the global leaderboard!\n\n"
        "Press the button below to start!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@bot_router.message(lambda m: m.text == "/leaderboard")
async def cmd_leaderboard(message: Message):
    from redis_client import get_top_players
    players = await get_top_players(5)

    if not players:
        await message.answer("No scores yet! Be the first to play!")
        return

    lines = ["*Tap Kings Leaderboard*\n"]
    for i, p in enumerate(players):
        lines.append(f"{i+1}. @{p['username']} - *{p['score']}* taps")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@bot_router.message(lambda m: m.text == "/help")
async def cmd_help(message: Message):
    await message.answer(
        "*Tap Kings Commands*\n\n"
        "/start - Open the game\n"
        "/leaderboard - Show top 5 players\n"
        "/help - This message",
        parse_mode="Markdown"
    )


async def setup_webhook():
    if bot and APP_URL and "localhost" not in APP_URL:
        await bot.set_webhook(WEBHOOK_URL)
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Play",
                web_app=WebAppInfo(url=APP_URL)
            )
        )
        print(f"Webhook set: {WEBHOOK_URL}")


@router.post("/telegram")
async def telegram_webhook(request: Request) -> Response:
    if not bot:
        return Response(status_code=200)
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot=bot, update=update)
    return Response(status_code=200)


async def notify_new_highscore(username: str, score: int, rank: int):
    if not bot:
        return
    channel_id = os.getenv("CHANNEL_ID")
    if channel_id:
        await bot.send_message(
            channel_id,
            f"New high score! @{username} just tapped *{score}* times! Rank #{rank}",
            parse_mode="Markdown"
        )