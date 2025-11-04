# holidays.py
import datetime
import re
from zoneinfo import ZoneInfo
import requests
import feedparser
from html import unescape
from typing import List, Dict, Tuple

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

DATE_RE = re.compile(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", re.IGNORECASE)

A_HOLIDAY_RE = re.compile(
    r'<a\s+href="(https?://(?:www\.)?calend\.ru/holidays/[^"]+)"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)
META_DESC_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _title_date(title: str) -> datetime.date | None:
    m = DATE_RE.search(title or "")
    if not m:
        return None
    day = int(m.group(1))
    month = RU_MONTHS.get(m.group(2).lower())
    year = int(m.group(3))
    if not month:
        return None
    return datetime.date(year, month, day)


def _fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def get_holidays_today() -> List[str]:
    url = "https://www.calend.ru/calendar/feed/"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    feed = feedparser.parse(resp.content)
    entries = list(getattr(feed, "entries", []))
    today = datetime.datetime.now(ZoneInfo("Europe/Moscow")).date()
    results = []
    for e in entries:
        title = (getattr(e, "title", "") or "").strip()
        d = _title_date(title)
        if d == today and title:
            results.append(title)
    return results or ["Сегодня нет записей"]


def get_holidays_for_date(target: datetime.date) -> List[str]:
    url = "https://www.calend.ru/calendar/feed/"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    feed = feedparser.parse(resp.content)
    entries = list(getattr(feed, "entries", []))
    results = []
    for e in entries:
        title = (getattr(e, "title", "") or "").strip()
        d = _title_date(title)
        if d == target and title:
            results.append(title)
    return results


def _extract_date_page_url_for(target: datetime.date) -> str | None:
    url = "https://www.calend.ru/calendar/feed/"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    feed = feedparser.parse(resp.content)
    for e in getattr(feed, "entries", []):
        title = (getattr(e, "title", "") or "").strip()
        d = _title_date(title)
        if d == target:
            return getattr(e, "link", None)
    return None


def _shorten(txt: str, limit: int = 200) -> str:
    txt = unescape(re.sub(r"\s+", " ", txt)).strip()
    if len(txt) <= limit:
        return txt
    return txt[: limit - 1].rstrip() + "…"


def get_holiday_details_grouped(
    target: datetime.date,
    max_items: int = 20,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Возвращает кортеж списков:
      (rus_list, other_list), где каждый элемент: {title, url, desc}
    Для «других» desc тоже подтягиваем, но бот его не показывает.
    """
    day_url = _extract_date_page_url_for(target)
    if not day_url:
        return [], []

    html = _fetch(day_url)

    # уникальные ссылки на праздники
    seen = set()
    base_items: List[Dict] = []
    for m in A_HOLIDAY_RE.finditer(html):
        url = m.group(1)
        title = unescape(m.group(2)).strip()
        if url in seen:
            continue
        seen.add(url)
        base_items.append({"title": title, "url": url})
        if len(base_items) >= max_items:
            break

    rus, other = [], []
    for it in base_items:
        try:
            page = _fetch(it["url"])
            mm = META_DESC_RE.search(page)
            desc = _shorten(mm.group(1)) if mm else ""
        except Exception:
            desc = ""

        title_l = it["title"].lower()
        desc_l = desc.lower()
        is_russia = ("росси" in title_l) or ("росси" in desc_l)  # Россия/России/российский…

        enriched = {"title": it["title"], "url": it["url"], "desc": desc}
        if is_russia:
            rus.append(enriched)
        else:
            other.append(enriched)

    return rus, other


def get_holiday_details_for_date(target: datetime.date, max_items: int = 10) -> List[Dict]:
    """
    Старая функция (оставлена для совместимости): просто соединяет все праздники.
    """
    rus, other = get_holiday_details_grouped(target, max_items)
    return rus + other



# # holidays.py
# import datetime
# import re
# from zoneinfo import ZoneInfo
# import requests
# import feedparser
# from html import unescape
# from typing import List, Dict
#
# # выглядим как обычный браузер — Calend.ru иногда режет без UA
# HEADERS = {
#     "User-Agent": (
#         "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
#         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
#     )
# }
#
# # соответствие русских месяцев числам
# RU_MONTHS = {
#     "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
#     "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
# }
#
# # вытаскиваем дату вида "4 ноября 2025" из заголовка ленты
# DATE_RE = re.compile(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", re.IGNORECASE)
#
#
# def _title_date(title: str) -> datetime.date | None:
#     m = DATE_RE.search(title or "")
#     if not m:
#         return None
#     day = int(m.group(1))
#     month = RU_MONTHS.get(m.group(2).lower())
#     year = int(m.group(3))
#     if not month:
#         return None
#     return datetime.date(year, month, day)
#
#
# def _fetch(url: str) -> str:
#     resp = requests.get(url, headers=HEADERS, timeout=20)
#     resp.raise_for_status()
#     return resp.text
#
#
# def get_holidays_today() -> List[str]:
#     """
#     Короткий список заголовков «на сегодня» (по Москве) из RSS «Ежедневник».
#     """
#     url = "https://www.calend.ru/calendar/feed/"
#     resp = requests.get(url, headers=HEADERS, timeout=15)
#     feed = feedparser.parse(resp.content)
#     entries = list(getattr(feed, "entries", []))
#
#     today = datetime.datetime.now(ZoneInfo("Europe/Moscow")).date()
#
#     results = []
#     for e in entries:
#         title = (getattr(e, "title", "") or "").strip()
#         d = _title_date(title)
#         if d == today and title:
#             results.append(title)
#
#     return results or ["Сегодня нет записей"]
#
#
# def get_holidays_for_date(target: datetime.date) -> List[str]:
#     """
#     Короткий список заголовков за указанную дату (по дате из заголовка RSS).
#     """
#     url = "https://www.calend.ru/calendar/feed/"
#     resp = requests.get(url, headers=HEADERS, timeout=15)
#     feed = feedparser.parse(resp.content)
#     entries = list(getattr(feed, "entries", []))
#
#     results = []
#     for e in entries:
#         title = (getattr(e, "title", "") or "").strip()
#         d = _title_date(title)
#         if d == target and title:
#             results.append(title)
#     return results
#
#
# # -------------------- обогащение: ссылки и описания --------------------
#
# A_HOLIDAY_RE = re.compile(
#     r'<a\s+href="(https?://(?:www\.)?calend\.ru/holidays/[^"]+)"[^>]*>([^<]+)</a>',
#     re.IGNORECASE,
# )
#
# META_DESC_RE = re.compile(
#     r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
#     re.IGNORECASE,
# )
#
# def _extract_date_page_url_for(target: datetime.date) -> str | None:
#     """
#     Находим в RSS запись за target и берём link — это страница дня,
#     где перечислены все события/праздники.
#     """
#     url = "https://www.calend.ru/calendar/feed/"
#     resp = requests.get(url, headers=HEADERS, timeout=15)
#     feed = feedparser.parse(resp.content)
#     for e in getattr(feed, "entries", []):
#         title = (getattr(e, "title", "") or "").strip()
#         d = _title_date(title)
#         if d == target:
#             return getattr(e, "link", None)
#     return None
#
#
# def _shorten(txt: str, limit: int = 180) -> str:
#     txt = unescape(re.sub(r"\s+", " ", txt)).strip()
#     if len(txt) <= limit:
#         return txt
#     return txt[: limit - 1].rstrip() + "…"
#
#
# def get_holiday_details_for_date(target: datetime.date, max_items: int = 10) -> List[Dict]:
#     """
#     Возвращает список словарей: {title, url, desc} для указанной даты.
#     Алгоритм:
#       1) Ищем в RSS ссылку на страницу конкретного дня.
#       2) Парсим на ней ссылки на отдельные праздники (раздел /holidays/…).
#       3) Для каждой страницы праздника берём meta-description как краткое описание.
#     """
#     day_url = _extract_date_page_url_for(target)
#     if not day_url:
#         return []
#
#     html = _fetch(day_url)
#
#     # собираем уникальные ссылки на праздники с названиями
#     seen = set()
#     items: List[Dict] = []
#     for m in A_HOLIDAY_RE.finditer(html):
#         url = m.group(1)
#         title = unescape(m.group(2)).strip()
#         if url in seen:
#             continue
#         seen.add(url)
#         items.append({"title": title, "url": url})
#         if len(items) >= max_items:
#             break
#
#     # подтягиваем короткие описания из meta[name=description]
#     out: List[Dict] = []
#     for it in items:
#         try:
#             page = _fetch(it["url"])
#             mm = META_DESC_RE.search(page)
#             desc = _shorten(mm.group(1)) if mm else ""
#         except Exception:
#             desc = ""
#         out.append({"title": it["title"], "url": it["url"], "desc": desc})
#
#     return out
#
#
