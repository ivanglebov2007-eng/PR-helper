import logging
import asyncio
import warnings
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
from telegram.warnings import PTBUserWarning

from config import BOT_TOKEN, DATABASE_URL
from database import Database
from handlers import *
from states import *

warnings.filterwarnings("ignore", category=PTBUserWarning)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация БД
db = Database(DATABASE_URL)

async def main():
    logger.info("🚀 Запуск...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(120)
        .read_timeout(120)
        .build()
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('new_request', new_request_start))
    application.add_handler(CommandHandler('my_requests', my_requests))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    logger.info("✅ Запускаем polling...")

    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("🎯 Бот работает!")
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await application.stop()
        await application.shutdown()
        db.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановлен")
