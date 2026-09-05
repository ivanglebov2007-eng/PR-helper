import logging
from datetime import datetime
from typing import Optional

# Исправленный импорт для новой версии
from telegram import Update
from telegram.constants import ParseMode  # <-- ИЗМЕНЕНО!
from telegram.ext import ContextTypes, ConversationHandler

from config import CHIEF_ID, CREATOR_ID, GROUP_ID, REQUIRED_FIELDS
from database import Database, RequestData
from states import *
from keyboards import get_main_keyboard, get_cancel_keyboard, get_skip_keyboard
from utils import (
    validate_media_link, validate_url, format_subscribers,
    format_date, sanitize_text, truncate_text
)

logger = logging.getLogger(__name__)
db = Database()

# ============ Проверка прав ============

def is_chief(user_id: int) -> bool:
    return user_id == CHIEF_ID

def is_dep_chief(user_id: int) -> bool:
    return user_id in db.dep_chiefs

def is_admin(user_id: int) -> bool:
    return is_chief(user_id) or is_dep_chief(user_id)

def is_pr_manager(user_id: int) -> bool:
    return user_id in db.pr_managers or is_admin(user_id)

def is_creator(user_id: int) -> bool:
    return user_id == CREATOR_ID

# ============ Основные команды ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.effective_user
    user_id = user.id
    
    # Проверяем доступ
    if not is_pr_manager(user_id) and not is_creator(user_id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\n\n"
            "Обратитесь к Chief PR Manager для получения доступа.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Приветственное сообщение
    welcome_text = f"👋 <b>Добро пожаловать, {sanitize_text(user.full_name)}!</b>\n\n"
    
    if is_creator(user_id):
        welcome_text += (
            "🤖 <b>Вы - Создатель бота</b>\n\n"
            "Доступны все функции управления."
        )
    elif is_admin(user_id):
        welcome_text += "👑 <b>Вы - администратор</b>\n\nДоступны все функции управления."
    else:
        welcome_text += "📝 <b>Вы - PR Manager</b>\n\nДоступно создание запросов и просмотр своих заявок."
    
    keyboard = get_main_keyboard(
        is_admin=is_admin(user_id),
        is_creator=is_creator(user_id)
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

# ============ Создание запроса ============

async def new_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания нового запроса"""
    user_id = update.effective_user.id
    
    if not is_pr_manager(user_id):
        await update.message.reply_text("❌ У вас нет прав для создания запросов.")
        return ConversationHandler.END
    
    # Очищаем временные данные
    db.set_pending_request(user_id, {})
    
    await update.message.reply_text(
        "📝 <b>Создание нового запроса</b>\n\n"
        "Шаг 1 из 6: Отправьте <b>скриншот переписки с медиа</b> (файл изображения):\n\n"
        "Для отмены отправьте /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    return SCREENSHOT

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка скриншота"""
    user_id = update.effective_user.id
    photo = update.message.photo
    
    if not photo:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте скриншот как изображение (фото).\n"
            "Или отправьте /cancel для отмены.",
            reply_markup=get_cancel_keyboard()
        )
        return SCREENSHOT
    
    try:
        # Получаем ссылку на фото (сохраняем в телеграме)
        file = await photo[-1].get_file()
        file_url = file.file_path
        
        # Сохраняем во временные данные
        pending = db.get_pending_request(user_id) or {}
        pending['screenshot'] = file_url
        db.set_pending_request(user_id, pending)
        
        await update.message.reply_text(
            "✅ Скриншот получен!\n\n"
            "Шаг 2 из 6: Отправьте <b>ссылку на канал</b> (YouTube, Twitch или TikTok):\n\n"
            "Пример: https://www.youtube.com/@channel",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return MEDIA_LINK
        
    except Exception as e:
        logger.error(f"Ошибка обработки скриншота: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте еще раз или отправьте /cancel"
        )
        return SCREENSHOT

async def handle_media_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылки на медиа"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not validate_media_link(text):
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте корректную ссылку на YouTube, Twitch или TikTok.\n"
            "Ссылка должна начинаться с http:// или https://\n\n"
            "Или отправьте /cancel для отмены.",
            reply_markup=get_cancel_keyboard()
        )
        return MEDIA_LINK
    
    pending = db.get_pending_request(user_id) or {}
    pending['media_link'] = text
    db.set_pending_request(user_id, pending)
    
    await update.message.reply_text(
        "✅ Ссылка получена!\n\n"
        "Шаг 3 из 6: Отправьте <b>название канала</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    return CHANNEL_NAME

async def handle_channel_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия канала"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not text:
        await update.message.reply_text(
            "❌ Название канала не может быть пустым.\n"
            "Отправьте /cancel для отмены.",
            reply_markup=get_cancel_keyboard()
        )
        return CHANNEL_NAME
    
    pending = db.get_pending_request(user_id) or {}
    pending['channel_name'] = sanitize_text(text)
    db.set_pending_request(user_id, pending)
    
    await update.message.reply_text(
        "✅ Название получено!\n\n"
        "Шаг 4 из 6: Отправьте <b>количество подписчиков</b> (только цифры):\n\n"
        "Примеры: 10000 или 10,000",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    return SUBSCRIBERS

async def handle_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка количества подписчиков"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    try:
        subs = int(text.replace(' ', '').replace(',', '').replace('.', ''))
        if subs < 0:
            raise ValueError
        formatted_subs = f"{subs:,}".replace(',', ' ')
    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте число (количество подписчиков).\n"
            "Примеры: 10000 или 10,000\n\n"
            "Отправьте /cancel для отмены.",
            reply_markup=get_cancel_keyboard()
        )
        return SUBSCRIBERS
    
    pending = db.get_pending_request(user_id) or {}
    pending['subscribers'] = formatted_subs
    db.set_pending_request(user_id, pending)
    
    await update.message.reply_text(
        f"✅ Количество подписчиков: {formatted_subs}\n\n"
        "Шаг 5 из 6: Отправьте <b>ссылку на способ связи с медиа</b> "
        "(Telegram, email, сайт и т.д.):\n\n"
        "Пример: https://t.me/username",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    return CONTACT_LINK

async def handle_contact_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылки на способ связи"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not text:
        await update.message.reply_text(
            "❌ Ссылка не может быть пустой.\n"
            "Отправьте /cancel для отмены.",
            reply_markup=get_cancel_keyboard()
        )
        return CONTACT_LINK
    
    # Добавляем https если нет
    if not text.startswith(('http://', 'https://')):
        text = 'https://' + text
    
    pending = db.get_pending_request(user_id) or {}
    pending['contact_link'] = text
    db.set_pending_request(user_id, pending)
    
    await update.message.reply_text(
        "✅ Ссылка получена!\n\n"
        "Шаг 6 из 6: Отправьте <b>желаемые условия от медиа-партнера</b> "
        "(можно пропустить, нажав /skip):",
        parse_mode=ParseMode.HTML,
        reply_markup=get_skip_keyboard()
    )
    return CONDITIONS

async def handle_conditions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка условий"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    pending = db.get_pending_request(user_id) or {}
    pending['conditions'] = sanitize_text(text) if text else "Не указаны"
    db.set_pending_request(user_id, pending)
    
    # Завершаем создание запроса
    return await finish_request(update, context)

async def skip_conditions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропуск условий"""
    user_id = update.effective_user.id
    pending = db.get_pending_request(user_id) or {}
    pending['conditions'] = "Не указаны"
    db.set_pending_request(user_id, pending)
    
    await update.message.reply_text("⏭️ Условия пропущены.")
    return await finish_request(update, context)

async def finish_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение создания запроса"""
    user = update.effective_user
    user_id = user.id
    pending = db.get_pending_request(user_id) or {}
    
    # Проверяем наличие всех обязательных полей
    missing = [f for f in REQUIRED_FIELDS if f not in pending]
    if missing:
        await update.message.reply_text(
            f"❌ Ошибка: не все обязательные поля заполнены: {', '.join(missing)}\n"
            "Пожалуйста, начните заново с /new_request"
        )
        db.clear_pending_request(user_id)
        return ConversationHandler.END
    
    # Создаем тему в группе
    topic_id = await create_request_topic(update, context, pending)
    
    if topic_id:
        # Сохраняем данные в БД
        request_data = RequestData(
            screenshot=pending['screenshot'],
            media_link=pending['media_link'],
            channel_name=pending['channel_name'],
            subscribers=pending['subscribers'],
            contact_link=pending['contact_link'],
            conditions=pending['conditions'],
            user_id=user_id,
            created_at=datetime.now().isoformat()
        )
        db.add_topic(topic_id, request_data)
        
        await update.message.reply_text(
            "✅ <b>Запрос успешно создан!</b>\n\n"
            f"📌 Тема создана в группе и отмечена для Chief PR Manager.\n"
            f"🆔 ID темы: <code>{topic_id}</code>\n\n"
            "Ожидайте ответа от руководства.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось создать запрос. Пожалуйста, попробуйте позже."
        )
    
    db.clear_pending_request(user_id)
    return ConversationHandler.END

async def create_request_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, request_data: dict) -> Optional[int]:
    """Создание темы в группе с запросом"""
    user = update.effective_user
    topic_title = f"Запрос от {user.full_name} - {request_data['channel_name']}"
    
    try:
        # Создаем тему
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=topic_title[:255]
        )
        topic_id = topic.message_thread_id
        
        # Формируем сообщение
        message_text = (
            f"📢 <b>НОВЫЙ ЗАПРОС НА МЕДИА-ПАРТНЕРСТВО</b>\n\n"
            f"👤 <b>PR Менеджер:</b> {sanitize_text(user.full_name)} "
            f"(@{user.username or 'нет username'})\n"
            f"📱 <b>ID:</b> <code>{user.id}</code>\n"
            f"📅 <b>Дата:</b> {format_date(datetime.now().isoformat())}\n\n"
            f"📌 <b>Название канала:</b> {sanitize_text(request_data['channel_name'])}\n"
            f"👥 <b>Подписчиков:</b> {request_data['subscribers']}\n"
            f"🔗 <b>Ссылка на медиа:</b> <a href='{request_data['media_link']}'>Ссылка</a>\n"
            f"📎 <b>Скриншот переписки:</b> <a href='{request_data['screenshot']}'>Смотреть</a>\n"
            f"📞 <b>Способ связи:</b> <a href='{request_data['contact_link']}'>Ссылка</a>\n"
            f"📝 <b>Желаемые условия:</b>\n{sanitize_text(request_data['conditions'])}\n\n"
            f"🔔 <b>Ожидайте ответа от руководства!</b>"
        )
        
        # Отправляем сообщение в тему
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=message_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        # Пинуем чифа и деп.чифа
        mentions = [f"<a href='tg://user?id={CHIEF_ID}'>Chief</a>"]
        for dep_id in db.dep_chiefs:
            mentions.append(f"<a href='tg://user?id={dep_id}'>Dep.Chief</a>")
        
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=f"🔔 Внимание! Новый запрос!\n\n{', '.join(mentions)}",
            parse_mode=ParseMode.HTML
        )
        
        return topic_id
        
    except Exception as e:
        logger.error(f"Ошибка создания темы: {e}")
        return None

