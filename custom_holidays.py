# custom_holidays.py
import json
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict

CUSTOM_FILE = Path("custom_holidays.json")


def _read() -> List[Dict]:
    if CUSTOM_FILE.exists():
        try:
            return json.loads(CUSTOM_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _write(rows: List[Dict]) -> None:
    CUSTOM_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def add_custom(date_str: str, title: str, repeat: str = "once") -> Dict:
    """
    Добавляет праздник.
    date_str: 'YYYY-MM-DD'
    title: короткое название
    repeat: 'annual' или 'once'
    """
    # валидация даты и нормализация
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    title = (title or "").strip()
    if not title:
        raise ValueError("Пустое название")

    repeat = "annual" if repeat == "annual" else "once"

    rows = _read()
    rec = {"date": d.isoformat(), "title": title, "repeat": repeat}

    # дедуп по дате+названию
    for r in rows:
        if r["date"] == rec["date"] and r["title"].lower() == rec["title"].lower():
            return r  # уже есть — просто возвращаем

    rows.append(rec)
    _write(rows)
    return rec


def get_for_date(day: date) -> List[str]:
    """
    Возвращает список названий праздников на конкретную дату,
    учитывая ежегодные повторы.
    """
    rows = _read()
    out = []
    for r in rows:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        except Exception:
            continue

        if r.get("repeat") == "annual":
            if (d.month, d.day) == (day.month, day.day):
                out.append(r.get("title", ""))
        else:
            if d == day:
                out.append(r.get("title", ""))

    return [t for t in out if t]
