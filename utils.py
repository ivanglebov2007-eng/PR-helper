import re
from typing import Optional
from datetime import datetime
from config import DATE_FORMAT, PLATFORMS

def validate_media_link(url: str) -> bool:
    """Проверка ссылки на медиа-платформу"""
    url = url.lower()
    return any(platform in url for platform in PLATFORMS) and (url.startswith('http://') or url.startswith('https://'))

def validate_url(url: str) -> bool:
    """Базовая проверка URL"""
    return url.startswith('http://') or url.startswith('https://')

def format_subscribers(count: str) -> str:
    """Форматирование числа подписчиков"""
    try:
        num = int(count.replace(' ', '').replace(',', '').replace('.', ''))
        if num < 0:
            return count
        return f"{num:,}".replace(',', ' ')
    except ValueError:
        return count

def format_date(iso_date: str) -> str:
    """Форматирование даты"""
    try:
        dt = datetime.fromisoformat(iso_date)
        return dt.strftime(DATE_FORMAT)
    except:
        return iso_date

def sanitize_text(text: str) -> str:
    """Очистка текста от опасных символов"""
    if not text:
        return ""
    # Экранируем HTML-символы
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def truncate_text(text: str, max_length: int = 100) -> str:
    """Обрезка текста до указанной длины"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + '...'

def extract_username(text: str) -> str:
    """Извлечение username из текста"""
    # Удаляем @ если есть
    username = text.strip()
    if username.startswith('@'):
        username = username[1:]
    return username

def is_valid_topic_id(topic_id: str) -> bool:
    """Проверка валидности ID темы"""
    try:
        int(topic_id)
        return True
    except ValueError:
        return False