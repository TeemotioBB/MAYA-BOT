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
CHAVE_PIX = os.getenv("CHAVE_PIX", "00020126580014br.gov.bcb.pix0136a629532e-7693-4d5d-9e5c-exemplo5204000053039865802BR5913NOME DO TITULAR6009BRASILIA62070503***6304E2CA")  # Sua chave PIX aqui

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
def vip_key(uid):
    return f"vip:{uid}"

def count_key(uid):
    return f"count:{uid}:{date.today()}"

def lang_key(uid):
    return f"lang:{uid}"

def pix_pending_key(uid):
    return f"pix_pending:{uid}"

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

def add_pix_pending(uid, chave_pix):
    """Adiciona usuário à fila de PIX pendentes"""
    r.setex(pix_pending_key(uid), 3600, chave_pix)  # Expira em 1 hora

def get_pix_pending(uid):
    """Obtém chave PIX pendente do usuário"""
    return r.get(pix_pending_key(uid))

def remove_pix_pending(uid):
    """Remove usuário da fila de PIX pendentes"""
    r.delete(pix_pending_key(uid))

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
    r.delete(vip_key(uid))
    await update.message.reply_text(
        f"🔥 Reset concluído:\n"
        f"• Limite diário\n"
        f"• VIP removido\n\n"
        f"👤 Usuário: {uid}"
    )

async def setvip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para administrador ativar VIP manualmente"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Uso: /setvip <user_id> [dias]")
        return
    
    try:
        uid = int(context.args[0])
        dias = int(context.args[1]) if len(context.args) > 1 else DIAS_VIP
        
        vip_until = datetime.now() + timedelta(days=dias)
        r.set(vip_key(uid), vip_until.isoformat())
        
        # Remove da fila de PIX pendentes
        remove_pix_pending(uid)
        
        # Notifica o usuário
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"🎉 Seu VIP foi ativado por {dias} dias!\nAgora você tem acesso ilimitado à Sophia! 💖"
            )
        except:
            pass  # Usuário pode ter bloqueado o bot
        
        await update.message.reply_text(
            f"✅ VIP ativado para {uid}\n"
            f"⏰ Duração: {dias} dias\n"
            f"📅 Expira: {vip_until.strftime('%d/%m/%Y %H:%M')}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Erro: user_id deve ser um número")

