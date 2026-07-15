import json
import os
import requests
import gspread
import ssl
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = "8978567584:AAF4WItWVW7yOgsZi4FzF2VeSnZ6OobXNeY"
ADMIN_CHAT_ID = "-1004425242771"
SHEET_ID = "1Y32KfFWg0mK3QwxAXo0FOAwYuMZydcZyEX-OFT3yXu4"
DEEPSEEK_API_KEY = "sk-92e1723ef81c460ebf65ce1a48d1ea3b"  # ← ВСТАВ СВІЙ КЛЮЧ

TG_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==========================================
# 🧠 НАЛАШТУВАННЯ ШТУЧНОГО ІНТЕЛЕКТУ
# ==========================================

SYSTEM_PROMPT = """Ти досвідчений, ввічливий, але суворий менеджер інтернет-магазину меблевої фурнітури та виробництва 'BlackWood'. Спілкуйся живою українською мовою. Будь як досвідчений майстер: без зайвих соплей і підлабузництва. Тільки конкретика: розміри, матеріали, терміни. Не пиши довгих текстів.
Місто: Рівне, вул. Валерія Опанасюка, 8.

БАЗА ЗНАНЬ КОМПАНІЇ (Відповідай тільки по цих даних):
- Телефон менеджера: +380673987757
- Графік роботи: Пн-Пт з 09:00 до 18:00, Субота з 10:00 до 15:00, Неділя - вихідний.
- Терміни виготовлення: 7-10 робочих днів.
- Умови оплати та аванс: Працюємо по авансу 50% на розпил ДСП. Меблева фурнітура та дизайн-проєкти — по повній передплаті.
- Реквізити для оплати: ФОП Калаур Анастасія Леонідівна р/р: UA973220010000026002320072476 ІПН: 3453317341. Після оплати проси скинути квитанцію в чат.
- Доставка: Нова Пошта за тарифами перевізника, самовивіз з виробництва, доставка по місту від 800 гривень.
- Декор ДСП: Клієнти можуть обрати наживо у нас в офісі або скинути нам уже готове маркування (код) декору.

ЩО МИ РОБИМО:
Ви продаєте широкий асортимент меблевої фурнітури: петлі, направляючі, саморізи, ролики, газліфти.
Надаєте послуги: порізка ДСП, лазерна різка металу та гнуття металу. Проєктуєте меблі, робите меблі для бізнесу, лавки з металу.

ЯК ПРИЙМАТИ ЗАМОВЛЕННЯ ТА ВІДПОВІДАТИ НА ПИТАННЯ:
- Якщо клієнт хоче замовити деталь (метал чи ДСП) — кажи, що ми приймаємо креслення в БУДЬ-ЯКОМУ форматі. Хоч малюнок від руки на листочку в клітинку. Хай просто скидає фотку в чат із вказаними розмірами.
- 3D-проектування: Якщо клієнт не має креслень, кажи, що ми робимо повний 3D-проєкт. Вартість розробки: тумбочка або стелаж — 600 грн; шафа — 1200-1500 грн (залежить від складності); кухня — від 2500 грн. КРИТИЧНО ВАЖЛИВО: Називай ціну ТІЛЬКИ на той виріб, про який йде мова в діалозі! Не вивалюй клієнту весь прайс-лист.
- Питання про вартість погонного метра кухні (або будь-яких меблів): НІКОЛИ не кажи ціну з голови. Завжди відповідай так: "Для початку потрібно зробити проєктування, щоб прорахувати розмір кожної деталі. Після цього ми кидаємо це на розкрій, дізнаємося точну кількість матеріалів і тоді буде відома загальна вартість. Фурнітура рахується окремо, бо вона дуже різна по ціні."
- Якщо клієнт питає ціну або можливість виготовлення без конкретики, зразу уточнюй: "Який матеріал вас цікавить? Які точні розміри чи кількість?" — витягуй з нього деталі.

КРИТИЧНЕ ПРАВИЛО: НІКОЛИ не вигадуй номери телефонів, графіки, ціни чи правила, яких немає в цій інструкції. НІКОЛИ НЕ ОБІЦЯЙ ЗНИЖОК ТА БЕЗКОШТОВНОЇ ДОСТАВКИ. Усі знижки обговорюються виключно індивідуально з живим менеджером. Якщо клієнт питає те, чого ти не знаєш точно з цієї інструкції або прайсу, або починає скаржитися — кажи: 'Це питання краще уточнити в офісі, зараз покличу живого менеджера'."""

