import time
import requests
import datetime
from threading import Thread
from vk_api import VkApi
from flask import Flask, request
from zoneinfo import ZoneInfo

# ========== Настройки ==========
VK_TOKEN = "vk1.a.reHQ5pJrSXaDax_ynpXzzcLTlfznehHS2E433giDDpjI35-jE8cV2XhquIJw7YOQ9NgS_zBV7eRXNNrHwsF7Zg7b-5AG7vChlfoIHLXJ7fhIxeY9La7f3VN-m2WrmK_SA43yYvGefJVag2AkBHRz9lTgJvChygoSxDxd8IcM1YuBxAy-zakRcZHDMojwM52helu67r2cEu3XFHAMjlJxZQ"
TELEGRAM_BOT_TOKEN = "8018843975:AAFwPpPKDSn__AMlPjl-AAcnOb-cc-hSpFQ"
TELEGRAM_CHAT_ID = "@info_chat_prostor"
CONFIRMATION_TOKEN = "a0516acf"

CHATS = {"Песочница": 9, "Мидлы": 10}

CHECK_INTERVAL = 15  # интервал проверки в секундах
previous_members = {}  # хранение предыдущих участников чатов

# ================================

vk = VkApi(token=VK_TOKEN)
vk_api = vk.get_api()
user_cache = {}
stats = {
    chat_name: {
        "messages": {},
        "messages_by_id": {},
        "reactions": {},
        "totals": {"messages": 0, "reactions": 0}
    }
    for chat_name in CHATS
}
previous_week_stats = {chat_name: {"messages": 0, "reactions": 0} for chat_name in CHATS}

app = Flask(__name__)

# ================= Функции ===================
def send_telegram(message, retries=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for _ in range(retries):
        try:
            r = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
                timeout=10
            )
            if r.status_code == 200:
                return True
        except:
            time.sleep(2)
    print("Не удалось отправить сообщение в Telegram")
    return False


def get_user_name(user_id):
    user_id_int = int(user_id) if isinstance(user_id, str) else user_id
    if user_id_int in user_cache:
        return user_cache[user_id_int]
    try:
        response = vk_api.users.get(user_ids=user_id_int)
        if response:
            user = response[0]
            name = f"{user.get('first_name')} {user.get('last_name')}"
            user_cache[user_id_int] = name
            return name
    except Exception as e:
        print(f"Ошибка получения имени пользователя {user_id}: {e}")
    return str(user_id)


def update_stats_message(chat_name, user_id, message_id):
    uid = int(user_id)
    chat_stats = stats[chat_name]
    chat_stats["messages"][uid] = chat_stats["messages"].get(uid, 0) + 1
    chat_stats["totals"]["messages"] += 1
    chat_stats["messages_by_id"][message_id] = uid


def handle_reaction_event(chat_name, message_id, user_id, reaction_id=None):
    user_id_int = int(user_id)
    chat_stats = stats[chat_name]

    if message_id not in chat_stats["reactions"]:
        chat_stats["reactions"][message_id] = {}

    if reaction_id is not None:
        reaction = str(reaction_id)
        if reaction not in chat_stats["reactions"][message_id]:
            chat_stats["reactions"][message_id][reaction] = set()
        users_set = chat_stats["reactions"][message_id][reaction]
        if user_id_int not in users_set:
            users_set.add(user_id_int)
            chat_stats["totals"]["reactions"] += 1
    else:
        for reaction, users_set in chat_stats["reactions"][message_id].items():
            if user_id_int in users_set:
                users_set.remove(user_id_int)
                chat_stats["totals"]["reactions"] = max(chat_stats["totals"]["reactions"] - 1, 0)


