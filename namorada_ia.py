#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
WEBHOOK FIXO NO CÓDIGO | RESET TOTAL
"""

import os
import asyncio
import logging
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

# 🔥 WEBHOOK FIXO (IGNORA RAILWAY)
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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROK_API_URL,
                    headers=self.headers,
                    json=payload,
                    timeout=30
                ) as resp:

                    if resp.status != 200:
                        logger.error(await resp.text())
                        return "Hmm… algo deu errado 😕"

                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"Grok error: {e}")
            return "Tive um errinho agora 😕 Me fala de novo, amor?"

grok = Grok()

# ================= TELEGRAM =================
async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    resposta = await grok.responder(texto)
    await update.message.reply_text(resposta)

# ================= FLASK + WEBHOOK =================
app = Flask(__name__)

application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem)
)

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

    webhook_final = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"

    # 🔥 RESET TOTAL (IGNORA CACHE / VARIÁVEL)
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(
        webhook_final,
        drop_pending_updates=True
    )

    logger.info(f"🌐 Webhook FIXO FINAL: {webhook_final}")

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("❌ TELEGRAM_TOKEN não definido")
    if not GROK_API_KEY:
        raise RuntimeError("❌ GROK_API_KEY não definido")

    logger.info("🚀 Iniciando Sophia Bot (WEBHOOK FIXO)")

    asyncio.run(setup_webhook())
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
