#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
REDIS | VIP | TELEGRAM STARS | RAILWAY
MEMÓRIA CURTA REAL (SEM HALLUCINATION)
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

# ⚠️ Redis fixo (como solicitado)
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

# ================= CONFIG =================
LIMITE_DIARIO = 15
VIP_DIAS = 15
VIP_PRECO_STARS = 250

MODEL = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= MEMÓRIA CURTA =================
MAX_MEMORIA = 6  # 3 interações (user + bot)
memoria_curta = {}  # user_id -> deque

def get_memoria(uid: int):
    if uid not in memoria_curta:
        memoria_curta[uid] = deque(maxlen=MAX_MEMORIA)
    return memoria_curta[uid]

# ================= PROMPT =================
SOPHIA_PROMPT = """
Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica e afetuosa ❤️
Respostas curtas (2–3 frases).
Sempre faça perguntas.
Use emojis ocasionalmente 💖

REGRAS CRÍTICAS:
- Nunca invente fatos passados.
- Só lembre do que foi dito explicitamente nesta conversa.
- Se não houver memória suficiente, admita que não lembra.
- Nunca crie memórias falsas.
"""

# ================= GROK =================
class Grok:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }

    async def responder(self, uid: int, texto: str) -> str:
        mem = get_memoria(uid)

        messages = [
            {"role": "system", "content": SOPHIA_PROMPT},
            *list(mem),
            {"role": "user", "content": texto}
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
                resposta = data["choices"][0]["message"]["content"]

        # salva memória REAL
        mem.append({"role": "user", "content": texto})
        mem.append({"role": "assistant", "content": resposta})

        return resposta

grok = Grok()

# ================= REDIS KEYS =================
def vip_key(uid): return f"vip:{uid}"
def count_key(uid): return f"count:{uid}:{date.today()}"
def payment_key(pid): return f"payment:{pid}"

# ================= UTIL =================
def is_vip(uid: int) -> bool:
    until = r.get(vip_key(uid))
    return bool(until and datetime.fromisoformat(until) > datetime.now())

def count_today(uid: int) -> int:
    return int(r.get(count_key(uid)) or 0)

def inc_count(uid: int):
    key = count_key(uid)
    r.incr(key, 1)
    r.expire(key, 86400)

# ================= HANDLER TEXTO =================
async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    texto = update.message.text.strip()
    texto_lower = texto.lower()

    # 🧠 blindagem inteligente de memória
    gatilhos = ["você lembra", "vc lembra", "lembra do meu dia", "lembra de ontem"]

    if any(g in texto_lower for g in gatilhos):
        mem = get_memoria(uid)
        if len(mem) < 2:
            await update.message.reply_text(
                "Hmm… não lembro exatamente, amor 😅 Me conta de novo?"
            )
            return
        # se houver memória, deixa o Grok responder normalmente

    if not is_vip(uid) and count_today(uid) >= LIMITE_DIARIO:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="comprar_vip")]
        ])
        await update.message.reply_text(
            "💔 Seu limite de mensagens comigo acabou hoje, amor.\n"
            "Volte amanhã ou vire VIP pra continuar comigo 💖",
            reply_markup=keyboard
        )
        return

    inc_count(uid)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    resposta = await grok.responder(uid, texto)
    await update.message.reply_text(resposta)

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "comprar_vip":
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="VIP Sophia 💖",
            description="Conversa ilimitada por 15 dias",
            payload="vip_15_dias",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP 15 dias", VIP_PRECO_STARS)]
        )

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def pagamento_sucesso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    uid = update.effective_user.id
    pid = payment.telegram_payment_charge_id

    if r.exists(payment_key(pid)):
        return

    r.set(payment_key(pid), "ok")

    vip_until = datetime.now() + timedelta(days=VIP_DIAS)
    r.set(vip_key(uid), vip_until.isoformat())

    r.rpush(
        "faturamento",
        f"{uid}|{VIP_PRECO_STARS}|{datetime.now().isoformat()}"
    )

    await update.message.reply_text(
        "💖 Pagamento aprovado!\nSeu VIP está ativo por 15 dias 😘"
    )

# ================= AVISO VIP =================
async def avisar_vip_expirando(application: Application):
    while True:
        for key in r.scan_iter("vip:*"):
            uid = int(key.split(":")[1])
            until = datetime.fromisoformat(r.get(key))

            if 0 < (until - datetime.now()).days == 1:
                try:
                    await application.bot.send_message(
                        chat_id=uid,
                        text="⏰ Amor, seu VIP acaba amanhã 💔\nRenove pra continuar comigo 💖"
                    )
                except:
                    pass
        await asyncio.sleep(3600)

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, pagamento_sucesso))

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
    loop.create_task(avisar_vip_expirando(application))
    logger.info("🤖 Sophia Bot ONLINE com memória curta funcional")

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
    logger.info("🚀 Iniciando Sophia Bot (MEMÓRIA CORRETA)")
    app.run(host="0.0.0.0", port=PORT)
