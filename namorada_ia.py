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

# ================= PIX (ADICIONADO) =================
PIX_VALOR = "R$ 29,90"
PIX_CHAVE = "SUA_CHAVE_PIX_AQUI"

def aguardando_pix_key(uid):
    return f"pix_wait:{uid}"

# ================= ADMIN =================
ADMIN_IDS = {1293602874}

# ================= ÁUDIOS PT-BR =================
AUDIO_PT_1 = "CQACAgEAAxkBAAEDAAEkaVRmK1n5WoDUbeTBKyl6sgLwfNoAAoYGAAIZwaFG88ZKij8fw984BA"
AUDIO_PT_2 = "CQACAgEAAxkBAAEDAAEmaVRmPJ5iuBOaXyukQ06Ui23TSokAAocGAAIZwaFGkIERRmRoPes4BA"

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
    await update.message.reply_text(f"🔥 Reset total para {uid}")

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
            "💕 Prontinho, meu amor! Agora é oficial ❤️\n"
            "Como você está se sentindo agora? 😘"
        ),
        # ===== PIX (ADICIONADO) =====
        "pix_info": (
            "💳 *Pagamento via PIX*\n\n"
            f"✨ Valor: {PIX_VALOR}\n\n"
            "Clique abaixo para copiar a chave PIX 👇"
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
            "💕 All set, my love! ❤️\nHow are you feeling now? 😘"
        )
    }
}

# ================= PROMPT =================
def build_prompt(is_vip_user: bool, lang: str):
    if lang == "en":
        return "You are Sophia, a 23-year-old virtual girlfriend. Affectionate ❤️"
    return "Você é Sophia, uma namorada virtual carinhosa ❤️"

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
            ]
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
    r"(foto|selfie|imagem|photo|pic|vip|pelada|nude|naked)",
    re.IGNORECASE
)

# ================= START =================
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

    # ===== PIX (ADICIONADO) =====
    elif query.data == "pix_info":
        await context.bot.send_message(
            query.message.chat_id,
            TEXTS["pt"]["pix_info"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Copiar chave PIX", callback_data="pix_copy")]
            ])
        )

    elif query.data == "pix_copy":
        await context.bot.send_message(
            query.message.chat_id,
            PIX_CHAVE,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Enviar comprovante", callback_data="pix_comprovante")]
            ])
        )

    elif query.data == "pix_comprovante":
        r.setex(aguardando_pix_key(uid), 600, "1")
        await context.bot.send_message(
            query.message.chat_id,
            "📸 Agora me envie o comprovante aqui 💖"
        )

# ================= COMPROVANTE PIX (ADICIONADO) =================
async def comprovante_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not r.get(aguardando_pix_key(uid)):
        return

    user = update.effective_user
    admin_id = list(ADMIN_IDS)[0]

    caption = (
        "💳 *COMPROVANTE PIX*\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"👤 Nome: {user.first_name}\n"
        f"🔗 Username: @{user.username if user.username else 'N/A'}"
    )

    if update.message.photo:
        await context.bot.send_photo(
            admin_id,
            update.message.photo[-1].file_id,
            caption=caption,
            parse_mode="Markdown"
        )
    elif update.message.document:
        await context.bot.send_document(
            admin_id,
            update.message.document.file_id,
            caption=caption,
            parse_mode="Markdown"
        )

    r.delete(aguardando_pix_key(uid))
    await update.message.reply_text("✅ Comprovante recebido! Agora é só aguardar 😘")

# ================= MENSAGENS =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""
    lang = get_lang(uid)

    if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
        buttons = [[InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]]
        if lang == "pt":
            buttons.insert(0, [InlineKeyboardButton("💳 Pagar com PIX", callback_data="pix_info")])
        await context.bot.send_photo(
            update.effective_chat.id,
            FOTO_TEASE_FILE_ID,
            caption=TEXTS[lang]["photo_block"],
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        buttons = [[InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]]
        if lang == "pt":
            buttons.insert(0, [InlineKeyboardButton("💳 Pagar com PIX", callback_data="pix_info")])
        await update.message.reply_text(TEXTS[lang]["limit"], reply_markup=InlineKeyboardMarkup(buttons))
        return

    if not is_vip(uid):
        increment(uid)

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    reply = await grok.reply(uid, text)
    await update.message.reply_text(reply)

# ================= PAGAMENTO STARS =================
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
application.add_handler(CommandHandler("reset", reset_cmd))
application.add_handler(CommandHandler("resetall", resetall_cmd))
application.add_handler(
    MessageHandler(filters.PHOTO | filters.Document.ALL, comprovante_handler)
)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

# ================= LOOP BLINDADO =================
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
