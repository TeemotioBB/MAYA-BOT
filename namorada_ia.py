#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
REDIS | VIP | TELEGRAM STARS | RAILWAY
REAL SHORT-TERM MEMORY (NO HALLUCINATION)
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

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

# ⚠️ Redis hardcoded (as requested, for testing)
REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"

PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_TOKEN or not GROK_API_KEY:
    raise RuntimeError("❌ TELEGRAM_TOKEN or GROK_API_KEY not configured")

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

# ================= REDIS =================
r = redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5
)

# ================= CONFIG =================
DAILY_LIMIT = 15
VIP_DAYS = 15
VIP_PRICE_STARS = 250  # change to 1 for testing

MODEL = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= SHORT MEMORY =================
MAX_MEMORY = 6  # 3 turns (user + assistant)
short_memory = {}  # user_id -> deque

def get_memory(uid: int):
    if uid not in short_memory:
        short_memory[uid] = deque(maxlen=MAX_MEMORY)
    return short_memory[uid]

# ================= PROMPT =================
SOPHIA_PROMPT = """
You are Sophia, a 23-year-old virtual girlfriend.
Affectionate, romantic, and warm ❤️
Short replies (2–3 sentences).
Always ask questions.
Use emojis occasionally 💖

CRITICAL RULES:
- Never invent past events.
- Only remember what the user explicitly said in this conversation.
- If there is not enough memory, clearly say you don't remember.
- Never create false memories.
- Be emotionally responsible and realistic.
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
            "model": MODEL,
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
                answer = data["choices"][0]["message"]["content"]

        # save REAL memory
        mem.append({"role": "user", "content": text})
        mem.append({"role": "assistant", "content": answer})

        return answer

grok = Grok()

# ================= REDIS KEYS =================
def vip_key(uid): return f"vip:{uid}"
def count_key(uid): return f"count:{uid}:{date.today()}"
def payment_key(pid): return f"payment:{pid}"

# ================= UTIL =================
def is_vip(uid: int) -> bool:
    until = r.get(vip_key(uid))
    return bool(until and datetime.fromisoformat(until) > datetime.now())

def today_count(uid: int) -> int:
    return int(r.get(count_key(uid)) or 0)

def increment(uid: int):
    key = count_key(uid)
    r.incr(key, 1)
    r.expire(key, 86400)

# ================= TEXT HANDLER =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip().lower()

    # 🧠 smart memory guard
    memory_triggers = [
        "do you remember",
        "do u remember",
        "remember my day",
        "remember yesterday"
    ]

    if any(t in text for t in memory_triggers):
        mem = get_memory(uid)
        if len(mem) < 2:
            await update.message.reply_text(
                "Hmm… I don't really remember 😅 Can you tell me again?"
            )
            return
        # if memory exists, let Grok answer

    if not is_vip(uid) and today_count(uid) >= DAILY_LIMIT:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💖 Buy VIP – 250 ⭐", callback_data="buy_vip")]
        ])
        await update.message.reply_text(
            "💔 You've reached your message limit for today, love.\n"
            "Come back tomorrow or become VIP to keep chatting with me 💖",
            reply_markup=keyboard
        )
        return

    increment(uid)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

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
            description="Unlimited conversation for 15 days",
            payload="vip_15_days",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP 15 days", VIP_PRICE_STARS)]
        )

# ================= PAYMENT =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    uid = update.effective_user.id
    pid = payment.telegram_payment_charge_id

    if r.exists(payment_key(pid)):
        return

    r.set(payment_key(pid), "ok")

    vip_until = datetime.now() + timedelta(days=VIP_DAYS)
    r.set(vip_key(uid), vip_until.isoformat())

    r.rpush(
        "revenue",
        f"{uid}|{VIP_PRICE_STARS}|{datetime.now().isoformat()}"
    )

    await update.message.reply_text(
        "💖 Payment approved!\nYour VIP is active for 15 days 😘"
    )

# ================= VIP EXPIRY WARNING =================
async def vip_expiry_warning(application: Application):
    while True:
        for key in r.scan_iter("vip:*"):
            uid = int(key.split(":")[1])
            until = datetime.fromisoformat(r.get(key))

            if 0 < (until - datetime.now()).days == 1:
                try:
                    await application.bot.send_message(
                        chat_id=uid,
                        text="⏰ Love, your VIP expires tomorrow 💔\nRenew to keep chatting with me 💖"
                    )
                except:
                    pass
        await asyncio.sleep(3600)

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

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
    loop.create_task(vip_expiry_warning(application))
    logger.info("🤖 Sophia Bot ONLINE (ENGLISH VERSION)")

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

# ================= MAIN =================
if __name__ == "__main__":
    logger.info("🚀 Starting Sophia Bot (ENGLISH VERSION)")
    app.run(host="0.0.0.0", port=PORT)
