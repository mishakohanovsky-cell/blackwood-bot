import json
import os
import requests
import gspread
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file

# Додаткові бібліотеки для роботи з Excel
import openpyxl
from io import BytesIO

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = "8978567584:AAF4WItWVW7yOgsZi4FzF2VeSnZ6OobXNeY"
ADMIN_CHAT_ID = "-1004425242771"
SHEET_ID = "1Y32KfFWg0mK3QwxAXo0FOAwYuMZydcZyEX-OFT3yXu4"
DEEPSEEK_API_KEY = "sk-92e1723ef81c460ebf65ce1a48d1ea3b"

TG_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==========================================
# 🛡️ АВТОМАТИЧНЕ ВІДНОВЛЕННЯ ВЕБХУКА
# ==========================================
def ensure_webhook():
    try:
        info = requests.get(f"{TG_API_URL}/getWebhookInfo").json()
        current_url = info.get("result", {}).get("url", "")
        expected_url = "https://blackwood-bot.onrender.com/api/bot"
        if current_url != expected_url:
            requests.get(f"{TG_API_URL}/setWebhook?url={expected_url}")
            print("Webhook updated")
    except:
        pass

# ==========================================
# 🧠 НАЛАШТУВАННЯ ШТУЧНОГО ІНТЕЛЕКТУ
# ==========================================

SYSTEM_PROMPT = """Ти досвідчений, ввічливий менеджер інтернет-магазину..."""  # Твій System Prompt без змін

# Швидкі відповіді без ШІ (економія токенів)
FAQ_ANSWERS = {
    # Твої FAQ без змін
}

# ==========================================
# 💾 МЕХАНІКА ПАМ'ЯТІ ТА ПРАЙСУ
# ==========================================
CRM_FILE = os.path.join(BASE_DIR, 'crm_db.json')
STATES_FILE = os.path.join(BASE_DIR, 'user_states.json')
HISTORY_FILE = os.path.join(BASE_DIR, 'chat_history.json')

CATALOG_CACHE = {"text": "", "last_update": datetime.min}
TRAINING_CACHE = {"data": [], "last_update": datetime.min}

def get_gsheet_sheet(sheet_name):
    gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
    sh = gc.open_by_key(SHEET_ID)
    try:
        return sh.worksheet(sheet_name)
    except:
        return None

def load_training_data():
    # Без змін
    pass

def find_in_training(user_question):
    # Без змін
    pass

def add_to_training(question, answer):
    # Без змін
    pass

def get_catalog_context():
    # Без змін
    pass

def get_user_history(user_id):
    # Без змін
    pass

def append_history(user_id, role, text):
    # Без змін
    pass

def ask_deepseek(user_id, prompt):
    # Без змін
    pass

# ==========================================
# 📊 ФУНКЦІЯ ОНОВЛЕННЯ ЦІН З EXCEL-ФАЙЛУ
# ==========================================
def update_prices_from_excel(file_bytes):
    """
    Читає Excel-файл з байтів, оновлює Google-таблицю.
    Повертає (updated_count, new_count, errors).
    """
    try:
        wb = openpyxl.load_workbook(BytesIO(file_bytes))
        ws_excel = wb.active
    except Exception as e:
        return 0, 0, [f"Помилка читання Excel: {e}"]

    # Підключаємося до Google Sheets
    try:
        gc = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.sheet1  # Основний аркуш з товарами
    except Exception as e:
        return 0, 0, [f"Помилка доступу до Google Sheets: {e}"]

    # Завантажуємо існуючі товари в словник {article: row_number}
    existing = {}
    try:
        rows = ws.get_all_values()
        header = rows[0] if rows else []
        # Визначаємо індекси колонок за назвами
        id_col = header.index("id") if "id" in header else 0
        price_col = header.index("price") if "price" in header else 4
        name_col = header.index("name") if "name" in header else 1
        variant_col = header.index("variant") if "variant" in header else 3
    except Exception as e:
        return 0, 0, [f"Помилка структури таблиці: {e}"]

    for i, row in enumerate(rows[1:], start=2):
        if len(row) > id_col:
            existing[row[id_col]] = i

    updates_count = 0
    new_count = 0
    errors = []

    # Проходимо по рядках Excel
    for row in ws_excel.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 3:
            continue

        # Припускаємо структуру: [№, Артикул, Назва, Ціна, ..., Кількість]
        article = str(row[1]).strip() if row[1] else ""
        name = str(row[2]).strip() if row[2] else ""
        price = float(row[3]) if row[3] else 0.0
        quantity = int(row[5]) if len(row) > 5 and row[5] else 0

        if not article or not name:
            continue

        # Витягуємо розмір для variant
        def parse_size(product_name):
            patterns = [r'L[=\s]*(\d+)', r'd[=\s]*(\d+)', r'(\d+)\s*(?:мм|mm)']
            for p in patterns:
                match = re.search(p, product_name, re.IGNORECASE)
                if match:
                    return match.group(1)
            return ""

        variant = parse_size(name)
        status = "В наявності" if quantity > 0 else "Закінчилось"

        try:
            if article in existing:
                row_num = existing[article]
                # Оновлюємо ціну, назву, варіант, статус
                ws.update(f"B{row_num}", [[name]])
                ws.update(f"E{row_num}", [[price]])
                if variant:
                    ws.update(f"D{row_num}", [[variant]])
                ws.update(f"H{row_num}", [[status]])
                updates_count += 1
            else:
                # Додаємо новий рядок: id, name, category, variant, price, image, description, old_price, status
                new_row = [article, name, "", variant, price, "", "", "", status]
                ws.append_row(new_row)
                new_count += 1
        except Exception as e:
            errors.append(f"Помилка обробки артикула {article}: {e}")

    return updates_count, new_count, errors

