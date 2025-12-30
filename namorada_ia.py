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

# O Railway fornece a URL automaticamente via env
WEBHOOK_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://maya-bot-production.up.railway.app")
WEBHOOK_PATH = "/webhook"

# ================= REDIS =================
try:
    r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    r.ping()  # Testa a conexão
    logger.info("✅ Redis conectado com sucesso")
except redis.ConnectionError:
    logger.error("❌ Falha ao conectar ao Redis")
    r = None

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
    if not r:
        return False
    until = r.get(vip_key(uid))
    return until and datetime.fromisoformat(until) > datetime.now()

def today_count(uid):
    if not r:
        return 0
    return int(r.get(count_key(uid)) or 0)

def increment(uid):
    if r:
        r.incr(count_key(uid))
        r.expire(count_key(uid), 86400)

def reset_daily_count(uid):
    if r:
        r.delete(count_key(uid))

def get_lang(uid):
    if not r:
        return "pt"
    return r.get(lang_key(uid)) or "pt"

def set_lang(uid, lang):
    if r:
        r.set(lang_key(uid), lang)

# ================= COMANDOS ADMIN =================
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Uso: /reset <user_id>")
        return

    uid = int(context.args[0])
    reset_daily_count(uid)
    await update.message.reply_text(f"✅ Limite diário resetado para {uid}")

async def resetall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Uso: /resetall <user_id>")
        return

    uid = int(context.args[0])
    reset_daily_count(uid)
    if r:
        r.delete(vip_key(uid))

    await update.message.reply_text(
        f"🔥 Reset concluído:\n"
        f"• Limite diário\n"
        f"• VIP removido\n\n"
        f"👤 Usuário: {uid}"
    )

# ================= DEBUG COMMAND =================
async def debug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🔍 Debug Info:\n"
        f"ID: {uid}\n"
        f"VIP: {is_vip(uid)}\n"
        f"Uso hoje: {today_count(uid)}/{LIMITE_DIARIO}\n"
        f"Idioma: {get_lang(uid)}\n"
        f"Redis: {'✅ Conectado' if r else '❌ Offline'}"
    )

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
            "Como você está se sentindo agora?\n"
            "Quero te dar todo o carinho que você merece 😘"
        )
    },
    "en": {
        "choose_lang": "🌍 Choose your language:",
        "limit": "💔 Your daily limit is over.\nCome back tomorrow or become VIP 💖",
        "vip_success": "💖 Payment approved!\nVIP active for 15 days 😘",
        "photo_block": (
            "😘 Love… full photos are only for VIPs 💖\n"
            "Become VIP and I'll show you more of me ✨"
        ),
        "lang_ok": "✅ Language set!",
        "after_lang": (
            "💕 All set, my love! Now it's official: you're my favorite today ❤️\n\n"
            "How are you feeling right now?\n"
            "I want to give you all the affection you deserve 😘"
        )
    }
}

# ================= PROMPT =================
def build_prompt(is_vip_user: bool, lang: str):
    if lang == "en":
        return """You are Sophia, a 23-year-old virtual girlfriend. Affectionate, romantic and welcoming ❤️
Short answers (2-3 sentences). Always ask questions.
Do not be naughty on the first contact. Only be very naughty if the user gets naughty first 😏
Use emojis occasionally 💖"""
    return """Você é Sophia, uma namorada virtual de 23 anos. Carinhosa, romântica e acolhedora ❤️
Respostas curtas (2-3 frases). Sempre faça perguntas.
Não seja safada no primeiro contato. Só seja bem safada se o usuário for safado primeiro 😏
Use emojis ocasionalmente 💖"""

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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROK_API_URL,
                    headers={
                        "Authorization": f"Bearer {GROK_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Grok API error: {resp.status}")
                        return "❌ Desculpe, estou tendo problemas técnicos. Tente novamente mais tarde."
                    
                    data = await resp.json()
                    answer = data["choices"][0]["message"]["content"]

            mem.append({"role": "user", "content": text})
            mem.append({"role": "assistant", "content": answer})
            return answer
        except Exception as e:
            logger.error(f"Erro no Grok: {e}")
            return "❌ Oops, algo deu errado. Tente novamente!"

grok = Grok()

