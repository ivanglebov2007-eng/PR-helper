from telegram.ext import ConversationHandler

(
    SCREENSHOT,
    MEDIA_LINK,
    CHANNEL_NAME,
    SUBSCRIBERS,
    CONTACT_LINK,
    CONDITIONS
) = range(6)

WAITING_USERNAME = 10
WAITING_USER_ID = 11
WAITING_KEYWORD = 12
WAITING_TOPIC_ID = 13
