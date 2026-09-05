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
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_panel_keyboard(is_creator: bool = False, is_chief: bool = False, is_dep_chief: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    keyboard.append([InlineKeyboardButton("👥 Управление пользователями", callback_data="manage_users")])
    keyboard.append([InlineKeyboardButton("🔍 Поиск тем", callback_data="search")])
    keyboard.append([InlineKeyboardButton("🔒 Закрыть тему", callback_data="close_topic")])
    keyboard.append([InlineKeyboardButton("📊 Статистика", callback_data="statistics")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_manage_users_keyboard(is_creator: bool = False, is_chief: bool = False, is_dep_chief: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    
    if is_creator:
        keyboard.append([InlineKeyboardButton("➕ Добавить Создателя", callback_data="add_creator")])
        keyboard.append([InlineKeyboardButton("➕ Добавить Chief", callback_data="add_chief")])
        keyboard.append([InlineKeyboardButton("➕ Добавить Dep.Chief", callback_data="add_dep")])
        keyboard.append([InlineKeyboardButton("➕ Добавить PR", callback_data="add_pr")])
    elif is_chief:
        keyboard.append([InlineKeyboardButton("➕ Добавить Chief", callback_data="add_chief")])
        keyboard.append([InlineKeyboardButton("➕ Добавить Dep.Chief", callback_data="add_dep")])
        keyboard.append([InlineKeyboardButton("➕ Добавить PR", callback_data="add_pr")])
    elif is_dep_chief:
        keyboard.append([InlineKeyboardButton("➕ Добавить PR", callback_data="add_pr")])
    
    keyboard.append([InlineKeyboardButton("➖ Удалить пользователя", callback_data="remove_user")])
    keyboard.append([InlineKeyboardButton("📋 Список пользователей", callback_data="list_users")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])

def get_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ])

def get_my_requests_keyboard(topics: list) -> InlineKeyboardMarkup:
    keyboard = []
    for topic_id, data in topics:
        status = "🟢" if data.is_active else "🔴"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {data.channel_name} ({data.subscribers})",
                callback_data=f"open_topic_{topic_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_topic_action_keyboard(topic_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📂 Перейти к теме", callback_data=f"goto_topic_{topic_id}")],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("🔒 Закрыть тему", callback_data=f"close_topic_{topic_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="my_requests")])
    return InlineKeyboardMarkup(keyboard)

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

# ============ СОЗДАНИЕ ЗАПРОСА ============

async def new_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_pr_manager(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    if GROUP_ID == 0:
        await update.message.reply_text("❌ GROUP_ID не настроен!")
        return

    context.user_data['request_state'] = 'SCREENSHOT'
    context.user_data['request_data'] = {}

    await update.message.reply_text(
        "📝 <b>Шаг 1/6: отправьте СКРИНШОТ переписки</b>\n\n"
        "Отправьте фото (скриншот диалога с медиа):",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get('request_state')
    
    if not state:
        return
    
    request_data = context.user_data.get('request_data', {})
    
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
    
    if state == 'CONDITIONS':
        text = update.message.text.strip()
        request_data['conditions'] = sanitize_text(text) if text else "Не указаны"
        context.user_data['request_data'] = request_data
        
        await finish_request(update, context)

async def finish_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    request_data = context.user_data.get('request_data', {})
    
    missing = [f for f in REQUIRED_FIELDS if f not in request_data]
    if missing:
        await update.message.reply_text(
            f"❌ Не хватает полей: {', '.join(missing)}\n"
            "Начните заново с /new_request"
        )
        context.user_data.pop('request_state', None)
        context.user_data.pop('request_data', None)
        return

    # ОТПРАВКА ФОТО В ГРУППУ
    screenshot_url = request_data.get('screenshot')
    photo_sent = False
    
    if screenshot_url:
        try:
            # Пробуем отправить фото
            await context.bot.send_photo(
                chat_id=GROUP_ID,
                photo=screenshot_url,
                caption=f"📸 Скриншот переписки для запроса: {request_data['channel_name']}",
                parse_mode=ParseMode.HTML
            )
            photo_sent = True
            logger.info("✅ Фото отправлено в группу")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото: {e}")
            # Пробуем отправить как документ
            try:
                await context.bot.send_document(
                    chat_id=GROUP_ID,
                    document=screenshot_url,
                    caption=f"📸 Скриншот переписки для запроса: {request_data['channel_name']}"
                )
                photo_sent = True
                logger.info("✅ Фото отправлено как документ")
            except Exception as e2:
                logger.error(f"❌ Ошибка отправки документа: {e2}")

    # Создаем тему
    topic_id = await create_request_topic(update, context, request_data, photo_sent)

    if topic_id:
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
        error_msg = "❌ Не удалось создать запрос. Проверьте:\n" \
                    "1. Что бот является администратором группы\n" \
                    "2. Что в группе включён режим форума\n" \
                    "3. Что у бота есть право 'Управление темами'\n" \
                    "4. Что GROUP_ID правильный (должен быть отрицательным!)"
        await update.message.reply_text(error_msg)

    context.user_data.pop('request_state', None)
    context.user_data.pop('request_data', None)

async def create_request_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, request_data: dict, photo_sent: bool = False) -> Optional[int]:
    user = update.effective_user
    topic_title = f"Запрос от {user.full_name} — {request_data['channel_name']}"

    try:
        if GROUP_ID == 0:
            logger.error("GROUP_ID не настроен!")
            return None

        # Проверяем доступ к группе
        chat = await context.bot.get_chat(GROUP_ID)
        logger.info(f"✅ Группа: {chat.title} (ID: {chat.id})")

        # Проверяем права бота
        bot_member = await context.bot.get_chat_member(GROUP_ID, context.bot.id)
        logger.info(f"Статус бота: {bot_member.status}")

        # Создаем тему
        logger.info(f"📝 Создаю тему: {topic_title[:255]}")
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=topic_title[:255]
        )
        topic_id = topic.message_thread_id
        logger.info(f"✅ Тема создана! ID: {topic_id}")

        # Формируем сообщение
        photo_text = "📸 Скриншот приложен ниже" if photo_sent else "📸 Скриншот: (не удалось отправить)"
        
        text = (
            f"📢 <b>НОВЫЙ ЗАПРОС НА МЕДИА-ПАРТНЕРСТВО</b>\n\n"
            f"👤 <b>PR Менеджер:</b> {sanitize_text(user.full_name)}\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📅 <b>Дата:</b> {format_date(datetime.now().isoformat())}\n\n"
            f"📌 <b>Канал:</b> {sanitize_text(request_data['channel_name'])}\n"
            f"👥 <b>Подписчиков:</b> {request_data['subscribers']}\n"
            f"🔗 <b>Ссылка:</b> <a href='{request_data['media_link']}'>Открыть</a>\n"
            f"📞 <b>Связь:</b> <a href='{request_data['contact_link']}'>Написать</a>\n"
            f"📝 <b>Условия:</b>\n{sanitize_text(request_data['conditions'])}\n\n"
            f"{photo_text}\n\n"
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

        # === ТЕГИРУЕМ CHIEF ===
        try:
            chief_mention = f"<a href='tg://user?id={CHIEF_ID}'>Chief</a>"
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=topic_id,
                text=f"🔔 {chief_mention}, новый запрос!",
                parse_mode=ParseMode.HTML
            )
            logger.info("✅ Chief уведомлён")
        except Exception as e:
            logger.error(f"❌ Ошибка тегирования Chief: {e}")

        # === ТЕГИРУЕМ DEP.CHIEF ===
        for dep_id in db.dep_chiefs:
            try:
                dep_mention = f"<a href='tg://user?id={dep_id}'>Dep.Chief</a>"
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    message_thread_id=topic_id,
                    text=f"🔔 {dep_mention}, новый запрос!",
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"✅ Dep.Chief {dep_id} уведомлён")
            except Exception as e:
                logger.error(f"❌ Ошибка тегирования Dep.Chief {dep_id}: {e}")

        # === СКРЫВАЕМ ТЕМУ ОТ ОБЫЧНЫХ ПОЛЬЗОВАТЕЛЕЙ ===
        try:
            # Получаем всех администраторов
            admins = await context.bot.get_chat_administrators(GROUP_ID)
            admin_ids = [admin.user.id for admin in admins]
            
            # Запрещаем всем отправлять сообщения в теме
            await context.bot.set_forum_topic_permissions(
                chat_id=GROUP_ID,
                message_thread_id=topic_id,
                permissions={
                    "can_send_messages": False,
                    "can_send_media_messages": False,
                    "can_send_polls": False,
                    "can_send_other_messages": False,
                    "can_add_web_page_previews": False,
                    "can_change_info": False,
                    "can_invite_users": False,
                    "can_pin_messages": False
                }
            )
            
            # Разрешаем только админам
            for admin in admins:
                try:
                    await context.bot.set_forum_topic_permissions(
                        chat_id=GROUP_ID,
                        message_thread_id=topic_id,
                        user_id=admin.user.id,
                        permissions={
                            "can_send_messages": True,
                            "can_send_media_messages": True,
                            "can_send_polls": True,
                            "can_send_other_messages": True,
                            "can_add_web_page_previews": True,
                            "can_change_info": True,
                            "can_invite_users": True,
                            "can_pin_messages": True
                        }
                    )
                except:
                    pass
                    
            logger.info(f"✅ Тема {topic_id} скрыта от обычных пользователей")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось скрыть тему: {e}")

        logger.info(f"✅ Тема {topic_id} создана успешно!")
        return topic_id

    except Exception as e:
        logger.error(f"❌ Ошибка создания темы: {e}")
        return None

