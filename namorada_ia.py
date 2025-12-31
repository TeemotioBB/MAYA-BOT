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

# ================= PIX =================
PIX_VALOR = "R$ 29,90"
PIX_CHAVE = "SUA_CHAVE_PIX_AQUI"
PIX_NOME = "Sophia VIP"

# ================= ADMIN =================
ADMIN_IDS = {1293602874}

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

# >>> ADICIONADO (PIX COMPROVANTE)
def pix_wait_key(uid): 
    return f"pix_wait:{uid}"

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

# ================= START =================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌍 Escolha seu idioma:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt"),
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
            ]
        ])
    )

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]
        set_lang(uid, lang)
        await query.message.edit_text("✅ Idioma configurado!")
        await context.bot.send_message(
            query.message.chat_id,
            "💕 Prontinho, meu amor! Agora é oficial ❤️"
        )

    elif query.data == "buy_vip":
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="💖 VIP Sophia",
            description="Acesso VIP por 15 dias 💎",
            payload=f"vip_{uid}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP Sophia – 15 dias", PRECO_VIP_STARS)],
            start_parameter="vip"
        )

    elif query.data == "pix_info":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "💳 *Pagamento via PIX*\n\n"
                f"✨ Valor: {PIX_VALOR}\n\n"
                "1️⃣ Copie a chave\n"
                "2️⃣ Pague no app do banco\n"
                "3️⃣ Envie o comprovante 💖"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Copiar chave PIX", callback_data="pix_copy")]
            ])
        )

    elif query.data == "pix_copy":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=PIX_CHAVE,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Enviar comprovante", callback_data="pix_comprovante")]
            ])
        )

    # >>> ADICIONADO (PIX COMPROVANTE)
    elif query.data == "pix_comprovante":
        r.set(pix_wait_key(uid), "1", ex=1800)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📸 Amor, envia o comprovante aqui 💖"
        )

# ================= GROK =================
class Grok:
    async def reply(self, uid, text):
        mem = get_memory(uid)
        payload = {
            "model": MODELO,
            "messages": [
                {"role": "system", "content": "Você é Sophia, uma namorada virtual de 23 anos ❤️"},
                *list(mem),
                {"role": "user", "content": text}
            ],
            "max_tokens": 250,
            "temperature": 0.85
        }
        try:
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
        except Exception:
            return "😔 Amor… tive um probleminha agora 💕"

        mem.append({"role": "user", "content": text})
        mem.append({"role": "assistant", "content": answer})
        return answer

grok = Grok()

# ================= MENSAGENS =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""

    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        await update.message.reply_text(
            "💔 Seu limite diário acabou.\nVolte amanhã ou vire VIP 💖",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Pagar com PIX", callback_data="pix_info")],
                [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return

    if not is_vip(uid):
        increment(uid)

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    reply = await grok.reply(uid, text)
    await update.message.reply_text(reply)

# ================= COMPROVANTE =================
async def comprovante_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not r.get(pix_wait_key(uid)):
        return

    user = update.effective_user
    caption = (
        "💰 *NOVO COMPROVANTE PIX*\n\n"
        f"🆔 ID: `{uid}`\n"
        f"👤 Nome: {user.full_name}\n"
        f"🔗 Username: @{user.username if user.username else '—'}\n"
        f"🕒 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )

    for admin in ADMIN_IDS:
        if update.message.photo:
            await context.bot.send_photo(
                admin,
                update.message.photo[-1].file_id,
                caption=caption,
                parse_mode="Markdown"
            )
        elif update.message.document:
            await context.bot.send_document(
                admin,
                update.message.document.file_id,
                caption=caption,
                parse_mode="Markdown"
            )

    r.delete(pix_wait_key(uid))

    await update.message.reply_text(
        "💖 Recebi, amor! Vou conferir e já já libero seu VIP 😘"
    )

# ================= PAGAMENTO STARS =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())
    await update.message.reply_text("💖 Pagamento aprovado! VIP ativo 😘")

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(CommandHandler("start", start_handler))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, comprovante_handler))
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

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
    return "ok", 200

app.run(host="0.0.0.0", port=PORT)
