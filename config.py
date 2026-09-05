import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CREATOR_ID = int(os.getenv('CREATOR_ID', 0))
CHIEF_ID = int(os.getenv('CHIEF_ID', 0))
GROUP_ID = int(os.getenv('GROUP_ID', 0))
DATABASE_URL = os.getenv('DATABASE_URL')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")
if CREATOR_ID == 0:
    raise ValueError("CREATOR_ID не найден в переменных окружения!")
if CHIEF_ID == 0:
    raise ValueError("CHIEF_ID не найден в переменных окружения!")
if GROUP_ID == 0:
    raise ValueError("GROUP_ID не найден в переменных окружения!")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден в переменных окружения!")

DATA_DIR = os.getenv('DATA_DIR', 'data')
DATA_FILE = os.path.join(DATA_DIR, 'data.json')

MAX_REQUEST_TITLE_LENGTH = 255
DATE_FORMAT = '%d.%m.%Y %H:%M'

PLATFORMS = ['youtube', 'twitch', 'tiktok']
REQUIRED_FIELDS = ['screenshot', 'media_link', 'channel_name', 'subscribers', 'contact_link']