# ==========================================
# 🎛 INLINE-КЛАВІАТУРИ БОТА (з Render URL)
# ==========================================
# Твої KEYBOARDS, RESPONSES, CRM_TEMPLATES без змін, але з URL на Render

# ... (тут уся велика частина з клавіатурами, обробниками повідомлень, health-check)

# ==========================================
# 🔄 HEALTH CHECK + АВТОМАТИЧНЕ ВІДНОВЛЕННЯ ВЕБХУКА
# ==========================================
@app.route("/health", methods=["GET"])
def health_check():
    ensure_webhook()
    return "OK", 200

@app.route("/api/bot", methods=["POST"])
def tg_webhook():
    update = request.json
    if not update:
        return "OK", 200

    crm_db = load_json(CRM_FILE, {"users_to_topics": {}, "topics_to_users": {}})
    user_states = load_json(STATES_FILE, {})

    if "callback_query" in update:
        # Твоя існуюча обробка callback'ів
        pass

    elif "message" in update:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        text = str(msg.get("text", "")).strip()

        if chat_id == ADMIN_CHAT_ID:
            thread_id = str(msg.get("message_thread_id")) if msg.get("message_thread_id") else None

            # ---- ОБРОБКА EXCEL-ФАЙЛУ ДЛЯ ОНОВЛЕННЯ ЦІН ----
            if "document" in msg:
                doc = msg["document"]
                file_name = doc.get("file_name", "")
                if file_name.lower().endswith(('.xls', '.xlsx')):
                    try:
                        # Завантажуємо файл з Telegram
                        file_id = doc["file_id"]
                        file_info = send_tg_request("getFile", {"file_id": file_id})
                        file_path = file_info.get("result", {}).get("file_path")
                        if file_path:
                            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                            resp = requests.get(file_url)
                            if resp.status_code == 200:
                                # Обробляємо файл
                                updated, new, errors = update_prices_from_excel(resp.content)
                                response_text = f"✅ Прайс-лист оброблено:\n- Оновлено товарів: {updated}\n- Додано нових: {new}"
                                if errors:
                                    response_text += "\n❗ Помилки:\n" + "\n".join(errors[:5])
                                send_tg_request("sendMessage", {
                                    "chat_id": ADMIN_CHAT_ID,
                                    "message_thread_id": thread_id,
                                    "text": response_text
                                })
                            else:
                                send_tg_request("sendMessage", {
                                    "chat_id": ADMIN_CHAT_ID,
                                    "message_thread_id": thread_id,
                                    "text": "❌ Не вдалося завантажити файл із серверів Telegram."
                                })
                    except Exception as e:
                        send_tg_request("sendMessage", {
                            "chat_id": ADMIN_CHAT_ID,
                            "message_thread_id": thread_id,
                            "text": f"❌ Помилка оновлення цін: {e}"
                        })
                    return "OK", 200

            # ... решта адмінських команд (/admin, розсилка, копіювання повідомлень)
            # Залиш все без змін

        else:
            # Обробка звичайних користувачів (фото, FAQ, навчання, ШІ)
            # ... (твій існуючий код)
            pass

    return "OK", 200

# ... решта маршрутів (каталог, історія, веб-сторінки, LIGNACAD)
