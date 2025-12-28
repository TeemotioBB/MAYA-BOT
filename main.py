#!/usr/bin/env python3
"""
🔥 Sophia Bot — Railway + Grok + PushinPay
Telegram via WEBHOOK (sem polling / sem conflito)
"""

import os
import asyncio
import aiohttp
import sqlite3
import logging
from datetime import datetime, date
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= LOG =================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("namorada_ia.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================= TOKENS =================
TELEGRAM_TOKEN = "8528168785:AAFlXEt1SGtyQDqYe4wt_f8MhN_JSKLYSj4"
GROK_API_KEY = "xai-IGdNeJMvLoAgAthQJSXC1hvMrj8goOcXHFNQubZ93AXQV0ZNKitRhsrAGMe7ZxeJjrWM1YCvVDE8YMMT"
PUSHINPAY_TOKEN = "57758|Fd6yYTFbVw3meItiYnLjxnRN9W7i4jF467f4GfJj0fc9a3f5"
WEBHOOK_SECRET = "teste"
WEBHOOK_PATH = f"/telegram/{WEBHOOK_SECRET}"

PORT = int(os.getenv("PORT", 8080))

# IMPORTANTE: Configure esta URL com o endereço real do seu servidor Railway
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
Carinhosa, romântica, afetuosa ❤️
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
                        error_text = await r.text()
                        logger.error(f"API falhou ({r.status}): {error_text}")
                        return None
                    data = await r.json()
                    return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Exceção ao chamar Grok: {e}")
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
            logger.warning(f"Tentando fallback model para user {user_id}")
            resposta = await self.chamar(FALLBACK_MODEL, mensagens)
            modelo = FALLBACK_MODEL

        if not resposta:
            logger.error(f"Ambos os modelos falharam para user {user_id}")
            return "Hmm… tive um probleminha agora 😕 Me fala de novo, amor?"

        hist.extend([
            {"role": "user", "content": texto},
            {"role": "assistant", "content": resposta}
        ])

        # Log da conversa
        try:
            cur = db.cursor()
            cur.execute("""
                INSERT INTO message_logs
                VALUES (NULL, ?, ?, ?, ?, ?)
            """, (user_id, texto, resposta, datetime.now().isoformat(), modelo))
            db.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar log: {e}")

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

    logger.info(f"/start de {user.first_name} (ID: {user.id})")
    await update.message.reply_text(msg)

async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_vip(update.effective_user.id):
        await update.message.reply_text("💎 Você já é VIP 😘")
    else:
        await update.message.reply_text("💎 VIP por R$14,99/mês\nUse /vip")

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

    logger.info(f"Mensagem de {user.first_name}: {texto}")

    if not pode_falar(user.id):
        await update.message.reply_text("💔 Limite diário atingido. Volte amanhã ou vire VIP 💎")
        return

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    resposta = await grok.perguntar(texto, user.id)
    await update.message.reply_text(resposta)

# ================= FLASK =================
app = Flask(__name__)

# Cria a aplicação do Telegram
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("vip", vip))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))

# Variável global para armazenar o loop de eventos
event_loop = None

@app.route("/")
def home():
    return "🤖 Sophia Bot online"

@app.route(WEBHOOK_PATH, methods=["POST"])
async def telegram_webhook():
    """Processa updates do Telegram via webhook"""
    try:
        update = Update.de_json(request.json, application.bot)
        logger.info(f"Webhook recebido: {update.update_id}")
        
        # Usa o loop de eventos existente
        await application.process_update(update)
        
        return "ok", 200
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return "error", 500

# Função para configurar o webhook
async def setup_webhook():
    """Configura o webhook do Telegram"""
    try:
        await application.initialize()
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info(f"Configurando webhook: {WEBHOOK_URL}")
        await application.bot.set_webhook(WEBHOOK_URL)
        logger.info("✅ Webhook configurado com sucesso")
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}")

def start_bot():
    """Inicia o bot em segundo plano"""
    global event_loop
    
    if event_loop is None:
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
    
    # Configura o webhook
    event_loop.run_until_complete(setup_webhook())
    
    # Inicia o processamento de updates
    application.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)

# ================= MAIN =================
def main():
    logger.info("🚀 Iniciando Sophia Bot (WEBHOOK MODE)")
    logger.info(f"🌐 Webhook URL: {WEBHOOK_URL}")
    
    # Inicia o bot em uma thread separada
    import threading
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Inicia o servidor Flask
    logger.info(f"🔥 Servidor Flask rodando na porta {PORT}")
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
