#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
WEBHOOK FIXO | LIMITE DIÁRIO | VIP COM TELEGRAM STARS
python-telegram-bot v20+
"""

import os
import asyncio
import logging
import threading
import aiohttp
from datetime import datetime, timedelta, date
from flask import Flask, request

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

# ================= TOKENS =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
PORT = int(os.getenv("PORT", 8080))

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

# ================= GROK =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-4-fast-reasoning"

SOPHIA_PROMPT = """
Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica e afetuosa ❤️
Respostas curtas (2–3 frases).
Sempre faça perguntas.
Use emojis ocasionalmente 💖
"""

# ================= CONFIGURAÇÕES =================
LIMITE_DIARIO = 15
VIP_DIAS = 15
VIP_PRECO_STARS = 250
MEMORIA_MAX = 10

mensagens_hoje = {}     # user_id -> {date, count}
vip_usuarios = {}      # user_id -> datetime
memoria_usuarios = {}  # user_id -> histórico curto

# ================= GROK =================
class Grok:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }

    async def responder(self, user_id: int, texto: str) -> str:
        historico = memoria_usuarios.setdefault(user_id, [])

        mensagens = [
            {"role": "system", "content": SOPHIA_PROMPT},
            *historico,
            {"role": "user", "content": texto}
        ]

        payload = {
            "model": MODEL,
            "messages": mensagens,
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
                resposta = data["choices"][0]["message"]["content"]

        historico.extend([
            {"role": "user", "content": texto},
            {"role": "assistant", "content": resposta}
        ])

        if len(historico) > MEMORIA_MAX:
            memoria_usuarios[user_id] = historico[-MEMORIA_MAX:]

        return resposta

grok = Grok()

# ================= UTIL =================
def is_vip(user_id: int) -> bool:
    return user_id in vip_usuarios and vip_usuarios[user_id] > datetime.now()

def limite_excedido(user_id: int) -> bool:
    hoje = date.today()
    dados = mensagens_hoje.setdefault(user_id, {"date": hoje, "count": 0})

    if dados["date"] != hoje:
        dados["date"] = hoje
        dados["count"] = 0

    return dados["count"] >= LIMITE_DIARIO

def incrementar(user_id: int):
    mensagens_hoje[user_id]["count"] += 1

# ================= HANDLER TEXTO =================
async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.effective_user.id

    if not is_vip(user_id):
        if limite_excedido(user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="comprar_vip")]
            ])
            await update.message.reply_text(
                "💔 Seu limite de mensagens comigo encerrou por hoje, amor.\n"
                "Volte amanhã ou se torne meu cliente VIP 💖",
                reply_markup=keyboard
            )
            return
        else:
            incrementar(user_id)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    resposta = await grok.responder(user_id, texto)
    await update.message.reply_text(resposta)

# ================= CALLBACK BOTÃO =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "comprar_vip":
        prices = [LabeledPrice("VIP 15 dias", VIP_PRECO_STARS)]

        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="VIP Sophia 💖",
            description="Conversa ilimitada por 15 dias",
            payload="vip_15_dias",
            provider_token="",
            currency="XTR",
            prices=prices
        )

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def pagamento_sucesso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload

    if payload == "vip_15_dias":
        vip_usuarios[user_id] = datetime.now() + timedelta(days=VIP_DIAS)
        await update.message.reply_text(
            "💖 Pagamento aprovado!\n"
            "Agora você pode conversar comigo sem limites por 15 dias 😘"
        )

# ================= APP TELEGRAM =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, pagamento_sucesso))

# ================= LOOP ASYNC =================
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
    logger.info("🤖 Sophia Bot iniciado")

asyncio.run_coroutine_threadsafe(setup(), loop)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Sophia Bot online"

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.run_coroutine_threadsafe(
        application.process_update(update),
        loop
    )
    return "ok", 200

# ================= MAIN =================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Sophia Bot")
    app.run(host="0.0.0.0", port=PORT)
