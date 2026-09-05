from telegram.ext import ConversationHandler

# ============ СОСТОЯНИЯ ДЛЯ СОЗДАНИЯ ЗАПРОСА ============
(
    SCREENSHOT,      # 0
    MEDIA_LINK,      # 1
    CHANNEL_NAME,    # 2
    SUBSCRIBERS,     # 3
    CONTACT_LINK,    # 4
    CONDITIONS       # 5
) = range(6)

# ============ СОСТОЯНИЯ ДЛЯ АДМИН-ДЕЙСТВИЙ ============
WAITING_USERNAME = 10
WAITING_USER_ID = 11
WAITING_KEYWORD = 12
WAITING_TOPIC_ID = 13