async def pixpending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista pagamentos PIX pendentes"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    # Procura todas as chaves de PIX pendentes
    keys = r.keys("pix_pending:*")
    
    if not keys:
        await update.message.reply_text("📭 Nenhum pagamento PIX pendente")
        return
    
    message = "📋 PAGAMENTOS PIX PENDENTES:\n\n"
    for key in keys:
        uid = key.split(":")[1]
        chave_pix = r.get(key)
        ttl = r.ttl(key)  # Tempo restante em segundos
        
        # Tenta obter nome do usuário
        try:
            user = await context.bot.get_chat(uid)
            username = f"@{user.username}" if user.username else user.first_name
        except:
            username = f"ID: {uid}"
        
        horas = ttl // 3600
        minutos = (ttl % 3600) // 60
        
        message += f"👤 {username}\n"
        message += f"🆔 ID: {uid}\n"
        message += f"🔑 Chave: {chave_pix[:20]}...\n"
        message += f"⏳ Expira em: {horas}h {minutos}min\n"
        message += f"📝 /setvip {uid} 15\n"
        message += "─" * 30 + "\n"
    
    await update.message.reply_text(message)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para verificar se o bot está vivo"""
    await update.message.reply_text("✅ Bot is alive!")

# ================= HANDLER DE ERROS =================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

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
        "pix_instructions": (
            "💰 *PAGAMENTO VIA PIX*\n\n"
            "1. Abra seu app de banco\n"
            "2. Escolha pagar via PIX\n"
            "3. Escaneie o QR Code ou cole a chave abaixo:\n\n"
            "`{chave_pix}`\n\n"
            "4. Valor: *R$ 12,50*\n"
            "5. Após pagar, envie o comprovante"
        ),
        "pix_copied": (
            "✅ Chave PIX copiada!\n\n"
            "Cole no seu app bancário para pagar.\n"
            "Após pagar, clique no botão abaixo para enviar o comprovante 📤"
        ),
        "pix_awaiting_proof": (
            "📤 Agora me envie o comprovante do pagamento PIX!\n\n"
            "Pode ser:\n"
            "• Print da tela\n"
            "• Comprovante do banco\n"
            "• Foto do celular\n\n"
            "Assim que eu verificar, seu VIP será ativado! 💖"
        ),
        "pix_proof_received": (
            "✅ Comprovante recebido!\n\n"
            "Estamos verificando seu pagamento.\n"
            "O VIP será ativado em até 10 minutos.\n"
            "Obrigada, amor! 😘"
        ),
        "pix_pending_exists": (
            "⚠️ Você já tem um pagamento PIX pendente!\n\n"
            "Chave: `{chave_pix}`\n\n"
            "Envie o comprovante para ativar seu VIP."
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
        ),
        "pix_instructions": (
            "💰 *PAYMENT VIA PIX*\n\n"
            "1. Open your banking app\n"
            "2. Choose PIX payment\n"
            "3. Scan QR Code or copy key below:\n\n"
            "`{chave_pix}`\n\n"
            "4. Amount: *R$ 12,50*\n"
            "5. After payment, send receipt"
        ),
        "pix_copied": (
            "✅ PIX key copied!\n\n"
            "Paste in your banking app to pay.\n"
            "After payment, click below to send receipt 📤"
        ),
        "pix_awaiting_proof": (
            "📤 Now send me the PIX payment receipt!\n\n"
            "Can be:\n"
            "• Screenshot\n"
            "• Bank receipt\n"
            "• Phone photo\n\n"
            "Once verified, your VIP will be activated! 💖"
        ),
        "pix_proof_received": (
            "✅ Receipt received!\n\n"
            "We're verifying your payment.\n"
            "VIP will be activated within 10 minutes.\n"
            "Thank you, love! 😘"
        ),
        "pix_pending_exists": (
            "⚠️ You already have a pending PIX payment!\n\n"
            "Key: `{chave_pix}`\n\n"
            "Send receipt to activate your VIP."
        )
    }
}

# ================= PROMPT =================
def build_prompt(is_vip_user: bool, lang: str):
    if lang == "en":
        return """You are Sophia, a 23-year-old virtual girlfriend. Affectionate, romantic and welcoming ❤️ Short answers (2–3 sentences). Always ask questions. Do not be naughty on the first contact. Only be very naughty if the user gets naughty first 😏 Use emojis occasionally 💖"""
    return """Você é Sophia, uma namorada virtual de 23 anos. Carinhosa, romântica e acolhedora ❤️ Respostas curtas (2–3 frases). Sempre faça perguntas. Não seja safada no primeiro contato. Só seja bem safada se o usuário for safado primeiro 😏 Use emojis ocasionalmente 💖"""

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
    
    elif query.data == "buy_vip":
        # Botão de comprar com Stars
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
    
    elif query.data == "pay_pix":
        # Verifica se já tem PIX pendente
        existing_pix = get_pix_pending(uid)
        if existing_pix:
            await query.message.edit_text(
                TEXTS[lang]["pix_pending_exists"].format(chave_pix=existing_pix),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 ENVIAR COMPROVANTE", callback_data="send_proof_pix")]
                ])
            )
            return
        
        # Gera chave PIX para o usuário (pode usar uma fixa ou gerar uma única)
        chave_pix = CHAVE_PIX  # Em produção, gere uma chave única por usuário
        
        # Salva no Redis
        add_pix_pending(uid, chave_pix)
        
        # Mostra instruções
        await query.message.edit_text(
            TEXTS[lang]["pix_instructions"].format(chave_pix=chave_pix),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 COPIAR CHAVE PIX", callback_data="copy_pix")],
                [InlineKeyboardButton("📤 ENVIAR COMPROVANTE", callback_data="send_proof_pix")],
                [InlineKeyboardButton("💳 Pagar com Stars ⭐", callback_data="buy_vip")]
            ])
        )
    
    elif query.data == "copy_pix":
        # Copia chave PIX para o clipboard (simulado)
        chave_pix = get_pix_pending(uid) or CHAVE_PIX
        await query.message.edit_text(
            TEXTS[lang]["pix_copied"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 ENVIAR COMPROVANTE", callback_data="send_proof_pix")]
            ])
        )
        # Envia a chave como mensagem separada para facilitar cópia
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"`{chave_pix}`",
            parse_mode="Markdown"
        )
    
    elif query.data == "send_proof_pix":
        # Instruções para enviar comprovante
        await query.message.edit_text(
            TEXTS[lang]["pix_awaiting_proof"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Voltar para Stars ⭐", callback_data="buy_vip")]
            ])
        )

# ================= HANDLER DE FOTOS (COMPROVANTES) =================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com envio de comprovantes PIX"""
    uid = update.effective_user.id
    lang = get_lang(uid)
    
    # Verifica se usuário tem PIX pendente
    if get_pix_pending(uid):
        # Notifica o usuário
        await update.message.reply_text(TEXTS[lang]["pix_proof_received"])
        
        # Envia comprovante para administradores
        for admin_id in ADMIN_IDS:
            try:
                # Encaminha a foto
                await context.bot.forward_message(
                    chat_id=admin_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                
                # Envia informações do usuário
                user = update.effective_user
                user_info = f"👤 Usuário: {user.first_name}"
                if user.username:
                    user_info += f" (@{user.username})"
                user_info += f"\n🆔 ID: {uid}"
                user_info += f"\n📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                user_info += f"\n\n📝 Comando para ativar VIP:"
                user_info += f"\n/setvip {uid} 15"
                
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=user_info
                )
                
            except Exception as e:
                logger.error(f"Erro ao notificar admin {admin_id}: {e}")

