import os
import json
import logging
import datetime
import requests
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
import google.generativeai as genai

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ambil Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Render akan memberikan port otomatis, default biasanya 10000 atau kita set 8080
PORT = int(os.environ.get('PORT', 8080))

# Google Form Config
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeWpnON8JdSw4f1KGApufxOmpnNmlRIPkR6o1gd4jET9XRVPQ/formResponse"

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    print("❌ ERROR: TELEGRAM_TOKEN atau GEMINI_API_KEY belum diisi!")
    exit(1)

# Setup Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})

# PROMPT LENGKAP (Tanpa Pengurangan)
SYSTEM_PROMPT = """
Kamu adalah asisten pencatat keuangan. Tugasmu adalah mengekstrak data menjadi format JSON.
Field JSON yang wajib ada:
- date (YYYY-MM-DD, jika user bilang 'kemarin' sesuaikan dengan tanggal hari ini)
- time (HH:MM, jika tidak ada isi "-")
- merchant (Nama toko/tempat, jika tidak ada isi "-")
- category (Pilih satu: F&B, Groceries, Transport, Shopping, Health, Utilities, Lainnya)
- items (Ringkasan barang yang dibeli)
- payment_method (Tunai/Card/QRIS/Transfer, tebak jika tidak disebut)
- total_amount (Hanya angka integer, tanpa titik/rupiah. Contoh: 50000)

Jika input tidak jelas/bukan pengeluaran, isi semua dengan null.
"""

# Logic Functions
def safe_json_parse(text):
    try:
        return json.loads(text.replace("```json", "").replace("```", "").strip())
    except:
        return {"total_amount": None}

def save_to_form(data):
    try:
        f_data = {
            "entry.784379828": data.get('date', '-'),
            "entry.434918157": data.get('time', '-'),
            "entry.1191905024": data.get('merchant', '-'),
            "entry.1614057050": data.get('category', '-'),
            "entry.2110336352": data.get('items', '-'),
            "entry.654424859": data.get('payment_method', '-'),
            "entry.1595554226": str(data.get('total_amount', 0))
        }
        requests.post(FORM_URL, data=f_data, timeout=10)
        return True
    except Exception as e:
        logger.error(f"Form Error: {e}")
        return False

def analyze_ai(content, is_image=False):
    try:
        if is_image:
            img_data = requests.get(content).content
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                tmp.write(img_data)
                tmp_path = tmp.name
            
            img_file = genai.upload_file(tmp_path)
            res = model.generate_content([SYSTEM_PROMPT, img_file])
            os.remove(tmp_path)
        else:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            res = model.generate_content(f"{SYSTEM_PROMPT}\nWaktu Sekarang: {now}\nData: {content}")
        
        return safe_json_parse(res.text)
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return {"total_amount": None}

# Bot Handlers
def start(update, context):
    update.message.reply_text("✅ Bot Keuangan Aktif di Render! Kirim struk atau teks pengeluaran.")

def handle_msg(update, context):
    try: context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except: pass
    
    msg = update.message.reply_text("⏳ Memproses data...")
    
    res_data = {}
    if update.message.photo:
        file = update.message.photo[-1].get_file()
        res_data = analyze_ai(file.file_path, True)
    elif update.message.text:
        res_data = analyze_ai(update.message.text, False)

    if res_data.get('total_amount'):
        if save_to_form(res_data):
            reply = (f"✅ **Tersimpan ke Google Form!**\n"
                     f"📅 Tanggal: {res_data.get('date')}\n"
                     f"🏪 Toko: {res_data.get('merchant')}\n"
                     f"📂 Kategori: {res_data.get('category')}\n"
                     f"💰 Total: Rp {res_data.get('total_amount', 0):,}")
            msg.edit_text(reply, parse_mode='Markdown')
        else:
            msg.edit_text("⚠️ Data terbaca, tapi gagal simpan ke Google Form.")
    else:
        msg.edit_text("❌ Gagal membaca data pengeluaran.")

# Flask Server
app = Flask(__name__)
bot = Bot(token=TELEGRAM_TOKEN)
dispatcher = Dispatcher(bot, None, workers=4, use_context=True)
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.photo | (Filters.text & ~Filters.command), handle_msg))

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
        return "OK"
    return "Not JSON", 400

@app.route('/')
def index():
    return "Bot is Running on Render"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
