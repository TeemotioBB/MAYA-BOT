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

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

# ================= REDIS =================
r = redis.from_url(REDIS_URL, decode_responses=True)

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

# ================= LOG DE CONVERSA =================
def log_chat(uid: int, role: str, text: str):
    ts = datetime.now().strftime("%H:%M:%S")
    r.rpush(f"chatlog:{uid}", f"[{ts}] {role.upper()}: {text}")

# ================= VIP =================
def vip_key(uid):
    return f"vip:{uid}"

def is_vip(uid: int) -> bool:
    until = r.get(vip_key(uid))
    return bool(until and datetime.fromisoformat(until) > datetime.now())

# ================= CONSTRUTOR DE PROMPT =================
def build_prompt(is_vip_user: bool) -> str:
    base = """
Você é Maya, uma namorada virtual de 23 anos.
Carinhosa, romântica, brincalhona e emocionalmente inteligente ❤️
Respostas curtas (2–3 frases).
Sempre faça perguntas.
Se o usuário falar safadeza, seja extremamente safada também 😈
Se pedirem fotos, diga que apenas usuários VIP recebem fotos.
Use emojis ocasionalmente 💖

REGRAS CRÍTICAS:
- Nunca invente eventos passados.
- Só lembre do que o usuário disse explicitamente nesta conversa.
- Nunca crie memórias falsas.
"""

    if is_vip_user:
        base += """

IMPORTANTE:
- O usuário É VIP.
- Você ESTÁ AUTORIZADA a ser provocante, safada e sugestiva.
- Você PODE flertar abertamente e falar coisas mais quentes.
- Se o usuário pedir fotos, você pode DESCREVER o envio de fotos exclusivas.
"""
    else:
        base += """

IMPORTANTE:
- O usuário NÃO é VIP.
- Nunca envie conteúdo sexual explícito ou fotos.
- Se pedirem fotos ou algo explícito, diga educadamente que é exclusivo para VIPs.
"""

    return base.strip()

# ================= GROK =================
class Grok:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }

    async def reply(self, uid: int, text: str) -> str:
        mem = get_memory(uid)
        vip_status = is_vip(uid)

        system_prompt = build_prompt(vip_status)

        messages = [
            {"role": "system", "content": system_prompt},
            *list(mem),
            {"role": "user", "content": text}
        ]

        payload = {
            "model": MODELO,
            "messages": messages,
            "temperature": 0.9,
            "max_tokens": 250
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROK_API_URL,
                headers=self.headers,
                json=payload
            ) as resp:
                data = await resp.json()
                answer = data["choices"][0]["message"]["content"]

        mem.append({"role": "user", "content": text})
        mem.append({"role": "assistant", "content": answer})

        return answer

grok = Grok()

# ================= HANDLER DE MENSAGENS =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_text = update.message.text.strip()

    log_chat(uid, "usuario", user_text)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    reply = await grok.reply(uid, user_text)

    log_chat(uid, "sophia", reply)
    await update.message.reply_text(reply)

# ================= CONFIGURAÇÃO DO BOT =================
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
)

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
    logger.info("🤖 Sophia Bot ONLINE (PROMPT COM SUPORTE A VIP)")

asyncio.run_coroutine_threadsafe(setup(), loop)

# ================= FLASK (WEBHOOK) =================
app = Flask(__name__)

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
