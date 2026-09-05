import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Константы (читаем из .env)
BOT_TOKEN = os.getenv('BOT_TOKEN')
CREATOR_ID = int(os.getenv('CREATOR_ID', 0))
CHIEF_ID = int(os.getenv('CHIEF_ID', 0))
GROUP_ID = int(os.getenv('GROUP_ID', 0))

# Проверка обязательных переменных
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле!")
if CREATOR_ID == 0:
    raise ValueError("CREATOR_ID не найден в .env файле!")
if CHIEF_ID == 0:
    raise ValueError("CHIEF_ID не найден в .env файле!")
if GROUP_ID == 0:
    raise ValueError("GROUP_ID не найден в .env файле!")

# Пути к файлам
DATA_FILE = os.getenv('DATA_FILE', 'data.json')
LOG_FILE = os.getenv('LOG_FILE', 'bot.log')

# Настройки бота
MAX_REQUEST_TITLE_LENGTH = 255
DATE_FORMAT = '%d.%m.%Y %H:%M'

# Платформы для проверки ссылок
PLATFORMS = ['youtube', 'twitch', 'tiktok']

# Обязательные поля для запроса
REQUIRED_FIELDS = ['screenshot', 'media_link', 'channel_name', 'subscribers', 'contact_link']
