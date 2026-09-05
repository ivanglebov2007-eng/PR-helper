#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from telegram.request import HTTPXRequest
import httpx

from config import BOT_TOKEN
from database import Database
from handlers import *
from states import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    """Запуск бота с повторными попытками"""
    logger.info("Запуск бота...")
    
    # Загружаем базу данных
    db.load()
    logger.info(f"Загружено {len(db.pr_managers)} PR менеджеров")
    
    # Настройка клиента с увеличенным таймаутом
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=30.0),
        limits=httpx.Limits(max_keepalive_connections=5)
    )
    request = HTTPXRequest(client=client)
    
    # Создаем приложение
    application = Application.builder()\
        .token(BOT_TOKEN)\
        .request(request)\
        .connect_timeout(60.0)\
        .read_timeout(60.0)\
        .build()
    
    # Conversation handler
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
    
    # Добавляем обработчики
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
    
    # Запускаем с повторными попытками
    logger.info("Бот запущен и готов к работе!")
    
    # Пытаемся запустить с повторными попытками
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            await application.initialize()
            await application.start()
            await application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            # Ждем пока бот работает
            while True:
                await asyncio.sleep(1)
        except Exception as e:
            retry_count += 1
            logger.error(f"Ошибка (попытка {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                logger.info(f"Перезапуск через 5 секунд...")
                await asyncio.sleep(5)
            else:
                logger.error("Превышено максимальное количество попыток")
                break

if __name__ == '__main__':
    asyncio.run(main())