# 🔐 Telegram Pass Manager Bot

Ushbu bot shaxsiy parollaringiz va Gmail hisoblaringizni xavfsiz saqlash uchun yaratilgan. Barcha ma'lumotlar PBKDF2 shifrlash va tasodifiy tuz (salt) yordamida shifrlangan binary ko'rinishida `vault.bin` fayliga saqlanadi.

Dastur **faqat standart Python kutubxonalaridan** foydalangan holda yozilgan, shuning uchun hech qanday qo'shimcha plagin yoki paket o'rnatish shart emas (`pip install` kerak emas).

---

## ⚙️ Sozlash (Configuration)

Loyiha papkasidagi `.env` faylini oching va quyidagi ma'lumotlarni kiriting:

1. **`BOT_TOKEN`**: @BotFather orqali yaratilgan botingizning tokeni.
2. **`ALLOWED_USER_ID`**: Sizning shaxsiy Telegram User ID'ingiz. Bot boshqa hech kimga javob bermasligi va ma'lumotlarni begonalardan himoya qilish uchun bu **shart**.
   * *O'z ID'ingizni bilish uchun Telegram'da `@userinfobot` botiga biror xabar yuboring, u sizga ID raqamingizni ko'rsatadi.*

---

## 🚀 Botni ishga tushirish

Terminal orqali loyiha papkasiga o'ting va botni ishga tushiring:

```bash
python3 main.py
```

---

## 📱 Bot buyruqlari va foydalanish

Botingizga o'ting va quyidagi buyruqlarni yuboring:

### 1. Akkaunt qo'shish (`/add`)
Format: `/add <gmail> <parol> <kalit>`
* **Gmail:** Akkaunt pochtasi.
* **Parol:** Akkaunt paroli.
* **Kalit:** Akkauntni shifrlash uchun ishlatiladigan ixtiyoriy seed/parol (masalan: `meningmaxfiykodim`).
* **Misol:**
  `/add test@gmail.com parolim123 maxfiykalit`

> 💡 *Eslatma: Har bir akkaunt uchun har xil yoki bir xil kalit (seed) ishlatishingiz mumkin.*

### 2. Akkauntlarni ko'rish (`/get`)
Format: `/get <kalit>`
* Kiritilgan kalit (seed) yordamida shifrlangan bazadagi ma'lumotlar tekshiriladi va faqat shu kalit bilan shifrlangan akkauntlar yechilib, ko'rsatiladi.
* **Misol:**
  `/get maxfiykalit`

### 3. Ma'lumotlarni o'chirish (`/clear`)
Bazada saqlangan barcha ma'lumotlarni to'liq o'chirib tashlaydi.
* **Buyruq:** `/clear`
