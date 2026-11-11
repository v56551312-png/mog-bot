import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "")
STORAGE_CHAT_ID = int(os.getenv("STORAGE_CHAT_ID", "0") or 0)
SEASON_END = os.getenv("SEASON_END", "2026-12-31")
PRIZE_TEXT = os.getenv("PRIZE_TEXT", "NFT + 700 ⭐")
COLOR_PRICE = 15          # цена смены цвета карточки, в Telegram Stars
PERIOD_DAYS = 7           # период для топа
DB_PATH = os.getenv("DB_PATH", "mog.db")
