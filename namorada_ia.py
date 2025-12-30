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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"
PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN não configurado!")
    raise RuntimeError("TELEGRAM_TOKEN não configurado")
if not GROK_API_KEY:
    logger.error("❌ GROK_API_KEY não configurado!")
    raise RuntimeError("GROK_API_KEY não configurado")

# URL do Railway - IMPORTANTE: já inclui https://
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL", "https://maya-bot-production.up.railway.app")
WEBHOOK_PATH = "/telegram"  # Mantém o mesmo que já está sendo usado

logger.info(f"🌐 Webhook URL: {WEBHOOK_URL}")
logger.info(f"🛤️ Webhook Path: {WEBHOOK_PATH}")

# ================= REDIS =================
try:
    r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    r.ping()
    logger.info("✅ Redis conectado")
except redis.ConnectionError as e:
    logger.error(f"❌ Redis falhou: {e}")
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
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.now()
    except:
        return False

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
        ),
        "welcome": "💖 Olá amor! Eu sou a Sophia, sua namorada virtual ❤️"
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
        ),
        "welcome": "💖 Hello love! I'm Sophia, your virtual girlfriend ❤️"
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
    uid = update.effective_user.id
    lang = get_lang(uid)
    
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

# ================= FLASK APP =================
app = Flask(__name__)

# ================= INICIALIZAÇÃO DO BOT =================
# Cria a aplicação
application = None
update_queue = asyncio.Queue()

def init_bot():
    global application
    try:
        logger.info("🤖 Inicializando bot...")
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Adiciona handlers
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(CommandHandler("reset", reset_cmd))
        application.add_handler(CommandHandler("resetall", resetall_cmd))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        application.add_handler(CallbackQueryHandler(callback_handler))
        application.add_handler(PreCheckoutQueryHandler(pre_checkout))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))
        
        # Inicializa
        logger.info("✅ Bot inicializado com sucesso!")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar bot: {e}")
        return False

# Inicializa o bot
bot_initialized = init_bot()

# ================= ROTAS FLASK =================
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Endpoint do webhook do Telegram"""
    if not bot_initialized or not application:
        logger.error("Bot não inicializado!")
        return "Bot não inicializado", 500
    
    try:
        # Processa a atualização do Telegram
        update = Update.de_json(request.get_json(force=True), application.bot)
        
        # Cria uma nova tarefa para processar a atualização
        async def process_update():
            await application.process_update(update)
        
        # Executa de forma síncrona
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_update())
        
        return "ok", 200
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return "error", 500

@app.route("/", methods=["GET"])
def health_check():
    return f"""
    <h1>✅ Sophia Bot está online!</h1>
    <p>Status: <strong>{"Operacional" if bot_initialized else "Erro na inicialização"}</strong></p>
    <p>Redis: {'✅ Conectado' if r else '❌ Offline'}</p>
    <p>Webhook: {WEBHOOK_URL + WEBHOOK_PATH}</p>
    <p>Para configurar o webhook, acesse: <a href="/setwebhook">/setwebhook</a></p>
    <p>Para remover o webhook, acesse: <a href="/deletewebhook">/deletewebhook</a></p>
    """

@app.route("/setwebhook", methods=["GET"])
def set_webhook():
    """Configura o webhook manualmente"""
    if not bot_initialized or not application:
        return "Bot não inicializado", 500
    
    try:
        webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        logger.info(f"🔗 Configurando webhook: {webhook_url}")
        
        # Função assíncrona para configurar webhook
        async def configure_webhook():
            await application.bot.delete_webhook(drop_pending_updates=True)
            result = await application.bot.set_webhook(webhook_url)
            return result
        
        # Executa de forma síncrona
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(configure_webhook())
        
        logger.info(f"✅ Webhook configurado: {result}")
        
        return f"""
        <h1>✅ Webhook Configurado!</h1>
        <p>URL: {webhook_url}</p>
        <p>Resultado: {result}</p>
        <p><a href="/">Voltar</a></p>
        """
    except Exception as e:
        logger.error(f"❌ Erro ao configurar webhook: {e}")
        return f"<h1>❌ Erro: {e}</h1>", 500

@app.route("/deletewebhook", methods=["GET"])
def delete_webhook():
    """Remove o webhook"""
    if not bot_initialized or not application:
        return "Bot não inicializado", 500
    
    try:
        # Função assíncrona para remover webhook
        async def remove_webhook():
            result = await application.bot.delete_webhook()
            return result
        
        # Executa de forma síncrona
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(remove_webhook())
        
        return f"""
        <h1>✅ Webhook Removido!</h1>
        <p>Resultado: {result}</p>
        <p><a href="/">Voltar</a></p>
        """
    except Exception as e:
        return f"<h1>❌ Erro: {e}</h1>", 500

# Configura o webhook automaticamente ao iniciar (se possível)
def setup_webhook_on_start():
    """Tenta configurar o webhook quando a aplicação iniciar"""
    if not bot_initialized or not application:
        return
    
    try:
        # Espera um pouco para garantir que o servidor está pronto
        import time
        time.sleep(2)
        
        webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        logger.info(f"🔄 Tentando configurar webhook automaticamente: {webhook_url}")
        
        # Tenta configurar de forma assíncrona
        async def configure():
            try:
                await application.bot.delete_webhook(drop_pending_updates=True)
                await application.bot.set_webhook(webhook_url)
                logger.info("✅ Webhook configurado automaticamente!")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Não foi possível configurar webhook automaticamente: {e}")
                logger.info("ℹ️ Configure manualmente em: /setwebhook")
                return False
        
        # Executa em uma thread separada para não bloquear
        import threading
        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(configure())
        
        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
        
    except Exception as e:
        logger.error(f"❌ Erro na configuração automática: {e}")

# Tenta configurar o webhook automaticamente (em background)
setup_webhook_on_start()

# NÃO USE app.run() - O Railway inicia o Flask automaticamente
# Apenas exportamos o app para o Railway
if __name__ == "__main__":
    # Apenas para desenvolvimento local
    logger.info("🚀 Iniciando Sophia Bot localmente...")
    from waitress import serve
    serve(app, host="0.0.0.0", port=PORT)