# ==========================================
# 💾 МЕХАНІКА ПАМ'ЯТІ ТА ПРАЙСУ
# ==========================================
CRM_FILE = os.path.join(BASE_DIR, 'crm_db.json')
STATES_FILE = os.path.join(BASE_DIR, 'user_states.json')
HISTORY_FILE = os.path.join(BASE_DIR, 'chat_history.json')

CATALOG_CACHE = {"text": "", "last_update": datetime.min}

def get_catalog_context():
    global CATALOG_CACHE
    if (datetime.now() - CATALOG_CACHE["last_update"]).seconds < 300:
        return CATALOG_CACHE["text"]

    try:
        gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
        sh = gc.open_by_key(SHEET_ID)
        records = sh.sheet1.get_all_records()

        catalog_text = "\n\n--- АКТУАЛЬНИЙ ПРАЙС З БАЗИ ---\n(Використовуй ці ціни, якщо клієнт питає про конкретний товар. Якщо товару тут нема - кажи, що треба уточнити на складі):\n"
        count = 0
        for row in records:
            if row.get("name") and row.get("price"):
                catalog_text += f"- {row['name']}: {row['price']} грн\n"
                count += 1
            if count >= 100:
                break

        CATALOG_CACHE["text"] = catalog_text
        CATALOG_CACHE["last_update"] = datetime.now()
        return catalog_text
    except Exception as e:
        return ""

def get_user_history(user_id):
    hist_db = load_json(HISTORY_FILE, {})
    return hist_db.get(str(user_id), [])

def append_history(user_id, role, text):
    hist_db = load_json(HISTORY_FILE, {})
    uid = str(user_id)
    if uid not in hist_db:
        hist_db[uid] = []
    hist_db[uid].append({"role": role, "text": text})
    hist_db[uid] = hist_db[uid][-6:]
    save_json(HISTORY_FILE, hist_db)

def ask_deepseek(user_id, prompt):
    """Запит до DeepSeek через бібліотеку openai (працює на Render)"""
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY.startswith("sk-ТВІЙ"):
        return "Помилка: API-ключ DeepSeek не налаштовано. Передаю адміну."

    try:
        from openai import OpenAI

        # Створюємо клієнт один раз і кешуємо (простий спосіб)
        if not hasattr(ask_deepseek, "_client"):
            ask_deepseek._client = OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com"
            )
        client = ask_deepseek._client

        raw_hist = get_user_history(user_id)
        dynamic_system_prompt = SYSTEM_PROMPT + get_catalog_context()

        messages = [{"role": "system", "content": dynamic_system_prompt}]
        for msg in raw_hist:
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": msg["text"]})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.5,
            max_tokens=500
        )

        reply_text = response.choices[0].message.content

        append_history(user_id, "user", prompt)
        append_history(user_id, "model", reply_text)

        return reply_text

    except Exception as e:
        # Повертаємо зрозумілу помилку
        return f"Ой, шось я завис. Помилка ШІ: {e}"