# ============ Остальные команды ============

async def my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать запросы пользователя"""
    user_id = update.effective_user.id
    topics = db.get_user_topics(user_id)
    
    if not topics:
        await update.message.reply_text("📋 У вас пока нет созданных запросов.")
        return
    
    message = "📋 <b>Ваши запросы:</b>\n\n"
    for topic_id in topics:
        if topic_id in db.topics:
            data = db.topics[topic_id]
            status = "🟢 Активна" if data.is_active else "🔴 Закрыта"
            message += (
                f"• <b>{sanitize_text(data.channel_name)}</b>\n"
                f"  ID: <code>{topic_id}</code> | {status}\n"
                f"  📅 {format_date(data.created_at)}\n"
                f"  👥 {data.subscribers}\n\n"
            )
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

async def close_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрытие темы"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ У вас нет прав для закрытия тем.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Укажите ID темы для закрытия.\n"
            "Пример: /close_topic 123\n\n"
            "ID темы можно найти в сообщении или через /search"
        )
        return
    
    try:
        topic_id = int(args[0])
        
        if topic_id not in db.topics:
            await update.message.reply_text("❌ Тема не найдена.")
            return
        
        if not db.topics[topic_id].is_active:
            await update.message.reply_text("❌ Тема уже закрыта.")
            return
        
        # Закрываем тему
        if db.close_topic(topic_id, user_id):
            # Отправляем уведомление в группу
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=topic_id,
                text=f"🔒 Тема закрыта администратором."
            )
            
            await update.message.reply_text(f"✅ Тема {topic_id} успешно закрыта.")
        else:
            await update.message.reply_text("❌ Ошибка при закрытии темы.")
            
    except ValueError:
        await update.message.reply_text("❌ ID темы должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка закрытия темы: {e}")
        await update.message.reply_text("❌ Произошла ошибка при закрытии темы.")

async def search_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск тем по ключевым словам"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ У вас нет прав для поиска тем.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Укажите ключевое слово для поиска.\n"
            "Пример: /search канал\n"
            "или /search \"название канала\""
        )
        return
    
    keyword = ' '.join(args).lower()
    results = db.search_topics(keyword)
    
    if results:
        message = f"🔍 <b>Результаты поиска по '{keyword}':</b>\n\n"
        for topic_id, data in results:
            message += (
                f"• ID: <code>{topic_id}</code> | {sanitize_text(data.channel_name)}\n"
                f"  👥 {data.subscribers} | 📅 {format_date(data.created_at)}\n"
                f"  📝 {truncate_text(data.conditions, 50)}\n\n"
            )
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"❌ По запросу '{keyword}' ничего не найдено.")

# ============ Управление пользователями ============

async def add_pr_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление PR менеджера по ID"""
    user_id = update.effective_user.id
    
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Только Chief PR Manager может добавлять PR менеджеров.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Использование: /add_pr_by_id @username id\n"
            "Пример: /add_pr_by_id @john 123456789"
        )
        return
    
    try:
        username = args[0].replace('@', '')
        new_user_id = int(args[1])
        
        if db.add_pr_manager(new_user_id):
            await update.message.reply_text(
                f"✅ Пользователь @{username} (ID: {new_user_id}) добавлен как PR Manager."
            )
            
            # Отправляем уведомление
            try:
                await context.bot.send_message(
                    chat_id=new_user_id,
                    text="🎉 Вас добавили как PR Manager! Теперь вы можете создавать запросы через бота.\n\n"
                         "Используйте /start для начала работы."
                )
            except:
                logger.warning(f"Не удалось отправить уведомление пользователю {new_user_id}")
        else:
            await update.message.reply_text("❌ Пользователь уже является PR Manager.")
            
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")

