import time
import requests
import datetime
from threading import Thread
from vk_api import VkApi
from flask import Flask, request
from zoneinfo import ZoneInfo   # встроенный модуль для часовых поясов

# ========== Настройки ==========
VK_TOKEN = "vk1.a.reHQ5pJrSXaDax_ynpXzzcLTlfznehHS2E433giDDpjI35-jE8cV2XhquIJw7YOQ9NgS_zBV7eRXNNrHwsF7Zg7b-5AG7vChlfoIHLXJ7fhIxeY9La7f3VN-m2WrmK_SA43yYvGefJVag2AkBHRz9lTgJvChygoSxDxd8IcM1YuBxAy-zakRcZHDMojwM52helu67r2cEu3XFHAMjlJxZQ"
TELEGRAM_BOT_TOKEN = "8018843975:AAFwPpPKDSn__AMlPjl-AAcnOb-cc-hSpFQ"
TELEGRAM_CHAT_ID = "@testprostor"
CHECK_INTERVAL = 10
CONFIRMATION_TOKEN = "a7b2fe10"

CHATS = {
    "Песочница": 9,
    "Мидлы": 10
}
# ================================

vk = VkApi(token=VK_TOKEN)
vk_api = vk.get_api()
previous_members = {}
user_cache = {}
stats = {chat_name: {"messages": {}, "reactions": {}, "totals": {"messages": 0, "reactions": 0}} for chat_name in CHATS}
previous_week_stats = {chat_name: {"messages": 0, "reactions": 0} for chat_name in CHATS}

app = Flask(__name__)