# ================ Пересчёт сообщений за неделю ================
def rebuild_message_stats_weekly():
    tz = ZoneInfo("Europe/Moscow")
    now = datetime.datetime.now(tz)

    days_since_friday = (now.weekday() - 4) % 7
    last_friday_18 = now - datetime.timedelta(days=days_since_friday)
    last_friday_18 = last_friday_18.replace(hour=18, minute=0, second=0, microsecond=0)
    start_timestamp = int(last_friday_18.timestamp())

    for chat_name, chat_id in CHATS.items():
        chat_stats = stats[chat_name]
        chat_stats["messages"] = {}
        chat_stats["messages_by_id"] = {}

        offset = 0
        count = 200
        while True:
            resp = vk_api.messages.getHistory(peer_id=2000000000 + chat_id,
                                              count=count,
                                              offset=offset)
            items = resp.get("items", [])
            if not items:
                break

            for msg in items:
                msg_date = msg.get("date", 0)
                if msg_date < start_timestamp:
                    continue
                uid = msg.get("from_id")
                mid = msg.get("id")
                chat_stats["messages"][uid] = chat_stats["messages"].get(uid, 0) + 1
                chat_stats["messages_by_id"][mid] = uid

            offset += len(items)
            if len(items) < count:
                break

        chat_stats["totals"]["messages"] = sum(chat_stats["messages"].values())


# ================= Формирование отчёта =================
def build_report(reset=True, weekly=True):
    if weekly:
        rebuild_message_stats_weekly()
    else:
        pass

    msg = "📊 <b>Статистика за неделю</b>\n\n" if weekly else "⚡️ <b>Промежуточная статистика</b>\n\n"
    for chat_name in CHATS:
        chat_stats = stats[chat_name]
        total_msgs = chat_stats['totals']['messages']
        total_reacts = chat_stats['totals']['reactions']
        msg += (
            f"💬 <b>{chat_name}</b>\n"
            f"Всего сообщений: {total_msgs}\n"
            f"Всего реакций: {total_reacts}\n\n"
        )

        top_msgs = sorted(chat_stats["messages"].items(), key=lambda x: x[1], reverse=True)[:10]
        msg += "<b>Топ-10 по сообщениям:</b>\n"
        for uid, count in top_msgs:
            msg += f" - {get_user_name(uid)} — {count}\n"

        total_reacts_by_user = {}
        for reactions_by_msg in chat_stats["reactions"].values():
            for users_set in reactions_by_msg.values():
                for uid in users_set:
                    total_reacts_by_user[uid] = total_reacts_by_user.get(uid, 0) + 1
        top_reacts = sorted(total_reacts_by_user.items(), key=lambda x: x[1], reverse=True)[:10]
        msg += "\n<b>Топ-10 по реакциям:</b>\n"
        for uid, count in top_reacts:
            msg += f" - {get_user_name(uid)} — {count}\n"

        prev = previous_week_stats.get(chat_name, {"messages": 0, "reactions": 0})
        delta_msgs = delta_reacts = 0.0
        if prev["messages"] > 0:
            delta_msgs = (total_msgs - prev["messages"]) / prev["messages"] * 100
        if prev["reactions"] > 0:
            delta_reacts = (total_reacts - prev["reactions"]) / prev["reactions"] * 100

        msg += (
            f"\nСообщений больше на {delta_msgs:.1f}%\n"
            f"Реакций больше на {delta_reacts:.1f}%\n"
        )
        msg += "\n" + "―" * 30 + "\n\n"

        previous_week_stats[chat_name] = {"messages": total_msgs, "reactions": total_reacts}

    send_telegram(msg)

    if reset:
        for chat_name in CHATS:
            stats[chat_name]["messages"] = {}
            stats[chat_name]["messages_by_id"] = {}
            stats[chat_name]["totals"]["messages"] = 0


def make_weekly_report():
    build_report(reset=True, weekly=True)


