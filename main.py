#!/usr/bin/env python3
"""
🔥 Sophia Bot — Railway + Grok + PushinPay
Telegram via WEBHOOK (estável, sem polling, sem erro de loop)
"""

import os
import asyncio
import aiohttp
import sqlite3
import logging
from datetime import datetime, date
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.constants import ChatAction

# ================= LOG =================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= TOKENS =================
TELEGRAM_TOKEN = "8528168785:AAFlXEt1SGtyQDqYe4wt_f8MhN_JSKLYSj4"
GROK_API_KEY = "xai-IGdNeJMvLoAgAthQJSXC1hvMrj8goOcXHFNQubZ93AXQV0ZNKitRhsrAGMe7ZxeJjrWM1YCvVDE8YMMT"
PUSHINPAY_TOKEN = "57758|Fd6yYTFbVw3meItiYnLjxnRN9W7i4jF467f4GfJj0fc9a3f5"

WEBHOOK_SECRET = "teste"
WEBHOOK_PATH = f"/telegram/{WEBHOOK_SECRET}"

PORT = int(os.getenv("PORT", 8080))

WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    f"https://maya-bot-production.up.railway.app{WEBHOOK_PATH}"
)

# ================= CONFIG =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
PRIMARY_MODEL = "grok-4-fast-reasoning"
FALLBACK_MODEL = "grok-beta"

VIP_PRICE_CENTS = 1499
LIMITE_DIARIO = 15

# ================= DB =================
def get_db():
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
    return conn

db = get_db()

def is_vip(user_id: int) -> bool:
    cur = db.cursor()
    cur.execute("SELECT active FROM vip_users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return bool(row and row[0] == 1)

# ================= GROK =================
SOPHIA_PERSONALIDADE = """Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica e afetuosa ❤️
Respostas curtas e naturais (máx 2–3 frases)
Sempre faça perguntas
Use emojis ocasionalmente 💖
"""

class GrokCerebro:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }
        self.historico = {}

    async def chamar(self, modelo, mensagens):
        payload = {
            "model": modelo,
            "messages": mensagens,
            "max_tokens": 250,
            "temperature": 0.85
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROK_API_URL,
                    headers=self.headers,
                    json=payload,
                    timeout=30
                ) as r:
                    if r.status != 200:
                        logger.error(await r.text())
                        return None
                    data = await r.json()
                    return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Erro Grok: {e}")
            return None

    async def perguntar(self, texto, user_id):
        hist = self.historico.setdefault(user_id, [])

        mensagens = [
            {"role": "system", "content": SOPHIA_PERSONALIDADE},
            *hist[-6:],
            {"role": "user", "content": texto}
        ]

        resposta = await self.chamar(PRIMARY_MODEL, mensagens)
        modelo = PRIMARY_MODEL

        if not resposta:
            resposta = await self.chamar(FALLBACK_MODEL, mensagens)
            modelo = FALLBACK_MODEL

        if not resposta:
            return "Hmm… tive um probleminha agora 😕 Me fala de novo, amor?"

        hist.extend([
            {"role": "user", "content": texto},
            {"role": "assistant", "content": resposta}
        ])

        cur = db.cursor()
        cur.execute("""
            INSERT INTO message_logs
            VALUES (NULL, ?, ?, ?, ?, ?)
        """, (user_id, texto, resposta, datetime.now().isoformat(), modelo))
        db.commit()

        return resposta

grok = GrokCerebro()

# ================= TELEGRAM =================
contador = {}
datas = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contador[user.id] = 0
    datas[user.id] = date.today()

    msg = f"Oi {user.first_name}! 💖\n\n"
    msg += "💎 VIP ilimitado!" if is_vip(user.id) else f"✨ Você tem {LIMITE_DIARIO} mensagens hoje"
    await update.message.reply_text(msg)

async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_vip(update.effective_user.id):
        await update.message.reply_text("💎 Você já é VIP 😘")
    else:
        await update.message.reply_text("💎 VIP por R$14,99/mês")

def pode_falar(user_id):
    hoje = date.today()
    if datas.get(user_id) != hoje:
        datas[user_id] = hoje
        contador[user_id] = 0

    if is_vip(user_id):
        return True

    contador[user_id] += 1
    return contador[user_id] <= LIMITE_DIARIO

async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    texto = update.message.text.strip()

    if not pode_falar(user.id):
        await update.message.reply_text("💔 Limite diário atingido. Volte amanhã ou vire VIP 💎")
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    resposta = await grok.perguntar(texto, user.id)
    await update.message.reply_text(resposta)

# ================= FLASK =================
app = Flask(__name__)

application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("vip", vip))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))

@app.route("/")
def home():
    return "🤖 Sophia Bot online"

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.json, application.bot)
    application.create_task(application.process_update(update))
    return "ok", 200

# ================= MAIN =================
async def setup_webhook():
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(WEBHOOK_URL)

def main():
    logger.info("🚀 Iniciando Sophia Bot (WEBHOOK)")
    logger.info(f"🌐 Webhook: {WEBHOOK_URL}")
    asyncio.run(setup_webhook())
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
