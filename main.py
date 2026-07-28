import base64
import json
import os
import time
import urllib.request
import urllib.parse
import hashlib
import shutil
import threading
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Yo'llar va sozlamalar
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(REPO_DIR, "vault.meta.json")
DATA_PATH = os.path.join(REPO_DIR, "accounts.enc")
PBKDF2_ITERATIONS = 390000
SESSION_TIMEOUT = 300  # 5 daqiqa faollik muddati

# Baza bog'lash
if not os.path.exists(META_PATH):
    peer_meta = os.path.join(REPO_DIR, "../secvault/vault.meta.json")
    peer_data = os.path.join(REPO_DIR, "../secvault/accounts.enc")
    if os.path.exists(peer_meta) and os.path.exists(peer_data):
        try:
            shutil.copy(peer_meta, META_PATH)
            shutil.copy(peer_data, DATA_PATH)
            print("Mavjud SecVault bazasi aniqlandi va muvaffaqiyatli bog'landi!")
        except Exception as e:
            print(f"Baza nusxalashda xatolik: {e}")

# .env yuklash
def load_env():
    env = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        env[key.strip()] = val.strip()
    return env

env = load_env()
BOT_TOKEN = env.get("BOT_TOKEN")
ALLOWED_USER_ID = env.get("ALLOWED_USER_ID")

# Seanslar: {chat_id: {"dek": dek_bytes, "state": state_str, "last_activity": float, "temp": {}, "msg_ids": []}}
sessions = {}

# API helper
def call_api(method, params=None):
    if not BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = None
    if params:
        data = urllib.parse.urlencode(params).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"Telegram API xatosi ({method}): {e}")
        return None

# Xabarlarni kuzatish (Message tracking)
def track_msg(chat_id, msg_id):
    if chat_id in sessions:
        if "msg_ids" not in sessions[chat_id]:
            sessions[chat_id]["msg_ids"] = []
        sessions[chat_id]["msg_ids"].append(msg_id)

# Xabar yuborish va ID sini saqlab qolish
def send_msg(chat_id, text, reply_markup=None, parse_mode=None):
    params = {"chat_id": chat_id, "text": text, "protect_content": True}
    if reply_markup:
        params["reply_markup"] = reply_markup if isinstance(reply_markup, str) else json.dumps(reply_markup)
    if parse_mode:
        params["parse_mode"] = parse_mode
        
    res = call_api("sendMessage", params)
    if res and res.get("ok"):
        msg_id = res["result"]["message_id"]
        track_msg(chat_id, msg_id)
        return msg_id
    return None

# Barcha kuzatilgan xabarlarni Telegram'dan o'chirish (Chatni tozalash)
def clear_chat_messages(chat_id):
    if chat_id in sessions and "msg_ids" in sessions[chat_id]:
        # Xabarlarni o'chirish (teskari tartibda o'chirilsa chiroyli chiqadi)
        for msg_id in reversed(sessions[chat_id]["msg_ids"]):
            call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        sessions[chat_id]["msg_ids"] = []

# Kalit hosil qilish
def derive_key(secret: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))

def load_meta() -> dict:
    with open(META_PATH, "r") as f:
        return json.load(f)

def save_meta(meta: dict) -> None:
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

def load_accounts(dek: bytes) -> dict:
    if not os.path.exists(DATA_PATH) or os.path.getsize(DATA_PATH) == 0:
        return {}
    with open(DATA_PATH, "rb") as f:
        token = f.read()
    raw = Fernet(dek).decrypt(token)
    return json.loads(raw.decode())

def save_accounts(dek: bytes, accounts: dict) -> None:
    raw = json.dumps(accounts).encode()
    token = Fernet(dek).encrypt(raw)
    with open(DATA_PATH, "wb") as f:
        f.write(token)

def mask_email(email: str) -> str:
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 5:
        masked_local = local[0] + "***"
    else:
        masked_local = local[:3] + "..." + local[-2:]
    return f"{masked_local}@{domain}"

