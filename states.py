from telegram.ext import ConversationHandler

# Состояния для создания запроса
(
    SCREENSHOT,      # 0
    MEDIA_LINK,      # 1
    CHANNEL_NAME,    # 2
    SUBSCRIBERS,     # 3
    CONTACT_LINK,    # 4
    CONDITIONS       # 5
) = range(6)

# Состояния для поиска
SEARCH_KEYWORD = 10

# Состояния для управления пользователями
ADD_PR_USERNAME = 20
ADD_PR_ID = 21