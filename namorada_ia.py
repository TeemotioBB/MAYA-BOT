#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
WEBHOOK + FLASK (CORRETO)
python-telegram-bot v20+
"""

import os
import asyncio
import logging
import aiohttp
import redis
from datetime import datetime, timedelta, date
from flask import Flask, request

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
    PreCheckoutQueryHandler
)

# ================= LOG =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
PORT = int(os.getenv("PORT", 8080))

REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

if not TELEGRAM_TOKEN or not GROK_API_KEY:
    raise RuntimeError("❌ Variáveis de ambiente não configuradas")

# ================= REDIS =================
r = redis.from_url(REDIS_URL, decode_responses=True)

# ================= CONFIG =================
LIMITE_DIARIO = 15
DIAS_VIP = 15
PRECO_VIP_STARS = 250

# ================= APP =================
app = Flask(__name__)
application = Application.builder().token(TELEGRAM_TOKEN).build()

# ================= LOOP ASYNC GLOBAL =================
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ================= VIP =================
def vip_key(uid): return f"vip:{uid}"
def count_key(uid): return f"count:{uid}:{date.today()}"

def is_vip(uid):
    until = r.get(vip_key(uid))
    return bool(until and datetime.fromisoformat(until) > datetime.now())

def today_count(uid):
    return int(r.get(count_key(uid)) or 0)

def increment(uid):
    r.incr(count_key(uid), 1)
    r.expire(count_key(uid), 86400)

# ================= GROK =================
class Grok:
    async def reply(self, text: str) -> str:
        headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "grok-4-fast-reasoning",
            "messages": [
                {"role": "system", "content": "Você é Sophia, carinhosa e romântica."},
                {"role": "user", "content": text}
            ],
            "max_tokens": 150
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.x.ai/v1/chat/completions",
                headers=headers,
                json=payload
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

grok = Grok()

# ================= HANDLER =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    uid = update.effective_user.id
    text = update.message.text.lower()

    logger.info(f"📩 Mensagem recebida: {text}")

    if not is_vip(uid) and "vip" in text:
        await update.message.reply_text(
            "💖 Quer virar VIP? Converse comigo sem limites por 15 dias 😘",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💖 Virar VIP – 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return

    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        await update.message.reply_text(
            "💔 Você atingiu o limite diário. Vire VIP para continuar 💖"
        )
        return

    increment(uid)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    resposta = await grok.reply(update.message.text)
    await update.message.reply_text(resposta)

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.data == "buy_vip":
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title="VIP Sophia 💖",
            description="Conversas ilimitadas por 15 dias",
            payload="vip",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP", PRECO_VIP_STARS)]
        )

# ================= REGISTRO =================
application.add_handler(MessageHandler(filters.TEXT, message_handler))
application.add_handler(CallbackQueryHandler(callback_handler))

# ================= STARTUP =================
async def startup():
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}")
    logger.info("🚀 Webhook configurado e bot iniciado")

loop.run_until_complete(startup())

# ================= WEBHOOK FLASK (SINCRONO) =================
@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.run_coroutine_threadsafe(
        application.process_update(update),
        loop
    )
    return "ok", 200

@app.route("/")
def home():
    return "🤖 Sophia Bot online"

# ================= MAIN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)