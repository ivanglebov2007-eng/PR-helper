import logging
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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

db = None

def set_db(database_instance):
    global db
    db = database_instance

def is_chief(user_id: int) -> bool:
    if user_id == CHIEF_ID:
        return True
    if db:
        return db.is_chief(user_id)
    return False

def is_dep_chief(user_id: int) -> bool:
    if user_id == CHIEF_ID:
        return True
    if db:
        return db.is_dep_chief(user_id)
    return False

def is_admin(user_id: int) -> bool:
    return is_chief(user_id) or is_dep_chief(user_id) or user_id == CREATOR_ID

def is_pr_manager(user_id: int) -> bool:
    if user_id == CREATOR_ID or user_id == CHIEF_ID:
        return True
    if db:
        return db.is_pr_manager(user_id)
    return False

def is_creator(user_id: int) -> bool:
    return user_id == CREATOR_ID

async def get_user_name(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    try:
        chat = await context.bot.get_chat(user_id)
        if chat.username:
            return f"@{chat.username}"
        elif chat.full_name:
            return chat.full_name
        else:
            return str(user_id)
    except:
        return str(user_id)

async def close_topic_with_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int) -> bool:
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        return False
    if not db.get_topic(topic_id):
        return False
    topic_data = db.get_topic(topic_id)
    if not topic_data or not topic_data.is_active:
        return False
    db.close_topic(topic_id, user_id)
    try:
        await context.bot.delete_forum_topic(
            chat_id=GROUP_ID,
            message_thread_id=topic_id
        )
        logger.info(f"✅ Тема {topic_id} удалена из группы и заархивирована в БД")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления темы {topic_id}: {e}")
        return True

