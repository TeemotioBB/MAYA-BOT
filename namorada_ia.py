#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
VIP | TELEGRAM STARS | REDIS | RAILWAY
IDIOMA DINÂMICO (PT / EN)
"""

import os
import asyncio
import logging
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

# ================= ADMIN =================
ADMIN_IDS = {1293602874}

# ================= ÁUDIOS PT-BR =================
AUDIO_PT_1 = "CQACAgEAAxkBAAEC_-NpU_w1-00YgEJL-4wpp-ZuA85lCAAChgYAAhnBoUbzxkqKPx_D3zgE"
AUDIO_PT_2 = "CQACAgEAAxkBAAEC_-dpU_xseVVAm20oulK6viSv8w_pwwAChwYAAhnBoUaQgRFGZGg96zgE"

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

def reset_daily_count(uid):
    r.delete(count_key(uid))

def get_lang(uid):
    return r.get(lang_key(uid)) or "pt"

def set_lang(uid, lang):
    r.set(lang_key(uid), lang)

# ================= COMANDOS ADMIN =================
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    uid = int(context.args[0])
    reset_daily_count(uid)
    await update.message.reply_text(f"✅ Limite diário resetado para {uid}")

async def resetall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    uid = int(context.args[0])
    reset_daily_count(uid)
    r.delete(vip_key(uid))
    await update.message.reply_text("🔥 Reset completo")

async def vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    uid = int(context.args[0])
    dias = int(context.args[1])
    r.set(vip_key(uid), (datetime.now() + timedelta(days=dias)).isoformat())
    await update.message.reply_text(f"💎 VIP ativado por {dias} dias")

# ================= TEXTOS =================
TEXTS = {
    "pt": {
        "choose_lang": "🌍 Escolha seu idioma:",
        "limit": "💔 Seu limite diário acabou.\nVolte amanhã ou vire VIP 💖",
        "vip_success": "💖 Pagamento aprovado!\nVIP ativo por 15 dias 😘",
        "photo_block": "😘 Fotos completas só para VIPs 💖",
        "lang_ok": "✅ Idioma configurado!",
        "after_lang": "💕 Prontinho! Como você está se sentindo agora?",
        "pix_msg": (
            "💖 Pagamento via Pix 💖\n\n"
            "🔑 Chave Pix:\nSEU_PIX_AQUI\n\n"
            "💰 Valor:\nR$ 19,90\n\n"
            "Envie o comprovante após pagar 😘"
        )
    },
    "en": {
        "choose_lang": "🌍 Choose your language:",
        "limit": "💔 Your daily limit is over.\nBecome VIP 💖",
        "vip_success": "💖 Payment approved!\nVIP active 😘",
        "photo_block": "😘 Full photos are VIP only 💖",
        "lang_ok": "✅ Language set!",
        "after_lang": "💕 All set! How are you feeling now?",
        "pix_msg": "💖 Pix payment 💖\nSend receipt after payment 😘"
    }
}

# ================= PROMPT =================
def build_prompt(is_vip_user, lang):
    return "Você é Sophia, uma namorada virtual carinhosa ❤️"

# ================= GROK =================
class Grok:
    async def reply(self, uid, text):
        mem = get_memory(uid)
        payload = {
            "model": MODELO,
            "messages": mem + [{"role": "user", "content": text}],
            "max_tokens": 250
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROK_API_URL,
                headers={"Authorization": f"Bearer {GROK_API_KEY}"},
                json=payload
            ) as resp:
                data = await resp.json()
                answer = data["choices"][0]["message"]["content"]
        mem.append({"role": "assistant", "content": answer})
        return answer

grok = Grok()

# ================= START =================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TEXTS["pt"]["choose_lang"],
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt"),
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
        ]])
    )

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]
        set_lang(uid, lang)
        await query.message.edit_text(TEXTS[lang]["lang_ok"])
        await context.bot.send_message(query.message.chat_id, TEXTS[lang]["after_lang"])

    elif query.data == "pay_pix":
        await context.bot.send_message(query.message.chat_id, TEXTS[get_lang(uid)]["pix_msg"])

    elif query.data == "buy_vip":
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="VIP Sophia",
            description="15 dias VIP",
            payload=f"vip_{uid}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP", PRECO_VIP_STARS)]
        )

# ================= MESSAGE =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        await update.message.reply_text(TEXTS[get_lang(uid)]["limit"])
        return
    increment(uid)
    reply = await grok.reply(uid, update.message.text)
    await update.message.reply_text(reply)

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start_handler))
application.add_handler(CommandHandler("reset", reset_cmd))
application.add_handler(CommandHandler("resetall", resetall_cmd))
application.add_handler(CommandHandler("vip", vip_cmd))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(PreCheckoutQueryHandler(lambda u, c: u.pre_checkout_query.answer(ok=True)))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, lambda u, c: payment_success(u, c)))

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r.set(vip_key(update.effective_user.id),
          (datetime.now() + timedelta(days=DIAS_VIP)).isoformat())
    await update.message.reply_text(TEXTS[get_lang(update.effective_user.id)]["vip_success"])

# ================= FLASK =================
app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.get_event_loop().create_task(application.process_update(update))
    return "ok", 200

# ================= START =================
async def main():
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_BASE_URL + WEBHOOK_PATH)
    await application.start()

asyncio.get_event_loop().run_until_complete(main())
app.run(host="0.0.0.0", port=PORT)