# ==========================================
# 🎛 INLINE-КЛАВІАТУРИ БОТА
# ==========================================
KEYBOARDS = {
    "MAIN": {"inline_keyboard": [
        [{"text": "Статус замовлення", "callback_data": "menu_status"}],
        [{"text": "⚙️ Наші послуги", "callback_data": "menu_services"}],
        [{"text": "📦 Відкрити Каталог", "web_app": {"url": "https://habs.pythonanywhere.com/"}}],
        [{"text": "👨‍🔧 Зв'язок з менеджером", "callback_data": "menu_manager"}],
        [{"text": "📸 Наші роботи", "web_app": {"url": "https://habs.pythonanywhere.com/works"}}],
        [{"text": "ℹ️ Інфо / Доставка", "callback_data": "menu_delivery"}]
    ]},
    "SERVICES": {"inline_keyboard": [
        [{"text": "⚙️ Обробка металу", "callback_data": "menu_metal"}],
        [{"text": "🪵 Розпил та обробка ДСП", "callback_data": "menu_dsp"}],
        [{"text": "📐 3D Конструювання меблів", "callback_data": "menu_3d"}],
        [{"text": "🔙 Головне меню", "callback_data": "menu_main"}]
    ]},
    "METAL": {"inline_keyboard": [
        [{"text": "Лазерна різка", "callback_data": "menu_laser"}],
        [{"text": "Гнуття металу", "callback_data": "menu_bend"}],
        [{"text": "🔙 Назад", "callback_data": "menu_services"}]
    ]},
    "ORDER_ACTION": {"inline_keyboard": [
        [{"text": "Замовити / Питання", "callback_data": "menu_action"}],
        [{"text": "🔙 Назад", "callback_data": "menu_metal"}]
    ]},
    "BACK_TO_SERVICES": {"inline_keyboard": [
        [{"text": "👤 Відправити розкрій / Питання", "callback_data": "menu_action"}],
        [{"text": "🔙 Назад", "callback_data": "menu_services"}]
    ]},
    "BACK_TO_SERVICES_3D": {"inline_keyboard": [
        [{"text": "👤 Зв'язатись з менеджером", "callback_data": "menu_manager"}],
        [{"text": "🔙 Назад", "callback_data": "menu_services"}]
    ]},
    "DELIVERY": {"inline_keyboard": [
        [{"text": "🗺 Прокласти маршрут", "callback_data": "menu_map"}],
        [{"text": "🔙 Головне меню", "callback_data": "menu_main"}]
    ]},
    "ADMIN": {"inline_keyboard": [
        [{"text": "📢 Розсилка ВСІМ", "callback_data": "admin_bc_all"}],
        [{"text": "🔥 Розсилка ПОКУПЦЯМ", "callback_data": "admin_bc_vip"}],
        [{"text": "📊 Статистика бази", "callback_data": "admin_stats"}]
    ]}
}

RESPONSES = {
    "WELCOME": "Здоров був! Це офіційний бот BlackWood. Тут ти можеш дізнатися, чи готові твої деталі, або зв'язатися з менеджером. Вибирай, що треба, в меню нижче 👇",
    "MANAGER": "Менеджер BlackWood вже біжить до тебе. Поки чекаєш, напиши тут своє питання",
    "ORDER_REQ": "Напиши номер свого замовлення (або прізвище), і я подивлюсь, де воно зараз",
    "ORDER_DONE": "Номер прийняв! Менеджер зараз гляне в базу і відпише тобі сюди статус.",
    "SERVICES_MAIN": "BlackWood — це повний технологічний цикл. Ми не просто залізо гнемо, ми робимо речі, які служать роками. Вибирай напрямок, який тебе цікавить 👇",
    "DSP": "Робимо професійний розпил, пазування та крайкування листових матеріалів (ДСП, МДФ, ХДФ). Працюємо на німецькому ЧПУ-обладнанні Homag — геометрія ідеальна. Скидай свою карту розкрою менеджеру!",
    "METAL_MAIN": "Працюємо з металом: точна лазерна різка та гнуття на станку. Вибирай процес 👇",
    "LASER": "Ріжемо метал до такої-то товщини. Скинути креслення менеджеру?",
    "BENDING": "Гнемо метал до такої-то товщини. Скинути креслення менеджеру?",
    "ACTION_CONFIRM": "Прийнято! Скидай свої креслення чи розміри, менеджер вже відкриває чат",
    "DESIGN_3D": "Розробляємо повний конструкторський проєкт твоїх меблів. Опиши свою ідею або скинь ескіз менеджеру.",
    "DELIVERY": "📦 Доставка: Самовивіз по Рівному або Нова Пошта по Україні.\n💵 Оплата: На карту або аванс на розпил.\nПитання — стукай менеджеру!",
    "MAP": "📍 Шукай нас тут: м. Рівне, вул. Валерія Опанасюка, 8"
}

