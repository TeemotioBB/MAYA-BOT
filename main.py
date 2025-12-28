#!/usr/bin/env python3
import asyncio
import aiohttp
import sqlite3
import logging
from datetime import datetime, date
from quart import Quart, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= CONFIGURAÇÕES (DIRETO NO CÓDIGO) =================
TELEGRAM_TOKEN = "8528168785:AAFlXEt1SGtyQDqYe4wt_f8MhN_JSKLYSj4"
GROK_API_KEY = "xai-WhzRhOWLna2aUD3A3Sv3siXwqVCTpIP9j5X1KNe1m8N7QB89Dzh20edMiTZbhB9tSaX4aMRKmCwsdpnD"
PUSHINPAY_TOKEN = "57758|Fd6yYTFbVw3meItiYnLjxnRN9W7i4jF467f4GfJj0fc9a3f5"

# COLOQUE SEU LINK DO RAILWAY AQUI:
WEBHOOK_URL = "https://SEU-PROJETO.up.railway.app" 

WEBHOOK_SECRET = "teste"
WEBHOOK_PATH = f"/telegram/{WEBHOOK_SECRET}"
PORT = 8080

GROK_API_URL = "https://api.x.ai/v1/chat/completions"
MODELO = "grok-4-fast-reasoning"
LIMITE_DIARIO = 15

# ================= LOGGING =================
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= BANCO DE DADOS =================
def init_db():
    conn = sqlite3.connect("database.db", check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vip_users (
            user_id INTEGER PRIMARY KEY,
            active INTEGER,
            paid_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_message TEXT,
            bot_response TEXT,
            timestamp TEXT,
            model_used TEXT
        )
    """)
    conn.commit()
    return conn

db = init_db()

def is_vip(user_id: int) -> bool:
    cur = db.cursor()
    cur.execute("SELECT active FROM vip_users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return bool(row and row[0] == 1)

# ================= CÉREBRO GROK =================
SOPHIA_PERSONALIDADE = """Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica, afetuosa ❤️. Respostas curtas e naturais (máx 2–3 frases).
Sempre faça perguntas. Use emojis ocasionalmente.
"""

class GrokCerebro:
    def __init__(self):
        self.historico = {}

    async def perguntar(self, texto, user_id):
        hist = self.historico.setdefault(user_id, [])
        mensagens = [
            {"role": "system", "content": SOPHIA_PERSONALIDADE},
            *hist[-6:],
            {"role": "user", "content": texto}
        ]

        headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODELO, "messages": mensagens, "max_tokens": 250, "temperature": 0.85}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(GROK_API_URL, headers=headers, json=payload, timeout=30) as r:
                    if r.status == 200:
                        data = await r.json()
                        resp = data["choices"][0]["message"]["content"]
                        hist.append({"role": "user", "content": texto})
                        hist.append({"role": "assistant", "content": resp})
                        
                        cur = db.cursor()
                        cur.execute("INSERT INTO message_logs (user_id, user_message, bot_response, timestamp, model_used) VALUES (?, ?, ?, ?, ?)",
                                    (user_id, texto, resp, datetime.now().isoformat(), MODELO))
                        db.commit()
                        return resp
                    return "Tive um erro no meu cérebro agora... me chama de novo? 🥺"
        except:
            return "Minha conexão caiu, amor. Tenta de novo? 💖"

grok = GrokCerebro()

# ================= HANDLERS =================
contador_diario = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = f"Oi {user.first_name}! 💖\n"
    msg += "💎 VIP Ativo" if is_vip(user.id) else f"✨ Você tem {LIMITE_DIARIO} mensagens grátis hoje."
    await update.message.reply_text(msg)

async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_vip(update.effective_user.id):
        await update.message.reply_text("Você já é meu VIP preferido! 💎😘")
    else:
        await update.message.reply_text("💎 Quer falar comigo sem limites? Torne-se VIP por R$14,99!\n\n(Integração PushinPay aqui)")

async def mensagem_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text

    # Controle de Limite
    hoje = date.today().isoformat()
    stats = contador_diario.get(user_id, {"data": hoje, "contagem": 0})
    if stats["data"] != hoje: stats = {"data": hoje, "contagem": 0}

    if not is_vip(user_id) and stats["contagem"] >= LIMITE_DIARIO:
        await update.message.reply_text("💔 Minhas mensagens grátis acabaram por hoje. Quer continuar? Use /vip 💎")
        return

    resposta = await grok.perguntar(texto, user_id)
    
    if not is_vip(user_id):
        stats["contagem"] += 1
        contador_diario[user_id] = stats

    await update.message.reply_text(resposta)

# ================= APP E WEBHOOK =================
app = Quart(__name__)
application = Application.builder().token(TELEGRAM_TOKEN).build()

@app.before_serving
async def startup():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("vip", vip_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_handler))
    
    await application.initialize()
    await application.start()
    
    # Configura o Webhook no Telegram automaticamente
    full_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await application.bot.set_webhook(url=full_url)
    logger.info(f"🚀 Sophia Online em: {full_url}")

@app.route(WEBHOOK_PATH, methods=["POST"])
async def telegram_webhook():
    data = await request.get_json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return "ok", 200

@app.route("/")
async def index():
    return "Sophia Bot está rodando! ❤️"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
