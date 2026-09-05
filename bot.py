#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import asyncio
import warnings
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler
)
from telegram.warnings import PTBUserWarning

from config import BOT_TOKEN
from database import Database
from handlers import *
from states import *

# Игнорируем предупреждение PTB
warnings.filterwarnings(
    action="ignore",
    message=r".*CallbackQueryHandler.*",
    category=PTBUserWarning
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database()

async def main():
    """Запуск бота"""
    logger.info("🚀 Запуск бота...")
    
    db.load()
    logger.info(f"📊 Загружено {len(db.pr_managers)} PR менеджеров")
    
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(120.0)
        .read_timeout(120.0)
        .write_timeout(120.0)
        .build()
    )
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('new_request', new_request_start),
            CallbackQueryHandler(button_callback, pattern='^new_request$')
        ],
        states={
            SCREENSHOT: [
                MessageHandler(filters.PHOTO, handle_screenshot),
                CommandHandler('cancel', cancel)
            ],
            MEDIA_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_media_link),
                CommandHandler('cancel', cancel)
            ],
            CHANNEL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_name),
                CommandHandler('cancel', cancel)
            ],
            SUBSCRIBERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_subscribers),
                CommandHandler('cancel', cancel)
            ],
            CONTACT_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contact_link),
                CommandHandler('cancel', cancel)
            ],
            CONDITIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conditions),
                CommandHandler('skip', skip_conditions),
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(button_callback, pattern='^skip$'),
                CallbackQueryHandler(button_callback, pattern='^cancel$')
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="new_request_conv",
        persistent=False
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('my_requests', my_requests))
    application.add_handler(CommandHandler('close_topic', close_topic))
    application.add_handler(CommandHandler('search', search_topics))
    application.add_handler(CommandHandler('add_pr_by_id', add_pr_by_id))
    application.add_handler(CommandHandler('add_dep', add_dep))
    application.add_handler(CommandHandler('remove_user', remove_user))
    application.add_handler(CommandHandler('list_users', list_users))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    logger.info("✅ Бот инициализирован, запускаем polling...")
    
    try:
        await application.initialize()
        await application.start()
        
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        logger.info("🎯 Бот успешно запущен и слушает сообщения!")
        
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        raise
    
    finally:
        await application.stop()
        await application.shutdown()
        logger.info("🛑 Бот остановлен")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка: {e}")