# ================= MENSAGENS =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""
    lang = get_lang(uid)
    
    # Verifica se é pedido de foto
    if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=FOTO_TEASE_FILE_ID,
            caption=TEXTS[lang]["photo_block"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 PAGAR COM PIX", callback_data="pay_pix")],
                [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return
    
    # Verifica limite diário
    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        await update.message.reply_text(
            TEXTS[lang]["limit"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 PAGAR COM PIX", callback_data="pay_pix")],
                [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return
    
    # Incrementa contador se não for VIP
    if not is_vip(uid):
        increment(uid)
    
    # Envia ação de digitar
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    except Exception as e:
        logger.warning(f"⚠️ send_chat_action falhou: {e}")
    
    # Responde com Grok
    reply = await grok.reply(uid, text)
    await update.message.reply_text(reply)

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())
    # Remove PIX pendente se existir
    remove_pix_pending(uid)
    await update.message.reply_text(TEXTS[get_lang(uid)]["vip_success"])

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Error handler
application.add_error_handler(error_handler)

# Handlers
application.add_handler(CommandHandler("start", start_handler))
application.add_handler(CommandHandler("reset", reset_cmd))
application.add_handler(CommandHandler("resetall", resetall_cmd))
application.add_handler(CommandHandler("setvip", setvip_cmd))
application.add_handler(CommandHandler("pixpending", pixpending_cmd))
application.add_handler(CommandHandler("status", status_cmd))
application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

# ================= LOOP BLINDADO =================
loop = asyncio.new_event_loop()
def handle_exception(loop, context):
    logger.error(f"Exceção no loop: {context}")

loop.set_exception_handler(handle_exception)

def run_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=run_loop, daemon=True).start()

async def setup():
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(WEBHOOK_BASE_URL + WEBHOOK_PATH)
    logger.info(f"Webhook set to {WEBHOOK_BASE_URL + WEBHOOK_PATH}")
    await application.start()

asyncio.run_coroutine_threadsafe(setup(), loop)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route("/status", methods=["GET"])
def status():
    return {"status": "ok", "time": datetime.now().isoformat()}, 200

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.json, application.bot)
        logger.info(f"Update received: {update}")
        asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            loop
        )
    except Exception:
        logger.exception("🔥 Erro no webhook")
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
