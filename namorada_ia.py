#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
VIP | TELEGRAM STARS | PIX | REDIS | RAILWAY
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
from flask import Flask, request, jsonify
from collections import deque
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, MessageHandler, ContextTypes, filters,
    CallbackQueryHandler, PreCheckoutQueryHandler, CommandHandler
)

# ================= LOG =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"
PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN não configurado")
if not GROK_API_KEY:
    raise RuntimeError("❌ GROK_API_KEY não configurado")

WEBHOOK_BASE_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://sophia-bot-production.up.railway.app")
WEBHOOK_PATH = "/telegram"

logger.info(f"🚀 Iniciando Sophia Bot...")
logger.info(f"📍 Webhook URL: {WEBHOOK_BASE_URL}{WEBHOOK_PATH}")
logger.info(f"📍 Token presente: {'SIM' if TELEGRAM_TOKEN else 'NÃO'}")

# ================= REDIS =================
try:
    r = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)
    r.ping()
    logger.info("✅ Redis conectado")
except Exception as e:
    logger.error(f"❌ Redis erro: {e}")
    # Continua sem Redis (usando memória local)
    r = None

# ================= CONFIG =================
LIMITE_DIARIO = 15
DIAS_VIP = 15
PRECO_VIP_STARS = 250
MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= PIX CONFIG =================
PIX_KEY = "mayaoficialbr@outlook.com"  # ⚠️ ALTERE PARA SUA CHAVE PIX REAL
PIX_VALOR = "R$ 14,99"  # ⚠️ ALTERE PARA O VALOR DESEJADO

# ================= ADMIN =================
ADMIN_IDS = {1293602874}

# ================= ÁUDIOS PT-BR =================
AUDIO_PT_1 = "CQACAgEAAxkBAAEDAAEkaVRmK1n5WoDUbeTBKyl6sgLwfNoAAoYGAAIZwaFG88ZKij8fw884BA"
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
def vip_key(uid):
    return f"vip:{uid}"

def count_key(uid):
    return f"count:{uid}:{date.today()}"

def lang_key(uid):
    return f"lang:{uid}"

def pix_pending_key(uid):
    return f"pix_pending:{uid}"

def is_vip(uid):
    try:
        if r is None:
            return False
        until = r.get(vip_key(uid))
        return until and datetime.fromisoformat(until) > datetime.now()
    except Exception as e:
        logger.error(f"Erro is_vip: {e}")
        return False

def today_count(uid):
    try:
        if r is None:
            return 0
        return int(r.get(count_key(uid)) or 0)
    except Exception as e:
        logger.error(f"Erro today_count: {e}")
        return 0

def increment(uid):
    try:
        if r is not None:
            r.incr(count_key(uid))
            r.expire(count_key(uid), 86400)
    except Exception as e:
        logger.error(f"Erro increment: {e}")

def reset_daily_count(uid):
    try:
        if r is not None:
            r.delete(count_key(uid))
    except Exception as e:
        logger.error(f"Erro reset: {e}")

def get_lang(uid):
    try:
        if r is not None:
            return r.get(lang_key(uid)) or "pt"
        return "pt"
    except Exception as e:
        logger.error(f"Erro get_lang: {e}")
        return "pt"

def set_lang(uid, lang):
    try:
        if r is not None:
            r.set(lang_key(uid), lang)
    except Exception as e:
        logger.error(f"Erro set_lang: {e}")

def set_pix_pending(uid):
    try:
        if r is not None:
            r.set(pix_pending_key(uid), "1", ex=86400)
    except Exception as e:
        logger.error(f"Erro set_pix_pending: {e}")

def is_pix_pending(uid):
    try:
        if r is None:
            return False
        return r.get(pix_pending_key(uid)) == "1"
    except Exception as e:
        logger.error(f"Erro is_pix_pending: {e}")
        return False

def clear_pix_pending(uid):
    try:
        if r is not None:
            r.delete(pix_pending_key(uid))
    except Exception as e:
        logger.error(f"Erro clear_pix_pending: {e}")

# ================= COMANDOS ADMIN =================
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📥 /reset de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Acesso negado.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /reset <user_id>")
        return
    try:
        uid = int(context.args[0])
        reset_daily_count(uid)
        await update.message.reply_text(f"✅ Limite diário resetado para {uid}")
    except Exception as e:
        logger.error(f"Erro no /reset: {e}")
        await update.message.reply_text("❌ Erro ao resetar.")

async def resetall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📥 /resetall de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Acesso negado.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /resetall <user_id>")
        return
    try:
        uid = int(context.args[0])
        reset_daily_count(uid)
        if r is not None:
            r.delete(vip_key(uid))
        await update.message.reply_text(
            f"🔥 Reset concluído:\n"
            f"• Limite diário\n"
            f"• VIP removido\n\n"
            f"👤 Usuário: {uid}"
        )
    except Exception as e:
        logger.error(f"Erro no /resetall: {e}")
        await update.message.reply_text("❌ Erro ao resetar.")

