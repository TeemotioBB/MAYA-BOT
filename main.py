#!/usr/bin/env python3
"""
🔥 Sophia Bot — Railway + Grok + PushinPay
VIP mensal R$14,99 com liberação automática
v2.0 - Com Logs e Tratamento de Erro
"""

import os
import asyncio
import aiohttp
import sqlite3
import logging
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

# ================= CONFIGURAÇÃO DE LOGS =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("namorada_ia.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================= ENV =================
# Usa a chave do ambiente ou a fornecida pelo usuário como fallback
BACKUP_KEY = "xai-HQrz9YdxnAJ4MAQMFAPapxSALXwQ7QfHuBjzvH2uF6OqiZJi2QNLb0khYveAchzGarIs8zHe9ElNYbZy"
# Token do Telegram recuperado do backup
BACKUP_TELEGRAM_TOKEN = "8528168785:AAEvDjIGUjRyz8RAfJwM4Ygr7nG6aMF_eLM"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or BACKUP_TELEGRAM_TOKEN
GROK_API_KEY = os.getenv("GROK_API_KEY") or BACKUP_KEY
PUSHINPAY_TOKEN = os.getenv("PUSHINPAY_TOKEN")
WEBHOOK_SECRET = os.getenv("PUSHINPAY_WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", 8080))

# ================= CONFIG BOT =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-4-fast-reasoning"  # Modelo confirmado nos testes

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
    try:
        cur = db.cursor()
        cur.execute("SELECT active FROM vip_users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return bool(row and row[0] == 1)
    except Exception as e:
        logger.error(f"Erro ao verificar VIP: {e}")
        return False

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
        # Gerenciamento de histórico básico em memória
        hist = self.historico.setdefault(user_id, [])
        
        payload = {
            "model": GROK_MODEL,
            "messages": [
                {"role": "system", "content": SOPHIA_PERSONALIDADE},
                *hist[-10:], # Mantém apenas as últimas 10 interações
                {"role": "user", "content": mensagem}
            ],
            "max_tokens": 220,
            "temperature": 0.8
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROK_API_URL,
                    headers=self.headers,
                    json=payload,
                    timeout=20
                ) as r:
                    if r.status != 200:
                        error_text = await r.text()
                        logger.error(f"Erro API Grok ({r.status}): {error_text}")
                        # Verifica se é erro de chave
                        if r.status == 400 or r.status == 401:
                             logger.critical("VERIFIQUE A CHAVE DE API!")
                        return None
                    
                    data = await r.json()
                    resp = data["choices"][0]["message"]["content"]
                    
                    # Atualiza histórico apenas se sucesso
                    hist.append({"role": "user", "content": mensagem})
                    hist.append({"role": "assistant", "content": resp})
                    
                    return resp
        except Exception as e:
            logger.error(f"Exceção ao chamar Grok: {e}")
            return None

grok = GrokCerebro()

# ================= TELEGRAM =================
contador = {}
datas = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contador[user.id] = 0
    datas[user.id] = date.today()
    
    # Limpa histórico ao reiniciar
    if user.id in grok.historico:
        grok.historico[user.id] = []

    logger.info(f"Usuário iniciou: {user.first_name} (ID: {user.id})")

    await update.message.reply_text(
        f"Oi {user.first_name}! 💖\n"
        f"{'💎 Você é VIP' if is_vip(user.id) else '✨ Vamos conversar'}"
    )

def pode_falar(user_id):
    try:
        hoje = date.today()
        if datas.get(user_id) != hoje:
            datas[user_id] = hoje
            contador[user_id] = 0
        contador[user_id] += 1
        return contador[user_id] <= LIMITE_DIARIO
    except Exception as e:
        logger.error(f"Erro ao verificar limite: {e}")
        return True # Falha aberta

async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg_text = update.message.text

    if not is_vip(user.id):
        if not pode_falar(user.id):
            await update.message.reply_text(
                "💔 Seu limite terminou por hoje.\n\n"
                "💎 Para continuar comigo sem limites, adquira o VIP:\n"
                "https://app.pushinpay.com.br/service/pay/A0941D4B-2D0C-4E33-86F8-72A00B0D83B0"
            )
            return

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    
    logger.info(f"Mensagem de {user.first_name}: {msg_text}")
    
    resposta = await grok.perguntar(msg_text, user.id)
    
    if not resposta:
        logger.warning("Falha na resposta do Grok, usando fallback.")
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
    logger.info(f"Pagamento recebido: {tx_id}")

    try:
        cur = db.cursor()
        cur.execute("SELECT user_id FROM payments WHERE transaction_id = ?", (tx_id,))
        row = cur.fetchone()
        if not row:
            logger.warning(f"Transação {tx_id} não encontrada no DB.")
            return jsonify({"error": "transaction not found"}), 404

        user_id = row[0]
        cur.execute("""
            INSERT OR REPLACE INTO vip_users (user_id, active, paid_at)
            VALUES (?, 1, ?)
        """, (user_id, datetime.now().isoformat()))
        db.commit()
        logger.info(f"VIP ativado para user_id {user_id}")
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return jsonify({"error": "db error"}), 500

    return jsonify({"vip": "ativado"})

# ================= MAIN =================
def main():
    logger.info("Sophia Bot iniciando...")
    
    # Criar loop de evento explicitamente para evitar problemas com threads
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN não encontrado!")
        print("Defina o TELEGRAM_TOKEN no ambiente.")
        return

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))

    # Webhook em thread separada
    from threading import Thread
    server_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=PORT))
    server_thread.daemon = True
    server_thread.start()
    logger.info(f"Webhook rodando na porta {PORT}")

    logger.info("Bot Telegram Poll Iniciado")
    telegram_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