# ============ МОИ ЗАПРОСЫ ============

async def my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    topics = db.get_user_topics(user_id)

    if not topics:
        await update.message.reply_text("📋 У вас нет запросов.")
        return

    topics_list = []
    for tid in topics:
        data = db.topics.get(tid)
        if data:
            topics_list.append((tid, data))
    
    if not topics_list:
        await update.message.reply_text("📋 У вас нет запросов.")
        return

    text = "📋 <b>Ваши запросы:</b>\n\n"
    for tid, data in topics_list:
        status = "🟢 Активна" if data.is_active else "🔴 Закрыта"
        text += f"• <b>{sanitize_text(data.channel_name)}</b>\n"
        text += f"  ID: <code>{tid}</code> | {status}\n"
        text += f"  👥 {data.subscribers}\n\n"

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_my_requests_keyboard(topics_list)
    )

async def open_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    query = update.callback_query
    user_id = query.from_user.id
    
    topic_data = db.topics.get(topic_id)
    if not topic_data:
        await query.edit_message_text("❌ Тема не найдена.")
        return
    
    if topic_data.user_id != user_id and not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ У вас нет доступа к этой теме.")
        return
    
    topic_link = f"https://t.me/c/{str(GROUP_ID)[4:]}/{topic_id}"
    
    text = (
        f"📂 <b>Тема #{topic_id}</b>\n\n"
        f"📌 <b>Канал:</b> {sanitize_text(topic_data.channel_name)}\n"
        f"👥 <b>Подписчиков:</b> {topic_data.subscribers}\n"
        f"📅 <b>Создана:</b> {format_date(topic_data.created_at)}\n"
        f"📝 <b>Условия:</b>\n{sanitize_text(topic_data.conditions)}\n\n"
        f"🔗 <a href='{topic_link}'>Перейти к теме</a>"
    )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=get_topic_action_keyboard(topic_id, is_admin(user_id) or is_creator(user_id))
    )