#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Grok 4 Fast Reasoning
REDIS | VIP | TELEGRAM STARS | RAILWAY
MEMÓRIA CURTA REAL (SEM HALLUCINATION)
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

# ⚠️ Redis fixo (como solicitado)
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

# ================= CONFIG =================
LIMITE_DIARIO = 15
VIP_DIAS = 15
VIP_PRECO_STARS = 250

MODEL = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= MEMÓRIA CURTA =================
MAX_MEMORIA = 6  # 3 interações (user + bot)
memoria_curta = {}  # user_id -> deque

def get_memoria(uid: int):
    if uid not in memoria_curta:
        memoria_curta[uid] = deque(maxlen=MAX_MEMORIA)
    return memoria_curta[uid]

# ================= PROMPT =================
SOPHIA_PROMPT = """
Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica e afetuosa ❤️
Respostas curtas (2–3 frases).
Sempre faça perguntas.
Use emojis ocasionalmente 💖

REGRAS CRÍTICAS:
- Nunca invente fatos passados.
- Só lembre do que foi dito explicitamente nesta conversa.
- Se não houver memória suficiente, admita que não lembra.
- Nunca crie memórias falsas.
"""

# ================= GROK =================
class Grok:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }

    async def responder(self, uid: int, texto: str) -> str:
        mem = get_memoria(uid)

        messages = [
            {"role": "system", "content": SOPHIA_PROMPT},
            *list(mem),
            {"role": "user", "content": texto}
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
                resposta = data["choices"][0]["message"]["content"]

        # salva memória REAL
        mem.append({"role": "user", "content": texto})
        mem.append({"role": "assistant", "content": resposta})

        return resposta

grok = Grok()

# ================= REDIS KEYS =================
def vip_key(uid): return f"vip:{uid}"
def count_key(uid): return f"count:{uid}:{date.today()}"
def payment_key(pid): return f"payment:{pid}"

# ================= UTIL =================
def is_vip(uid: int) -> bool:
    until = r.get(vip_key(uid))
    return bool(until and datetime.fromisoformat(until) > datetime.now())

def count_today(uid: int) -> int:
    return int(r.get(count_key(uid)) or 0)

def inc_count(uid: int):
    key = count_key(uid)
    r.incr(key, 1)
    r.expire(key, 86400)

# ================= HANDLER TEXTO =================
async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    texto = update.message.text.strip()
    texto_lower = texto.lower()

    # 🧠 blindagem inteligente de memória
    gatilhos = ["você lembra", "vc lembra", "lembra do meu dia", "lembra de ontem"]

    if any(g in texto_lower for g in gatilhos):
        mem = get_memoria(uid)
        if len(mem) < 2:
            await update.message.reply_text(
                "Hmm… não lembro exatamente, amor 😅 Me conta de novo?"
            )
            return
        # se houver memória, deixa o Grok responder normalmente

    if not is_vip(uid) and count_today(uid) >= LIMITE_DIARIO:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💖 Comprar VIP – 1 ⭐", callback_data="comprar_vip")]
        ])
        await update.message.reply_text(
            "💔 Seu limite de mensagens comigo acabou hoje, amor.\n"
            "Volte amanhã ou vire VIP pra continuar comigo 💖",
            reply_markup=keyboard
        )
        return

    inc_count(uid)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    resposta = await grok.responder(uid, texto)
    await update.message.reply_text(resposta)

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "comprar_vip":
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="VIP Sophia 💖",
            description="Conversa ilimitada por 15 dias",
            payload="vip_15_dias",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP 15 dias", VIP_PRECO_STARS)]
        )

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def pagamento_sucesso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    uid = update.effective_user.id
    pid = payment.telegram_payment_charge_id

    if r.exists(payment_key(pid)):
        return

    r.set(payment_key(pid), "ok")

    vip_until = datetime.now() + timedelta(days=VIP_DIAS)
    r.set(vip_key(uid), vip_until.isoformat())

    r.rpush(
        "faturamento",
        f"{uid}|{VIP_PRECO_STARS}|{datetime.now().isoformat()}"
    )

    await update.message.reply_text(
        "💖 Pagamento aprovado!\nSeu VIP está ativo por 15 dias 😘"
    )

# ================= AVISO VIP =================
async def avisar_vip_expirando(application: Application):
    while True:
        for key in r.scan_iter("vip:*"):
            uid = int(key.split(":")[1])
            until = datetime.fromisoformat(r.get(key))

            if 0 < (until - datetime.now()).days == 1:
                try:
                    await application.bot.send_message(
                        chat_id=uid,
                        text="⏰ Amor, seu VIP acaba amanhã 💔\nRenove pra continuar comigo 💖"
                    )
                except:
                    pass
        await asyncio.sleep(3600)

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, pagamento_sucesso))

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
    loop.create_task(avisar_vip_expirando(application))
    logger.info("🤖 Sophia Bot ONLINE com memória curta funcional")

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
    logger.info("🚀 Iniciando Sophia Bot (MEMÓRIA CORRETA)")
    app.run(host="0.0.0.0", port=PORT)