CRM_TEMPLATES = {
    "tpl_rekv": "💳 <b>Реквізити для оплати:</b>\nФОП Калаур А.Л.\nIBAN: UA 973220010000026002320072476\nІПН 3453317341\nПісля оплати скиньте квитанцію сюди.",
    "tpl_done": "✅ <b>Ваше замовлення готове!</b>\nСьогодні відправляємо. Номер ТТН скинемо трохи згодом.",
    "tpl_manager": "👨‍🔧 Менеджер BlackWood вже біжить до тебе! Поки чекаєш, напиши своє питання детальніше."
}

def load_json(path, default):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_tg_request(method, payload):
    payload = {k: v for k, v in payload.items() if v is not None}
    return requests.post(f"{TG_API_URL}/{method}", json=payload).json()

def get_or_create_topic(user_id, user_name):
    crm_db = load_json(CRM_FILE, {"users_to_topics": {}, "topics_to_users": {}})
    if user_id in crm_db["users_to_topics"]:
        return crm_db["users_to_topics"][user_id], crm_db
    topic_res = send_tg_request("createForumTopic", {"chat_id": ADMIN_CHAT_ID, "name": f"👤 {user_name}"})
    if topic_res.get("ok"):
        thread_id = str(topic_res["result"]["message_thread_id"])
        crm_db = load_json(CRM_FILE, {"users_to_topics": {}, "topics_to_users": {}})
        if user_id not in crm_db["users_to_topics"]:
            crm_db["users_to_topics"][user_id] = thread_id
            crm_db["topics_to_users"][thread_id] = user_id
            save_json(CRM_FILE, crm_db)
            keyboard = {"inline_keyboard": [
                [{"text": "💳 Реквізити", "callback_data": "tpl_rekv"}],
                [{"text": "✅ Замовлення готове", "callback_data": "tpl_done"}],
                [{"text": "👨‍🔧 Менеджер", "callback_data": "tpl_manager"}]
            ]}
            send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": "🎛 <b>Пульт керування:</b>", "parse_mode": "HTML", "reply_markup": keyboard})
        return crm_db["users_to_topics"][user_id], crm_db
    return None, crm_db

