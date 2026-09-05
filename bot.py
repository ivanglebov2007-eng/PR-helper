#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler
)
import httpx

from config import BOT_TOKEN
from database import Database
from handlers import *
from states import *

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database()

async def main():
    """Запуск бота с повторными попытками"""
    logger.info("🚀 Запуск бота...")
    
    # Загружаем базу данных
    db.load()
    logger.info(f"📊 Загружено {len(db.pr_managers)} PR менеджеров")
    
    # === НАСТРОЙКА ПРОКСИ (раскомментируйте если нужно) ===
    # Если Telegram заблокирован, используйте прокси:
    # 1. SOCKS5 прокси (через Tor или VPN):
    # proxy_url = "socks5://127.0.0.1:1080"
    # 2. HTTP прокси:
    # proxy_url = "http://127.0.0.1:8080"
    
    # Создаем приложение с увеличенными таймаутами
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(120.0)
        .read_timeout(120.0)
        .write_timeout(120.0)
        .build()
    )
    
    # Если используете прокси, добавьте это:
    # from telegram.request import HTTPXRequest
    # import httpx
    # 
    # proxy_url = "socks5://127.0.0.1:1080"  # Ваш прокси
    # http_client = httpx.AsyncClient(
    #     proxy=proxy_url,
    #     timeout=httpx.Timeout(120.0, connect=60.0)
    # )
    # request = HTTPXRequest(http_client=http_client)
    # application = (
    #     Application.builder()
    #     .token(BOT_TOKEN)
    #     .request(request)
    #     .connect_timeout(120.0)
    #     .read_timeout(120.0)
    #     .write_timeout(120.0)
    #     .build()
    # )
    
    # Conversation handler для создания запроса
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
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('my_requests', my_requests))
    application.add_handler(CommandHandler('close_topic', close_topic))
    application.add_handler(CommandHandler('search', search_topics))
    application.add_handler(CommandHandler('add_pr_by_id', add_pr_by_id))
    application.add_handler(CommandHandler('add_dep', add_dep))
    application.add_handler(CommandHandler('remove_user', remove_user))
    application.add_handler(CommandHandler('list_users', list_users))
    
    # Обработчик callback-запросов
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота с повторными попытками при ошибках
    logger.info("✅ Бот инициализирован, запускаем polling...")
    
    max_retries = 5
    retry_count = 0
    retry_delay = 10  # секунд
    
    while retry_count < max_retries:
        try:
            # Запускаем бота
            await application.initialize()
            await application.start()
            
            # Запускаем polling
            await application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            
            logger.info("🎯 Бот успешно запущен и слушает сообщения!")
            
            # Бесконечный цикл ожидания
            while True:
                await asyncio.sleep(1)
                
        except httpx.ConnectTimeout as e:
            retry_count += 1
            logger.error(f"❌ Ошибка подключения (попытка {retry_count}/{max_retries}): {e}")
            
            if retry_count < max_retries:
                logger.info(f"⏳ Повторная попытка через {retry_delay} секунд...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Увеличиваем задержку
            else:
                logger.error("❌ Превышено максимальное количество попыток подключения")
                break
                
        except Exception as e:
            retry_count += 1
            logger.error(f"❌ Критическая ошибка (попытка {retry_count}/{max_retries}): {e}")
            
            if retry_count < max_retries:
                logger.info(f"⏳ Перезапуск через {retry_delay} секунд...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("❌ Превышено максимальное количество попыток")
                break
    
    # Останавливаем бота
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