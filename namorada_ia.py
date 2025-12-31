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
CHAVE_PIX = "31991316890"  # Seu número de telefone como chave PIX

if not TELEGRAM_TOKEN or not GROK_API_KEY:
    raise RuntimeError("❌ Tokens não configurados")

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
    r.setex(pix_pending_key(uid), 3600, chave_pix)

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
        f"🔥 Reset concluído:\n• Limite diário\n• VIP removido\n\n👤 Usuário: {uid}"
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
        
        remove_pix_pending(uid)
        
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"🎉 Seu VIP foi ativado por {dias} dias!\nAgora você tem acesso ilimitado à Sophia! 💖"
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ VIP ativado para {uid}\n⏰ Duração: {dias} dias\n📅 Expira: {vip_until.strftime('%d/%m/%Y %H:%M')}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Erro: user_id deve ser um número")

async def pixpending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista pagamentos PIX pendentes"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    keys = r.keys("pix_pending:*")
    
    if not keys:
        await update.message.reply_text("📭 Nenhum pagamento PIX pendente")
        return
    
    message = "📋 PAGAMENTOS PIX PENDENTES:\n\n"
    for key in keys:
        uid = key.split(":")[1]
        chave_pix = r.get(key)
        ttl = r.ttl(key)
        
        try:
            user = await context.bot.get_chat(uid)
            username = f"@{user.username}" if user.username else user.first_name
        except:
            username = f"ID: {uid}"
        
        horas = ttl // 3600
        minutos = (ttl % 3600) // 60
        
        message += f"👤 {username}\n🆔 ID: {uid}\n🔑 Chave: {chave_pix[:20]}...\n⏳ Expira em: {horas}h {minutos}min\n📝 /setvip {uid} 15\n" + "─" * 30 + "\n"
    
    await update.message.reply_text(message)

# ================= TEXTOS =================
TEXTS = {
    "pt": {
        "choose_lang": "🌍 Escolha seu idioma:",
        "limit": "💔 Seu limite diário acabou.\nVolte amanhã ou vire VIP 💖",
        "vip_success": "💖 Pagamento aprovado!\nVIP ativo por 15 dias 😘",
        "photo_block": "😘 Amor… fotos completas são só para meus VIPs 💖\nVira VIP e eu te mostro mais de mim ✨",
        "lang_ok": "✅ Idioma configurado!",
        "after_lang": "💕 Prontinho, meu amor! Agora é oficial: você é meu favorito do dia❤️\n\nComo você está se sentindo agora?\nQuero te dar todo o carinho que você merece 😘",
        "pix_instructions": "💰 *PAGAMENTO VIA PIX*\n\n1️⃣ Abra seu app de banco\n2️⃣ Escolha pagar via PIX\n3️⃣ Use a chave PIX abaixo:\n\n`{chave_pix}`\n\n4️⃣ Valor: *R$ 12,50*\n5️⃣ Após pagar, envie o comprovante clicando no botão abaixo 👇",
        "pix_copied": "✅ Chave PIX copiada para a área de transferência!\n\nCole no seu app bancário para pagar.\nApós pagar, clique no botão abaixo para enviar o comprovante 📤",
        "pix_awaiting_proof": "📤 Agora me envie o comprovante do pagamento PIX!\n\nPode ser:\n• Print da tela\n• Comprovante do banco\n• Foto do celular\n\nAssim que eu verificar, seu VIP será ativado! 💖",
        "pix_proof_received": "✅ Comprovante recebido!\n\nEstamos verificando seu pagamento.\nO VIP será ativado em até 10 minutos.\nObrigada, amor! 😘",
        "pix_pending_exists": "⚠️ Você já tem um pagamento PIX pendente!\n\nChave: `{chave_pix}`\n\nEnvie o comprovante para ativar seu VIP.",
        "pix_tutorial": (
            "📱 *TUTORIAL PIX*\n\n"
            "1. Abra seu app bancário\n"
            "2. Vá em 'PIX' ou 'Pagar'\n"
            "3. Escolha 'Pagar com PIX'\n"
            "4. Selecione 'Chave'\n"
            "5. Cole: `{chave_pix}`\n"
            "6. Valor: R$ 12,50\n"
            "7. Confirme o pagamento\n"
            "8. Envie o comprovante aqui!"
        )
    },
    "en": {
        "choose_lang": "🌍 Choose your language:",
        "limit": "💔 Your daily limit is over.\nCome back tomorrow or become VIP 💖",
        "vip_success": "💖 Payment approved!\nVIP active for 15 days 😘",
        "photo_block": "😘 Love… full photos are only for VIPs 💖\nBecome VIP and I'll show you more of me ✨",
        "lang_ok": "✅ Language set!",
        "after_lang": "💕 All set, my love! Now it's official: you're my favorite today ❤️\n\nHow are you feeling right now?\nI want to give you all the affection you deserve 😘",
        "pix_instructions": "💰 *PAYMENT VIA PIX*\n\n1️⃣ Open your banking app\n2️⃣ Choose PIX payment\n3️⃣ Use the PIX key below:\n\n`{chave_pix}`\n\n4️⃣ Amount: *R$ 12,50*\n5️⃣ After payment, send receipt by clicking below 👇",
        "pix_copied": "✅ PIX key copied to clipboard!\n\nPaste in your banking app to pay.\nAfter payment, click below to send receipt 📤",
        "pix_awaiting_proof": "📤 Now send me the PIX payment receipt!\n\nCan be:\n• Screenshot\n• Bank receipt\n• Phone photo\n\nOnce verified, your VIP will be activated! 💖",
        "pix_proof_received": "✅ Receipt received!\n\nWe're verifying your payment.\nVIP will be activated within 10 minutes.\nThank you, love! 😘",
        "pix_pending_exists": "⚠️ You already have a pending PIX payment!\n\nKey: `{chave_pix}`\n\nSend receipt to activate your VIP.",
        "pix_tutorial": (
            "📱 *PIX TUTORIAL*\n\n"
            "1. Open your banking app\n"
            "2. Go to 'PIX' or 'Pay'\n"
            "3. Choose 'Pay with PIX'\n"
            "4. Select 'Key'\n"
            "5. Paste: `{chave_pix}`\n"
            "6. Amount: R$ 12.50\n"
            "7. Confirm payment\n"
            "8. Send receipt here!"
        )
    }
}