async def add_dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление заместителя"""
    user_id = update.effective_user.id
    
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Только Chief PR Manager может добавлять заместителей.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Использование: /add_dep @username id\n"
            "Пример: /add_dep @john 123456789"
        )
        return
    
    try:
        username = args[0].replace('@', '')
        new_user_id = int(args[1])
        
        if db.add_dep_chief(new_user_id):
            await update.message.reply_text(
                f"✅ Пользователь @{username} (ID: {new_user_id}) добавлен как Dep.Chief PR Manager."
            )
            
            # Отправляем уведомление
            try:
                await context.bot.send_message(
                    chat_id=new_user_id,
                    text="🎉 Вас добавили как Dep.Chief PR Manager! Теперь у вас есть права администратора.\n\n"
                         "Используйте /start для начала работы."
                )
            except:
                logger.warning(f"Не удалось отправить уведомление пользователю {new_user_id}")
        else:
            await update.message.reply_text("❌ Пользователь уже является Dep.Chief.")
            
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление пользователя"""
    user_id = update.effective_user.id
    
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Недостаточно прав.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Использование: /remove_user @username id\n"
            "Пример: /remove_user @john 123456789"
        )
        return
    
    try:
        username = args[0].replace('@', '')
        remove_id = int(args[1])
        
        # Защита от удаления чифа
        if remove_id == CHIEF_ID:
            await update.message.reply_text("❌ Нельзя удалить Chief PR Manager.")
            return
        
        removed = False
        if db.remove_pr_manager(remove_id):
            removed = True
        if db.remove_dep_chief(remove_id):
            removed = True
            
        if removed:
            await update.message.reply_text(
                f"✅ Пользователь @{username} (ID: {remove_id}) удален."
            )
        else:
            await update.message.reply_text("❌ Пользователь не найден.")
            
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех пользователей"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Недостаточно прав.")
        return
    
    message = "👥 <b>Список пользователей:</b>\n\n"
    
    # PR Managers
    if db.pr_managers:
        message += "👤 <b>PR Managers:</b>\n"
        for uid in db.pr_managers:
            message += f"• <code>{uid}</code>\n"
        message += "\n"
    
    # Dep.Chief
    if db.dep_chiefs:
        message += "👤 <b>Dep.Chief PR Managers:</b>\n"
        for uid in db.dep_chiefs:
            message += f"• <code>{uid}</code>\n"
        message += "\n"
    
    # Chief
    message += f"👑 <b>Chief PR Manager:</b>\n• <code>{CHIEF_ID}</code>"
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