# ================= Функции ===================
def send_telegram(message, retries=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for _ in range(retries):
        try:
            r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
            if r.status_code == 200:
                return True
        except:
            time.sleep(2)
    print("Не удалось отправить сообщение в Telegram")
    return False

def get_chat_members(chat_id):
    try:
        response = vk_api.messages.getConversationMembers(peer_id=2000000000 + chat_id)
        return set(item['member_id'] for item in response['items'])
    except:
        return set()

def get_user_name(user_id):
    if user_id in user_cache:
        return user_cache[user_id]
    try:
        response = vk_api.users.get(user_ids=user_id)
        if response:
            user = response[0]
            name = f"{user.get('first_name')} {user.get('last_name')}"
            user_cache[user_id] = name
            return name
    except:
        pass
    return str(user_id)

def update_stats_message(chat_name, user_id):
    user_str = str(user_id)
    chat_stats = stats[chat_name]
    chat_stats["messages"][user_str] = chat_stats["messages"].get(user_str, 0) + 1
    chat_stats["totals"]["messages"] += 1

def handle_reaction_event(chat_name, message_id, user_id, reaction, event_type):
    chat_stats = stats[chat_name]

    if message_id not in chat_stats["reactions"]:
        chat_stats["reactions"][message_id] = {}

    if reaction not in chat_stats["reactions"][message_id]:
        chat_stats["reactions"][message_id][reaction] = set()

    users_set = chat_stats["reactions"][message_id][reaction]

    if event_type == "reaction_add":
        if user_id not in users_set:
            users_set.add(user_id)
            chat_stats["totals"]["reactions"] += 1
    elif event_type == "reaction_remove":
        if user_id in users_set:
            users_set.remove(user_id)
            chat_stats["totals"]["reactions"] = max(chat_stats["totals"]["reactions"] - 1, 0)

def update_reactions(chat_id, chat_name):
    try:
        history = vk_api.messages.getHistory(peer_id=2000000000 + chat_id, count=100)
        messages = history.get('items', [])

        for message in messages:
            message_id = message['id']
            reactions_response = vk_api.messages.getMessagesReactions(
                peer_id=2000000000 + chat_id,
                message_ids=[message_id],
                extended=1
            )

            items = reactions_response.get('items', [])
            for item in items:
                for reaction in item.get('reactions', []):
                    users = reaction.get('users', [])
                    for user_id in users:
                        handle_reaction_event(chat_name, message_id, user_id, reaction['reaction'], 'reaction_add')

    except Exception as e:
        print(f"Ошибка при обновлении реакций в чате {chat_name}: {e}")

# ================= Формирование отчётов =================
def build_report(reset=True, weekly=False):
    if weekly:
        send_telegram("Генерирую отчёт по неделе...")
        msg = "📊 <b>Статистика за неделю</b>\n\n"
    else:
        msg = "⚡️ <b>Промежуточная статистика</b>\n\n"

    for chat_name in CHATS:
        chat_stats = stats[chat_name]
        total_msgs = chat_stats['totals']['messages']
        total_reacts = chat_stats['totals']['reactions']

        msg += f"📌 <b>{chat_name}</b>\n"
        msg += f"  Всего сообщений: {total_msgs}\n"
        msg += f"  Всего реакций: {total_reacts}\n\n"

        # Топ сообщений
        top_msgs = sorted(chat_stats["messages"].items(), key=lambda x: x[1], reverse=True)[:10]
        if top_msgs:
            msg += "  📝 <b>Топ-10 по сообщениям:</b>\n"
            for uid, count in top_msgs:
                msg += f"    - {get_user_name(uid)} — {count}\n"

        # Топ реакций
        total_reacts_by_user = {}
        for reactions_by_msg in chat_stats["reactions"].values():
            for users_set in reactions_by_msg.values():
                for uid in users_set:
                    total_reacts_by_user[uid] = total_reacts_by_user.get(uid, 0) + 1

        if total_reacts_by_user:
            top_reacts = sorted(total_reacts_by_user.items(), key=lambda x: x[1], reverse=True)[:10]
            msg += "\n  ❤️ <b>Топ-10 по реакциям:</b>\n"
            for uid, count in top_reacts:
                msg += f"    - {get_user_name(uid)} — {count}\n"

        # Сравнение с прошлой неделей
        if weekly:
            prev = previous_week_stats.get(chat_name, {"messages": 0, "reactions": 0})
            delta_msgs = 0.0
            delta_reacts = 0.0
            if prev["messages"] > 0:
                delta_msgs = (total_msgs - prev["messages"]) / prev["messages"] * 100
            if prev["reactions"] > 0:
                delta_reacts = (total_reacts - prev["reactions"]) / prev["reactions"] * 100
            msg += f"\nСообщений больше на {delta_msgs:.1f}%\n"
            msg += f"Реакций больше на {delta_reacts:.1f}%\n"

        msg += "\n" + "―" * 30 + "\n\n"

    send_telegram(msg)

    if weekly:
        for chat_name in CHATS:
            previous_week_stats[chat_name] = {
                "messages": stats[chat_name]["totals"]["messages"],
                "reactions": stats[chat_name]["totals"]["reactions"]
            }

    if reset:
        for chat_name in CHATS:
            stats[chat_name] = {"messages": {}, "reactions": {}, "totals": {"messages": 0, "reactions": 0}}

def make_weekly_report():
    build_report(reset=True, weekly=True)

def make_interim_report():
    build_report(reset=False, weekly=False)

# ================= Основной цикл VK =================
def bot_loop():
    for chat_name, chat_id in CHATS.items():
        previous_members[chat_name] = get_chat_members(chat_id)
    print("Бот запущен. Отслеживание VK активно.")

    while True:
        try:
            for chat_name, chat_id in CHATS.items():
                current_members = get_chat_members(chat_id)

                new_members = current_members - previous_members[chat_name]
                for member in new_members:
                    name = get_user_name(member)
                    vk_link = f"https://vk.com/id{member}"
                    send_telegram(f"➕ {name} ({vk_link}) присоединился к '{chat_name}'.")

                left_members = previous_members[chat_name] - current_members
                for member in left_members:
                    name = get_user_name(member)
                    vk_link = f"https://vk.com/id{member}"
                    send_telegram(f"➖ {name} ({vk_link}) покинул '{chat_name}'.")

                previous_members[chat_name] = current_members
                update_reactions(chat_id, chat_name)

            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("Ошибка VK loop:", e)
            time.sleep(CHECK_INTERVAL)

# ================= Telegram long polling =================
def telegram_polling():
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": 30, "offset": offset + 1}
            resp = requests.get(url, params=params, timeout=35)
            updates = resp.json().get("result", [])

            for update in updates:
                offset = max(offset, update["update_id"])
                message = update.get("message")
                if message:
                    text = message.get("text", "")
                    if text == "/report":
                        send_telegram("Генерирую промежуточный отчёт...")
                        Thread(target=make_interim_report).start()
        except Exception as e:
            print("Ошибка Telegram polling:", e)
            time.sleep(5)

# ================= Flask Callback API =================
@app.route("/", methods=["POST"])
def callback():
    data = request.get_json()

    if data.get("type") == "confirmation":
        return CONFIRMATION_TOKEN

    elif data.get("type") == "message_new":
        obj = data["object"]
        peer_id = obj["peer_id"]
        chat_id = peer_id - 2000000000
        for chat_name, cid in CHATS.items():
            if cid == chat_id:
                update_stats_message(chat_name, obj.get("from_id"))
        return "ok"

    elif data.get("type") == "message_reaction_event":
        obj = data["object"]
        peer_id = obj.get("peer_id")
        if peer_id is None:
            return "ok"
        chat_id = peer_id - 2000000000
        message_id = obj.get("message_id")
        user_id = obj.get("reacted_id")
        reaction = str(obj.get("reaction_id"))
        
        event_type = obj.get("event_type")  # 'reaction_add' или 'reaction_remove'
        if event_type not in ["reaction_add", "reaction_remove"]:
            return "ok"
        
        for chat_name, cid in CHATS.items():
            if cid == chat_id and user_id is not None:
                handle_reaction_event(chat_name, message_id, user_id, reaction, event_type)
        return "ok"

    return "ok"

# ================= Планировщик отчётов =================
def report_scheduler():
    tz = ZoneInfo("Europe/Moscow")
    while True:
        try:
            now = datetime.datetime.now(tz)
            if now.weekday() == 4 and now.hour == 23 and now.minute == 55:
                print("Время еженедельного отчёта! Генерирую...")
                Thread(target=make_weekly_report).start()
                time.sleep(60)
            else:
                time.sleep(20)
        except Exception as e:
            print("Ошибка в планировщике отчётов:", e)
            time.sleep(60)

# ================= Запуск =================
Thread(target=bot_loop, daemon=True).start()
Thread(target=telegram_polling, daemon=True).start()
Thread(target=report_scheduler, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)