async def goto_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    query = update.callback_query
    topic_link = f"https://t.me/c/{str(GROUP_ID)[4:]}/{topic_id}"
    
    await query.edit_message_text(
        f"🔗 <b>Переход к теме #{topic_id}</b>\n\n"
        f"Нажмите на ссылку ниже, чтобы открыть тему:\n"
        f"<a href='{topic_link}'>Открыть тему #{topic_id}</a>\n\n"
        f"Или скопируйте ссылку:\n<code>{topic_link}</code>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# ============ АДМИН-ПАНЕЛЬ ============

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ Нет прав.")
        return
    
    text = (
        "⚙️ <b>Админ-панель</b>\n\n"
        "Управление ботом и пользователями.\n"
        f"👤 Ваша роль: "
        f"{'Создатель' if is_creator(user_id) else 'Chief' if is_chief(user_id) else 'Dep.Chief'}"
    )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard(
            is_creator=is_creator(user_id),
            is_chief=is_chief(user_id),
            is_dep_chief=is_dep_chief(user_id)
        )
    )

async def statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ Нет прав.")
        return
    
    active_topics = len([t for t in db.topics.values() if t.is_active])
    closed_topics = len([t for t in db.topics.values() if not t.is_active])
    
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👤 <b>Пользователи:</b>\n"
        f"  • Создатель: 1\n"
        f"  • Chief: 1\n"
        f"  • Dep.Chief: {len(db.dep_chiefs)}\n"
        f"  • PR Managers: {len(db.pr_managers)}\n\n"
        f"📋 <b>Темы:</b>\n"
        f"  • Всего: {len(db.topics)}\n"
        f"  • Активных: {active_topics}\n"
        f"  • Закрытых: {closed_topics}\n\n"
        f"💾 <b>База данных:</b>\n"
        f"  • Файл: {db.file_path}"
    )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard(
            is_creator=is_creator(user_id),
            is_chief=is_chief(user_id),
            is_dep_chief=is_dep_chief(user_id)
        )
    )

