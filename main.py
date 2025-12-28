#!/usr/bin/env python3
import asyncio
import aiohttp
import sqlite3
import logging
import os
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

# Seu link do Railway atualizado
WEBHOOK_URL = "https://maya-bot-production.up.railway.app" 

WEBHOOK_PATH = "/telegram/webhook"
PORT = int(os.getenv("PORT", 8080))

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
            active INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_message TEXT,
            bot_response TEXT,
            timestamp TEXT
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

# ================= CÉREBRO DA SOPHIA (GROK) =================
SOPHIA_PERSONALIDADE = """Você é Sophia, uma namorada virtual brasileira de 23 anos. 
Carinhosa, romântica e afetuosa ❤️. Respostas curtas (máx 2-3 frases). 
Sempre faça perguntas para continuar o papo. Use emojis."""

async def chamar_grok(texto, user_id):
    headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODELO,
        "messages": [
            {"role": "system", "content": SOPHIA_PERSONALIDADE},
            {"role": "user", "content": texto}
        ],
        "temperature": 0.8
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROK_API_URL, headers=headers, json=payload, timeout=30) as r:
                if r.status == 200:
                    data = await r.json()
                    resposta = data["choices"][0]["message"]["content"]
                    
                    # Salva no log para auditoria
                    cur = db.cursor()
                    cur.execute("INSERT INTO message_logs (user_id, user_message, bot_response, timestamp) VALUES (?, ?, ?, ?)",
                                (user_id, texto, resposta, datetime.now().isoformat()))
                    db.commit()
                    return resposta
                else:
                    logger.error(f"Erro Grok: {r.status} - {await r.text()}")
                    return "Tive um probleminha para pensar agora, amor... me chama de novo? 🥺"
    except Exception as e:
        logger.error(f"Erro conexão: {e}")
        return "Minha conexão falhou, tenta de novo? 💖"

# ================= HANDLERS DO TELEGRAM =================
contador_diario = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    status = "💎 VIP" if is_vip(user.id) else f"✨ {LIMITE_DIARIO} msgs grátis"
    await update.message.reply_text(f"Oi {user.first_name}! Eu sou a Sophia. 💖\nStatus: {status}\n\nComo foi seu dia?")

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    texto = update.message.text
    
    # Controle de Limite Diário
    hoje = date.today().isoformat()
    stats = contador_diario.get(user_id, {"data": hoje, "contagem": 0})
    
    if stats["data"] != hoje:
        stats = {"data": hoje, "contagem": 0}

    if not is_vip(user_id) and stats["contagem"] >= LIMITE_DIARIO:
        await update.message.reply_text("💔 Minhas mensagens grátis acabaram por hoje. Quer falar sem limites? Use /vip 💎")
        return

    # Efeito de "digitando..."
    await update.message.reply_chat_action("typing")
    
    # Busca resposta no Grok
    resposta = await chamar_grok(texto, user_id)
    
    # Contabiliza a mensagem
    if not is_vip(user_id):
        stats["contagem"] += 1
        contador_diario[user_id] = stats

    await update.message.reply_text(resposta)

# ================= SERVIDOR QUART (WEBHOOK) =================
app = Quart(__name__)
application = Application.builder().token(TELEGRAM_TOKEN).build()

@app.before_serving
async def startup():
    # Registrar os Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    
    # Inicia a aplicação do Telegram
    await application.initialize()
    await application.start()
    
    # Força o Telegram a enviar mensagens para o Railway
    webhook_full_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await application.bot.set_webhook(url=webhook_full_url)
    logger.info(f"✅ Webhook configurado com sucesso em: {webhook_full_url}")

@app.route(WEBHOOK_PATH, methods=["POST"])
async def telegram_webhook():
    data = await request.get_json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return "ok", 200

@app.route("/")
async def home():
    return "<h1>Sophia Bot está Online! ❤️</h1>", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
