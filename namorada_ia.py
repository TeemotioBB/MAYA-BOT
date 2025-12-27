#!/usr/bin/env python3
"""
🔥 Sophia Bot — Railway + Grok + PushinPay
VIP mensal R$14,99 com liberação automática
"""

import os
import asyncio
import aiohttp
import sqlite3
from datetime import datetime, date
from flask import Flask, request, jsonify, abort
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("8528168785:AAEvDjIGUjRyz8RAfJwM4Ygr7nG6aMF_eLM")
GROK_API_KEY = os.getenv("xai-WhzRhOWLna2aUD3A3Sv3siXwqVCTpIP9j5X1KNe1m8N7QB89Dzh20edMiTZbhB9tSaX4aMRKmCwsdpnD")
PUSHINPAY_TOKEN = os.getenv("57758|Fd6yYTFbVw3meItiYnLjxnRN9W7i4jF467f4GfJj0fc9a3f5")
WEBHOOK_SECRET = os.getenv("PUSHINPAY_WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", 8080))

# ================= CONFIG =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-4-fast-reasoning"

VIP_PRICE_CENTS = 1499
LIMITE_DIARIO = 15

# ================= DB =================
def get_db():
    conn = sqlite3.connect("database.db", check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            transaction_id TEXT PRIMARY KEY,
            user_id INTEGER,
            status TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vip_users (
            user_id INTEGER PRIMARY KEY,
            active INTEGER,
            paid_at TEXT
        )
    """)
    return conn

db = get_db()

def is_vip(user_id: int) -> bool:
    cur = db.cursor()
    cur.execute("SELECT active FROM vip_users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return bool(row and row[0] == 1)

# ================= GROK =================
SOPHIA_PERSONALIDADE = """Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica, afetuosa ❤️
Respostas curtas e naturais
Sempre faz perguntas
Se perguntarem onde você mora, diga que vive viajando o mundo 🌍✈️
"""

class GrokCerebro:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }
        self.historico = {}

    async def perguntar(self, mensagem, user_id):
        hist = self.historico.setdefault(user_id, [])
        payload = {
            "model": GROK_MODEL,
            "messages": [
                {"role": "system", "content": SOPHIA_PERSONALIDADE},
                *hist[-10:],
                {"role": "user", "content": mensagem}
            ],
            "max_tokens": 220,
            "temperature": 0.8
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROK_API_URL,
                headers=self.headers,
                json=payload,
                timeout=20
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                resp = data["choices"][0]["message"]["content"]
                hist.append({"role": "user", "content": mensagem})
                hist.append({"role": "assistant", "content": resp})
                return resp

grok = GrokCerebro()

# ================= TELEGRAM =================
contador = {}
datas = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contador[user.id] = 0
    datas[user.id] = date.today()

    await update.message.reply_text(
        f"Oi {user.first_name}! 💖\n"
        f"{'💎 Você é VIP' if is_vip(user.id) else '✨ Vamos conversar'}"
    )

def pode_falar(user_id):
    hoje = date.today()
    if datas.get(user_id) != hoje:
        datas[user_id] = hoje
        contador[user_id] = 0
    contador[user_id] += 1
    return contador[user_id] <= LIMITE_DIARIO

async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_vip(user.id):
        if not pode_falar(user.id):
            await update.message.reply_text(
                "💔 Seu limite terminou por hoje.\n\n"
                "💎 Para continuar comigo sem limites, adquira o VIP:\n"
                "https://app.pushinpay.com.br/service/pay/A0941D4B-2D0C-4E33-86F8-72A00B0D83B0"
            )
            return

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    resposta = await grok.perguntar(update.message.text, user.id)
    if not resposta:
        resposta = "Tô aqui com você ❤️ Me conta mais…"
    await update.message.reply_text(resposta)

# ================= FLASK WEBHOOK =================
app = Flask(__name__)

@app.route("/webhook/pushinpay", methods=["POST"])
def pushinpay_webhook():
    if request.headers.get("X-PushinPay-Secret") != WEBHOOK_SECRET:
        abort(403)

    data = request.json
    if data.get("status") != "paid":
        return jsonify({"ok": True})

    tx_id = data["id"]

    cur = db.cursor()
    cur.execute("SELECT user_id FROM payments WHERE transaction_id = ?", (tx_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "transaction not found"}), 404

    user_id = row[0]
    cur.execute("""
        INSERT OR REPLACE INTO vip_users (user_id, active, paid_at)
        VALUES (?, 1, ?)
    """, (user_id, datetime.now().isoformat()))
    db.commit()

    return jsonify({"vip": "ativado"})

# ================= MAIN =================
def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))

    from threading import Thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=PORT)).start()

    telegram_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
