import time
import requests
import datetime
import json
from threading import Thread
from vk_api import VkApi
from flask import Flask, request

# ========== Настройки ==========
VK_TOKEN = "vk1.a.reHQ5pJrSXaDax_ynpXzzcLTlfznehHS2E433giDDpjI35-jE8cV2XhquIJw7YOQ9NgS_zBV7eRXNNrHwsF7Zg7b-5AG7vChlfoIHLXJ7fhIxeY9La7f3VN-m2WrmK_SA43yYvGefJVag2AkBHRz9lTgJvChygoSxDxd8IcM1YuBxAy-zakRcZHDMojwM52helu67r2cEu3XFHAMjlJxZQ"
TELEGRAM_BOT_TOKEN = "8018843975:AAFwPpPKDSn__AMlPjl-AAcnOb-cc-hSpFQ"
TELEGRAM_CHAT_ID = "@info_chat_prostor"
CHECK_INTERVAL = 10  # секунд между проверками
CONFIRMATION_TOKEN = "db79a8bd"

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

app = Flask(__name__)
last_report_time = None

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
        return {chat_name: {"messages": {}, "reactions": {}, "totals": {"messages": 0, "reactions": 0}} for chat_name in CHATS}

def save_stats(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================= Сбор статистики сообщений ============
def update_stats_messages(chat_id, chat_name):
    stats = load_stats()
    try:
        offset = 0
        while True:
            history = vk_api.messages.getHistory(peer_id=2000000000 + chat_id, count=200, offset=offset)
            messages = history.get("items", []) if isinstance(history, dict) else []

            if not messages:
                break

            for msg in messages:
                date = datetime.datetime.fromtimestamp(msg["date"])
                if (datetime.datetime.now() - date).days > 7:
                    return

                uid = msg.get("from_id")
                if uid:
                    user_str = str(uid)
                    chat_stats = stats.get(chat_name, {"messages": {}, "reactions": {}, "totals": {"messages": 0, "reactions": 0}})
                    chat_stats["messages"][user_str] = chat_stats["messages"].get(user_str, 0) + 1
                    chat_stats["totals"]["messages"] += 1
                    stats[chat_name] = chat_stats
            offset += 200
    except Exception as e:
        print("Ошибка при получении истории:", e)
    finally:
        save_stats(stats)

# ================= Обработка реакций через callback ============
def handle_reaction_event(chat_name, user_id, reaction, event_type):
    stats = load_stats()
    chat_stats = stats.get(chat_name, {"messages": {}, "reactions": {}, "totals": {"messages": 0, "reactions": 0}})
    user_str = str(user_id)
    if user_str not in chat_stats["reactions"]:
        chat_stats["reactions"][user_str] = {}

    if event_type == "reaction_add":
        chat_stats["reactions"][user_str][reaction] = chat_stats["reactions"][user_str].get(reaction, 0) + 1
        chat_stats["totals"]["reactions"] += 1
    elif event_type == "reaction_remove":
        chat_stats["reactions"][user_str][reaction] = max(chat_stats["reactions"][user_str].get(reaction, 1) - 1, 0)
        chat_stats["totals"]["reactions"] = max(chat_stats["totals"]["reactions"] - 1, 0)

    stats[chat_name] = chat_stats
    save_stats(stats)

# ================= Формирование отчёта ============
def make_weekly_report(reset=True):
    stats = load_stats()
    try:
        with open(PREV_FILE, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except:
        prev = {chat_name: {"totals": {"messages": 0, "reactions": 0}} for chat_name in CHATS}

    msg = "<b>📊 Статистика за неделю</b>\n\n"

    for chat_name in CHATS:
        chat_stats = stats.get(chat_name, {"messages": {}, "reactions": {}, "totals": {"messages": 0, "reactions": 0}})
        msg += f"<b>{chat_name}</b>\n"
        msg += f"Всего сообщений: {chat_stats['totals']['messages']}\n"
        msg += f"Всего реакций: {chat_stats['totals']['reactions']}\n"

        top_msgs = sorted(chat_stats["messages"].items(), key=lambda x: x[1], reverse=True)[:10]
        msg += "<b>Топ-10 по сообщениям:</b>\n"
        for uid, count in top_msgs:
            msg += f"- {get_user_name(uid)} — {count}\n"

        # топ по реакциям без типов
        total_reacts_by_user = {uid: sum(emoji_counts.values()) for uid, emoji_counts in chat_stats["reactions"].items()}
        top_reacts = sorted(total_reacts_by_user.items(), key=lambda x: x[1], reverse=True)[:10]
        msg += "<b>Топ-10 по реакциям:</b>\n"
        for uid, count in top_reacts:
            msg += f"- {get_user_name(uid)} — {count}\n"

        prev_msgs = prev.get(chat_name, {}).get("totals", {}).get("messages", 0)
        prev_reacts = prev.get(chat_name, {}).get("totals", {}).get("reactions", 0)
        delta_msgs = ((chat_stats["totals"]["messages"] - prev_msgs) / prev_msgs * 100) if prev_msgs > 0 else 0
        delta_reacts = ((chat_stats["totals"]["reactions"] - prev_reacts) / prev_reacts * 100) if prev_reacts > 0 else 0
        msg += f"Сообщений больше на {delta_msgs:.1f}%\n"
        msg += f"Реакций больше на {delta_reacts:.1f}%\n\n"

    try:
        send_telegram(msg)
        print("Отчёт отправлен")
        if reset:
            with open(PREV_FILE, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            save_stats({chat_name: {"messages": {}, "reactions": {}, "totals": {"messages": 0, "reactions": 0}} for chat_name in CHATS})
    except Exception as e:
        print("Ошибка при отправке отчёта:", e)

# ================= Основной цикл =================
def bot_loop():
    global last_report_time
    for chat_name, chat_id in CHATS.items():
        previous_members[chat_name] = get_chat_members(chat_id)
    print("Бот запущен.")

    # ближайшая пятница 18:00
    now = datetime.datetime.now()
    days_ahead = 4 - now.weekday()  # пятница=4
    if days_ahead < 0:
        days_ahead += 7
    first_report_time = now.replace(hour=18, minute=0, second=0, microsecond=0) + datetime.timedelta(days=days_ahead)
    last_report_time = None

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

                update_stats_messages(chat_id, chat_name)

            now = datetime.datetime.now()
            if now >= first_report_time and (last_report_time is None or (now - last_report_time).total_seconds() > 3600):
                make_weekly_report()
                last_report_time = now
                first_report_time += datetime.timedelta(weeks=1)

            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("Ошибка:", e)
            time.sleep(CHECK_INTERVAL)

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
                update_stats_messages(chat_id, chat_name)
        return "ok"

    elif data.get("type") == "message_reaction_event":
        obj = data["object"]
        peer_id = obj.get("peer_id")
        if peer_id is None:
            return "ok"
        chat_id = peer_id - 2000000000
        user_id = obj.get("reacted_id")
        reaction = str(obj.get("reaction_id"))
        event_type = "reaction_add"  # VK callback для добавления/удаления реакции
        for chat_name, cid in CHATS.items():
            if cid == chat_id and user_id is not None:
                handle_reaction_event(chat_name, user_id, reaction, event_type)
        return "ok"

    return "ok"

# ================= Запуск =================
Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