# ================= Flask Callback =================
@app.route("/", methods=["POST"])
def callback():
    data = request.get_json()
    if data.get("type") == "confirmation":
        return CONFIRMATION_TOKEN

    elif data.get("type") == "message_new":
        obj = data["object"]["message"]
        peer_id = obj["peer_id"]
        message_id = obj["id"]
        chat_id = peer_id - 2000000000

        # ✅ Обычное сообщение
        for chat_name, cid in CHATS.items():
            if cid == chat_id:
                update_stats_message(chat_name, obj.get("from_id"), message_id)
        return "ok"

    elif data.get("type") == "message_reaction_event":
        obj = data["object"]
        peer_id = obj.get("peer_id")
        if peer_id is None:
            return "ok"
        chat_id = peer_id - 2000000000
        message_id = obj.get("cmid") or obj.get("message_id")
        user_id = obj.get("reacted_id")
        reaction_id = obj.get("reaction_id")
        for chat_name, cid in CHATS.items():
            if cid == chat_id and user_id is not None:
                handle_reaction_event(chat_name, message_id, user_id, reaction_id)
        return "ok"

    elif data.get("type") == "message_delete":
        obj = data["object"]
        peer_id = obj.get("peer_id")
        message_ids = obj.get("message_ids", [])
        chat_id = peer_id - 2000000000

        for chat_name, cid in CHATS.items():
            if cid == chat_id:
                chat_stats = stats[chat_name]
                for mid in message_ids:
                    if mid in chat_stats["messages_by_id"]:
                        uid = chat_stats["messages_by_id"].pop(mid)
                        if uid in chat_stats["messages"]:
                            chat_stats["messages"][uid] = max(chat_stats["messages"][uid] - 1, 0)
                            chat_stats["totals"]["messages"] = max(chat_stats["totals"]["messages"] - 1, 0)

                    if mid in chat_stats["reactions"]:
                        reactions_by_msg = chat_stats["reactions"].pop(mid)
                        for users_set in reactions_by_msg.values():
                            chat_stats["totals"]["reactions"] -= len(users_set)
                        chat_stats["totals"]["reactions"] = max(chat_stats["totals"]["reactions"], 0)
        return "ok"

    return "ok"


# ================= Планировщик отчётов =================
def report_scheduler():
    tz = ZoneInfo("Europe/Moscow")
    while True:
        now = datetime.datetime.now(tz)
        if now.weekday() == 4 and now.hour == 18 and now.minute == 0:
            print("Время еженедельного отчёта! Генерирую...")
            Thread(target=make_weekly_report).start()
            time.sleep(60)
        else:
            time.sleep(20)


# ================= Функция получения участников =================
def get_chat_members(chat_id):
    try:
        response = vk_api.messages.getConversationMembers(peer_id=2000000000 + chat_id)
        members = set()
        for item in response.get("items", []):
            member_id = item.get("member_id")
            if member_id is not None:
                members.add(member_id)
        return members
    except Exception as e:
        print(f"Ошибка получения участников чата {chat_id}: {e}")
        return set()


# ================= Основной цикл VK =================
def bot_loop():
    for chat_name, chat_id in CHATS.items():
        previous_members[chat_name] = get_chat_members(chat_id)
    print("Бот запущен. Отслеживание VK активно.")

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

                # Покинувшие участники
                left_members = previous_members[chat_name] - current_members
                for member in left_members:
                    name = get_user_name(member)
                    vk_link = f"https://vk.com/id{member}"
                    send_telegram(f"➖ {name} ({vk_link}) покинул '{chat_name}'.")

                previous_members[chat_name] = current_members
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("Ошибка VK loop:", e)
            time.sleep(CHECK_INTERVAL)


# ================= Запуск =================
if __name__ == "__main__":
    # Запуск планировщика отчётов
    Thread(target=report_scheduler, daemon=True).start()
    # Запуск цикла VK
    Thread(target=bot_loop, daemon=True).start()
    print("Бот запущен. Еженедельный отчёт собирается в пятницу 18:00. Отслеживание VK активно.")
    # Flask сервер
    app.run(host="0.0.0.0", port=8080)





