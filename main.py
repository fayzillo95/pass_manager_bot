import base64
import json
import os
import time
import urllib.request
import urllib.parse
import hashlib
import shutil
import threading
import subprocess
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Yo'llar va sozlamalar
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(REPO_DIR, "vault.meta.json")
DATA_PATH = os.path.join(REPO_DIR, "accounts.enc")
MSG_IDS_PATH = os.path.join(REPO_DIR, "msg_ids.json")
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

def get_config(key):
    val = os.environ.get(key)
    if val:
        return val
    return env.get(key)

BOT_TOKEN = get_config("BOT_TOKEN")
ALLOWED_USER_ID = get_config("ALLOWED_USER_ID")

CONFIG_PATH = os.path.join(REPO_DIR, "github_config.json")

def load_github_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_github_config(token=None, repo=None):
    cfg = load_github_config()
    if token is not None:
        cfg["token"] = token
    if repo is not None:
        cfg["repo"] = repo
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"GitHub config saqlashda xatolik: {e}")

def get_github_token():
    cfg = load_github_config()
    return cfg.get("token") or get_config("GITHUB_TOKEN")

def get_github_repo():
    cfg = load_github_config()
    return cfg.get("repo") or get_config("GITHUB_REPO")

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

# Diskdan xabar ID'larini yuklash
def load_msg_ids():
    if os.path.exists(MSG_IDS_PATH):
        try:
            with open(MSG_IDS_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# Diskka xabar ID'larini yozish
def save_msg_ids(all_ids):
    try:
        with open(MSG_IDS_PATH, "w") as f:
            json.dump(all_ids, f)
    except Exception as e:
        print(f"Msg IDs saqlashda xatolik: {e}")

# Hozirgi seanslar ID'larini diskda yangilash
def save_current_msg_ids():
    data = {}
    for chat_id, sess in sessions.items():
        if "msg_ids" in sess:
            data[str(chat_id)] = sess["msg_ids"]
    save_msg_ids(data)

# Xabarlarni kuzatish (Message tracking)
def track_msg(chat_id, msg_id):
    if chat_id in sessions:
        if "msg_ids" not in sessions[chat_id]:
            sessions[chat_id]["msg_ids"] = []
        sessions[chat_id]["msg_ids"].append(msg_id)
        save_current_msg_ids()

# Xabar yuborish va ID sini saqlab qolish
def send_msg(chat_id, text, reply_markup=None, parse_mode=None):
    params = {"chat_id": chat_id, "text": text}
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
        save_current_msg_ids()

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
    # Yangilanishlarni GitHub'ga push qilish
    sync_github_push()

# GitHub'ga shifrlangan bazani push qilish
def sync_github_push():
    token = get_github_token()
    repo = get_github_repo()
    if not token or not repo:
        print("GitHub token yoki repo topilmadi. Auto-push o'tkazib yuborildi.")
        return False
    
    print("GitHub'ga ma'lumotlarni yuborish (push)...")
    try:
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        
        # Git sozlamalarini faqat ushbu repo uchun moslash
        subprocess.run(["git", "config", "user.name", "SecVault Bot"], cwd=REPO_DIR, check=False)
        subprocess.run(["git", "config", "user.email", "bot@secvault.local"], cwd=REPO_DIR, check=False)
        
        # Origin ulanishini boshidan toza sozlash (Render'da remote mavjud bo'lmasligi mumkin)
        subprocess.run(["git", "remote", "remove", "origin"], cwd=REPO_DIR, check=False)
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=REPO_DIR, check=True)
        
        # Fayllarni gitga kiritish va push qilish
        subprocess.run(["git", "add", "-f", "accounts.enc", "vault.meta.json"], cwd=REPO_DIR, check=True)
        subprocess.run(["git", "commit", "-m", "backup: update vault data in real-time [skip ci]"], cwd=REPO_DIR, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_DIR, check=True)
        
        print("Muvaffaqiyatli GitHub'ga push qilindi!")
        return True
    except Exception as e:
        print(f"GitHub'ga push qilishda xatolik yuz berdi: {e}")
        return False

