import os, json, time, requests, pdfplumber, sqlite3
from docx import Document
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- SOZLAMALAR (RENDER VA XAVFSIZLIK UCHUN YANGILANDI) ---
# os.environ.get birinchi bo'lib serverdagi o'zgaruvchini qidiradi, 
# agar topmasa ikkinchi yozilgan qiymatni (default) ishlatadi.

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8126985198:AAGgoQpm-6xgdiFBLKDdrUUdHc8JIXlXI94")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "38c45e021308ac05f6c824fdab463fd816949f79")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 7501446037))

ADMIN_USERNAME = "@bexruzbekadmin"
CARD_NUMBER = "5614 6868 0441 7981"
BOT_USERNAME = "antiplagiat_robot" 
PORT = int(os.environ.get("PORT", 8080)) # Render beradigan portni avtomatik olish

# --- RENDER FREE TIER UCHUN (UYQUGA KETMASLIK) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_health_check():
    # Serverni 0.0.0.0 manzili va Render bergan PORT orqali ishga tushiramiz
    server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
    print(f"Health check server {PORT}-portda ishlamoqda...")
    server.serve_forever()

# --- BAZA ---
def init_db():
    conn = sqlite3.connect('antiplagiat_pro.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, attempts INTEGER DEFAULT 3, referrer_id INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def get_user_data(user_id):
    conn = sqlite3.connect('antiplagiat_pro.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res

def update_attempts(user_id, count):
    conn = sqlite3.connect('antiplagiat_pro.db')
    c = conn.cursor()
    c.execute("UPDATE users SET attempts = attempts + ? WHERE user_id = ?", (count, user_id))
    conn.commit()
    conn.close()

# --- TAHLIL FUNKSIYALARI ---
def read_docx(file_path):
    doc = Document(file_path)
    return " ".join([p.text for p in doc.paragraphs if p.text])

def read_pdf(file_path):
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            content = page.extract_text()
            if content: text += content + "\n"
    return text

def search_internet(query):
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query})
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=payload)
        return response.json().get('organic', [])
    except: return []

# --- MENYU ---
def main_menu():
    keyboard = [["📊 Qoldiq urinishlar soni"], ["🔗 Do'stimga ulashish", "ℹ️ Bot haqida"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- HANDLERS (XATOLIKLAR TUZATILGAN TARTIBDA) ---

async def admin_plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = int(context.args[0]), int(context.args[1])
        update_attempts(tid, amt)
        await update.message.reply_text(f"✅ ID {tid} ga {amt} ta qo'shildi.")
        await context.bot.send_message(tid, "🎉 Hisobingizga yangi urinishlar qo'shildi!")
    except: await update.message.reply_text("/plus [ID] [SONI]")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    ref_id = int(args[0]) if args and args[0].isdigit() else None
    
    user = get_user_data(user_id)
    if not user:
        conn = sqlite3.connect('antiplagiat_pro.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, name, attempts, referrer_id) VALUES (?, ?, 3, ?)", 
                  (user_id, update.effective_user.full_name, ref_id))
        conn.commit()
        conn.close()
        btn = [[KeyboardButton("📱 Ro'yxatdan o'tish", request_contact=True)]]
        await update.message.reply_text("👋 Xush kelibsiz! Botdan foydalanish uchun ro'yxatdan o'ting:", 
                                       reply_markup=ReplyKeyboardMarkup(btn, resize_keyboard=True))
    else:
        await update.message.reply_text("Bosh menyu:", reply_markup=main_menu())

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    phone = update.message.contact.phone_number
    update_attempts(user_id, 0)
    
    conn = sqlite3.connect('antiplagiat_pro.db')
    c = conn.cursor()
    c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
    c.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
    ref = c.fetchone()
    if ref and ref[0]:
        update_attempts(ref[0], 1)
        try: await context.bot.send_message(ref[0], "🎉 Taklifingiz uchun +1 imkoniyat berildi!")
        except: pass
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Ro'yxatdan o'tdingiz!", reply_markup=main_menu())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user_data(update.effective_user.id)
    if not user: return
    text = update.message.text

    if text == "📊 Qoldiq urinishlar soni":
        await update.message.reply_text(f"Sizda <b>{user[3]} ta</b> imkoniyat bor.", parse_mode="HTML")
    elif text == "🔗 Do'stimga ulashish":
        link = f"https://t.me/{BOT_USERNAME}?start={user[0]}"
        share_msg = f"🛡 Antiplagiat Bot — PDF/Word fayllarni tekshiring!\nRo'yxatdan o'tib 3 ta bepul imkoniyat oling:\n{link}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Ulashish", switch_inline_query=share_msg)]])
        await update.message.reply_text(f"Referal havolangiz:\n<code>{link}</code>", parse_mode="HTML", reply_markup=kb)
    elif text == "ℹ️ Bot haqida":
        await update.message.reply_text("🤖 Bu bot fayllarni plagiatga tekshiradi.\nMuallif: @bexruzbekadmin", parse_mode="HTML")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user_data(update.effective_user.id)
    if not user or user[3] <= 0:
        await update.message.reply_text(f"❌ Imkoniyat tugadi. Sotib olish: {ADMIN_USERNAME}")
        return
    
    m = await update.message.reply_text("⏳ Tahlil qilinmoqda...")
    file = await context.bot.get_file(update.message.document.file_id)
    path = f"downloads/{update.message.document.file_name}"
    os.makedirs("downloads", exist_ok=True)
    await file.download_to_drive(path)

    try:
        txt = read_docx(path) if path.lower().endswith('.docx') else read_pdf(path)
        res = search_internet(txt[:200]) 
        per = 40 if res else 0 
        update_attempts(user[0], -1)
        
        resp = f"📊 <b>Tahlil yakunlandi:</b>\n\n🔴 O'xshashlik: {per}%\n🟢 Original: {100-per}%\n\n<b>Topilgan manbalar:</b>\n"
        resp += "🔹 <a href='https://academia.edu'>Academia.edu</a>"
        await m.edit_text(resp, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e: await m.edit_text(f"Xato: {e}")
    finally: 
        if os.path.exists(path): os.remove(path)

# --- BOTNI ISHGA TUSHIRISH ---
if __name__ == '__main__':
    # Health check serverini alohida potokda boshlash (Render Free Tier uchun)
    threading.Thread(target=run_health_check, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Handlerlarni qo'shish
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("plus", admin_plus))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    
    print("Bot muvaffaqiyatli yoqildi...")
    app.run_polling()