@app.route("/api/bot", methods=["POST"])
def tg_webhook():
    update = request.json
    if not update:
        return "OK", 200

    crm_db = load_json(CRM_FILE, {"users_to_topics": {}, "topics_to_users": {}})
    user_states = load_json(STATES_FILE, {})

    if "callback_query" in update:
        cq = update["callback_query"]
        cb_data = cq.get("data")
        msg = cq.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id"))

        if chat_id == ADMIN_CHAT_ID:
            thread_id = str(msg.get("message_thread_id")) if msg.get("message_thread_id") else None
            if cb_data.startswith("admin_bc_"):
                mode = cb_data.replace("admin_bc_", "")
                user_states["admin_bc_mode"] = mode
                save_json(STATES_FILE, user_states)
                send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": f"⏳ <b>Режим розсилки активовано.</b>\nСкидай сюди що завгодно!", "parse_mode": "HTML"})
            elif cb_data == "admin_stats":
                users_count = len(crm_db.get("users_to_topics", {}))
                vip_count = 0
                try:
                    gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
                    data_hist = gc.open_by_key(SHEET_ID).worksheet("Історія").get_all_values()[1:]
                    vip_count = len(set([str(row[1]).strip() for row in data_hist if len(row) >= 2 and str(row[1]).strip().isdigit()]))
                except:
                    pass
                send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": f"📊 <b>Статистика:</b>\n👥 Всього: {users_count}\n🛍 Покупців: {vip_count}", "parse_mode": "HTML"})
            elif cb_data in CRM_TEMPLATES:
                user_id = crm_db["topics_to_users"].get(thread_id)
                if user_id:
                    if user_id.startswith("web_"):
                        send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": "⚠️ <i>Це клієнт з сайту (без Телеграму). Зв'яжіться з ним по номеру телефону!</i>", "parse_mode": "HTML"})
                    else:
                        send_tg_request("sendMessage", {"chat_id": user_id, "text": CRM_TEMPLATES[cb_data], "parse_mode": "HTML"})
                        send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": f"✅ <i>Відправлено:</i>\n{CRM_TEMPLATES[cb_data]}", "parse_mode": "HTML"})
        else:
            user_id = chat_id
            user_name = cq.get("from", {}).get("first_name", "Клієнт")
            thread_id, crm_db = get_or_create_topic(user_id, user_name)
            out_text, out_kb, admin_ping = None, None, None
            if cb_data == "menu_main":
                out_text, out_kb = RESPONSES["WELCOME"], KEYBOARDS["MAIN"]
                user_states[user_id] = "MAIN"
            elif cb_data == "menu_services":
                out_text, out_kb = RESPONSES["SERVICES_MAIN"], KEYBOARDS["SERVICES"]
            elif cb_data == "menu_status":
                out_text = RESPONSES["ORDER_REQ"]
                user_states[user_id] = "WAITING_ORDER"
            elif cb_data == "menu_metal":
                out_text, out_kb = RESPONSES["METAL_MAIN"], KEYBOARDS["METAL"]
            elif cb_data == "menu_dsp":
                out_text, out_kb = RESPONSES["DSP"], KEYBOARDS["BACK_TO_SERVICES"]
            elif cb_data == "menu_3d":
                out_text, out_kb = RESPONSES["DESIGN_3D"], KEYBOARDS["BACK_TO_SERVICES_3D"]
            elif cb_data == "menu_laser":
                out_text, out_kb = RESPONSES["LASER"], KEYBOARDS["ORDER_ACTION"]
            elif cb_data == "menu_bend":
                out_text, out_kb = RESPONSES["BENDING"], KEYBOARDS["ORDER_ACTION"]
            elif cb_data in ["menu_manager", "menu_action"]:
                out_text, out_kb = RESPONSES["ACTION_CONFIRM"] if cb_data == "menu_action" else RESPONSES["MANAGER"], KEYBOARDS["MAIN"]
                admin_ping = "🔔 <b>Клієнт просить зв'язку!</b>"
            elif cb_data == "menu_delivery":
                out_text, out_kb = RESPONSES["DELIVERY"], KEYBOARDS["DELIVERY"]
            elif cb_data == "menu_map":
                out_text, out_kb = RESPONSES["MAP"], KEYBOARDS["MAIN"]
            if out_text:
                send_tg_request("sendMessage", {"chat_id": user_id, "text": out_text, "parse_mode": "HTML", "reply_markup": out_kb})
            if admin_ping and thread_id:
                send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": admin_ping, "parse_mode": "HTML"})
        send_tg_request("answerCallbackQuery", {"callback_query_id": cq["id"]})

    elif "message" in update:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        text = str(msg.get("text", "")).strip()
        if chat_id == ADMIN_CHAT_ID:
            thread_id = str(msg["message_thread_id"]) if msg.get("message_thread_id") else None
            if text == "/admin":
                send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": "🎛 <b>Панель розсилок:</b>", "parse_mode": "HTML", "reply_markup": KEYBOARDS["ADMIN"]})
                return "OK", 200
            bc_mode = user_states.get("admin_bc_mode")
            if bc_mode:
                user_states["admin_bc_mode"] = None
                save_json(STATES_FILE, user_states)
                msg_id = msg["message_id"]
                send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": "🚀 <b>Починаю розсилку...</b>", "parse_mode": "HTML"})
                if bc_mode == "all":
                    users = [u for u in crm_db.get("users_to_topics", {}).keys() if not u.startswith("web_")]
                    success = sum(1 for u in users if send_tg_request("copyMessage", {"chat_id": u, "from_chat_id": ADMIN_CHAT_ID, "message_id": msg_id}).get("ok"))
                    send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": f"📢 <b>Готово!</b> Доставлено: {success}/{len(users)}.", "parse_mode": "HTML"})
                elif bc_mode == "vip":
                    try:
                        gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
                        data_hist = gc.open_by_key(SHEET_ID).worksheet("Історія").get_all_values()[1:]
                        vip_users = list(set([str(r[1]).strip() for r in data_hist if len(r) >= 2 and str(r[1]).strip().isdigit() and not str(r[1]).startswith("web_")]))
                        success = sum(1 for u in vip_users if send_tg_request("copyMessage", {"chat_id": u, "from_chat_id": ADMIN_CHAT_ID, "message_id": msg_id}).get("ok"))
                        send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": f"🔥 <b>Готово!</b> Доставлено: {success}/{len(vip_users)}.", "parse_mode": "HTML"})
                    except Exception as e:
                        send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": f"❌ Помилка Гугла: {e}"})
                return "OK", 200
            elif thread_id:
                user_id = crm_db["topics_to_users"].get(thread_id)
                if user_id and not msg.get("from", {}).get("is_bot"):
                    if user_id.startswith("web_"):
                        send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": "⚠️ <i>Цей клієнт зайшов з сайту. Він не отримає це повідомлення в Телеграм. Дзвони йому!</i>", "parse_mode": "HTML"})
                    else:
                        send_tg_request("copyMessage", {"chat_id": user_id, "from_chat_id": ADMIN_CHAT_ID, "message_id": msg["message_id"]})
        else:
            user_id = chat_id
            user_name = msg.get("from", {}).get("first_name", "Клієнт")
            thread_id, crm_db = get_or_create_topic(user_id, user_name)
            if text == "/start":
                send_tg_request("sendMessage", {"chat_id": user_id, "text": RESPONSES["WELCOME"], "parse_mode": "HTML", "reply_markup": KEYBOARDS["MAIN"]})
                user_states[user_id] = "MAIN"
            else:
                current_state = user_states.get(user_id, "MAIN")
                if current_state == "WAITING_ORDER":
                    send_tg_request("sendMessage", {"chat_id": user_id, "text": RESPONSES["ORDER_DONE"], "reply_markup": KEYBOARDS["MAIN"]})
                    user_states[user_id] = "MAIN"
                    if thread_id:
                        send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": f"🔢 <b>Клієнт вказав замовлення:</b> {text}", "parse_mode": "HTML"})
                else:
                    ai_answer = ask_deepseek(user_id, text)
                    send_tg_request("sendMessage", {"chat_id": user_id, "text": ai_answer})
                    if thread_id:
                        send_tg_request("sendMessage", {"chat_id": ADMIN_CHAT_ID, "message_thread_id": thread_id, "text": f"💬 <b>Клієнт:</b> {text}\n🤖 <b>Бот:</b> {ai_answer}", "parse_mode": "HTML"})
    save_json(CRM_FILE, crm_db)
    save_json(STATES_FILE, user_states)
    return "OK", 200

