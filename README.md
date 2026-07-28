# 🔐 SecVault Telegram Bot

Ushbu bot shaxsiy parollaringiz va Gmail hisoblaringizni xavfsiz saqlash uchun yaratilgan. Barcha ma'lumotlar PBKDF2 va Fernet (AES-128) algoritmlari yordamida shifrlangan binary ko'rinishida `accounts.enc` faylida saqlanadi.

Dastur **faqat standart Python kutubxonalari va `cryptography`** paketidan foydalanadi.

---

## ⚙️ Sozlash (Configuration)

Loyiha papkasidagi `.env` faylini oching va quyidagi ma'lumotlarni kiriting (Render'ga deploy qilganda ularni `Environment Variables` bo'limiga kiritasiz):

1. **`BOT_TOKEN`**: @BotFather orqali yaratilgan botingizning tokeni.
2. **`ALLOWED_USER_ID`**: Sizning shaxsiy Telegram User ID'ingiz. Bot faqat sizga javob berishi uchun bu **shart**.
3. **`GITHUB_TOKEN`**: GitHub Personal Access Token (PAT).
4. **`GITHUB_REPO`**: GitHub repozitoriyangiz nomi (masalan: `fayzillo95/pass_manager_bot`).

---

## 🚀 Botni ishga tushirish

Terminal orqali loyiha papkasiga o'ting va botni ishga tushiring:

```bash
python3 main.py
```

---

## 📱 Bot buyruqlari va menyudan foydalanish

Botga kirib `/start` yozganingizdan keyin u qulflangan holatda bo'ladi. Uni **Seed** parolingiz bilan ochasiz (Unlock).

### 🖥️ Tugmalar Menyusi:
* **📋 To'liq list:** Barcha akkauntlar va parollarni ochiq ko'rinishda chiqaradi.
* **📧 Emaillar:** Faqat emaillar ro'yxatini ko'rsatadi.
* **👁️ Masked list:** Emaillar va parollarni yashirin (masked) formatda ko'rsatadi.
* **➕ Yangi qo'shish:** Akkaunt qo'shish jarayonini boshlaydi.
* **✏️ Tahrirlash:** Mavjud akkaunt parolini tahrirlaydi.
* **❌ O'chirish:** Akkauntni bazadan o'chiradi.
* **🔄 GitHub Sync:** GitHub'dan yangi parollarni tortadi (`pull`) va local o'zgarishlarni GitHub'ga yuklaydi (`push`).
* **🧹 Chatni tozalash:** Chatdagi barcha ochiq parollar yozishmalarini Telegram'dan o'chirib tozalaydi.
* **🔒 Qulflash:** Seansni yopadi va chatni avtomatik tozalaydi.

---

### 🔑 Maxfiy Sozlamalar Buyruqlari (Commands):

Ushbu buyruqlar faqat botga **kirilgan (unlocked)** holatda ishlaydi:

#### 1. GitHub Sozlamalari:
* `/set_token <token>` — GitHub Personal Access Tokenni o'rnatadi. (Maxfiylik uchun yuborgan xabaringiz chatdan o'chiriladi).
* `/set_repo <owner/repo>` — Ma'lumotlar saqlanadigan GitHub reponi o'rnatadi.
* `/github_status` — Hozirgi ulanish va sozlamalar holatini ko'rsatadi.

#### 2. Seed va Salt Yangilash:
* `/change_seed <yangi_seed>` — Master parolingizni (Seed) o'zgartiradi va **yangi tasodifiy Tuz (Salt) yaratib** barcha ma'lumotlarni qayta shifrlaydi. (Yuborgan xabaringiz chatdan o'chiriladi).
* `/change_recovery <savol>|<javob>` — Tiklash savoli va javobini o'zgartiradi hamda **yangi tasodifiy Tiklash Tuzi (Recovery Salt) yaratib** kalitlarni qayta shifrlaydi. (Yuborgan xabaringiz chatdan o'chiriladi).