def get_main_reply_keyboard(is_admin: bool = False, is_creator: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        ["📝 Создать запрос"],
        ["📋 Мои запросы"],
    ]
    if is_admin or is_creator:
        keyboard.append(["⚙️ Админ-панель"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["❌ Отмена"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_skip_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["⏭️ Пропустить"],
            ["❌ Отмена"]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_admin_reply_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["👥 Управление пользователями"],
        ["🔍 Поиск тем", "🔒 Закрыть тему"],
        ["📊 Статистика", "📂 Архив"],
        ["🔙 Назад"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_manage_users_reply_keyboard(is_creator: bool = False, is_chief: bool = False, is_dep_chief: bool = False) -> ReplyKeyboardMarkup:
    keyboard = []
    if is_creator:
        keyboard.append(["➕ Добавить Создателя"])
        keyboard.append(["➕ Добавить Chief"])
        keyboard.append(["➕ Добавить Dep.Chief"])
        keyboard.append(["➕ Добавить PR"])
    elif is_chief:
        keyboard.append(["➕ Добавить Chief"])
        keyboard.append(["➕ Добавить Dep.Chief"])
        keyboard.append(["➕ Добавить PR"])
    elif is_dep_chief:
        keyboard.append(["➕ Добавить PR"])
    keyboard.append(["➖ Удалить пользователя"])
    keyboard.append(["📋 Список пользователей"])
    keyboard.append(["🔙 Назад"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_my_requests_inline_keyboard(topics: list) -> InlineKeyboardMarkup:
    keyboard = []
    for topic_id, data in topics:
        status = "🟢" if data.is_active else "🔴"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {data.channel_name}",
                callback_data=f"open_topic_{topic_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_topic_action_inline_keyboard(topic_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📂 Перейти к теме", callback_data=f"goto_topic_{topic_id}")],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("🔒 Закрыть тему", callback_data=f"close_topic_{topic_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="my_requests")])
    return InlineKeyboardMarkup(keyboard)

def get_back_to_main_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ])

def get_close_topic_inline_keyboard(active_topics: list) -> InlineKeyboardMarkup:
    keyboard = []
    if not active_topics:
        keyboard.append([InlineKeyboardButton("📭 Нет активных тем", callback_data="no_topics")])
    else:
        for topic_id, data in active_topics:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔴 {data.channel_name} ({data.subscribers})",
                    callback_data=f"close_topic_select_{topic_id}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔴 Закрыть ВСЕ темы", callback_data="close_all_topics")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_archive_inline_keyboard(closed_topics: list) -> InlineKeyboardMarkup:
    keyboard = []
    if not closed_topics:
        keyboard.append([InlineKeyboardButton("📭 Архив пуст", callback_data="no_topics")])
    else:
        for topic_id, data in closed_topics[:20]:
            keyboard.append([
                InlineKeyboardButton(
                    f"📁 {data.channel_name}",
                    callback_data=f"archive_topic_{topic_id}"
                )
            ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if not is_pr_manager(user_id) and not is_creator(user_id):
        await update.message.reply_text(
            "❌ У вас нет доступа.\nОбратитесь к Chief PR Manager.",
            reply_markup=get_cancel_reply_keyboard()
        )
        return
    text = f"👋 <b>Главное меню, {sanitize_text(user.full_name)}!</b>\n\nВыберите действие:"
    keyboard = get_main_reply_keyboard(
        is_admin=is_admin(user_id),
        is_creator=is_creator(user_id)
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def new_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_pr_manager(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    if GROUP_ID == 0:
        await update.message.reply_text(
            "❌ GROUP_ID не настроен!",
            reply_markup=get_cancel_reply_keyboard()
        )
        return
    context.user_data['request_state'] = 'SCREENSHOT'
    context.user_data['request_data'] = {}
    await update.message.reply_text(
        "📝 <b>Шаг 1/6: отправьте СКРИНШОТ переписки</b>\n\n"
        "Отправьте фото (скриншот диалога с медиа):\n\n"
        "Или нажмите 'Отмена' для выхода.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_reply_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data.get('request_state')
    add_state = context.user_data.get('add_state')
    remove_state = context.user_data.get('remove_state')
    search_state = context.user_data.get('search_state')
    
    if add_state == 'WAITING_USERNAME':
        await add_user_confirm(update, context)
        return
    if remove_state == 'WAITING_USER_ID':
        await remove_user_confirm(update, context)
        return
    if search_state == 'WAITING_KEYWORD':
        await search_topics_confirm(update, context)
        return
    
    if not state:
        if text == "📝 Создать запрос":
            await new_request_start(update, context)
            return
        elif text == "📋 Мои запросы":
            await my_requests(update, context)
            return
        elif text == "⚙️ Админ-панель":
            await admin_panel(update, context)
            return
        elif text == "👥 Управление пользователями":
            await manage_users(update, context)
            return
        elif text == "🔍 Поиск тем":
            await search_topics_prompt(update, context)
            return
        elif text == "🔒 Закрыть тему":
            await show_close_topics(update, context)
            return
        elif text == "📊 Статистика":
            await statistics(update, context)
            return
        elif text == "📂 Архив":
            await show_archive(update, context)
            return
        elif text == "➕ Добавить Создателя":
            await add_user_start(update, context, "creator")
            return
        elif text == "➕ Добавить Chief":
            await add_user_start(update, context, "chief")
            return
        elif text == "➕ Добавить Dep.Chief":
            await add_user_start(update, context, "dep")
            return
        elif text == "➕ Добавить PR":
            await add_user_start(update, context, "pr")
            return
        elif text == "➖ Удалить пользователя":
            await remove_user_start(update, context)
            return
        elif text == "📋 Список пользователей":
            await list_users(update, context)
            return
        elif text == "🔙 Назад":
            await back_to_main(update, context)
            return
        elif text == "❌ Отмена":
            await cancel_operation(update, context)
            return
        elif text == "⏭️ Пропустить":
            request_data = context.user_data.get('request_data', {})
            request_data['conditions'] = "Не указаны"
            context.user_data['request_data'] = request_data
            await update.message.reply_text("⏭️ Условия пропущены.")
            await finish_request(update, context)
            return
        return
    
    request_data = context.user_data.get('request_data', {})
    
    if state == 'SCREENSHOT':
        photo = update.message.photo
        if not photo:
            await update.message.reply_text(
                "❌ Отправьте изображение (фото).\nПопробуйте ещё раз:",
                reply_markup=get_cancel_reply_keyboard()
            )
            return
        try:
            photo_obj = photo[-1]
            file_id = photo_obj.file_id
            file_unique_id = photo_obj.file_unique_id
            file = await photo_obj.get_file()
            file_url = file.file_path
            
            request_data['screenshot'] = file_url
            request_data['screenshot_info'] = {
                'file_id': file_id,
                'file_unique_id': file_unique_id,
                'caption': f"📸 Скриншот для запроса: {request_data.get('channel_name', 'канал')}"
            }
            context.user_data['request_data'] = request_data
            context.user_data['request_state'] = 'MEDIA_LINK'
            
            await update.message.reply_text(
                "✅ Скриншот получен!\n\n"
                "📎 <b>Шаг 2/6: отправьте ссылку на канал</b>\n"
                "Поддерживаются: YouTube, Twitch, TikTok\n\n"
                "Пример: https://www.youtube.com/@channel",
                parse_mode=ParseMode.HTML,
                reply_markup=get_cancel_reply_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка скриншота: {e}")
            await update.message.reply_text(
                "❌ Ошибка при загрузке фото. Попробуйте ещё раз.",
                reply_markup=get_cancel_reply_keyboard()
            )
        return
    
    if state == 'MEDIA_LINK':
        if not validate_media_link(text):
            await update.message.reply_text(
                "❌ Некорректная ссылка.\n"
                "Ссылка должна начинаться с http:// или https://\n"
                "И содержать: youtube, twitch или tiktok\n\n"
                "Попробуйте ещё раз:",
                reply_markup=get_cancel_reply_keyboard()
            )
            return
        request_data['media_link'] = text
        context.user_data['request_data'] = request_data
        context.user_data['request_state'] = 'CHANNEL_NAME'
        await update.message.reply_text(
            "✅ Ссылка принята.\n\n"
            "📌 <b>Шаг 3/6: введите название канала</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_reply_keyboard()
        )
        return
    
    if state == 'CHANNEL_NAME':
        if not text:
            await update.message.reply_text(
                "❌ Название не может быть пустым.",
                reply_markup=get_cancel_reply_keyboard()
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
            reply_markup=get_cancel_reply_keyboard()
        )
        return
    
    if state == 'SUBSCRIBERS':
        try:
            subs = int(text.replace(' ', '').replace(',', '').replace('.', ''))
            if subs < 0:
                raise ValueError
            formatted = f"{subs:,}".replace(',', ' ')
        except ValueError:
            await update.message.reply_text(
                "❌ Введите корректное число (только цифры).\n"
                "Пример: 10000",
                reply_markup=get_cancel_reply_keyboard()
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
            reply_markup=get_cancel_reply_keyboard()
        )
        return
    
    if state == 'CONTACT_LINK':
        if not text:
            await update.message.reply_text(
                "❌ Введите ссылку.",
                reply_markup=get_cancel_reply_keyboard()
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
            "Или нажмите 'Пропустить':",
            parse_mode=ParseMode.HTML,
            reply_markup=get_skip_reply_keyboard()
        )
        return
    
    if state == 'CONDITIONS':
        request_data['conditions'] = sanitize_text(text) if text else "Не указаны"
        context.user_data['request_data'] = request_data
        await finish_request(update, context)

async def finish_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    request_data = context.user_data.get('request_data', {})
    
    missing = [f for f in REQUIRED_FIELDS if f not in request_data or not request_data[f]]
    if missing:
        await update.message.reply_text(
            f"❌ Не хватает полей: {', '.join(missing)}\n"
            "Начните заново с /new_request",
            reply_markup=get_main_reply_keyboard(
                is_admin=is_admin(user_id),
                is_creator=is_creator(user_id)
            )
        )
        context.user_data.pop('request_state', None)
        context.user_data.pop('request_data', None)
        return

    screenshot_info = request_data.get('screenshot_info', {})
    photo_file_id = screenshot_info.get('file_id')
    photo_caption = screenshot_info.get('caption', f"📸 Скриншот для запроса: {request_data['channel_name']}")
    
    photo_sent = False
    
    if photo_file_id:
        try:
            sent_photo = await context.bot.send_photo(
                chat_id=GROUP_ID,
                photo=photo_file_id,
                caption=photo_caption,
                parse_mode=ParseMode.HTML
            )
            photo_sent = True
            logger.info("✅ Фото отправлено в группу по file_id")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото по file_id: {e}")
            try:
                sent_doc = await context.bot.send_document(
                    chat_id=GROUP_ID,
                    document=photo_file_id,
                    caption=photo_caption
                )
                photo_sent = True
                logger.info("✅ Фото отправлено как документ")
            except Exception as e2:
                logger.error(f"❌ Ошибка отправки документа: {e2}")
    
    if not photo_sent:
        screenshot_url = request_data.get('screenshot')
        if screenshot_url:
            try:
                await context.bot.send_photo(
                    chat_id=GROUP_ID,
                    photo=screenshot_url,
                    caption=photo_caption,
                    parse_mode=ParseMode.HTML
                )
                photo_sent = True
                logger.info("✅ Фото отправлено по ссылке")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки фото по ссылке: {e}")
                try:
                    await context.bot.send_message(
                        chat_id=GROUP_ID,
                        text=f"📸 {photo_caption}\n{screenshot_url}",
                        parse_mode=ParseMode.HTML
                    )
                    photo_sent = True
                    logger.info("✅ Ссылка на скриншот отправлена")
                except Exception as e3:
                    logger.error(f"❌ Ошибка отправки ссылки: {e3}")

    topic_id = await create_request_topic(update, context, request_data, photo_sent, request_data.get('screenshot'))

    if topic_id:
        request_obj = RequestData(
            screenshot=request_data.get('screenshot', 'Не указан'),
            media_link=request_data['media_link'],
            channel_name=request_data['channel_name'],
            subscribers=request_data['subscribers'],
            contact_link=request_data['contact_link'],
            conditions=request_data.get('conditions', "Не указаны"),
            user_id=user_id,
            created_at=datetime.now().isoformat()
        )
        db.add_topic(topic_id, request_obj)
        keyboard = get_main_reply_keyboard(
            is_admin=is_admin(user_id),
            is_creator=is_creator(user_id)
        )
        await update.message.reply_text(
            f"✅ <b>Запрос успешно создан!</b>\n\n"
            f"🆔 ID темы: <code>{topic_id}</code>\n"
            f"📌 Тема создана в группе и отмечена для руководства.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    else:
        error_msg = "❌ Не удалось создать запрос. Проверьте:\n" \
                    "1. Что бот является администратором группы\n" \
                    "2. Что в группе включён режим форума\n" \
                    "3. Что у бота есть право 'Управление темами'\n" \
                    "4. Что GROUP_ID правильный (должен быть отрицательным!)"
        await update.message.reply_text(
            error_msg,
            reply_markup=get_main_reply_keyboard(
                is_admin=is_admin(user_id),
                is_creator=is_creator(user_id)
            )
        )
    context.user_data.pop('request_state', None)
    context.user_data.pop('request_data', None)

async def create_request_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, request_data: dict, photo_sent: bool = False, screenshot_url: str = None) -> Optional[int]:
    user = update.effective_user
    topic_title = f"Запрос от {user.full_name} — {request_data['channel_name']}"
    try:
        if GROUP_ID == 0:
            logger.error("GROUP_ID не настроен!")
            return None
        chat = await context.bot.get_chat(GROUP_ID)
        logger.info(f"✅ Группа: {chat.title} (ID: {chat.id})")
        bot_member = await context.bot.get_chat_member(GROUP_ID, context.bot.id)
        logger.info(f"Статус бота: {bot_member.status}")
        logger.info(f"📝 Создаю тему: {topic_title[:255]}")
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=topic_title[:255]
        )
        topic_id = topic.message_thread_id
        logger.info(f"✅ Тема создана! ID: {topic_id}")
        if photo_sent:
            photo_text = "📸 Скриншот приложен выше"
        elif screenshot_url:
            photo_text = f"📸 <a href='{screenshot_url}'>Скриншот</a>"
        else:
            photo_text = "📸 Скриншот: (не удалось отправить)"
        text = (
            f"📢 <b>НОВЫЙ ЗАПРОС НА МЕДИА-ПАРТНЕРСТВО</b>\n\n"
            f"👤 <b>PR Менеджер:</b> {sanitize_text(user.full_name)}\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📅 <b>Дата:</b> {format_date(datetime.now().isoformat())}\n\n"
            f"📌 <b>Канал:</b> {sanitize_text(request_data['channel_name'])}\n"
            f"👥 <b>Подписчиков:</b> {request_data['subscribers']}\n"
            f"🔗 <b>Ссылка:</b> <a href='{request_data['media_link']}'>Открыть</a>\n"
            f"📞 <b>Связь:</b> <a href='{request_data['contact_link']}'>Написать</a>\n"
            f"📝 <b>Условия:</b>\n{sanitize_text(request_data.get('conditions', 'Не указаны'))}\n\n"
            f"{photo_text}\n\n"
            f"⏳ <b>Ожидайте ответа от руководства!</b>"
        )
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        chief_name = await get_user_name(context, CHIEF_ID)
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=topic_id,
                text=f"🔔 <a href='tg://user?id={CHIEF_ID}'>{chief_name}</a>, новый запрос!",
                parse_mode=ParseMode.HTML
            )
            logger.info("✅ Chief уведомлён")
        except Exception as e:
            logger.error(f"❌ Ошибка тегирования Chief: {e}")
        dep_chiefs = db.get_dep_chiefs()
        if dep_chiefs:
            for dep_id in dep_chiefs:
                dep_name = await get_user_name(context, dep_id)
                try:
                    await context.bot.send_message(
                        chat_id=GROUP_ID,
                        message_thread_id=topic_id,
                        text=f"🔔 <a href='tg://user?id={dep_id}'>{dep_name}</a>, новый запрос!",
                        parse_mode=ParseMode.HTML
                    )
                    logger.info(f"✅ Dep.Chief {dep_id} уведомлён")
                except Exception as e:
                    logger.error(f"❌ Ошибка тегирования Dep.Chief {dep_id}: {e}")
        else:
            logger.info("ℹ️ Dep.Chief не найдены в БД")
        try:
            admins = await context.bot.get_chat_administrators(GROUP_ID)
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

# ============ ОСТАЛЬНЫЕ ФУНКЦИИ (my_requests, admin_panel, статистика, управление пользователями и т.д.) ============
# Они остаются без изменений из предыдущей версии
# (полный код всех функций есть в предыдущих сообщениях)

async def my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    topics = db.get_user_topics(user_id)
    if not topics:
        keyboard = get_main_reply_keyboard(
            is_admin=is_admin(user_id),
            is_creator=is_creator(user_id)
        )
        await update.message.reply_text(
            "📋 У вас нет запросов.",
            reply_markup=keyboard
        )
        return
    topics_list = []
    for tid in topics:
        data = db.get_topic(tid)
        if data:
            topics_list.append((tid, data))
    if not topics_list:
        keyboard = get_main_reply_keyboard(
            is_admin=is_admin(user_id),
            is_creator=is_creator(user_id)
        )
        await update.message.reply_text(
            "📋 У вас нет запросов.",
            reply_markup=keyboard
        )
        return
    text = "📋 <b>Ваши запросы:</b>"
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_my_requests_inline_keyboard(topics_list)
    )

async def open_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    query = update.callback_query
    user_id = query.from_user.id
    topic_data = db.get_topic(topic_id)
    if not topic_data:
        await query.edit_message_text("❌ Тема не найдена.")
        return
    if topic_data.user_id != user_id and not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ У вас нет доступа к этой теме.")
        return
    topic_link = f"https://t.me/c/{str(GROUP_ID)[4:]}/{topic_id}"
    await query.edit_message_text(
        f"🔗 <b>Переход к теме #{topic_id}</b>\n\n"
        f"<a href='{topic_link}'>Открыть тему</a>\n\n"
        f"ID: <code>{topic_id}</code>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=get_topic_action_inline_keyboard(topic_id, is_admin(user_id) or is_creator(user_id))
    )

async def goto_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    query = update.callback_query
    topic_link = f"https://t.me/c/{str(GROUP_ID)[4:]}/{topic_id}"
    await query.edit_message_text(
        f"🔗 <a href='{topic_link}'>Открыть тему #{topic_id}</a>\n\n"
        f"ID: <code>{topic_id}</code>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=get_back_to_main_inline_keyboard()
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    text = (
        "⚙️ <b>Админ-панель</b>\n\n"
        "Управление ботом и пользователями.\n"
        f"👤 Ваша роль: "
        f"{'Создатель' if is_creator(user_id) else 'Chief' if is_chief(user_id) else 'Dep.Chief'}"
    )
    keyboard = get_admin_reply_keyboard()
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def show_close_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    active_topics = db.get_active_topics()
    if not active_topics:
        keyboard = [
            [InlineKeyboardButton("📭 Нет активных тем", callback_data="no_topics")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        await update.message.reply_text(
            "📭 Нет активных тем для закрытия.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    text = "🔒 <b>Выберите тему для закрытия:</b>\n\n"
    for topic_id, data in active_topics:
        text += f"• ID: <code>{topic_id}</code> | {sanitize_text(data.channel_name)} ({data.subscribers})\n"
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_close_topic_inline_keyboard(active_topics)
    )

async def close_topic_select(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ Нет прав.")
        return
    if not db.get_topic(topic_id):
        await query.edit_message_text("❌ Тема не найдена.")
        return
    topic_data = db.get_topic(topic_id)
    if not topic_data or not topic_data.is_active:
        await query.edit_message_text("❌ Тема уже закрыта.")
        return
    success = await close_topic_with_delete(update, context, topic_id)
    if success:
        await query.edit_message_text(f"✅ Тема {topic_id} успешно закрыта и заархивирована.")
    else:
        await query.edit_message_text("❌ Ошибка при закрытии темы.")

async def close_all_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ Нет прав.")
        return
    active_topics = db.get_active_topics()
    if not active_topics:
        await query.edit_message_text("📭 Нет активных тем для закрытия.")
        return
    await query.edit_message_text(f"⏳ Закрываю {len(active_topics)} тем...")
    success_count = 0
    for topic_id, _ in active_topics:
        success = await close_topic_with_delete(update, context, topic_id)
        if success:
            success_count += 1
    await query.edit_message_text(
        f"✅ Закрыто {success_count} из {len(active_topics)} тем.\n"
        f"❌ Не закрыто: {len(active_topics) - success_count}"
    )

async def show_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    closed_topics = db.get_closed_topics()
    if not closed_topics:
        keyboard = [
            [InlineKeyboardButton("📭 Архив пуст", callback_data="no_topics")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        await update.message.reply_text(
            "📭 Архив пуст.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    text = "📂 <b>Архив закрытых тем</b>\n\n"
    for topic_id, data in closed_topics[:10]:
        closed_date = format_date(data.closed_at) if data.closed_at else "неизвестно"
        text += f"• {sanitize_text(data.channel_name)} ({data.subscribers}) — закрыта {closed_date}\n"
    text += f"\n📊 Всего в архиве: {len(closed_topics)}"
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_archive_inline_keyboard(closed_topics)
    )

async def archive_topic_view(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await query.edit_message_text("❌ Нет прав.")
        return
    topic_data = db.get_topic(topic_id)
    if not topic_data:
        await query.edit_message_text("❌ Тема не найдена.")
        return
    text = (
        f"📂 <b>Архивная тема #{topic_id}</b>\n\n"
        f"📌 <b>Канал:</b> {sanitize_text(topic_data.channel_name)}\n"
        f"👥 <b>Подписчиков:</b> {topic_data.subscribers}\n"
        f"📅 <b>Создана:</b> {format_date(topic_data.created_at)}\n"
        f"🔗 <b>Ссылка:</b> <a href='{topic_data.media_link}'>Открыть</a>\n"
        f"📞 <b>Связь:</b> <a href='{topic_data.contact_link}'>Написать</a>\n"
        f"📝 <b>Условия:</b>\n{sanitize_text(topic_data.conditions)}\n"
        f"📸 <b>Скриншот:</b> <a href='{topic_data.screenshot}'>Смотреть</a>\n\n"
        f"🔒 <b>Закрыта:</b> {format_date(topic_data.closed_at) if topic_data.closed_at else 'неизвестно'}"
    )
    keyboard = [
        [InlineKeyboardButton("🔙 Назад в архив", callback_data="archive_back")]
    ]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    stats = db.get_statistics()
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👤 <b>Пользователи:</b>\n"
        f"  • Создатель: 1\n"
        f"  • Chief: 1\n"
        f"  • Dep.Chief: {stats['dep_chief_count']}\n"
        f"  • PR Managers: {stats['pr_count']}\n"
        f"  • Всего: {stats['total_users']}\n\n"
        f"📋 <b>Темы:</b>\n"
        f"  • Всего: {stats['total_topics']}\n"
        f"  • Активных: {stats['active_topics']}\n"
        f"  • Закрытых (в архиве): {stats['closed_topics']}\n\n"
        f"💾 <b>База данных:</b>\n"
        f"  • Тип: PostgreSQL"
    )
    keyboard = get_admin_reply_keyboard()
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    text = (
        "👥 <b>Управление пользователями</b>\n\n"
        "Выберите действие:\n"
        f"👤 Ваша роль: "
        f"{'Создатель' if is_creator(user_id) else 'Chief' if is_chief(user_id) else 'Dep.Chief'}\n\n"
        f"📋 Всего пользователей: {len(db.get_all_users())}"
    )
    keyboard = get_manage_users_reply_keyboard(
        is_creator=is_creator(user_id),
        is_chief=is_chief(user_id),
        is_dep_chief=is_dep_chief(user_id)
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str):
    user_id = update.effective_user.id
    if role == "creator" and not is_creator(user_id):
        await update.message.reply_text("❌ Только Создатель может добавлять Создателя.")
        return
    if role == "chief" and not is_creator(user_id) and not is_chief(user_id):
        await update.message.reply_text("❌ Только Chief или Создатель может добавлять Chief.")
        return
    if role == "dep" and not is_creator(user_id) and not is_chief(user_id):
        await update.message.reply_text("❌ Только Chief или Создатель может добавлять Dep.Chief.")
        return
    role_names = {
        "creator": "Создателя",
        "chief": "Chief PR Manager",
        "dep": "Dep.Chief PR Manager",
        "pr": "PR Manager"
    }
    context.user_data['add_role'] = role
    context.user_data['add_state'] = 'WAITING_USERNAME'
    await update.message.reply_text(
        f"➕ <b>Добавление {role_names.get(role, 'пользователя')}</b>\n\n"
        f"Отправьте username пользователя (например, @username) или его ID:\n\n"
        f"Пример: @john или 123456789\n\n"
        f"💡 <b>Важно:</b> Чтобы добавить пользователя по username,\n"
        f"пользователь должен:\n"
        f"1. Иметь публичный username в Telegram\n"
        f"2. Написать боту в ЛС (/start)\n\n"
        f"Для отмены нажмите кнопку 'Отмена'.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_reply_keyboard()
    )

async def add_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    role = context.user_data.get('add_role')
    if not role:
        return
    if text == "❌ Отмена":
        await cancel_operation(update, context)
        return
    new_user_id = None
    username = text.replace('@', '').strip()
    if username.isdigit():
        new_user_id = int(username)
    else:
        try:
            chat = await context.bot.get_chat(f"@{username}")
            new_user_id = chat.id
        except:
            pass
    if not new_user_id:
        await update.message.reply_text(
            "❌ Не удалось найти пользователя.\n\n"
            "💡 <b>Совет:</b>\n"
            "1. Попросите пользователя написать боту: /start\n"
            "2. Или используйте ID пользователя (цифры)\n\n"
            "Или нажмите 'Отмена'.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_reply_keyboard()
        )
        return
    if new_user_id == CHIEF_ID:
        await update.message.reply_text("❌ Это Chief PR Manager.")
        return
    if new_user_id == CREATOR_ID:
        await update.message.reply_text("❌ Это Создатель.")
        return
    success = False
    if role == "creator":
        if is_creator(user_id):
            success = db.add_user(new_user_id, role='pr')
            await update.message.reply_text(
                f"✅ Пользователь {new_user_id} добавлен как PR Manager."
            )
        else:
            await update.message.reply_text("❌ Нет прав для добавления Создателя.")
            return
    elif role == "chief":
        if is_creator(user_id) or is_chief(user_id):
            success = db.add_user(new_user_id, role='pr')
            await update.message.reply_text(
                f"✅ Пользователь {new_user_id} добавлен как PR Manager."
            )
        else:
            await update.message.reply_text("❌ Нет прав для добавления Chief.")
            return
    elif role == "dep":
        if is_creator(user_id) or is_chief(user_id):
            success = db.add_user(new_user_id, role='dep_chief')
            if success:
                await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен как Dep.Chief.")
            else:
                await update.message.reply_text("❌ Ошибка добавления.")
        else:
            await update.message.reply_text("❌ Нет прав для добавления Dep.Chief.")
            return
    elif role == "pr":
        success = db.add_user(new_user_id, role='pr')
        if success:
            await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен как PR Manager.")
        else:
            await update.message.reply_text("❌ Ошибка добавления.")
    if success:
        try:
            await context.bot.send_message(
                chat_id=new_user_id,
                text=f"🎉 Вас добавили в систему PR Manager бота!\n\nВаша роль: {role.upper()}\nИспользуйте /start для начала работы."
            )
        except:
            pass
        keyboard = get_manage_users_reply_keyboard(
            is_creator=is_creator(user_id),
            is_chief=is_chief(user_id),
            is_dep_chief=is_dep_chief(user_id)
        )
        await update.message.reply_text("✅ Операция завершена.", reply_markup=keyboard)
    context.user_data.pop('add_role', None)
    context.user_data.pop('add_state', None)

async def remove_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    context.user_data['remove_state'] = 'WAITING_USER_ID'
    await update.message.reply_text(
        "➖ <b>Удаление пользователя</b>\n\n"
        "Отправьте ID пользователя, которого хотите удалить:\n\n"
        "Пример: 123456789\n\n"
        "⚠️ Нельзя удалить Chief PR Manager и Создателя.\n\n"
        "Для отмены нажмите кнопку 'Отмена'.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_reply_keyboard()
    )

async def remove_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text == "❌ Отмена":
        await cancel_operation(update, context)
        return
    try:
        remove_id = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Введите корректный ID (только цифры).",
            reply_markup=get_cancel_reply_keyboard()
        )
        return
    if remove_id == CHIEF_ID:
        await update.message.reply_text("❌ Нельзя удалить Chief PR Manager.")
        return
    if remove_id == CREATOR_ID:
        await update.message.reply_text("❌ Нельзя удалить Создателя.")
        return
    success = db.remove_user(remove_id)
    if success:
        await update.message.reply_text(f"✅ Пользователь {remove_id} удалён.")
    else:
        await update.message.reply_text("❌ Пользователь не найден.")
    keyboard = get_manage_users_reply_keyboard(
        is_creator=is_creator(user_id),
        is_chief=is_chief(user_id),
        is_dep_chief=is_dep_chief(user_id)
    )
    await update.message.reply_text("✅ Операция завершена.", reply_markup=keyboard)
    context.user_data.pop('remove_state', None)

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    text = "👥 <b>Список пользователей:</b>\n\n"
    all_users = db.get_all_users()
    pr_users = [u for u in all_users if u['role'] == 'pr']
    dep_users = [u for u in all_users if u['role'] == 'dep_chief']
    chief_users = [u for u in all_users if u['role'] == 'chief']
    if pr_users:
        text += "👤 <b>PR Managers:</b>\n"
        for u in pr_users:
            name = await get_user_name(context, u['user_id'])
            text += f"• <a href='tg://user?id={u['user_id']}'>{name}</a>\n"
        text += "\n"
    if dep_users:
        text += "👤 <b>Dep.Chief:</b>\n"
        for u in dep_users:
            name = await get_user_name(context, u['user_id'])
            text += f"• <a href='tg://user?id={u['user_id']}'>{name}</a>\n"
        text += "\n"
    if chief_users:
        text += "👤 <b>Chief:</b>\n"
        for u in chief_users:
            name = await get_user_name(context, u['user_id'])
            text += f"• <a href='tg://user?id={u['user_id']}'>{name}</a>\n"
        text += "\n"
    chief_name = await get_user_name(context, CHIEF_ID)
    text += f"👑 <b>Chief PR Manager:</b>\n• <a href='tg://user?id={CHIEF_ID}'>{chief_name}</a>\n\n"
    creator_name = await get_user_name(context, CREATOR_ID)
    text += f"👑 <b>Creator:</b>\n• <a href='tg://user?id={CREATOR_ID}'>{creator_name}</a>"
    keyboard = get_manage_users_reply_keyboard(
        is_creator=is_creator(user_id),
        is_chief=is_chief(user_id),
        is_dep_chief=is_dep_chief(user_id)
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def search_topics_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return
    context.user_data['search_state'] = 'WAITING_KEYWORD'
    await update.message.reply_text(
        "🔍 <b>Поиск тем</b>\n\n"
        "Введите ключевое слово для поиска:\n\n"
        "Пример: канал\n\n"
        "Для отмены нажмите 'Отмена'.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_reply_keyboard()
    )

async def search_topics_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text == "❌ Отмена":
        await cancel_operation(update, context)
        return
    if not text:
        await update.message.reply_text(
            "❌ Введите ключевое слово.",
            reply_markup=get_cancel_reply_keyboard()
        )
        return
    keyword = text.lower()
    results = db.search_topics(keyword)
    if not results:
        keyboard = get_admin_reply_keyboard()
        await update.message.reply_text(
            f"❌ По запросу '{keyword}' ничего не найдено.",
            reply_markup=keyboard
        )
        context.user_data.pop('search_state', None)
        return
    text_msg = f"🔍 <b>Результаты поиска по '{keyword}':</b>\n\n"
    for tid, data in results:
        text_msg += f"• ID: <code>{tid}</code> | {sanitize_text(data.channel_name)}\n"
        text_msg += f"  👥 {data.subscribers} | 📅 {format_date(data.created_at)}\n\n"
    keyboard = get_admin_reply_keyboard()
    context.user_data.pop('search_state', None)
    await update.message.reply_text(
        text_msg,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    try:
        await query.answer()
        data = query.data
        if data.startswith("open_topic_"):
            topic_id = int(data.split("_")[2])
            await open_topic(update, context, topic_id)
            return
        if data.startswith("goto_topic_"):
            topic_id = int(data.split("_")[2])
            await goto_topic(update, context, topic_id)
            return
        if data.startswith("close_topic_select_"):
            topic_id = int(data.split("_")[3])
            await close_topic_select(update, context, topic_id)
            return
        if data.startswith("close_topic_"):
            topic_id = int(data.split("_")[2])
            await close_topic_select(update, context, topic_id)
            return
        if data.startswith("archive_topic_"):
            topic_id = int(data.split("_")[2])
            await archive_topic_view(update, context, topic_id)
            return
        if data == "close_all_topics":
            await close_all_topics(update, context)
            return
        if data == "no_topics":
            await query.edit_message_text("📭 Нет тем.")
            return
        if data == "archive_back":
            await show_archive(update, context)
            return
        if data == "back_to_main":
            user = query.from_user
            context.user_data.pop('add_state', None)
            context.user_data.pop('remove_state', None)
            context.user_data.pop('search_state', None)
            context.user_data.pop('close_state', None)
            context.user_data.pop('add_role', None)
            text = f"👋 <b>Главное меню, {sanitize_text(user.full_name)}!</b>\n\nВыберите действие:"
            keyboard = get_main_reply_keyboard(
                is_admin=is_admin(user_id),
                is_creator=is_creator(user_id)
            )
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            return
        if data == "admin_panel":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            text = (
                "⚙️ <b>Админ-панель</b>\n\n"
                "Управление ботом и пользователями.\n"
                f"👤 Ваша роль: "
                f"{'Создатель' if is_creator(user_id) else 'Chief' if is_chief(user_id) else 'Dep.Chief'}"
            )
            keyboard = get_admin_reply_keyboard()
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            return
        if data == "my_requests":
            topics = db.get_user_topics(user_id)
            if not topics:
                keyboard = get_main_reply_keyboard(
                    is_admin=is_admin(user_id),
                    is_creator=is_creator(user_id)
                )
                await query.edit_message_text(
                    "📋 У вас нет запросов.",
                    reply_markup=keyboard
                )
                return
            topics_list = []
            for tid in topics:
                data_topic = db.get_topic(tid)
                if data_topic:
                    topics_list.append((tid, data_topic))
            if not topics_list:
                keyboard = get_main_reply_keyboard(
                    is_admin=is_admin(user_id),
                    is_creator=is_creator(user_id)
                )
                await query.edit_message_text(
                    "📋 У вас нет запросов.",
                    reply_markup=keyboard
                )
                return
            text = "📋 <b>Ваши запросы:</b>"
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_my_requests_inline_keyboard(topics_list)
            )
            return
    except Exception as e:
        logger.error(f"Callback error: {e}")
        try:
            await query.edit_message_text("❌ Ошибка. Попробуйте позже.")
        except:
            pass

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    context.user_data.pop('add_state', None)
    context.user_data.pop('remove_state', None)
    context.user_data.pop('search_state', None)
    context.user_data.pop('close_state', None)
    context.user_data.pop('add_role', None)
    text = f"👋 <b>Главное меню, {sanitize_text(user.full_name)}!</b>\n\nВыберите действие:"
    keyboard = get_main_reply_keyboard(
        is_admin=is_admin(user_id),
        is_creator=is_creator(user_id)
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data.pop('request_state', None)
    context.user_data.pop('request_data', None)
    context.user_data.pop('add_role', None)
    context.user_data.pop('add_state', None)
    context.user_data.pop('remove_state', None)
    context.user_data.pop('search_state', None)
    context.user_data.pop('close_state', None)
    await update.message.reply_text(
        "❌ Операция отменена.",
        reply_markup=get_main_reply_keyboard(
            is_admin=is_admin(user_id),
            is_creator=is_creator(user_id)
        )
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Пожалуйста, попробуйте позже."
            )
        except:
            pass
