# bot.py
import asyncio
import pytz
import re
from datetime import datetime, date

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TOKEN
from holidays import (
    get_holidays_today,
    get_holidays_for_date,
    get_holiday_details_grouped,   # <-- используем группировку
)
from subscriptions import load_subs, add_sub, remove_sub
from custom_holidays import get_for_date, add_custom

dp = Dispatcher()

# --- Клавиатура ---
MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📆 Сегодня"), KeyboardButton(text="🔎 Поиск по дате")],
        [KeyboardButton(text="🔔 Подписаться"), KeyboardButton(text="🔕 Отписаться")],
        [KeyboardButton(text="➕ Добавить праздник")],
    ],
    resize_keyboard=True,
)

# --- Подписки ---
CHAT_IDS: set[int] = load_subs()

# --- FSM ---
class AddHoliday(StatesGroup):
    waiting_date = State()
    waiting_title = State()
    waiting_repeat = State()

class SearchByDate(StatesGroup):
    waiting_date = State()

# --- Парсеры дат ---
RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
DATE_ONLY_RE = re.compile(r"^\s*(\d{1,2})\s+([А-Яа-яЁё]+)\s*$")
DDMM_RE = re.compile(r"^\s*(\d{1,2})[.\-/](\d{1,2})\s*$")

def parse_ru_day_month(text: str) -> datetime | None:
    m = DATE_ONLY_RE.match(text or "")
    if not m:
        return None
    day = int(m.group(1))
    mon_name = m.group(2).lower()
    mon = RU_MONTHS.get(mon_name)
    if not mon:
        return None
    tz = pytz.timezone("Europe/Moscow")
    try:
        return tz.localize(datetime(datetime.now(tz).year, mon, day))
    except ValueError:
        return None

def parse_ddmm(text: str) -> datetime | None:
    m = DDMM_RE.match(text or "")
    if not m:
        return None
    day = int(m.group(1))
    mon = int(m.group(2))
    tz = pytz.timezone("Europe/Moscow")
    try:
        return tz.localize(datetime(datetime.now(tz).year, mon, day))
    except ValueError:
        return None

# --- Форматирование ---
def html_list_rus(details: list[dict]) -> str:
    """Ссылки + описание (для России)."""
    if not details:
        return "• Ничего не найдено"
    lines = []
    for d in details:
        lines.append(f'• <a href="{d["url"]}"><b>{d["title"]}</b></a>\n  <i>{d.get("desc","")}</i>')
    return "\n".join(lines)

def html_list_links_only(details: list[dict]) -> str:
    """Только ссылки (для других стран)."""
    if not details:
        return "• —"
    return "\n".join(f'• <a href="{d["url"]}"><b>{d["title"]}</b></a>' for d in details)