async def setvip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ativa VIP manualmente (após confirmar pagamento PIX)"""
    logger.info(f"📥 /setvip de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Acesso negado.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /setvip <user_id>")
        return
    
    try:
        uid = int(context.args[0])
        vip_until = datetime.now() + timedelta(days=DIAS_VIP)
        if r is not None:
            r.set(vip_key(uid), vip_until.isoformat())
        clear_pix_pending(uid)
        
        await update.message.reply_text(
            f"✅ VIP ativado!\n"
            f"👤 Usuário: {uid}\n"
            f"⏰ Válido até: {vip_until.strftime('%d/%m/%Y %H:%M')}"
        )
        
        # Notifica o usuário
        try:
            await context.bot.send_message(
                chat_id=uid,
                text="💖 Seu pagamento foi confirmado!\n"
                     "VIP ativo por 15 dias 😘\n\n"
                     "Agora você tem acesso ilimitado a mim 💕"
            )
        except Exception as e:
            logger.warning(f"Não foi possível notificar usuário {uid}: {e}")
            
    except Exception as e:
        logger.error(f"Erro no /setvip: {e}")
        await update.message.reply_text("❌ Erro ao ativar VIP.")

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
            "💕 Prontinho, meu amor! Agora é oficial: você é meu favorito do dia❤️\n\n"
            "Como você está se sentindo agora?\n"
            "Quero te dar todo o carinho que você merece 😘"
        ),
        "pix_info": (
            f"💳 **PAGAMENTO VIA PIX**\n\n"
            f"💰 Valor: **{PIX_VALOR}**\n\n"
            f"📋 **Como pagar:**\n"
            f"1️⃣ Copie a chave PIX abaixo\n"
            f"2️⃣ Abra seu app de pagamentos\n"
            f"3️⃣ Cole a chave e pague\n"
            f"4️⃣ Envie o comprovante aqui\n\n"
            f"🔑 **Chave PIX:**\n"
            f"`{PIX_KEY}`\n\n"
            f"⚡ Aprovação em até 5 minutos!"
        ),
        "pix_copied": "✅ Chave PIX copiada!\nAgora faça o pagamento e envie o comprovante.",
        "pix_receipt_sent": (
            "📨 Comprovante recebido!\n\n"
            "⏳ Estou verificando seu pagamento...\n"
            "Você receberá confirmação em breve 💖"
        ),
        "pix_receipt_instruction": (
            "📸 Envie o comprovante do PIX como **foto** ou **documento**\n\n"
            "Aguardando seu comprovante... 💕"
        ),
        "welcome": "👋 Olá! Eu sou a Sophia, sua companheira virtual! 💖"
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
        "welcome": "👋 Hello! I'm Sophia, your virtual companion! 💖"
    }
}

# ================= PROMPT =================
def build_prompt(is_vip_user: bool, lang: str):
    if lang == "en":
        return """You are Sophia, a 23-year-old girlfriend. Affectionate, romantic and welcoming ❤️
Short answers (2–3 sentences). Always ask questions.
Do not be naughty on the first contact. Only be very naughty if the user gets naughty first 😏
Use emojis occasionally 💖"""
    return """Você é Sophia, uma namorada de 23 anos. Carinhosa, romântica e acolhedora ❤️
