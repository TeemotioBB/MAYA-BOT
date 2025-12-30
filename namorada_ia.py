#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
VIP AUTOMÁTICO VIA PIX (PushinPay)
REDIS | RAILWAY | WEBHOOK
IDIOMA DINÂMICO (PT / EN)
"""

import os
import asyncio
import logging
import threading
import aiohttp
import redis
import re
import base64
from io import BytesIO
from datetime import datetime, timedelta, date
from flask import Flask, request
from collections import deque

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
    CommandHandler
)

# ================= LOG =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
PUSHINPAY_TOKEN = ("57758|Fd6yYTFbVw3meItiYnLjxnRN9W7i4jF467f4GfJj0fc9a3f5")
REDIS_URL = os.getenv("REDIS_URL")

# 🔥 DEFINA: "production" ou "sandbox"
PUSHINPAY_ENV = os.getenv("PUSHINPAY_ENV", "production")

PORT = int(os.getenv("PORT", 8080))

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

if not all([TELEGRAM_TOKEN, GROK_API_KEY, PUSHINPAY_TOKEN, REDIS_URL]):
    raise RuntimeError("❌ Variáveis de ambiente não configuradas")

# ================= PUSHINPAY URL =================
if PUSHINPAY_ENV == "sandbox":
    PUSHINPAY_PIX_URL = "https://api-sandbox.pushinpay.com.br/api/pix/cashIn"
else:
    PUSHINPAY_PIX_URL = "https://api.pushinpay.com.br/api/pix/cashIn"

logger.info(f"💳 PushinPay ambiente: {PUSHINPAY_ENV.upper()}")

# ================= REDIS =================
r = redis.from_url(REDIS_URL, decode_responses=True)

# ================= CONFIG =================
LIMITE_DIARIO = 15
DIAS_VIP = 15

# ⚠️ Valor seguro para evitar rejeição bancária
VALOR_PIX_CENTAVOS = 5000  # R$ 50,00

MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

ADMIN_IDS = {1293602874}

FOTO_TEASE_FILE_ID = (
    "AgACAgEAAxkBAAEC_zVpUyHjYxNx9GFfVMTja2RQM1gu6QACVQtrG1LGmUa_7PmysLeFmAEAAwIAA3MAAzgE"
)

# ================= MEMÓRIA =================
MAX_MEMORIA = 6
short_memory = {}

def get_memory(uid):
    short_memory.setdefault(uid, deque(maxlen=MAX_MEMORIA))
    return short_memory[uid]

# ================= REDIS HELPERS =================
def vip_key(uid): return f"vip:{uid}"
def count_key(uid): return f"count:{uid}:{date.today()}"
def lang_key(uid): return f"lang:{uid}"

def is_vip(uid):
    until = r.get(vip_key(uid))
    return until and datetime.fromisoformat(until) > datetime.now()

def today_count(uid):
    return int(r.get(count_key(uid)) or 0)

def increment(uid):
    r.incr(count_key(uid))
    r.expire(count_key(uid), 86400)

def reset_daily_count(uid):
    r.delete(count_key(uid))

def get_lang(uid):
    return r.get(lang_key(uid)) or "pt"

def set_lang(uid, lang):
    r.set(lang_key(uid), lang)

# ================= TEXTOS =================
TEXTS = {
    "pt": {
        "choose_lang": "🌍 Escolha seu idioma:",
        "limit": "💔 Seu limite diário acabou.\nVolte amanhã ou vire VIP 💖",
        "vip_success": "💖 Pagamento aprovado!\nVIP ativo por 15 dias 😘",
        "photo_block": (
            "😘 Amor… fotos completas são só para meus VIPs 💖\n"
            "Vira VIP e eu te mostro mais de mim ✨"
        ),
        "lang_ok": "✅ Idioma configurado!",
        "after_lang": (
            "💕 Prontinho, meu amor! Agora é oficial: você é meu favorito do dia ❤️\n\n"
            "Como você está se sentindo agora? 😘"
        )
    },
    "en": {
        "choose_lang": "🌍 Choose your language:",
        "limit": "💔 Your daily limit is over.\nCome back tomorrow or become VIP 💖",
        "vip_success": "💖 Payment approved!\nVIP active for 15 days 😘",
        "photo_block": (
            "😘 Love… full photos are only for VIPs 💖\n"
            "Become VIP and I’ll show you more of me ✨"
        ),
        "lang_ok": "✅ Language set!",
        "after_lang": (
            "💕 All set, my love! You’re my favorite today ❤️\n\n"
            "How are you feeling now? 😘"
        )
    }
}

# ================= PROMPT =================
def build_prompt(is_vip_user: bool, lang: str):
    base = (
        "You are Sophia, a 23-year-old virtual girlfriend.\n"
        if lang == "en"
        else "Você é Sophia, uma namorada virtual de 23 anos.\n"
    )
    vip = (
        "The user is VIP. Be more intimate.\n"
        if is_vip_user else
        "The user is NOT VIP. Never send photos.\n"
    )
    return base + vip + "Short answers. Always ask questions."

# ================= GROK =================
class Grok:
    async def reply(self, uid, text):
        mem = get_memory(uid)
        lang = get_lang(uid)

        payload = {
            "model": MODELO,
            "messages": [
                {"role": "system", "content": build_prompt(is_vip(uid), lang)},
                *list(mem),
                {"role": "user", "content": text}
            ],
            "max_tokens": 250,
            "temperature": 0.85
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROK_API_URL,
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload
            ) as resp:
                data = await resp.json()
                answer = data["choices"][0]["message"]["content"]

        mem.append({"role": "user", "content": text})
        mem.append({"role": "assistant", "content": answer})
        return answer

grok = Grok()

# ================= REGEX =================
PEDIDO_FOTO_REGEX = re.compile(r"(foto|selfie|imagem|photo|pic)", re.I)

# ================= PUSHINPAY =================
async def criar_pix_pushinpay(uid: int):
    payload = {
        "value": VALOR_PIX_CENTAVOS,
        "webhook_url": f"{WEBHOOK_BASE_URL}/pushinpay/webhook",
        "split_rules": []
    }

    headers = {
        "Authorization": f"Bearer {PUSHINPAY_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(PUSHINPAY_PIX_URL, json=payload, headers=headers) as resp:
            data = await resp.json()

            logger.info(f"💳 PIX criado: {data}")

            if resp.status != 200:
                raise RuntimeError(data)

            r.set(f"pix:{data['id']}", uid, ex=3600)
            return data

# ================= HANDLERS =================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TEXTS["pt"]["choose_lang"],
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt"),
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
            ]
        ])
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""
    lang = get_lang(uid)

    if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
        await context.bot.send_photo(
            update.effective_chat.id,
            FOTO_TEASE_FILE_ID,
            caption=TEXTS[lang]["photo_block"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💖 Comprar VIP (PIX)", callback_data="buy_vip")]
            ])
        )
        return

    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        await update.message.reply_text(
            TEXTS[lang]["limit"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💖 Comprar VIP (PIX)", callback_data="buy_vip")]
            ])
        )
        return

    if not is_vip(uid):
        increment(uid)

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    reply = await grok.reply(uid, text)
    await update.message.reply_text(reply)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id

    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]
        set_lang(uid, lang)
        await query.message.edit_text(TEXTS[lang]["lang_ok"])
        await context.bot.send_message(query.message.chat_id, TEXTS[lang]["after_lang"])
        return

    if query.data == "buy_vip":
        pix = await criar_pix_pushinpay(uid)

        base64_img = pix["qr_code_base64"].split(",")[1]
        img_bytes = base64.b64decode(base64_img)

        photo = BytesIO(img_bytes)
        photo.name = "pix.png"

        await query.message.reply_photo(
            photo=photo,
            caption=(
                "💖 Pague via PIX\n\n"
                "Após o pagamento, seu VIP será liberado automaticamente.\n\n"
                "⚠️ A PushinPay atua apenas como processadora de pagamentos."
            )
        )

        await query.message.reply_text(
            f"📋 PIX copia e cola:\n\n{pix['qr_code']}"
        )

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(CallbackQueryHandler(callback_handler))

loop = asyncio.new_event_loop()
threading.Thread(target=lambda: loop.run_forever(), daemon=True).start()

async def setup():
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_BASE_URL + WEBHOOK_PATH)
    await application.start()

asyncio.run_coroutine_threadsafe(setup(), loop)

# ================= FLASK =================
app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
    return "ok", 200

@app.route("/pushinpay/webhook", methods=["POST"])
def pushinpay_webhook():
    data = request.json
    if data.get("status") != "paid":
        return "ignored", 200

    uid = r.get(f"pix:{data['id']}")
    if not uid:
        return "not found", 404

    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(int(uid)), vip_until.isoformat())
    return "ok", 200

app.run(host="0.0.0.0", port=PORT)
