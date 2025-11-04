# subscriptions.py
import json
from pathlib import Path
from typing import Set

SUBS_FILE = Path("subs.json")


def load_subs() -> Set[int]:
    """Загружает множество chat_id из файла (если файла нет — пустое множество)."""
    if SUBS_FILE.exists():
        try:
            data = json.loads(SUBS_FILE.read_text(encoding="utf-8"))
            return set(int(x) for x in data)
        except Exception:
            return set()
    return set()


def save_subs(chat_ids: Set[int]) -> None:
    """Сохраняет множество chat_id в файл (как отсортированный список)."""
    SUBS_FILE.write_text(json.dumps(sorted(chat_ids)), encoding="utf-8")


def add_sub(chat_ids: Set[int], chat_id: int) -> Set[int]:
    """Добавляет chat_id в подписку и сразу сохраняет."""
    chat_ids.add(int(chat_id))
    save_subs(chat_ids)
    return chat_ids


def remove_sub(chat_ids: Set[int], chat_id: int) -> Set[int]:
    """Удаляет chat_id из подписки и сразу сохраняет."""
    chat_ids.discard(int(chat_id))
    save_subs(chat_ids)
    return chat_ids
