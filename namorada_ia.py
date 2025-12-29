#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
WEBHOOK FIXO | LOOP ASYNC CORRETO
"""

import os
import asyncio
import logging
import threading
import aiohttp
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.constants import ChatAction

# ================= LOG =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ================= TOKENS =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
PORT = int(os.getenv("PORT", 8080))

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

# ================= GROK =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-4-fast-reasoning"

SOPHIA_PROMPT = """
Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica e afetuosa ❤️
Respostas curtas (2–3 frases).
Sempre faça perguntas.
Use emojis ocasionalmente 💖
"""

class Grok:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }

    async def responder(self, texto: str) -> str:
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SOPHIA_PROMPT},
                {"role": "user", "content": texto}
            ],
            "max_tokens": 250,
            "temperature": 0.85
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROK_API_URL,
                headers=self.headers,
                json=payload,
                timeout=30
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

grok = Grok()

# ================= TELEGRAM HANDLER =================
async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    resposta = await grok.responder(texto)
    await update.message.reply_text(resposta)

# ================= APP TELEGRAM =================
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem)
)

# ================= LOOP ASYNC BACKGROUND =================
loop = asyncio.new_event_loop()

def start_async_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_async_loop, daemon=True).start()

async def setup_telegram():
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(
        f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}",
        drop_pending_updates=True
    )
    await application.start()
    logger.info("🤖 Telegram Application iniciado")

asyncio.run_coroutine_threadsafe(setup_telegram(), loop)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Sophia Bot online"

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.run_coroutine_threadsafe(
        application.process_update(update),
        loop
    )
    return "ok", 200

# ================= MAIN =================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Sophia Bot (LOOP CORRETO)")
    app.run(host="0.0.0.0", port=PORT)
