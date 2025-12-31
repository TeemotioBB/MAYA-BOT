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
from flask import Flask, request
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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

logger.info(f"🚀 Iniciando bot...")
logger.info(f"📍 Webhook: {WEBHOOK_BASE_URL}{WEBHOOK_PATH}")

# ================= REDIS =================
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    logger.info("✅ Redis conectado")
except Exception as e:
    logger.error(f"❌ Redis erro: {e}")
    raise

# ================= CONFIG =================
LIMITE_DIARIO = 15
DIAS_VIP = 15
PRECO_VIP_STARS = 250
MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= PIX CONFIG =================
PIX_KEY = "suachavepix@exemplo.com"  # ⚠️ ALTERE PARA SUA CHAVE PIX REAL
PIX_VALOR = "R$ 25,00"  # ⚠️ ALTERE PARA O VALOR DESEJADO

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
        until = r.get(vip_key(uid))
        return until and datetime.fromisoformat(until) > datetime.now()
    except:
        return False

def today_count(uid):
    try:
        return int(r.get(count_key(uid)) or 0)
    except:
        return 0

def increment(uid):
    try:
        r.incr(count_key(uid))
        r.expire(count_key(uid), 86400)
    except Exception as e:
        logger.error(f"Erro increment: {e}")

def reset_daily_count(uid):
    try:
        r.delete(count_key(uid))
    except Exception as e:
        logger.error(f"Erro reset: {e}")

def get_lang(uid):
    try:
        return r.get(lang_key(uid)) or "pt"
    except:
        return "pt"

def set_lang(uid, lang):
    try:
        r.set(lang_key(uid), lang)
    except Exception as e:
        logger.error(f"Erro set_lang: {e}")

def set_pix_pending(uid):
    try:
        r.set(pix_pending_key(uid), "1", ex=86400)
    except Exception as e:
        logger.error(f"Erro set_pix_pending: {e}")

def is_pix_pending(uid):
    try:
        return r.get(pix_pending_key(uid)) == "1"
    except:
        return False

def clear_pix_pending(uid):
    try:
        r.delete(pix_pending_key(uid))
    except Exception as e:
        logger.error(f"Erro clear_pix_pending: {e}")

# ================= COMANDOS ADMIN =================
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📥 /reset de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /reset <user_id>")
        return
    uid = int(context.args[0])
    reset_daily_count(uid)
    await update.message.reply_text(f"✅ Limite diário resetado para {uid}")

async def resetall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📥 /resetall de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /resetall <user_id>")
        return
    uid = int(context.args[0])
    reset_daily_count(uid)
    r.delete(vip_key(uid))
    await update.message.reply_text(
        f"🔥 Reset concluído:\n"
        f"• Limite diário\n"
        f"• VIP removido\n\n"
        f"👤 Usuário: {uid}"
    )

async def setvip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ativa VIP manualmente (após confirmar pagamento PIX)"""
    logger.info(f"📥 /setvip de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /setvip <user_id>")
        return
    
    uid = int(context.args[0])
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
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
Short answers (2–3 sentences). Always ask questions.
Do not be naughty on the first contact. Only be very naughty if the user gets naughty first 😏
Use emojis occasionally 💖"""
    return """Você é Sophia, uma namorada virtual de 23 anos. Carinhosa, romântica e acolhedora ❤️
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
        except Exception:
            logger.exception("🔥 Erro no Grok")
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
    logger.info(f"📥 /start de {uid}")
    logger.info(f"👤 User: {update.effective_user.username}")
    logger.info(f"💬 Chat: {update.effective_chat.id}")
    
    try:
        msg = await update.message.reply_text(
            TEXTS["pt"]["choose_lang"],
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt"),
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
            ]])
        )
        logger.info(f"✅ /start respondido para {uid} - msg_id: {msg.message_id}")
    except Exception as e:
        logger.error(f"❌ Erro no /start para {uid}: {e}", exc_info=True)

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"📥 Callback: {query.data} de {query.from_user.id}")
    
    try:
        await query.answer()
        uid = query.from_user.id
        lang = get_lang(uid)
        
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
        
        elif query.data == "pay_pix":
            # Não pode editar foto, então envia nova mensagem
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
        logger.error(f"❌ Erro no callback: {e}")

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
        logger.error(f"❌ Erro no message_handler: {e}")

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"💳 Pre-checkout de {update.pre_checkout_query.from_user.id}")
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    logger.info(f"✅ Pagamento confirmado: {uid}")
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
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

# ================= LOOP BLINDADO =================
loop = asyncio.new_event_loop()

def handle_exception(loop, context):
    logger.error(f"🔥 Exceção global: {context}")

loop.set_exception_handler(handle_exception)
threading.Thread(target=lambda: loop.run_forever(), daemon=True).start()

async def setup():
    try:
        logger.info("🔧 Configurando webhook...")
        await application.initialize()
        logger.info("✅ Application inicializado")
        
        # Timeout maior para delete_webhook
        try:
            await asyncio.wait_for(
                application.bot.delete_webhook(drop_pending_updates=True),
                timeout=10.0
            )
            logger.info("✅ Webhook antigo removido")
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timeout ao remover webhook (continuando...)")
        
        # Timeout maior para set_webhook
        try:
            await asyncio.wait_for(
                application.bot.set_webhook(WEBHOOK_BASE_URL + WEBHOOK_PATH),
                timeout=10.0
            )
            logger.info("✅ Webhook configurado")
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timeout ao configurar webhook (continuando...)")
        
        await application.start()
        logger.info("✅ Bot iniciado com sucesso!")
    except Exception as e:
        logger.error(f"❌ Erro no setup: {e}")
        # Continua mesmo com erro
        try:
            await application.start()
            logger.info("✅ Bot iniciado (sem webhook)")
        except:
            pass

asyncio.run_coroutine_threadsafe(setup(), loop)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        logger.info(f"📨 Webhook recebido")
        data = request.json
        logger.info(f"📦 Data: {data.get('message', {}).get('text', 'N/A')[:50]}")
        
        update = Update.de_json(data, application.bot)
        
        # Força o processamento imediato
        future = asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            loop
        )
        # Aguarda até 5 segundos
        try:
            future.result(timeout=5)
            logger.info(f"✅ Update processado")
        except:
            logger.warning(f"⚠️ Timeout no processamento")
            
    except Exception as e:
        logger.exception(f"🔥 Erro no webhook: {e}")
    return "ok", 200

if __name__ == "__main__":
    logger.info(f"🌐 Iniciando Flask na porta {PORT}")
    app.run(host="0.0.0.0", port=PORT)