# Asosiy menyu
def send_main_menu(chat_id, text="Menyudan tanlang:"):
    keyboard = {
        "keyboard": [
            [{"text": "📋 To'liq list"}, {"text": "📧 Emaillar"}],
            [{"text": "👁️ Masked list"}, {"text": "➕ Yangi qo'shish"}],
            [{"text": "✏️ Tahrirlash"}, {"text": "❌ O'chirish"}],
            [{"text": "🧹 Chatni tozalash"}, {"text": "🔒 Qulflash"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }
    send_msg(chat_id, text, keyboard, parse_mode="Markdown")

# Bekor qilish tugmasi
def send_cancel_keyboard(chat_id, text):
    keyboard = {
        "keyboard": [[{"text": "🚫 Bekor qilish"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    send_msg(chat_id, text, keyboard, parse_mode="Markdown")

# Qulflash
def lock_session(chat_id, reason="Qulqlandi."):
    clear_chat_messages(chat_id)
    if chat_id in sessions:
        sessions[chat_id]["dek"] = None
        sessions[chat_id]["state"] = "locked"
        sessions[chat_id]["last_activity"] = 0
        sessions[chat_id]["temp"] = {}
    
    reply_markup = {"remove_keyboard": True}
    send_msg(chat_id, f"🔒 *Tizim yopiq.* {reason}\n\nOchish uchun *Seed* parolingizni kiriting:\n(Tiklash uchun `r` yozing)", reply_markup, parse_mode="Markdown")

# Timeout tekshirish
def check_session(chat_id):
    if chat_id not in sessions:
        sessions[chat_id] = {"dek": None, "state": "locked", "last_activity": 0, "temp": {}, "msg_ids": []}
        return False
        
    sess = sessions[chat_id]
    if sess["state"] == "locked" or sess["dek"] is None:
        return False
        
    if time.time() - sess["last_activity"] > SESSION_TIMEOUT:
        lock_session(chat_id, "Faollik bo'lmaganligi sababli seans avtomatik yopildi.")
        return False
        
    sess["last_activity"] = time.time()
    return True

# Telegram xabarlarini boshqarish
def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = str(message.get("from", {}).get("id", ""))
    text = message.get("text", "").strip()
    msg_id = message["message_id"]
    
    # Xavfsizlik cheklovi
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        call_api("sendMessage", {
            "chat_id": chat_id,
            "text": "❌ Ruxsat berilmagan foydalanuvchi."
        })
        return

    # Seansni sozlash va foydalanuvchi xabarlarini kuzatish
    if chat_id not in sessions:
        sessions[chat_id] = {"dek": None, "state": "locked", "last_activity": 0, "temp": {}, "msg_ids": []}
    
    sess = sessions[chat_id]
    track_msg(chat_id, msg_id)

    # /start komandasi
    if text == "/start":
        if not os.path.exists(META_PATH):
            sess["state"] = "init_seed"
            send_msg(chat_id, "👋 Salom! SecVault tizimi hali sozlanmagan.\n\n*Yangi Seed (asosiy parol)* o'ylab toping va uni yuboring:")
        else:
            lock_session(chat_id, "Tizimga xush kelibsiz!")
        return

    # --- 1. SOZLASh (INITIALIZATION) ---
    if sess["state"].startswith("init_"):
        # Seed kiritish jarayonida foydalanuvchi yuborgan maxfiy ma'lumotlarni chatdan darhol o'chirib yuboramiz
        call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        if msg_id in sess["msg_ids"]:
            sess["msg_ids"].remove(msg_id)
            
        if sess["state"] == "init_seed":
            if not text:
                send_msg(chat_id, "Seed bo'sh bo'lishi mumkin emas.")
                return
            sess["temp"]["seed"] = text
            sess["state"] = "init_seed_confirm"
            send_msg(chat_id, "Seed tasdiqlanishi uchun qayta kiriting (yuborilgan seed xavfsizlik uchun chatdan darhol o'chirildi):")
            
        elif sess["state"] == "init_seed_confirm":
            if text != sess["temp"]["seed"]:
                sess["state"] = "init_seed"
                send_msg(chat_id, "❌ Mos kelmadi! Qaytadan yangi Seed kiriting:")
                return
            sess["state"] = "init_question"
            send_msg(chat_id, "Seed tasdiqlandi.\n\nEndi *Tiklash savolini* kiriting:")
            
        elif sess["state"] == "init_question":
            sess["temp"]["question"] = text
            sess["state"] = "init_answer"
            send_msg(chat_id, "Ushbu savol uchun *Tiklash javobini* kiriting:")
            
        elif sess["state"] == "init_answer":
            seed = sess["temp"]["seed"]
            question = sess["temp"]["question"]
            answer = text
            
            dek = Fernet.generate_key()
            salt_seed = os.urandom(16)
            salt_recovery = os.urandom(16)
            
            meta = {
                "salt_seed": base64.b64encode(salt_seed).decode(),
                "wrapped_key_seed": Fernet(derive_key(seed, salt_seed)).encrypt(dek).decode(),
                "recovery_question": question,
                "salt_recovery": base64.b64encode(salt_recovery).decode(),
                "wrapped_key_recovery": Fernet(derive_key(answer, salt_recovery)).encrypt(dek).decode(),
            }
            save_meta(meta)
            save_accounts(dek, {})
            
            sess["dek"] = dek
            sess["state"] = "unlocked"
            sess["last_activity"] = time.time()
            sess["temp"] = {}
            
            send_main_menu(chat_id, "✅ *Tizim muvaffaqiyatli sozlandi va ochildi!*")
        return

    # --- 2. QULF HOLATI (LOCKED STATE) ---
    if sess["state"] == "locked" or sess["dek"] is None:
        meta = load_meta()
        
        # Har qanday holatda yuborilgan seed yoki parolni chatdan darhol o'chirib tashlaymiz!
        call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        if msg_id in sess["msg_ids"]:
            sess["msg_ids"].remove(msg_id)

        # Tiklash (Recovery)
        if text.lower() == 'r':
            sess["state"] = "recovery_mode"
            send_msg(chat_id, f"❓ *Tiklash savoli:* {meta['recovery_question']}\n\nJavobni yuboring (yuborilgan javob chatdan o'chiriladi):")
            return
            
        elif sess["state"] == "recovery_mode":
            secret = text
            salt = base64.b64decode(meta["salt_recovery"])
            wrapped = meta["wrapped_key_recovery"]
            key = derive_key(secret, salt)
            try:
                dek = Fernet(key).decrypt(wrapped.encode())
                sess["dek"] = dek
                sess["state"] = "unlocked"
                sess["last_activity"] = time.time()
                send_main_menu(chat_id, "🔓 *Tiklash javobi to'g'ri! Tizim ochildi.*")
            except InvalidToken:
                sess["state"] = "locked"
                send_msg(chat_id, "❌ Noto'g'ri javob. Tizim yopiqligicha qoldi. Seed kiriting:")
            return
            
        else:
            # Seed orqali ochish
            secret = text
            salt = base64.b64decode(meta["salt_seed"])
            wrapped = meta["wrapped_key_seed"]
            key = derive_key(secret, salt)
            try:
                dek = Fernet(key).decrypt(wrapped.encode())
                sess["dek"] = dek
                sess["state"] = "unlocked"
                sess["last_activity"] = time.time()
                
                # Ochish so'rovi yuborilganda kiritilgan seed xabarini o'chirganimizdan keyin menyuni ochamiz
                send_main_menu(chat_id, "🔓 *Tizim ochildi!*")
            except InvalidToken:
                send_msg(chat_id, "❌ Noto'g'ri Seed! Qaytadan urinib ko'ring (tiklash uchun `r` yuboring):")
            return

    # --- 3. OCHIQLIK HOLATI (UNLOCKED) ---
    if not check_session(chat_id):
        return

    if text == "🚫 Bekor qilish":
        sess["state"] = "unlocked"
        sess["temp"] = {}
        send_main_menu(chat_id, "Amal bekor qilindi.")
        return

    dek = sess["dek"]
    accounts = load_accounts(dek)

    # State Machine bo'yicha ma'lumotlar kiritish
    if sess["state"] != "unlocked":
        
        # Yangi qo'shish
        if sess["state"] == "add_gmail":
            email = text
            if email in accounts:
                send_cancel_keyboard(chat_id, "⚠️ Bu email allaqachon mavjud. Boshqa email kiriting:")
                return
            sess["temp"]["email"] = email
            sess["state"] = "add_password"
            send_cancel_keyboard(chat_id, f"📧 `{email}` uchun parolni kiriting (bu xabar o'chiriladi):")
            
        elif sess["state"] == "add_password":
            # Parol xabarini chat xavfsizligi uchun o'chirib tashlaymiz
            call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
            if msg_id in sess["msg_ids"]:
                sess["msg_ids"].remove(msg_id)
                
            password = text
            email = sess["temp"]["email"]
            accounts[email] = password
            save_accounts(dek, accounts)
            sess["state"] = "unlocked"
            sess["temp"] = {}
            send_main_menu(chat_id, f"✅ `{email}` muvaffaqiyatli saqlandi!")

        # Tahrirlash
        elif sess["state"] == "edit_gmail":
            email = text
            if email not in accounts:
                send_cancel_keyboard(chat_id, "❌ Bunday email topilmadi. Qayta kiriting:")
                return
            sess["temp"]["email"] = email
            sess["state"] = "edit_password"
            send_cancel_keyboard(chat_id, f"📧 `{email}` uchun yangi parolni kiriting (bu xabar o'chiriladi):")
            
        elif sess["state"] == "edit_password":
            call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
            if msg_id in sess["msg_ids"]:
                sess["msg_ids"].remove(msg_id)
                
            password = text
            email = sess["temp"]["email"]
            accounts[email] = password
            save_accounts(dek, accounts)
            sess["state"] = "unlocked"
            sess["temp"] = {}
            send_main_menu(chat_id, f"✅ `{email}` paroli yangilandi!")

        # O'chirish
        elif sess["state"] == "delete_gmail":
            email = text
            if email not in accounts:
                send_cancel_keyboard(chat_id, "❌ Bunday email topilmadi. Qayta kiriting:")
                return
            sess["temp"]["email"] = email
            sess["state"] = "delete_confirm"
            
            keyboard = {
                "keyboard": [[{"text": "✅ Ha, o'chirilsin"}, {"text": "🚫 Bekor qilish"}]],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            send_msg(chat_id, f"❓ `{email}` rostdan ham o'chirilsinmi?", keyboard)
            
        elif sess["state"] == "delete_confirm":
            if text == "✅ Ha, o'chirilsin":
                email = sess["temp"]["email"]
                del accounts[email]
                save_accounts(dek, accounts)
                sess["state"] = "unlocked"
                sess["temp"] = {}
                send_main_menu(chat_id, f"🗑️ `{email}` muvaffaqiyatli o'chirildi.")
            else:
                sess["state"] = "unlocked"
                sess["temp"] = {}
                send_main_menu(chat_id, "O'chirish bekor qilindi.")
        return

    # Menyudagi tugmalar
    if text == "📋 To'liq list":
        if not accounts:
            send_msg(chat_id, "Baza bo'sh.")
            return
        res = "📋 *To'liq parollar ro'yxati:*\n\n"
        for email, password in accounts.items():
            res += f"📧 `{email}`\n🔑 `{password}`\n\n"
        send_msg(chat_id, res, parse_mode="Markdown")
        
    elif text == "📧 Emaillar":
        if not accounts:
            send_msg(chat_id, "Baza bo'sh.")
            return
        res = "📧 *Emaillar ro'yxati:*\n\n"
        for email in accounts:
            res += f"• `{email}`\n"
        send_msg(chat_id, res, parse_mode="Markdown")
        
    elif text == "👁️ Masked list":
        if not accounts:
            send_msg(chat_id, "Baza bo'sh.")
            return
        res = "👁️ *Yashirin ro'yxati:*\n\n"
        for email, password in accounts.items():
            res += f"📧 `{mask_email(email)}`  |  🔑 `{'*' * len(password)}`\n"
        send_msg(chat_id, res, parse_mode="Markdown")
        
    elif text == "➕ Yangi qo'shish":
        sess["state"] = "add_gmail"
        sess["temp"] = {}
        send_cancel_keyboard(chat_id, "Yangi akkaunt qo'shish. Gmail manzilini yuboring:")
        
    elif text == "✏️ Tahrirlash":
        sess["state"] = "edit_gmail"
        sess["temp"] = {}
        send_cancel_keyboard(chat_id, "Tahrirlash. O'zgartiriladigan Gmail manzilini yuboring:")
        
    elif text == "❌ O'chirish":
        sess["state"] = "delete_gmail"
        sess["temp"] = {}
        send_cancel_keyboard(chat_id, "O'chirish. O'chiriladigan Gmail manzilini yuboring:")
        
    elif text == "🧹 Chatni tozalash":
        # Chatdagi barcha kuzatilgan xabarlarni o'chiradi
        clear_chat_messages(chat_id)
        # Tozalashdan keyin yangi toza menyu chiqarish
        send_main_menu(chat_id, "🧹 Chat tozalandi! Yangi seans boshlandi.")
        
    elif text == "🔒 Qulflash":
        lock_session(chat_id, "Sizning so'rovingizga ko'ra seans yopildi.")

# Faollikni fonda tekshirib turuvchi TTL funksiyasi
def session_ttl_checker():
    while True:
        time.sleep(5)  # Har 5 soniyada faollikni tekshiradi
        now = time.time()
        for chat_id, sess in list(sessions.items()):
            if sess.get("state") != "locked" and sess.get("dek") is not None:
                if now - sess.get("last_activity", 0) > SESSION_TIMEOUT:
                    # Inaktivlik aniqlanganda seans qulflanadi va xabarlar o'chiriladi
                    lock_session(chat_id, "Faollik bo'lmaganligi sababli seans avtomatik yopildi.")

# Bot profil ma'lumotlarini (Nomi, Tavsifi va menyu buyruqlarini) yangilash
def setup_bot_profile():
    print("Bot profilini yangilash...")
    call_api("setMyName", {"name": "SecVault Bot"})
    
    description_text = (
        "SecVault — shaxsiy parollar va Gmail hisoblarini xavfsiz saqlash boti.\n\n"
        "Barcha ma'lumotlar PBKDF2 va Fernet (AES-128) algoritmlari orqali shifrlanadi.\n\n"
        "🔑 Imkoniyatlar:\n"
        "— Hisoblarni xavfsiz shifrlash va saqlash\n"
        "— Emaillarni tahrirlash va o'chirish\n"
        "— 5 daqiqalik faolsizlikdan so'ng chatni tozalash va qulflash\n"
        "— Tiklash savoli orqali parollarni qayta tiklash"
    )
    call_api("setMyDescription", {"description": description_text})
    call_api("setMyShortDescription", {"short_description": "Shifrlangan parollar menejeri"})
    
    commands = [
        {"command": "start", "description": "Botni ishga tushirish / Qulflash"}
    ]
    call_api("setMyCommands", {"commands": json.dumps(commands)})

# Polling loop
def main():
    print("Bot ishga tushdi...")
    if not BOT_TOKEN:
        print("XATOLIK: .env faylida BOT_TOKEN topilmadi!")
        return
        
    # Bot profilini sozlash
    setup_bot_profile()
        
    # TTL tekshiruvchisini fonda (background thread) ishga tushirish
    threading.Thread(target=session_ttl_checker, daemon=True).start()
        
    offset = 0
    while True:
        updates = call_api("getUpdates", {"offset": offset, "timeout": 30})
        if updates and updates.get("ok"):
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message")
                if message:
                    handle_message(message)
        time.sleep(1)

if __name__ == "__main__":
    main()
