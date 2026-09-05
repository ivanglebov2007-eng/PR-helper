import logging
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from config import CHIEF_ID, CREATOR_ID, GROUP_ID, REQUIRED_FIELDS
from database import Database, RequestData
from states import *
from utils import (
    validate_media_link,
    format_date,
    sanitize_text,
    truncate_text
)

logger = logging.getLogger(__name__)
db = Database()

# ============ ПРОВЕРКА ПРАВ ============

def is_chief(user_id: int) -> bool:
    return user_id == CHIEF_ID

def is_dep_chief(user_id: int) -> bool:
    return user_id in db.dep_chiefs

def is_admin(user_id: int) -> bool:
    return is_chief(user_id) or is_dep_chief(user_id)

def is_pr_manager(user_id: int) -> bool:
    return user_id in db.pr_managers or is_admin(user_id) or is_creator(user_id)

def is_creator(user_id: int) -> bool:
    return user_id == CREATOR_ID

# ============ КЛАВИАТУРЫ ============

def get_main_keyboard(is_admin: bool = False, is_creator: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📝 Создать запрос", callback_data="new_request")],
        [InlineKeyboardButton("📋 Мои запросы", callback_data="my_requests")],
    ]
    if is_admin or is_creator:
        keyboard.extend([
            [InlineKeyboardButton("🔍 Поиск тем", callback_data="search")],
            [InlineKeyboardButton("👥 Управление пользователями", callback_data="manage_users")],
            [InlineKeyboardButton("🔒 Закрыть тему", callback_data="close_topic")]
        ])
    if is_creator:
        keyboard.append([InlineKeyboardButton("⚙️ Настройки", callback_data="settings")])
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])

def get_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ])

def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить PR", callback_data="add_pr")],
        [InlineKeyboardButton("👤 Добавить Dep.Chief", callback_data="add_dep")],
        [InlineKeyboardButton("➖ Удалить пользователя", callback_data="remove_user")],
        [InlineKeyboardButton("📋 Список пользователей", callback_data="list_users")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ])

# ============ КОМАНДА /start ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if not is_pr_manager(user_id) and not is_creator(user_id):
        await update.message.reply_text(
            "❌ У вас нет доступа.\nОбратитесь к Chief PR Manager.",
            reply_markup=get_cancel_keyboard()
        )
        return

    text = f"👋 <b>Добро пожаловать, {sanitize_text(user.full_name)}!</b>\n\n"
    if is_creator(user_id):
        text += "🤖 <b>Вы — Создатель</b>\nДоступны все функции."
    elif is_admin(user_id):
        text += "👑 <b>Вы — администратор</b>"
    else:
        text += "📝 <b>Вы — PR Manager</b>"

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(
            is_admin=is_admin(user_id),
            is_creator=is_creator(user_id)
        )
    )

# ============ СОЗДАНИЕ ЗАПРОСА (новая логика) ============

