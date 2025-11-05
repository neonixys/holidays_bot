# config.py
import os

# Если используете файл .env, раскомментируйте две строки ниже:
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Define it in environment (or in a .env file) before running the bot."
)