# --- Отправка двух сообщений (Россия / Остальные) ---
async def send_grouped(bot: Bot, chat_id: int, target: date):
    rus, other = get_holiday_details_grouped(target)

    # «свои»
    custom_list = get_for_date(target)
    custom_block = "\n".join(f"• (своё) <b>{t}</b>" for t in custom_list)

    # Сообщение 1 — Россия
    head_rus = "<b>🇷🇺 Праздники России:</b>\n"
    body_rus = html_list_rus(rus)
    if custom_block:
        body_rus += "\n" + custom_block
    await bot.send_message(
        chat_id,
        head_rus + body_rus,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    # Сообщение 2 — Остальные (только если есть)
    if other:
        head_other = "\n\n<b>🌍 Другие праздники:</b>\n"
        body_other = html_list_links_only(other)
        await bot.send_message(
            chat_id,
            head_other + body_other,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

# --- Рассылка «сегодня» ---
async def send_today(bot: Bot, chat_id: int):
    tz = pytz.timezone("Europe/Moscow")
    today_msk: date = datetime.now(tz).date()
    await send_grouped(bot, chat_id, today_msk)

async def broadcast_daily(bot: Bot):
    for chat_id in list(CHAT_IDS):
        try:
            await send_today(bot, chat_id)
        except Exception as e:
            print(f"[broadcast] chat {chat_id} error: {e}")

# --- Хендлеры ---
@dp.message(CommandStart())
async def start_handler(message: Message):
    add_sub(CHAT_IDS, message.chat.id)
    await message.answer(
        "Привет! Я включён ✅\n\n"
        "Нажимай кнопки снизу:\n"
        "• 📆 Сегодня — показать праздники\n"
        "• 🔎 Поиск по дате — 4 ноября / 21.01\n"
        "• 🔔 Подписаться — включить рассылку (09:00 МСК)\n"
        "• 🔕 Отписаться — отключить рассылку\n"
        "• ➕ Добавить праздник — добавить свой повод",
        reply_markup=MAIN_KB,
    )

@dp.message(Command("subscribe"))
async def subscribe_handler(message: Message):
    add_sub(CHAT_IDS, message.chat.id)
    await message.answer("Подписка включена ✅ Я напомню в 09:00 по Москве каждый день.")

@dp.message(Command("unsubscribe"))
async def unsubscribe_handler(message: Message):
    remove_sub(CHAT_IDS, message.chat.id)
    await message.answer("Подписка отключена 📴")

@dp.message(F.text.lower().in_({"сегодня", "📆 сегодня"}))
async def today_btn(message: Message):
    await send_today(message.bot, message.chat.id)

@dp.message(F.text.lower().in_({"подписаться", "🔔 подписаться"}))
async def subscribe_btn(message: Message):
    add_sub(CHAT_IDS, message.chat.id)
    await message.answer("Подписка включена ✅ Я напомню в 09:00 по Москве каждый день.")

@dp.message(F.text.lower().in_({"отписаться", "🔕 отписаться"}))
async def unsubscribe_btn(message: Message):
    remove_sub(CHAT_IDS, message.chat.id)
    await message.answer("Подписка отключена 📴")

# --- Мастер «Добавить праздник» ---
@dp.message(F.text.lower().in_({"➕ добавить праздник", "добавить праздник"}))
async def add_holiday_start(message: Message, state: FSMContext):
    await state.set_state(AddHoliday.waiting_date)
    await message.answer(
        "Введите дату в формате YYYY-MM-DD (например, 2025-11-04):",
        reply_markup=ReplyKeyboardRemove(),
    )

@dp.message(AddHoliday.waiting_date)
async def add_holiday_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%Y-%m-%d")
    except Exception:
        await message.answer("Неверный формат. Введите дату как YYYY-MM-DD (например, 2025-11-04).")
        return
    await state.update_data(date_str=message.text.strip())
    await state.set_state(AddHoliday.waiting_title)
    await message.answer("Введите короткое название праздника:")

@dp.message(AddHoliday.waiting_title)
async def add_holiday_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Название пустое. Введите короткое название праздника:")
        return
    await state.update_data(title=title)
    await state.set_state(AddHoliday.waiting_repeat)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Ежегодно")], [KeyboardButton(text="Один раз")]],
        resize_keyboard=True,
    )
    await message.answer("Повторять ежегодно?", reply_markup=kb)

@dp.message(AddHoliday.waiting_repeat, F.text.lower().in_({"ежегодно", "один раз"}))
async def add_holiday_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    repeat = "annual" if message.text.lower() == "ежегодно" else "once"
    try:
        rec = add_custom(data["date_str"], data["title"], repeat=repeat)
    except Exception as e:
        await state.clear()
        await message.answer(f"Не удалось сохранить: {e}", reply_markup=MAIN_KB)
        return
    await state.clear()
    await message.answer(
        f"Готово! Сохранён праздник:\n• {rec['title']} — {rec['date']} "
        f"({'ежегодно' if rec['repeat']=='annual' else 'один раз'})",
        reply_markup=MAIN_KB,
    )

# --- Поиск по дате ---
@dp.message(F.text.lower().in_({"🔎 поиск по дате", "поиск по дате"}))
async def search_by_date_start(message: Message, state: FSMContext):
    await state.set_state(SearchByDate.waiting_date)
    await message.answer(
        "Введите дату (4 ноября / 21.01):",
        reply_markup=ReplyKeyboardRemove(),
    )

@dp.message(SearchByDate.waiting_date)
async def search_by_date_finish(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    dt = parse_ru_day_month(text) or parse_ddmm(text)
    if not dt:
        await message.answer("Не понимаю формат. Введите «4 ноября» или «21.01».")
        return
    target = dt.date()
    await send_grouped(message.bot, message.chat.id, target)
    await state.clear()

# --- Фоллбек: просто прислали дату текстом ---
@dp.message(F.text)
async def fallback_date_parser(message: Message):
    dt = parse_ru_day_month(message.text) or parse_ddmm(message.text)
    if not dt:
        return
    await send_grouped(message.bot, message.chat.id, dt.date())

# --- Запуск ---
async def main():
    bot = Bot(token=TOKEN)
    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))
    scheduler.add_job(broadcast_daily, "cron", hour=9, minute=0, args=[bot])
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())



