import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Константы
BOT_TOKEN = os.getenv('BOT_TOKEN', "8841364478:AAGuMnVP3d3InObUVXfsMapRM0caDpPhZbo")
CREATOR_ID = int(os.getenv('CREATOR_ID', 1138809734))
CHIEF_ID = int(os.getenv('CHIEF_ID', 694679481))
GROUP_ID = int(os.getenv('GROUP_ID', -1001234567890))  # ЗАМЕНИТЕ!

# Настройки прокси (для обхода блокировок)
# Раскомментируйте если используете прокси
# PROXY_URL = os.getenv('PROXY_URL', 'socks5://127.0.0.1:1080')
# PROXY_ENABLED = bool(os.getenv('PROXY_ENABLED', False))

# Пути к файлам
DATA_FILE = 'data.json'
LOG_FILE = 'bot.log'

# Настройки бота
MAX_REQUEST_TITLE_LENGTH = 255
DATE_FORMAT = '%d.%m.%Y %H:%M'

# Платформы для проверки ссылок
PLATFORMS = ['youtube', 'twitch', 'tiktok']

# Обязательные поля для запроса
REQUIRED_FIELDS = ['screenshot', 'media_link', 'channel_name', 'subscribers', 'contact_link']

# Настройки подключения
CONNECTION_TIMEOUT = 120
READ_TIMEOUT = 120
WRITE_TIMEOUT = 120