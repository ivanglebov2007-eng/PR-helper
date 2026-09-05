from telegram.ext import ConversationHandler

# ============ СОСТОЯНИЯ ДЛЯ СОЗДАНИЯ ЗАПРОСА ============
# Используются в ConversationHandler
(
    SCREENSHOT,      # 0 - ожидание скриншота
    MEDIA_LINK,      # 1 - ожидание ссылки на канал
    CHANNEL_NAME,    # 2 - ожидание названия канала
    SUBSCRIBERS,     # 3 - ожидание количества подписчиков
    CONTACT_LINK,    # 4 - ожидание ссылки для связи
    CONDITIONS       # 5 - ожидание условий
) = range(6)

# ============ СОСТОЯНИЯ ДЛЯ АДМИН-ДЕЙСТВИЙ ============
# Используются в handle_message для ожидания ввода
WAITING_USERNAME = 10   # Ожидание username при добавлении пользователя
WAITING_USER_ID = 11    # Ожидание ID при удалении пользователя
WAITING_KEYWORD = 12    # Ожидание ключевого слова для поиска
WAITING_TOPIC_ID = 13   # Ожидание ID темы для закрытия