# ==========================================
# 🛒 МАРШРУТИ МАГАЗИНУ ТА КАБІНЕТУ
# ==========================================

@app.route("/api/promo/<code>", methods=["GET"])
def check_promo(code):
    try:
        gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
        try:
            promo_ws = gc.open_by_key(SHEET_ID).worksheet("Промокоди")
        except:
            return jsonify({"status": "error", "message": "Вкладка 'Промокоди' не знайдена."})
        records = promo_ws.get_all_values()[1:]
        for row in records:
            if len(row) >= 2:
                sheet_code = str(row[0]).strip()
                sheet_discount = str(row[1]).strip()
                if sheet_code.lower() == code.lower() and sheet_discount.isdigit():
                    return jsonify({"status": "success", "discount": int(sheet_discount)})
        return jsonify({"status": "error", "message": "Промокод недійсний!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Помилка сервера: {e}"})

@app.route("/api/order", methods=["POST"])
def create_order():
    data = request.json
    user_id = str(data.get("user_id"))
    user_name = data.get("user_name", "Клієнт")
    cart = data.get("cart", {})
    total = data.get("total", 0)
    promo = data.get("promo_code", "")

    items_text = "".join([f"▪️ {item['name']} — {item['qty']} шт. ({item['price'] * item['qty']} грн)\n" for item in cart.values()])
    promo_text = f"\n🎟 <b>Промокод:</b> {promo}" if promo else ""

    if user_id == "FROM_WEB_BROWSER":
        tracking_id = f"web_{user_name}"
        admin_text = f"🌐 <b>НОВЕ ЗАМОВЛЕННЯ З САЙТУ!</b>\n👤 <b>Клієнт:</b> {user_name}\n\n{items_text}{promo_text}\n💵 <b>Сума до сплати:</b> {total} грн"
    else:
        tracking_id = user_id
        admin_text = f"🔥 <b>НОВЕ ЗАМОВЛЕННЯ З ТЕЛЕГРАМ БОТА!</b>\n👤 <b>Клієнт:</b> <a href='tg://user?id={user_id}'>{user_name}</a>\n\n{items_text}{promo_text}\n💵 <b>Сума до сплати:</b> {total} грн"

    crm_db = load_json(CRM_FILE, {"users_to_topics": {}, "topics_to_users": {}})
    if tracking_id not in crm_db["users_to_topics"]:
        thread_id, crm_db = get_or_create_topic(tracking_id, user_name)
    else:
        thread_id = crm_db["users_to_topics"].get(tracking_id)

    payload = {"chat_id": ADMIN_CHAT_ID, "text": admin_text, "parse_mode": "HTML"}
    if thread_id:
        payload["message_thread_id"] = thread_id
    send_tg_request("sendMessage", payload)

    try:
        gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
        sh = gc.open_by_key(SHEET_ID)
        try:
            history_ws = sh.worksheet("Історія")
        except:
            history_ws = sh.add_worksheet(title="Історія", rows="1000", cols="5")
            history_ws.append_row(["Дата", "ID Клієнта", "Ім'я", "Товари", "Сума"])
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        items_summary = "; ".join([f"{item['name']} x{item['qty']}" for item in cart.values()])
        if promo:
            items_summary += f" [Промокод: {promo}]"
        history_ws.append_row([date_str, tracking_id, user_name, items_summary, total])
    except Exception as e:
        print(f"Помилка Гугла: {e}")

    return jsonify({"status": "success"})

