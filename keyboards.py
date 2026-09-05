from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_keyboard(is_admin: bool = False, is_creator: bool = False):
    """Главное меню"""
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
        keyboard.append(
            [InlineKeyboardButton("⚙️ Настройки бота", callback_data="settings")]
        )
    
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard():
    """Клавиатура для отмены"""
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_skip_keyboard():
    """Клавиатура для пропуска условий"""
    keyboard = [
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    """Административное меню"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить PR", callback_data="add_pr")],
        [InlineKeyboardButton("👤 Добавить Dep.Chief", callback_data="add_dep")],
        [InlineKeyboardButton("➖ Удалить пользователя", callback_data="remove_user")],
        [InlineKeyboardButton("📋 Список пользователей", callback_data="list_users")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)