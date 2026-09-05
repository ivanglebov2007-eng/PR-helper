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

# ============ СОЗДАНИЕ ЗАПРОСА ============

async def new_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_pr_manager(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return ConversationHandler.END

    db.set_pending_request(user_id, {})
    await update.message.reply_text(
        "📝 <b>Шаг 1/6: отправьте СКРИНШОТ переписки</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    return SCREENSHOT

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo = update.message.photo

    if not photo:
        await update.message.reply_text(
            "❌ Отправьте фото.",
            reply_markup=get_cancel_keyboard()
        )
        return SCREENSHOT

    try:
        file = await photo[-1].get_file()
        file_url = file.file_path

        pending = db.get_pending_request(user_id) or {}
        pending['screenshot'] = file_url
        db.set_pending_request(user_id, pending)

        await update.message.reply_text(
            "✅ Скриншот получен!\n\n"
            "📎 <b>Шаг 2/6: ссылка на канал</b> (YouTube, Twitch, TikTok)",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return MEDIA_LINK

    except Exception as e:
        logger.error(f"Ошибка скриншота: {e}")
        await update.message.reply_text("❌ Ошибка, попробуйте ещё раз.")
        return SCREENSHOT

async def handle_media_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not validate_media_link(text):
        await update.message.reply_text(
            "❌ Некорректная ссылка.\nНужно http:// и YouTube/Twitch/TikTok",
            reply_markup=get_cancel_keyboard()
        )
        return MEDIA_LINK

    pending = db.get_pending_request(user_id) or {}
    pending['media_link'] = text
    db.set_pending_request(user_id, pending)

    await update.message.reply_text(
        "✅ Ссылка принята.\n\n"
        "📌 <b>Шаг 3/6: название канала</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    return CHANNEL_NAME

async def handle_channel_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text("❌ Название не может быть пустым.", reply_markup=get_cancel_keyboard())
        return CHANNEL_NAME

    pending = db.get_pending_request(user_id) or {}
    pending['channel_name'] = sanitize_text(text)
    db.set_pending_request(user_id, pending)

    await update.message.reply_text(
        "✅ Название сохранено.\n\n"
        "👥 <b>Шаг 4/6: количество подписчиков</b> (только цифры)",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    return SUBSCRIBERS

async def handle_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    try:
        subs = int(text.replace(' ', '').replace(',', ''))
        formatted = f"{subs:,}".replace(',', ' ')
    except ValueError:
        await update.message.reply_text(
            "❌ Введите число.",
            reply_markup=get_cancel_keyboard()
        )
        return SUBSCRIBERS

    pending = db.get_pending_request(user_id) or {}
    pending['subscribers'] = formatted
    db.set_pending_request(user_id, pending)

    await update.message.reply_text(
        f"✅ Подписчиков: {formatted}\n\n"
        "📞 <b>Шаг 5/6: ссылка для связи</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    return CONTACT_LINK

async def handle_contact_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text("❌ Введите ссылку.", reply_markup=get_cancel_keyboard())
        return CONTACT_LINK

    if not text.startswith(('http://', 'https://')):
        text = 'https://' + text

    pending = db.get_pending_request(user_id) or {}
    pending['contact_link'] = text
    db.set_pending_request(user_id, pending)

    await update.message.reply_text(
        "✅ Ссылка сохранена.\n\n"
        "📝 <b>Шаг 6/6: условия</b> (или /skip)",
        parse_mode=ParseMode.HTML,
        reply_markup=get_skip_keyboard()
    )
    return CONDITIONS

async def handle_conditions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    pending = db.get_pending_request(user_id) or {}
    pending['conditions'] = sanitize_text(text) if text else "Не указаны"
    db.set_pending_request(user_id, pending)

    return await finish_request(update, context)

async def skip_conditions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pending = db.get_pending_request(user_id) or {}
    pending['conditions'] = "Не указаны"
    db.set_pending_request(user_id, pending)

    await update.message.reply_text("⏭️ Условия пропущены.")
    return await finish_request(update, context)

async def finish_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    pending = db.get_pending_request(user_id) or {}

    missing = [f for f in REQUIRED_FIELDS if f not in pending]
    if missing:
        await update.message.reply_text(
            f"❌ Не хватает: {', '.join(missing)}.\nНачните заново /new_request"
        )
        db.clear_pending_request(user_id)
        return ConversationHandler.END

    topic_id = await create_request_topic(update, context, pending)

    if topic_id:
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
            f"✅ <b>Запрос создан!</b>\n🆔 ID темы: <code>{topic_id}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("❌ Не удалось создать запрос.")

    db.clear_pending_request(user_id)
    return ConversationHandler.END

async def create_request_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, request_data: dict) -> Optional[int]:
    user = update.effective_user
    topic_title = f"Запрос от {user.full_name} — {request_data['channel_name']}"

    try:
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=topic_title[:255]
        )
        topic_id = topic.message_thread_id

        text = (
            f"📢 <b>НОВЫЙ ЗАПРОС</b>\n\n"
            f"👤 {sanitize_text(user.full_name)} (@{user.username or 'нет'})\n"
            f"📅 {format_date(datetime.now().isoformat())}\n\n"
            f"📌 {sanitize_text(request_data['channel_name'])}\n"
            f"👥 {request_data['subscribers']}\n"
            f"🔗 <a href='{request_data['media_link']}'>Ссылка</a>\n"
            f"📎 <a href='{request_data['screenshot']}'>Скриншот</a>\n"
            f"📞 <a href='{request_data['contact_link']}'>Связь</a>\n"
            f"📝 {sanitize_text(request_data['conditions'])}"
        )

        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

        mentions = [f"<a href='tg://user?id={CHIEF_ID}'>Chief</a>"]
        for dep_id in db.dep_chiefs:
            mentions.append(f"<a href='tg://user?id={dep_id}'>Dep.Chief</a>")

        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=f"🔔 Новый запрос!\n{', '.join(mentions)}",
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
            text += f"• <b>{sanitize_text(data.channel_name)}</b>\n  ID: <code>{tid}</code> | {status}\n\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def close_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ /close_topic <id>")
        return

    try:
        topic_id = int(args[0])
        if topic_id not in db.topics:
            await update.message.reply_text("❌ Тема не найдена.")
            return
        if not db.topics[topic_id].is_active:
            await update.message.reply_text("❌ Уже закрыта.")
            return

        db.close_topic(topic_id, user_id)
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text="🔒 Тема закрыта."
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
        await update.message.reply_text("❌ /search <слово>")
        return

    keyword = ' '.join(args).lower()
    results = db.search_topics(keyword)

    if not results:
        await update.message.reply_text(f"❌ Ничего не найдено по '{keyword}'.")
        return

    text = f"🔍 <b>Результаты по '{keyword}':</b>\n\n"
    for tid, data in results:
        text += f"• ID: <code>{tid}</code> | {sanitize_text(data.channel_name)}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def add_pr_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Только Chief.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /add_pr_by_id @username id")
        return

    try:
        username = args[0].replace('@', '')
        new_id = int(args[1])
        db.add_pr_manager(new_id)
        await update.message.reply_text(f"✅ @{username} (ID: {new_id}) добавлен.")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

async def add_dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Только Chief.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /add_dep @username id")
        return

    try:
        username = args[0].replace('@', '')
        new_id = int(args[1])
        db.add_dep_chief(new_id)
        await update.message.reply_text(f"✅ @{username} (ID: {new_id}) добавлен как Dep.Chief.")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_chief(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /remove_user @username id")
        return

    try:
        username = args[0].replace('@', '')
        remove_id = int(args[1])
        if remove_id == CHIEF_ID:
            await update.message.reply_text("❌ Нельзя удалить Chief.")
            return

        removed = db.remove_pr_manager(remove_id) or db.remove_dep_chief(remove_id)
        await update.message.reply_text(f"✅ @{username} удалён." if removed else "❌ Не найден.")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

# ============ СПИСОК ПОЛЬЗОВАТЕЛЕЙ С ССЫЛКАМИ ============

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and not is_creator(user_id):
        await update.message.reply_text("❌ Нет прав.")
        return

    text = "👥 <b>Список пользователей</b>\n\n"

    if db.pr_managers:
        text += "👤 <b>PR Managers</b>\n"
        for uid in db.pr_managers:
            text += f"• <a href='tg://user?id={uid}'>{uid}</a>\n"
        text += "\n"

    if db.dep_chiefs:
        text += "👤 <b>Dep.Chief</b>\n"
        for uid in db.dep_chiefs:
            text += f"• <a href='tg://user?id={uid}'>{uid}</a>\n"
        text += "\n"

    text += f"👑 <b>Chief</b>\n• <a href='tg://user?id={CHIEF_ID}'>{CHIEF_ID}</a>\n"
    text += f"\n👑 <b>Creator</b>\n• <a href='tg://user?id={CREATOR_ID}'>{CREATOR_ID}</a>"

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
            db.set_pending_request(user_id, {})
            await query.edit_message_text(
                "📝 <b>Шаг 1/6: отправьте СКРИНШОТ</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_cancel_keyboard()
            )
            context.user_data['state'] = SCREENSHOT

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
            await query.edit_message_text("🔍 /search <слово>")

        elif data == "manage_users":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await query.edit_message_text(
                "👥 <b>Управление</b>\n\n"
                "/add_pr_by_id @username id\n"
                "/add_dep @username id\n"
                "/remove_user @username id\n"
                "/list_users",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_keyboard()
            )

        elif data == "list_users":
            text = "👥 <b>Список пользователей</b>\n\n"
            if db.pr_managers:
                text += "👤 <b>PR Managers</b>\n"
                for uid in db.pr_managers:
                    text += f"• <a href='tg://user?id={uid}'>{uid}</a>\n"
                text += "\n"
            if db.dep_chiefs:
                text += "👤 <b>Dep.Chief</b>\n"
                for uid in db.dep_chiefs:
                    text += f"• <a href='tg://user?id={uid}'>{uid}</a>\n"
                text += "\n"
            text += f"👑 <b>Chief</b>\n• <a href='tg://user?id={CHIEF_ID}'>{CHIEF_ID}</a>\n"
            text += f"\n👑 <b>Creator</b>\n• <a href='tg://user?id={CREATOR_ID}'>{CREATOR_ID}</a>"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)

        elif data == "close_topic":
            if not is_admin(user_id) and not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await query.edit_message_text("🔒 /close_topic <id>")

        elif data == "add_pr":
            await query.edit_message_text("➕ /add_pr_by_id @username id")

        elif data == "add_dep":
            await query.edit_message_text("👤 /add_dep @username id")

        elif data == "remove_user":
            await query.edit_message_text("➖ /remove_user @username id")

        elif data == "back_to_main":
            keyboard = get_main_keyboard(
                is_admin=is_admin(user_id),
                is_creator=is_creator(user_id)
            )
            await query.edit_message_text(
                "👋 Главное меню",
                reply_markup=keyboard
            )

        elif data == "settings":
            if not is_creator(user_id):
                await query.edit_message_text("❌ Нет прав.")
                return
            await query.edit_message_text(
                f"⚙️ <b>Настройки</b>\n\n"
                f"PR: {len(db.pr_managers)}\n"
                f"Dep.Chief: {len(db.dep_chiefs)}\n"
                f"Тем: {len(db.topics)}",
                parse_mode=ParseMode.HTML
            )

        elif data == "skip":
            pending = db.get_pending_request(user_id) or {}
            pending['conditions'] = "Не указаны"
            db.set_pending_request(user_id, pending)
            await query.edit_message_text("⏭️ Пропущено")
            class Fake:
                pass
            fake_update = Fake()
            fake_update.effective_user = query.from_user
            fake_update.effective_chat = query.message.chat
            fake_update.message = Fake()
            fake_update.message.reply_text = lambda *a, **k: None
            await finish_request(fake_update, context)

        elif data == "cancel":
            db.clear_pending_request(user_id)
            await query.edit_message_text("❌ Отменено")
            keyboard = get_main_keyboard(
                is_admin=is_admin(user_id),
                is_creator=is_creator(user_id)
            )
            await context.bot.send_message(
                chat_id=user_id,
                text="👋 Главное меню",
                reply_markup=keyboard
            )

        else:
            await query.edit_message_text("❌ Неизвестно")

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
            await update.effective_message.reply_text("❌ Ошибка. Попробуйте позже.")
        except:
            pass

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.clear_pending_request(user_id)
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END