# GitHub'dan shifrlangan bazani pull qilish
def sync_github_pull():
    token = get_github_token()
    repo = get_github_repo()
    if not token or not repo:
        print("GitHub token yoki repo topilmadi. Auto-pull o'tkazib yuborildi.")
        return False
    
    print("GitHub'dan yangi ma'lumotlarni olish (pull)...")
    try:
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        
        # Origin ulanishini boshidan toza sozlash
        subprocess.run(["git", "remote", "remove", "origin"], cwd=REPO_DIR, check=False)
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=REPO_DIR, check=True)
        
        subprocess.run(["git", "pull", "origin", "main"], cwd=REPO_DIR, check=True)
        print("Muvaffaqiyatli GitHub'dan pull qilindi!")
        return True
    except Exception as e:
        print(f"GitHub'dan pull qilishda xatolik yuz berdi: {e}")
        return False

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
            [{"text": "🔄 GitHub Sync"}, {"text": "⚙️ GitHub Status"}],
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

    # --- GitHub Sozlamalari Buyruqlari ---
    if text.startswith("/set_token"):
        call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        if msg_id in sess["msg_ids"]:
            sess["msg_ids"].remove(msg_id)
            
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_msg(chat_id, "❌ Format noto'g'ri!\nFoydalanish: `/set_token <token>`")
            return
        
        token = parts[1]
        save_github_config(token=token)
        send_msg(chat_id, "✅ GitHub Personal Access Token muvaffaqiyatli saqlandi! (Matn xavfsizlik uchun chatdan o'chirildi)")
        return

    elif text.startswith("/set_repo"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_msg(chat_id, "❌ Format noto'g'ri!\nFoydalanish: `/set_repo <owner/repo>`")
            return
            
        repo = parts[1]
        save_github_config(repo=repo)
        send_msg(chat_id, f"✅ GitHub repozitoriyasi sozlandi: `{repo}`")
        return

    elif text == "/github_status":
        token = get_github_token()
        repo = get_github_repo()
        
        masked_token = "Sozlanmagan ❌"
        if token:
            masked_token = token[:7] + "..." + token[-4:] if len(token) > 10 else "Sozlangan ✅"
            
        repo_status = repo if repo else "Sozlanmagan ❌"
        
        status_text = (
            "⚙️ *GitHub Sinxronizatsiya Holati:*\n\n"
            f"📦 *Repozitoriya:* `{repo_status}`\n"
            f"🔑 *Token:* `{masked_token}`\n\n"
            "💡 *O'zgartirish:* `/set_token <token>` yoki `/set_repo <owner/repo>`"
        )
        send_msg(chat_id, status_text, parse_mode="Markdown")
        return

    # --- Seed (Master Parol) va Saltni o'zgartirish ---
    elif text.startswith("/change_seed"):
        call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        if msg_id in sess["msg_ids"]:
            sess["msg_ids"].remove(msg_id)
            
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_msg(chat_id, "❌ Format noto'g'ri!\nFoydalanish: `/change_seed <yangi_seed>`")
            return
            
        new_seed = parts[1]
        meta = load_meta()
        
        # Yangi tuz (salt) yaratish va kalitni qayta shifrlash
        new_salt = os.urandom(16)
        new_key = derive_key(new_seed, new_salt)
        
        meta["salt_seed"] = base64.b64encode(new_salt).decode()
        meta["wrapped_key_seed"] = Fernet(new_key).encrypt(dek).decode()
        
        save_meta(meta)
        sync_github_push()
        
        send_msg(chat_id, "✅ Seed parol va Salt muvaffaqiyatli yangilandi va sinxronizatsiya qilindi! (Matn xavfsizlik uchun chatdan o'chirildi)")
        return

    # --- Tiklash savol-javobi va Saltni o'zgartirish ---
    elif text.startswith("/change_recovery"):
        call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        if msg_id in sess["msg_ids"]:
            sess["msg_ids"].remove(msg_id)
            
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or "|" not in parts[1]:
            send_msg(chat_id, "❌ Format noto'g'ri!\nFoydalanish: `/change_recovery <savol>|<javob>`\nMisol: `/change_recovery Maktabingiz?|7`")
            return
            
        q_a = parts[1].split("|", 1)
        new_question = q_a[0].strip()
        new_answer = q_a[1].strip()
        
        meta = load_meta()
        new_salt = os.urandom(16)
        new_key = derive_key(new_answer, new_salt)
        
        meta["recovery_question"] = new_question
        meta["salt_recovery"] = base64.b64encode(new_salt).decode()
        meta["wrapped_key_recovery"] = Fernet(new_key).encrypt(dek).decode()
        
        save_meta(meta)
        sync_github_push()
        
        send_msg(chat_id, "✅ Tiklash savol-javobi va Salt muvaffaqiyatli yangilandi va sinxronizatsiya qilindi! (Matn xavfsizlik uchun chatdan o'chirildi)")
        return

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
        
    elif text == "🔄 GitHub Sync":
        send_msg(chat_id, "🔄 GitHub bilan sinxronizatsiya boshlandi...")
        pull_ok = sync_github_pull()
        push_ok = sync_github_push()
        
        # Yangi ma'lumotlarni xotiraga yuklash
        accounts = load_accounts(dek)
        
        if pull_ok or push_ok:
            send_main_menu(chat_id, "✅ GitHub bilan sinxronizatsiya yakunlandi!")
        else:
            send_main_menu(chat_id, "❌ Sinxronizatsiya amalga oshmadi. .env dagi GitHub ma'lumotlarini tekshiring.")
            
    elif text == "⚙️ GitHub Status":
        token = get_github_token()
        repo = get_github_repo()
        
        masked_token = "Sozlanmagan ❌"
        if token:
            masked_token = token[:7] + "..." + token[-4:] if len(token) > 10 else "Sozlangan ✅"
            
        repo_status = repo if repo else "Sozlanmagan ❌"
        
        try:
            # Serverdagi git holatini olish
            git_status_res = subprocess.run(["git", "status", "-s"], cwd=REPO_DIR, capture_output=True, text=True)
            git_status = git_status_res.stdout.strip() if git_status_res.stdout.strip() else "Barcha fayllar toza (Synced) ✅"
            
            git_commit_res = subprocess.run(["git", "log", "-1", "--oneline"], cwd=REPO_DIR, capture_output=True, text=True)
            last_commit = git_commit_res.stdout.strip() if git_commit_res.returncode == 0 else "Noma'lum"
        except Exception as e:
            git_status = f"Git status xatosi: {e}"
            last_commit = "Noma'lum"
            
        status_text = (
            "⚙️ *GitHub Sinxronizatsiya Holati:*\n\n"
            f"📦 *Repozitoriya:* `{repo_status}`\n"
            f"🔑 *Token:* `{masked_token}`\n\n"
            f"📊 *Git Status (Server):*\n`{git_status}`\n\n"
            f"📝 *Oxirgi commit (Backup):*\n`{last_commit}`\n\n"
            "💡 *O'zgartirish:* `/set_token <token>` yoki `/set_repo <owner/repo>`"
        )
        send_msg(chat_id, status_text, parse_mode="Markdown")
        
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

# Ishga tushganda eski xabarlarni chatdan o'chirish (Crash'dan himoya)
def startup_clean():
    print("Eski yozishmalarni tozalash...")
    old_data = load_msg_ids()
    for chat_id_str, msg_ids in old_data.items():
        try:
            chat_id = int(chat_id_str)
            for msg_id in reversed(msg_ids):
                call_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        except Exception as e:
            print(f"Eski xabarni o'chirishda xatolik: {e}")
    # Baza tozalangandan so'ng diskdagi faylni ham bo'shatamiz
    save_msg_ids({})

# Polling loop
def main():
    print("Bot ishga tushdi...")
    if not BOT_TOKEN:
        print("XATOLIK: .env faylida BOT_TOKEN topilmadi!")
        return
        
    # Bazani GitHub'dan tortib olish (pull)
    sync_github_pull()
        
    # Eski yozishmalarni tozalash
    startup_clean()
        
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