# ============ УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ============

async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ Нет прав.")
        return
    
    text = (
        "👥 <b>Управление пользователями</b>\n\n"
        "Выберите действие:\n"
        f"👤 Ваша роль: "
        f"{'Создатель' if is_creator(user_id) else 'Chief' if is_chief(user_id) else 'Dep.Chief'}\n\n"
        f"📋 Всего пользователей: {len(db.pr_managers) + len(db.dep_chiefs) + 2}"
    )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_manage_users_keyboard(
            is_creator=is_creator(user_id),
            is_chief=is_chief(user_id),
            is_dep_chief=is_dep_chief(user_id)
        )
    )

async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str):
    query = update.callback_query
    user_id = query.from_user.id
    
    if role == "creator" and not is_creator(user_id):
        await query.edit_message_text("❌ Только Создатель может добавлять Создателя.")
        return
    if role == "chief" and not is_creator(user_id) and not is_chief(user_id):
        await query.edit_message_text("❌ Только Chief или Создатель может добавлять Chief.")
        return
    if role == "dep" and not is_creator(user_id) and not is_chief(user_id):
        await query.edit_message_text("❌ Только Chief или Создатель может добавлять Dep.Chief.")
        return
    
    role_names = {
        "creator": "Создателя",
        "chief": "Chief PR Manager",
        "dep": "Dep.Chief PR Manager",
        "pr": "PR Manager"
    }
    
    context.user_data['add_role'] = role
    context.user_data['add_state'] = 'WAITING_USERNAME'
    
    await query.edit_message_text(
        f"➕ <b>Добавление {role_names.get(role, 'пользователя')}</b>\n\n"
        f"Отправьте username пользователя (например, @username) или его ID:\n\n"
        f"Пример: @john или 123456789\n\n"
        f"Для отмены нажмите кнопку ниже.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )

async def add_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    role = context.user_data.get('add_role')
    
    if not role:
        return
    
    username = text.replace('@', '')
    try:
        new_user_id = int(username)
    except ValueError:
        try:
            chat = await context.bot.get_chat(f"@{username}")
            new_user_id = chat.id
        except:
            await update.message.reply_text(
                "❌ Не удалось найти пользователя. Проверьте username или ID."
            )
            return
    
    success = False
    if role == "creator":
        if is_creator(user_id):
            success = db.add_pr_manager(new_user_id)
            await update.message.reply_text(
                f"✅ Пользователь {new_user_id} добавлен как PR Manager.\n"
                f"⚠️ Создатель может быть только один (ID: {CREATOR_ID})."
            )
        else:
            await update.message.reply_text("❌ Нет прав для добавления Создателя.")
            return
    elif role == "chief":
        if is_creator(user_id) or is_chief(user_id):
            success = db.add_pr_manager(new_user_id)
            await update.message.reply_text(
                f"✅ Пользователь {new_user_id} добавлен как PR Manager.\n"
                f"⚠️ Функция смены Chief в разработке."
            )
        else:
            await update.message.reply_text("❌ Нет прав для добавления Chief.")
            return
    elif role == "dep":
        if is_creator(user_id) or is_chief(user_id):
            success = db.add_dep_chief(new_user_id)
            if success:
                await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен как Dep.Chief.")
            else:
                await update.message.reply_text("❌ Пользователь уже является Dep.Chief.")
        else:
            await update.message.reply_text("❌ Нет прав для добавления Dep.Chief.")
            return
    elif role == "pr":
        success = db.add_pr_manager(new_user_id)
        if success:
            await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен как PR Manager.")
        else:
            await update.message.reply_text("❌ Пользователь уже является PR Manager.")
    
    if success:
        try:
            await context.bot.send_message(
                chat_id=new_user_id,
                text=f"🎉 Вас добавили в систему PR Manager бота!\n\nВаша роль: {role.upper()}\nИспользуйте /start для начала работы."
            )
        except:
            pass
    
    context.user_data.pop('add_role', None)
    context.user_data.pop('add_state', None)

async def remove_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ Нет прав.")
        return
    
    context.user_data['remove_state'] = 'WAITING_USER_ID'
    
    await query.edit_message_text(
        "➖ <b>Удаление пользователя</b>\n\n"
        "Отправьте ID пользователя, которого хотите удалить:\n\n"
        "Пример: 123456789\n\n"
        "⚠️ Нельзя удалить Chief PR Manager и Создателя.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )

async def remove_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    try:
        remove_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ Введите корректный ID (только цифры).")
        return
    
    if remove_id == CHIEF_ID:
        await update.message.reply_text("❌ Нельзя удалить Chief PR Manager.")
        return
    
    if remove_id == CREATOR_ID:
        await update.message.reply_text("❌ Нельзя удалить Создателя.")
        return
    
    removed = db.remove_pr_manager(remove_id) or db.remove_dep_chief(remove_id)
    if removed:
        await update.message.reply_text(f"✅ Пользователь {remove_id} удалён.")
    else:
        await update.message.reply_text("❌ Пользователь не найден.")
    
    context.user_data.pop('remove_state', None)

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

# ============ ПОИСК И ЗАКРЫТИЕ ТЕМ ============

async def search_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ /search <ключевое_слово>")
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

async def close_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ /close_topic <id_темы>")
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
            
            if GROUP_ID == 0:
                await query.edit_message_text("❌ GROUP_ID не настроен!")
                return
            
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
            
            topics_list = []
            for tid in topics:
                data_topic = db.topics.get(tid)
                if data_topic:
                    topics_list.append((tid, data_topic))
            
            text = "📋 <b>Ваши запросы:</b>\n\n"
            for tid, data_topic in topics_list:
                status = "🟢 Активна" if data_topic.is_active else "🔴 Закрыта"
                text += f"• <b>{sanitize_text(data_topic.channel_name)}</b>\n"
                text += f"  ID: <code>{tid}</code> | {status}\n"
                text += f"  👥 {data_topic.subscribers}\n\n"
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_my_requests_keyboard(topics_list)
            )
            return

        if data.startswith("open_topic_"):
            topic_id = int(data.split("_")[2])
            await open_topic(update, context, topic_id)
            return

        if data.startswith("goto_topic_"):
            topic_id = int(data.split("_")[2])
            await goto_topic(update, context, topic_id)
            return

        if data.startswith("close_topic_"):
            topic_id = int(data.split("_")[2])
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            
            if topic_id not in db.topics:
                await query.edit_message_text("❌ Тема не найдена.")
                return
            
            if not db.topics[topic_id].is_active:
                await query.edit_message_text("❌ Тема уже закрыта.")
                return
            
            db.close_topic(topic_id, user_id)
            
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=topic_id,
                text="🔒 Тема закрыта администратором."
            )
            
            await query.edit_message_text(f"✅ Тема {topic_id} закрыта.")
            return

        elif data == "admin_panel":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await admin_panel(update, context)
            return

        elif data == "statistics":
            await statistics(update, context)
            return

        elif data == "manage_users":
            await manage_users(update, context)
            return

        elif data == "add_creator":
            if not is_creator(user_id):
                await query.edit_message_text("❌ Только Создатель может добавлять Создателя.")
                return
            await add_user_start(update, context, "creator")
            return

        elif data == "add_chief":
            if not is_creator(user_id) and not is_chief(user_id):
                await query.edit_message_text("❌ Только Chief или Создатель может добавлять Chief.")
                return
            await add_user_start(update, context, "chief")
            return

        elif data == "add_dep":
            if not is_creator(user_id) and not is_chief(user_id):
                await query.edit_message_text("❌ Только Chief или Создатель может добавлять Dep.Chief.")
                return
            await add_user_start(update, context, "dep")
            return

        elif data == "add_pr":
            await add_user_start(update, context, "pr")
            return

        elif data == "remove_user":
            await remove_user_start(update, context)
            return

        elif data == "list_users":
            await list_users(update, context)
            return

        elif data == "search":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await query.edit_message_text(
                "🔍 <b>Поиск тем</b>\n\n"
                "Используйте команду:\n/search <ключевое_слово>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_panel_keyboard(
                    is_creator=is_creator(user_id),
                    is_chief=is_chief(user_id),
                    is_dep_chief=is_dep_chief(user_id)
                )
            )
            return

        elif data == "close_topic":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await query.edit_message_text(
                "🔒 <b>Закрытие темы</b>\n\n"
                "Используйте команду:\n/close_topic <id_темы>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_panel_keyboard(
                    is_creator=is_creator(user_id),
                    is_chief=is_chief(user_id),
                    is_dep_chief=is_dep_chief(user_id)
                )
            )
            return

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
            return

        elif data == "skip":
            request_data = context.user_data.get('request_data', {})
            request_data['conditions'] = "Не указаны"
            context.user_data['request_data'] = request_data
            await query.edit_message_text("⏭️ Условия пропущены.")
            class FakeUpdate:
                def __init__(self, user, chat):
                    self.effective_user = user
                    self.effective_chat = chat
                    self.message = type('obj', (object,), {
                        'reply_text': lambda self, *args, **kwargs: None
                    })()
            fake_update = FakeUpdate(query.from_user, query.message.chat)
            await finish_request(fake_update, context)
            return

        elif data == "cancel":
            context.user_data.pop('request_state', None)
            context.user_data.pop('request_data', None)
            context.user_data.pop('add_role', None)
            context.user_data.pop('add_state', None)
            context.user_data.pop('remove_state', None)
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
            return

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