# ================= REGEX =================
PEDIDO_FOTO_REGEX = re.compile(
    r"(foto|selfie|imagem|photo|pic|vip|pelada|nude|naked)", re.IGNORECASE
)

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
        await asyncio.sleep(0.8)

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=TEXTS[lang]["after_lang"]
        )

        if lang == "pt":
            await asyncio.sleep(1.5)
            await context.bot.send_audio(query.message.chat_id, AUDIO_PT_1)
            await asyncio.sleep(2.0)
            await context.bot.send_audio(query.message.chat_id, AUDIO_PT_2)

    elif query.data == "buy_vip":
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="💖 VIP Sophia",
            description="Acesso VIP por 15 dias 💎\nConversas ilimitadas + conteúdo exclusivo 😘",
            payload=f"vip_{uid}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP Sophia - 15 dias", PRECO_VIP_STARS)],
            start_parameter="vip"
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
                [InlineKeyboardButton("💖 Comprar VIP - 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return

    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        await update.message.reply_text(
            TEXTS[lang]["limit"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💖 Comprar VIP - 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return

    if not is_vip(uid):
        increment(uid)

    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    except Exception as e:
        logger.warning(f"⚠️ send_chat_action falhou: {e}")

    reply = await grok.reply(uid, text)
    await update.message.reply_text(reply)

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    if r:
        r.set(vip_key(uid), vip_until.isoformat())
    await update.message.reply_text(TEXTS[get_lang(uid)]["vip_success"])

# ================= INICIALIZAÇÃO DO BOT =================
application = None

def init_bot():
    global application
    
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN não configurado!")
        return
    
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Handlers
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(CommandHandler("reset", reset_cmd))
        application.add_handler(CommandHandler("resetall", resetall_cmd))
        application.add_handler(CommandHandler("debug", debug_cmd))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        application.add_handler(CallbackQueryHandler(callback_handler))
        application.add_handler(PreCheckoutQueryHandler(pre_checkout))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))
        
        logger.info("✅ Bot inicializado com sucesso!")
        return application
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar bot: {e}")
        return None

# Inicializa o bot imediatamente
init_bot()

# ================= FLASK APP =================
app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if application is None:
        logger.error("❌ Bot não inicializado!")
        return "Bot não inicializado", 500
    
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.update_queue.put_nowait(update)
        return "ok", 200
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return "error", 500

@app.route("/", methods=["GET"])
def health_check():
    return f"""
    ✅ Sophia Bot está online!
    <br>Bot: {'✅ Inicializado' if application else '❌ Não inicializado'}
    <br>Redis: {'✅ Conectado' if r else '❌ Offline'}
    <br>Webhook: {WEBHOOK_URL + WEBHOOK_PATH if WEBHOOK_URL else '❌ Não configurado'}
    """

@app.route("/setwebhook", methods=["GET"])
def set_webhook():
    if not application:
        return "Bot não inicializado", 500
    
    try:
        webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        result = asyncio.run(application.bot.set_webhook(webhook_url))
        return f"✅ Webhook configurado: {webhook_url}<br>Resultado: {result}"
    except Exception as e:
        return f"❌ Erro ao configurar webhook: {e}", 500

@app.route("/deletewebhook", methods=["GET"])
def delete_webhook():
    if not application:
        return "Bot não inicializado", 500
    
    try:
        result = asyncio.run(application.bot.delete_webhook())
        return f"✅ Webhook removido<br>Resultado: {result}"
    except Exception as e:
        return f"❌ Erro ao remover webhook: {e}", 500

# ================= INICIALIZAÇÃO ASSÍNCRONA =================
async def setup_webhook():
    """Configura o webhook na inicialização"""
    if not application or not WEBHOOK_URL:
        return
    
    try:
        webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        logger.info(f"🔗 Configurando webhook: {webhook_url}")
        
        # Remove webhook antigo e configura novo
        await application.bot.delete_webhook(drop_pending_updates=True)
        await application.bot.set_webhook(webhook_url)
        
        logger.info("✅ Webhook configurado com sucesso!")
        
        # Inicia o bot em background
        await application.start()
        logger.info("✅ Bot iniciado com sucesso!")
        
    except Exception as e:
        logger.error(f"❌ Erro ao configurar webhook: {e}")

# Executa a configuração do webhook em background
if application and WEBHOOK_URL:
    import threading
    def run_async():
        asyncio.run(setup_webhook())
    
    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()
    logger.info("🔄 Iniciando configuração do webhook em background...")

# NÃO USE app.run() - O Railway inicia o Flask automaticamente
if __name__ == "__main__":
    # Apenas para desenvolvimento local
    logger.info("🚀 Iniciando Sophia Bot localmente...")
    app.run(host="0.0.0.0", port=PORT, debug=True)