# ============ Обработчики кнопок ============

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "new_request":
        await new_request_start(update, context)
        
    elif data == "my_requests":
        await my_requests(update, context)
        await query.delete_message()
        
    elif data == "search":
        await query.edit_message_text(
            "🔍 Для поиска используйте команду:\n"
            "/search <ключевое слово>\n\n"
            "Пример: /search канал"
        )
        
    elif data == "manage_users":
        if not is_admin(user_id) and not is_creator(user_id):
            await query.edit_message_text("❌ Недостаточно прав.")
            return
        from keyboards import get_admin_keyboard
        await query.edit_message_text(
            "👥 <b>Управление пользователями</b>\n\n"
            "Доступные команды:\n"
            "/add_pr_by_id @username id - добавить PR\n"
            "/add_dep @username id - добавить Dep.Chief\n"
            "/remove_user @username id - удалить пользователя\n"
            "/list_users - список всех пользователей",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )
        
    elif data == "close_topic":
        if not is_admin(user_id) and not is_creator(user_id):
            await query.edit_message_text("❌ Недостаточно прав.")
            return
        await query.edit_message_text(
            "🔒 Для закрытия темы используйте команду:\n"
            "/close_topic <id_темы>\n\n"
            "ID темы можно найти в сообщении или через /search"
        )
        
    elif data == "add_pr":
        await query.edit_message_text(
            "➕ <b>Добавление PR Manager</b>\n\n"
            "Используйте команду:\n"
            "/add_pr_by_id @username id\n\n"
            "Пример: /add_pr_by_id @john 123456789",
            parse_mode=ParseMode.HTML
        )
        
    elif data == "add_dep":
        await query.edit_message_text(
            "👤 <b>Добавление Dep.Chief</b>\n\n"
            "Используйте команду:\n"
            "/add_dep @username id\n\n"
            "Пример: /add_dep @john 123456789",
            parse_mode=ParseMode.HTML
        )
        
    elif data == "remove_user":
        await query.edit_message_text(
            "➖ <b>Удаление пользователя</b>\n\n"
            "Используйте команду:\n"
            "/remove_user @username id\n\n"
            "Пример: /remove_user @john 123456789",
            parse_mode=ParseMode.HTML
        )
        
    elif data == "list_users":
        await list_users(update, context)
        
    elif data == "back_to_main":
        keyboard = get_main_keyboard(
            is_admin=is_admin(user_id),
            is_creator=is_creator(user_id)
        )
        await query.edit_message_text(
            "👋 Главное меню",
            reply_markup=keyboard
        )
        
    elif data == "skip":
        await skip_conditions(update, context)
        
    elif data == "cancel":
        user_id = update.effective_user.id
        db.clear_pending_request(user_id)
        await query.edit_message_text("❌ Операция отменена.")
        keyboard = get_main_keyboard(
            is_admin=is_admin(user_id),
            is_creator=is_creator(user_id)
        )
        await context.bot.send_message(
            chat_id=user_id,
            text="👋 Возврат в главное меню",
            reply_markup=keyboard
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания запроса"""
    user_id = update.effective_user.id
    db.clear_pending_request(user_id)
    
    await update.message.reply_text(
        "❌ Создание запроса отменено."
    )
    return ConversationHandler.END

# ============ Обработчик ошибок ============

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка. Пожалуйста, попробуйте позже."
        )