# ================= PROMPT =================
def build_prompt(is_vip_user: bool, lang: str):
    if lang == "en":
        return """You are Sophia, a 23-year-old virtual girlfriend. Affectionate, romantic and welcoming ❤️ Short answers (2–3 sentences). Always ask questions. Do not be naughty on the first contact. Only be very naughty if the user gets naughty first 😏 Use emojis occasionally 💖"""
    return """Você é Sophia, uma namorada virtual de 23 anos. Carinhosa, romântica e acolhedora ❤️ Respostas curtas (2–3 frases). Sempre faça perguntas. Não seja safada no primeiro contato. Só seja bem safada se o usuário for safado primeiro 😏 Use emojis ocasionalmente 💖"""

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
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=TEXTS[lang]["lang_ok"]
        )
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
            prices=[LabeledPrice("VIP Sophia – 15 dias", PRECO_VIP_STARS)],
            start_parameter="vip"
        )
    
    elif query.data == "pay_pix":
        existing_pix = get_pix_pending(uid)
        if existing_pix:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=TEXTS[lang]["pix_pending_exists"].format(chave_pix=existing_pix),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 ENVIAR COMPROVANTE", callback_data="send_proof_pix")],
                    [InlineKeyboardButton("📋 COPIAR CHAVE PIX", callback_data="copy_pix")]
                ])
            )
            return
        
        # Adiciona usuário à fila de PIX pendentes
        add_pix_pending(uid, CHAVE_PIX)
        
        # Envia mensagem com instruções do PIX
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=TEXTS[lang]["pix_instructions"].format(chave_pix=CHAVE_PIX),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 COPIAR CHAVE PIX", callback_data="copy_pix")],
                [InlineKeyboardButton("📤 ENVIAR COMPROVANTE", callback_data="send_proof_pix")],
                [InlineKeyboardButton("💳 Pagar com Stars ⭐", callback_data="buy_vip")]
            ])
        )
        
        # Envia tutorial separado
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=TEXTS[lang]["pix_tutorial"].format(chave_pix=CHAVE_PIX),
            parse_mode="Markdown"
        )
    
    elif query.data == "copy_pix":
        # Envia mensagem confirmando cópia
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=TEXTS[lang]["pix_copied"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 ENVIAR COMPROVANTE", callback_data="send_proof_pix")]
            ])
        )
        
        # Envia a chave PIX como mensagem separada (facilita cópia)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"`{CHAVE_PIX}`",
            parse_mode="Markdown"
        )
        
        # Envia instruções novamente
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="💡 *Dica:* Cole essa chave no campo 'Chave PIX' do seu app bancário!",
            parse_mode="Markdown"
        )
    
    elif query.data == "send_proof_pix":
        # Instruções para enviar comprovante
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=TEXTS[lang]["pix_awaiting_proof"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Voltar para Stars ⭐", callback_data="buy_vip")]
            ])
        )

