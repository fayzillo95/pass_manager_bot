# 🚀 SecVault Botni Render'ga Joylash va "Uyg'oq" Saqlash Rejasi

Render'ning bepul tarifi (Free tier) foydalanilmaganda (inaktiv bo'lganda) 15 daqiqada uyqu rejimiga o'tadi. Buni oldini olish va ma'lumotlarni o'chib ketishdan asrash uchun quyidagi reja asosida sozlashlarni amalga oshiramiz.

---

## 🛠️ 1. Texnik Sozlamalar Rejasi

### A. HTTP Server Qo'shish (Portni Tinglash)
Render bepul xizmat sifatida ishlashi uchun u portni tinglashi shart.
* **Yechim:** Python'ning standart `http.server` kutubxonasi yordamida kichik HTTP server yaratamiz va uni alohida oqimda (thread) Render ajratgan portda (`PORT` muhit o'zgaruvchisi, odatda 80 or 8080) ishga tushiramiz.

### B. Ichki Self-Ping Cron (Uyg'oq saqlash)
* **Yechim:** Dastur ichida har 10 daqiqada ishlaydigan fonda yana bir oqim (thread) ochamiz. U `.env` faylida ko'rsatilgan botning o'z havolasiga (`https://app-name.onrender.com/health`) HTTP so'rov yuborib turadi. Bu Render tizimini doimo faol va "uyg'oq" saqlaydi.

---

## ⚠️ 2. Render Xotira Cheklovi (Persistent Storage)
Render'ning bepul tarifida disk **ephemeral** (vaqtinchalik) hisoblanadi. Ya'ni bot o'chib yonganda yoki deploy bo'lganda barcha lokal fayllar (`accounts.enc`, `vault.meta.json`, `msg_ids.json`) **butunlay o'chib ketadi**.

### persistentlik uchun yechim (GitHub Sync):
* `.env` fayliga **`GITHUB_TOKEN`** (Personal Access Token) va **`GITHUB_REPO`** (masalan: `fayzillo95/pass_manager_bot`) qo'shamiz.
* Bot ishga tushganda GitHub API orqali `accounts.enc` va `vault.meta.json` fayllarini yuklab oladi (pull/fetch).
* Har safar yangi parol qo'shilganda yoki o'chirilganda, bot GitHub API yordamida yangilangan fayllarni avtomatik ravishda GitHub private repozitoriyasiga **commit va push** qilib qo'yadi.

---

## 📝 3. `.env` Fayliga Qo'shiladigan Yangi Qiymatlar

```env
# Render'dagi botingizning umumiy havolasi (Uyg'oq saqlash uchun)
APP_URL=https://secvault-bot.onrender.com

# GitHub orqali bazani sinxronizatsiya qilish uchun
GITHUB_TOKEN=ghp_your_github_personal_access_token
GITHUB_REPO=fayzillo95/pass_manager_bot
```

---

## 📋 4. Deploy Bosqichlari
1. Dastur kodini o'zgartirish (HTTP server, self-ping va GitHub API integratsiyasini qo'shish).
2. O'zgarishlarni GitHub'ga push qilish.
3. Render.com saytida yangi **Web Service** ochish va ushbu GitHub repoga bog'lash.
4. Render'da `Environment Variables` (muhit o'zgaruvchilari) bo'limida `.env` dagi ma'lumotlarni kiritish.