@app.route("/api/history/<user_id>", methods=["GET"])
def get_history(user_id):
    records = []
    try:
        gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
        data = gc.open_by_key(SHEET_ID).worksheet("Історія").get_all_values()[1:]
        for row in data:
            if len(row) >= 5 and row[1] == str(user_id):
                records.append({"date": row[0], "items": row[3], "total": row[4]})
    except:
        pass
    return jsonify(records)

@app.route("/api/works", methods=["GET"])
def get_works():
    try:
        gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
        return jsonify(gc.open_by_key(SHEET_ID).worksheet("Роботи").get_all_records())
    except:
        return jsonify([])

def load_products_with_discount(user_id=None):
    try:
        gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
        sh = gc.open_by_key(SHEET_ID)
        discount_pct, manual_discount_found = 0, False
        if user_id and str(user_id).strip() != "" and user_id != "FROM_WEB_BROWSER":
            try:
                for row in sh.worksheet("Знижки").get_all_values()[1:]:
                    if len(row) >= 2 and str(row[0]).strip() == str(user_id):
                        discount_pct = float(row[1].strip().replace('%', ''))
                        manual_discount_found = True
                        break
            except:
                pass
            if not manual_discount_found:
                try:
                    total_spent = sum([float(r[4]) for r in sh.worksheet("Історія").get_all_values()[1:] if len(r) >= 5 and r[1] == str(user_id)])
                    if total_spent >= 30000:
                        discount_pct = 15
                    elif total_spent >= 15000:
                        discount_pct = 10
                    elif total_spent >= 5000:
                        discount_pct = 5
                    elif total_spent >= 2000:
                        discount_pct = 3
                except:
                    pass

        products_dict = {}
        for row in sh.sheet1.get_all_records():
            if row.get("id") and row.get("name"):
                name = str(row["name"]).strip()
                if name not in products_dict:
                    products_dict[name] = {"name": name, "category": str(row.get("category", "Всі")), "image": str(row.get("image", "")), "description": str(row.get("description", "")), "variants": []}
                base_price, old_price = float(row.get("price") or 0), float(row.get("old_price") or 0)
                if discount_pct > 0 and base_price > 0:
                    old_price, base_price = base_price, round(base_price * (1 - discount_pct / 100), 2)
                products_dict[name]["variants"].append({"id": str(row["id"]), "variant_name": str(row.get("variant", "")).strip(), "price": base_price, "old_price": old_price, "status": str(row.get("status", "")).strip() or "В наявності"})

        try:
            dsp_ws = sh.worksheet("Залишки ДСП")
            dsp_id_counter = 999000
            for row in dsp_ws.get_all_records():
                name = str(row.get("Назва", "")).strip()
                qty = str(row.get("Кількість", "")).strip()
                price = float(row.get("Ціна") or 0) if row.get("Ціна") else 0
                img = str(row.get("Фото", "")).strip()
                if name:
                    if name not in products_dict:
                        products_dict[name] = {"name": name, "category": "ДСП", "image": img, "description": "Актуальний залишок плити на складі", "variants": []}
                    old_price = 0
                    if discount_pct > 0 and price > 0:
                        old_price = price
                        price = round(price * (1 - discount_pct / 100), 2)
                    status_val = f"В наявності: {qty} шт." if qty else "Закінчилось"
                    products_dict[name]["variants"].append({"id": f"dsp_{dsp_id_counter}", "variant_name": "", "price": price, "old_price": old_price, "status": status_val})
                    dsp_id_counter += 1
        except Exception as e:
            print(f"Помилка парсингу Залишків ДСП: {e}")

        return {"discount": discount_pct, "items": list(products_dict.values())}
    except:
        return {"discount": 0, "items": []}