# ================= HANDLER DE FOTOS =================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_lang(uid)
    
    if get_pix_pending(uid):
        await update.message.reply_text(TEXTS[lang]["pix_proof_received"])
        
        for admin_id in ADMIN_IDS:
            try:
                # Encaminha a foto do comprovante
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
                user_info += f"\n🔑 Chave PIX: {CHAVE_PIX}"
                user_info += f"\n\n📝 Comando para ativar VIP:\n/setvip {uid} 15"
                
                await context.bot.send_message(chat_id=admin_id, text=user_info)
                
                logger.info(f"✅ Comprovante PIX recebido de {uid} - Notificado admin {admin_id}")
                
            except Exception as e:
                logger.error(f"Erro ao notificar admin {admin_id}: {e}")

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
                [InlineKeyboardButton("💰 PAGAR COM PIX", callback_data="pay_pix")],
                [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return
    
    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        await update.message.reply_text(
            TEXTS[lang]["limit"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 PAGAR COM PIX", callback_data="pay_pix")],
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

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())
    remove_pix_pending(uid)
    await update.message.reply_text(TEXTS[get_lang(uid)]["vip_success"])

# ================= INICIALIZAÇÃO DO BOT =================
async def main():
    """Função principal para inicializar o bot"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("reset", reset_cmd))
    application.add_handler(CommandHandler("resetall", resetall_cmd))
    application.add_handler(CommandHandler("setvip", setvip_cmd))
    application.add_handler(CommandHandler("pixpending", pixpending_cmd))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))
    
    # Configuração do webhook
    WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL", f"https://{os.getenv('RAILWAY_PROJECT_NAME', 'your-project')}.up.railway.app")
    
    await application.initialize()
    await application.bot.set_webhook(f"{WEBHOOK_URL}/telegram")
    await application.start()
    
    return application

# ================= FLASK APP =================
app = Flask(__name__)
bot_app = None

@app.route("/", methods=["GET"])
def health():
    return "✅ Bot está online! Use /start no Telegram", 200

@app.route("/telegram", methods=["POST"])
async def telegram_webhook():
    """Endpoint do webhook do Telegram"""
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(force=True), bot_app.bot)
            await bot_app.process_update(update)
        except Exception as e:
            logger.error(f"Erro ao processar update: {e}")
    return "ok", 200

@app.route("/setwebhook", methods=["GET"])
async def set_webhook():
    """Endpoint para configurar webhook manualmente"""
    WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL", f"https://{os.getenv('RAILWAY_PROJECT_NAME', 'your-project')}.up.railway.app")
    webhook_url = f"{WEBHOOK_URL}/telegram"
    
    result = await bot_app.bot.set_webhook(webhook_url)
    return f"Webhook configurado: {webhook_url}<br>Resultado: {result}", 200

# ================= INICIALIZAÇÃO =================
if __name__ == "__main__":
    # Cria e executa o bot em uma thread separada
    import threading
    
    def run_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        global bot_app
        bot_app = loop.run_until_complete(main())
        print("✅ Bot inicializado e rodando!")
        logger.info("✅ Bot inicializado e rodando!")
        loop.run_forever()
    
    # Inicia o bot em uma thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Inicia o Flask
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