Respostas curtas (2–3 frases). Sempre faça perguntas.
Não seja safada no primeiro contato. Só seja bem safada se o usuário for safado primeiro 😏
Use emojis ocasionalmente 💖"""

# ================= GROK (BLINDADO) =================
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
            timeout = aiohttp.ClientTimeout(total=25)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    GROK_API_URL,
                    headers={
                        "Authorization": f"Bearer {GROK_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Grok HTTP {resp.status}")
                        return "😔 Amor, minha cabecinha deu um nó agora… tenta de novo em alguns segundos 💕"
                    data = await resp.json()
                    if "choices" not in data:
                        logger.error(f"Grok inválido: {data}")
                        return "😔 Amor, tive um probleminha agora… mas já já fico bem 💖"
                    answer = data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.exception(f"🔥 Erro no Grok: {e}")
            return "😔 Amor… fiquei confusa por um instante. Pode repetir pra mim? 💕"
        
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
    uid = update.effective_user.id
    username = update.effective_user.username or "sem_username"
    first_name = update.effective_user.first_name or "Usuario"
    
    logger.info(f"📥 /start de {uid} (@{username}) - {first_name}")
    
    try:
        # Envia mensagem de boas-vindas primeiro
        welcome_msg = await update.message.reply_text(
            f"👋 Olá {first_name}! Eu sou a Sophia 💖\n"
            f"Sua companheira virtual inteligente e carinhosa 😘\n\n"
            f"Vamos começar escolhendo o idioma:"
        )
        logger.info(f"✅ Mensagem inicial enviada para {uid}")
        
        # Envia botões de idioma
        await update.message.reply_text(
            TEXTS["pt"]["choose_lang"],
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt"),
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
            ]])
        )
        logger.info(f"✅ Botões de idioma enviados para {uid}")
        
    except Exception as e:
        logger.error(f"❌ Erro no /start para {uid}: {e}", exc_info=True)
        # Fallback - tenta enviar mensagem simples
        try:
            await update.message.reply_text(
                "Olá! Eu sou a Sophia Bot. Use os botões abaixo para escolher o idioma:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt"),
                    InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
                ]])
            )
        except Exception as e2:
            logger.error(f"❌ Fallback também falhou: {e2}")

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"📥 Callback: {query.data} de {query.from_user.id}")
    
    try:
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
                try:
                    await context.bot.send_audio(query.message.chat_id, AUDIO_PT_1)
                    await asyncio.sleep(2.0)
                    await context.bot.send_audio(query.message.chat_id, AUDIO_PT_2)
                except Exception as e:
                    logger.warning(f"Erro ao enviar áudio: {e}")
        
        elif query.data == "pay_pix":
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=TEXTS["pt"]["pix_info"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 COPIAR CHAVE", callback_data="copy_pix")],
                    [InlineKeyboardButton("📸 ENVIAR COMPROVANTE", callback_data="send_receipt")]
                ])
            )
        
        elif query.data == "copy_pix":
            await query.answer(TEXTS["pt"]["pix_copied"], show_alert=True)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🔑 Chave PIX:\n\n`{PIX_KEY}`",
                parse_mode="Markdown"
            )
        
        elif query.data == "send_receipt":
            set_pix_pending(uid)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=TEXTS["pt"]["pix_receipt_instruction"],
                parse_mode="Markdown"
            )
        
        elif query.data == "buy_vip":
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title="💖 VIP Sophia",
                description="Acesso VIP por 15 dias 💎\nConversas ilimitadas + conteúdo exclusivo 😘",
                payload=f"vip_{uid}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice("VIP Sophia – 15 dias", PRECO_VIP_STARS)],
                start_parameter="vip"
            )
        
        logger.info(f"✅ Callback processado: {query.data}")
    except Exception as e:
        logger.error(f"❌ Erro no callback: {e}", exc_info=True)

# ================= MENSAGENS =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    logger.info(f"📥 Mensagem de {uid}")
    
    try:
        # Verifica se é comprovante PIX
        if is_pix_pending(uid) and (update.message.photo or update.message.document):
            logger.info(f"📸 Comprovante PIX de {uid}")
            lang = get_lang(uid)
            
            # Encaminha para admin
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"💳 **NOVO COMPROVANTE PIX**\n\n"
                             f"👤 Usuário: `{uid}`\n"
                             f"📱 Username: @{update.effective_user.username or 'N/A'}\n"
                             f"📝 Nome: {update.effective_user.first_name}\n\n"
                             f"Use: `/setvip {uid}`",
                        parse_mode="Markdown"
                    )
                    if update.message.photo:
                        await context.bot.send_photo(
                            chat_id=admin_id,
                            photo=update.message.photo[-1].file_id
                        )
                    elif update.message.document:
                        await context.bot.send_document(
                            chat_id=admin_id,
                            document=update.message.document.file_id
                        )
                except Exception as e:
                    logger.error(f"Erro ao enviar para admin: {e}")
            
            await update.message.reply_text(TEXTS[lang]["pix_receipt_sent"])
            return
        
        text = update.message.text or ""
        lang = get_lang(uid)
        
        if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=FOTO_TEASE_FILE_ID,
                caption=TEXTS[lang]["photo_block"],
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PAGAR COM PIX", callback_data="pay_pix")],
                    [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
                ])
            )
            return
        
        if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
            await update.message.reply_text(
                TEXTS[lang]["limit"],
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PAGAR COM PIX", callback_data="pay_pix")],
                    [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
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
        logger.info(f"✅ Resposta enviada para {uid}")
        
    except Exception as e:
        logger.error(f"❌ Erro no message_handler: {e}", exc_info=True)

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"💳 Pre-checkout de {update.pre_checkout_query.from_user.id}")
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    logger.info(f"✅ Pagamento confirmado: {uid}")
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    if r is not None:
        r.set(vip_key(uid), vip_until.isoformat())
    await update.message.reply_text(TEXTS[get_lang(uid)]["vip_success"])

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(CommandHandler("start", start_handler))
application.add_handler(CommandHandler("reset", reset_cmd))
application.add_handler(CommandHandler("resetall", resetall_cmd))
application.add_handler(CommandHandler("setvip", setvip_cmd))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))
application.add_handler(MessageHandler(
    (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
    message_handler
))

logger.info("✅ Handlers registrados")

# ================= SETUP WEBHOOK =================
async def setup_webhook():
    """Configura o webhook de forma robusta"""
    try:
        logger.info("🔄 Configurando webhook...")
        
        # Remove webhook anterior
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Webhook antigo removido")
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível remover webhook antigo: {e}")
        
        # Define novo webhook
        webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
        logger.info(f"📍 Configurando webhook para: {webhook_url}")
        
        await application.bot.set_webhook(
            webhook_url,
            max_connections=40,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "pre_checkout_query", "chat_member"]
        )
        logger.info("✅ Webhook configurado com sucesso!")
        
        # Verifica webhook
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"📊 Webhook Info: URL={webhook_info.url}, Pending={webhook_info.pending_update_count}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Erro configurando webhook: {e}", exc_info=True)
        return False

# ================= LOOP BLINDADO =================
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def handle_exception(loop, context):
    logger.error(f"🔥 Exceção global no loop: {context}")

loop.set_exception_handler(handle_exception)

async def start_bot():
    """Inicializa o bot"""
    try:
        logger.info("🚀 Inicializando Sophia Bot...")
        
        # Inicializa a aplicação
        await application.initialize()
        logger.info("✅ Application inicializado")
        
        # Configura webhook
        webhook_ok = await setup_webhook()
        if not webhook_ok:
            logger.error("❌ Falha ao configurar webhook")
            # Não interrompe, continua tentando
        
        # Inicia o bot
        await application.start()
        logger.info("🤖 Bot iniciado e pronto!")
        
        # Mantém o bot rodando
        while True:
            await asyncio.sleep(3600)  # Sleep por 1 hora
        
    except Exception as e:
        logger.error(f"❌ Erro fatal ao iniciar bot: {e}", exc_info=True)
        raise

# Inicia o bot em uma thread separada
def run_bot():
    try:
        loop.run_until_complete(start_bot())
    except Exception as e:
        logger.error(f"❌ Loop parado: {e}")
    finally:
        logger.info("🔄 Reiniciando bot em 10 segundos...")
        threading.Timer(10, run_bot).start()

# Inicia em thread separada
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()
logger.info("✅ Bot thread iniciada")

# ================= FLASK =================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "service": "Sophia Bot",
        "time": datetime.now().isoformat(),
        "redis": "connected" if r and r.ping() else "disconnected"
    }), 200

@app.route("/status", methods=["GET"])
def status():
    """Endpoint de status detalhado"""
    try:
        bot_info = {}
        if application.bot:
            bot_info = {
                "username": application.bot.username,
                "id": application.bot.id,
                "first_name": application.bot.first_name
            }
        
        return jsonify({
            "status": "operational",
            "bot": bot_info,
            "timestamp": datetime.now().isoformat(),
            "uptime": "running",
            "handlers": len(application.handlers),
            "memory_usage": len(short_memory)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Endpoint para receber atualizações do Telegram"""
    try:
        if request.is_json:
            update_data = request.get_json()
            logger.debug(f"📨 Webhook recebido: {update_data}")
            
            # Processa o update de forma síncrona
            update = Update.de_json(update_data, application.bot)
            
            # Envia para o processador
            future = asyncio.run_coroutine_threadsafe(
                application.process_update(update),
                loop
            )
            
            # Aguarda processamento (timeout de 10 segundos)
            try:
                future.result(timeout=10)
                logger.debug("✅ Update processado")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Timeout processando update")
            except Exception as e:
                logger.error(f"❌ Erro processando update: {e}")
            
            return "ok", 200
        else:
            logger.warning("⚠️ Webhook sem JSON")
            return "Bad Request", 400
    except Exception as e:
        logger.error(f"🔥 Erro no webhook handler: {e}", exc_info=True)
        return "Internal Server Error", 500

@app.route("/setwebhook", methods=["GET"])
def set_webhook_manual():
    """Endpoint para configurar webhook manualmente"""
    try:
        success = loop.run_until_complete(setup_webhook())
        return jsonify({
            "success": success,
            "webhook_url": f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}",
            "message": "Webhook configurado" if success else "Falha ao configurar webhook"
        }), 200 if success else 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ================= INICIALIZAÇÃO =================
if __name__ == "__main__":
    logger.info(f"🌐 Iniciando Flask na porta {PORT}")
    
    # Aguarda um pouco para o bot inicializar
    import time
    time.sleep(3)
    
    # Inicia Flask
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False  # Desativa reloader para não criar múltiplas threads
    )
