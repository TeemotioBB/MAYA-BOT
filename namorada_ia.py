#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok + OpenAI (Vision + Whisper)
REDIS | VIP | SHORT-TERM MEMORY | RAILWAY
python-telegram-bot v20+
"""

import os
import asyncio
import logging
import threading
import aiohttp
import redis
import base64
import tempfile
from datetime import datetime, timedelta, date
from flask import Flask, request
from collections import deque

import openai

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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not GROK_API_KEY or not OPENAI_API_KEY:
    raise RuntimeError("❌ Missing TELEGRAM_TOKEN / GROK_API_KEY / OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"

PORT = int(os.getenv("PORT", 8080))

WEBHOOK_BASE_URL = "https://maya-bot-production.up.railway.app"
WEBHOOK_PATH = "/telegram"

# ================= REDIS =================
r = redis.from_url(REDIS_URL, decode_responses=True)

# ================= CONFIG =================
DAILY_LIMIT = 15
VIP_DAYS = 15
VIP_PRICE_STARS = 250  # use 1 to test

GROK_MODEL = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= MEMORY =================
MAX_MEMORY = 6
short_memory = {}

def get_memory(uid: int):
    if uid not in short_memory:
        short_memory[uid] = deque(maxlen=MAX_MEMORY)
    return short_memory[uid]

# ================= LOG CHAT =================
def log_chat(uid: int, role: str, text: str):
    ts = datetime.now().strftime("%H:%M:%S")
    r.rpush(f"chatlog:{uid}", f"[{ts}] {role.upper()}: {text}")

# ================= VIP =================
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

# ================= PROMPT =================
def build_prompt(vip: bool) -> str:
    base = """
You are Sophia, a virtual girlfriend.
Warm, affectionate and playful ❤️
Short replies (2–3 sentences).
Always ask questions.
Use emojis occasionally 💖

RULES:
- Never invent memories.
- Only remember what was said in this conversation.
- If unsure, say you don't remember.
"""
    if vip:
        base += """
VIP CONTEXT:
- The user is VIP.
- You may be more intimate and playful.
"""
    else:
        base += """
NON-VIP CONTEXT:
- Avoid exclusive content.
- Politely explain VIP benefits when relevant.
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
        system_prompt = build_prompt(is_vip(uid))

        messages = [
            {"role": "system", "content": system_prompt},
            *list(mem),
            {"role": "user", "content": text}
        ]

        payload = {
            "model": GROK_MODEL,
            "messages": messages,
            "temperature": 0.9,
            "max_tokens": 250
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(GROK_API_URL, headers=self.headers, json=payload) as resp:
                data = await resp.json()
                answer = data["choices"][0]["message"]["content"]

        mem.append({"role": "user", "content": text})
        mem.append({"role": "assistant", "content": answer})
        return answer

grok = Grok()

# ================= OPENAI — IMAGE =================
async def analyze_image(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode()
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image briefly and objectively."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
            ]
        }],
        max_tokens=120
    )
    return response.choices[0].message.content

# ================= OPENAI — AUDIO =================
async def transcribe_audio(audio_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".ogg") as f:
        f.write(audio_bytes)
        f.flush()
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=open(f.name, "rb")
        )
    return transcript["text"]

# ================= HANDLERS =================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    log_chat(uid, "user", text)

    if not is_vip(uid) and today_count(uid) >= DAILY_LIMIT:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💖 Buy VIP", callback_data="buy_vip")]
        ])
        msg = "You've reached today's limit. Come back tomorrow or become VIP 💖"
        log_chat(uid, "sophia", msg)
        await update.message.reply_text(msg, reply_markup=keyboard)
        return

    increment(uid)
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    reply = await grok.reply(uid, text)
    log_chat(uid, "sophia", reply)
    await update.message.reply_text(reply)

async def image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photo = update.message.photo[-1]

    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()

    description = await analyze_image(image_bytes)
    log_chat(uid, "image", description)

    reply = await grok.reply(uid, f"The user sent an image: {description}")
    log_chat(uid, "sophia", reply)
    await update.message.reply_text(reply)

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    voice = update.message.voice

    file = await voice.get_file()
    audio_bytes = await file.download_as_bytearray()

    text = await transcribe_audio(audio_bytes)
    log_chat(uid, "voice", text)

    reply = await grok.reply(uid, f"The user said (voice): {text}")
    log_chat(uid, "sophia", reply)
    await update.message.reply_text(reply)

# ================= PAYMENTS =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "buy_vip":
        await context.bot.send_invoice(
            chat_id=q.message.chat_id,
            title="VIP Sophia",
            description="Unlimited chat for 15 days",
            payload="vip_15",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP", VIP_PRICE_STARS)]
        )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    pid = update.message.successful_payment.telegram_payment_charge_id

    if r.exists(payment_key(pid)):
        return

    r.set(payment_key(pid), "ok")
    r.set(vip_key(uid), (datetime.now() + timedelta(days=VIP_DAYS)).isoformat())

    msg = "Payment approved! Your VIP is active 💖"
    log_chat(uid, "sophia", msg)
    await update.message.reply_text(msg)

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
application.add_handler(MessageHandler(filters.PHOTO, image_handler))
application.add_handler(MessageHandler(filters.VOICE, voice_handler))
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
    logger.info("🤖 Sophia Bot ONLINE (TEXT + IMAGE + AUDIO)")

asyncio.run_coroutine_threadsafe(setup(), loop)

# ================= FLASK =================
app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.json, application.bot)
    asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