async def new_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания запроса"""
    user_id = update.effective_user.id

    if not is_pr_manager(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    # Очищаем старые данные и устанавливаем состояние
    db.set_pending_request(user_id, {})
    context.user_data['request_state'] = 'SCREENSHOT'
    context.user_data['request_data'] = {}

    await update.message.reply_text(
        "📝 <b>Шаг 1/6: отправьте СКРИНШОТ переписки</b>\n\n"
        "Отправьте фото (скриншот диалога с медиа):",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех сообщений при создании запроса"""
    user_id = update.effective_user.id
    state = context.user_data.get('request_state')
    
    # Если нет активного запроса - игнорируем
    if not state:
        return
    
    # Получаем данные запроса
    request_data = context.user_data.get('request_data', {})
    
    # === Шаг 1: Скриншот ===
    if state == 'SCREENSHOT':
        photo = update.message.photo
        if not photo:
            await update.message.reply_text(
                "❌ Отправьте изображение (фото).\nПопробуйте ещё раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        try:
            file = await photo[-1].get_file()
            file_url = file.file_path
            request_data['screenshot'] = file_url
            context.user_data['request_data'] = request_data
            context.user_data['request_state'] = 'MEDIA_LINK'
            
            await update.message.reply_text(
                "✅ Скриншот получен!\n\n"
                "📎 <b>Шаг 2/6: отправьте ссылку на канал</b>\n"
                "Поддерживаются: YouTube, Twitch, TikTok\n\n"
                "Пример: https://www.youtube.com/@channel",
                parse_mode=ParseMode.HTML,
                reply_markup=get_cancel_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка скриншота: {e}")
            await update.message.reply_text(
                "❌ Ошибка при загрузке фото. Попробуйте ещё раз.",
                reply_markup=get_cancel_keyboard()
            )
        return
    
    # === Шаг 2: Ссылка на медиа ===
    if state == 'MEDIA_LINK':
        text = update.message.text.strip()
        if not validate_media_link(text):
            await update.message.reply_text(
                "❌ Некорректная ссылка.\n"
                "Ссылка должна начинаться с http:// или https://\n"
                "И содержать: youtube, twitch или tiktok\n\n"
                "Попробуйте ещё раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        request_data['media_link'] = text
        context.user_data['request_data'] = request_data
        context.user_data['request_state'] = 'CHANNEL_NAME'
        
        await update.message.reply_text(
            "✅ Ссылка принята.\n\n"
            "📌 <b>Шаг 3/6: введите название канала</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # === Шаг 3: Название канала ===
    if state == 'CHANNEL_NAME':
        text = update.message.text.strip()
        if not text:
            await update.message.reply_text(
                "❌ Название не может быть пустым.",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        request_data['channel_name'] = sanitize_text(text)
        context.user_data['request_data'] = request_data
        context.user_data['request_state'] = 'SUBSCRIBERS'
        
        await update.message.reply_text(
            "✅ Название сохранено.\n\n"
            "👥 <b>Шаг 4/6: количество подписчиков</b>\n"
            "Введите только цифры (пример: 10000 или 10,000):",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # === Шаг 4: Подписчики ===
    if state == 'SUBSCRIBERS':
        text = update.message.text.strip()
        try:
            subs = int(text.replace(' ', '').replace(',', '').replace('.', ''))
            if subs < 0:
                raise ValueError
            formatted = f"{subs:,}".replace(',', ' ')
        except ValueError:
            await update.message.reply_text(
                "❌ Введите корректное число (только цифры).\n"
                "Пример: 10000",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        request_data['subscribers'] = formatted
        context.user_data['request_data'] = request_data
        context.user_data['request_state'] = 'CONTACT_LINK'
        
        await update.message.reply_text(
            f"✅ Подписчиков: {formatted}\n\n"
            "📞 <b>Шаг 5/6: отправьте ссылку для связи</b>\n"
            "Telegram, email, сайт и т.д.:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # === Шаг 5: Ссылка для связи ===
    if state == 'CONTACT_LINK':
        text = update.message.text.strip()
        if not text:
            await update.message.reply_text(
                "❌ Введите ссылку.",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        if not text.startswith(('http://', 'https://')):
            text = 'https://' + text
        
        request_data['contact_link'] = text
        context.user_data['request_data'] = request_data
        context.user_data['request_state'] = 'CONDITIONS'
        
        await update.message.reply_text(
            "✅ Ссылка сохранена.\n\n"
            "📝 <b>Шаг 6/6: отправьте желаемые условия</b>\n"
            "Или нажмите кнопку 'Пропустить':",
            parse_mode=ParseMode.HTML,
            reply_markup=get_skip_keyboard()
        )
        return
    
    # === Шаг 6: Условия ===
    if state == 'CONDITIONS':
        text = update.message.text.strip()
        request_data['conditions'] = sanitize_text(text) if text else "Не указаны"
        context.user_data['request_data'] = request_data
        
        # Завершаем создание запроса
        await finish_request(update, context)

async def finish_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение создания запроса"""
    user = update.effective_user
    user_id = user.id
    
    # Получаем данные из context.user_data
    request_data = context.user_data.get('request_data', {})
    
    # Проверяем все поля
    missing = [f for f in REQUIRED_FIELDS if f not in request_data]
    if missing:
        await update.message.reply_text(
            f"❌ Не хватает полей: {', '.join(missing)}\n"
            "Начните заново с /new_request"
        )
        context.user_data.pop('request_state', None)
        context.user_data.pop('request_data', None)
        return

    # Создаем тему
    topic_id = await create_request_topic(update, context, request_data)

    if topic_id:
        # Сохраняем в БД
        request_obj = RequestData(
            screenshot=request_data['screenshot'],
            media_link=request_data['media_link'],
            channel_name=request_data['channel_name'],
            subscribers=request_data['subscribers'],
            contact_link=request_data['contact_link'],
            conditions=request_data['conditions'],
            user_id=user_id,
            created_at=datetime.now().isoformat()
        )
        db.add_topic(topic_id, request_obj)

        await update.message.reply_text(
            f"✅ <b>Запрос успешно создан!</b>\n\n"
            f"🆔 ID темы: <code>{topic_id}</code>\n"
            f"📌 Тема создана в группе и отмечена для руководства.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось создать запрос. Проверьте, что бот является администратором группы."
        )

    # Очищаем состояние
    context.user_data.pop('request_state', None)
    context.user_data.pop('request_data', None)

async def create_request_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, request_data: dict) -> Optional[int]:
    """Создание темы в группе"""
    user = update.effective_user
    topic_title = f"Запрос от {user.full_name} — {request_data['channel_name']}"

    try:
        # Создаем тему
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=topic_title[:255]
        )
        topic_id = topic.message_thread_id

        # Формируем сообщение
        text = (
            f"📢 <b>НОВЫЙ ЗАПРОС НА МЕДИА-ПАРТНЕРСТВО</b>\n\n"
            f"👤 <b>PR Менеджер:</b> {sanitize_text(user.full_name)}\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📅 <b>Дата:</b> {format_date(datetime.now().isoformat())}\n\n"
            f"📌 <b>Канал:</b> {sanitize_text(request_data['channel_name'])}\n"
            f"👥 <b>Подписчиков:</b> {request_data['subscribers']}\n"
            f"🔗 <b>Ссылка:</b> <a href='{request_data['media_link']}'>Открыть</a>\n"
            f"📎 <b>Скриншот:</b> <a href='{request_data['screenshot']}'>Смотреть</a>\n"
            f"📞 <b>Связь:</b> <a href='{request_data['contact_link']}'>Написать</a>\n"
            f"📝 <b>Условия:</b>\n{sanitize_text(request_data['conditions'])}\n\n"
            f"⏳ <b>Ожидайте ответа от руководства!</b>"
        )

        # Отправляем сообщение в тему
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

        # Уведомляем руководство
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

# ============ ОСТАЛЬНЫЕ КОМАНДЫ ============

async def my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    topics = db.get_user_topics(user_id)

    if not topics:
        await update.message.reply_text("📋 У вас нет запросов.")
        return

    text = "📋 <b>Ваши запросы:</b>\n\n"
    for tid in topics:
        data = db.topics.get(tid)
        if data:
            status = "🟢 Активна" if data.is_active else "🔴 Закрыта"
            text += (
                f"• <b>{sanitize_text(data.channel_name)}</b>\n"
                f"  ID: <code>{tid}</code> | {status}\n"
                f"  👥 {data.subscribers}\n\n"
            )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def close_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Использование: /close_topic <id_темы>")
        return

    try:
        topic_id = int(args[0])
        if topic_id not in db.topics:
            await update.message.reply_text("❌ Тема не найдена.")
            return
        if not db.topics[topic_id].is_active:
            await update.message.reply_text("❌ Тема уже закрыта.")
            return

        db.close_topic(topic_id, user_id)
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text="🔒 Тема закрыта администратором."
        )
        await update.message.reply_text(f"✅ Тема {topic_id} закрыта.")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

async def search_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Использование: /search <ключевое_слово>")
        return

    keyword = ' '.join(args).lower()
    results = db.search_topics(keyword)

    if not results:
        await update.message.reply_text(f"❌ По запросу '{keyword}' ничего не найдено.")
        return

    text = f"🔍 <b>Результаты поиска по '{keyword}':</b>\n\n"
    for tid, data in results:
        text += f"• ID: <code>{tid}</code> | {sanitize_text(data.channel_name)}\n"
        text += f"  👥 {data.subscribers} | 📅 {format_date(data.created_at)}\n\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def add_pr_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Только Chief PR Manager может добавлять PR.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /add_pr_by_id @username id")
        return

    try:
        username = args[0].replace('@', '')
        new_id = int(args[1])
        if db.add_pr_manager(new_id):
            await update.message.reply_text(f"✅ @{username} (ID: {new_id}) добавлен как PR Manager.")
        else:
            await update.message.reply_text("❌ Пользователь уже является PR Manager.")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

async def add_dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Только Chief PR Manager может добавлять Dep.Chief.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /add_dep @username id")
        return

    try:
        username = args[0].replace('@', '')
        new_id = int(args[1])
        if db.add_dep_chief(new_id):
            await update.message.reply_text(f"✅ @{username} (ID: {new_id}) добавлен как Dep.Chief.")
        else:
            await update.message.reply_text("❌ Пользователь уже является Dep.Chief.")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Недостаточно прав.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /remove_user @username id")
        return

    try:
        username = args[0].replace('@', '')
        remove_id = int(args[1])
        if remove_id == CHIEF_ID:
            await update.message.reply_text("❌ Нельзя удалить Chief PR Manager.")
            return

        removed = db.remove_pr_manager(remove_id) or db.remove_dep_chief(remove_id)
        if removed:
            await update.message.reply_text(f"✅ @{username} (ID: {remove_id}) удалён.")
        else:
            await update.message.reply_text("❌ Пользователь не найден.")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    text = "👥 <b>Список пользователей:</b>\n\n"

    if db.pr_managers:
        text += "👤 <b>PR Managers:</b>\n"
        for uid in db.pr_managers:
            text += f"• <a href='tg://user?id={uid}'>{uid}</a>\n"
        text += "\n"

    if db.dep_chiefs:
        text += "👤 <b>Dep.Chief:</b>\n"
        for uid in db.dep_chiefs:
            text += f"• <a href='tg://user?id={uid}'>{uid}</a>\n"
        text += "\n"

    text += f"👑 <b>Chief PR Manager:</b>\n• <a href='tg://user?id={CHIEF_ID}'>{CHIEF_ID}</a>\n\n"
    text += f"👑 <b>Creator:</b>\n• <a href='tg://user?id={CREATOR_ID}'>{CREATOR_ID}</a>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ============ ОБРАБОТЧИК КНОПОК ============

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    try:
        await query.answer()
        data = query.data

        if data == "new_request":
            if not is_pr_manager(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            
            # Очищаем старые данные и устанавливаем состояние
            context.user_data['request_state'] = 'SCREENSHOT'
            context.user_data['request_data'] = {}
            
            await query.edit_message_text(
                "📝 <b>Шаг 1/6: отправьте СКРИНШОТ переписки</b>\n\n"
                "Отправьте фото:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_cancel_keyboard()
            )
            return

        elif data == "my_requests":
            topics = db.get_user_topics(user_id)
            if not topics:
                await query.edit_message_text("📋 У вас нет запросов.")
                return
            text = "📋 <b>Ваши запросы:</b>\n\n"
            for tid in topics:
                data_topic = db.topics.get(tid)
                if data_topic:
                    status = "🟢 Активна" if data_topic.is_active else "🔴 Закрыта"
                    text += f"• <b>{sanitize_text(data_topic.channel_name)}</b>\n  ID: <code>{tid}</code> | {status}\n\n"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)

        elif data == "search":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await query.edit_message_text(
                "🔍 <b>Поиск тем</b>\n\n"
                "Используйте команду:\n/search <ключевое_слово>",
                parse_mode=ParseMode.HTML
            )

        elif data == "manage_users":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await query.edit_message_text(
                "👥 <b>Управление пользователями</b>\n\n"
                "Доступные команды:\n"
                "• /add_pr_by_id @username id — добавить PR\n"
                "• /add_dep @username id — добавить Dep.Chief\n"
                "• /remove_user @username id — удалить\n"
                "• /list_users — показать всех",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_keyboard()
            )

        elif data == "close_topic":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await query.edit_message_text(
                "🔒 <b>Закрытие темы</b>\n\n"
                "Используйте команду:\n/close_topic <id_темы>",
                parse_mode=ParseMode.HTML
            )

        elif data == "list_users":
            text = "👥 <b>Список пользователей:</b>\n\n"
            if db.pr_managers:
                text += "👤 <b>PR Managers:</b>\n"
                for uid in db.pr_managers:
                    text += f"• <a href='tg://user?id={uid}'>{uid}</a>\n"
                text += "\n"
            if db.dep_chiefs:
                text += "👤 <b>Dep.Chief:</b>\n"
                for uid in db.dep_chiefs:
                    text += f"• <a href='tg://user?id={uid}'>{uid}</a>\n"
                text += "\n"
            text += f"👑 <b>Chief PR Manager:</b>\n• <a href='tg://user?id={CHIEF_ID}'>{CHIEF_ID}</a>\n\n"
            text += f"👑 <b>Creator:</b>\n• <a href='tg://user?id={CREATOR_ID}'>{CREATOR_ID}</a>"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)

        elif data == "add_pr":
            await query.edit_message_text(
                "➕ <b>Добавление PR Manager</b>\n\n"
                "Команда:\n/add_pr_by_id @username id\n\n"
                "Пример: /add_pr_by_id @john 123456789",
                parse_mode=ParseMode.HTML
            )

        elif data == "add_dep":
            await query.edit_message_text(
                "👤 <b>Добавление Dep.Chief</b>\n\n"
                "Команда:\n/add_dep @username id\n\n"
                "Пример: /add_dep @john 123456789",
                parse_mode=ParseMode.HTML
            )

        elif data == "remove_user":
            await query.edit_message_text(
                "➖ <b>Удаление пользователя</b>\n\n"
                "Команда:\n/remove_user @username id\n\n"
                "Пример: /remove_user @john 123456789",
                parse_mode=ParseMode.HTML
            )

        elif data == "back_to_main":
            keyboard = get_main_keyboard(
                is_admin=is_admin(user_id),
                is_creator=is_creator(user_id)
            )
            user = query.from_user
            await query.edit_message_text(
                f"👋 <b>Главное меню, {sanitize_text(user.full_name)}!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )

        elif data == "settings":
            if not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            active_topics = len([t for t in db.topics.values() if t.is_active])
            await query.edit_message_text(
                f"⚙️ <b>Настройки бота</b>\n\n"
                f"👤 PR Managers: {len(db.pr_managers)}\n"
                f"👤 Dep.Chief: {len(db.dep_chiefs)}\n"
                f"📋 Всего тем: {len(db.topics)}\n"
                f"🟢 Активных: {active_topics}\n"
                f"💾 База: {db.file_path}",
                parse_mode=ParseMode.HTML
            )

        elif data == "skip":
            # Пропуск условий
            request_data = context.user_data.get('request_data', {})
            request_data['conditions'] = "Не указаны"
            context.user_data['request_data'] = request_data
            await query.edit_message_text("⏭️ Условия пропущены.")
            # Создаем fake update для завершения
            class FakeUpdate:
                def __init__(self, user, chat):
                    self.effective_user = user
                    self.effective_chat = chat
                    self.message = type('obj', (object,), {
                        'reply_text': lambda self, *args, **kwargs: None
                    })()
            fake_update = FakeUpdate(query.from_user, query.message.chat)
            await finish_request(fake_update, context)

        elif data == "cancel":
            # Отмена создания запроса
            context.user_data.pop('request_state', None)
            context.user_data.pop('request_data', None)
            await query.edit_message_text("❌ Операция отменена.")
            keyboard = get_main_keyboard(
                is_admin=is_admin(user_id),
                is_creator=is_creator(user_id)
            )
            user = query.from_user
            await context.bot.send_message(
                chat_id=user_id,
                text=f"👋 Главное меню, {sanitize_text(user.full_name)}",
                reply_markup=keyboard
            )

        else:
            await query.edit_message_text("❌ Неизвестная команда.")

    except Exception as e:
        logger.error(f"Callback error: {e}")
        try:
            await query.edit_message_text("❌ Ошибка. Попробуйте позже.")
        except:
            pass

# ============ ОБРАБОТЧИК ОШИБОК ============

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Пожалуйста, попробуйте позже."
            )
        except:
            pass