# # bot.py
# import asyncio
# import pytz
# import re
# from datetime import datetime, date
#
# from aiogram import Bot, Dispatcher, F
# from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
# from aiogram.filters import CommandStart, Command
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.state import StatesGroup, State
#
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
#
# from config import TOKEN
# from holidays import (
#     get_holidays_today,
#     get_holidays_for_date,
#     get_holiday_details_for_date,
# )
# from subscriptions import load_subs, add_sub, remove_sub
# from custom_holidays import get_for_date, add_custom
#
# dp = Dispatcher()
#
# # --- Клавиатура ---
# MAIN_KB = ReplyKeyboardMarkup(
#     keyboard=[
#         [KeyboardButton(text="📆 Сегодня")],
#         [KeyboardButton(text="🔎 Поиск по дате")],
#         [KeyboardButton(text="🔔 Подписаться"), KeyboardButton(text="🔕 Отписаться")],
#         [KeyboardButton(text="➕ Добавить праздник")],
#     ],
#     resize_keyboard=True,
# )
#
# # --- Подписки ---
# CHAT_IDS: set[int] = load_subs()
#
# # --- FSM для мастера добавления ---
# class AddHoliday(StatesGroup):
#     waiting_date = State()
#     waiting_title = State()
#     waiting_repeat = State()
#
# # --- FSM для поиска по дате ---
# class SearchByDate(StatesGroup):
#     waiting_date = State()
#
# # --- Поиск по дате: парсеры ---
# RU_MONTHS = {
#     "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
#     "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
# }
# DATE_ONLY_RE = re.compile(r"^\s*(\d{1,2})\s+([А-Яа-яЁё]+)\s*$")
# DDMM_RE = re.compile(r"^\s*(\d{1,2})[.\-/](\d{1,2})\s*$")
#
# def parse_ru_day_month(text: str) -> datetime | None:
#     """ '4 ноября' / '04 ноября' -> datetime текущего года (МСК) """
#     m = DATE_ONLY_RE.match(text or "")
#     if not m:
#         return None
#     day = int(m.group(1))
#     mon_name = m.group(2).lower()
#     mon = RU_MONTHS.get(mon_name)
#     if not mon:
#         return None
#     tz = pytz.timezone("Europe/Moscow")
#     try:
#         return tz.localize(datetime(datetime.now(tz).year, mon, day))
#     except ValueError:
#         return None
#
# def parse_ddmm(text: str) -> datetime | None:
#     """ '21.01' / '21-01' / '21/01' -> datetime текущего года (МСК) """
#     m = DDMM_RE.match(text or "")
#     if not m:
#         return None
#     day = int(m.group(1))
#     mon = int(m.group(2))
#     tz = pytz.timezone("Europe/Moscow")
#     try:
#         return tz.localize(datetime(datetime.now(tz).year, mon, day))
#     except ValueError:
#         return None
#
# # --- Форматирование HTML ---
# def format_details_html(details: list[dict], fallback_titles: list[str] | None = None) -> str:
#     """
#     Собирает красивый HTML: ссылка + краткое описание (если есть).
#     """
#     lines: list[str] = []
#     if details:
#         for d in details:
#             title = d.get("title", "")
#             url = d.get("url", "")
#             desc = d.get("desc", "")
#             if url and title:
#                 if desc:
#                     lines.append(f'• <a href="{url}"><b>{title}</b></a>\n  <i>{desc}</i>')
#                 else:
#                     lines.append(f'• <a href="{url}"><b>{title}</b></a>')
#     elif fallback_titles:
#         lines = [f"• <b>{t}</b>" for t in fallback_titles]
#     else:
#         lines = ["• Ничего не найдено"]
#     return "\n".join(lines)
#
# # --- Отправка «сегодня» ---
# async def send_today(bot: Bot, chat_id: int):
#     tz = pytz.timezone("Europe/Moscow")
#     today_msk: date = datetime.now(tz).date()
#
#     # Официальные (подробно, со ссылками)
#     details = get_holiday_details_for_date(today_msk)
#
#     # «Свои»
#     custom_list = get_for_date(today_msk)
#     custom_lines = [f"• (своё) <b>{t}</b>" for t in custom_list]
#
#     text = "<b>🎉 Праздники сегодня:</b>\n" + format_details_html(details)
#     if custom_lines:
#         text += "\n" + "\n".join(custom_lines)
#
#     await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
#
# async def broadcast_daily(bot: Bot):
#     for chat_id in list(CHAT_IDS):
#         try:
#             await send_today(bot, chat_id)
#         except Exception as e:
#             print(f"[broadcast] chat {chat_id} error: {e}")
#
# # --- Хендлеры общие ---
# @dp.message(CommandStart())
# async def start_handler(message: Message):
#     add_sub(CHAT_IDS, message.chat.id)
#     await message.answer(
#         "Привет! Я включён ✅\n\n"
#         "Нажимай кнопки снизу:\n"
#         "• 📆 Сегодня — показать праздники\n"
#         "• 🔎 Поиск по дате — введите, например, 4 ноября или 21.01\n"
#         "• 🔔 Подписаться — включить рассылку (09:00 МСК)\n"
#         "• 🔕 Отписаться — отключить рассылку\n"
#         "• ➕ Добавить праздник — добавить свой повод",
#         reply_markup=MAIN_KB,
#     )
#
# @dp.message(Command("subscribe"))
# async def subscribe_handler(message: Message):
#     add_sub(CHAT_IDS, message.chat.id)
#     await message.answer("Подписка включена ✅ Я напомню в 09:00 по Москве каждый день.")
#
# @dp.message(Command("unsubscribe"))
# async def unsubscribe_handler(message: Message):
#     remove_sub(CHAT_IDS, message.chat.id)
#     await message.answer("Подписка отключена 📴")
#
# @dp.message(F.text.lower().in_({"сегодня", "📆 сегодня"}))
# async def today_btn(message: Message):
#     await send_today(message.bot, message.chat.id)
#
# @dp.message(F.text.lower().in_({"подписаться", "🔔 подписаться"}))
# async def subscribe_btn(message: Message):
#     add_sub(CHAT_IDS, message.chat.id)
#     await message.answer("Подписка включена ✅ Я напомню в 09:00 по Москве каждый день.")
#
# @dp.message(F.text.lower().in_({"отписаться", "🔕 отписаться"}))
# async def unsubscribe_btn(message: Message):
#     remove_sub(CHAT_IDS, message.chat.id)
#     await message.answer("Подписка отключена 📴")
#
# # --- Мастер «Добавить праздник» ---
# class AddHoliday(StatesGroup):
#     waiting_date = State()
#     waiting_title = State()
#     waiting_repeat = State()
#
# @dp.message(F.text.lower().in_({"➕ добавить праздник", "добавить праздник"}))
# async def add_holiday_start(message: Message, state: FSMContext):
#     await state.set_state(AddHoliday.waiting_date)
#     await message.answer(
#         "Введите дату в формате YYYY-MM-DD (например, 2025-11-04):",
#         reply_markup=ReplyKeyboardRemove(),
#     )
#
# @dp.message(AddHoliday.waiting_date)
# async def add_holiday_date(message: Message, state: FSMContext):
#     try:
#         datetime.strptime(message.text.strip(), "%Y-%m-%d")
#     except Exception:
#         await message.answer("Неверный формат. Введите дату как YYYY-MM-DD (например, 2025-11-04).")
#         return
#     await state.update_data(date_str=message.text.strip())
#     await state.set_state(AddHoliday.waiting_title)
#     await message.answer("Введите короткое название праздника:")
#
# @dp.message(AddHoliday.waiting_title)
# async def add_holiday_title(message: Message, state: FSMContext):
#     title = message.text.strip()
#     if not title:
#         await message.answer("Название пустое. Введите короткое название праздника:")
#         return
#     await state.update_data(title=title)
#     await state.set_state(AddHoliday.waiting_repeat)
#     kb = ReplyKeyboardMarkup(
#         keyboard=[[KeyboardButton(text="Ежегодно")], [KeyboardButton(text="Один раз")]],
#         resize_keyboard=True,
#     )
#     await message.answer("Повторять ежегодно?", reply_markup=kb)
#
# @dp.message(AddHoliday.waiting_repeat, F.text.lower().in_({"ежегодно", "один раз"}))
# async def add_holiday_finish(message: Message, state: FSMContext):
#     data = await state.get_data()
#     repeat = "annual" if message.text.lower() == "ежегодно" else "once"
#     try:
#         rec = add_custom(data["date_str"], data["title"], repeat=repeat)
#     except Exception as e:
#         await state.clear()
#         await message.answer(f"Не удалось сохранить: {e}", reply_markup=MAIN_KB)
#         return
#     await state.clear()
#     await message.answer(
#         f"Готово! Сохранён праздник:\n• {rec['title']} — {rec['date']} "
#         f"({'ежегодно' if rec['repeat']=='annual' else 'один раз'})",
#         reply_markup=MAIN_KB,
#     )
#
# # --- «Поиск по дате» ---
# class SearchByDate(StatesGroup):
#     waiting_date = State()
#
# @dp.message(F.text.lower().in_({"🔎 поиск по дате", "поиск по дате"}))
# async def search_by_date_start(message: Message, state: FSMContext):
#     await state.set_state(SearchByDate.waiting_date)
#     await message.answer(
#         "Введите дату:\n• форматы: 4 ноября / 04 ноября / 21.01",
#         reply_markup=ReplyKeyboardRemove(),
#     )
#
# @dp.message(SearchByDate.waiting_date)
# async def search_by_date_finish(message: Message, state: FSMContext):
#     text = (message.text or "").strip()
#     dt = parse_ru_day_month(text) or parse_ddmm(text)
#     if not dt:
#         await message.answer("Не понимаю формат. Введите «4 ноября» или «21.01».")
#         return
#
#     target_date = dt.date()
#
#     # Детальные праздники (ссылки + описания) с Calend.ru
#     details = get_holiday_details_for_date(target_date)
#
#     # Твои «свои»
#     custom_list = get_for_date(target_date)
#     custom_lines = [f"• (своё) <b>{t}</b>" for t in custom_list]
#
#     pretty = target_date.strftime("%d.%m.%Y")
#     text = f"<b>🔎 Праздники на дату {pretty}:</b>\n" + format_details_html(details)
#     if custom_lines:
#         text += "\n" + "\n".join(custom_lines)
#
#     await message.answer(text, reply_markup=MAIN_KB, parse_mode="HTML", disable_web_page_preview=True)
#     await state.clear()
#
# # --- Фоллбек: если просто прислали дату текстом ---
# @dp.message(F.text)
# async def fallback_date_parser(message: Message):
#     dt = parse_ru_day_month(message.text) or parse_ddmm(message.text)
#     if not dt:
#         return
#     target_date = dt.date()
#     details = get_holiday_details_for_date(target_date)
#     custom_list = get_for_date(target_date)
#     custom_lines = [f"• (своё) <b>{t}</b>" for t in custom_list]
#     pretty = target_date.strftime("%d.%m.%Y")
#     text = f"<b>🔎 Праздники на дату {pretty}:</b>\n" + format_details_html(details)
#     if custom_lines:
#         text += "\n" + "\n".join(custom_lines)
#     await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
#
# # --- Запуск ---
# async def main():
#     bot = Bot(token=TOKEN)
#     scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))
#     scheduler.add_job(broadcast_daily, "cron", hour=9, minute=0, args=[bot])
#     scheduler.start()
#     await dp.start_polling(bot)
#
# if __name__ == "__main__":
#     asyncio.run(main())
#
