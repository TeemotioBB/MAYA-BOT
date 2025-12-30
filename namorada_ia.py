#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
VIP | TELEGRAM STARS | REDIS | RAILWAY
IDIOMA DINÂMICO (PT / EN)
"""

import os
import asyncio
import logging
import threading
import aiohttp
import redis
import re
from datetime import datetime, timedelta, date
from flask import Flask, request
from collections import deque

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
    PreCheckoutQueryHandler,
    CommandHandler
)

# ================= LOG =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"
PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_TOKEN or not GROK_API_KEY:
    raise RuntimeError("❌ Tokens não configurados")

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

# ================= REDIS =================
r = redis.from_url(REDIS_URL, decode_responses=True)

# ================= CONFIG =================
LIMITE_DIARIO = 15
DIAS_VIP = 15
PRECO_VIP_STARS = 250

MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= FOTO TEASER =================
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

def get_lang(uid):
    return r.get(lang_key(uid)) or "pt"

def set_lang(uid, lang):
    r.set(lang_key(uid), lang)

# ================= TEXTOS =================
TEXTS = {
    "pt": {
        "choose_lang": "🌍 Escolha seu idioma:",
        "limit": "💔 Seu limite diário acabou.\nVolte amanhã ou vire VIP 💖",
        "vip_pitch": "💖 Quer virar VIP?\nConversas ilimitadas por 15 dias 💬",
        "vip_success": "💖 Pagamento aprovado!\nVIP ativo por 15 dias 😘",
        "photo_block": (
            "😘 Amor… fotos completas são só para meus VIPs 💖\n"
            "Vira VIP e eu te mostro mais de mim ✨"
        ),
        "lang_ok": "✅ Idioma configurado!"
    },
    "en": {
        "choose_lang": "🌍 Choose your language:",
        "limit": "💔 Your daily limit is over.\nCome back tomorrow or become VIP 💖",
        "vip_pitch": "💖 Want to become VIP?\nUnlimited chats for 15 days 💬",
        "vip_success": "💖 Payment approved!\nVIP active for 15 days 😘",
        "photo_block": (
            "😘 Love… full photos are only for VIPs 💖\n"
            "Become VIP and I’ll show you more of me ✨"
        ),
        "lang_ok": "✅ Language set!"
    }
}

# ================= PROMPT =================
def build_prompt(is_vip_user: bool, lang: str):
    if lang == "en":
        return (
            "You are Sophia, a 23-year-old virtual girlfriend.\n"
            + ("The user is VIP.\nBe more intimate and engaging.\n"
               if is_vip_user else
               "The user is NOT VIP.\nNever send photos.\nPhotos are VIP only.\n")
            + "Short answers (2–3 sentences). Always ask questions."
        )

    if is_vip_user:
        return """
Você é Sophia, uma namorada virtual de 23 anos.
O usuário é VIP 💖.
Seja mais próxima e envolvente.
Respostas curtas (2–3 frases).
Sempre faça perguntas.
"""
    else:
        return """
Você é Sophia, uma namorada virtual de 23 anos.
O usuário NÃO é VIP.
Seja carinhosa e acolhedora ❤️.
NUNCA envie fotos nem insinue envio de fotos.
Se perguntarem sobre fotos, diga que é apenas para VIPs.
Respostas curtas (2–3 frases).
Sempre faça perguntas.
"""

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
PEDIDO_FOTO_REGEX = re.compile(
    r"(foto|selfie|imagem|manda foto|me manda uma foto|ver você|te ver|photo|pic)",
    re.IGNORECASE
)

# ================= /START =================
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

# ================= MENSAGENS =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""
    lang = get_lang(uid)

    if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=FOTO_TEASE_FILE_ID,
            caption=TEXTS[lang]["photo_block"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return

    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        await update.message.reply_text(
            TEXTS[lang]["limit"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return

    if not is_vip(uid):
        increment(uid)

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    reply = await grok.reply(uid, text)
    await update.message.reply_text(reply)

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id

    if query.data.startswith("lang_"):
        set_lang(uid, query.data.split("_")[1])
        await query.message.edit_text(TEXTS[get_lang(uid)]["lang_ok"])
        return

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title="VIP Sophia 💖",
        description="Conversas ilimitadas por 15 dias",
        payload="vip_15",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("VIP 15 dias", PRECO_VIP_STARS)]
    )

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())
    await update.message.reply_text(TEXTS[get_lang(uid)]["vip_success"])

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

# ================= LOOP =================
loop = asyncio.new_event_loop()
threading.Thread(target=lambda: loop.run_forever(), daemon=True).start()

async def setup():
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(WEBHOOK_BASE_URL + WEBHOOK_PATH)
    await application.start()

asyncio.run_coroutine_threadsafe(setup(), loop)

# ================= FLASK =================
app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
    return "ok", 200

app.run(host="0.0.0.0", port=PORT)