@app.route("/api/products", methods=["GET"])
def get_products():
    return jsonify(load_products_with_discount(request.args.get("user_id")))

@app.route("/", methods=["GET"])
def read_root():
    return send_file(os.path.join(BASE_DIR, "index.html"))

@app.route("/works", methods=["GET"])
def read_works():
    return send_file(os.path.join(BASE_DIR, "works.html"))

@app.route("/photo/<filename>", methods=["GET"])
def get_photo_file(filename):
    file_path = os.path.join(BASE_DIR, "photo", filename)
    return send_file(file_path) if os.path.exists(file_path) else ("Not Found", 404)

# ==========================================
# 🔑 LIGNACAD
# ==========================================
DB_FILE = os.path.join(BASE_DIR, 'clients.json')

def load_db():
    return json.load(open(DB_FILE, 'r')) if os.path.exists(DB_FILE) else {}

def save_db(data):
    json.dump(data, open(DB_FILE, 'w'), indent=4)

@app.route("/api/verify", methods=["POST"])
def verify():
    hwid = request.json.get('hwid')
    if not hwid:
        return jsonify({"status": "banned", "message": "ID не знайдено."})
    db = load_db()
    if hwid not in db:
        db[hwid] = {"status": "trial", "registered": datetime.now().isoformat(), "expires": (datetime.now() + timedelta(days=14)).isoformat(), "note": "Новий юзер"}
        save_db(db)
        return jsonify({"status": "ok", "message": "Welcome to trial"})
    user = db[hwid]
    if user["status"] == "banned":
        return jsonify({"status": "banned"})
    if user["status"] == "trial" and datetime.now() > datetime.fromisoformat(user["expires"]):
        user["status"] = "expired"
        save_db(db)
        return jsonify({"status": "banned", "message": "Час вийшов."})
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True)
