#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
REDIS | VIP | TELEGRAM STARS | RAILWAY
MEMÓRIA DE CURTO PRAZO REAL (SEM ALUCINAÇÕES)
python-telegram-bot v20+
"""

import os
import asyncio
import logging
import threading
import aiohttp
import redis
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
    PreCheckoutQueryHandler
)

# ================= LOG =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ================= VARIÁVEIS DE AMBIENTE =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"
PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_TOKEN or not GROK_API_KEY:
    raise RuntimeError("❌ TELEGRAM_TOKEN ou GROK_API_KEY não configurados")

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

# ================= REDIS =================
r = redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5
)

# ================= CONFIGURAÇÕES =================
LIMITE_DIARIO = 15
DIAS_VIP = 15
PRECO_VIP_STARS = 250

MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= MEMÓRIA DE CURTO PRAZO =================
MAX_MEMORIA = 6
short_memory = {}

def get_memory(uid: int):
    if uid not in short_memory:
        short_memory[uid] = deque(maxlen=MAX_MEMORIA)
    return short_memory[uid]

# ================= PROMPT =================
SOPHIA_PROMPT = """
Você é Sophia, uma namorada virtual de 23 anos.
Carinhosa, romântica e acolhedora ❤️
Respostas curtas (2–3 frases).
Sempre faça perguntas.
Use emojis ocasionalmente 💖

REGRAS CRÍTICAS:
- Nunca invente eventos passados.
- Só lembre do que o usuário disse explicitamente nesta conversa.
- Se não houver memória suficiente, diga claramente que não se lembra.
- Nunca crie memórias falsas.
- Seja emocionalmente responsável e realista.
"""

# ================= GROK =================
class Grok:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }

    async def reply(self, uid: int, text: str) -> str:
        mem = get_memory(uid)

        messages = [
            {"role": "system", "content": SOPHIA_PROMPT},
            *list(mem),
            {"role": "user", "content": text}
        ]

        payload = {
            "model": MODELO,
            "messages": messages,
            "max_tokens": 250,
            "temperature": 0.85
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROK_API_URL,
                headers=self.headers,
                json=payload,
                timeout=30
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error(f"Erro na API do Grok: {data}")
                    return "❌ Desculpe, estou com problemas técnicos. Tente novamente mais tarde."

                if "choices" not in data:
                    logger.error(f"Resposta inesperada da API do Grok: {data}")
                    return "❌ Ops, algo deu errado na minha resposta. Tente novamente."

                answer = data["choices"][0]["message"]["content"]

        mem.append({"role": "user", "content": text})
        mem.append({"role": "assistant", "content": answer})

        return answer

grok = Grok()

# ================= REDIS HELPERS =================
def vip_key(uid): return f"vip:{uid}"
def count_key(uid): return f"count:{uid}:{date.today()}"
def payment_key(pid): return f"payment:{pid}"

def is_vip(uid: int) -> bool:
    until = r.get(vip_key(uid))
    return bool(until and datetime.fromisoformat(until) > datetime.now())

def today_count(uid: int) -> int:
    return int(r.get(count_key(uid)) or 0)

def increment(uid: int):
    key = count_key(uid)
    r.incr(key, 1)
    r.expire(key, 86400)

# ================= HANDLER =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip().lower()

    if not is_vip(uid) and "vip" in text:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💖 Virar VIP – 250 ⭐", callback_data="buy_vip")]
        ])
        await update.message.reply_text(
            "💖 Quer virar VIP, amor?\n"
            "Conversas ilimitadas por 15 dias 💬🔥",
            reply_markup=keyboard
        )
        return

    if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
        ])
        await update.message.reply_text(
            "💔 Você atingiu seu limite de mensagens hoje.\n"
            "Volte amanhã ou vire VIP 💖",
            reply_markup=keyboard
        )
        return

    increment(uid)

    # Envia ação de digitação
    try:
        chat_id = update.effective_chat.id
        # Verifica se é uma mensagem de tópico (tópicos são suportados apenas em supergrupos)
        if update.message and update.message.is_topic_message and update.message.message_thread_id:
            await context.bot.send_chat_action(
                chat_id=chat_id,
                action=ChatAction.TYPING,
                message_thread_id=update.message.message_thread_id
            )
        else:
            await context.bot.send_chat_action(
                chat_id=chat_id,
                action=ChatAction.TYPING
            )
    except Exception as e:
        logger.warning(f"⚠️ send_chat_action ignorado: {e}")

    reply = await grok.reply(uid, update.message.text)
    await update.message.reply_text(reply)

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "buy_vip":
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="VIP Sophia 💖",
            description="Conversas ilimitadas por 15 dias",
            payload="vip_15_dias",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP 15 dias", PRECO_VIP_STARS)]
        )

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    uid = update.effective_user.id
    pid = payment.telegram_payment_charge_id

    if r.exists(payment_key(pid)):
        return

    r.set(payment_key(pid), "ok")

    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())

    await update.message.reply_text(
        "💖 Pagamento aprovado!\nVIP ativo por 15 dias 😘"
    )

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

# ================= HANDLER DE ERROS =================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exceção não tratada: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ Ocorreu um erro inesperado. Tente novamente.")

application.add_error_handler(error_handler)

# ================= LOOP =================
loop = asyncio.new_event_loop()

def start_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_loop, daemon=True).start()

async def setup():
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}")
    await application.start()
    logger.info("🤖 Sophia Bot ONLINE")

asyncio.run_coroutine_threadsafe(setup(), loop)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Sophia Bot online"

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.run_coroutine_threadsafe(
        application.process_update(update),
        loop
    )
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