ION)
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

# ⚠️ Redis fixo (como solicitado)
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

# ================= CONFIG =================
LIMITE_DIARIO = 15
VIP_DIAS = 15
VIP_PRECO_STARS = 1

MODEL = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= MEMÓRIA CURTA =================
MAX_MEMORIA = 6  # 3 interações (user + bot)
memoria_curta = {}  # user_id -> deque

def get_memoria(uid: int):
    if uid not in memoria_curta:
        memoria_curta[uid] = deque(maxlen=MAX_MEMORIA)
    return memoria_curta[uid]

# ================= PROMPT =================
SOPHIA_PROMPT = """
Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica e afetuosa ❤️
Respostas curtas (2–3 frases).
Sempre faça perguntas.
Use emojis ocasionalmente 💖

REGRAS CRÍTICAS:
- Nunca invente fatos passados.
- Só lembre do que foi dito explicitamente nesta conversa.
- Se não houver memória suficiente, admita que não lembra.
- Nunca crie memórias falsas.
"""

# ================= GROK =================
class Grok:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }

    async def responder(self, uid: int, texto: str) -> str:
        mem = get_memoria(uid)

        messages = [
            {"role": "system", "content": SOPHIA_PROMPT},
            *list(mem),
            {"role": "user", "content": texto}
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
                resposta = data["choices"][0]["message"]["content"]

        # salva memória REAL
        mem.append({"role": "user", "content": texto})
        mem.append({"role": "assistant", "content": resposta})

        return resposta

grok = Grok()

# ================= REDIS KEYS =================
def vip_key(uid): return f"vip:{uid}"
def count_key(uid): return f"count:{uid}:{date.today()}"
def payment_key(pid): return f"payment:{pid}"

# ================= UTIL =================
def is_vip(uid: int) -> bool:
    until = r.get(vip_key(uid))
    return bool(until and datetime.fromisoformat(until) > datetime.now())

def count_today(uid: int) -> int:
    return int(r.get(count_key(uid)) or 0)

def inc_count(uid: int):
    key = count_key(uid)
    r.incr(key, 1)
    r.expire(key, 86400)

# ================= HANDLER TEXTO =================
async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    texto = update.message.text.strip()
    texto_lower = texto.lower()

    # 🧠 blindagem inteligente de memória
    gatilhos = ["você lembra", "vc lembra", "lembra do meu dia", "lembra de ontem"]

    if any(g in texto_lower for g in gatilhos):
        mem = get_memoria(uid)
        if len(mem) < 2:
            await update.message.reply_text(
                "Hmm… não lembro exatamente, amor 😅 Me conta de novo?"
            )
            return
        # se houver memória, deixa o Grok responder normalmente

    if not is_vip(uid) and count_today(uid) >= LIMITE_DIARIO:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="comprar_vip")]
        ])
        await update.message.reply_text(
            "💔 Seu limite de mensagens comigo acabou hoje, amor.\n"
            "Volte amanhã ou vire VIP pra continuar comigo 💖",
            reply_markup=keyboard
        )
        return

    inc_count(uid)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    resposta = await grok.responder(uid, texto)
    await update.message.reply_text(resposta)

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "comprar_vip":
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="VIP Sophia 💖",
            description="Conversa ilimitada por 15 dias",
            payload="vip_15_dias",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("VIP 15 dias", VIP_PRECO_STARS)]
        )

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def pagamento_sucesso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    uid = update.effective_user.id
    pid = payment.telegram_payment_charge_id

    if r.exists(payment_key(pid)):
        return

    r.set(payment_key(pid), "ok")

    vip_until = datetime.now() + timedelta(days=VIP_DIAS)
    r.set(vip_key(uid), vip_until.isoformat())

    r.rpush(
        "faturamento",
        f"{uid}|{VIP_PRECO_STARS}|{datetime.now().isoformat()}"
    )

    await update.message.reply_text(
        "💖 Pagamento aprovado!\nSeu VIP está ativo por 15 dias 😘"
    )

# ================= AVISO VIP =================
async def avisar_vip_expirando(application: Application):
    while True:
        for key in r.scan_iter("vip:*"):
            uid = int(key.split(":")[1])
            until = datetime.fromisoformat(r.get(key))

            if 0 < (until - datetime.now()).days == 1:
                try:
                    await application.bot.send_message(
                        chat_id=uid,
                        text="⏰ Amor, seu VIP acaba amanhã 💔\nRenove pra continuar comigo 💖"
                    )
                except:
                    pass
        await asyncio.sleep(3600)

# ================= APP =================
application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, pagamento_sucesso))

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
    loop.create_task(avisar_vip_expirando(application))
    logger.info("🤖 Sophia Bot ONLINE com memória curta funcional")

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
    logger.info("🚀 Iniciando Sophia Bot (MEMÓRIA CORRETA)")
    app.run(host="0.0.0.0", port=PORT)
