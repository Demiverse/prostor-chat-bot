import time
import requests
from vk_api import VkApi
from threading import Thread
from flask import Flask

# ========== Настройки ==========
VK_TOKEN = "vk1.a.reHQ5pJrSXaDax_ynpXzzcLTlfznehHS2E433giDDpjI35-jE8cV2XhquIJw7YOQ9NgS_zBV7eRXNNrHwsF7Zg7b-5AG7vChlfoIHLXJ7fhIxeY9La7f3VN-m2WrmK_SA43yYvGefJVag2AkBHRz9lTgJvChygoSxDxd8IcM1YuBxAy-zakRcZHDMojwM52helu67r2cEu3XFHAMjlJxZQ"
TELEGRAM_BOT_TOKEN = "8018843975:AAFwPpPKDSn__AMlPjl-AAcnOb-cc-hSpFQ"
TELEGRAM_CHAT_ID = "@info_chat_prostor"
CHECK_INTERVAL = 10  # секунд между проверками

CHATS = {
    "Песочница": 9,  # ID чата
    "Мидлы": 10       # ID второго чата
}
# ================================

vk = VkApi(token=VK_TOKEN)
vk_api = vk.get_api()
previous_members = {}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

def get_chat_members(chat_id):
    response = vk_api.messages.getConversationMembers(peer_id=2000000000 + chat_id)
    return set(item['member_id'] for item in response['items'])

def get_user_name(user_id):
    response = vk_api.users.get(user_ids=user_id)
    if response:
        user = response[0]
        return f"{user.get('first_name')} {user.get('last_name')}"
    return str(user_id)

def bot_loop():
    # Инициализация без уведомлений
    for chat_name, chat_id in CHATS.items():
        previous_members[chat_name] = get_chat_members(chat_id)
    print("Бот запущен. Теперь уведомления только для новых входов/выходов.")

    while True:
        try:
            for chat_name, chat_id in CHATS.items():
                current_members = get_chat_members(chat_id)

                # Новые участники
                new_members = current_members - previous_members[chat_name]
                for member in new_members:
                    name = get_user_name(member)
                    vk_link = f"https://vk.com/id{member}"
                    send_telegram(f"Пользователь {name} ({vk_link}) присоединился к чату '{chat_name}'.")

                # Покинувшие участники
                left_members = previous_members[chat_name] - current_members
                for member in left_members:
                    name = get_user_name(member)
                    vk_link = f"https://vk.com/id{member}"
                    send_telegram(f"Пользователь {name} ({vk_link}) покинул чат '{chat_name}'.")

                previous_members[chat_name] = current_members

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("Ошибка:", e)
            time.sleep(CHECK_INTERVAL)

# ========== Flask для Replit/Uptime Robot ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот VK работает!"

# Запускаем бот в отдельном потоке, чтобы Flask тоже работал
Thread(target=bot_loop).start()

# Запуск веб-сервера Replit
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
