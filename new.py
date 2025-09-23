import time
import requests
import datetime
import json
from threading import Thread
from vk_api import VkApi
from flask import Flask

# ========== Настройки ==========
VK_TOKEN = "vk1.a.reHQ5pJrSXaDax_ynpXzzcLTlfznehHS2E433giDDpjI35-jE8cV2XhquIJw7YOQ9NgS_zBV7eRXNNrHwsF7Zg7b-5AG7vChlfoIHLXJ7fhIxeY9La7f3VN-m2WrmK_SA43yYvGefJVag2AkBHRz9lTgJvChygoSxDxd8IcM1YuBxAy-zakRcZHDMojwM52helu67r2cEu3XFHAMjlJxZQ"
TELEGRAM_BOT_TOKEN = "8018843975:AAFwPpPKDSn__AMlPjl-AAcnOb-cc-hSpFQ"
TELEGRAM_CHAT_ID = "@info_chat_prostor"
CHECK_INTERVAL = 10  # секунд между проверками

CHATS = {
    "Песочница": 9,
    "Мидлы": 10
}

STATS_FILE = "weekly_stats.json"
PREV_FILE = "previous_week.json"
# ================================

vk = VkApi(token=VK_TOKEN)
vk_api = vk.get_api()
previous_members = {}

# ================= Функции ===================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})


def get_chat_members(chat_id):
    response = vk_api.messages.getConversationMembers(peer_id=2000000000 + chat_id)
    return set(item['member_id'] for item in response['items'])


def get_user_name(user_id):
    try:
        response = vk_api.users.get(user_ids=user_id)
        if response:
            user = response[0]
            return f"{user.get('first_name')} {user.get('last_name')}"
    except:
        pass
    return str(user_id)


def load_stats():
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        # Инициализация структуры для каждого чата
        return {chat_name: {"messages": {}, "totals": {"messages": 0}} for chat_name in CHATS}


def save_stats(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ================= Сбор статистики ============
def update_stats(chat_id, chat_name):
    stats = load_stats()
    try:
        offset = 0
        while True:
            history = vk_api.messages.getHistory(peer_id=2000000000 + chat_id, count=200, offset=offset)

            # безопасно получаем список сообщений
            if isinstance(history, dict):
                messages = history.get("items", [])
            elif isinstance(history, list):
                messages = history
            else:
                messages = []

            if not messages:
                break

            for msg in messages:
                date = datetime.datetime.fromtimestamp(msg["date"])
                if (datetime.datetime.now() - date).days > 7:
                    return

                uid = msg.get("from_id")
                if uid:
                    user_str = str(uid)
                    chat_stats = stats.get(chat_name, {"messages": {}, "totals": {"messages": 0}})
                    chat_stats["messages"][user_str] = chat_stats["messages"].get(user_str, 0) + 1
                    chat_stats["totals"]["messages"] += 1
                    stats[chat_name] = chat_stats
            offset += 200
    except Exception as e:
        print("Ошибка при получении истории:", e)
    finally:
        save_stats(stats)


# ================= Формирование отчета =========
def make_weekly_report(reset=True):
    stats = load_stats()
    try:
        with open(PREV_FILE, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except:
        prev = {chat_name: {"totals": {"messages": 0}} for chat_name in CHATS}

    msg = "<b>📊 Статистика сообщений за последнюю неделю</b>\n\n"

    for chat_name in CHATS:
        chat_stats = stats.get(chat_name, {"messages": {}, "totals": {"messages": 0}})
        msg += f"<b>{chat_name}</b>\n"
        msg += f"Всего сообщений: {chat_stats['totals']['messages']}\n"

        # топ по сообщениям
        top_msgs = sorted(chat_stats["messages"].items(), key=lambda x: x[1], reverse=True)[:10]
        msg += "<b>Топ-10 по сообщениям:</b>\n"
        for uid, count in top_msgs:
            msg += f"- {get_user_name(uid)} — {count}\n"

        # сравнение с прошлым
        prev_msgs = prev.get(chat_name, {}).get("totals", {}).get("messages", 0)
        delta_msgs = ((chat_stats["totals"]["messages"] - prev_msgs) / prev_msgs * 100) if prev_msgs > 0 else 0
        msg += f"Сообщений больше на {delta_msgs:.1f}%\n\n"

    try:
        send_telegram(msg)
        print("Отчёт отправлен")
        if reset:
            with open(PREV_FILE, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            # обнуляем статистику для новой недели
            save_stats({chat_name: {"messages": {}, "totals": {"messages": 0}} for chat_name in CHATS})
    except Exception as e:
        print("Ошибка при отправке отчёта:", e)


# ================= Основной цикл =================
def bot_loop():
    for chat_name, chat_id in CHATS.items():
        previous_members[chat_name] = get_chat_members(chat_id)
    print("Бот запущен.")

    while True:
        try:
            for chat_name, chat_id in CHATS.items():
                current_members = get_chat_members(chat_id)

                # Новые участники
                new_members = current_members - previous_members[chat_name]
                for member in new_members:
                    name = get_user_name(member)
                    vk_link = f"https://vk.com/id{member}"
                    send_telegram(f"➕ {name} ({vk_link}) присоединился к '{chat_name}'.")

                # Покинувшие
                left_members = previous_members[chat_name] - current_members
                for member in left_members:
                    name = get_user_name(member)
                    vk_link = f"https://vk.com/id{member}"
                    send_telegram(f"➖ {name} ({vk_link}) покинул '{chat_name}'.")

                previous_members[chat_name] = current_members

                # обновляем статистику сообщений
                update_stats(chat_id, chat_name)

            # автоотчёт раз в неделю — пятница 18:00
            now = datetime.datetime.now()
            if now.weekday() == 4 and now.hour == 18 and now.minute < CHECK_INTERVAL:
                make_weekly_report()
                time.sleep(60)  # чтобы не дублировалось в течение минуты

            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("Ошибка:", e)
            time.sleep(CHECK_INTERVAL)


# ================= Flask для Replit/Uptime Robot ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот VK работает!"


# ================= Запуск =================
Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
