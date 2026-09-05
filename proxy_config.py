# proxy_config.py
# Настройки прокси для обхода блокировок

# SOCKS5 прокси (например, через Tor или VPN)
PROXY_CONFIG = {
    'proxy_url': 'socks5://127.0.0.1:1080',  # Замените на ваш прокси
    'urllib3_proxy_kwargs': {
        'username': '',  # Если нужен логин
        'password': '',  # Если нужен пароль
    }
}

# Или HTTP прокси
# PROXY_CONFIG = {
#     'proxy_url': 'http://127.0.0.1:8080',
# }